#!/usr/bin/env python3
"""Dump V2 reserved shared memory around UTCLDSWS on a Modal B200."""

from __future__ import annotations

import ctypes
from pathlib import Path

import modal


HERE = Path(__file__).resolve()
ROOT = HERE.parents[2] if len(HERE.parents) > 2 else Path.cwd()
SOURCE = HERE.with_name("utcldsws_reserved_dump_sm100.sass")
NWORDS = 49

IMAGE = modal.Image.from_registry(
    "nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11"
).entrypoint([])
app = modal.App("utcldsws-reserved-dump", image=IMAGE)


@app.function(gpu="B200", timeout=120)
def run_probe(cubin: bytes, function_name: str, repetitions: int) -> list[list[int]]:
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
    module = CUmodule()
    blob = ctypes.create_string_buffer(cubin)
    check(cuda.cuModuleLoadData(
        ctypes.byref(module), ctypes.cast(blob, ctypes.c_void_p)),
        "cuModuleLoadData")
    function = CUfunction()
    symbol = f"_Z{len(function_name)}{function_name}".encode()
    check(cuda.cuModuleGetFunction(
        ctypes.byref(function), module, symbol), "cuModuleGetFunction")

    rows = []
    for _ in range(repetitions):
        allocation = CUdeviceptr()
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
            ctypes.byref(host), allocation, ctypes.sizeof(host)),
            "cuMemcpyDtoH")
        rows.append(list(host))
    return rows


@app.local_entrypoint()
def main(repetitions: int = 3, active_allocation: bool = False) -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from assembler import assemble_kernel

    source = SOURCE.read_text()
    if active_allocation:
        source = source.replace(
            "    #!tmem_alloc_1cta(UR5, 32)\n"
            "    #!tmem_dealloc_1cta(UR5, 32)\n",
            "    #!tmem_dealloc_1cta(UR5, 32)\n", 1)
        source = source.replace(
            "    LDS R8,  [UR8+0x00];[0:7:{}:1:0]\n",
            "    #!tmem_alloc_1cta(UR5, 32)\n"
            "    LDS R8,  [UR8+0x00];[0:7:{}:1:0]\n", 1)
    result = assemble_kernel(source, arch="sm100a", check_deps=False)
    for run, words in enumerate(run_probe.remote(
            result.code, result.kernel_name, repetitions)):
        before, after, sws = words[:24], words[24:48], words[48]
        changed = [
            (4 * i, before[i], after[i])
            for i in range(24) if before[i] != after[i]
        ]
        nonzero = [(4 * i, value) for i, value in enumerate(before) if value]
        print({
            "run": run,
            "active_allocation": active_allocation,
            "sws": f"0x{sws:08x}",
            "changed": [
                (f"0x{off:02x}", f"0x{old:08x}", f"0x{new:08x}")
                for off, old, new in changed
            ],
            "before_nonzero": [
                (f"0x{off:02x}", f"0x{value:08x}")
                for off, value in nonzero
            ],
        })
