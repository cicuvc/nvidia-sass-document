#!/usr/bin/env python3
"""Functional tests for both directions of MOV's uniform-indexed GPR mode."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


SOURCE = """#fn midx(out<8>) {
    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
    UMOV UR4, 0x28;[7:7:{}:5:1]
    UMOV UR5, 0x2c;[7:7:{}:5:1]
    MOV32I R16, 0x12345678;[7:7:{}:5:1]
    MOV32I R40, 0x89abcdef;[7:7:{}:5:1]
    MOV32I R44, 0;[7:7:{}:5:1]
    MOV R50, R[UR4];[7:7:{}:5:1]
    MOV R[UR5], R16;[7:7:{}:5:1]
    MOV R[UR4], 0x76543210;[7:7:{}:5:1]
    STG.E.STRONG.GPU [{R2,R3}], R50;[7:1:{1}:8:0]
    STG.E.STRONG.GPU [{R2,R3}+4], R44;[7:1:{}:8:0]
    STG.E.STRONG.GPU [{R2,R3}+8], R40;[7:1:{}:8:0]
    EXIT;[7:7:{}:5:0]
}"""

reset_context()
mod = CudaModule(assemble(SOURCE, check_deps=False))
out = mod.devmem_alloc(32)
try:
    mod.device_write(out, bytes(32))
    mod.launch("midx", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    got = struct.unpack("<3I", mod.device_read(out, 12))
finally:
    mod.devmem_free(out)

want = (0x89ABCDEF, 0x12345678, 0x76543210)
print("got: ", [f"0x{x:08x}" for x in got])
print("want:", [f"0x{x:08x}" for x in want])
assert got == want, (got, want)
print("=== MOV indexedRF functional test: ALL PASS ===")
