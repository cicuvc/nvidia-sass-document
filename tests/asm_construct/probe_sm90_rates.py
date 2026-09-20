#!/usr/bin/env python3
"""H100 (sm_90) clean solo pipe rates via CS2R windows.

Every stream runs in one warp, bracket variants per op.  The H20 conflict
note's "~2.0 cyc/inst solo" numbers were measured with yield=1 brackets
([7:7:{}:1:1]) — after the yield=1-switch-cost discovery (see
notes/sm120/yield_dispatch_cost.md) those numbers are suspect, so this probe
re-measures with [7:7:{}:1:0:7] (no yield, reuse) and [7:7:{}:1:1] (yield).

Run:  ASSEMBLER_ARCH=sm90 python3 probe_sm90_rates.py        (on an H100)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from archutil import adapt_source  # noqa: E402

OPS = {
    "nop": "NOP",
    "mov": "MOV R{d}, R4",
    "iadd": "IADD R{d}, PT, R4, R9",
    "iadd3": "IADD3 R{d}, R4, R9, R8",
    "lop3": "LOP3.LUT R{d}, R4, R9, R8, 0x96",
    "shf": "SHF.L.U32 R{d}, R4, 0x3, R9",
    "prmt": "PRMT R{d}, R4, 0x3210, R9",
    "imnmx": "IMNMX R{d}, R4, R9, PT",
    "isel": "SEL R{d}, R4, R9, P0",
    "fmnmx": "FMNMX R{d}, R4, R9, PT",
    "fsel": "FSEL R{d}, R4, R9, PT",
    "imad": "IMAD R{d}, R4, R9, R8",
    "imad_wide": "IMAD.WIDE {{R{d},R{d}1}}, R4, R9, {{R8,R9}}",
    "imad_hi": "IMAD.HI R{d}, R4, R9, {{R8,R9}}",
    "idp4a": "IDP.4A.U8.U8 R{d}, R4, R9, R8",
    "ffma": "FFMA R{d}, R4, R9, R8",
    "fadd": "FADD R{d}, R4, R9",
    "fmul": "FMUL R{d}, R4, R9",
    "hfma2": "HFMA2 R{d}, R4, R9, R8",
    "hadd2": "HADD2 R{d}, R4, R9",
    "dadd": "DADD {{R{d},R{d}1}}, {{R4,R5}}, {{R8,R9}}",
    "dfma": "DFMA {{R{d},R{d}1}}, {{R4,R5}}, {{R8,R9}}, {{R10,R11}}",
    "mufu": "MUFU.RCP R{d}, R4",
    "isetp": "ISETP.LT.AND P0, PT, R4, R9, PT",
}

N = 1024


def src(op: str, bracket: str) -> str:
    lines = [
        "#fn t(out<8>) {",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:2:0]",
        "    MOV32I R4, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R8, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R9, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R10, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R11, 0x3f803c00;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R4, R4, PT;[7:7:{}:5:1]",
        "    MOV R12, RZ;[7:7:{1}:5:1]",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
    ]
    wide = "WIDE" in OPS[op] or OPS[op].split()[0] in ("DADD", "DFMA")
    for j in range(N):
        d = 40 + (j % 20) * (2 if wide else 1)
        inst = OPS[op].replace("{d}1", str(d + 1)).format(d=d)
        lines.append(f"    {inst};{bracket}")
    lines += [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    IADD3 R30, R30, R12, RZ;[7:7:{}:5:1]",
        "    STG.E.64 [{R2,R3}], {R30,R31};[0:1:{}:8:0]",
        "    STG.E.64 [{R2,R3}+0x8], {R32,R33};[0:1:{}:8:0]",
        "    EXIT;[7:7:{0}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(op, bracket, reps=8):
    mod = CudaModule(assemble(adapt_source(src(op, bracket)), check_deps=False))
    out = mod.devmem_alloc(16)
    best = None
    mod.launch("t", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    for _ in range(reps):
        mod.launch("t", grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
        if best is None or t1 - t0 < best:
            best = t1 - t0
    mod.devmem_free(out)
    return best / N


def main():
    print(f"{'op':10s} {'reuse':>7s} {'yield':>7s}")
    for op in OPS:
        # batch_t=7 is an illegal combination for fe/mio ops (NOP/MUFU)
        br_plain = "[7:7:{}:1:0]" if op in ("nop", "mufu") else "[7:7:{}:1:0:7]"
        try:
            r_reuse = run(op, br_plain)
        except Exception as e:
            r_reuse = f"ERR:{str(e)[:40]}"
        try:
            r_yield = run(op, "[7:7:{}:1:1]")
        except Exception as e:
            r_yield = f"ERR:{str(e)[:40]}"
        def fmt(x):
            return f"{x:7.3f}" if isinstance(x, float) else f"{x:>7s}"
        print(f"{op:10s} {fmt(r_reuse)} {fmt(r_yield)}", flush=True)


if __name__ == "__main__":
    main()
