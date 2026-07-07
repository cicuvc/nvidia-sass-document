#!/usr/bin/env python3
"""Decoder + synthetic round-trip verifier for GATHER (sm_90a).

GATHER (opcode 0x241, int_pipe, INST_TYPE_COUPLED_MATH) is a register-level
sub-element gather — the read-side sibling of SCATTER (0x218). It collects
sub-byte data elements from source registers into Rd, driven by a metadata index
(mdidx) with configurable data/index sizes and a group count. Fixed-latency.
Part of the 2:4 structured-sparsity metadata + low-precision packing cluster
(GENMETADATA/SPMETADATA are the neighbors in ref_memo).

FORMAT: GATHER.<datasize>.<idxsize>.<num> Rd, Ra, Rb, Rc, mdidx, dstbyte, srchalf

No hardware encodings observed; validated by encoder<->decoder round-trip.
"""

DATASIZE = {0: "16", 1: "8", 2: "4"}
IDXSIZE = {0: "U2", 1: "U4", 2: "U8"}
NUM = {0: "1G", 1: "2G", 2: "4G"}

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def reg(n):
    return "RZ" if n == 255 else f"R{n}"

def pred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("PT" if p == 7 else f"P{p}")

def encode(datasize, idxsize, num, Rd, Ra, Rb, Rc, mdidx, dstbyte, srchalf, Pg=7, Pg_not=0):
    v = 0
    v |= (0x241 & 0xfff)          # opcode [11:0]; bit[91]=0
    v |= (mdidx & 0xf) << 78
    v |= (idxsize & 3) << 75
    # size[73]=*0, e[72]=0 pinned
    v |= (Rc & 0xff) << 64
    v |= (datasize & 3) << 61
    v |= (dstbyte & 3) << 57
    v |= (srchalf & 1) << 56
    v |= (num & 3) << 53
    v |= (Rb & 0xff) << 32
    v |= (Ra & 0xff) << 24
    v |= (Rd & 0xff) << 16
    v |= (Pg_not & 1) << 15
    v |= (Pg & 7) << 12
    return v & ((1 << 64) - 1), v >> 64

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode == 0x241, f"opcode {opcode:#x}"
    mdidx = bits(v, 81, 78)
    idxsize = bits(v, 76, 75)
    Rc = bits(v, 71, 64)
    datasize = bits(v, 62, 61)
    dstbyte = bits(v, 58, 57)
    srchalf = bits(v, 56, 56)
    num = bits(v, 54, 53)
    Rb = bits(v, 39, 32)
    Ra = bits(v, 31, 24)
    Rd = bits(v, 23, 16)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)

    mods = [f".{DATASIZE[datasize]}", f".{IDXSIZE[idxsize]}", f".{NUM[num]}"]
    ops = f"{reg(Rd)}, {reg(Ra)}, {reg(Rb)}, {reg(Rc)}, {mdidx:#x}, {dstbyte:#x}, {srchalf:#x}"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}GATHER{''.join(mods)} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    return ok

# Synthetic round-trip cases (spec field map + CONDITIONS bounds; not from hardware).
CASES = [
    # datasize,idxsize,num, Rd,Ra,Rb,Rc, mdidx,dstbyte,srchalf, asm
    (0, 0, 0, 4, 8, 12, 255, 14, 0, 0, "GATHER.16.U2.1G R4, R8, R12, RZ, 0xe, 0x0, 0x0 ;"),   # 16->1G only, U2/1G mdidx<=14
    (1, 1, 1, 5, 6, 7, 8,   4, 2, 1, "GATHER.8.U4.2G R5, R6, R7, R8, 0x4, 0x2, 0x1 ;"),        # 8-><=2G, U4/2G mdidx<=4
    (2, 2, 1, 2, 3, 4, 5,   0, 3, 0, "GATHER.4.U8.2G R2, R3, R4, R5, 0x0, 0x3, 0x0 ;"),        # U8-><=2G, U8/2G mdidx<=0
]

if __name__ == "__main__":
    allok = True
    for ds, idx, num, Rd, Ra, Rb, Rc, md, db, sh, exp in CASES:
        lo, hi = encode(ds, idx, num, Rd, Ra, Rb, Rc, md, db, sh)
        allok &= decode(lo, hi, exp)
    print("\nALL PASS (synthetic round-trip)" if allok else "\nFAILURES")
