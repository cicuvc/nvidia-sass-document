#!/usr/bin/env python3
"""Phased B200 V1/V2 entry-fragment capture.

Each phase runs in a fresh CUDA context and targets exactly one ABI version:
validate LEPC, copy its exact 16-byte word, then copy the containing 4-KiB
page.  It never mixes V1/V2 or reads RPC/ATEXIT architectural state.
"""

from __future__ import annotations

import modal


IMAGE = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11"
    ).entrypoint([])
)
app = modal.App("sm100-entry-fragment-lepc", image=IMAGE)


def source(v2: bool = False) -> str:
    # LEPC is deliberately instruction 0. The remaining load/store sequence
    # follows the already-proven B200 minimal-cubin schedule.
    v2_pragma = ("    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1_V2(1)\n"
                 if v2 else "")
    name = "entry_v2" if v2 else "entry_v1"
    return (f"#fn {name}(out<8>) {{\n"
            "    #pragma REGCOUNT(12)\n"
            "    #pragma TCGEN05_1CTA_USED(1)\n"
            + v2_pragma + """
    LEPC {R4,R5};[0:7:{}:5:1]
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[2:7:{}:1:0]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R4,R5};[3:7:{0,1,2}:1:0]
    EXIT;[7:7:{3}:5:0]
}""")


def build(v2: bool = False) -> tuple[bytes, tuple[int, int]]:
    from assembler import assemble_kernel

    result = assemble_kernel(source(v2), arch="sm100a", check_deps=True)
    v1_record = bytes((4, 0x4f, 4, 0, 4, 0, 0, 0))
    v2_record = bytes((4, 0x4f, 4, 0, 6, 0, 0, 0))
    expected, rejected = ((v2_record, v1_record) if v2 else
                          (v1_record, v2_record))
    if expected not in result.code or rejected in result.code:
        version = "V2" if v2 else "V1"
        raise RuntimeError(f"cubin is not unambiguously TMEM_CTA1 {version}")
    return result.code, result.encoded[0]


def build_copy16() -> bytes:
    from assembler import assemble_kernel

    source_text = """#fn copy16(src<8>, dst<8>) {
    #pragma REGCOUNT(16)
    LDC.64 {R4,R5}, #param(src);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(dst);[1:7:{}:1:0]
    LDG.E.128.STRONG.GPU {R8,R9,R10,R11}, [{R4,R5}];[2:7:{0}:8:0]
    STG.E.128.STRONG.GPU [{R6,R7}], {R8,R9,R10,R11};[3:7:{1,2}:8:0]
    EXIT;[7:7:{3}:5:0]
}"""
    return assemble_kernel(source_text, arch="sm100a", check_deps=True).code


def build_copy_page() -> bytes:
    """Build a one-thread, fully unrolled 4-KiB code-page copier."""
    from assembler import assemble_kernel

    lines = [
        "#fn copy_page(src<8>, dst<8>) {",
        "    #pragma REGCOUNT(16)",
        "    LDC.64 {R4,R5}, #param(src);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(dst);[1:7:{}:1:0]",
    ]
    for off in range(0, 0x1000, 16):
        load_req = "0,3" if off == 0 else "3"
        store_req = "1,2" if off == 0 else "2"
        lines += [
            f"    LDG.E.128.STRONG.GPU {{R8,R9,R10,R11}}, "
            f"[{{R4,R5}}+0x{off:x}];[2:7:{{{load_req}}}:8:0]",
            f"    STG.E.128.STRONG.GPU [{{R6,R7}}+0x{off:x}], "
            f"{{R8,R9,R10,R11}};[3:7:{{{store_req}}}:8:0]",
        ]
    lines += ["    EXIT;[7:7:{3}:5:0]", "}"]
    return assemble_kernel("\n".join(lines), arch="sm100a",
                           check_deps=True).code


