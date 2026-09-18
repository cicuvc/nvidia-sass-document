#!/usr/bin/env python3
"""Compile or run tcgen05.alloc/dealloc kernels on a Modal B200.

The local entry point sends CUDA source to a CUDA-devel container, returns the
cubin and cuobjdump output, and stores the generated cubin under /tmp for
follow-up lifting/encoding comparison.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import modal


IMAGE = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11"
    ).entrypoint([])
)
app = modal.App("tcgen05-alloc-disasm", image=IMAGE)
HANDLER_COPY_SIZE = 0x800


SOURCE = r"""
#include <cstdint>

extern "C" __global__ void alloc32(uint32_t *out) {
    __shared__ uint32_t taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&taddr)) : "memory");
    __syncwarp();
    uint32_t v = taddr;
    if (threadIdx.x == 0) out[0] = v;
    asm volatile(
        "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
        :: "r"(v) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
        ::: "memory");
}

extern "C" __global__ void alloc64(uint32_t *out) {
    __shared__ uint32_t taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 64;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&taddr)) : "memory");
    __syncwarp();
    uint32_t v = taddr;
    if (threadIdx.x == 0) out[0] = v;
    asm volatile(
        "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 64;\n"
        :: "r"(v) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
        ::: "memory");
}

extern "C" __global__ void alloc512(uint32_t *out) {
    __shared__ uint32_t taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 512;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&taddr)) : "memory");
    __syncwarp();
    uint32_t v = taddr;
    if (threadIdx.x == 0) out[0] = v;
    asm volatile(
        "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 512;\n"
        :: "r"(v) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
        ::: "memory");
}

