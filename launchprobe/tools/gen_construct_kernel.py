#!/usr/bin/env python3
"""gen_construct_kernel.py <out_va_hex> <value_hex> > /tmp/construct_kernel.bin

Hand-built minimal sm_120 kernel for the from-scratch launch:
loads the global descriptor from c[0x0][0x358], stores <value> to a
fixed device address (<out_va>), exits. No params, no LDC.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat

out_va = int(sys.argv[1], 16)
value = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0xDEADBEEF

SRC = f"""
LDCU.64 {{UR4,UR5}}, c[0x0][0x358];[0:7:{{}}:1:0]
MOV32I R0, 0x{out_va & 0xFFFFFFFF:x};[7:7:{{}}:5:1]
MOV32I R1, 0x{(out_va >> 32) & 0xFFFFFFFF:x};[7:7:{{}}:5:1]
MOV32I R2, 0x{value:x};[7:7:{{}}:5:1]
STG.E desc[{{UR4,UR5}}][{{R0,R1}}+0x0], R2;[0:1:{{0,1}}:1:0]
EXIT;[7:7:{{}}:5:0]
"""

words = assemble_flat(SRC)
out = bytearray()
for lo, hi in words:
    out += lo.to_bytes(8, "little") + hi.to_bytes(8, "little")
sys.stderr.write(f"[gen] {len(words)} instructions, {len(out)} bytes\n")
sys.stdout.buffer.write(bytes(out))
