#!/usr/bin/env python3
"""Decoder/verifier for LDGSTS (sm_90a). cp.async: async copy global->shared.

Opcodes: 0x1fae (RR / desc forms, global addr in reg pair), 0x1dae (RUR form).
memdesc bit[76]=1 -> desc[URc][Ra.64] descriptor addressing (ptxas default sm_90).
Fields (RR/desc form):
  Rd  [23:16]  shared destination register (the 'Rb' slot -> Rd field)
  Ra  [31:24]  global address register (64-bit pair when input_reg_sz)
  Ra_URc [69:64] descriptor UR (desc form)
  sz  [75:73]  SZ_32_64_128 (32=4 default, 64=5, 128=6)
  sp2 [72:71]  SP2 (nosp2/LTC64B/128B/256B)
  loc [81]     LOC (BYPASS=0, ACCESS=1 default)
  fc  [82]     FILLCTRL (nofillctrl=0, ZFILL=1)
  cop [86:84]  COP (EF/EN/EL/LU/EU/NA)
  Pnz [89:87], Pnz_not [90]
"""

SZ = {4: "32", 5: "64", 6: "128"}
SP2 = {0: "", 1: ".LTC64B", 2: ".LTC128B", 3: ".LTC256B"}
LOC = {0: ".BYPASS", 1: ""}  # ACCESS is default (unprinted)
FC = {0: "", 1: ".ZFILL"}

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def reg(n):
    return "RZ" if n == 255 else f"R{n}"

def ureg(n):
    return "URZ" if n == 63 else f"UR{n}"

def pred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("PT" if p == 7 else f"P{p}")

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode in (0x1fae, 0x1dae), f"opcode {opcode:#x}"
    Rd = bits(v, 23, 16)
    Ra = bits(v, 31, 24)
    Ra_URc = bits(v, 69, 64)
    sz = bits(v, 75, 73)
    sp2 = bits(v, 72, 71)
    loc = bits(v, 81, 81)
    fc = bits(v, 82, 82)
    cop = bits(v, 86, 84)
    memdesc = bits(v, 76, 76)
    Pnz = bits(v, 89, 87)
    Pnz_not = bits(v, 90, 90)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    dst_wr_sb = bits(v, 112, 110)

    # modifier print order observed: .E .<BYPASS> .<LTCxxxB> .<sz> .<ZFILL>
    mods = [".E"]
    if LOC[loc]:
        mods.append(LOC[loc])
    if SP2[sp2]:
        mods.append(SP2[sp2])
    if SZ[sz] != "32":
        mods.append("." + SZ[sz])
    if FC[fc]:
        mods.append(FC[fc])
    # address operand (desc form)
    if memdesc:
        addr = f"desc[{ureg(Ra_URc)}][{reg(Ra)}.64]"
    else:
        addr = f"[{reg(Ra)}.64]"
    ops = f"[{reg(Rd)}], {addr}"
    pnz = pred(Pnz, Pnz_not)
    if pnz:
        ops += f", {pnz}"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}LDGSTS{''.join(mods)} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [cop={cop} wr_sb={dst_wr_sb}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x0000000002077fae, 0x000fe2000b921844, "LDGSTS.E [R7], desc[UR4][R2.64] ;"),
    (0x0000000002077fae, 0x000fe2000b921a44, "LDGSTS.E.64 [R7], desc[UR4][R2.64] ;"),
    (0x0000000002077fae, 0x000fe2000b921c44, "LDGSTS.E.128 [R7], desc[UR4][R2.64] ;"),
    (0x0000000002077fae, 0x000fe2000b901c44, "LDGSTS.E.BYPASS.128 [R7], desc[UR4][R2.64] ;"),
    (0x0000000004077fae, 0x000fe80008161c44, "LDGSTS.E.128.ZFILL [R7], desc[UR4][R4.64], P0 ;"),
    (0x0000000002077fae, 0x000fe2000b921d44, "LDGSTS.E.LTC128B.128 [R7], desc[UR4][R2.64] ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
