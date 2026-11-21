#!/usr/bin/env python3
"""Round-trip sm100 UTCHMMA collectors and the TMEM A source."""

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
    (".WS", "UTCHMMA.WS "),
    (".WS.B_KEEP", "UTCHMMA.WS.B_KEEP "),
    (".WS.B_REUSE.B_KEEP.BUFFER3", "UTCHMMA.WS.B_REUSE.B_KEEP.BUFFER3 "),
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

# nvcc 13.1 sm_100a, tests/utchmma_test.cu: independent A-from-TMEM vector.
# TMEMA used to be absent from the matcher's composite operand types.
tmem_a = (
    "UTCHMMA.1CTA tmem[UR7], gdesc[{UR8,UR9}], tmem[UR6], "
    "tmem[UR4], idesc[{UR5,UR6}], URZ, UPT;[7:4:{0,1,2,3,4}:12:1]"
)
assert assemble_flat(tmem_a, arch="sm100a") == [
    (0x00ff0408070079ea, 0x01f9d8000b800006)
]
try:
    assemble_flat(tmem_a.replace("tmem[UR7]", "tmem[UR7+0x8]"), arch="sm100a")
except (MatchError, SyntaxError, ValueError):
    pass
else:
    raise AssertionError("UTCHMMA silently discarded a TMEM A immediate")

# TMEM composites must not consume collector modifier defaults before matching.
for mods, bitmask in ((".A_KEEP",1<<20),(".A_REUSE",1<<22),(".A_KEEP.A_REUSE",(1<<20)|(1<<22))):
    plain=assemble_flat(tmem_a,arch="sm100a")[0]
    changed=assemble_flat(tmem_a.replace("UTCHMMA.1CTA", "UTCHMMA.1CTA"+mods),arch="sm100a")[0]
    assert changed==(plain[0],plain[1]|bitmask), (mods,changed,plain)

print("UTCHMMA collector modifier and TMEM A round-trip: PASS")
