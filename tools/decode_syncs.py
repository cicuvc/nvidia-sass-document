#!/usr/bin/env python3
"""Decoder for the sm_90 SYNCS instruction family — shared-memory synchronization
(mbarrier ops + shared uniform atomics), on mio_pipe, compute-only.

9 sm_90 variants (10 on sm_100+, which adds FLUSH), dispatched by opcode:
  0x19a7 ARRIVE/TCNT   SYNCS.ARRIVE.TRANS64[.RED|.TMASK][.<paramtype>] Rd, [addr], Rb
  0x15a7 PHASECHK      SYNCS.PHASECHK.TRANS64[.TRYWAIT] Pu, [addr], Rb
  0x15b2 uniform EXCH  SYNCS.EXCH.64  URd, [URa(+off)], URb
  0x13b2 uniform CAS   SYNCS.CAS.64   URd, [URa(+off)], URb, URc
  0x19b2 uniform LD    SYNCS.LD[.64]  URd, [URa(+off)]
  0x19b1 CCTL          SYNCS.CCTL...  (mbarrier cache control)
  0x09b1 CCTL_ALL      SYNCS.CCTL...ALL
  0x15b1 LD (GPR)      SYNCS.LD[.WATCH] Rd, [addr]
  0x03a7 FLUSH         SYNCS.FLUSH (sm_100+)

mbarrier semantics (tx-count arrive/expect_tx, phase-parity try_wait) are covered in
notes/sm90/arch/tma_mbarrier.md; this decoder reconstructs the disassembly text.

Key fields (ARRIVE 0x19a7 / PHASECHK 0x15a7):
  paramtype=[86:84] PARAMTYPE {0 A1TR(hidden),1 A1T0,2 A0T1,3 A0TR,4 A0TX,5 ART0}
  retval  =[74:73] {0 OLDSTATE(hidden),1 .TMASK,2 .RED}
  wait    =[72]    PHASECHK {1 .TRYWAIT}
  Pu=[83:81]  Rd=[23:16]  Rb=[39:32]  Ra=[31:24]  URc=[69:64]  off=[63:40]
EXCH/CAS/LD (uniform): URd=[21:16] URa=[29:24] URb=[37:32] off=[63:40]

Usage: python3 decode_syncs.py            (self-test)
       python3 decode_syncs.py <sass.txt>  (validate every SYNCS in a dump)
"""
import re
import sys

PARAMTYPE = {0: "", 1: ".A1T0", 2: ".A0T1", 3: ".A0TR", 4: ".A0TX", 5: ".ART0",
             6: ".INVALID6", 7: ".INVALID7"}
RETVAL = {0: "", 1: ".TMASK", 2: ".RED", 3: ".INVALID3"}


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def reg(n):
    return "RZ" if n == 0xff else "R%d" % n


def ureg(n):
    return "URZ" if n == 63 else "UR%d" % n


def pred(idx):
    return "PT" if idx == 7 else "P%d" % idx


def _addr(inst):
    ra, urc, off = bits(inst, 31, 24), bits(inst, 69, 64), bits(inst, 63, 40)
    parts = []
    if ra != 0xff:
        parts.append(reg(ra))
    # cuobjdump keeps the explicit +URZ component for GPR-based shared
    # addresses, but suppresses the RZ component for uniform-only addresses.
    if urc != 63 or ra != 0xff:
        parts.append(ureg(urc))
    if off:
        parts.append("%#x" % off)
    return "[%s]" % "+".join(parts or ["RZ"])


def _uaddr(inst):
    ura, off = bits(inst, 29, 24), bits(inst, 63, 40)
    parts = [ureg(ura)]
    if off:
        parts.append("%#x" % off)
    return "[%s]" % "+".join(parts)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    uniform = opcode in (0x15b2, 0x13b2, 0x19b2)
    pname = ("UPT" if pg == 7 else "UP%d" % pg) if uniform else pred(pg)
    guard = "" if (pg == 7 and pg_not == 0) else "@%s%s " % ("!" if pg_not else "", pname)

    body = _body(inst, opcode)
    return guard + body


