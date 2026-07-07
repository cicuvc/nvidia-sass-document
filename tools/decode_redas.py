#!/usr/bin/env python3
"""Decoder/verifier for REDAS (sm_90a). Reduce-async to distributed shared memory.

REDAS = PTX red.async.shared::cluster (atomic reduce into a remote CTA's shared
memory + signal an mbarrier tx-count). Single opcode 0x1dbe, sibling of STAS.
Fields:
  op   [90:87]  REDAS_OP (ADD/MIN/MAX/INC/DEC/AND/OR/XOR)
  sz   [75:73]  REDAS_SZ (U32=0 default, S32=1, U64=2)
  mem  [80:77]  sem/sco/private via TABLES_mem_4
  e    [72]     1 = Ra is a 64-bit register pair ([Ra.64])
  Ra_URc [69:64], Ra_offset [63:40], Rb [39:32], Ra [31:24]
Note SASS prints U64 as ".64" and S32 as ".S32"; U32 is unprinted.
"""

REDOP = {0: "ADD", 1: "MIN", 2: "MAX", 3: "INC", 4: "DEC", 5: "AND", 6: "OR", 7: "XOR"}
SZ = {0: "", 1: ".S32", 2: ".64"}

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def reg(n, wide=False):
    base = "RZ" if n == 255 else f"R{n}"
    return base + (".64" if wide and n != 255 else "")

def ureg(n):
    return "URZ" if n == 63 else f"UR{n}"

def pred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("PT" if p == 7 else f"P{p}")

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode == 0x1dbe, f"opcode {opcode:#x}"
    op = bits(v, 90, 87)
    sz = bits(v, 75, 73)
    mem = bits(v, 80, 77)
    e = bits(v, 72, 72)
    Ra = bits(v, 31, 24)
    Rb = bits(v, 39, 32)
    Ra_URc = bits(v, 69, 64)
    Ra_off = bits(v, 63, 40)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    src_rel_sb = bits(v, 115, 113)

    mods = [f".{REDOP[op]}", SZ[sz]]
    addr = f"[{reg(Ra, wide=bool(e))}"
    if Ra_URc != 63:
        addr += f"+{ureg(Ra_URc)}"
    if Ra_off:
        addr += f"+{Ra_off:#x}"
    addr += "]"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}REDAS{''.join(mods)} {addr}, {reg(Rb)} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [mem={mem} rd_sb={src_rel_sb}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x0000000002007dbe, 0x001fe2000800013f, "REDAS.ADD [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000880013f, "REDAS.MIN [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000900013f, "REDAS.MAX [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000880033f, "REDAS.MIN.S32 [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000900033f, "REDAS.MAX.S32 [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000980013f, "REDAS.INC [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000a00013f, "REDAS.DEC [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000a80013f, "REDAS.AND [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000b00013f, "REDAS.OR [R2.64], R0 ;"),
    (0x0000000002007dbe, 0x001fe2000b80013f, "REDAS.XOR [R2.64], R0 ;"),
    (0x0000000204007dbe, 0x001fe2000800053f, "REDAS.ADD.64 [R4.64], R2 ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
