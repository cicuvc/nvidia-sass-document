#!/usr/bin/env python3
"""Decoder/verifier for UTMASTG (sm_90a). TMA tensor tile store shared->global.

Single opcode 0x13b5. memdesc bit[76] selects the _desc form (desc[URe] at [45:40]).
No multicast/URc (stores don't multicast).
"""

TENSORDIM = {0: "1D", 1: "2D", 2: "3D", 3: "4D", 4: "5D",
             5: "INVALID5", 6: "INVALID6", 7: "INVALID7"}

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
    assert opcode == 0x13b5, f"opcode {opcode:#x}"
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
    ops = f"[{ureg(URb)}], [{ureg(URa)}]"
    if memdesc:
        ops += f", desc[{ureg(URe)}]"
    pred = upred(Pg, Pg_not)
    preds = f"@{pred} " if pred else ""
    asm = f"{preds}UTMASTG{''.join(mods)} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [rd_sb={src_rel_sb}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x00000004060073b5, 0x0003e20008000000, "UTMASTG.1D [UR4], [UR6] ;"),
    (0x00000004080073b5, 0x0003e20008008000, "UTMASTG.2D [UR4], [UR8] ;"),
    (0x000000040a0073b5, 0x0003e20008010000, "UTMASTG.3D [UR4], [UR10] ;"),
    (0x000000080e0073b5, 0x0003e20008018000, "UTMASTG.4D [UR8], [UR14] ;"),
    (0x000000080e0073b5, 0x0003e20008020000, "UTMASTG.5D [UR8], [UR14] ;"),
    (0x000000040a0073b5, 0x0003e20008050000, "UTMASTG.3D.IM2COL [UR4], [UR10] ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
