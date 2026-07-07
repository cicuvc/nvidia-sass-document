#!/usr/bin/env python3
"""Decoder/verifier for UBLKRED (sm_90a). Non-tensor bulk reduction cp.reduce.async.bulk.

Single opcode 0x13bb. Fields:
  op   [89:87]  RedOp
  sz   [84:81]  SIZE_ublkred (type)
  mem  [80:77]  sem/sco via TABLES_mem_5
  memdesc [76]
  src  [74]  (sh) SONLY_ublkred (always S=1)
  dst  [73]  (sz1) DST (G=0/S=1)
Operands: [URb]=dest, [URa]=source(Sa,shared), URc(=size or mbarrier).
"""

DST = {0: "G", 1: "S"}
SRC = {1: "S"}
REDOP = {0: "ADD", 1: "MIN", 2: "MAX", 3: "INC", 4: "DEC", 5: "AND", 6: "OR", 7: "XOR"}
SIZE = {0: "U32", 1: "S32", 2: "U64", 3: "S64", 4: "F16.RN", 5: "F32.RN",
        6: "F32.FTZ.RN", 7: "F64.RN", 8: "BF16.RN"}

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
    assert opcode == 0x13bb, f"opcode {opcode:#x}"
    op = bits(v, 89, 87)
    sz = bits(v, 84, 81)
    src = bits(v, 74, 74)
    dst = bits(v, 73, 73)
    memdesc = bits(v, 76, 76)
    URc = bits(v, 69, 64)
    URb = bits(v, 37, 32)
    URa = bits(v, 29, 24)
    URe = bits(v, 45, 40)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    src_rel_sb = bits(v, 115, 113)

    mods = [f".{DST[dst]}", f".{SRC[src]}", f".{REDOP[op]}"]
    if sz != 0:  # U32 is default, not printed
        mods.append("." + SIZE[sz])
    ops = f"[{ureg(URb)}], [{ureg(URa)}], {ureg(URc)}"
    if memdesc:
        ops += f", desc[{ureg(URe)}]"
    pred = upred(Pg, Pg_not)
    preds = f"@{pred} " if pred else ""
    asm = f"{preds}UBLKRED{''.join(mods)} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [rd_sb={src_rel_sb}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x00000008040073bb, 0x0023d80008000406, "UBLKRED.G.S.ADD [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80008800406, "UBLKRED.G.S.MIN [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80009000406, "UBLKRED.G.S.MAX [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80009800406, "UBLKRED.G.S.INC [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d8000a000406, "UBLKRED.G.S.DEC [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d8000a800406, "UBLKRED.G.S.AND [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d8000b000406, "UBLKRED.G.S.OR [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d8000b800406, "UBLKRED.G.S.XOR [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80008020406, "UBLKRED.G.S.ADD.S32 [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80008040406, "UBLKRED.G.S.ADD.U64 [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80008860406, "UBLKRED.G.S.MIN.S64 [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d800080a0406, "UBLKRED.G.S.ADD.F32.RN [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d800080e0406, "UBLKRED.G.S.ADD.F64.RN [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80008080406, "UBLKRED.G.S.ADD.F16.RN [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80008100406, "UBLKRED.G.S.ADD.BF16.RN [UR8], [UR4], UR6 ;"),
    (0x00000008040073bb, 0x0023d80008880406, "UBLKRED.G.S.MIN.F16.RN [UR8], [UR4], UR6 ;"),
    (0x0000000a040073bb, 0x0011d80008000608, "UBLKRED.S.S.ADD [UR10], [UR4], UR8 ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
