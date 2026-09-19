#!/usr/bin/env python3
"""Run the assembler-native UTCLDSWS allocator-state probe on Modal B200."""

from __future__ import annotations

import ctypes
from pathlib import Path

import modal


HERE = Path(__file__).resolve()
ROOT = HERE.parents[2] if len(HERE.parents) > 2 else Path.cwd()
SOURCE = HERE.with_name("utcldsws_allocator_state_sm100.sass")
NWORDS = 10

IMAGE = modal.Image.from_registry(
    "nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11"
).entrypoint([])
app = modal.App("utcldsws-allocator-state", image=IMAGE)


@app.function(gpu="B200", timeout=120)
def run_probe(cubin: bytes, function_name: str) -> dict[str, object]:
    cuda = ctypes.CDLL("libcuda.so.1")
    CUdevice = ctypes.c_int
    CUcontext = ctypes.c_void_p
    CUmodule = ctypes.c_void_p
    CUfunction = ctypes.c_void_p
    CUdeviceptr = ctypes.c_uint64

    cuda.cuGetErrorName.argtypes = [ctypes.c_int,
                                    ctypes.POINTER(ctypes.c_char_p)]
    cuda.cuGetErrorString.argtypes = [ctypes.c_int,
                                      ctypes.POINTER(ctypes.c_char_p)]

    def check(code: int, call: str) -> None:
        if not code:
            return
        name, desc = ctypes.c_char_p(), ctypes.c_char_p()
        cuda.cuGetErrorName(code, ctypes.byref(name))
        cuda.cuGetErrorString(code, ctypes.byref(desc))
        raise RuntimeError(
            f"{call}: {code} "
            f"{name.value.decode() if name.value else '?'}: "
            f"{desc.value.decode() if desc.value else '?'}")

    cuda.cuInit.argtypes = [ctypes.c_uint]
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(CUdevice), ctypes.c_int]
    cuda.cuCtxCreate_v2.argtypes = [ctypes.POINTER(CUcontext), ctypes.c_uint,
                                    CUdevice]
    cuda.cuModuleLoadData.argtypes = [ctypes.POINTER(CUmodule), ctypes.c_void_p]
    cuda.cuModuleGetFunction.argtypes = [ctypes.POINTER(CUfunction), CUmodule,
                                         ctypes.c_char_p]
    cuda.cuMemAlloc_v2.argtypes = [ctypes.POINTER(CUdeviceptr), ctypes.c_size_t]
    cuda.cuMemsetD32_v2.argtypes = [CUdeviceptr, ctypes.c_uint, ctypes.c_size_t]
    cuda.cuLaunchKernel.argtypes = [
        CUfunction, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
    ]
    cuda.cuCtxSynchronize.argtypes = []
    cuda.cuMemcpyDtoH_v2.argtypes = [ctypes.c_void_p, CUdeviceptr,
                                     ctypes.c_size_t]

    check(cuda.cuInit(0), "cuInit")
    dev, ctx = CUdevice(), CUcontext()
    check(cuda.cuDeviceGet(ctypes.byref(dev), 0), "cuDeviceGet")
    check(cuda.cuCtxCreate_v2(ctypes.byref(ctx), 0, dev), "cuCtxCreate")
    module, allocation = CUmodule(), CUdeviceptr()
    blob = ctypes.create_string_buffer(cubin)
    check(cuda.cuModuleLoadData(
        ctypes.byref(module), ctypes.cast(blob, ctypes.c_void_p)),
        "cuModuleLoadData")
    function = CUfunction()
    symbol = f"_Z{len(function_name)}{function_name}".encode()
    check(cuda.cuModuleGetFunction(
        ctypes.byref(function), module, symbol), "cuModuleGetFunction")
    check(cuda.cuMemAlloc_v2(
        ctypes.byref(allocation), NWORDS * 4), "cuMemAlloc")
    check(cuda.cuMemsetD32_v2(
        allocation, 0xdeadbeef, NWORDS), "cuMemsetD32")
    arg0 = CUdeviceptr(allocation.value)
    params = (ctypes.c_void_p * 1)(
        ctypes.cast(ctypes.byref(arg0), ctypes.c_void_p))
    check(cuda.cuLaunchKernel(
        function, 1, 1, 1, 32, 1, 1, 0, None, params, None),
        "cuLaunchKernel")
    check(cuda.cuCtxSynchronize(), "cuCtxSynchronize")
    host = (ctypes.c_uint32 * NWORDS)()
    check(cuda.cuMemcpyDtoH_v2(
        ctypes.byref(host), allocation, ctypes.sizeof(host)), "cuMemcpyDtoH")
    return {"words": list(host)}


