#!/usr/bin/env python3
"""Decoder/verifier for UBLKCP (sm_90a). Reconstructs disassembly from lo64+hi64."""
import struct

DST = {0: "G", 1: "S"}
MULTICAST = {0: None, 1: "MULTICAST"}
SP2 = {0: None, 1: "LTC64B", 2: "LTC128B", 3: "LTC256B"}
SEQ = {0: None, 1: "SEQUENCED"}
# TABLES_mem_5(sem,sco,0) -> value ; we invert for print of .STRONG.<sco>
SEM = {1: "WEAK", 2: "STRONG"}
SCO = {0: None, 1: "CTA", 2: "SM", 3: "VC", 4: "GPU", 5: "SYS"}
# invert mem_5: (sem,sco,c=0) -> code
MEM5 = {(1,0,0):0,(2,2,0):5,(2,1,0):5,(2,4,0):7,(2,3,0):7,(2,5,0):10,(3,2,0):8,(3,4,0):12}
MEM5_INV = {}
for (sem,sco,c),code in MEM5.items():
    MEM5_INV.setdefault(code, (sem,sco))

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def ureg(n):
    return "URZ" if n == 63 else f"UR{n}"

def upred(p, notbit):
    if p == 7 and not notbit:
        return None
    s = ("!" if notbit else "") + ("UPT" if p == 7 else f"UP{p}")
    return s

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode == 0x13ba, f"opcode {opcode:#x}"
    multicast = bits(v, 75, 75)
    src = bits(v, 74, 74)
    dst = bits(v, 73, 73)
    sp2 = bits(v, 82, 81)
    seq = bits(v, 83, 83)
    mem = bits(v, 80, 77)
    memdesc = bits(v, 76, 76)
    URc = bits(v, 69, 64)
    URb = bits(v, 37, 32)
    URa = bits(v, 29, 24)
    URe = bits(v, 45, 40)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    # control (hi bits)
    src_rel_sb = bits(v, 115, 113)
    dst_wr_sb = bits(v, 112, 110)
    req_bit_set = bits(v, 121, 116)

    mods = [f".{DST[dst]}", f".{DST[src]}"]
    if MULTICAST[multicast]:
        mods.append(".MULTICAST")
    if SP2[sp2]:
        mods.append("." + SP2[sp2])
    if SEQ[seq]:
        mods.append(".SEQ")
    sem, sco = MEM5_INV.get(mem, (1, 0))
    if sem == 2:
        mods.append(".STRONG" + ("." + SCO[sco] if SCO[sco] else ""))
    ops = f"[{ureg(URb)}], [{ureg(URa)}], {ureg(URc)}"
    if memdesc:
        ops += f", desc[{ureg(URe)}]"
    pred = upred(Pg, Pg_not)
    preds = f"@{pred} " if pred else ""
    asm = f"{preds}UBLKCP{''.join(mods)} {ops} ;"
    info = f"  ctrl: rd_sb(src_rel)={src_rel_sb} wr_sb(dst)={dst_wr_sb} req={req_bit_set:#x}"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    print(info)
    return ok

VECTORS = [
    (0x000000060a0073ba, 0x0011d80008000a08, "UBLKCP.S.G.MULTICAST [UR6], [UR10], UR8 ;"),
    (0x00000006040073ba, 0x0003e20008000405, "UBLKCP.G.S [UR6], [UR4], UR5 ;"),
    (0x00000004080073ba, 0x0023d80008000206, "UBLKCP.S.G [UR4], [UR8], UR6 ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
