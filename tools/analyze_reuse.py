#!/usr/bin/env python3
"""Analyse ptxas `.reuse` usage in cuobjdump SASS against the SM120 reuse-cache
model (notes/sm90/arch/control_codes.md runtime semantics):

  1. RMW hazard: is a `.reuse` register ever ALSO a destination of the same
     instruction?  (Our experiments show this serves stale data -> ptxas
     must never emit it.)
  2. Consumer contract: does the immediately-next instruction read the reused
     register in the SAME operand slot (position index among operands)?
     (A miss just falls back to RF silently, so this is the "expected" rate.)
  3. Any-next-register read (loose): next instruction reads the reused reg in
     any slot.
"""
import re
import sys
from collections import Counter

REG = re.compile(r"\bR(\d+|Z)\b")
DEST_MNEM = None

def regnum(tok):
    m = REG.search(tok)
    if not m:
        return None
    return 255 if m.group(1) == "Z" else int(m.group(1))

def split_operands(text):
    """Split instruction body (after mnemonic) into operand strings."""
    parts = []
    depth = 0
    cur = ""
    for ch in text:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts

def is_reuse(tok):
    return ".reuse" in tok

def strip_reuse(tok):
    return tok.replace(".reuse", "")

# Instructions that write a register pair/quad in Rd.  NOTE: SHF.*.U64/S64
# and HADD2/HFMA2/HMUL2 (fp16x2) are NOT pair writers — Rd stays a single
# 32-bit register (their .U64/.F32 etc. are width/sel modifiers).
PAIR_MNEM = re.compile(
    r"\.WIDE|\.128\b|\.v2\b|\.v4\b|"
    r"DADD|DMUL|DFMA|D2F|F2D|"                       # double precision (R64 pair)
    r"(?:LD|ST)[A-Za-z0-9.]*\.(?:64|128)\b|"         # memory .64/.128
    r"F2I\.64|I2F\.64|F2F\.64|"                      # 64-bit converts
    r"R2UR\.64|UR2R\.64|MOV\.64\b|MOV64I|I2UR\.64|UR2I\.64"
)

def parse_line(line):
    """Return (addr, mnemonic, operands, reuse_ops) or None."""
    m = re.match(r"\s*/\*([0-9a-f]+)\*/\s+(.*?)(?:\s*;\s*|\s*/\*)", line)
    if not m:
        return None
    addr = int(m.group(1), 16)
    body = m.group(2).strip()
    # strip leading predicate @Px
    body = re.sub(r"^@[!]?P[0-6T]+\s*", "", body)
    if not body or body.startswith("//"):
        return None
    toks = body.split(None, 1)
    mnemonic = toks[0].upper()
    if len(toks) < 2:
        return None
    ops = split_operands(toks[1])
    reuse_ops = [(i, regnum(strip_reuse(o))) for i, o in enumerate(ops)
                 if is_reuse(o) and regnum(strip_reuse(o)) is not None]
    return addr, mnemonic, ops, reuse_ops

def dest_regs(ops, mnemonic):
    """Dest GPRs (Rd, and Rd+1 for wide/64 forms). Also predicate dests."""
    dests = []
    if not ops:
        return dests
    r = regnum(ops[0])
    if r is not None:
        dests.append(r)
        if PAIR_MNEM.search(mnemonic):
            dests.append(r + 1)
    return dests

def main(path):
    reuse_total = 0
    rmw = 0
    rmw_examples = []
    next_same_slot = 0
    next_same_reg_any = 0
    next_not_read = 0
    next_missing = 0
    prev = None  # (addr, mnemonic, ops, reuse_ops)

    with open(path) as f:
        for line in f:
            s = line.strip()
            # hi64 continuation line ("/* 0x... */") or blank -> not an
            # instruction; keep prev so adjacency survives.
            if s.startswith("/* 0x") or s == "":
                continue
            if "Function :" in line or ".target" in line or "code for sm_" in line:
                prev = None
                continue
            parsed = parse_line(line)
            if parsed is None:
                prev = None
                continue
            addr, mnemonic, ops, reuse_ops = parsed
            if prev is not None:
                paddr, pmn, pops, preuse = prev
                pdests = dest_regs(pops, pmn)
                for (pi, pr) in preuse:
                    # RMW check: reused register == dest of the producer
                    if pr in pdests:
                        rmw += 1
                        if len(rmw_examples) < 8:
                            rmw_examples.append((paddr, pmn, pops, pi, pr))
                    # consumer contract: this instruction (current) is the
                    # producer's immediate successor.
                    if pi < len(ops):
                        cr = regnum(strip_reuse(ops[pi]))
                        if cr == pr:
                            next_same_slot += 1
                    if any(regnum(o) == pr for o in ops):
                        next_same_reg_any += 1
                    else:
                        next_not_read += 1
                reuse_total += len(preuse)
            prev = parsed
        # flush tail reuse (no successor)
        if prev is not None:
            reuse_total += len(prev[3])
            for _pi, _pr in prev[3]:
                next_missing += 1

    print(f"file: {path}")
    print(f"reuse operands total: {reuse_total}")
    print(f"  RMW hazard (reused reg == dest): {rmw}")
    if rmw_examples:
        for a, m, o, pi, pr in rmw_examples:
            print(f"    @{a:#06x} {m} {' '.join(o)} (reuse slot {pi} = R{pr if pr<256 else 'Z'})")
    print(f"  next-instr same slot + same reg: {next_same_slot} "
          f"({100*next_same_slot/max(reuse_total,1):.1f}%)")
    print(f"  next-instr reads reg (any slot):  {next_same_reg_any} "
          f"({100*next_same_reg_any/max(reuse_total,1):.1f}%)")
    print(f"  next-instr does NOT read reg:     {next_not_read}")
    print(f"  no successor (tail):              {next_missing}")

if __name__ == "__main__":
    main(sys.argv[1])
