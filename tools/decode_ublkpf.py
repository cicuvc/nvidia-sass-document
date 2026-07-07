#!/usr/bin/env python3
"""Decoder/verifier for UBLKPF (sm_90a). Non-tensor bulk prefetch global->L2.

Single opcode 0x13bc (cp.async.bulk.prefetch). memdesc bit[76] selects _desc form.
Operands: [URa]=source global addr(64b), URc=size(32b), desc[URe]=cache policy desc.
`.L2` (L2ONLY enum) always printed, no encoding bit.
"""

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def ureg(n):
    return "URZ" if n == 63 else f"UR{n}"

def upred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("UPT" if p == 7 else f"UP{p}")

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode == 0x13bc, f"opcode {opcode:#x}"
    memdesc = bits(v, 76, 76)
    URc = bits(v, 69, 64)
    URa = bits(v, 29, 24)
    URe = bits(v, 45, 40)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    src_rel_sb = bits(v, 115, 113)

    ops = f"[{ureg(URa)}], {ureg(URc)}"
    if memdesc:
        ops += f", desc[{ureg(URe)}]"
    pred = upred(Pg, Pg_not)
    preds = f"@{pred} " if pred else ""
    asm = f"{preds}UBLKPF.L2 {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [rd_sb={src_rel_sb} memdesc={memdesc}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x00000000060073bc, 0x0001e40008000004, "UBLKPF.L2 [UR6], UR4 ;"),
    (0x00000600080073bc, 0x0001e40008001004, "UBLKPF.L2 [UR8], UR4, desc[UR6] ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
