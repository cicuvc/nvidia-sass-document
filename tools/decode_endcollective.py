#!/usr/bin/env python3
"""Decoder / validator for the sm_90 ENDCOLLECTIVE instruction (opcode 0x91b).

ENDCOLLECTIVE closes the warp collective-region opened by WARPSYNC.COLLECTIVE
(strict 1:1 pairing; the WARPSYNC.COLLECTIVE target points at ENDCOLLECTIVE's
successor). No target, no register operands.

  @Pg ENDCOLLECTIVE [Pp]

Fields (128-bit):
  opcode = {bit[91], bits[11:0]} = 0x91b
  Pg=[14:12] Pg_not=[15]      guard predicate
  Pp/Pnz=[89:87] Pp_not=[90]  predicate operand (printed if != PT)

Unlike the rest of the CBU family, INSTRUCTION_TYPE = INST_TYPE_COUPLED_MATH
(fixed-latency coupled), not DECOUPLED_BRU; opex uses TABLES_opex_1.

Usage: python3 decode_endcollective.py            (self-test)
       python3 decode_endcollective.py <sass.txt>  (validate every ENDCOLLECTIVE)
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
    if opcode != 0x91b:
        return "?opcode 0x%x" % opcode
    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    pp_s = "" if (pp == 7 and pp_not == 0) else " %s" % pred(pp, pp_not)
    return "%sENDCOLLECTIVE%s" % (guard, pp_s)


# (lo64, hi64, expected) — libcusparse + -G build ground truth
VECTORS = [
    (0x000000000000791b, 0x022fe20003800000, "ENDCOLLECTIVE"),   # libcusparse
    (0x000000000000791b, 0x003fde0003800000, "ENDCOLLECTIVE"),   # -G build
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        ok += got == exp
        print("%s %-16s (exp %s)" % ("OK " if got == exp else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bENDCOLLECTIVE\b", m.group(2)):
            continue
        text, lo = m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16))
        total += 1
        ok += got == text
        if got != text:
            print("XX got %-16s exp %-16s [%016x]" % (got, text, lo))
    print("%s: %d/%d ENDCOLLECTIVE matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
