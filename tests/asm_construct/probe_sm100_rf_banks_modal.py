#!/usr/bin/env python3
"""Distinguish 2-bank/2R from 4-bank B200 GPR collection on Modal.

The two-source FADD/HADD2 matrix first establishes whether two reads can be
served from one candidate bank.  The decisive three-source comparison is:

* parity 2-bank/2R: (mod4 0,2,0) has three even sources and takes two cycles;
* mod4 4-bank/2R: (0,2,0) is a 2+1 distribution and remains one cycle.

All math cases use RZ destinations, eliminating GPR writeback from the timed
body.  Packed FFMA2 repeats the test with three 64-bit source pairs.  Multiple
unroll lengths are fit as cycles=m*N+c, so clock-read and launch overhead stays
in the intercept.

Run with the authenticated Modal environment::

    modal run tests/asm_construct/probe_sm100_rf_banks_modal.py
"""

from __future__ import annotations

import ctypes
import statistics
import struct
from pathlib import Path

import modal


CUDA_IMAGE = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .entrypoint([])
)
app = modal.App("b200-rf-bank-probe", image=CUDA_IMAGE)


def source(op: str, ra: int, rb: int, count: int, rc: int | None = None) -> str:
    if op == "fadd":
        instruction = f"FADD RZ, R{ra}, R{rb}"
    elif op == "hadd2":
        instruction = f"HADD2 RZ, R{ra}, R{rb}"
    elif op == "ffma":
        assert rc is not None
        instruction = f"FFMA RZ, R{ra}, R{rb}, R{rc}"
    elif op == "ffma2":
        assert rc is not None
        instruction = (
            "FFMA2.F32x2.F32x2.F32x2 RZ, "
            f"{{R{ra},R{ra + 1}}}, {{R{rb},R{rb + 1}}}, "
            f"{{R{rc},R{rc + 1}}}"
        )
    elif op == "nop":
        instruction = "NOP"
    else:
        raise ValueError(op)
    lines = [
        "#fn rfprobe(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
    ]
    for reg in range(24, 48):
        lines.append(f"    MOV32I R{reg}, 0x3f803c00;[7:7:{{}}:5:1]")
    lines += [
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{0,1}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
    ]
    timed_sched = "[7:7:{}:1:0]" if op == "nop" else "[7:7:{}:1:0:1]"
    lines += [f"    {instruction};{timed_sched}" for _ in range(count)]
    lines += [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R16,R17};[2:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R32,R33};[3:7:{}:1:0]",
        "    EXIT;[7:7:{2,3}:5:0]",
        "}",
    ]
    return "\n".join(lines)


