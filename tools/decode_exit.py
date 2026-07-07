#!/usr/bin/env python3
"""Decoder for the sm_90 thread terminators EXIT (0x94d) and KILL (0x95b).

  EXIT : @Pg EXIT{.mode}{.NO_ATEXIT} [Pp]     terminate the thread
  KILL : @Pg KILL [Pp]                        discard (pixel-shader only)

Fields (128-bit):
  opcode = {bit[91], bits[11:0]}
  Pg=[14:12] Pg_not=[15]      guard predicate
  Pp/Pnz=[89:87] Pp_not=[90]  predicate operand (printed if != PT, e.g. "EXIT P1")
  EXIT only: mode=[85:84] EXIT_MODE  {0:-, 1:.KEEPREFCOUNT, 2:.PREEMPTED, 3:.???3}
             no_atexit=[86]          {0:-, 1:.NO_ATEXIT}

KILL is legal only in pixel shaders (SHADER_TYPE==PS); it never appears in compute
SASS (patch-derived rendering here). Both are DECOUPLED_BRU on cbu_pipe.
Usage: python3 decode_exit.py            (self-test)
       python3 decode_exit.py <sass.txt> (validate every EXIT/KILL in a dump)
"""
import re
import sys

MODE = {0: "", 1: ".KEEPREFCOUNT", 2: ".PREEMPTED", 3: ".???3"}


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode == 0x94d:
        mnem = "EXIT"
    elif opcode == 0x95b:
        mnem = "KILL"
    else:
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    pp_s = "" if (pp == 7 and pp_not == 0) else " %s" % pred(pp, pp_not)

    if mnem == "EXIT":
        mnem += MODE[bits(inst, 85, 84)]
        if bits(inst, 86, 86):
            mnem += ".NO_ATEXIT"
    return "%s%s%s" % (guard, mnem, pp_s)


# (lo64, hi64, expected) — real cusparse + cubin-patch ground truth
VECTORS = [
    (0x000000000000794d, 0x000fea0003800000, "EXIT"),
    (0x000000000000194d, 0x000fea0003800000, "@P1 EXIT"),                # cusparse
    (0x000000000000594d, 0x000fea0000800000, "@P5 EXIT P1"),             # cusparse
    (0x000000000000794d, 0x000fea0003900000, "EXIT.KEEPREFCOUNT"),       # patch
    (0x000000000000794d, 0x000fea0003a00000, "EXIT.PREEMPTED"),          # patch
    (0x000000000000794d, 0x000fea0003c00000, "EXIT.NO_ATEXIT"),          # patch
    (0x000000000000795b, 0x000fea0003800000, "KILL"),                    # patch (PS-only)
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        ok += got == exp
        print("%s %-22s (exp %s)" % ("OK " if got == exp else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\b(EXIT|KILL)\b", m.group(2)):
            continue
        text, lo = m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16))
        total += 1
        ok += got == text
        if got != text:
            print("XX got %-22s exp %-22s [%016x]" % (got, text, lo))
    print("%s: %d/%d EXIT/KILL matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
