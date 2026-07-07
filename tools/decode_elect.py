#!/usr/bin/env python3
"""Decoder for the sm_90 ELECT instruction (elect a leader lane in a warp).

ELECT picks one leader lane from a candidate set and returns:
  - Pu  : leader predicate (true only in the elected lane)
  - URd : uniform reg receiving the elected lane's id
The candidate set comes from a uniform-register membermask (URa) or a predicate (Pp).

  0x182f  elect_       : @Pg ELECT[.IGNOREKILL] Pu, URd, [~]URa   URa=[29:24], e=[72]
  0x082f  elect_Pp_    : @Pg ELECT[.IGNOREKILL] Pu, URd, [!]Pp    Pp=[89:87], not=[90]
  0x182f  elect_noURa_ : @Pg ELECT[.IGNOREKILL] Pu, URd           (ALT; rendered as elect_)

Common fields (128-bit):
  opcode = {bit[91], bits[11:0]}   (b91=1 -> URa form 0x182f, b91=0 -> Pp form 0x82f)
  Pg=[14:12]/[15]   guard predicate
  ignoreKill=[85]   1 -> .IGNOREKILL
  Pu=[83:81]        leader output predicate
  URd=[21:16]       leader-id output uniform reg (URZ=63)

INST_TYPE_COUPLED_MATH (dispatches on cbu_pipe but scheduled as fixed-latency coupled).
Usage: python3 decode_elect.py            (self-test)
       python3 decode_elect.py <sass.txt> (validate every ELECT in a dump)
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
    if opcode == 0x182f:
        ura_form = True
    elif opcode == 0x82f:
        ura_form = False
    else:
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    ik = ".IGNOREKILL" if bits(inst, 85, 85) else ""

    pu = "P%d" % bits(inst, 83, 81) if bits(inst, 83, 81) != 7 else "PT"
    urd_v = bits(inst, 21, 16)
    urd = "URZ" if urd_v == 63 else "UR%d" % urd_v

    if ura_form:
        ura_v = bits(inst, 29, 24)
        inv = "~" if bits(inst, 72, 72) else ""
        src = "%s%s" % (inv, "URZ" if ura_v == 63 else "UR%d" % ura_v)
    else:
        src = pred(bits(inst, 89, 87), bits(inst, 90, 90))

    return "%sELECT%s %s, %s, %s" % (guard, ik, pu, urd, src)


# (lo64, hi64, expected) — real (elect.sync PTX) + cubin-patch
VECTORS = [
    (0x00000000003f782f, 0x000fe20003800000, "ELECT P0, URZ, PT"),          # asm elect.sync
    (0x00000000003f782f, 0x000fe20003a00000, "ELECT.IGNOREKILL P0, URZ, PT"),
    (0x000000000506082f, 0x000fe2000b860000, "@P0 ELECT P3, UR6, UR5"),
    (0x000000000506082f, 0x000fe2000b860100, "@P0 ELECT P3, UR6, ~UR5"),
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        ok += got == exp
        print("%s %-32s (exp %s)" % ("OK " if got == exp else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bELECT\b", m.group(2)):
            continue
        text, lo = m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16))
        total += 1
        ok += got == text
        if got != text:
            print("XX got %-30s exp %-30s [%016x]" % (got, text, lo))
    print("%s: %d/%d ELECT matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
