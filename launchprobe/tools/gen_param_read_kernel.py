#!/usr/bin/env python3
"""gen_param_read_kernel.py <probe_out_va_hex> > /tmp/param_read.bin

Reads c[0x0][0x380..0x3a0] (param base) and stores the raw words to a fixed
UVM address, so the host can see exactly what the SM's constant path returns.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_flat

out_va = int(sys.argv[1], 16)

SRC = f"""
LDCU.64 {{UR4,UR5}}, c[0x0][0x358];[0:7:{{}}:1:0]
LDC.64 {{R0,R1}}, c[0x0][0x380];[1:7:{{}}:1:0]
LDC.64 {{R2,R3}}, c[0x0][0x388];[2:7:{{}}:1:0]
LDC.64 {{R4,R5}}, c[0x0][0x390];[3:7:{{}}:1:0]
LDC.64 {{R6,R7}}, c[0x0][0x398];[4:7:{{}}:1:0]
MOV32I R8, 0x{out_va & 0xFFFFFFFF:x};[5:7:{{}}:5:1]
MOV32I R9, 0x{(out_va >> 32) & 0xFFFFFFFF:x};[5:7:{{}}:5:1]
STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0x0], R0;[5:7:{{0,1}}:1:0]
STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0x4], R1;[5:7:{{0,1}}:1:0]
STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0x8], R2;[5:7:{{0,1,2}}:1:0]
STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0xc], R3;[5:7:{{0,1,2}}:1:0]
STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0x10], R4;[5:7:{{0,1,3}}:1:0]
STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0x14], R5;[5:7:{{0,1,3}}:1:0]
STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0x18], R6;[5:7:{{0,1,4}}:1:0]
STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0x1c], R7;[5:7:{{0,1,4}}:1:0]
EXIT;[7:7:{{}}:5:0]
"""

words = assemble_flat(SRC)
out = bytearray()
for lo, hi in words:
    out += lo.to_bytes(8, "little") + hi.to_bytes(8, "little")
sys.stderr.write(f"[gen] {len(words)} instructions, {len(out)} bytes\n")
sys.stdout.buffer.write(bytes(out))
