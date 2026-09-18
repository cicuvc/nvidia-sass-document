#!/usr/bin/env python3
"""Round-trip the sm100 UTCHMMA collector-A operand modifiers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat
from assembler.sass_matcher import MatchError
from tools.decode_utchmma import decode_utchmma


BASE = (
    "UTCHMMA.1CTA{mods} gdesc[{{UR20,UR21}}], "
    "gdesc[{{UR22,UR23}}], tmem[UR10], tmem[UR14], "
    "idesc[{{UR15,UR16}}], URZ, UPT;[7:0:{{0}}:12:1]"
)

cases = [
    ("", "UTCHMMA "),
    (".A_KEEP", "UTCHMMA.A_KEEP "),
    (".A_REUSE", "UTCHMMA.A_REUSE "),
    (".A_REUSE.A_KEEP", "UTCHMMA.A_REUSE.A_KEEP "),
]

for mods, prefix in cases:
    lo, hi = assemble_flat(BASE.format(mods=mods), arch="sm100a")[0]
    got = decode_utchmma(lo, hi)
    assert got is not None and got.startswith(prefix), (mods, got)

# UTCHMMA's TMEM operands have no immediate field.  The parser understands
# tmem[UR+imm] for LDTM/STTM, but the matcher must reject it here instead of
# silently assembling the same bits as tmem[UR].
try:
    assemble_flat(BASE.format(mods="").replace(
        "tmem[UR10]", "tmem[UR10+0x80]", 1), arch="sm100a")
except (MatchError, SyntaxError, ValueError):
    pass
else:
    raise AssertionError("UTCHMMA silently discarded a TMEM immediate")

print("UTCHMMA collector modifier round-trip: PASS")
