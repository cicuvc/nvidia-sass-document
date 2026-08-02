#!/usr/bin/env python3
"""Migrate hand-written SASS to explicit register groups {Ra,Rb}.

Rewrites the legacy implicit-pair syntax used in the assembler test kernels:
    LDC.64 R6, ...        ->  LDC.64 {R6,R7}, ...
    LDCU.64 UR4, ...      ->  LDCU.64 {UR4,UR5}, ...
    desc[UR4]             ->  desc[{UR4,UR5}]
    [R6.64+0x0]           ->  [{R6,R7}+0x0]
    <mnemonic>.64 R2      ->  {R2,R3}  (64-bit dest/src single-reg)
    <mnemonic>.128 R2     ->  {R2,R3,R4,R5}
When a rewrite lands inside a Python f-string, the braces are doubled.

Usage: python3 migrate_groups.py FILE...  (in-place)
"""
import re
import sys


def is_fstring_line(line: str) -> bool:
    """True if the line contains an f-prefixed string literal."""
    m = re.search(r"\bf(\"|')", line)
    return bool(m)


def esc(line_is_f: bool, group: str) -> str:
    """Wrap a {Ra,Rb} group, doubling braces inside an f-string."""
    if line_is_f:
        return group.replace("{", "{{").replace("}", "}}")
    return group


def migrate_line(line: str) -> str:
    f = is_fstring_line(line)
    out = line

    # 1. memory address [Rx.64+off]  ->  [{Rx,Rx+1}+off]
    def addr_repl(m):
        n = int(m.group(1))
        return esc(f, "{" + ",".join(f"R{r}" for r in range(n, n + 2)) + "}")
    out = re.sub(r"\[R(\d+)\.64", lambda m: "[" + addr_repl(m), out)

    # 2. desc[URx] -> desc[{URx,URx+1}]
    def desc_repl(m):
        n = int(m.group(1))
        return "desc[" + esc(f, "{" + ",".join(f"UR{r}" for r in range(n, n + 2)) + "}") + "]"
    out = re.sub(r"desc\[UR(\d+)\]", desc_repl, out)

    # 3. mnemonic-level .64/.128 with a single-register operand -> group.
    #    Only when the register token is followed by a comma (dest or src),
    #    and is NOT already part of a group or an address.
    def mnem_repl(m):
        prefix = m.group(1) + " "    # e.g. "LDCU.64 " or "MOV.64 "
        n = int(m.group(2)[1:])
        width = 128 if prefix.rstrip().endswith(".128") else 64
        count = width // 32
        regs = ", ".join(f"R{r}" for r in range(n, n + count))
        return prefix + esc(f, "{" + regs + "}")
    out = re.sub(r"\b(LDCU\.64|LDC\.64|ULDC\.64|MOV\.64|STG\.64|STL\.64|STS\.64|LDG\.64|LDS\.64|LDL\.64|MOV\.128|LDG\.128|LDS\.128|STG\.128|STS\.128) (R\d+)(?=[,;])",
                 mnem_repl, out)

    # 4. uniform-register mnemonic dest: LDCU.64 UR4 (handled above by same
    #    regex? no - UR needs separate). LDCU.64 UR4,
    def umnem_repl(m):
        prefix = m.group(1) + " "
        n = int(m.group(2)[2:])
        regs = ", ".join(f"UR{r}" for r in range(n, n + 2))
        return prefix + esc(f, "{" + regs + "}")
    out = re.sub(r"\b(LDCU\.64|ULDC\.64|UMOV\.64) (UR\d+)(?=[,;])", umnem_repl, out)

    return out


def main() -> int:
    changed = 0
    for path in sys.argv[1:]:
        src = open(path).read()
        new = "\n".join(migrate_line(l) for l in src.split("\n"))
        if new != src:
            open(path, "w").write(new)
            changed += 1
            print(f"migrated {path}")
    print(f"{changed} file(s) rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
