#!/usr/bin/env python3
"""Decoder/verifier for UTMAPF (sm_90a). TMA tensor prefetch global->L2.

Two opcodes (mirror UTMALDG):
  0x15b8 = utmapf__UUU        (plain .tile, no URc)
  0x13b8 = utmapf_URc__UUU    (URc present; im2col)
`.L2` (L2ONLY enum, only value) is always printed but has no encoding bit.
memdesc bit[76] selects the _desc form.
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
    assert opcode in (0x13b8, 0x15b8), f"opcode {opcode:#x}"
    has_urc = (opcode == 0x13b8)
    dim = bits(v, 81, 79)
    im2col = bits(v, 82, 82) if has_urc else 0
    memdesc = bits(v, 76, 76)
    URc = bits(v, 69, 64)
    URb = bits(v, 37, 32)
    URa = bits(v, 29, 24)
    URe = bits(v, 45, 40)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    src_rel_sb = bits(v, 115, 113)

    mods = [".L2", f".{TENSORDIM[dim]}"]
    if im2col:
        mods.append(".IM2COL")
    ops = f"[{ureg(URb)}], [{ureg(URa)}]"
    if has_urc:
        ops += f", {ureg(URc)}"
    if memdesc:
        ops += f", desc[{ureg(URe)}]"
    pred = upred(Pg, Pg_not)
    preds = f"@{pred} " if pred else ""
    asm = f"{preds}UTMAPF{''.join(mods)} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [op={opcode:#x} rd_sb={src_rel_sb}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x00000006040075b8, 0x0001e40008000000, "UTMAPF.L2.1D [UR6], [UR4] ;"),
    (0x00000006040075b8, 0x0001e40008008000, "UTMAPF.L2.2D [UR6], [UR4] ;"),
    (0x00000008040075b8, 0x0001e40008010000, "UTMAPF.L2.3D [UR8], [UR4] ;"),
    (0x00000008040075b8, 0x0001e40008018000, "UTMAPF.L2.4D [UR8], [UR4] ;"),
    (0x00000008040075b8, 0x0001e40008020000, "UTMAPF.L2.5D [UR8], [UR4] ;"),
    (0x00000008060073b8, 0x0001e40008050004, "UTMAPF.L2.3D.IM2COL [UR8], [UR6], UR4 ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
