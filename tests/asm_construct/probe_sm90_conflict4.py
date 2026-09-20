#!/usr/bin/env python3
"""H100: 4-warp same-subcore aggregate capacity per pipe (w0/w4/w8/w12)."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble  # noqa: E402
from archutil import adapt_source  # noqa: E402

OPS = {
    "ffma": "FFMA R{d}, R4, R9, R8",
    "iadd3": "IADD3 R{d}, R4, R9, R8",
    "imad": "IMAD R{d}, R4, R9, R8",
    "hfma2": "HFMA2 R{d}, R4, R9, R8",
    "dadd": "DADD {{R{d},R{d}1}}, {{R4,R5}}, {{R8,R9}}",
}
SOLO = {"ffma": 1.008, "iadd3": 2.008, "imad": 2.007, "hfma2": 2.007, "dadd": 2.007}
N = 1024
BR = "[7:7:{}:1:0:7]"


def build(op, mix=None):
    # mix: optional second op; w0/w4 = op, w8/w12 = mix
    tmpl = OPS[op]
    stride = 2 if "{" in tmpl else 1
    body = []
    for j in range(N):
        d = 40 + (j % 16) * stride
        body.append(f"    {tmpl.replace('{d}1', str(d+1)).format(d=d)};{BR}")
    lines = [
        "#fn t(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:2:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{4}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1}:5:1]",
        "    MOV32I R4, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R8, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R9, 0x3f803c00;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:6:0]",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
    ] + body + [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    STG.E.64 [{R6,R7}], {R30,R31};[0:1:{}:8:0]",
        "    STG.E.64 [{R6,R7}+0x8], {R32,R33};[0:1:{}:8:0]",
        "    EXIT;[7:7:{0}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(op, reps=16):
    mod = CudaModule(assemble(adapt_source(build(op)), check_deps=False))
    out = mod.devmem_alloc(512 * 16)
    mod.launch("t", grid=(1,), block=(512,), args=[out])
    mod.synchronize()
    best = None
    for _ in range(reps):
        mod.launch("t", grid=(1,), block=(512,), args=[out])
        mod.synchronize()
        raw = mod.device_read(out, 512 * 16)
        ws = [struct.unpack_from("<QQ", raw, w * 32 * 16) for w in (0, 4, 8, 12)]
        lo = max(w[0] for w in ws)
        hi = min(w[1] for w in ws)
        ov = hi - lo
        if best is None or ov > best[0]:
            best = (ov, ws)
    mod.devmem_free(out)
    ov, ws = best
    rates = [N / (e - s) for s, e in ws]
    agg = sum(rates)
    return (f"{op:6s} x4 same-subcore: overlap={ov:6d} "
            f"rates={'/'.join(f'{r:.3f}' for r in rates)} agg={agg:.3f} inst/clk "
            f"(solo cap {4 / SOLO[op]:.2f})")


if __name__ == "__main__":
    for op in OPS:
        print(run(op), flush=True)