// Minimal multi-warp CTA-group::1 control.  Exactly warp 0 participates in
// the warp-synchronous PTX allocator/deallocator.  CTA barriers publish the
// resulting TMEM column to the consumer warps and keep deallocation after
// every consumer has finished reading it.
extern "C" __global__ void alloc_multi(uint32_t *out) {
    __shared__ uint32_t taddr;
    const uint32_t tid = threadIdx.x;
    if (tid < 32) {
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0], 32;\n"
            :: "r"((uint32_t)__cvta_generic_to_shared(&taddr)) : "memory");
    }
    __syncthreads();
    if ((tid & 31) == 0)
        out[tid >> 5] = taddr;
    __syncthreads();
    if (tid < 32) {
        const uint32_t v = taddr;
        asm volatile(
            "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
            :: "r"(v) : "memory");
        asm volatile(
            "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
            ::: "memory");
    }
}
"""


def make_atexit_probe_source(source: str, copy_handler: bool = False) -> str:
    """Add BMOV ATEXIT_PC samples around the tail relinquish sequence."""
    pad = "\n".join(
        "    IADD3 R20, R20, RZ, RZ;[7:7:{}:5:1]" for _ in range(8))
    source = source.replace("    #pragma REGCOUNT(12)",
                            "    #pragma REGCOUNT(32)")
    before = """    #def_label(L_5d0)
    ELECT P0, URZ, PT;[7:7:{}:1:0]"""
    copy = ""
    if copy_handler:
        lines = []
        for off in range(0, HANDLER_COPY_SIZE, 16):
            lines += [
                f"    LDG.E.128.STRONG.GPU {{R16,R17,R18,R19}}, "
                f"[{{R10,R11}}+0x{off:x}];[2:7:{{}}:8:0]",
                f"    STG.E.128.STRONG.GPU desc[{{UR8,UR9}}]"
                f"[{{R14,R15}}+0x{0x100 + off:x}], "
                "{R16,R17,R18,R19};[7:7:{1,2}:8:0]",
            ]
        copy = "\n" + "\n".join(lines)
    before_probe = f"""    #def_label(L_5d0)
    LDC.64 {{R14,R15}}, #param(out);[1:7:{{}}:1:0]
    BMOV R10, ATEXIT_PC.LO;[3:7:{{}}:5:1]
{pad}
    BMOV R11, ATEXIT_PC.HI;[4:7:{{}}:5:1]
{pad}{copy}
    ELECT P0, URZ, PT;[7:7:{{}}:1:0]"""
    if before not in source:
        raise ValueError("relinquish entry anchor not found")
    source = source.replace(before, before_probe, 1)

    after = """    STS.U8 [UR4], R0;[7:7:{}:1:0]
    EXIT;[7:7:{}:5:0]"""
    after_probe = f"""    STS.U8 [UR4], R0;[7:7:{{}}:1:0]
    BMOV R12, ATEXIT_PC.LO;[5:7:{{}}:5:1]
{pad}
    BMOV R13, ATEXIT_PC.HI;[0:7:{{}}:5:1]
{pad}
    STG.E.64.STRONG.GPU desc[{{UR8,UR9}}][{{R14,R15}}+0x8], {{R10,R11}};[7:7:{{0,1,2,3,4,5}}:8:0]
    STG.E.64.STRONG.GPU desc[{{UR8,UR9}}][{{R14,R15}}+0x10], {{R12,R13}};[7:7:{{0,1,2,3,4,5}}:8:0]
    EXIT;[7:7:{{}}:5:0]"""
    if after not in source:
        raise ValueError("relinquish exit anchor not found")
    return source.replace(after, after_probe, 1)


def make_atexit_write_probe_source(source: str) -> str:
    """Write a kernel-local VA to ATEXIT_PC, read it back, then restore it."""
    pad = "\n".join(
        "    IADD3 R20, R20, RZ, RZ;[7:7:{}:5:1]" for _ in range(8))
    source = source.replace("    #pragma REGCOUNT(12)",
                            "    #pragma REGCOUNT(32)")
    anchor = """    #def_label(L_5d0)
    ELECT P0, URZ, PT;[7:7:{}:1:0]"""
    probe = f"""    #def_label(L_5d0)
    LDC.64 {{R22,R23}}, #param(out);[1:7:{{}}:1:0]
    BMOV R10, ATEXIT_PC.LO;[3:7:{{}}:5:1]
{pad}
    BMOV R11, ATEXIT_PC.HI;[4:7:{{}}:5:1]
{pad}
    LEPC {{R12,R13}}, #label(write_target);[2:7:{{}}:5:1]
    BMOV.64 ATEXIT_PC, {{R12,R13}};[7:7:{{2}}:5:1]
{pad}
    BMOV R14, ATEXIT_PC.LO;[5:7:{{}}:5:1]
{pad}
    BMOV R15, ATEXIT_PC.HI;[0:7:{{}}:5:1]
{pad}
    BMOV.64 ATEXIT_PC, {{R10,R11}};[7:7:{{}}:5:1]
    STG.E.64.STRONG.GPU desc[{{UR8,UR9}}][{{R22,R23}}+0x8], {{R10,R11}};[7:7:{{0,1,2,3,4,5}}:8:0]
    STG.E.64.STRONG.GPU desc[{{UR8,UR9}}][{{R22,R23}}+0x10], {{R12,R13}};[7:7:{{0,1,2,3,4,5}}:8:0]
    STG.E.64.STRONG.GPU desc[{{UR8,UR9}}][{{R22,R23}}+0x18], {{R14,R15}};[7:7:{{0,1,2,3,4,5}}:8:0]
    ELECT P0, URZ, PT;[7:7:{{}}:1:0]"""
    if anchor not in source:
        raise ValueError("relinquish entry anchor not found")
    source = source.replace(anchor, probe, 1)
    tail = """    #def_label(L_700)
    BRA #label(L_700);[7:7:{}:0:1]
}"""
    target = """    #def_label(L_700)
    BRA #label(L_700);[7:7:{}:0:1]
    #def_label(write_target)
    EXIT.NO_ATEXIT;[7:7:{}:5:0]
}"""
    if tail not in source:
        raise ValueError("kernel tail anchor not found")
    return source.replace(tail, target, 1)


def make_ldst_probe_source(source: str) -> str:
    """Replace the allocator smoke-test payload with a 32-lane TMEM roundtrip.

    Each lane stores 0x12340000+lane into one TMEM column with STTM and loads
    it back with LDTM; lane 0 is copied to host-visible memory.  The nvcc
    control kernel separately validates all 32 returned lanes.
    FENCE.VIEW.ASYNC.T is the SASS lowering of tcgen05.wait::st;
    tcgen05.wait::ld is represented by the SB3 wait on STG.
    """
    source = source.replace("    #pragma REGCOUNT(12)",
                            "    #pragma REGCOUNT(32)")
    old = """    LDS R5, [UR5];[2:7:{}:1:0]
    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]
    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]
    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R5;[7:0:{2}:1:0]
    NOP;[7:7:{}:1:0]"""
    new = """    LDS R5, [UR5];[2:7:{}:1:0]
    R2UR UR10, R5;[7:7:{2}:13:1]
    LOP3.LUT R16, R0, 0x12340000, RZ, 0xfc, !PT;[7:7:{0}:5:1]
    STTM tmem[UR10], R16;[7:7:{}:1:0]
    FENCE.VIEW.ASYNC.T;[3:7:{}:2:0]
    LDTM R17, tmem[UR10];[3:7:{3}:1:0]
    NOP;[7:7:{}:1:0]
    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{}:13:1]
    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]
    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R17;[7:0:{2,3}:1:0]"""
    if old not in source:
        raise ValueError("allocator payload anchor not found")
    source = source.replace(old, new, 1)
    # The deallocation epilogue reuses R2/R3.  STG collects operands late,
    # so its read scoreboard must be released before the first overwrite.
    old_reuse = "LOP3.LUT R2, R0, 0xffff, RZ, 0xc0, !PT;[7:7:{0}:2:0:1]"
    new_reuse = "LOP3.LUT R2, R0, 0xffff, RZ, 0xc0, !PT;[7:7:{0}:2:0:1]"
    if old_reuse not in source:
        raise ValueError("deallocation R2 reuse anchor not found")
    return source.replace(old_reuse, new_reuse, 1)


def make_gmem_control_source(source: str, ldc_wr: int = 2,
                             ldc_stall: int = 2,
                             stg_req: str = "2,3",
                             stg_rd: int = 0,
                             gap_nops: int = 0) -> str:
    """The ldst probe with TMEM operations replaced by a register move."""
    source = make_ldst_probe_source(source)
    old = """    STTM tmem[UR10], R16;[7:7:{}:1:0]
    FENCE.VIEW.ASYNC.T;[3:7:{}:2:0]
    LDTM R17, tmem[UR10];[3:7:{3}:1:0]
    NOP;[7:7:{}:1:0]"""
    new = """    MOV R17, R16;[7:7:{}:5:1]
    NOP;[7:7:{}:1:0]
    NOP;[7:7:{}:1:0]
    NOP;[7:7:{}:1:0]"""
    if old not in source:
        raise ValueError("gmem control TMEM anchor not found")
    source = source.replace(old, new, 1)
    old_sched = """    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]
    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R17;[7:0:{2,3}:1:0]"""
    gap = "".join(
        "    NOP;[7:7:{}:1:0]\n" for _ in range(gap_nops))
    new_sched = (
        "    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];"
        f"[{ldc_wr}:7:{{}}:{ldc_stall}:0]\n"
        f"{gap}"
        "    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R17;"
        f"[7:{stg_rd}:{{{stg_req}}}:1:0]")
    if old_sched not in source:
        raise ValueError("gmem control schedule anchor not found")
    return source.replace(old_sched, new_sched, 1)


def make_ldst_x2_probe_source(source: str) -> str:
    """Turn the x1 roundtrip into .32x32b.x2 and export lane 0's pair."""
    source = make_ldst_probe_source(source)
    changes = (
        ("    LOP3.LUT R16, R0, 0x12340000, RZ, 0xfc, !PT;"
         "[7:7:{0}:5:1]",
         "    LOP3.LUT R16, R0, 0x12340000, RZ, 0xfc, !PT;"
         "[7:7:{0}:5:1]\n"
         "    LOP3.LUT R17, R0, 0x56780000, RZ, 0xfc, !PT;"
         "[7:7:{}:5:1]"),
        ("    STTM tmem[UR10], R16;[7:7:{}:1:0]",
         "    STTM.x2 tmem[UR10], {R16,R17};[7:7:{}:1:0]"),
        ("    LDTM R17, tmem[UR10];[3:7:{3}:1:0]",
         "    LDTM.x2 {R18,R19}, tmem[UR10];[3:7:{3}:1:0]"),
        ("    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R17;"
         "[7:0:{2,3}:1:0]",
         "    @!P0 STG.E.64 desc[{UR8,UR9}][{R2,R3}], {R18,R19};"
         "[7:0:{2,3}:1:0]"),
    )
    for old, new in changes:
        if old not in source:
            raise ValueError(f"x2 probe anchor not found: {old}")
        source = source.replace(old, new, 1)
    return source