@app.function(gpu="B200", image=CUDA_IMAGE, timeout=600)
def run_batch(items: list[tuple[str, bytes]], reps: int) -> dict[str, list[int]]:
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
        name, desc = ctypes.c_char_p(), ctypes.c_char_p()
        cuda.cuGetErrorName(code, ctypes.byref(name))
        cuda.cuGetErrorString(code, ctypes.byref(desc))
        raise RuntimeError(
            f"{call}: {code} {name.value!r} {desc.value!r}"
        )

    cuda.cuInit.argtypes = [ctypes.c_uint]
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(CUdevice), ctypes.c_int]
    cuda.cuCtxCreate_v2.argtypes = [
        ctypes.POINTER(CUcontext), ctypes.c_uint, CUdevice
    ]
    cuda.cuCtxDestroy_v2.argtypes = [CUcontext]
    cuda.cuModuleLoadData.argtypes = [ctypes.POINTER(CUmodule), ctypes.c_void_p]
    cuda.cuModuleUnload.argtypes = [CUmodule]
    cuda.cuModuleGetFunction.argtypes = [
        ctypes.POINTER(CUfunction), CUmodule, ctypes.c_char_p
    ]
    cuda.cuMemAlloc_v2.argtypes = [ctypes.POINTER(CUdeviceptr), ctypes.c_size_t]
    cuda.cuMemFree_v2.argtypes = [CUdeviceptr]
    cuda.cuMemsetD32_v2.argtypes = [CUdeviceptr, ctypes.c_uint, ctypes.c_size_t]
    cuda.cuLaunchKernel.argtypes = [
        CUfunction,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
    ]
    cuda.cuCtxSynchronize.argtypes = []
    cuda.cuMemcpyDtoH_v2.argtypes = [ctypes.c_void_p, CUdeviceptr, ctypes.c_size_t]

    check(cuda.cuInit(0), "cuInit")
    device = CUdevice()
    check(cuda.cuDeviceGet(ctypes.byref(device), 0), "cuDeviceGet")
    context = CUcontext()
    check(cuda.cuCtxCreate_v2(ctypes.byref(context), 0, device), "cuCtxCreate_v2")
    results: dict[str, list[int]] = {}
    try:
        allocation = CUdeviceptr()
        check(cuda.cuMemAlloc_v2(ctypes.byref(allocation), 16), "cuMemAlloc_v2")
        try:
            for label, image in items:
                blob = ctypes.create_string_buffer(image)
                module, function = CUmodule(), CUfunction()
                check(
                    cuda.cuModuleLoadData(
                        ctypes.byref(module), ctypes.cast(blob, ctypes.c_void_p)
                    ),
                    f"cuModuleLoadData({label})",
                )
                try:
                    check(
                        cuda.cuModuleGetFunction(
                            ctypes.byref(function), module, b"_Z7rfprobe"
                        ),
                        f"cuModuleGetFunction({label})",
                    )
                    arg0 = CUdeviceptr(allocation.value)
                    params = (ctypes.c_void_p * 1)(
                        ctypes.cast(ctypes.byref(arg0), ctypes.c_void_p)
                    )
                    samples = []
                    for rep in range(reps + 1):
                        check(cuda.cuMemsetD32_v2(allocation, 0, 4), "cuMemsetD32_v2")
                        check(
                            cuda.cuLaunchKernel(
                                function, 1, 1, 1, 1, 1, 1,
                                0, None, params, None,
                            ),
                            f"cuLaunchKernel({label})",
                        )
                        check(cuda.cuCtxSynchronize(), "cuCtxSynchronize")
                        out = (ctypes.c_uint64 * 2)()
                        check(
                            cuda.cuMemcpyDtoH_v2(
                                ctypes.byref(out), allocation, ctypes.sizeof(out)
                            ),
                            "cuMemcpyDtoH_v2",
                        )
                        if rep:
                            samples.append((out[1] - out[0]) & 0xFFFFFFFFFFFFFFFF)
                    results[label] = samples
                finally:
                    check(cuda.cuModuleUnload(module), "cuModuleUnload")
        finally:
            check(cuda.cuMemFree_v2(allocation), "cuMemFree_v2")
    finally:
        check(cuda.cuCtxDestroy_v2(context), "cuCtxDestroy_v2")
    return results


def fit_slope(points: list[tuple[int, float]]) -> float:
    xm = statistics.mean(x for x, _ in points)
    ym = statistics.mean(y for _, y in points)
    return (
        sum((x - xm) * (y - ym) for x, y in points)
        / sum((x - xm) ** 2 for x, _ in points)
    )


