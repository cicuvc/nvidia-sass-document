#!/usr/bin/env python3
"""SM120 IMMA operand-layout suffix parser/matcher regression."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat  # noqa: E402
from assembler.sass_matcher import MatchError  # noqa: E402
from assembler.sass_parser import parse_sass  # noqa: E402


VALID = (
    "IMMA.16816.U8.U8 {R32,R33,R34,R35}, {R16,R17}.ROW, R20.COL, "
    "{R24,R25,R26,R27}, !UPT;[7:7:{}:1:0]"
)

inst = parse_sass(VALID)[0]
assert inst.operands[1].row == 0 and inst.operands[1].col is None
assert inst.operands[2].col == 1 and inst.operands[2].row is None
assert len(assemble_flat(VALID, arch="sm120")) == 1

for bad in (
    VALID.replace("{R16,R17}.ROW", "{R16,R17}").replace("R20.COL", "R20"),
    VALID.replace("{R16,R17}.ROW", "{R16,R17}.COL").replace(
        "R20.COL", "R20.ROW"),
):
    try:
        assemble_flat(bad, arch="sm120")
    except MatchError:
        pass
    else:
        raise AssertionError(f"invalid IMMA layout suffixes matched: {bad}")

print("=== IMMA .ROW/.COL syntax: ALL PASS ===")
