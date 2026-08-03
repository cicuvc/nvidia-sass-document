#!/usr/bin/env python3
"""Decoder for the sm_90 HMMA tensor-core instruction (mma.sync family).

The classic 4-register-output HMMA shapes share one encoding variant:
    HMMA.16816.F32.BF16  (m16n8k16 bf16 -> f32, A-accumulate)
    HMMA.1688.F32.F16    (m16n8k8  f16 -> f32)
    ...                  (size/srcfmt/dstfmt select the shape)

fp16_pipe / VQ_HMMA.  SASS form (cuobjdump prints scalar, assembler uses groups):
    HMMA.16816.F32.BF16 Rd, Ra, Rb, Rc        ; cuobjdump
    HMMA.16816.F32.BF16 {Rd..Rd+3}, {Ra..Ra+3}, {Rb,Rb+1}, {Rc..Rc+3}  ; source

Fields (128-bit):
  opcode = {bit[91], bits[11:0]} = 0x23c
  size   = [78],[75]  SIZE_1688_16816_1684  (0=1688, 1=16816, 2=1684)
  dstfmt = [76]       FloatNo64  (0=F16, 1=F32)  -- also the memdesc bit
  srcfmt = [83:82]    SRCFMT (0=F16, 1=BF16, 2=TF32, 3=E6M9)
  Rd     = [23:16]    Ra=[31:24]  Rb=[39:32]  Rc=[71:64]
  Pg     = [14:12] / Pg_not=[15]

Register widths (PREDICATES): Rd/Rc = 64+(F32)*64, Ra = 64+((16816&&(F16|BF16))*64),
Rb = 32+((16816&&(F16|BF16))*32).  For 16816 F32/BF16: Rd/Rc 4x32, Ra 4x32, Rb 2x32.

Usage: python3 decode_hmma.py            (self-test)
       python3 decode_hmma.py <sass.txt> (validate every HMMA in a dump)
"""
import re
import sys

SIZE = {0: "1688", 1: "16816", 2: "1684"}
SRCFMT = {0: "F16", 1: "BF16", 2: "TF32", 3: "E6M9"}


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def reg(n):
    return "RZ" if n == 0xff else "R%d" % n


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode not in (0x23c, 0x1e79):
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)

    size = SIZE.get(bits(inst, 78, 78) << 1 | bits(inst, 75, 75), "?")
    dstfmt = "F32" if bits(inst, 76, 76) else "F16"
    srcfmt = SRCFMT.get(bits(inst, 83, 82), "?")

    rd, ra, rb, rc = (bits(inst, 23, 16), bits(inst, 31, 24),
                      bits(inst, 39, 32), bits(inst, 71, 64))
    # F16 is the default source format (no suffix in cuobjdump); BF16/TF32/E6M9
    # are printed, matching cuobjdump's "HMMA.16816.F32" vs "HMMA.16816.F32.BF16".
    mnem = "HMMA.%s.%s" % (size, dstfmt)
    if srcfmt != "F16":
        mnem += ".%s" % srcfmt
    return "%s%s %s, %s, %s, %s" % (guard, mnem, reg(rd), reg(ra), reg(rb), reg(rc))


# (lo64, hi64, expected) — nvcc mma.sync m16n8k16 bf16/f16 lowering (verified)
VECTORS = [
    (0x000000020404723c, 0x000fe20000041808, "HMMA.16816.F32.BF16 R4, R4, R2, R8"),
    (0x000000020404723c, 0x000fe2000000180c, "HMMA.16816.F32 R4, R4, R2, R12"),
    (0x00000014101c723c, 0x000fe20000041818, "HMMA.16816.F32.BF16 R28, R16, R20, R24"),
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
        if not m or not re.search(r"\bHMMA\b", m.group(2)):
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
    print("%s: %d/%d HMMA matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