@app.local_entrypoint()
def main(minimal: bool = False, stage: str = "full") -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from assembler import assemble_kernel

    source = SOURCE.read_text()
    if minimal:
        source = r"""
#fn utcldsws_state(out<8>) {
    #pragma MAXREG_COUNT(16)
    UTCLDSWS UR10;[0:7:{}:1:0]
    IMAD.U32 R0, RZ, RZ, UR10;[7:7:{0}:4:1]
    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
    LDCU.64 {UR6,UR7}, #spec_const(SLOT_DEFAULT_CDESC);[2:7:{}:1:0]
    STG.E desc[{UR6,UR7}][{R2,R3}], R0;[7:7:{1,2}:8:0]
    EXIT;[7:7:{}:5:0]
}
"""
    elif stage == "storeload":
        source = r"""
#fn utcldsws_state(out<8>) {
    #pragma MAXREG_COUNT(16)
    UMOV UR10, 0xa5a55a5a;[7:7:{}:1:0]
    UTCSTSWS UR10;[0:7:{}:1:0]
    UTCLDSWS UR11;[1:7:{0}:1:0]
    UTCSTSWS URZ;[0:7:{1}:1:0]
    IMAD.U32 R0, RZ, RZ, UR11;[7:7:{1}:4:1]
    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
    LDCU.64 {UR6,UR7}, #spec_const(SLOT_DEFAULT_CDESC);[2:7:{}:1:0]
    STG.E desc[{UR6,UR7}][{R2,R3}], R0;[7:7:{0,1,2}:8:0]
    EXIT;[7:7:{}:5:0]
}
"""
    elif stage == "smoke":
        source = HERE.with_name("tcgen05_builtin_alloc_v1_sm100.sass").read_text()
    elif stage != "full":
        if stage not in ("control", "before", "after_alloc", "after_free"):
            raise ValueError(
                "stage must be full, smoke, control, before, after_alloc, or "
                "after_free")
        snapshot = "" if stage == "control" else """
    UTCLDSWS UR20;[0:7:{}:1:0]
    IMAD.U32 R8, RZ, RZ, UR20;[7:7:{0}:4:1]
"""
        if stage == "control":
            snapshot = "    IMAD.MOV.U32 R8, RZ, RZ, 0xc0117001;[7:7:{}:4:1]\n"
        snapshot += """
    LDS R10, [UR8+0x10];[0:7:{}:1:0]
    IMAD.MOV.U32 R11, RZ, RZ, RZ;[7:7:{}:4:1]
    LDS.U8 R12, [UR8];[0:7:{}:1:0]
"""
        alloc = "    #!tmem_alloc_1cta(UR5, 32)\n"
        dealloc = "    #!tmem_dealloc_1cta(UR5, 32)\n"
        if stage == "before":
            body = snapshot + alloc + dealloc
        elif stage == "after_alloc":
            body = alloc + snapshot + dealloc
        else:
            body = alloc + dealloc + snapshot
        source = f"""
#fn utcldsws_state(out<8>) {{
    #pragma SHARED(4)
    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)
    #pragma MAXREG_COUNT(48)
    LDC R1, c[0x0][0x37c];[7:7:{{}}:8:0]
    S2UR UR5, SR_CgaCtaId;[0:7:{{}}:1:0]
    UMOV UR4, 0x400;[7:7:{{}}:1:0]
    ULEA UR5, UR5, UR4, 0x18;[7:7:{{0}}:9:1]
    S2UR UR8, SR_CgaCtaId;[0:7:{{}}:1:0]
    UMOV UR9, 0x40;[7:7:{{}}:1:0]
    ULEA UR8, UR8, UR9, 0x18;[7:7:{{0}}:9:1]
{body}
    LDS R9, [UR5];[0:7:{{}}:1:0]
    LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
    LDCU.64 {{UR6,UR7}}, #spec_const(SLOT_DEFAULT_CDESC);[2:7:{{}}:1:0]
    STG.E desc[{{UR6,UR7}}][{{R2,R3}}+0x00], R8;[7:7:{{0,1,2}}:8:0]
    STG.E desc[{{UR6,UR7}}][{{R2,R3}}+0x04], R9;[7:7:{{}}:8:0]
    STG.E desc[{{UR6,UR7}}][{{R2,R3}}+0x08], R10;[7:7:{{}}:8:0]
    STG.E desc[{{UR6,UR7}}][{{R2,R3}}+0x0c], R11;[7:7:{{}}:8:0]
    STG.E desc[{{UR6,UR7}}][{{R2,R3}}+0x10], R12;[7:7:{{}}:8:0]
    #!tmem_relinquish_alloc_permit_1cta()
    EXIT;[7:7:{{}}:5:0]
}}
"""
    result = assemble_kernel(source, arch="sm100a", check_deps=False)
    raw = run_probe.remote(result.code, result.kernel_name)["words"]
    if minimal:
        print({"sws": f"0x{raw[0]:08x}"})
        return
    if stage == "storeload":
        print({"stage": stage, "sws": f"0x{raw[0]:08x}"})
        return
    if stage == "smoke":
        print({"stage": stage, "taddr": f"0x{raw[0]:08x}"})
        return
    if stage != "full":
        print({
            "stage": stage,
            "sws": f"0x{raw[0]:08x}",
            "taddr": f"0x{raw[1]:08x}",
            "allocator_mask": f"0x{raw[2]:08x}",
            "occupied": f"0x{raw[2] & 0xffff:04x}",
            "head": f"0x{raw[2] >> 16:04x}",
            "phase": f"0x{raw[4]:08x}",
        })
        return
    labels = (
        "sws_before", "allocator_mask_before", "phase_before",
        "sws_alloc", "taddr", "allocator_mask_alloc", "phase_alloc",
        "sws_free", "allocator_mask_free", "phase_free",
    )
    values = dict(zip(labels, (f"0x{x:08x}" for x in raw)))
    taddr = raw[4]
    bit = 1 << ((taddr & 0xffff) >> 5)
    values["expected_unit_bit"] = f"0x{bit:08x}"
    values["sws_alloc_xor_before"] = f"0x{raw[3] ^ raw[0]:08x}"
    values["sws_free_xor_alloc"] = f"0x{raw[7] ^ raw[3]:08x}"
    print(values)
