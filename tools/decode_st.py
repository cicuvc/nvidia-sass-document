#!/usr/bin/env python3
"""Decoder/verifier for ST (sm_90a) — generic-address-space store.

ST (opcode 0x1985 memdesc/uniform, 0x385 plain) stores to the *generic* address
space (state space resolved at runtime), unlike STG (global only). mio_pipe,
INST_TYPE_DECOUPLED_RD_SCBD, VQ_AGU. On sm_90 ptxas emits the memdesc form:
ST.E ... desc[URc][Ra.64+off], Rb.

Mirrors LD but: no Pnz field, no SP2, uses TABLES_mem_0, dst_wr_sb pinned 7
(a store owns no write scoreboard), and Rb is the source data (not Rd dest).
"""

SZ = {0: ".U8", 1: ".S8", 2: ".U16", 3: ".S16", 4: "", 5: ".64", 6: ".128"}
COP = {0: ".EF", 1: "", 2: ".EL", 3: ".LU", 4: ".EU", 5: ".NA"}
# TABLES_mem_0 code -> printed qualifier (same scope naming; verified STRONG.SYS=10)
MEM = {0: "", 4: ".CONSTANT", 2: ".CTA", 6: ".STRONG.GPU.PRIVATE",
       8: ".MMIO.GPU", 5: ".STRONG.SM", 7: ".STRONG.GPU", 10: ".STRONG.SYS"}

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
    assert opcode in (0x1985, 0x385), f"opcode {opcode:#x}"
    Rb = bits(v, 39, 32)
    Ra = bits(v, 31, 24)
    Ra_URc = bits(v, 69, 64)
    Ra_off = bits(v, 63, 40)
    sz = bits(v, 75, 73)
    e = bits(v, 72, 72)
    cop = bits(v, 86, 84)
    mem = bits(v, 80, 77)
    memdesc = bits(v, 76, 76)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)

    mods = []
    if e:
        mods.append(".E")
    mods.append(COP[cop])
    mods.append(MEM.get(mem, f".mem{mem}"))
    mods.append(SZ[sz])
    modstr = "".join(m for m in mods if m)
    off = Ra_off - (1 << 24) if Ra_off >= (1 << 23) else Ra_off
    ra = reg(Ra, wide=bool(e))
    if memdesc:
        addr = f"desc[{ureg(Ra_URc)}][{ra}"
    else:
        addr = f"[{ra}"
    if off:
        addr += f"+{off:#x}"
    addr += "]"
    ops = f"{addr}, {reg(Rb)}"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}ST{modstr} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x0000000502007985, 0x001fe2000c101904, "ST.E desc[UR4][R2.64], R5 ;"),
    (0x0000000502007985, 0x001fe2000c101104, "ST.E.U8 desc[UR4][R2.64], R5 ;"),
    (0x0000000502007985, 0x001fe2000c101504, "ST.E.U16 desc[UR4][R2.64], R5 ;"),
    (0x0000000402007985, 0x001fe2000c101b04, "ST.E.64 desc[UR4][R2.64], R4 ;"),
    (0x0000000402007985, 0x001fe2000c101d04, "ST.E.128 desc[UR4][R2.64], R4 ;"),
    (0x0000100502007985, 0x001fe2000c115904, "ST.E.STRONG.SYS desc[UR4][R2.64+0x10], R5 ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
