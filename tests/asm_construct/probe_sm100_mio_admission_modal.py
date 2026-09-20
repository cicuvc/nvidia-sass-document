#!/usr/bin/env python3
"""Run short-burst MIO admission curves on a Modal B200."""

from __future__ import annotations

import ctypes
import statistics
import struct
from pathlib import Path

import modal


HERE = Path(__file__).resolve()
ROOT = HERE.parents[2] if len(HERE.parents) > 2 else Path.cwd()

IMAGE = modal.Image.from_registry(
    "nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11"
).entrypoint([])
app = modal.App("sm100-mio-admission", image=IMAGE)


@app.function(gpu="B200", timeout=600)
def run_sweep(cases: list[tuple[int, bytes, int]], function_name: str,
              block_size: int, actors: tuple[int, ...],
              repetitions: int) -> list[tuple[int, list[int]]]:
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
    cuda.cuModuleUnload.argtypes = [CUmodule]

    check(cuda.cuInit(0), "cuInit")
    dev, ctx = CUdevice(), CUcontext()
    check(cuda.cuDeviceGet(ctypes.byref(dev), 0), "cuDeviceGet")
    check(cuda.cuCtxCreate_v2(ctypes.byref(ctx), 0, dev), "cuCtxCreate")
    output_size = max(size for _, _, size in cases)
    allocation = CUdeviceptr()
    check(cuda.cuMemAlloc_v2(
        ctypes.byref(allocation), output_size), "cuMemAlloc")
    results = []
    symbol = f"_Z{len(function_name)}{function_name}".encode()
    for n, cubin, requested_size in cases:
        module, function = CUmodule(), CUfunction()
        blob = ctypes.create_string_buffer(cubin)
        check(cuda.cuModuleLoadData(
            ctypes.byref(module), ctypes.cast(blob, ctypes.c_void_p)),
            "cuModuleLoadData")
        check(cuda.cuModuleGetFunction(
            ctypes.byref(function), module, symbol), "cuModuleGetFunction")
        spans = []
        for _ in range(repetitions + 1):
            check(cuda.cuMemsetD32_v2(
                allocation, 0, output_size // 4), "cuMemsetD32")
            arg0 = CUdeviceptr(allocation.value)
            params = (ctypes.c_void_p * 1)(
                ctypes.cast(ctypes.byref(arg0), ctypes.c_void_p))
            check(cuda.cuLaunchKernel(
                function, 1, 1, 1, block_size, 1, 1, 0, None,
                params, None), "cuLaunchKernel")
            check(cuda.cuCtxSynchronize(), "cuCtxSynchronize")
            host = (ctypes.c_ubyte * output_size)()
            check(cuda.cuMemcpyDtoH_v2(
                ctypes.byref(host), allocation, output_size), "cuMemcpyDtoH")
            raw = bytes(host)
            times = [struct.unpack_from("<QQ", raw, warp * 16)
                     for warp in actors]
            spans.append((max(t1 for _, t1 in times)
                          - min(t0 for t0, _ in times)) & ((1 << 64) - 1))
        results.append((n, spans[1:]))
        check(cuda.cuModuleUnload(module), "cuModuleUnload")
    return results


def parse_counts(text: str) -> list[int]:
    if "-" in text:
        lo, hi = (int(x) for x in text.split("-", 1))
        return list(range(lo, hi + 1))
    return [int(x) for x in text.split(",") if x.strip()]


@app.local_entrypoint()
def main(mode: str = "xu", actors: str = "one", conflict: int = 0,
         counts: str = "0-16", repetitions: int = 7) -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(HERE.parent))
    from assembler import assemble
    from probe_mio_queue_depth import ACTORS, source

    if mode not in ("lsu", "lsu128", "ldg", "cbu", "xu", "fp64", "dfma"):
        raise ValueError("unsupported mode")
    actor_warps = ACTORS[actors]
    ns = parse_counts(counts)
    cases = []
    for n in ns:
        src = source(n, mode, actor_warps, conflict)
        cubin = assemble(src, arch="sm100a", check_deps=True)
        output_size = (max(actor_warps) + 1) * 16
        if mode == "ldg":
            global_step = 128 if conflict <= 1 else 4096
            output_size = max(
                output_size,
                0x1000 + n * global_step
                + (max(actor_warps) + 1) * 32 * 4 * max(conflict, 1))
        cases.append((n, cubin, output_size))
    rows = run_sweep.remote(
        cases, "mioburst", (max(actor_warps) + 1) * 32,
        actor_warps, repetitions)
    print(f"mode={mode} actors={actors} conflict={conflict}")
    print("N median min max delta")
    previous = None
    for n, values in rows:
        med = statistics.median(values)
        delta = "-" if previous is None else f"{med - previous:g}"
        print(f"{n:2d} {med:6g} {min(values):3d} {max(values):3d} {delta}")
        previous = med
