#!/usr/bin/env python3
"""Decoder/verifier for FENCE (sm_90a) — async-proxy view fence.

Opcode 0x3c6, mio_pipe, INST_TYPE_DECOUPLED_WR_SCBD, VQ_FENCE_S / VQ_FENCE_G.
No operands. Always FENCE.VIEW.ASYNC; memType [72] selects .S (shared, 0) vs
.G (global, 1). Distinct from MEMBAR — this is the proxy view-fence that orders
the async (TMA/cp.async) proxy against the generic proxy.
"""

MEMTYPE = {0: "S", 1: "G"}

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def pred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("PT" if p == 7 else f"P{p}")

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode == 0x3c6, f"opcode {opcode:#x}"
    memType = bits(v, 72, 72)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)

    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}FENCE.VIEW.ASYNC.{MEMTYPE[memType]} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x00000000000073c6, 0x000fe20000000000, "FENCE.VIEW.ASYNC.S ;"),
    (0x00000000000073c6, 0x000fe20000000100, "FENCE.VIEW.ASYNC.G ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
