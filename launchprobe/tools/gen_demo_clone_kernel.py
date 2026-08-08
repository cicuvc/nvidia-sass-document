#!/usr/bin/env python3
"""gen_demo_clone_kernel.py > /tmp/demo_clone.bin
Repo-assembler clone of nvcc's demo kernel (same instruction selection).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat

SRC = """
LDC R1, c[0x0][0x37c];[7:7:{}:5:1]
S2R R7, SR_TID.X;[7:7:{}:5:1]
LDC.64 {R4,R5}, c[0x0][0x388];[0:7:{}:1:0]
LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]
LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:1:0]
IMAD R5, R5, R4, R7;[7:7:{0}:1:0]
IMAD.WIDE.U32 {R2,R3}, R7, 0x4, {R2,R3};[7:7:{2}:1:0]
STG.E desc[{UR4,UR5}][{R2,R3}+0x0], R5;[0:1:{1}:1:0]
EXIT;[7:7:{}:5:0]
"""

words = assemble_flat(SRC)
out = bytearray()
for lo, hi in words:
    out += lo.to_bytes(8, "little") + hi.to_bytes(8, "little")
sys.stderr.write(f"[gen] {len(words)} instructions, {len(out)} bytes\n")
sys.stdout.buffer.write(bytes(out))
