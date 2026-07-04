#!/usr/bin/env python3
"""FSETP decoder — FP32 comparison result to predicates."""

from typing import Optional

FCMP_NAMES = {0:"F",1:"LT",2:"EQ",3:"LE",4:"GT",5:"NE",6:"GE",7:"NUM",
              8:"NAN",9:"LTU",10:"EQU",11:"LEU",12:"GTU",13:"NEU",14:"GEU",15:"T"}
BOP_NAMES = {0:"AND",1:"OR",2:"XOR"}

def extract(lo64, hi64, bits):
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val
def get_opcode(lo64, hi64):
    return extract(lo64, hi64, [91,11,10,9,8,7,6,5,4,3,2,1,0])
def pred_s(p, n):
    if p == 7: return f"{'!' if n else ''}PT"
    return f"{'!' if n else ''}P{p}"

def decode_fsetp(lo64, hi64):
    opc = get_opcode(lo64, hi64)
    if opc != 0x20b: return None
    pg = extract(lo64, hi64, [14,13,12]); pg_not = extract(lo64, hi64, [15])
    pu = extract(lo64, hi64, [83,82,81]); pv = extract(lo64, hi64, [86,85,84])
    pp = extract(lo64, hi64, [89,88,87]); pp_not = extract(lo64, hi64, [90])
    fcomp = extract(lo64, hi64, [79,78,77,76]); bop = extract(lo64, hi64, [75,74])
    ftz = extract(lo64, hi64, [80])
    ra = extract(lo64, hi64, [31,30,29,28,27,26,25,24])
    rb = extract(lo64, hi64, [39,38,37,36,35,34,33,32])

    parts = []
    if pg != 7: parts.append(f"@{'!' if pg_not else ''}P{pg}")

    suff = []
    suff.append(FCMP_NAMES.get(fcomp, f"??{fcomp}"))
    if ftz: suff.append("FTZ")
    if bop in BOP_NAMES: suff.append(BOP_NAMES[bop])

    pp_s = pred_s(pp, pp_not)
    ra_s = f"RZ" if ra==0xff else f"R{ra}"
    rb_s = f"RZ" if rb==0xff else f"R{rb}"
    pu_s = pred_s(pu, 0)
    pv_s = pred_s(pv, 0)

    parts.append(f"FSETP.{'.'.join(suff)} {pu_s}, {pv_s}, {ra_s}, {rb_s}, {pp_s};")
    return " ".join(parts)

TESTS = [
    ("0x000000050400720b", "0x001fc80003f11000", "FSETP.LT.FTZ.AND"),  # from FSET test
    ("0x000000050400720b", "0x001fc80000701000", "FSETP.LT.AND"),
    ("0x000000050400720b", "0x001fc80003f04000", "FSETP.GT.AND"),
    ("0x000000050400720b", "0x001fc80003f0d000", "FSETP.NEU.AND"),
    ("0x000000050400720b", "0x001fc80003f0e000", "FSETP.GEU.AND"),
]

ok = 0
for lo_s, hi_s, exp in TESTS:
    r = decode_fsetp(int(lo_s,16), int(hi_s,16))
    m = "(match)" if r and exp in r else "(MISMATCH)"
    if r and exp in r: ok += 1
    print(f"  expected: {exp}")
    print(f"  decoded:  {r} {m}\n")
print(f"{ok}/{len(TESTS)} matches")
