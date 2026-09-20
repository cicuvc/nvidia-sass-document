#!/usr/bin/env python3
"""Probe B200 UTCHMMA admission with post-instruction timestamp bounds."""

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
app = modal.App("sm100-utchmma-admission", image=IMAGE)


@app.function(gpu="B200", timeout=300)
def run_cases(cases: list[tuple[bytes, str, int, int]],
              repetitions: int) -> list[tuple[str, list[list[int]]]]:
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
    results = []
    for cubin, name, block_size, output_size in cases:
        module, function = CUmodule(), CUfunction()
        blob = ctypes.create_string_buffer(cubin)
        check(cuda.cuModuleLoadData(
            ctypes.byref(module), ctypes.cast(blob, ctypes.c_void_p)),
            "cuModuleLoadData")
        symbol = f"_Z{len(name)}{name}".encode()
        check(cuda.cuModuleGetFunction(
            ctypes.byref(function), module, symbol), "cuModuleGetFunction")
        allocation = CUdeviceptr()
        check(cuda.cuMemAlloc_v2(
            ctypes.byref(allocation), output_size), "cuMemAlloc")
        launches = []
        for launch_index in range(repetitions + 1):
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
            if launch_index:
                launches.append(list(struct.unpack(
                    f"<{output_size // 8}Q", bytes(host))))
        results.append((name, launches))
        check(cuda.cuModuleUnload(module), "cuModuleUnload")
    return results


@app.local_entrypoint()
def main(count: int = 8, repetitions: int = 7, mma_stall: int = 1,
         second_delay: int = 0, n_shape: int = 8,
         no_observer: bool = False) -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(HERE.parent))
    from assembler import assemble_kernel
    from probe_sm100_utchmma_warp_quantum import source

    if (not 2 <= count <= 8 or not 1 <= mma_stall <= 12
            or n_shape not in (8, 128)):
        raise ValueError("count must be 2..8, mma_stall 1..12, and n_shape 8/128")
    configs = (
        ("diff", (0, 1), 2),
        ("same", (0, 4), 1),
    )
    rounds = max(128, count * 24)
    timer_qword = rounds
    output_size = (rounds * 8 + 2 * count * 8 + 7) & ~7
    cases = []
    metadata = {}
    for label, producers, observer in configs:
        if no_observer:
            observer = max(producers) + 1
        name = f"utchmma_admit_{label}_c{count}_s{mma_stall}"
        src = source(name, count, (0, second_delay), producers, observer, True)
        if no_observer:
            src = "\n".join(
                line.replace(", URZ, UPT;", ", URZ, !UPT;")
                if "UTCHMMA" in line else line
                for line in src.splitlines())
        old_idesc = ((1 << 4) | (1 << 7) | (1 << 10)
                     | (1 << 17) | (8 << 24))
        new_idesc = ((1 << 4) | (1 << 7) | (1 << 10)
                     | ((n_shape >> 3) << 17) | (8 << 24))
        src = src.replace(f"UMOV UR15, {old_idesc:#x}",
                          f"UMOV UR15, {new_idesc:#x}")
        src = "\n".join(
            line.replace("[7:0:{}:12:1]", f"[7:0:{{}}:{mma_stall}:1]")
            if "UTCHMMA" in line else line
            for line in src.splitlines())
        result = assemble_kernel(src, arch="sm100a", check_deps=False)
        block_warps = max(producers) + 1 if no_observer else \
            max(*producers, observer) + 1
        cases.append((result.code, name, block_warps * 32, output_size))
        metadata[name] = (label, producers)

    for name, launches in run_cases.remote(cases, repetitions):
        label, producers = metadata[name]
        all_intervals = [[], []]
        print(f"placement={label} producers={producers} stall={mma_stall}")
        for run, qwords in enumerate(launches):
            streams = []
            for producer in range(2):
                begin = timer_qword + producer * count
                stamps = qwords[begin:begin + count]
                intervals = [stamps[i + 1] - stamps[i]
                             for i in range(count - 1)]
                streams.append(intervals)
                for i, value in enumerate(intervals):
                    all_intervals[producer].append((i, value))
            print({"run": run, "intervals": streams})
        for producer in range(2):
            by_index = []
            for i in range(count - 1):
                values = [v for j, v in all_intervals[producer] if j == i]
                by_index.append(statistics.median(values))
            print({"producer": producer, "median_intervals": by_index})
