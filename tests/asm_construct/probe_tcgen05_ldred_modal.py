#!/usr/bin/env python3
"""Run the hand-assembled LDTM.STAT semantic probe on B200 and B300.

B300 executes a native sm103 cubin produced solely by this repository's
assembler.  For B200, build an sm100 cubin with ordinary-LDTM placeholders and
replace just those 128-bit words with the corresponding sm103 LDTM.STAT words.
This tests the opcode on B200 without confounding it with an sm103 ELF rejection.

Run in the authenticated environment::

    /home/cicuvc/miniconda3/envs/blkw/bin/modal run \
      tests/asm_construct/probe_tcgen05_ldred_modal.py
"""

from __future__ import annotations

import ctypes
import struct
import tempfile
from pathlib import Path

import modal


_HERE = Path(__file__).resolve()
# Modal mounts this one file at /root; repository paths are needed only by the
# local entrypoint, but module import must also succeed in the remote worker.
ROOT = _HERE.parents[2] if len(_HERE.parents) > 2 else Path.cwd()
SOURCE = Path(__file__).with_name(
    "tcgen05_ldred_semantics_sm103.sass")
OUTPUT_WORDS = 25

CUDA_IMAGE = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11"
    ).entrypoint([])
)
app = modal.App("tcgen05-ldred-semantics", image=CUDA_IMAGE)


def _run(cubin: bytes, function_name: str) -> dict[str, object]:
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

    def error(code: int, call: str) -> dict[str, object]:
        name, desc = ctypes.c_char_p(), ctypes.c_char_p()
        cuda.cuGetErrorName(code, ctypes.byref(name))
        cuda.cuGetErrorString(code, ctypes.byref(desc))
        return {
            "ok": False,
            "stage": call,
            "code": code,
            "name": name.value.decode() if name.value else "?",
            "description": desc.value.decode() if desc.value else "?",
        }

    cuda.cuInit.argtypes = [ctypes.c_uint]
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(CUdevice), ctypes.c_int]
    cuda.cuCtxCreate_v2.argtypes = [ctypes.POINTER(CUcontext), ctypes.c_uint,
                                    CUdevice]
    cuda.cuCtxDestroy_v2.argtypes = [CUcontext]
    cuda.cuModuleLoadData.argtypes = [ctypes.POINTER(CUmodule), ctypes.c_void_p]
    cuda.cuModuleUnload.argtypes = [CUmodule]
    cuda.cuModuleGetFunction.argtypes = [ctypes.POINTER(CUfunction), CUmodule,
                                         ctypes.c_char_p]
    cuda.cuMemAlloc_v2.argtypes = [ctypes.POINTER(CUdeviceptr), ctypes.c_size_t]
    cuda.cuMemFree_v2.argtypes = [CUdeviceptr]
    cuda.cuMemsetD32_v2.argtypes = [CUdeviceptr, ctypes.c_uint, ctypes.c_size_t]
    cuda.cuLaunchKernel.argtypes = [
        CUfunction, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
    ]
    cuda.cuCtxSynchronize.argtypes = []
    cuda.cuMemcpyDtoH_v2.argtypes = [ctypes.c_void_p, CUdeviceptr,
                                     ctypes.c_size_t]

    code = cuda.cuInit(0)
    if code:
        return error(code, "cuInit")
    dev, ctx = CUdevice(), CUcontext()
    code = cuda.cuDeviceGet(ctypes.byref(dev), 0)
    if code:
        return error(code, "cuDeviceGet")
    code = cuda.cuCtxCreate_v2(ctypes.byref(ctx), 0, dev)
    if code:
        return error(code, "cuCtxCreate")
    module, allocation = CUmodule(), CUdeviceptr()
    try:
        blob = ctypes.create_string_buffer(cubin)
        code = cuda.cuModuleLoadData(
            ctypes.byref(module), ctypes.cast(blob, ctypes.c_void_p))
        if code:
            return error(code, "cuModuleLoadData")
        function = CUfunction()
        mangled = f"_Z{len(function_name)}{function_name}".encode()
        code = cuda.cuModuleGetFunction(
            ctypes.byref(function), module, mangled)
        if code == 500:  # extern "C" kernels retain the plain symbol name
            code = cuda.cuModuleGetFunction(
                ctypes.byref(function), module, function_name.encode())
        if code:
            return error(code, "cuModuleGetFunction")
        nbytes = OUTPUT_WORDS * 4
        code = cuda.cuMemAlloc_v2(ctypes.byref(allocation), nbytes)
        if code:
            return error(code, "cuMemAlloc")
        code = cuda.cuMemsetD32_v2(allocation, 0xdeadbeef, OUTPUT_WORDS)
        if code:
            return error(code, "cuMemsetD32")
        arg0 = CUdeviceptr(allocation.value)
        params = (ctypes.c_void_p * 1)(
            ctypes.cast(ctypes.byref(arg0), ctypes.c_void_p))
        code = cuda.cuLaunchKernel(function, 1, 1, 1, 32, 1, 1, 0, None,
                                   params, None)
        if code:
            return error(code, "cuLaunchKernel")
        code = cuda.cuCtxSynchronize()
        if code:
            return error(code, "cuCtxSynchronize")
        host = (ctypes.c_uint32 * OUTPUT_WORDS)()
        code = cuda.cuMemcpyDtoH_v2(
            ctypes.byref(host), allocation, ctypes.sizeof(host))
        if code:
            return error(code, "cuMemcpyDtoH")
        return {"ok": True, "words": list(host)}
    finally:
        if allocation.value:
            cuda.cuMemFree_v2(allocation)
        if module.value:
            cuda.cuModuleUnload(module)
        cuda.cuCtxDestroy_v2(ctx)