@app.local_entrypoint()
def main(reps: int = 5, smoke: bool = False, ffma: bool = False,
         ffma2: bool = False) -> None:
    # Modal ships this script alone to /root for the remote function.  Keep
    # repository-relative imports local: run_batch only consumes cubin bytes.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from assembler import assemble

    if smoke:
        image = assemble(source("nop", 24, 28, 16), arch="sm100",
                         check_deps=False)
        raw = run_batch.remote([("smoke", image)], max(reps, 1))
        print(f"B200 smoke cycles: {raw['smoke']}")
        return

    lengths = (128, 256, 512)
    if ffma2:
        patterns = {
            "all_start0": (24, 28, 32),
            "all_start2": (26, 30, 34),
            "split_002": (24, 28, 26),
            "split_020": (24, 26, 28),
            "split_200": (26, 24, 28),
            "split_022": (24, 26, 30),
            "split_202": (26, 24, 30),
            "split_220": (26, 30, 24),
        }
        items = []
        for label, (ra, rb, rc) in patterns.items():
            for n in lengths:
                items.append((
                    f"ffma2:{label}:N{n}",
                    assemble(source("ffma2", ra, rb, n, rc), arch="sm100",
                             check_deps=False),
                ))
        for n in lengths:
            items.append((
                f"nop:00:N{n}",
                assemble(source("nop", 24, 28, n), arch="sm100",
                         check_deps=False),
            ))
        raw = run_batch.remote(items, reps)
        print("B200 packed FFMA2 slopes (SR_CLOCK ticks/instruction)")
        for label in patterns:
            points = [(n, float(min(raw[f"ffma2:{label}:N{n}"])))
                      for n in lengths]
            print(f"  {label:16s} {fit_slope(points):7.3f}")
        nop_points = [(n, float(min(raw[f"nop:00:N{n}"])))
                      for n in lengths]
        print(f"  {'NOP':16s} {fit_slope(nop_points):7.3f}")
        return

    if ffma:
        # Distinct physical registers are used even when residues repeat.
        # The permutations separate a bank-count effect from operand-port
        # asymmetry in the FMA collector.
        patterns = {
            "distinct_012": (24, 25, 26),
            "split_002": (24, 28, 26),
            "split_020": (24, 26, 28),
            "split_200": (26, 24, 28),
            "split_022": (24, 26, 30),
            "split_202": (26, 24, 30),
            "split_220": (26, 30, 24),
            "same4_000": (24, 28, 32),
            "same4_222": (26, 30, 34),
            "odd_split_113": (25, 29, 27),
            "odd_split_133": (25, 27, 31),
            "same4_111": (25, 29, 33),
            "same4_333": (27, 31, 35),
        }
        items = []
        for label, (ra, rb, rc) in patterns.items():
            for n in lengths:
                items.append((
                    f"ffma:{label}:N{n}",
                    assemble(source("ffma", ra, rb, n, rc), arch="sm100",
                             check_deps=False),
                ))
        for n in lengths:
            items.append((
                f"nop:00:N{n}",
                assemble(source("nop", 24, 28, n), arch="sm100",
                         check_deps=False),
            ))
        raw = run_batch.remote(items, reps)
        print("B200 three-source FFMA slopes (SR_CLOCK ticks/instruction)")
        for label in patterns:
            points = [(n, float(min(raw[f"ffma:{label}:N{n}"])))
                      for n in lengths]
            print(f"  {label:16s} {fit_slope(points):7.3f}")
        nop_points = [(n, float(min(raw[f"nop:00:N{n}"])))
                      for n in lengths]
        print(f"  {'NOP':16s} {fit_slope(nop_points):7.3f}")
        return

    items: list[tuple[str, bytes]] = []
    # Full low-two-bit matrix.  Same-residue pairs use a distinct register
    # four positions away, avoiding duplicate-operand broadcast/elision.
    for op in ("fadd", "hadd2"):
        for a in range(4):
            for b in range(4):
                ra = 24 + a
                rb = 28 + b if a == b else 24 + b
                for n in lengths:
                    label = f"{op}:{a}{b}:N{n}"
                    items.append(
                        (label, assemble(source(op, ra, rb, n),
                                         arch="sm100", check_deps=False))
                    )
    for n in lengths:
        items.append(
            (f"nop:00:N{n}", assemble(source("nop", 24, 28, n),
                                       arch="sm100", check_deps=False))
        )

    raw = run_batch.remote(items, reps)
    print("B200 RF source-collection slopes (cycles/instruction)")
    for op in ("fadd", "hadd2"):
        matrix = []
        print(f"\n{op.upper()} rows=Ra mod4, columns=Rb mod4")
        for a in range(4):
            row = []
            for b in range(4):
                points = []
                for n in lengths:
                    samples = raw[f"{op}:{a}{b}:N{n}"]
                    points.append((n, float(min(samples))))
                row.append(fit_slope(points))
            matrix.append(row)
            print("  " + " ".join(f"{x:7.3f}" for x in row))
        same4 = statistics.mean(matrix[i][i] for i in range(4))
        same2_not4 = statistics.mean(
            (matrix[0][2], matrix[2][0], matrix[1][3], matrix[3][1])
        )
        different_parity = statistics.mean(
            matrix[a][b] for a in range(4) for b in range(4)
            if (a ^ b) & 1
        )
        print(
            f"  same mod4={same4:.3f}, same parity/different mod4="
            f"{same2_not4:.3f}, different parity={different_parity:.3f}"
        )
    nop_points = [
        (n, float(min(raw[f"nop:00:N{n}"]))) for n in lengths
    ]
    print(f"\nNOP control: {fit_slope(nop_points):.3f} cycles/instruction")


if __name__ == "__main__":
    # Normal invocation is through `modal run`; this guard only prevents an
    # accidental plain Python execution from silently doing nothing.
    raise SystemExit("use: modal run tests/asm_construct/probe_sm100_rf_banks_modal.py")
