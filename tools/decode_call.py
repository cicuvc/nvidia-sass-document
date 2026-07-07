#!/usr/bin/env python3
"""Decoder for the sm_90 CALL instruction (function call).

12 CLASSes across two families x four target kinds:
  ABS: imm 0x0943 | const 0x0b43 | reg 0x0343 | ureg 0x1943   /ABSONLY -> ".ABS"
  REL: imm 0x0944 |               reg 0x0344 | ureg 0x1944   /RelOpt  -> ".REL"

  CALL.ABS  {Pp,} 0x<abs>            imm55  = bits[80:34]∥[23:16]*4  (raw absolute)
  CALL.ABS  {Pp,} c[bank][off*4]     const  = bank[58:54], off=sx14([53:40])*4
  CALL.ABS  {Pp,} R<Ra> [0x<off>]    reg    = Ra[31:24] + off (raw sImm*4)
  CALL.ABS  {Pp,} UR<URa> [0x<off>]  ureg   = URa[29:24] + off
  CALL.REL  {Pp,} 0x<target>         imm56  target = PC+0x10 + sImm*4  (PC-resolved)
  CALL.REL  {Pp,} R<Ra> [0x<off>]    reg    off = PC+0x10 + sImm*4 (PC-resolved)
  CALL.REL  {Pp,} UR<URa> [0x<off>]  ureg

Common fields (128-bit):
  opcode = {bit[91], bits[11:0]}
  Pg=[14:12] Pg_not=[15]      guard predicate
  Pp/Pnz=[89:87] Pp_not=[90]  divergence predicate (printed if != PT)
  depth=[86] CALL_DEPTH       0=INC (hidden), 1=NOINC -> ".NOINC"
  sImm at [81:34]∥[23:16] (imm-abs uses [80:34]), SCALE 4

Emitted by ptxas as CALL.REL.NOINC for non-inlined calls (8494x in libcublas);
other forms obtained by cubin-patch + nvdisasm.
Usage: python3 decode_call.py            (self-test)
       python3 decode_call.py <sass.txt> (validate every CALL in a dump)
"""
import re
import sys

ADDR_MASK = (1 << 40) - 1
# opcode -> (abs/rel, kind)
OPC = {
    0x943: ("ABS", "imm"), 0xb43: ("ABS", "const"),
    0x343: ("ABS", "reg"), 0x1943: ("ABS", "ureg"),
    0x944: ("REL", "imm"), 0x344: ("REL", "reg"), 0x1944: ("REL", "ureg"),
}


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def sx(v, w):
    return v - (1 << w) if v & (1 << (w - 1)) else v


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode not in OPC:
        return "?opcode 0x%x" % opcode
    absrel, kind = OPC[opcode]

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
    depth = bits(inst, 86, 86)

    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    pp_s = "" if (pp == 7 and pp_not == 0) else "%s, " % pred(pp, pp_not)
    mnem = "CALL." + absrel + (".NOINC" if depth else "")

    hi_imm = 80 if (kind == "imm" and absrel == "ABS") else 81
    simm = sx((bits(inst, hi_imm, 34) << 8) | bits(inst, 23, 16), hi_imm - 34 + 1 + 8)

    def offval():
        raw = simm * 4
        v = (pc + 0x10 + raw) if absrel == "REL" else raw
        return v & ADDR_MASK

    if kind == "imm":
        body = "0x%x" % offval()
    elif kind == "const":
        bank = bits(inst, 58, 54)
        o = sx(bits(inst, 53, 40), 14) * 4
        body = "c[%#x][%s%#x]" % (bank, "-" if o < 0 else "", abs(o))
    elif kind == "reg":
        ra = bits(inst, 31, 24)
        reg = "RZ" if ra == 0xff else "R%d" % ra
        show = absrel == "REL" or simm != 0
        body = reg + (" 0x%x" % offval() if show else "")
    else:  # ureg
        ura = bits(inst, 29, 24)
        reg = "URZ" if ura == 63 else "UR%d" % ura
        show = absrel == "REL" or simm != 0
        body = reg + (" 0x%x" % offval() if show else "")

    return "%s%s %s%s" % (guard, mnem, pp_s, body)


# (pc, lo64, hi64, expected) — libcublas + cubin-patch ground truth
VECTORS = [
    (0x0170, 0x0000007800207944, 0x000fea0003c00000, "CALL.REL.NOINC 0x7a00"),   # libcublas
    (0x08a0, 0x0000007400ec7944, 0x000fea0003c00000, "CALL.REL.NOINC 0x8060"),   # libcublas
    (0x00e0, 0x0000000400240943, 0x000fea0003800000, "@P0 CALL.ABS 0x490"),
    (0x00e0, 0x0000000400240943, 0x000fea0003c00000, "@P0 CALL.ABS.NOINC 0x490"),
    (0x00e0, 0x0000400000000b43, 0x000fea0003800000, "@P0 CALL.ABS c[0x0][0x100]"),
    (0x00e0, 0x0000000404240343, 0x000fea0003800000, "@P0 CALL.ABS R4 0x490"),
    (0x00e0, 0x0000000400240944, 0x000fea0003800000, "@P0 CALL.REL 0x580"),
    (0x00e0, 0x0000000404240344, 0x000fea0003800000, "@P0 CALL.REL R4 0x580"),
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
        if not m or not re.search(r"\bCALL\b", m.group(2)):
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
    print("%s: %d/%d CALL matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
