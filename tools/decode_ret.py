#!/usr/bin/env python3
"""Decoder for the sm_90 RET instruction (return from subroutine).

8 CLASSes across 2 opcodes:
  0x0950  RET  reg   : @Pg RET.{REL|ABS}[.NODEC] {Pp,} R<Ra> 0x<off>    Ra=[31:24]
  0x1950  RET  ureg  : @Pg RET.{REL|ABS}[.NODEC] {Pp,} UR<URa> 0x<off>  URa=[29:24]

Fields (128-bit):
  opcode = {bit[91], bits[11:0]}   (b91=1 -> uniform-register form 0x1950)
  Pg=[14:12] Pg_not=[15]      guard predicate
  Pp/Pnz=[89:87] Pp_not=[90]  divergence predicate (printed if != PT)
  depth=[86] RET_DEPTH        0=DEC (hidden), 1=NODEC -> ".NODEC"
  addr =[85] RET_ADDR         0=.REL, 1=.ABS
  sImm = bits[81:34]∥bits[23:16] (56-bit signed), SCALE 4
         REL -> offset = PC+0x10 + sImm*4 (PC-resolved); ABS -> raw sImm*4; masked 40-bit
  Ra=[31:24] (GPR pair, holds the return address)  /  URa=[29:24]

ptxas emits RET.REL.NODEC R<n> (register-ABI return); see notes/ret.md.
Usage: python3 decode_ret.py            (self-test)
       python3 decode_ret.py <sass.txt> (validate every RET in a dump)
"""
import re
import sys

ADDR_MASK = (1 << 40) - 1


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def sx(v, w):
    return v - (1 << w) if v & (1 << (w - 1)) else v


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode == 0x950:
        uniform = False
    elif opcode == 0x1950:
        uniform = True
    else:
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
    depth = bits(inst, 86, 86)
    absmode = bits(inst, 85, 85)
    simm = sx((bits(inst, 81, 34) << 8) | bits(inst, 23, 16), 56)

    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    pp_s = "" if (pp == 7 and pp_not == 0) else "%s, " % pred(pp, pp_not)
    mnem = "RET." + ("ABS" if absmode else "REL") + (".NODEC" if depth else "")

    raw = simm * 4
    off = ((pc + 0x10 + raw) if absmode == 0 else raw) & ADDR_MASK

    if uniform:
        ura = bits(inst, 29, 24)
        reg = "URZ" if ura == 63 else "UR%d" % ura
    else:
        ra = bits(inst, 31, 24)
        reg = "RZ" if ra == 0xff else "R%d" % ra

    return "%s%s %s%s 0x%x" % (guard, mnem, pp_s, reg, off)


# (pc, lo64, hi64, expected) — real ptxas output from tests/call_test.cu + patches
VECTORS = [
    (0x0320, 0xfffffffc14347950, 0x004fec0003c3ffff, "RET.REL.NODEC R20 0x0"),
    (0x0370, 0xfffffffc06207950, 0x000fec0003c3ffff, "RET.REL.NODEC R6 0x0"),
    (0x00e0, 0x0000000404240950, 0x000fea0000200000, "@P0 RET.ABS P0, R4 0x490"),
    (0x00e0, 0x0000000404240950, 0x000fea0000000000, "@P0 RET.REL P0, R4 0x580"),
    (0x00e0, 0x0000000404241950, 0x000fea0008400000, "@P1 RET.REL.NODEC P0, UR4 0x580"),
]


def run_vectors():
    ok = 0
    for pc, lo, hi, exp in VECTORS:
        got = decode(lo, hi, pc)
        ok += got == exp
        print("%s pc=0x%04x  %-24s (exp %s)" % ("OK " if got == exp else "XX ", pc, got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bRET\b", m.group(2)):
            continue
        pc, text, lo = int(m.group(1), 16), m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        hi = int(hm.group(1), 16)
        got = decode(lo, hi, pc)
        total += 1
        ok += got == text
        if got != text:
            print("XX pc=0x%x got %-24s exp %-24s [%016x %016x]" % (pc, got, text, lo, hi))
    print("%s: %d/%d RET matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
