#!/usr/bin/env python3
"""Run fixed-pipeline short-burst admission probes on a Modal B200."""

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
app = modal.App("sm100-scalar-admission", image=IMAGE)


@app.function(gpu="B200", timeout=600)
def run_cases(cases: list[
        tuple[str, bytes, str, int, int, tuple[int, ...]]],
              repetitions: int) -> list[tuple[str, list[int]]]:
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
    output_size = max(size for _, _, _, _, size, _ in cases)
    allocation = CUdeviceptr()
    check(cuda.cuMemAlloc_v2(
        ctypes.byref(allocation), output_size), "cuMemAlloc")
    results = []
    for label, cubin, function_name, block_size, requested_size, actors in cases:
        module, function = CUmodule(), CUfunction()
        blob = ctypes.create_string_buffer(cubin)
        check(cuda.cuModuleLoadData(
            ctypes.byref(module), ctypes.cast(blob, ctypes.c_void_p)),
            "cuModuleLoadData")
        check(cuda.cuModuleGetFunction(
            ctypes.byref(function), module,
            f"_Z{len(function_name)}{function_name}".encode()),
            "cuModuleGetFunction")
        spans = []
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
            if not launch_index:
                continue
            host = (ctypes.c_ubyte * requested_size)()
            check(cuda.cuMemcpyDtoH_v2(
                ctypes.byref(host), allocation, requested_size),
                "cuMemcpyDtoH")
            raw = bytes(host)
            times = [struct.unpack_from("<QQ", raw, warp * 16)
                     for warp in actors]
            spans.append(max(t1 for _, t1 in times)
                         - min(t0 for t0, _ in times))
        results.append((label, spans))
        check(cuda.cuModuleUnload(module), "cuModuleUnload")
    return results


