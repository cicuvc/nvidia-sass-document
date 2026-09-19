#!/usr/bin/env python3
"""sm103 assembler regression for the fused tcgen05.ld.red opcode."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from assembler import assemble_flat, assemble_kernel  # noqa: E402


# Vectors captured from tests/tcgen05_ld_red.cu, compiled with CUDA 13.1 for
# sm_103a.  Explicit groups are required by the hand assembler even though
# cuobjdump prints only their base register.
CASES = (
    ("LDTM.STAT.x2.MAX R7, {R4,R5}, tmem[UR4];[0:7:{0}:1:0]",
     0x00000004070475EE, 0x001E2200080C0000),
    ("LDTM.STAT.x4.MIN.S32 R9, {R4,R5,R6,R7}, tmem[UR4];"
     "[0:7:{0}:1:0]",
     0x00000004090475EE, 0x001E220008140009),
    ("LDTM.STAT.x2.MAXABS.F32.NAN R7, {R4,R5}, tmem[UR4];"
     "[0:7:{0}:1:0]",
     0x00000004070475EE, 0x001E2200080C0016),
    # One PTX .16x32bx2 operation becomes a lane-0..15 half and a lane-16..31
    # half.  Only the second instruction claims the completion scoreboard.
    ("LDTM.STAT.16dp32bit_t0_t15.x4.MIN R9, {R4,R5,R6,R7}, "
     "tmem[UR4];[7:7:{0}:1:0]",
     0x00000004090475EE, 0x001FE20008900008),
    ("LDTM.STAT.16dp32bit_t16_t31.x4.MIN R9, {R4,R5,R6,R7}, "
     "tmem[UR4+0x10];[0:7:{}:1:0]",
     0x00001004090475EE, 0x000E220008920008),
)

for source, want_lo, want_hi in CASES:
    got = assemble_flat(source, arch="sm103")
    assert got == [(want_lo, want_hi)], (
        source, [(hex(lo), hex(hi)) for lo, hi in got],
        (hex(want_lo), hex(want_hi)))

# The real-hardware semantics kernel must remain a wholly assembler-native
# sm103a cubin containing the expected four full-warp STAT operations and the
# two halves of the split operation.
semantic_source = Path(__file__).with_name(
    "tcgen05_ldred_semantics_sm103.sass").read_text()
semantic = assemble_kernel(
    semantic_source, arch="sm103a", check_deps=False)
semantic_opcodes = [(((hi >> 27) & 1) << 12) | (lo & 0xfff)
                    for lo, hi in semantic.encoded]
assert semantic_opcodes.count(0x15ee) == 6
assert semantic.params == [(0, 0x380, 8)]

print("tcgen05.ld.red / LDTM.STAT sm103 encodings: PASS")
