#!/usr/bin/env python3
"""Decoder for the sm_90 BAR instruction (CTA / named-barrier synchronization).

BAR is compute-only (SHADER_TYPE==CS) and runs on the **mio_pipe** (not cbu_pipe).
26 CLASSes = barmode x operand-form; the opcode's low bits pick the operand form:
  0xb1d II (baridx imm, count imm)   0x91d IR (baridx imm, count reg)
  0x51d RI (baridx reg, count imm)   0x31d RR (baridx reg == count reg)

  barmode [79:77]: 0 SYNC | 1 ARV | 2 RED | 3 SCAN | 4 SYNCALL
  defer   [80]   : 1 -> .DEFER_BLOCKING
  bop     [75:74]: RED op  0 POPC | 1 AND | 2 OR      (RED mode only)
  barname [57:54]: named-barrier index 0..15  (imm forms)
  Sc      [53:42]: thread count (imm forms; omitted when 0 for SYNC/RED)
  Rb/Rc   [39:32]: barrier/count register (reg forms)
  Pp/Pnz  [89:87]: source predicate (RED/SCAN)
  Pg      [14:12]/[15]: guard predicate

Renders (verified): BAR.SYNC.DEFER_BLOCKING 0x0 | BAR.SYNC.DEFER_BLOCKING 0x1, 0x100 |
BAR.ARV 0x1, 0x100 | BAR.RED.POPC.DEFER_BLOCKING 0x0, P0 | BAR.SYNCALL

Usage: python3 decode_bar.py            (self-test)
       python3 decode_bar.py <sass.txt> (validate every BAR in a dump)
"""
import re
import sys

MODE = {0: "SYNC", 1: "ARV", 2: "RED", 3: "SCAN", 4: "SYNCALL"}
BOP = {0: ".POPC", 1: ".AND", 2: ".OR", 3: ".???3"}
# opcode -> (baridx_is_reg, count_is_reg)
FORM = {0xb1d: (False, False), 0x91d: (False, True),
        0x51d: (True, False), 0x31d: (True, True)}


def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def pred(idx, neg):
    return ("!" if neg else "") + ("PT" if idx == 7 else "P%d" % idx)


def decode(lo64, hi64, pc=0):
    inst = lo64 | (hi64 << 64)
    opcode = (bits(inst, 91, 91) << 12) | bits(inst, 11, 0)
    if opcode not in FORM:
        return "?opcode 0x%x" % opcode
    bar_reg, cnt_reg = FORM[opcode]

    pg, pg_not = bits(inst, 14, 12), bits(inst, 15, 15)
    barmode = MODE.get(bits(inst, 79, 77), "?mode")
    defer = ".DEFER_BLOCKING" if bits(inst, 80, 80) else ""

    guard = "" if (pg == 7 and pg_not == 0) else "@%s " % pred(pg, pg_not)
    mnem = "BAR." + barmode
    if barmode == "RED":
        mnem += BOP[bits(inst, 75, 74)]
    mnem += defer

    if barmode == "SYNCALL":
        return (guard + mnem).rstrip()

    reg = bits(inst, 39, 32)
    reg_s = "RZ" if reg == 0xff else "R%d" % reg
    barname = bits(inst, 57, 54)
    sc = bits(inst, 53, 42)

    ops = []
    ops.append(reg_s if bar_reg else "0x%x" % barname)          # barrier operand
    # count operand: shown if reg, or if imm != 0
    if cnt_reg:
        ops.append(reg_s)
    elif sc != 0:
        ops.append("0x%x" % sc)
    if barmode in ("RED", "SCAN"):                              # source predicate
        pp, pp_not = bits(inst, 89, 87), bits(inst, 90, 90)
        ops.append(pred(pp, pp_not))

    return "%s%s %s" % (guard, mnem, ", ".join(ops))


# (lo64, hi64, expected) — real ptxas output (tests/bar_test.cu)
VECTORS = [
    (0x0000000000007b1d, 0x000fec0000010000, "BAR.SYNC.DEFER_BLOCKING 0x0"),
    (0x0044000000007b1d, 0x000fe20000010000, "BAR.SYNC.DEFER_BLOCKING 0x1, 0x100"),
    (0x0044000000007b1d, 0x000ff00000002000, "BAR.ARV 0x1, 0x100"),
    (0x0000000000007b1d, 0x000fec0000014000, "BAR.RED.POPC.DEFER_BLOCKING 0x0, P0"),
    (0x0000000000007b1d, 0x000fec0000014400, "BAR.RED.AND.DEFER_BLOCKING 0x0, P0"),
]


def run_vectors():
    ok = 0
    for lo, hi, exp in VECTORS:
        got = decode(lo, hi)
        ok += got == exp
        print("%s %-40s (exp %s)" % ("OK " if got == exp else "XX ", got, exp))
    print("\n%d/%d vectors matched" % (ok, len(VECTORS)))


LINE = re.compile(r"/\*([0-9a-f]+)\*/\s+(.*?);\s*/\*\s*([0-9a-fx]+)\s*\*/")
HEX = re.compile(r"/\*\s*([0-9a-fx]+)\s*\*/")


def validate_dump(path):
    lines = open(path).readlines()
    total = ok = 0
    for i, ln in enumerate(lines):
        m = LINE.search(ln)
        if not m or not re.search(r"\bBAR\.", m.group(2)):   # BAR. (exclude MEMBAR/BAR_ARV)
            continue
        text, lo = m.group(2).strip(), int(m.group(3), 16)
        hm = HEX.search(lines[i + 1]) if i + 1 < len(lines) else None
        if not hm:
            continue
        got = decode(lo, int(hm.group(1), 16))
        total += 1
        ok += got == text
        if got != text:
            print("XX got %-38s exp %-38s [%016x]" % (got, text, lo))
    print("%s: %d/%d BAR matched" % (path, ok, total))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            validate_dump(p)
    else:
        run_vectors()