def parse_csv(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def parse_counts(text: str) -> list[int]:
    if "-" in text:
        lo, hi = (int(x) for x in text.split("-", 1))
        return list(range(lo, hi + 1))
    return [int(x) for x in text.split(",") if x.strip()]


BARRIER_OPS = {
    "aluheavy": "@P6 IADD3 RZ, RZ, RZ, RZ",
    "lop3": "@P6 LOP3.LUT RZ, RZ, RZ, RZ, 0x96",
    "shf": "@P6 SHF.R.U32.HI RZ, RZ, RZ, RZ",
    "alulite": "@P6 IADD RZ, PT, RZ, RZ",
    "mov": "@P6 MOV RZ, RZ",
    "isetp": "@P6 ISETP.NE.AND P1, PT, RZ, RZ, PT",
    "fmaheavy": "@P6 IMAD RZ, RZ, RZ, RZ",
    "imul": "@P6 IMUL.U32 RZ, RZ, RZ",
    "fswzadd": "@P6 FSWZADD.NDV RZ, RZ, RZ, PPPPPPPP",
    "fmalite": "@P6 FFMA RZ, RZ, RZ, RZ",
    "fadd": "@P6 FADD RZ, RZ, RZ",
    "fmul": "@P6 FMUL RZ, RZ, RZ",
    "packed": "@P6 HFMA2 RZ, RZ, RZ, RZ",
    "hadd2": "@P6 HADD2 RZ, RZ, RZ",
    "hmul2": "@P6 HMUL2 RZ, RZ, RZ",
    "rf_aluheavy": "@P6 IADD3 RZ, R24, R26, R28",
    "rf_fmaheavy": "@P6 IMAD RZ, R24, R26, R28",
}

BARRIER_MIX = {
    "mix_aluh_alul": ("aluheavy", "alulite"),
    "mix_aluh_fmah": ("aluheavy", "fmaheavy"),
    "mix_aluh_fmal": ("aluheavy", "fmalite"),
    "mix_aluh_fp16": ("aluheavy", "packed"),
    "mix_alul_fmah": ("alulite", "fmaheavy"),
    "mix_alul_fmal": ("alulite", "fmalite"),
    "mix_alul_fp16": ("alulite", "packed"),
    "mix_fmah_fmal": ("fmaheavy", "fmalite"),
    "mix_fmah_fp16": ("fmaheavy", "packed"),
    "mix_fmal_fp16": ("fmalite", "packed"),
    "mix_rf_aluh_fmah": ("rf_aluheavy", "rf_fmaheavy"),
}

BARRIER_SCHED = {
    "rf_aluheavy": "[7:7:{}:1:0]",
    "rf_fmaheavy": "[7:7:{}:1:0]",
}

BARRIER_PLACEMENTS = {
    "one": ((0,), 1),
    "same2": ((0, 4), 1),
    "diff2": ((0, 1), 2),
}


def barrier_source(n: int, mode: str, placement: str, active: bool,
                   producer_delay: int = 0) -> tuple[str, int]:
    """Time producer progress with a CBU barrier and clean-subcore observer.

    Unlike an ending CS2R in the producer, BAR.SYNC does not need int_pipe.
    The observer is placed on a subcore not occupied by any producer, so its
    ending CS2R cannot wait behind the INT burst being measured.
    """
    producers, observer = BARRIER_PLACEMENTS[placement]
    op_names = BARRIER_MIX.get(mode, (mode,))
    ops = tuple(BARRIER_OPS[name] for name in op_names)
    if active:
        ops = tuple(op.removeprefix("@P6 ") for op in ops)
    lines = [
        "#fn fixedbarrier(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    ISETP.F P6, RZ, RZ;[7:7:{}:13:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for warp in producers:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
            "[7:7:{}:13:1]",
            "    @P0 BRA #label(producer);[7:7:{}:5:1]",
        ]
    lines += [
        f"    ISETP.EQ.AND P0, PT, R5, 0x{observer:x}, PT;"
        "[7:7:{}:13:1]",
        "    @P0 BRA #label(observer);[7:7:{}:5:1]",
        # Warps between a sparse producer/observer placement must exit here,
        # not join BAR 1: their longer comparison path otherwise determines
        # the apparent short-burst knee.  Exited warps are no longer barrier
        # participants.
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(producer)",
    ]
    lines += ["    NOP;[7:7:{}:8:1]" for _ in range(producer_delay)]
    lines += [f"    {ops[i % len(ops)]};"
              f"{BARRIER_SCHED.get(op_names[i % len(ops)], '[7:7:{}:1:0:7]')}"
              for i in range(n)]
    lines += [
        "    BRA #label(join);[7:7:{}:5:1]",
        "#def_label(observer)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "#def_label(join)",
        f"    BAR.SYNC 1, 0x{(len(producers) + 1) * 32:x};"
        "[7:7:{}:5:1]",
        f"    ISETP.EQ.AND P0, PT, R5, 0x{observer:x}, PT;"
        "[7:7:{}:13:1]",
        "    @!P0 BRA #label(done);[7:7:{}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines), (max(*producers, observer) + 1) * 32


def phased_source(n_first: int, first_mode: str, n_second: int,
                  second_mode: str, gap: int, gap_kind: str,
                  placement: str, active: bool,
                  producer_delay: int = 0) -> tuple[str, int]:
    """Issue A**n_first, an optional phase boundary, then B**n_second."""
    producers, observer = BARRIER_PLACEMENTS[placement]
    first = BARRIER_OPS[first_mode]
    second = BARRIER_OPS[second_mode]
    if active:
        first = first.removeprefix("@P6 ")
        second = second.removeprefix("@P6 ")
    lines = [
        "#fn phasedbarrier(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(4)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    ISETP.F P6, RZ, RZ;[7:7:{}:13:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for warp in producers:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
            "[7:7:{}:13:1]",
            "    @P0 BRA #label(producer);[7:7:{}:5:1]",
        ]
    lines += [
        f"    ISETP.EQ.AND P0, PT, R5, 0x{observer:x}, PT;"
        "[7:7:{}:13:1]",
        "    @P0 BRA #label(observer);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(producer)",
    ]
    lines += ["    NOP;[7:7:{}:8:1]" for _ in range(producer_delay)]
    lines += [f"    {first};[7:7:{{}}:1:0:7]" for _ in range(n_first)]
    if gap_kind == "nop":
        lines += ["    NOP;[7:7:{}:1:0]" for _ in range(gap)]
    elif gap_kind == "nanosleep":
        lines += [f"    NANOSLEEP 0x{gap:x};[7:7:{{}}:5:1]"]
    elif gap_kind == "syncbar":
        lines += [
            f"    BAR.SYNC 2, 0x{(len(producers) + 1) * 32:x};"
            "[7:7:{}:5:1]",
        ]
    elif gap_kind == "ldswait":
        for _ in range(gap):
            lines += [
                "    LDS R30, [RZ];[5:7:{}:1:0]",
                "    NOP;[7:7:{5}:1:0]",
            ]
    else:
        raise ValueError(f"invalid phase gap kind: {gap_kind}")
    lines += [f"    {second};[7:7:{{}}:1:0:7]" for _ in range(n_second)]
    lines += [
        "    BRA #label(join);[7:7:{}:5:1]",
        "#def_label(observer)",
    ]
    if gap_kind == "syncbar":
        lines += [
            f"    BAR.SYNC 2, 0x{(len(producers) + 1) * 32:x};"
            "[7:7:{}:5:1]",
        ]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "#def_label(join)",
        f"    BAR.SYNC 1, 0x{(len(producers) + 1) * 32:x};"
        "[7:7:{}:5:1]",
        f"    ISETP.EQ.AND P0, PT, R5, 0x{observer:x}, PT;"
        "[7:7:{}:13:1]",
        "    @!P0 BRA #label(done);[7:7:{}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines), (max(*producers, observer) + 1) * 32


@app.local_entrypoint()
def main(modes: str = "aluheavy,fmaheavy,fmalite,packed,alulite",
         placements: str = "one", counts: str = "0-16",
         repetitions: int = 7, active: bool = False,
         prefix_hi: int = 0, prefix_packed: int = 0,
         prefix_active: bool = False,
         barrier_method: bool = False,
         producer_delay: int = 0, phase_pairs: str = "",
         phase_prefixes: str = "0,3,5,8,12",
         phase_suffixes: str = "0-16",
         phase_gaps: str = "0,2,4,8",
         phase_gap_kind: str = "nop") -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(HERE.parent))
    from assembler import assemble
    from probe_scalar_admission_depth import ACTORS, OPS, source

    selected_modes = parse_csv(modes)
    selected_placements = parse_csv(placements)
    ns = parse_counts(counts)
    pairs = []
    for item in parse_csv(phase_pairs):
        names = item.split(":", 1)
        if len(names) != 2:
            raise ValueError(f"invalid phase pair: {item!r}")
        pairs.append(tuple(names))
    phase_as = parse_counts(phase_prefixes)
    phase_bs = parse_counts(phase_suffixes)
    gaps = parse_counts(phase_gaps)
    valid_modes = ({**BARRIER_OPS, **BARRIER_MIX}
                   if barrier_method else OPS)
    valid_placements = BARRIER_PLACEMENTS if barrier_method else ACTORS
    if ((not pairs and not selected_modes)
            or any(mode not in valid_modes for mode in selected_modes)
            or not selected_placements
            or any(place not in valid_placements
                   for place in selected_placements)
            or not ns or min(ns) < 0 or max(ns) > 100
            or not phase_as or min(phase_as) < 0 or max(phase_as) > 100
            or not phase_bs or min(phase_bs) < 0 or max(phase_bs) > 100
            or not gaps or min(gaps) < 0
            or max(gaps) > (0x10000 if phase_gap_kind == "nanosleep" else 64)
            or any(a not in BARRIER_OPS or b not in BARRIER_OPS
                   for a, b in pairs)
            or phase_gap_kind not in {
                "nop", "nanosleep", "syncbar", "ldswait"
            }
            or repetitions <= 0 or not 0 <= producer_delay <= 32):
        raise ValueError("invalid mode, placement, count, or repetition")

    cases = []
    if pairs:
        for first_mode, second_mode in pairs:
            for placement in selected_placements:
                for gap in gaps:
                    for n_first in phase_as:
                        for n_second in phase_bs:
                            src, block_size = phased_source(
                                n_first, first_mode, n_second, second_mode,
                                gap, phase_gap_kind, placement, active,
                                producer_delay)
                            cubin = assemble(
                                src, arch="sm100a", check_deps=True)
                            label = (f"phase:{first_mode}:{second_mode}:"
                                     f"{placement}:A={n_first}:B={n_second}:"
                                     f"G={gap}")
                            cases.append((label, cubin, "phasedbarrier",
                                          block_size, 16, (0,)))
        result_map = dict(run_cases.remote(cases, repetitions))
        for first_mode, second_mode in pairs:
            for placement in selected_placements:
                print(f"phase={first_mode}->{second_mode} "
                      f"placement={placement} active={active} "
                      f"gap_kind={phase_gap_kind}")
                print(f"B={','.join(map(str, phase_bs))}")
                for gap in gaps:
                    for n_first in phase_as:
                        medians = []
                        for n_second in phase_bs:
                            label = (f"phase:{first_mode}:{second_mode}:"
                                     f"{placement}:A={n_first}:B={n_second}:"
                                     f"G={gap}")
                            medians.append(statistics.median(result_map[label]))
                        base = medians[0]
                        extra = [value - base for value in medians]
                        print(f"A={n_first:2d} gap={gap:2d} base={base:g} "
                              f"dB={','.join(f'{x:g}' for x in extra)}")
        return

    for mode in selected_modes:
        for placement in selected_placements:
            for n in ns:
                if barrier_method:
                    src, block_size = barrier_source(
                        n, mode, placement, active, producer_delay)
                    function_name = "fixedbarrier"
                    output_size = 16
                    actors = (0,)
                else:
                    actors = ACTORS[placement]
                    block_size = (max(actors) + 1) * 32
                    output_size = (max(actors) + 1) * 16
                    src = source(n, mode, actors, active, True, prefix_hi,
                                 prefix_packed, prefix_active, 0)
                    function_name = "scalarburst"
                cubin = assemble(src, arch="sm100a", check_deps=True)
                label = f"{mode}:{placement}:N={n}"
                cases.append((label, cubin, function_name, block_size,
                              output_size, actors))

    result_map = dict(run_cases.remote(cases, repetitions))
    for mode in selected_modes:
        for placement in selected_placements:
            print(f"mode={mode} placement={placement} active={active} "
                  f"prefix_hi={prefix_hi} prefix_packed={prefix_packed} "
                  f"prefix_active={prefix_active} "
                  f"barrier_method={barrier_method} "
                  f"producer_delay={producer_delay}")
            print("N median min max delta")
            previous = None
            for n in ns:
                values = result_map[f"{mode}:{placement}:N={n}"]
                med = statistics.median(values)
                delta = "-" if previous is None else f"{med - previous:g}"
                print(f"{n:2d} {med:6g} {min(values):3d} "
                      f"{max(values):3d} {delta}")
                previous = med
