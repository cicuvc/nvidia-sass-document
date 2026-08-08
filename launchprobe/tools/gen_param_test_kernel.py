#!/usr/bin/env python3
"""gen_param_test_kernel.py > /tmp/param_test_kernel.bin

Hand kernel exercising the param/const-bank path like nvcc's demo prologue:
  R2:R3 = c[0x0][0x380] (out ptr), R4:R5 = c[0x0][0x388] (a|b),
  UR4:UR5 = c[0x0][0x358] (desc); then out[0]=a, out[1]=b, out[2]=tid, out[3]=0xdeadbeef.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat

SRC = """
LDCU.64 {UR4,UR5}, c[0x0][0x358];[0:7:{}:1:0]
LDC.64 {R2,R3}, c[0x0][0x380];[1:7:{}:1:0]
LDC.64 {R4,R5}, c[0x0][0x388];[2:7:{}:1:0]
S2R R7, SR_TID.X;[7:7:{}:5:1]
STG.E desc[{UR4,UR5}][{R2,R3}+0x0], R4;[3:7:{0,1,2}:1:0]
STG.E desc[{UR4,UR5}][{R2,R3}+0x4], R5;[4:7:{0,1,2}:1:0]
STG.E desc[{UR4,UR5}][{R2,R3}+0x8], R7;[5:7:{0,1,2}:1:0]
MOV32I R6, 0xdeadbeef;[7:7:{}:5:1]
STG.E desc[{UR4,UR5}][{R2,R3}+0xc], R6;[0:1:{0,1,2}:1:0]
EXIT;[7:7:{}:5:0]
"""

words = assemble_flat(SRC)
out = bytearray()
for lo, hi in words:
    out += lo.to_bytes(8, "little") + hi.to_bytes(8, "little")
sys.stderr.write(f"[gen] {len(words)} instructions, {len(out)} bytes\n")
sys.stdout.buffer.write(bytes(out))
