#!/usr/bin/env python3
"""H100 (sm_90) windowed two-warp same-subcore conflict matrix.

Method: victim = w0 (512 insts), contender = w4 (2048 insts, same SMSP since
warp%4), both timestamped with CS2R; take the max-overlap rep and compute
per-warp rates inside the overlap window.  Clean brackets [7:7:{}:1:0:7]
(no yield — the yield switch cost confounds; see notes/sm120/
yield_dispatch_cost.md).  Each (victim, contender) pair runs in a subprocess
(fault isolation is unnecessary but keeps CUDA contexts fresh).

Answer sought: which pipe pairs share a datapath on GH100?
  aggregate == slower solo rate  -> shared single server
  aggregate == sum of solo rates -> disjoint resources
"""
import struct
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

OPS = {
    "ffma":  ("FFMA R{d}, R4, R9, R8", 1),
    "fadd":  ("FADD R{d}, R4, R9", 1),
    "iadd3": ("IADD3 R{d}, R4, R9, R8", 1),
    "lop3":  ("LOP3.LUT R{d}, R4, R9, R8, 0x96", 1),
    "imad":  ("IMAD R{d}, R4, R9, R8", 1),
    "hfma2": ("HFMA2 R{d}, R4, R9, R8", 1),
    "dadd":  ("DADD {{R{d},R{d}1}}, {{R4,R5}}, {{R8,R9}}", 2),
    "mufu":  ("MUFU.RCP R{d}, R4", 1),
    "nop":   ("NOP", 1),
}

BR = {"mufu": "[7:7:{}:1:0]", "nop": "[7:7:{}:1:0]"}
DEFAULT_BR = "[7:7:{}:1:0:7]"


def build(victim, contender, nv=1024, nc=1024):
    def body(op, n):
        tmpl, stride = OPS[op]
        out = []
        for j in range(n):
            d = 40 + (j % 18) * stride
            inst = tmpl.replace("{d}1", str(d + 1)).format(d=d)
            out.append(f"    {inst};{BR.get(op, DEFAULT_BR)}")
        return out

    lines = [
        "#fn t(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:2:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{4}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    ISETP.EQ.AND P1, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    MOV32I R4, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R8, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R9, 0x3f803c00;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:6:0]",
        "    @P0 BRA #label(victim);[7:7:{}:6:0]",
        "    @P1 BRA #label(contender);[7:7:{}:6:0]",
        "    EXIT;[7:7:{}:5:0]",
        "#def_label(victim)",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
    ]
    lines += body(victim, nv)
    lines += [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    STG.E.64 [{R6,R7}], {R30,R31};[0:1:{}:8:0]",
        "    STG.E.64 [{R6,R7}+0x8], {R32,R33};[0:1:{}:8:0]",
        "    EXIT;[7:7:{0}:5:0]",
        "#def_label(contender)",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
    ]
    lines += body(contender, nc)
    lines += [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    STG.E.64 [{R6,R7}], {R30,R31};[0:1:{}:8:0]",
        "    STG.E.64 [{R6,R7}+0x8], {R32,R33};[0:1:{}:8:0]",
        "    EXIT;[7:7:{0}:5:0]",
        "}",
    ]
    return "\n".join(lines), nv, nc


def run_pair(victim, contender, reps=16):
    sys.path.insert(0, str(REPO))
    from assembler import CudaModule, assemble
    from archutil import adapt_source
    src, nv, nc = build(victim, contender)
    mod = CudaModule(assemble(adapt_source(src), check_deps=False))
    out = mod.devmem_alloc(256 * 16)
    mod.launch("t", grid=(1,), block=(256,), args=[out])
    mod.synchronize()
    best = None
    for _ in range(reps):
        mod.launch("t", grid=(1,), block=(256,), args=[out])
        mod.synchronize()
        raw = mod.device_read(out, 256 * 16)
        v0, v1 = struct.unpack_from("<QQ", raw, 0)
        c0, c1 = struct.unpack_from("<QQ", raw, 128 * 16)
        ov = max(0, min(v1, c1) - max(v0, c0))
        if best is None or ov > best[0]:
            best = (ov, v0, v1, c0, c1)
    mod.devmem_free(out)
    ov, v0, v1, c0, c1 = best
    # Equal-length streams: in the max-overlap rep both windows approximate
    # the common interval, so whole-window rates are the contention rates.
    union = max(v1, c1) - min(v0, c0)
    v_rate = nv / (v1 - v0)
    c_rate = nc / (c1 - c0)
    return (f"{victim:6s}<-{contender:6s} overlap/union={ov / union:4.2f} "
            f"victim={v_rate:.3f} contender={c_rate:.3f} agg={v_rate + c_rate:.3f} inst/clk")


# solo cycles/inst from probe_sm90_rates.py on H100 (2026-09-20)
SOLO = {"ffma": 1.008, "fadd": 1.008, "iadd3": 2.008, "lop3": 2.008,
        "imad": 2.007, "hfma2": 2.007, "dadd": 2.007, "mufu": 7.998,
        "nop": 1.008}


PAIRS = [
    ("ffma", "ffma"), ("iadd3", "iadd3"), ("imad", "imad"),
    ("hfma2", "hfma2"), ("dadd", "dadd"),
    ("ffma", "iadd3"), ("iadd3", "ffma"),
    ("ffma", "imad"), ("imad", "ffma"),
    ("iadd3", "imad"), ("imad", "iadd3"),
    ("ffma", "hfma2"), ("hfma2", "ffma"),
    ("ffma", "dadd"), ("dadd", "ffma"),
    ("ffma", "mufu"), ("iadd3", "mufu"),
    ("iadd3", "lop3"),
]

if __name__ == "__main__":
    if len(sys.argv) == 3:
        print(run_pair(sys.argv[1], sys.argv[2]), flush=True)
    else:
        for v, c in PAIRS:
            r = subprocess.run([sys.executable, __file__, v, c],
                               capture_output=True, text=True, timeout=300)
            print(r.stdout.strip() or r.stderr.strip()[-150:], flush=True)
