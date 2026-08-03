#!/usr/bin/env python3
"""Decoder for the sm_120 QMMA tensor-core fp8 instruction (mma.sync fp8).

    QMMA.16832.F32.E4M3.E4M3 Rd, Ra, Rb, Rc     ; m16n8k32 e4m3 -> f32
    QMMA.16816.F32.E4M3.E5M2 ...                ; size/srcFmtA/srcFmtB select shape

fp16_pipe / VQ_HMMA (same class as HMMA).  The dense qmma_/qmma_rowcol_
variants (opcode 0x27a) share one encoding; size 16832 = m16n8k32 (each 32-bit
fragment word holds 4 fp8), 16816 = m16n8k16.

Fields (128-bit):
  opcode  = {bit[91], bits[11:0]} = 0x27a
  size    = [76:75]    SIZE_16816_16832 (0=16816, 1=16832)
  dstfmt  = [77]       FloatNo64 (0=F16, 1=F32) -- also the ntz bit
  srcFmtA = [83:82],[78]  SRCFMTA_qmma (0=E4M3, 1=E5M2, 2=E3M4, 3=E3M2, 4=E2M3, 5=E2M1)
  srcFmtB = [85:84],[79]
  Rd=[23:16]  Ra=[31:24]  Rb=[39:32]  Rc=[71:64]
  Pg     = [14:12] / Pg_not=[15]

Usage: python3 decode_qmma.py            (self-test)
       python3 decode_qmma.py <sass.txt> (validate every QMMA in a dump)
"""
import re
import sys

SIZE = {0: "16816", 1: "16832"}
# QMMA srcFmt enum (sm120, probed): grouped by mantissa width.
# E4M3/E3M4/E2M3 (3-mantissa) = 0/1/2, E5M2/E3M2/E2M1 (2-mantissa) = 4/5/6.
FMT = {0: "E4M3", 1: "E3M4", 2: "E2M3", 4: "E5M2", 5: "E3M2", 6: "E2M1"}


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def reg(n):
    return "RZ" if n == 0xff else "R%d" % n


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode not in (0x27a, 0x47a, 0x47e):
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)

    rd, ra, rb, rc = (bits(inst, 23, 16), bits(inst, 31, 24),
                      bits(inst, 39, 32), bits(inst, 71, 64))
    if opcode in (0x47a, 0x47e):            # QMMA.SF / MXQMMA (block scaling)
        size = "16832"
        dstfmt = "F32"
        sfa = FMT.get(bits(inst, 83, 82) | (bits(inst, 78, 78) << 2), "?")
        sfb = FMT.get(bits(inst, 85, 84) | (bits(inst, 79, 79) << 2), "?")
        re, rh = bits(inst, 47, 40), bits(inst, 59, 52)
        uri = (bits(inst, 77, 73) << 3) | bits(inst, 62, 60)
        uri_s = "URZ" if uri == 255 else "UR%d" % uri
        name = "MXQMMA" if opcode == 0x47e else "QMMA"
        mnem = "%s.SF.%s.%s.%s.%s.E8" % (name, size, dstfmt, sfa, sfb)
        return "%s%s %s, %s, %s, %s, %s, %s, %s" % (
            guard, mnem, reg(rd), reg(ra), reg(rb), reg(rc), reg(re), reg(rh),
            uri_s)
    size = SIZE.get(bits(inst, 76, 75), "?")
    dstfmt = "F32" if bits(inst, 77, 77) else "F16"
    sfa = FMT.get(bits(inst, 83, 82) | (bits(inst, 78, 78) << 2), "?")
    sfb = FMT.get(bits(inst, 85, 84) | (bits(inst, 79, 79) << 2), "?")
    return "%sQMMA.%s.%s.%s.%s %s, %s, %s, %s" % (
        guard, size, dstfmt, sfa, sfb, reg(rd), reg(ra), reg(rb), reg(rc))


# (lo64, hi64, expected) — nvcc mma.sync lowering (verified)
VECTORS = [
    (0x000000020404727a, 0x000fd00000002c0c,
     "QMMA.16832.F32.E4M3.E4M3 R4, R4, R2, R12"),
    (0x7ff0ff020404747a, 0x000fe2000000beff,
     "QMMA.SF.16832.F32.E4M3.E5M2.E8 R4, R4, R2, RZ, RZ, RZ, URZ"),
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        ok += got == exp
        print("%s %-44s (exp %s)" % ("OK " if got == exp else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bQMMA\b", m.group(2)):
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
    print("%s: %d/%d QMMA matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