@app.function(gpu="B200", image=IMAGE, timeout=30)
def run_lepc(cubin_data: bytes, v2: bool = False) -> dict[str, object]:
    import ctypes
    import pathlib
    import subprocess

    path = pathlib.Path("/tmp/entry-v1-lepc.cubin")
    path.write_bytes(cubin_data)
    cuda = ctypes.CDLL("libcuda.so.1")
    CUdevice = ctypes.c_int
    CUcontext = ctypes.c_void_p
    CUmodule = ctypes.c_void_p
    CUfunction = ctypes.c_void_p
    CUdeviceptr = ctypes.c_uint64

    def check(code: int, call: str) -> None:
        if code:
            raise RuntimeError(f"{call}: CUDA error {code}")

    cuda.cuInit.argtypes = [ctypes.c_uint]
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(CUdevice), ctypes.c_int]
    cuda.cuCtxCreate_v2.argtypes = [ctypes.POINTER(CUcontext), ctypes.c_uint,
                                    CUdevice]
    cuda.cuModuleLoad.argtypes = [ctypes.POINTER(CUmodule), ctypes.c_char_p]
    cuda.cuModuleGetFunction.argtypes = [ctypes.POINTER(CUfunction), CUmodule,
                                         ctypes.c_char_p]
    cuda.cuMemAlloc_v2.argtypes = [ctypes.POINTER(CUdeviceptr), ctypes.c_size_t]
    cuda.cuMemcpyDtoH_v2.argtypes = [ctypes.c_void_p, CUdeviceptr,
                                     ctypes.c_size_t]
    cuda.cuLaunchKernel.argtypes = [
        CUfunction, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
    ]
    cuda.cuCtxSynchronize.argtypes = []

    check(cuda.cuInit(0), "cuInit")
    dev, ctx, mod, fun = CUdevice(), CUcontext(), CUmodule(), CUfunction()
    out = CUdeviceptr()
    check(cuda.cuDeviceGet(ctypes.byref(dev), 0), "cuDeviceGet")
    check(cuda.cuCtxCreate_v2(ctypes.byref(ctx), 0, dev), "cuCtxCreate")
    check(cuda.cuModuleLoad(ctypes.byref(mod), str(path).encode()),
          "cuModuleLoad")
    symbol = b"_Z8entry_v2" if v2 else b"_Z8entry_v1"
    check(cuda.cuModuleGetFunction(ctypes.byref(fun), mod, symbol),
          "cuModuleGetFunction")
    check(cuda.cuMemAlloc_v2(ctypes.byref(out), 8), "cuMemAlloc")
    arg0 = CUdeviceptr(out.value)
    params = (ctypes.c_void_p * 1)(
        ctypes.cast(ctypes.byref(arg0), ctypes.c_void_p))
    check(cuda.cuLaunchKernel(fun, 1, 1, 1, 32, 1, 1, 0,
                             None, params, None), "cuLaunchKernel")
    check(cuda.cuCtxSynchronize(), "cuCtxSynchronize")
    value = ctypes.c_uint64()
    check(cuda.cuMemcpyDtoH_v2(ctypes.byref(value), out, 8), "cuMemcpyDtoH")
    disasm = subprocess.run(["cuobjdump", "-sass", str(path)], check=True,
                            text=True, capture_output=True).stdout
    version = subprocess.run(["nvcc", "--version"], check=True, text=True,
                             capture_output=True).stdout.splitlines()[-1]
    return {"lepc": value.value, "nvcc_version": version,
            "sass_head": "\n".join(disasm.splitlines()[:18])}


