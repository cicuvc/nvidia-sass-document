#!/usr/bin/env python3
"""Decoder for the sm_90 WARPSYNC instruction (warp-lane reconverge / __syncwarp).

6 CLASSes over 2 opcodes; the [86:85] `cop` field selects the mode:
  imm/RIR  0x948:  cop0 -> WARPSYNC.ALL
                   cop2 -> WARPSYNC.COLLECTIVE.ALL 0x<target>     (cop1 invalid)
  reg/RRR  0x348:  cop0 -> WARPSYNC R<Ra>
                   cop1 -> WARPSYNC.EXCLUSIVE R<Ra>
                   cop2 -> WARPSYNC.COLLECTIVE R<Ra>, 0x<target>

Fields (128-bit):
  opcode = {bit[91], bits[11:0]}   0x948=imm(full-mask), 0x348=reg-mask
  Pg=[14:12] Pg_not=[15]      guard predicate
  Pp/Pnz=[89:87] Pp_not=[90]  predicate operand (printed if != PT)
  cop=[86:85]                 mode: 0=ALL/plain, 1=EXCLUSIVE, 2=COLLECTIVE
  Ra=[31:24]                  lane-mask register (reg forms)
  sImm=[81:34]∥[23:16] SCALE4 COLLECTIVE branch target = PC+0x10 + sImm*4

Usage: python3 decode_warpsync.py            (self-test)
       python3 decode_warpsync.py <sass.txt> (validate every WARPSYNC in a dump)
"""
import re
import sys

ADDR_MASK = (1 << 48) - 1


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def sx(v, w):
    return v - (1 << w) if v & (1 << (w - 1)) else v


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode == 0x948:
        immform = True
    elif opcode == 0x348:
        immform = False
    else:
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
    cop = bits(inst, 86, 85)

    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    pp_s = "" if (pp == 7 and pp_not == 0) else "%s, " % pred(pp, pp_not)
    simm = sx((bits(inst, 81, 34) << 8) | bits(inst, 23, 16), 56)
    target = (pc + 0x10 + simm * 4) & ADDR_MASK

    if immform:
        if cop == 0:                                   # WARPSYNC.ALL [Pp]
            tail = "" if not pp_s else " " + pp_s[:-2]
            return "%sWARPSYNC.ALL%s" % (guard, tail)
        if cop == 2:
            return "%sWARPSYNC.COLLECTIVE.ALL %s0x%x" % (guard, pp_s, target)
        return "%sWARPSYNC.???%d" % (guard, cop)      # cop1 invalid for imm
    else:
        ra = bits(inst, 31, 24)
        reg = "RZ" if ra == 0xff else "R%d" % ra
        if cop == 0:
            return "%sWARPSYNC %s%s" % (guard, pp_s, reg)
        if cop == 1:
            return "%sWARPSYNC.EXCLUSIVE %s%s" % (guard, pp_s, reg)
        return "%sWARPSYNC.COLLECTIVE %s%s, 0x%x" % (guard, pp_s, reg, target)


# (pc, lo64, hi64, expected) — libcusparse + cubin-patch ground truth
VECTORS = [
    (0x16c0, 0x0000000000007948, 0x000fea0003800000, "WARPSYNC.ALL"),           # libcusparse
    (0x18b0, 0x0000000006087348, 0x022fea0003c00000, "WARPSYNC.COLLECTIVE R6, 0x18e0"),  # libcusparse
    (0x00e0, 0x0000000004087948, 0x000fea0003c00000, "WARPSYNC.COLLECTIVE.ALL 0x110"),
    (0x00e0, 0x0000000004087348, 0x000fea0003800000, "WARPSYNC R4"),
    (0x00e0, 0x0000000004087348, 0x000fea0003a00000, "WARPSYNC.EXCLUSIVE R4"),
    (0x00e0, 0x0000000004087348, 0x000fea0003c00000, "WARPSYNC.COLLECTIVE R4, 0x110"),
]


def run_vectors():
    ok = 0
    for pc, lo, hi, exp in VECTORS:
        got = decode(lo, hi, pc)
        ok += got == exp
        print("%s pc=0x%04x  %-32s (exp %s)" % ("OK " if got == exp else "XX ", pc, got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bWARPSYNC\b", m.group(2)):
            continue
        pc, text, lo = int(m.group(1), 16), m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16), pc)
        total += 1
        ok += got == text
        if got != text:
            print("XX pc=0x%x got %-30s exp %-30s [%016x]" % (pc, got, text, lo))
    print("%s: %d/%d WARPSYNC matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
