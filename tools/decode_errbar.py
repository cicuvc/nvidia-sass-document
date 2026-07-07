#!/usr/bin/env python3
"""Decoder for the sm_90 error-barrier instructions ERRBAR (0x9ab) and CGAERRBAR (0x5ab).

Error barriers: they synchronize/surface *deferred errors* (async/bulk memory faults,
ECC, etc.) from prior operations. The compiler emits them right after a MEMBAR fence:
    MEMBAR.<scope> ; ERRBAR ; CGAERRBAR
so a fence both orders memory and guarantees pending errors are observed. Also seen in
kernel cleanup/exit paths. Both are mio_pipe, operand-less (guard only).
  ERRBAR    0x9ab  INST_TYPE_COUPLED_MATH  (blocks, fixed-latency)
  CGAERRBAR 0x5ab  INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD  (cluster-scope, decoupled)

Fields (128-bit): opcode={bit[91],[11:0]}; Pg=[14:12]/[15] guard.
Usage: python3 decode_errbar.py            (self-test)
       python3 decode_errbar.py <sass.txt>  (validate every ERRBAR/CGAERRBAR)
"""
import re
import sys

OPC = {0x9ab: "ERRBAR", 0x5ab: "CGAERRBAR"}


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode not in OPC:
        return "?opcode 0x%x" % opcode
    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    return "%s%s" % (guard, OPC[opcode])


VECTORS = [
    (0x00000000000079ab, 0x000fc00000000000, "ERRBAR"),      # after MEMBAR fence
    (0x00000000000075ab, 0x000fec0000000000, "CGAERRBAR"),   # cluster-scope error barrier
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
        if not m or not re.search(r"\b(ERRBAR|CGAERRBAR)\b", m.group(2)):
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
    print("%s: %d/%d ERRBAR/CGAERRBAR matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