@app.function(gpu="B200", image=CUDA_IMAGE, timeout=120)
def run_b200(cubin: bytes, function_name: str) -> dict[str, object]:
    return _run(cubin, function_name)


@app.function(gpu="B300", image=CUDA_IMAGE, timeout=120)
def run_b300(cubin: bytes, function_name: str) -> dict[str, object]:
    return _run(cubin, function_name)


def _sm100_placeholder_source(source: str) -> str:
    replacements = {
        "LDTM.STAT.x4.MAX R40, {R36,R37,R38,R39}, tmem[UR10]":
            "LDTM.x4 {R36,R37,R38,R39}, tmem[UR10]",
        "LDTM.STAT.x4.MIN.S32 R52, {R48,R49,R50,R51}, tmem[UR10]":
            "LDTM.x4 {R48,R49,R50,R51}, tmem[UR10]",
        "LDTM.STAT.x4.MAXABS.F32.NAN R64, {R60,R61,R62,R63}, tmem[UR10]":
            "LDTM.x4 {R60,R61,R62,R63}, tmem[UR10]",
        "LDTM.STAT.x4.MINABS.F32 R76, {R72,R73,R74,R75}, tmem[UR10]":
            "LDTM.x4 {R72,R73,R74,R75}, tmem[UR10]",
        "LDTM.STAT.16dp32bit_t0_t15.x4.MIN R88, {R84,R85,R86,R87}, tmem[UR10]":
            "LDTM.16dp32bit_t0_t15.x4 {R84,R85,R86,R87}, tmem[UR10]",
        "LDTM.STAT.16dp32bit_t16_t31.x4.MIN R88, {R84,R85,R86,R87}, tmem[UR10+0x10]":
            "LDTM.16dp32bit_t16_t31.x4 {R84,R85,R86,R87}, tmem[UR10+0x10]",
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise AssertionError(f"placeholder anchor count != 1: {old}")
        source = source.replace(old, new)
    return source


def _patch_b200(sm100_result, sm103_result) -> bytes:
    """Copy only sm103 LDTM.STAT words into the sm100 text section."""
    from sassdbg.cubin import load_kernel

    if len(sm100_result.encoded) != len(sm103_result.encoded):
        raise AssertionError("sm100/sm103 expanded instruction counts differ")
    data = bytearray(sm100_result.code)
    with tempfile.NamedTemporaryFile(suffix=".cubin") as tmp:
        tmp.write(data)
        tmp.flush()
        kernel = load_kernel(tmp.name, sm100_result.kernel_name)
    patched = []
    for i, (lo, hi) in enumerate(sm103_result.encoded):
        opcode = (((hi >> (91 - 64)) & 1) << 12) | (lo & 0xfff)
        if opcode != 0x15ee:
            continue
        struct.pack_into("<QQ", data, kernel.file_off + i * 16, lo, hi)
        patched.append(i)
    if len(patched) != 6:
        raise AssertionError(f"expected six LDTM.STAT words, got {patched}")
    return bytes(data)


def _is_nan(bits: int) -> bool:
    return bits & 0x7f800000 == 0x7f800000 and bits & 0x007fffff != 0


def _check_b300(result: dict[str, object]) -> dict[str, object]:
    if not result.get("ok"):
        return result
    words = result["words"]
    expected = (
        ("u32_max", [9, 2, 15, 4], 15),
        ("s32_min", [0xfffffffb, 7, 0xffffffec, 3], 0xffffffec),
        ("f32_maxabs_nan", [0x3f800000, 0xc0800000,
                            0x7fc12345, 0x40000000], None),
        ("f32_minabs", [0x40800000, 0xc0000000,
                        0x3f000000, 0xc1000000], 0x3f000000),
        ("split_u32_min", [9, 2, 15, 4], 2),
    )
    failures = []
    red_values = {name: set() for name, _, _ in expected}
    for case, (name, vector, red) in enumerate(expected):
        got = words[case * 5:case * 5 + 5]
        red_values[name].add(got[4])
        red_ok = _is_nan(got[4]) if red is None else got[4] == red
        if got[:4] != vector or not red_ok:
            failures.append({"case": name, "got": [hex(x) for x in got]})
    return {
        "ok": not failures,
        "failures": failures[:8],
        "red_values": {
            name: [hex(x) for x in sorted(values)]
            for name, values in red_values.items()
        },
        "lane0": [hex(x) for x in words],
    }


@app.local_entrypoint()
def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from assembler import assemble_kernel

    source = SOURCE.read_text()
    sm103 = assemble_kernel(source, arch="sm103a", check_deps=False)
    sm100 = assemble_kernel(_sm100_placeholder_source(source), arch="sm100a",
                            check_deps=False)
    b200_raw = _patch_b200(sm100, sm103)
    print({
        "assembler": {
            "sm103_instructions": len(sm103.encoded),
            "sm100_instructions": len(sm100.encoded),
            "ldtm_stat_words_patched_into_sm100": 6,
        }
    })
    print({"B300": _check_b300(
        run_b300.remote(sm103.code, sm103.kernel_name))})
    b200_result = run_b200.remote(b200_raw, sm100.kernel_name)
    b200_result.pop("words", None)
    print({"B200_raw_opcode": b200_result})
