#!/usr/bin/env python3
"""H100: is the FP64 unit per-SMSP or SM-shared?  One DADD warp per subcore
(w0,w1,w2,w3 -> SMSP 0,1,2,3) plus a 4x-same-subcore control."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble  # noqa: E402
from archutil import adapt_source  # noqa: E402

N = 1024
BR = "[7:7:{}:1:0:7]"


def build(op):
    lines = [
        "#fn t(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:2:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,4}:5:1]",
        "    MOV32I R4, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R8, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R9, 0x3f803c00;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:6:0]",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
    ]
    for j in range(N):
        d = 40 + (j % 16) * 2
        inst = OPS[op].replace("%D1%", str(d + 1)).replace("%D%", str(d))
        lines.append(f"    {inst};{BR}")
    lines += [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    STG.E.64 [{R6,R7}], {R30,R31};[0:1:{}:8:0]",
        "    STG.E.64 [{R6,R7}+0x8], {R32,R33};[0:1:{}:8:0]",
        "    EXIT;[7:7:{0}:5:0]",
        "}",
    ]
    return "\n".join(lines)


OPS = {
    "dadd": "DADD {R%D%,R%D1%}, {R4,R5}, {R8,R9}",
    "dfma": "DFMA {R%D%,R%D1%}, {R4,R5}, {R8,R9}, {R10,R11}",
}


def run(op, warps, reps=16):
    mod = CudaModule(assemble(adapt_source(build(op)), check_deps=False))
    out = mod.devmem_alloc(512 * 16)
    nthreads = 32 * (max(warps) + 1)
    mod.launch("t", grid=(1,), block=(nthreads,), args=[out])
    mod.synchronize()
    best = None
    for _ in range(reps):
        mod.launch("t", grid=(1,), block=(nthreads,), args=[out])
        mod.synchronize()
        raw = mod.device_read(out, 512 * 16)
        ws = [struct.unpack_from("<QQ", raw, w * 32 * 16) for w in warps]
        lo = max(w[0] for w in ws)
        hi = min(w[1] for w in ws)
        if best is None or hi - lo > best[0]:
            best = (hi - lo, ws)
    mod.devmem_free(out)
    return best[1]


if __name__ == "__main__":
    for op in OPS:
        for warps, tag in (((0,), "solo"), ((0, 1, 2, 3), "diff-subcore x4"),
                           ((0, 4, 8, 12), "same-subcore x4")):
            ws = run(op, warps)
            rates = "/".join(f"{N / (e - s):.3f}" for s, e in ws)
            print(f"{op:5s} {tag:16s} rates(inst/clk)={rates}", flush=True)