def _body(inst, opcode):
    if opcode == 0x19a7:                                    # ARRIVE / TCNT
        m = "SYNCS.ARRIVE.TRANS64" + RETVAL[bits(inst, 74, 73)]
        if bits(inst, 75, 75):
            m += ".OPTOUT"
        m += PARAMTYPE[bits(inst, 86, 84)]
        return "%s %s, %s, %s" % (m, reg(bits(inst, 23, 16)), _addr(inst), reg(bits(inst, 39, 32)))
    if opcode == 0x15a7:                                    # PHASECHK
        w = ".TRYWAIT" if bits(inst, 72, 72) else ""
        return "SYNCS.PHASECHK.TRANS64%s %s, %s, %s" % (
            w, pred(bits(inst, 83, 81)), _addr(inst), reg(bits(inst, 39, 32)))
    if opcode == 0x15b2:                                    # uniform EXCH
        return "SYNCS.EXCH.64 %s, %s, %s" % (
            ureg(bits(inst, 21, 16)), _uaddr(inst), ureg(bits(inst, 37, 32)))
    if opcode == 0x13b2:                                    # uniform CAS
        urcmp = bits(inst, 37, 32)
        return "SYNCS.CAS.64 %s, %s, %s, %s" % (
            ureg(bits(inst, 21, 16)), _uaddr(inst), ureg(urcmp), ureg(urcmp + 2))
    if opcode == 0x19b2:                                    # uniform LD
        return "SYNCS.LD.64 %s, %s" % (ureg(bits(inst, 21, 16)), _uaddr(inst))
    if opcode == 0x19b1:
        op = "WB" if bits(inst, 72, 72) else "IV"
        return "SYNCS.CCTL.%s %s" % (op, _addr(inst))
    if opcode == 0x09b1:
        op = "WBALL" if bits(inst, 72, 72) else "IVALL"
        return "SYNCS.CCTL.%s" % op
    if opcode == 0x15b1:
        watch = ".WATCH" if bits(inst, 74, 74) else ""
        return "SYNCS.LD.64%s %s, %s" % (
            watch, reg(bits(inst, 23, 16)), _addr(inst))
    if opcode == 0x03a7:
        return "SYNCS.FLUSH"
    return "?opcode 0x%x" % opcode


VECTORS = [
    (0x00000000ffff79a7, 0x000fe20008000006, "SYNCS.ARRIVE.TRANS64 RZ, [UR6], R0"),
    (0x000000ffff0279a7, 0x000e240008100006, "SYNCS.ARRIVE.TRANS64.A1T0 R2, [UR6], RZ"),
    (0x00000002ff0679a7, 0x0084220008500004, "SYNCS.ARRIVE.TRANS64.ART0 R6, [UR4], R2"),
    (0x000000ffffff79a7, 0x000fe20008100004, "SYNCS.ARRIVE.TRANS64.A1T0 RZ, [UR4], RZ"),
    (0x000000ffffff79a7, 0x000fe20008100407, "SYNCS.ARRIVE.TRANS64.RED.A1T0 RZ, [UR7], RZ"),
    (0x00000000ff0075a7, 0x000e240008000144, "SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR4], R0"),
    (0x00000004063f85b2, 0x0000640008000100, "@!UP0 SYNCS.EXCH.64 URZ, [UR6], UR4"),
    (0x00000004093f75b2, 0x0010640008000100, "SYNCS.EXCH.64 URZ, [UR9], UR4"),
    (0x00000004ff0279a7, 0x000e8a0008500a06,
     "SYNCS.ARRIVE.TRANS64.TMASK.OPTOUT.ART0 R2, [UR6], R4"),
    (0x00000000ff0079b1, 0x000e8a0008000006, "SYNCS.CCTL.IV [UR6]"),
    (0x00000000ff0079b1, 0x000e8a0008000106, "SYNCS.CCTL.WB [UR6]"),
    (0x00000000000079b1, 0x000e8a0000000000, "SYNCS.CCTL.IVALL"),
    (0x00000000000079b1, 0x000e8a0000000100, "SYNCS.CCTL.WBALL"),
    (0x00000000ff0875b1, 0x000e8a0008000606, "SYNCS.LD.64.WATCH R8, [UR6]"),
    (0x00000008060c73b2, 0x000e8a0008000200,
     "SYNCS.CAS.64 UR12, [UR6], UR8, UR10"),
    (0x00000000000073a7, 0x000e8a0000002000, "SYNCS.FLUSH"),
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        # strip guard for compare (EXCH vector has @!UP0 from a uniform-pred guard)
        got_cmp = got
        ok += got_cmp == exp
        print("%s %-42s (exp %s)" % ("OK " if got_cmp == exp else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bSYNCS\.", m.group(2)):
            continue
        text = m.group(2).strip()
        lo = int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16))
        total += 1
        ok += got == text
        if got != text:
            print("XX got %-40s exp %-40s [%016x]" % (got, text, lo))
    print("%s: %d/%d SYNCS matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
