#!/usr/bin/env python3
"""Decoder for the sm_90 NANOSLEEP instruction (timed warp back-off sleep).

Suspends the warp for ~N nanoseconds (exponential-backoff hint for spin/poll loops);
the timed cousin of YIELD. Duration source picks the variant:

  0x095d  __I / _clear_ : imm ns = Sb[63:32]   (clear bit[83]=1 -> NANOSLEEP.CLEAR)
  0x035d  __R           : reg   = Rb[39:32]
  0x0b5d  __C           : const bank
  0x1b5d  __CX / 0x1d5d __U : const-extended / uniform-reg

Fields (128-bit):
  opcode = {bit[91], bits[11:0]}
  Pg=[14:12]/[15]   guard predicate
  Pp/Pnz=[89:87]/[90]  predicate operand (printed if != PT)
  rand=[86] -> .RAND | warp=[85] -> .WARP | syncs=[84] -> .SYNCS | clear=[83] -> .CLEAR
  Sb=[63:32]  imm duration (ns)   |   Rb=[39:32] reg duration

cbu_pipe / DECOUPLED_BRU; RPC_WRITERS + CBU_OPS_WITH_REQ.
Usage: python3 decode_nanosleep.py            (self-test)
       python3 decode_nanosleep.py <sass.txt>  (validate every NANOSLEEP in a dump)
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
    kind = {0x95d: "imm", 0x35d: "reg", 0xb5d: "const",
            0x1b5d: "constx", 0x1d5d: "ureg"}.get(opcode)
    if kind is None:
        return "?opcode 0x%x" % opcode

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)

    if opcode == 0x95d and bits(inst, 83, 83):          # nanosleep_clear_
        pp_s = "" if (pp == 7 and pp_not == 0) else " %s" % pred(pp, pp_not)
        return "%sNANOSLEEP.CLEAR%s" % (guard, pp_s)

    mods = ""
    if bits(inst, 86, 86):
        mods += ".RAND"
    if bits(inst, 85, 85):
        mods += ".WARP"
    if bits(inst, 84, 84):
        mods += ".SYNCS"

    if kind == "imm":
        src = "0x%x" % bits(inst, 63, 32)
    elif kind == "reg":
        rb = bits(inst, 39, 32)
        src = "RZ" if rb == 0xff else "R%d" % rb
    elif kind == "ureg":
        ur = bits(inst, 39, 32) & 0x3f
        src = "URZ" if ur == 63 else "UR%d" % ur
    else:
        src = "c[..][..]"                               # const forms (not sampled)
    return "%sNANOSLEEP%s %s" % (guard, mods, src)


# (lo64, hi64, expected) — real ptxas (tests/nanosleep_test.cu) + cubin-patch
VECTORS = [
    (0x000000640000795d, 0x000fea0003800000, "NANOSLEEP 0x64"),
    (0x000000200000795d, 0x000fea0003800000, "NANOSLEEP 0x20"),
    (0x000000040000735d, 0x004fea0003800000, "NANOSLEEP R4"),
    (0x000000640000795d, 0x000fea0003c00000, "NANOSLEEP.RAND 0x64"),
    (0x000000640000795d, 0x000fea0003a00000, "NANOSLEEP.WARP 0x64"),
    (0x000000640000795d, 0x000fea0003900000, "NANOSLEEP.SYNCS 0x64"),
    (0x000000640000795d, 0x000fea0003880000, "NANOSLEEP.CLEAR"),
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
        if not m or not re.search(r"\bNANOSLEEP\b", m.group(2)):
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
    print("%s: %d/%d NANOSLEEP matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