def make_ldst_column_probe_source(source: str) -> str:
    """Store x2, then recover it with x1 loads at offsets 0 and 1."""
    source = make_ldst_x2_probe_source(source)
    old = "    LDTM.x2 {R18,R19}, tmem[UR10];[3:7:{3}:1:0]"
    new = """    LDTM R18, tmem[UR10];[3:7:{3}:1:0]
    LDTM R19, tmem[UR10+0x1];[4:7:{}:1:0]"""
    if old not in source:
        raise ValueError("column probe LDTM anchor not found")
    source = source.replace(old, new, 1)
    return source.replace("[7:0:{2,3}:1:0]", "[7:0:{2,3,4}:1:0]", 1)


@app.function(gpu="B200", image=IMAGE, timeout=30)
def compile_remote(source: str) -> tuple[bytes, str, str]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cu = root / "alloc.cu"
        cubin = root / "alloc.cubin"
        cu.write_text(source)
        build = subprocess.run(
            ["nvcc", "-arch=sm_100a", "-cubin", "-O3", "-o", str(cubin), str(cu)],
            text=True, capture_output=True,
        )
        if build.returncode:
            raise RuntimeError(f"nvcc failed:\n{build.stdout}\n{build.stderr}")
        sass = subprocess.run(
            ["cuobjdump", "-sass", str(cubin)], text=True, capture_output=True,
            check=True,
        )
        elf = subprocess.run(
            ["cuobjdump", "-elf", str(cubin)], text=True, capture_output=True,
            check=True,
        )
        return cubin.read_bytes(), sass.stdout, elf.stdout


