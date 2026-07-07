#!/usr/bin/env python3
"""Decoder/verifier for UTMALDG (sm_90a). TMA tensor tile load global->shared.

Two opcodes:
  0x15b4 = utmaldg__UUU        (plain .tile, no URc mbarrier operand printed)
  0x13b4 = utmaldg_URc__UUU    (URc present; im2col and/or multicast)
memdesc bit[76] selects the _desc form (extra desc[URe] at [45:40]).
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
    assert opcode in (0x13b4, 0x15b4), f"opcode {opcode:#x}"
    has_urc = (opcode == 0x13b4)
    dim = bits(v, 81, 79)
    im2col = bits(v, 82, 82) if has_urc else 0
    multicast = bits(v, 75, 75) if has_urc else 0
    memdesc = bits(v, 76, 76)
    URc = bits(v, 69, 64)
    URb = bits(v, 37, 32)
    URa = bits(v, 29, 24)
    URe = bits(v, 45, 40)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    src_rel_sb = bits(v, 115, 113)

    mods = [f".{TENSORDIM[dim]}"]
    if im2col:
        mods.append(".IM2COL")
    if multicast:
        mods.append(".MULTICAST")
    ops = f"[{ureg(URb)}], [{ureg(URa)}]"
    if has_urc:
        ops += f", {ureg(URc)}"
    if memdesc:
        ops += f", desc[{ureg(URe)}]"
    pred = upred(Pg, Pg_not)
    preds = f"@{pred} " if pred else ""
    asm = f"{preds}UTMALDG{''.join(mods)} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [op={opcode:#x} rd_sb={src_rel_sb}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x00000008040075b4, 0x0011d80008000000, "UTMALDG.1D [UR8], [UR4] ;"),
    (0x00000008040075b4, 0x0011d80008008000, "UTMALDG.2D [UR8], [UR4] ;"),
    (0x00000008040075b4, 0x0011d80008010000, "UTMALDG.3D [UR8], [UR4] ;"),
    (0x00000008040075b4, 0x0011d80008018000, "UTMALDG.4D [UR8], [UR4] ;"),
    (0x00000008040075b4, 0x0011d80008020000, "UTMALDG.5D [UR8], [UR4] ;"),
    (0x00000008060073b4, 0x0011d80008050004, "UTMALDG.3D.IM2COL [UR8], [UR6], UR4 ;"),
    (0x00000008060073b4, 0x0011d80008008804, "UTMALDG.2D.MULTICAST [UR8], [UR6], UR4 ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
