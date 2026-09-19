#!/usr/bin/env python3
"""Windowed CS2R same-subcore conflict probe (sm_89 methodology fix).

The A100-style conflict probe (min-over-reps victim slope) is unreliable on
sm_89 because same-subcore warp pairs are bistable: some launches fully
serialize victim and contender (contender window starts exactly when the
victim's ends).  This probe records per-warp CS2R start/end timestamps and
selects the max-overlap rep, reporting per-warp inst/clk and the aggregate.

Run:  PROBE_ARCH=sm89 python3 tests/asm_construct/probe_sm89_scalar_windows.py
"""
import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble

INST = {
  "ffma": "FFMA R{d}, R4, R9, R8",
  "fadd": "FADD R{d}, R4, R9",
  "iadd": "IADD R{d}, PT, R4, R9",
  "iadd3": "IADD3 R{d}, R4, R9, R8",
  "imad": "IMAD R{d}, R4, R9, R8",
  "hfma2": "HFMA2 R{d}, R4, R9, R8",
  "mov":  "MOV R{d}, R4",
  "nop":  "NOP",
}

def src(insts, warps, n, block=512):
    # every listed warp runs insts[w % len] for n insts; windows recorded
    lines = [
        "#fn t(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    S2R R0, SR_TID.X;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
        "    NOP;[7:7:{}:1:1]",
        "    MOV R6, 0x10;[7:7:{}:6:0]",
        "    IMAD.WIDE.U32 {R2,R3}, R0, R6, c[0x0][0x160];[7:7:{}:6:0]",
        "    SHR R5, R0, 0x5;[7:7:{}:6:0]",
    ]
    for i, w in enumerate(warps):
        lines.append(f"    ISETP.EQ.AND P{i}, PT, R5, 0x{w:x}, PT;[7:7:{{}}:13:1]")
    lines += [
        "    MOV R4, 0x3f800000;[7:7:{}:6:0]",
        "    MOV R8, 0x3f000000;[7:7:{}:6:0]",
        "    MOV R9, 0x40000000;[7:7:{}:6:0]",
        "    BAR.SYNC 0;[7:7:{}:6:0]",
    ]
    for i, w in enumerate(warps):
        lines.append(f"    @P{i} BRA #label(w{i});[7:7:{{}}:6:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    for i, w in enumerate(warps):
        inst = INST[insts[i % len(insts)]]
        lines.append(f"#def_label(w{i})")
        lines.append("    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]")
        lines.append("    NOP;[7:7:{}:1:1]")
        lines += [f"    {inst.format(d=40+j%40)};[7:7:{{}}:1:0:7]" for j in range(n)]
        lines += [
            "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
            "    STG.E.64.STRONG.GPU [{R2,R3}], {R30,R31};[0:1:{}:8:0]",
            "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R32,R33};[0:1:{}:8:0]",
            "    EXIT;[7:7:{}:5:0]",
        ]
    lines.append("}")
    return "\n".join(lines)

def run(insts, warps, n=512, block=512, reps=10):
    mod = CudaModule(assemble(src(insts, warps, n, block), arch="sm89", check_deps=False))
    out = mod.devmem_alloc(block*16)
    mod.launch("t", grid=(1,), block=(block,), args=[out]); mod.synchronize()
    best = None
    for _ in range(reps):
        mod.launch("t", grid=(1,), block=(block,), args=[out]); mod.synchronize()
        raw = mod.device_read(out, block*16)
        rec = {w: struct.unpack_from("<QQ", raw, w*32*16) for w in warps}
        ov0 = max(t0 for t0, _ in rec.values()); ov1 = min(t1 for _, t1 in rec.values()); ov = ov1 - ov0
        if best is None or ov > best[1]:
            best = (rec, ov)
    mod.devmem_free(out)
    rec, _ = best
    start = min(t0 for t0, _ in rec.values())
    end = max(t1 for _, t1 in rec.values())
    ov0 = max(t0 for t0, _ in rec.values())
    ov1 = min(t1 for _, t1 in rec.values())
    agg_all = len(warps) * n / (end - start)
    per = {w: n / (t1 - t0) for w, (t0, t1) in rec.items()}
    return per, agg_all, ov1 - ov0

cases = [
    (["hfma2"], [0, 4]),
    (["hfma2"], [0, 4, 8, 12]),
    (["ffma", "hfma2"], [0, 4]),
    (["iadd", "hfma2"], [0, 4]),
    (["fadd"], [0, 4]),
    (["iadd", "fadd"], [0, 4]),
    (["ffma", "fadd"], [0, 4]),
    (["iadd", "ffma"], [0, 4]),
    (["ffma", "iadd"], [0, 4]),
    (["ffma", "imad"], [0, 4]),
    (["iadd", "imad"], [0, 4]),
    (["hfma2", "imad"], [0, 4]),
]
for insts, warps in cases:
    per, agg, ov = run(insts, warps)
    p = " ".join(f"w{w}={r:.2f}" for w, r in per.items())
    print(f"{'/'.join(insts):20s} warps={warps} per-warp inst/clk: {p}  aggregate={agg:.2f}/clk  overlap={ov}", flush=True)
print("DONE")
