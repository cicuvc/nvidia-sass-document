#!/usr/bin/env python3
"""Compile, load, and execute a minimal sm_100a cubin on a Modal B200.

Run locally with the Modal CLI environment::

    modal run tools/modal_b200_minimal.py

The remote side compiles a standalone cubin with nvcc, then loads it through
the CUDA Driver API via ctypes.  No CUDA Runtime kernel-launch wrapper is used.
"""

from __future__ import annotations

import modal


CUDA_IMAGE = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .entrypoint([])
)

app = modal.App("b200-minimal-cubin", image=CUDA_IMAGE)


@app.function(gpu="B200", timeout=600)
def run_cubin(cubin_data: bytes | None = None) -> dict[str, object]:
    import ctypes
    import hashlib
    import pathlib
    import subprocess

    work = pathlib.Path("/tmp/b200-minimal-cubin")
    work.mkdir(parents=True, exist_ok=True)
    source = work / "minimal.cu"
    cubin = work / "minimal.cubin"
    producer = "local SASS assembler" if cubin_data is not None else "nvcc"
    if cubin_data is not None:
        cubin.write_bytes(cubin_data)
    else:
        source.write_text(
            r'''extern "C" __global__ void minimal(unsigned long long *out) {
    if (threadIdx.x == 0) {
        out[0] = 0xb200c0de12345678ULL;
    }
}
'''
        )

    smi = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,compute_cap,driver_version,memory.total",
            "--format=csv,noheader",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    nvcc_version = subprocess.run(
        ["nvcc", "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if cubin_data is None:
        subprocess.run(
            [
                "nvcc", "-cubin", "-arch=sm_100a", "-O0",
                "-o", str(cubin), str(source),
            ],
            check=True,
        )

    cuda = ctypes.CDLL("libcuda.so.1")
    CUdevice = ctypes.c_int
    CUcontext = ctypes.c_void_p
    CUmodule = ctypes.c_void_p
    CUfunction = ctypes.c_void_p
    CUdeviceptr = ctypes.c_uint64

    cuda.cuGetErrorName.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
    cuda.cuGetErrorString.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]

    def check(code: int, call: str) -> None:
        if code == 0:
            return
        name = ctypes.c_char_p()
        desc = ctypes.c_char_p()
        cuda.cuGetErrorName(code, ctypes.byref(name))
        cuda.cuGetErrorString(code, ctypes.byref(desc))
        raise RuntimeError(
            f"{call}: {code} "
            f"{name.value.decode() if name.value else '?'}: "
            f"{desc.value.decode() if desc.value else '?'}"
        )

    cuda.cuInit.argtypes = [ctypes.c_uint]
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(CUdevice), ctypes.c_int]
    cuda.cuDeviceComputeCapability.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        CUdevice,
    ]
    cuda.cuCtxCreate_v2.argtypes = [
        ctypes.POINTER(CUcontext), ctypes.c_uint, CUdevice
    ]
    cuda.cuModuleLoad.argtypes = [ctypes.POINTER(CUmodule), ctypes.c_char_p]
    cuda.cuModuleGetFunction.argtypes = [
        ctypes.POINTER(CUfunction), CUmodule, ctypes.c_char_p
    ]
    cuda.cuMemAlloc_v2.argtypes = [ctypes.POINTER(CUdeviceptr), ctypes.c_size_t]
    cuda.cuMemFree_v2.argtypes = [CUdeviceptr]
    cuda.cuLaunchKernel.argtypes = [
        CUfunction,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]
    cuda.cuCtxSynchronize.argtypes = []
    cuda.cuMemcpyDtoH_v2.argtypes = [ctypes.c_void_p, CUdeviceptr, ctypes.c_size_t]
    cuda.cuCtxDestroy_v2.argtypes = [CUcontext]

    check(cuda.cuInit(0), "cuInit")
    device = CUdevice()
    check(cuda.cuDeviceGet(ctypes.byref(device), 0), "cuDeviceGet")
    major, minor = ctypes.c_int(), ctypes.c_int()
    check(
        cuda.cuDeviceComputeCapability(
            ctypes.byref(major), ctypes.byref(minor), device
        ),
        "cuDeviceComputeCapability",
    )

    context = CUcontext()
    module = CUmodule()
    function = CUfunction()
    allocation = CUdeviceptr()
    check(cuda.cuCtxCreate_v2(ctypes.byref(context), 0, device), "cuCtxCreate_v2")
    try:
        check(cuda.cuModuleLoad(ctypes.byref(module), str(cubin).encode()), "cuModuleLoad")
        get_function = cuda.cuModuleGetFunction(
            ctypes.byref(function), module, b"minimal"
        )
        if get_function != 0:
            # CubinBuilder exports hand-written kernels under their ordinary
            # C++ ABI spelling, while the nvcc reference uses extern "C".
            get_function = cuda.cuModuleGetFunction(
                ctypes.byref(function), module, b"_Z7minimal"
            )
        check(get_function, "cuModuleGetFunction")
        check(cuda.cuMemAlloc_v2(ctypes.byref(allocation), 8), "cuMemAlloc_v2")
        try:
            # kernelParams is an array of pointers to host-side argument values.
            arg0 = CUdeviceptr(allocation.value)
            params = (ctypes.c_void_p * 1)(ctypes.cast(ctypes.byref(arg0), ctypes.c_void_p))
            check(
                cuda.cuLaunchKernel(
                    function,
                    1,
                    1,
                    1,
                    32,
                    1,
                    1,
                    0,
                    None,
                    params,
                    None,
                ),
                "cuLaunchKernel",
            )
            check(cuda.cuCtxSynchronize(), "cuCtxSynchronize")
            result = ctypes.c_uint64()
            check(
                cuda.cuMemcpyDtoH_v2(
                    ctypes.byref(result), allocation, ctypes.sizeof(result)
                ),
                "cuMemcpyDtoH_v2",
            )
        finally:
            check(cuda.cuMemFree_v2(allocation), "cuMemFree_v2")
    finally:
        check(cuda.cuCtxDestroy_v2(context), "cuCtxDestroy_v2")

    data = cubin.read_bytes()
    disassembly = subprocess.run(
        ["cuobjdump", "-sass", str(cubin)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {
        "nvidia_smi": smi,
        "producer": producer,
        "compute_capability": f"{major.value}.{minor.value}",
        "nvcc_version": nvcc_version.splitlines()[-1],
        "cubin_size": len(data),
        "cubin_sha256": hashlib.sha256(data).hexdigest(),
        "result": f"0x{result.value:016x}",
        "expected": "0xb200c0de12345678",
        "sass": "\n".join(disassembly.splitlines()[:24]),
    }


@app.local_entrypoint()
def main(nvcc_reference: bool = False) -> None:
    if nvcc_reference:
        cubin_data = None
    else:
        from assembler import assemble

        sass = r'''#fn minimal(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]
    MOV32I R4, 0x12345678;[7:7:{}:8:1]
    MOV32I R5, 0xb200c0de;[7:7:{}:8:1]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R4,R5};[2:7:{0,1}:1:0]
    EXIT;[7:7:{2}:5:0]
}'''
        cubin_data = assemble(sass, arch="sm100", check_deps=True)
        print(f"local assembler produced {len(cubin_data)} cubin bytes")

    result = run_cubin.remote(cubin_data)
    for key, value in result.items():
        print(f"{key}:\n{value}" if "\n" in str(value) else f"{key}: {value}")
    if result["result"] != result["expected"]:
        raise SystemExit("minimal cubin returned the wrong value")
