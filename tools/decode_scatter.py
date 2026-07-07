#!/usr/bin/env python3
"""Decoder + synthetic round-trip verifier for SCATTER (sm_90a).

SCATTER (opcode 0x218, int_pipe, INST_TYPE_COUPLED_MATH) is a register-level
byte/nibble permute — NOT a memory store. It writes selected sub-elements of the
source registers into destination byte lanes under a lane mask, driven by an
index. Sibling of GATHER (0x241). Fixed-latency coupled-math op.

FORMAT: SCATTER.<mode>.<elsize>.<idxsize>[.SP] Rd, Ra, Rb, Rc, vecidx, mask

No hardware encodings were observed (stock ptxas/cublas do not emit it), so this
decoder is validated by an ENCODER round-trip against the spec field map.
"""

MODE = {0: "THREAD", 1: "QUAD", 2: "PAIR"}
ELSIZE = {0: "U8", 1: "U16"}
IDXSIZE = {0: "U4_H0", 1: "U4_H1", 2: "U8", 3: "U4_B0", 4: "U4_B1",
           5: "U4_B2", 6: "U4_B3", 7: "U8_H0", 8: "U8_H1"}
SPARSE = {0: "", 1: "SP"}

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def reg(n):
    return "RZ" if n == 255 else f"R{n}"

def pred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("PT" if p == 7 else f"P{p}")

def encode(mode, elsize, idxsize, sparse, Rd, Ra, Rb, Rc, vecidx, mask, Pg=7, Pg_not=0):
    v = 0
    v |= (0x218 & 0xfff)          # opcode [11:0]; bit[91]=0 for 0x218
    v |= (sparse & 1) << 90
    v |= (vecidx & 0x7f) << 83
    v |= (mode & 3) << 81
    v |= (mask & 0xf) << 77
    v |= (idxsize & 0xf) << 73
    v |= (elsize & 1) << 72
    v |= (Rc & 0xff) << 64
    v |= (Rb & 0xff) << 32
    v |= (Ra & 0xff) << 24
    v |= (Rd & 0xff) << 16
    v |= (Pg_not & 1) << 15
    v |= (Pg & 7) << 12
    return v & ((1 << 64) - 1), v >> 64

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode == 0x218, f"opcode {opcode:#x}"
    sparse = bits(v, 90, 90)
    vecidx = bits(v, 89, 83)
    mode = bits(v, 82, 81)
    mask = bits(v, 80, 77)
    idxsize = bits(v, 76, 73)
    elsize = bits(v, 72, 72)
    Rc = bits(v, 71, 64)
    Rb = bits(v, 39, 32)
    Ra = bits(v, 31, 24)
    Rd = bits(v, 23, 16)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)

    mods = [f".{MODE[mode]}", f".{ELSIZE[elsize]}", f".{IDXSIZE[idxsize]}"]
    if SPARSE[sparse]:
        mods.append(".SP")
    ops = f"{reg(Rd)}, {reg(Ra)}, {reg(Rb)}, {reg(Rc)}, {vecidx:#x}, {mask:#x}"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}SCATTER{''.join(mods)} {ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    return ok

# Synthetic round-trip cases (spec field map; not from hardware).
CASES = [
    # mode,elsize,idxsize,sparse, Rd,Ra,Rb,Rc, vecidx,mask, asm
    (0, 0, 0, 0, 4, 8, 12, 255, 0, 0xf, "SCATTER.THREAD.U8.U4_H0 R4, R8, R12, RZ, 0x0, 0xf ;"),
    (1, 1, 2, 0, 5, 6, 7, 8,   3, 0x3, "SCATTER.QUAD.U16.U8 R5, R6, R7, R8, 0x3, 0x3 ;"),
    (2, 0, 7, 1, 2, 3, 4, 5,   1, 0x5, "SCATTER.PAIR.U8.U8_H0.SP R2, R3, R4, R5, 0x1, 0x5 ;"),
]

if __name__ == "__main__":
    allok = True
    for mode, el, idx, sp, Rd, Ra, Rb, Rc, vi, mask, exp in CASES:
        lo, hi = encode(mode, el, idx, sp, Rd, Ra, Rb, Rc, vi, mask)
        allok &= decode(lo, hi, exp)
    print("\nALL PASS (synthetic round-trip)" if allok else "\nFAILURES")
