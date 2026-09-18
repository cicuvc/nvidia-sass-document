#!/usr/bin/env python3
"""sm100a assembler regression for TMEM load/store/copy operands."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from assembler import assemble_flat  # noqa: E402


# Scheduling brackets reproduce the scoreboard fields in the nvcc vectors;
# wide register operands are deliberately explicit in assembler source.
CASES = (
    ("STTM tmem[UR6], R4;[7:0:{2}:1:0]",
     0x00000004000079ED, 0x0041E20008040006),
    ("STTM.x2 tmem[UR6], {R4,R5};[7:0:{3}:1:0]",
     0x00000004000079ED, 0x0081E200080C0006),
    ("STTM.16dp32bit_t16_t31.x2 tmem[UR6+0x10], {R4,R5};"
     "[7:0:{}:1:0]",
     0x00001004000079ED, 0x0001E200088A0006),
    ("LDTM R0, tmem[UR6];[0:7:{0}:1:0]",
     0x00000006000079EE, 0x001E220008040000),
    ("LDTM.x2 {R24,R25}, tmem[UR6];[1:7:{}:1:0]",
     0x00000006001879EE, 0x000E6200080C0000),
    ("LDTM.16dp32bit_t16_t31.x2 {R16,R17}, tmem[UR6+0x10];"
     "[5:7:{}:1:0]",
     0x00001006001079EE, 0x000F6200088A0000),
    ("UTCCP.T.S tmem[UR6], gdesc[{UR8,UR9}];[7:0:{0}:12:1]",
     0x00000008060079E7, 0x0011D80008000000),
    ("UTCCP.T.S.2x64dp128bit_lw02_lw13 "
     "tmem[UR6], gdesc[{UR8,UR9}];[7:0:{0}:12:1]",
     0x00000008060079E7, 0x0011D80009000000),
    ("UTCCP.T.S.2x64dp128bit_lw01_lw23 "
     "tmem[UR6], gdesc[{UR8,UR9}];[7:0:{0}:12:1]",
     0x00000008060079E7, 0x0011D80009080000),
    ("UTCCP.T.S.4x32dp128bit "
     "tmem[UR6], gdesc[{UR8,UR9}];[7:0:{0}:12:1]",
     0x00000008060079E7, 0x0011D80009100000),
)

for source, want_lo, want_hi in CASES:
    got = assemble_flat(source, arch="sm100a")
    assert got == [(want_lo, want_hi)], (
        source, [(hex(lo), hex(hi)) for lo, hi in got],
        (hex(want_lo), hex(want_hi)))

print("tcgen05 LDTM/STTM/UTCCP sm100a encodings: PASS")
