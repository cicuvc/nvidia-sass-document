#!/usr/bin/env python3
"""Decoder/verifier for UTMAREDG (sm_90a). TMA tensor reduction store shared->global.

Single opcode 0x13b6. Like UTMASTG but adds a RedOp field (Pnz) at [89:87].
memdesc bit[76] selects the _desc form.
"""

TENSORDIM = {0: "1D", 1: "2D", 2: "3D", 3: "4D", 4: "5D",
             5: "INVALID5", 6: "INVALID6", 7: "INVALID7"}
REDOP = {0: "ADD", 1: "MIN", 2: "MAX", 3: "INC", 4: "DEC", 5: "AND", 6: "OR", 7: "XOR"}

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
    assert opcode == 0x13b6, f"opcode {opcode:#x}"
    op = bits(v, 89, 87)
    dim = bits(v, 81, 79)
    im2col = bits(v, 82, 82)
    memdesc = bits(v, 76, 76)
    URb = bits(v, 37, 32)
    URa = bits(v, 29, 24)
    URe = bits(v, 45, 40)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    src_rel_sb = bits(v, 115, 113)

    mods = [f".{TENSORDIM[dim]}"]
    if im2col:
        mods.append(".IM2COL")
    mods.append(f".{REDOP[op]}")
    ops = f"[{ureg(URb)}], [{ureg(URa)}]"
    if memdesc:
        ops += f", desc[{ureg(URe)}]"
    pred = upred(Pg, Pg_not)
    preds = f"@{pred} " if pred else ""
    asm = f"{preds}UTMAREDG{''.join(mods)} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [rd_sb={src_rel_sb}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x00000004060073b6, 0x0023d80008000000, "UTMAREDG.1D.ADD [UR4], [UR6] ;"),
    (0x000000040a0073b6, 0x0003f20008008000, "UTMAREDG.2D.ADD [UR4], [UR10] ;"),
    (0x000000040a0073b6, 0x0003f20008808000, "UTMAREDG.2D.MIN [UR4], [UR10] ;"),
    (0x000000040a0073b6, 0x0003f20009008000, "UTMAREDG.2D.MAX [UR4], [UR10] ;"),
    (0x000000040a0073b6, 0x0003f20009808000, "UTMAREDG.2D.INC [UR4], [UR10] ;"),
    (0x000000040a0073b6, 0x0003f2000a008000, "UTMAREDG.2D.DEC [UR4], [UR10] ;"),
    (0x000000040a0073b6, 0x0003f2000a808000, "UTMAREDG.2D.AND [UR4], [UR10] ;"),
    (0x000000040a0073b6, 0x0003f2000b008000, "UTMAREDG.2D.OR [UR4], [UR10] ;"),
    (0x000000040a0073b6, 0x0003f2000b808000, "UTMAREDG.2D.XOR [UR4], [UR10] ;"),
    (0x000000040a0073b6, 0x0003f20008010000, "UTMAREDG.3D.ADD [UR4], [UR10] ;"),
    (0x000000080e0073b6, 0x0003ee0008020000, "UTMAREDG.5D.ADD [UR8], [UR14] ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
