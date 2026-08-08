#!/usr/bin/env python3
"""gen_probe_regs_kernel.py > /tmp/probe_regs.bin

Debug kernel: dumps every register the nvcc demo prologue touches into
out[0..9] (R2/R3 param ptr, R4/R5 params, R7 tid, R1 stack base,
R8/R9 = IMAD.WIDE result). Correct scoreboard discipline throughout:
S2R/LDC are variable-latency and every consumer waits via req={}.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_kernel

SRC = """#fn k() {
    LDC R1, c[0x0][0x37c];[0:7:{}:1:0]
    LDC.64 {R2,R3}, c[0x0][0x380];[1:7:{}:1:0]
    LDC.64 {R4,R5}, c[0x0][0x388];[2:7:{}:1:0]
    LDCU.64 {UR4,UR5}, c[0x0][0x358];[3:7:{}:1:0]
    S2R R7, SR_TID.X;[4:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x0], R2;[5:7:{1,3}:1:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x4], R3;[5:7:{1,3}:1:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x8], R4;[5:7:{1,2,3}:1:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0xc], R5;[5:7:{1,2,3}:1:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x10], R7;[5:7:{1,3,4}:1:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x14], R1;[5:7:{0,1,3}:1:0]
    IMAD.WIDE.U32 {R8,R9}, R7, 0x4, {R2,R3};[7:7:{1,4}:5:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x18], R8;[5:7:{1,3}:7:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x1c], R9;[5:7:{1,3}:7:0]
    EXIT;[7:7:{}:5:0]
}"""

r = assemble_kernel(SRC, check_deps=True, strict_deps=True)
out = bytearray()
for lo, hi in r.encoded:
    out += lo.to_bytes(8, "little") + hi.to_bytes(8, "little")
sys.stderr.write(f"[gen] {len(r.encoded)} instructions, {len(out)} bytes\n")
sys.stdout.buffer.write(bytes(out))