@app.function(gpu="B200", image=IMAGE, timeout=30)
def run_copy(target_cubin: bytes, copy_cubin: bytes,
             page_copy: bool = False, v2: bool = False) -> dict[str, object]:
    """Fresh context: capture LEPC, then run one selected copy kernel."""
    import ctypes
    import pathlib

    root = pathlib.Path("/tmp/entry-v1-copy")
    root.mkdir(exist_ok=True)
    target_path, copy_path = root / "target.cubin", root / "copy.cubin"
    target_path.write_bytes(target_cubin)
    copy_path.write_bytes(copy_cubin)

    cuda = ctypes.CDLL("libcuda.so.1")
    CUdevice = ctypes.c_int
    CUcontext = ctypes.c_void_p
    CUmodule = ctypes.c_void_p
    CUfunction = ctypes.c_void_p
    CUdeviceptr = ctypes.c_uint64

    def check(code: int, call: str) -> None:
        if code:
            raise RuntimeError(f"{call}: CUDA error {code}")

    cuda.cuInit.argtypes = [ctypes.c_uint]
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(CUdevice), ctypes.c_int]
    cuda.cuCtxCreate_v2.argtypes = [ctypes.POINTER(CUcontext), ctypes.c_uint,
                                    CUdevice]
    cuda.cuModuleLoad.argtypes = [ctypes.POINTER(CUmodule), ctypes.c_char_p]
    cuda.cuModuleGetFunction.argtypes = [ctypes.POINTER(CUfunction), CUmodule,
                                         ctypes.c_char_p]
    cuda.cuMemAlloc_v2.argtypes = [ctypes.POINTER(CUdeviceptr), ctypes.c_size_t]
    cuda.cuMemcpyDtoH_v2.argtypes = [ctypes.c_void_p, CUdeviceptr,
                                     ctypes.c_size_t]
    cuda.cuLaunchKernel.argtypes = [
        CUfunction, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
    ]
    cuda.cuCtxSynchronize.argtypes = []

    check(cuda.cuInit(0), "cuInit")
    dev, ctx = CUdevice(), CUcontext()
    check(cuda.cuDeviceGet(ctypes.byref(dev), 0), "cuDeviceGet")
    check(cuda.cuCtxCreate_v2(ctypes.byref(ctx), 0, dev), "cuCtxCreate")

    target_mod, target_fun = CUmodule(), CUfunction()
    check(cuda.cuModuleLoad(ctypes.byref(target_mod),
                            str(target_path).encode()), "load target")
    target_symbol = b"_Z8entry_v2" if v2 else b"_Z8entry_v1"
    check(cuda.cuModuleGetFunction(ctypes.byref(target_fun), target_mod,
                                   target_symbol), "get target")
    capture = CUdeviceptr()
    check(cuda.cuMemAlloc_v2(ctypes.byref(capture), 8), "alloc capture")
    capture_arg = CUdeviceptr(capture.value)
    target_params = (ctypes.c_void_p * 1)(
        ctypes.cast(ctypes.byref(capture_arg), ctypes.c_void_p))
    check(cuda.cuLaunchKernel(target_fun, 1, 1, 1, 32, 1, 1, 0,
                             None, target_params, None), "launch target")
    check(cuda.cuCtxSynchronize(), "sync target")
    lepc = ctypes.c_uint64()
    check(cuda.cuMemcpyDtoH_v2(ctypes.byref(lepc), capture, 8), "read LEPC")

    copy_mod, copy_fun = CUmodule(), CUfunction()
    check(cuda.cuModuleLoad(ctypes.byref(copy_mod), str(copy_path).encode()),
          "load copy")
    copy_symbol = b"_Z9copy_page" if page_copy else b"_Z6copy16"
    check(cuda.cuModuleGetFunction(ctypes.byref(copy_fun), copy_mod,
                                   copy_symbol), "get copy")
    copy_size = 0x1000 if page_copy else 16
    copy_src = lepc.value & ~0xfff if page_copy else lepc.value
    copied = CUdeviceptr()
    check(cuda.cuMemAlloc_v2(ctypes.byref(copied), copy_size), "alloc copied")
    src_arg, dst_arg = CUdeviceptr(copy_src), CUdeviceptr(copied.value)
    copy_params = (ctypes.c_void_p * 2)(
        ctypes.cast(ctypes.byref(src_arg), ctypes.c_void_p),
        ctypes.cast(ctypes.byref(dst_arg), ctypes.c_void_p),
    )
    check(cuda.cuLaunchKernel(copy_fun, 1, 1, 1, 1, 1, 1, 0,
                             None, copy_params, None), "launch copy")
    check(cuda.cuCtxSynchronize(), "sync copy")
    raw = (ctypes.c_ubyte * copy_size)()
    check(cuda.cuMemcpyDtoH_v2(raw, copied, copy_size), "read copied bytes")
    return {"lepc": lepc.value, "copy_src": copy_src,
            "raw_hex": bytes(raw).hex()}


@app.local_entrypoint()
def main(copy16: bool = False, copy_page: bool = False,
         v2: bool = False) -> None:
    cubin, first_word = build(v2)
    if copy16 and copy_page:
        raise ValueError("select only one phase")
    if copy16:
        result = run_copy.remote(cubin, build_copy16(), False, v2)
        expected = (first_word[0].to_bytes(8, "little")
                    + first_word[1].to_bytes(8, "little"))
        got = bytes.fromhex(str(result["raw_hex"]))
        print(f"LEPC returned 0x{int(result['lepc']):016x}")
        print(f"copied={got.hex()} expected={expected.hex()}")
        print("LEPC self-word: PASS" if got == expected
              else "LEPC self-word: FAIL")
        return
    if copy_page:
        from pathlib import Path

        result = run_copy.remote(cubin, build_copy_page(), True, v2)
        raw = bytes.fromhex(str(result["raw_hex"]))
        version = "v2" if v2 else "v1"
        path = Path(f"/tmp/sm100_entry_fragment_{version}_page.bin")
        path.write_bytes(raw)
        offset = int(result["lepc"]) - int(result["copy_src"])
        expected = (first_word[0].to_bytes(8, "little")
                    + first_word[1].to_bytes(8, "little"))
        print(f"LEPC returned 0x{int(result['lepc']):016x}")
        print(f"page base 0x{int(result['copy_src']):016x}, "
              f"user entry offset 0x{offset:x}")
        print("entry word: PASS" if raw[offset:offset + 16] == expected
              else "entry word: FAIL")
        print(f"page capture: {path} ({len(raw):#x} bytes)")
        return
    result = run_lepc.remote(cubin, v2)
    version = "V2" if v2 else "V1"
    print(f"cubin={len(cubin)} bytes entry_fragment=TMEM_CTA1({version})")
    print(f"static instruction 0={first_word[0]:016x}:{first_word[1]:016x}")
    print(f"LEPC returned 0x{int(result['lepc']):016x}")
    print(result["nvcc_version"])
    print(result["sass_head"])
