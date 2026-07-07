#!/usr/bin/env python3
"""DSETP decoder — FP64 compare-set-predicate, 10 variants (RRU observed)."""
from typing import Optional

FCMP = {0:"MIN",1:"LT",2:"EQ",3:"LE",4:"GT",5:"NE",6:"GE",7:"NUM",8:"NAN",
        9:"LTU",10:"EQU",11:"LEU",12:"GTU",13:"NEU",14:"GEU",15:"MAX"}
BOP = {0:"AND",1:"OR",2:"XOR"}

def extract(lo, hi, bits):
    val = 0
    for bit in bits:
        bv = ((hi >> (bit - 64)) if bit >= 64 else (lo >> bit)) & 1
        val = (val << 1) | bv
    return val

def get_opcode(lo, hi):
    return extract(lo, hi, [91] + list(range(11, -1, -1)))

OPCODES = {0x22a, 0x42a, 0x62a, 0x162a, 0x1e2a}

def decode_dsetp(lo, hi):
    opc = get_opcode(lo, hi)
    if opc not in OPCODES: return None

    pg = extract(lo, hi, [14,13,12]); pg_not = extract(lo, hi, [15])
    test = extract(lo, hi, [79,78,77,76])
    bop = extract(lo, hi, [75,74])
    pu = extract(lo, hi, [83,82,81])
    pv = extract(lo, hi, [86,85,84])
    pp = extract(lo, hi, [89,88,87]); pp_not = extract(lo, hi, [90])
    ra = extract(lo, hi, [31,30,29,28,27,26,25,24])

    is_rru = (extract(lo, hi, [37,36,35,34,33,32]) != 0)
    if is_rru:
        urb = extract(lo, hi, [37,36,35,34,33,32])
        rc_s = f"UR{urb}"
    else:
        rc = extract(lo, hi, [39,38,37,36,35,34,33,32])
        rc_s = f"R{rc}" if rc != 0xff else "RZ"

    parts = []; mnem = "DSETP"
    if pg != 7: parts.append(f"@{'!' if pg_not else ''}P{pg}")
    if test != 0: mnem += f".{FCMP.get(test, str(test))}"
    if bop != 0: mnem += f".{BOP.get(bop, str(bop))}"
    parts.append(mnem)
    parts.append(f"P{pu},"); parts.append(f"P{pv},")
    parts.append(f"R{ra},"); parts.append(f"{rc_s},")
    parts.append(f"{'!' if pp_not else ''}P{pp}")
    return " ".join(parts)

if __name__ == "__main__":
    tests = [
        (0x0000000406007e2a, 0x000fe60008000204, "DSETP P0, P0, R6, UR4, P0"),
    ]
    ok = 0
    for lo, hi, exp in tests:
        r = decode_dsetp(lo, hi); s = "OK" if r == exp else "MISMATCH"
        if r == exp: ok += 1
        print(f"{r:55s} [{s}]" + (f"  expected: {exp}" if s != "OK" else ""))
    print(f"\n{ok}/{len(tests)} PASS")
