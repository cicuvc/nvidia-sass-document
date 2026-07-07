#!/usr/bin/env python3
"""Decoder for the sm_90 YIELD instruction (warp-scheduler yield hint, opcode 0x946).

YIELD asks the warp scheduler to switch away from the issuing warp/group (a
fairness / forward-progress hint used in poll / spin-wait loops). No target, no
register operands.

  @Pg YIELD [Pp]

Fields (128-bit):
  opcode = {bit[91], bits[11:0]} = 0x946
  Pg=[14:12] Pg_not=[15]      guard predicate
  Pp/Pnz=[89:87] Pp_not=[90]  predicate operand (printed if != PT)

Usage: python3 decode_yield.py            (self-test)
       python3 decode_yield.py <sass.txt> (validate every YIELD in a dump)
"""
import re
import sys


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode != 0x946:
        return "?opcode 0x%x" % opcode
    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    pp_s = "" if (pp == 7 and pp_not == 0) else " %s" % pred(pp, pp_not)
    return "%sYIELD%s" % (guard, pp_s)


# (lo64, hi64, expected) — libcusparse + cubin-patch ground truth
VECTORS = [
    (0x0000000000007946, 0x000fea0003800000, "YIELD"),            # libcusparse
    (0x0000000000000946, 0x000fea0003800000, "@P0 YIELD"),        # patch (Pg=P0)
    (0x0000000000007946, 0x000fea0001800000, "YIELD P3"),         # patch (Pp=P3)
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        ok += got == exp
        print("%s %-12s (exp %s)" % ("OK " if got == exp else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bYIELD\b", m.group(2)):
            continue
        text, lo = m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16))
        total += 1
        ok += got == text
        if got != text:
            print("XX got %-12s exp %-12s [%016x]" % (got, text, lo))
    print("%s: %d/%d YIELD matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
