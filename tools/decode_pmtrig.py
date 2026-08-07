#!/usr/bin/env python3
"""Decoder for the sm_90 PMTRIG instruction (performance-monitor trigger,
opcode 0x801, fe_pipe).

Main CLASS pmtrig_ layout (128-bit):
  opcode  = {bit[91], bits[11:0]}          (13-bit, 0x801)
  Pg      = bits[14:12], Pg_not = bit[15]  guard predicate   ('@!Px')
  Pp      = bits[89:87], Pp_not = bit[90]  trigger predicate (printed if != PT)
  imm     = bits[47:32]                    16-bit event bitmask (1 << N for
                                           PTX pmevent N; .mask passes M raw)
  pm_pred = bits[103:102]                  PM_PRED (PMN/PM1/PM2/PM3) — which
                                           performance-monitor counter the
                                           trigger feeds; default PMN, never
                                           emitted by ptxas / cuobjdump.

Usage: python3 decode_pmtrig.py            (built-in self-test vectors)
       python3 decode_pmtrig.py <sass.txt> (validate every PMTRIG in a dump)
"""
import re
import sys


def bits(val, hi, lo):
    return (val >> lo) & ((1 << (hi - lo + 1)) - 1)


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode != 0x801:
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
    imm = bits(inst, 47, 32)

    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    pp_s = "" if (pp == 7 and pp_not == 0) else "%s, " % pred(pp, pp_not)
    return "%sPMTRIG %s0x%x" % (guard, pp_s, imm)


# (lo64, hi64, expected) — real nvcc pmevent dumps (sm_90 == sm_120 encodings),
# plus hand-built Pg/Pp variants using the CLASS field map.
VECTORS = [
    (0x0000000100007801, 0x000fe20003800000, "PMTRIG 0x1"),
    (0x0000000200007801, 0x000fe20003800000, "PMTRIG 0x2"),
    (0x0000000400007801, 0x000fe20003800000, "PMTRIG 0x4"),
    (0x0000000800007801, 0x000fe20003800000, "PMTRIG 0x8"),
    (0x0000001000007801, 0x000fe20003800000, "PMTRIG 0x10"),
    (0x0000800000007801, 0x000fe20003800000, "PMTRIG 0x8000"),
    (0x0000000500007801, 0x000fe20003800000, "PMTRIG 0x5"),
    (0x0000ffff00007801, 0x000fe20003800000, "PMTRIG 0xffff"),
    # @!P0 PMTRIG 0x10   (Pg=0, Pg_not=1)
    (0x0000001000008801, 0x000fe20003800000, "@!P0 PMTRIG 0x10"),
    # PMTRIG !P1, 0x8    (Pp=1, Pp_not=1: hi64 bits[26]=1, [25:23]=1)
    (0x0000000800007801, 0x000fe20004800000, "PMTRIG !P1, 0x8"),
    # @P3 PMTRIG P2, 0x8000  (Pg=3, Pp=2: hi64 bits[25:23]=2)
    (0x0000800000023801, 0x000fe20001000000, "@P3 PMTRIG P2, 0x8000"),
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        good = got == exp
        ok += good
        print("%s %-24s (exp %s)" % ("OK " if good else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bPMTRIG\b", m.group(2)):
            continue
        text, lo = m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16))
        total += 1
        ok += got == text
        if got != text:
            print("XX got %-24s exp %-24s [%016x]" % (got, text, lo))
    print("%s: %d/%d PMTRIG matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
