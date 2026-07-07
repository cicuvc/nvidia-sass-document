#!/usr/bin/env python3
"""Decoder for the sm_90 ARRIVES instruction (arrive on the cp.async/LDGSTS mbarrier).

ARRIVES connects a cp.async (LDGSTS) group's completion to an mbarrier, so the barrier
tracks async-copy completion. It is what PTX `cp.async.mbarrier.arrive[.noinc]` lowers to:
  cp.async.mbarrier.arrive.shared.b64        -> ARRIVES.LDGSTSBAR.64.TRANSCNT [addr]
  cp.async.mbarrier.arrive.noinc.shared.b64  -> ARRIVES.LDGSTSBAR.64.ARVCNT   [addr]
mio_pipe, compute-only; the address must have Ra==RZ (uniform-reg addressed shared bar).

Fields (128-bit):
  opcode = {bit[91], bits[11:0]} = 0x19b0
  sz     = [75:73]  CInteger_64  (5 -> .64)
  arrive = [72]     LDGSTSBARONLY (0 -> .LDGSTSBAR)
  barop  = [71:70]  BAROP {0 LEGACY, 1 ARVCNT, 2 TRANSCNT}
  addr   = [Ra + URc + off]  Ra[31:24]=RZ, URc[69:64], off[63:40]
  Pg     = [14:12]/[15]

Usage: python3 decode_arrives.py            (self-test)
       python3 decode_arrives.py <sass.txt>  (validate every ARRIVES in a dump)
"""
import re
import sys

BAROP = {0: ".LEGACY", 1: ".ARVCNT", 2: ".TRANSCNT", 3: ".INVALID3"}


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def ureg(n):
    return "URZ" if n == 63 else "UR%d" % n


def reg(n):
    return "RZ" if n == 0xff else "R%d" % n


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode != 0x19b0:
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)

    sz = ".64" if bits(inst, 75, 73) == 5 else ".sz%d" % bits(inst, 75, 73)
    lg = ".LDGSTSBAR" if bits(inst, 72, 72) == 0 else ".???"
    mnem = "ARRIVES" + lg + sz + BAROP[bits(inst, 71, 70)]

    ra, urc, off = bits(inst, 31, 24), bits(inst, 69, 64), bits(inst, 63, 40)
    parts = []
    if ra != 0xff:
        parts.append(reg(ra))
    if urc != 63:
        parts.append(ureg(urc))
    if off:
        parts.append("%#x" % off)
    addr = "[%s]" % "+".join(parts or ["RZ"])
    return "%s%s %s" % (guard, mnem, addr)


# (lo64, hi64, expected) — cp.async.mbarrier.arrive lowering
VECTORS = [
    (0x00000000ff0079b0, 0x000fe20008000a87, "ARRIVES.LDGSTSBAR.64.TRANSCNT [UR7]"),
    (0x00000000ff0079b0, 0x000fe20008000a47, "ARRIVES.LDGSTSBAR.64.ARVCNT [UR7]"),
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        ok += got == exp
        print("%s %-38s (exp %s)" % ("OK " if got == exp else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bARRIVES\b", m.group(2)):
            continue
        text, lo = m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16))
        total += 1
        ok += got == text
        if got != text:
            print("XX got %-36s exp %-36s [%016x]" % (got, text, lo))
    print("%s: %d/%d ARRIVES matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