@app.function(gpu="B200", image=IMAGE, timeout=30)
def run_remote(cubin_data: bytes, function_name: str, block_size: int = 32,
               output_words: int = 0,
               repetitions: int = 1,
               cluster_x: int = 0) -> dict[str, object]:
    """Load a hand-assembled cubin and return its first u32 output word."""
    import ctypes
    import pathlib
    import struct

    cubin = pathlib.Path("/tmp/tcgen05-hand.cubin")
    cubin.write_bytes(cubin_data)
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
    cuda.cuMemsetD32_v2.argtypes = [CUdeviceptr, ctypes.c_uint, ctypes.c_size_t]
    cuda.cuMemcpyDtoH_v2.argtypes = [ctypes.c_void_p, CUdeviceptr,
                                     ctypes.c_size_t]
    cuda.cuLaunchKernel.argtypes = [
        CUfunction, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
    ]
    cuda.cuCtxSynchronize.argtypes = []

    class AttrVal(ctypes.Union):
        _fields_ = [("pad", ctypes.c_ubyte * 64)]

    class LaunchAttr(ctypes.Structure):
        _fields_ = [("id", ctypes.c_int),
                    ("pad", ctypes.c_ubyte * 4),
                    ("value", AttrVal)]

    class LaunchConfig(ctypes.Structure):
        _fields_ = [("gridDimX", ctypes.c_uint),
                    ("gridDimY", ctypes.c_uint),
                    ("gridDimZ", ctypes.c_uint),
                    ("blockDimX", ctypes.c_uint),
                    ("blockDimY", ctypes.c_uint),
                    ("blockDimZ", ctypes.c_uint),
                    ("sharedMemBytes", ctypes.c_uint),
                    ("hStream", ctypes.c_void_p),
                    ("attrs", ctypes.POINTER(LaunchAttr)),
                    ("numAttrs", ctypes.c_uint)]

    cuda.cuLaunchKernelEx.argtypes = [ctypes.POINTER(LaunchConfig), CUfunction,
                                      ctypes.POINTER(ctypes.c_void_p),
                                      ctypes.c_void_p]

    check(cuda.cuInit(0), "cuInit")
    dev, ctx, mod = CUdevice(), CUcontext(), CUmodule()
    out = CUdeviceptr()
    check(cuda.cuDeviceGet(ctypes.byref(dev), 0), "cuDeviceGet")
    check(cuda.cuCtxCreate_v2(ctypes.byref(ctx), 0, dev), "cuCtxCreate")
    check(cuda.cuModuleLoad(ctypes.byref(mod), str(cubin).encode()),
          "cuModuleLoad")
    out_size = max(0x100 + HANDLER_COPY_SIZE, output_words * 4)
    check(cuda.cuMemAlloc_v2(ctypes.byref(out), out_size), "cuMemAlloc")
    arg0 = CUdeviceptr(out.value)
    params = (ctypes.c_void_p * 1)(
        ctypes.cast(ctypes.byref(arg0), ctypes.c_void_p))
    raw = (ctypes.c_ubyte * out_size)()
    samples_u64 = []
    multi_samples_u64 = {}
    multi_timer_deltas_u64 = {}
    multi_words_u64 = {}
    multi_words_u32 = {}
    multi_timer_pair_samples = {}
    multi_requested_word_samples = {}
    for name in function_name.split(","):
        fun = CUfunction()
        check(cuda.cuModuleGetFunction(ctypes.byref(fun), mod, name.encode()),
              f"cuModuleGetFunction({name})")
        check(cuda.cuMemsetD32_v2(out, 0xdeadbeef, out_size // 4),
              "cuMemsetD32")
        samples_u64 = []
        timer_samples = []
        pair_samples = []
        requested_word_samples = []
        for _ in range(repetitions):
            if cluster_x:
                attr = LaunchAttr()
                attr.id = 4  # CU_LAUNCH_ATTRIBUTE_CLUSTER_DIMENSION
                dims = (ctypes.c_uint * 3)(cluster_x, 1, 1)
                ctypes.memmove(ctypes.byref(attr.value), ctypes.byref(dims),
                               ctypes.sizeof(dims))
                attrs = (LaunchAttr * 1)(attr)
                cfg = LaunchConfig(cluster_x, 1, 1, block_size, 1, 1, 0,
                                   None, attrs, 1)
                check(cuda.cuLaunchKernelEx(ctypes.byref(cfg), fun, params,
                                            None),
                      f"cuLaunchKernelEx({name})")
            else:
                check(cuda.cuLaunchKernel(fun, 1, 1, 1, block_size, 1, 1, 0,
                                         None, params, None),
                      f"cuLaunchKernel({name})")
            check(cuda.cuCtxSynchronize(), "cuCtxSynchronize")
            check(cuda.cuMemcpyDtoH_v2(raw, out, ctypes.sizeof(raw)),
                  "cuMemcpyDtoH")
            lo, hi = struct.unpack_from("<II", bytes(raw), 0)
            samples_u64.append(lo | hi << 32)
            end_lo, end_hi = struct.unpack_from("<II", bytes(raw), 8)
            timer_samples.append(
                ((end_lo | end_hi << 32) - (lo | hi << 32))
                & ((1 << 64) - 1))
            launch_pairs = []
            dead64 = 0xDEADBEEFDEADBEEF
            launch_words = struct.unpack_from(
                f"<{min(len(raw) // 4, max(256, output_words))}I",
                bytes(raw), 0)
            requested_word_samples.append([
                hex(x) for x in launch_words[:min(256, output_words)]
            ])
            for warp in range(min(block_size // 32,
                                  len(launch_words) // 4)):
                base = warp * 4
                start = launch_words[base] | launch_words[base + 1] << 32
                end = launch_words[base + 2] | launch_words[base + 3] << 32
                if start != dead64 and end != dead64:
                    launch_pairs.append(
                        (warp, (end - start) & ((1 << 64) - 1)))
            pair_samples.append(launch_pairs)
        multi_samples_u64[name] = samples_u64
        multi_timer_deltas_u64[name] = timer_samples
        multi_words_u64[name] = list(struct.unpack_from("<8Q", bytes(raw), 0))
        multi_words_u32[name] = list(struct.unpack_from("<32I", bytes(raw), 0))
        multi_timer_pair_samples[name] = pair_samples
        multi_requested_word_samples[name] = requested_word_samples
    words = struct.unpack_from("<32I", bytes(raw), 0)
    n_words = min(len(raw) // 4, max(256, output_words))
    words_all = struct.unpack_from(f"<{n_words}I", bytes(raw), 0)
    unique_words = sorted(set(words_all))
    timer_begin = words_all[0] | (words_all[1] << 32)
    timer_end = words_all[2] | (words_all[3] << 32)
    # Bandwidth probes store one four-word record per warp:
    # {clock_delta_lo, clock_delta_hi, sink, vector_width}.
    warp_deltas_u64 = [
        words_all[warp * 4] | (words_all[warp * 4 + 1] << 32)
        for warp in range(min(block_size // 32, n_words // 4))
    ]
    # Generic per-warp timing layout used by hand-SASS topology probes:
    # two consecutive u64 values (start,end) per warp.  Keep this in addition
    # to the older four-u32 bandwidth-record decoder above.
    timer_pair_records = []
    dead64 = 0xDEADBEEFDEADBEEF
    pair_count = min(block_size // 32, n_words // 4)
    for warp in range(pair_count):
        base = warp * 4
        start = words_all[base] | (words_all[base + 1] << 32)
        end = words_all[base + 2] | (words_all[base + 3] << 32)
        if start != dead64 and end != dead64:
            timer_pair_records.append(
                (warp, start, end, (end - start) & ((1 << 64) - 1)))
    timer_pair_span = 0
    if timer_pair_records:
        timer_pair_span = (max(x[2] for x in timer_pair_records)
                           - min(x[1] for x in timer_pair_records))
    return {
        "words": [hex(x) for x in words[:8]],
        "words32": [hex(x) for x in words],
        "requested_words32_head": [hex(x) for x in words_all[:256]],
        "requested_words32_tail": [hex(x) for x in words_all[-64:]],
        "lane_first_words": [hex(words_all[lane * 8])
                             for lane in range(n_words // 8)],
        "unique_output_word_count": len(unique_words),
        "unique_output_words_head": [hex(x) for x in unique_words[:16]],
        "unique_output_words_tail": [hex(x) for x in unique_words[-16:]],
        "samples_u64": samples_u64,
        "multi_samples_u64": multi_samples_u64,
        "multi_timer_deltas_u64": multi_timer_deltas_u64,
        "multi_words_u64": multi_words_u64,
        "multi_words_u32": multi_words_u32,
        "multi_timer_pair_samples": multi_timer_pair_samples,
        "multi_requested_word_samples": multi_requested_word_samples,
        "timer_delta_u64": (timer_end - timer_begin) & ((1 << 64) - 1),
        "warp_deltas_u64": warp_deltas_u64,
        "timer_pair_records": timer_pair_records,
        "timer_pair_span": timer_pair_span,
        "atexit_before_relinquish": hex(words[2] | (words[3] << 32)),
        "atexit_after_relinquish": hex(words[4] | (words[5] << 32)),
        "handler_hex": bytes(raw[0x100:]).hex(),
    }


@app.local_entrypoint()
def main(hand_cubin: str = "", hand_source: str = "",
         compile_source: str = "", compile_output: str = "",
         function_name: str = "_Z7alloc32", atexit_probe: bool = False,
         copy_handler: bool = False, atexit_write_probe: bool = False,
         ldst_probe: bool = False, gmem_control: bool = False,
         ldst_x2_probe: bool = False, ldst_column_probe: bool = False,
         gmem_ldc_wr: int = 2, gmem_ldc_stall: int = 2,
         gmem_stg_req: str = "2,3", gmem_stg_rd: int = 0,
         gmem_gap_nops: int = 0, block_size: int = 32,
         output_words: int = 0, repetitions: int = 1,
         run_nvcc_function: str = "", cluster_x: int = 0,
         compact_results: bool = False) -> None:
    if compile_source:
        source = Path(compile_source).read_text()
        cubin, sass, elf = compile_remote.remote(source)
        out = Path(compile_output or "/tmp/modal_nvcc_sm100.cubin")
        out.write_bytes(cubin)
        out.with_suffix(".sass").write_text(sass)
        out.with_suffix(".elf.txt").write_text(elf)
        print(f"compiled {compile_source} -> {out} ({len(cubin)} bytes)")
        print(f"SASS: {out.with_suffix('.sass')}")
        print(f"ELF:  {out.with_suffix('.elf.txt')}")
        return
    if hand_source:
        from assembler import assemble_kernel

        source = Path(hand_source).read_text()
        if ldst_column_probe:
            source = make_ldst_column_probe_source(source)
        elif ldst_x2_probe:
            source = make_ldst_x2_probe_source(source)
        elif gmem_control:
            source = make_gmem_control_source(
                source, ldc_wr=gmem_ldc_wr, ldc_stall=gmem_ldc_stall,
                stg_req=gmem_stg_req, stg_rd=gmem_stg_rd,
                gap_nops=gmem_gap_nops)
        elif ldst_probe:
            source = make_ldst_probe_source(source)
        elif atexit_write_probe:
            source = make_atexit_write_probe_source(source)
        elif atexit_probe:
            source = make_atexit_probe_source(source, copy_handler)
        data = assemble_kernel(source, arch="sm100a",
                               check_deps=False).code
        result = run_remote.remote(data, function_name, block_size,
                                   output_words, repetitions, cluster_x)
        print(f"hand source: {hand_source} ({len(data)} cubin bytes)")
        handler_hex = result.pop("handler_hex", "")
        print(result)
        if ldst_probe or gmem_control:
            got = [int(v, 16) for v in result["words32"]]
            print({"lane0_roundtrip": "PASS"
                   if got[0] == 0x12340000 else "FAIL"})
        if ldst_x2_probe or ldst_column_probe:
            got = [int(v, 16) for v in result["words32"]]
            want = [0x12340000, 0x56780000]
            label = ("lane0_column_roundtrip" if ldst_column_probe
                     else "lane0_x2_roundtrip")
            print({label: "PASS"
                   if got[:2] == want else "FAIL"})
        if atexit_write_probe:
            words = [int(v, 16) for v in result["words"]]
            print({
                "original": hex(words[2] | words[3] << 32),
                "written_target": hex(words[4] | words[5] << 32),
                "readback": hex(words[6] | words[7] << 32),
            })
        if copy_handler and handler_hex:
            raw = bytes.fromhex(handler_hex)
            out = Path("/tmp/tcgen05_atexit_handler.bin")
            out.write_bytes(raw)
            print(f"handler bytes: {out} ({len(raw):#x})")
        return
    if hand_cubin:
        data = Path(hand_cubin).read_bytes()
        result = run_remote.remote(data, function_name, block_size,
                                   output_words, repetitions, cluster_x)
        print(f"hand cubin: {hand_cubin} ({len(data)} bytes)")
        result.pop("handler_hex", None)
        if compact_results:
            compact_samples = {}
            first_418_by_mod3 = {}
            transitions_by_mod2 = {}
            for name, samples in result["multi_requested_word_samples"].items():
                compact_samples[name] = [sample[:min(output_words, 32)]
                                         for sample in samples]
                launch_summaries = []
                for sample in samples:
                    words = [int(value, 16) for value in sample[:output_words]]
                    launch_summaries.append([
                        next((index // 3 for index in range(residue, len(words), 3)
                              if words[index] == 0x41800000), None)
                        for residue in range(3)
                    ])
                first_418_by_mod3[name] = launch_summaries
                transition_launches = []
                for sample in samples:
                    words = [int(value, 16) for value in sample[:output_words]]
                    per_residue = []
                    for residue in range(2):
                        transitions = []
                        previous = None
                        for index in range(residue, len(words), 2):
                            value = words[index]
                            if value != previous:
                                transitions.append((index // 2, hex(value)))
                                previous = value
                        per_residue.append(transitions[:32])
                    transition_launches.append(per_residue)
                transitions_by_mod2[name] = transition_launches
            print({
                "multi_requested_word_samples": compact_samples,
                "first_418_round_by_mod3": first_418_by_mod3,
                "transitions_by_mod2": transitions_by_mod2,
                "multi_timer_deltas_u64": result["multi_timer_deltas_u64"],
            })
        else:
            print(result)
        return
    cubin, sass, elf = compile_remote.remote(SOURCE)
    out = Path("/tmp/tcgen05_alloc_sm100.cubin")
    out.write_bytes(cubin)
    if run_nvcc_function:
        result = run_remote.remote(cubin, run_nvcc_function, block_size,
                                   output_words, repetitions, cluster_x)
        result.pop("handler_hex", None)
        print({"nvcc_run": run_nvcc_function, "result": result})
    print(f"wrote {out} ({len(cubin)} bytes)")
    print("\n===== SASS =====")
    print(sass)
    print("\n===== ELF (selected) =====")
    for line in elf.splitlines():
        if any(key in line for key in ("EIATTR_", ".nv.shared", "EF_CUDA_SM")):
            print(line)
