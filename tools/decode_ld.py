#!/usr/bin/env python3
"""Decoder/verifier for LD (sm_90a) — generic-address-space load.

LD (opcode 0x1980 memdesc/uniform, 0x980 plain) loads from the *generic* address
space (state space resolved at runtime: global/shared/local), unlike LDG (global
only). mio_pipe, INST_TYPE_DECOUPLED_RD_WR_SCBD, VQ_AGU_UNORDERED_WR.
On sm_90 ptxas emits the memdesc form: LD.E ... desc[URb][Ra.64+off].

Fields (memdesc form, mirrors LDG):
  Rd [23:16], Ra [31:24], Ra_URb [37:32], Ra_offset [63:40]
  sz [75:73] SZ_U8..128, e [72] E, sp2 [69:68], cop [86:84] COP
  mem [80:77] via TABLES_mem_1(sem,sco,private), memdesc [76], Pnz [67:64]
"""

SZ = {0: ".U8", 1: ".S8", 2: ".U16", 3: ".S16", 4: "", 5: ".64", 6: ".128"}
COP = {0: ".EF", 1: "", 2: ".EL", 3: ".LU", 4: ".EU", 5: ".NA"}
SP2 = {0: "", 1: ".LTC64B", 2: ".LTC128B", 3: ".LTC256B"}
# TABLES_mem_1 code -> printed qualifier (from LDG note + observed)
MEM = {0: "", 4: ".CONSTANT", 2: ".CTA", 6: ".STRONG.GPU.PRIVATE",
       8: ".MMIO.GPU", 5: ".STRONG.SM", 7: ".STRONG.GPU", 10: ".STRONG.SYS"}
PNZ = {0: None, 7: "P0", 6: "P1", 5: "P2", 4: "P3", 3: "P4", 2: "P5", 1: "P6",
       15: "!P0", 14: "!P1", 13: "!P2", 12: "!P3", 11: "!P4", 10: "!P5", 9: "!P6", 8: None}

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
    assert opcode in (0x1980, 0x980), f"opcode {opcode:#x}"
    Rd = bits(v, 23, 16)
    Ra = bits(v, 31, 24)
    Ra_URb = bits(v, 37, 32)
    Ra_off = bits(v, 63, 40)
    sz = bits(v, 75, 73)
    e = bits(v, 72, 72)
    sp2 = bits(v, 69, 68)
    cop = bits(v, 86, 84)
    mem = bits(v, 80, 77)
    memdesc = bits(v, 76, 76)
    pnz = bits(v, 67, 64)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)

    mods = []
    if e:
        mods.append(".E")
    mods.append(COP[cop])
    mods.append(SP2[sp2])
    mods.append(MEM.get(mem, f".mem{mem}"))
    mods.append(SZ[sz])
    modstr = "".join(m for m in mods if m)
    # sign-extend 24-bit offset
    off = Ra_off - (1 << 24) if Ra_off >= (1 << 23) else Ra_off
    ra = reg(Ra, wide=bool(e))
    if memdesc:
        addr = f"desc[{ureg(Ra_URb)}][{ra}"
    else:
        addr = f"[{ra}"
    if off:
        addr += f"+{off:#x}"
    addr += "]"
    ops = f"{reg(Rd)}, {addr}"
    pn = PNZ.get(pnz)
    if pn:
        ops += f", {pn}"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}LD{modstr} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x0000000402037980, 0x001eaa000c101900, "LD.E R3, desc[UR4][R2.64] ;"),
    (0x0000000402037980, 0x001eaa000c101100, "LD.E.U8 R3, desc[UR4][R2.64] ;"),
    (0x0000000402037980, 0x001eaa000c101500, "LD.E.U16 R3, desc[UR4][R2.64] ;"),
    (0x0000000402027980, 0x001eaa000c101b00, "LD.E.64 R2, desc[UR4][R2.64] ;"),
    (0x0000000402087980, 0x001eaa000c101d00, "LD.E.128 R8, desc[UR4][R2.64] ;"),
    (0x0000100404057980, 0x001eaa000c115900, "LD.E.STRONG.SYS R5, desc[UR4][R4.64+0x10] ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
