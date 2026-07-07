#!/usr/bin/env python3
"""Decoder/verifier for MEMBAR (sm_90a) — memory barrier / fence.

Opcode 0x992, mio_pipe, INST_TYPE_DECOUPLED_RD_SCBD, VQ_UNORDERED. No operands.
Fields: sem [80:79] (MEMBAR_SEM), sco [78:76] (scope).
"""

SEM = {0: "SC", 1: "ALL", 2: "", 3: "MMIO"}  # 2=nomembar_sem (unprinted)
SCO = {0: "CTA", 1: "SM", 2: "GPU", 3: "SYS", 5: "VC", 6: "CTA.PARTIAL"}

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def pred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("PT" if p == 7 else f"P{p}")

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode == 0x992, f"opcode {opcode:#x}"
    sem = bits(v, 80, 79)
    sco = bits(v, 78, 76)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)

    mods = []
    if SEM[sem]:
        mods.append("." + SEM[sem])
    mods.append("." + SCO.get(sco, f"sco{sco}"))
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}MEMBAR{''.join(mods)} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x0000000000007992, 0x000fec0000000000, "MEMBAR.SC.CTA ;"),
    (0x0000000000007992, 0x0001ec0000008000, "MEMBAR.ALL.CTA ;"),
    (0x0000000000007992, 0x000fec000000a000, "MEMBAR.ALL.GPU ;"),
    (0x0000000000007992, 0x000fec000000b000, "MEMBAR.ALL.SYS ;"),
    (0x0000000000007992, 0x000fec0000002000, "MEMBAR.SC.GPU ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
