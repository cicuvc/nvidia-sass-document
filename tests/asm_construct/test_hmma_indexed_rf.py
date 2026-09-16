#!/usr/bin/env python3
"""Functional smoke test for SM120 HMMA's uniform-indexed accumulator."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


def kernel(indexed: bool) -> str:
    acc = "R[UR4]" if indexed else "{R40,R41,R42,R43}"
    return f"""#fn hidx(out<8>) {{
    LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
    UMOV UR4, 0x28;[7:7:{{}}:5:1]
    MOV32I R16, 0x3f803f80;[7:7:{{}}:5:1]
    MOV32I R17, 0x3f803f80;[7:7:{{}}:5:1]
    MOV32I R18, 0x3f803f80;[7:7:{{}}:5:1]
    MOV32I R19, 0x3f803f80;[7:7:{{}}:5:1]
    MOV32I R20, 0x3f803f80;[7:7:{{}}:5:1]
    MOV32I R21, 0x3f803f80;[7:7:{{}}:5:1]
    MOV32I R40, 0x41200000;[7:7:{{}}:5:1]
    MOV32I R41, 0x41300000;[7:7:{{}}:5:1]
    MOV32I R42, 0x41400000;[7:7:{{}}:5:1]
    MOV32I R43, 0x41500000;[7:7:{{}}:5:1]
    HMMA.16816.F32.BF16 {acc}, {{R16,R17,R18,R19}}, {{R20,R21}}, {acc}, UPT;[7:7:{{}}:1:0]
    NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1]
    NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1]
    NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1]
    NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1] NOP;[7:7:{{}}:5:1]
    STG.E.128.STRONG.GPU [{{R2,R3}}], {{R40,R41,R42,R43}};[7:1:{{1}}:8:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(indexed: bool) -> tuple[float, ...]:
    reset_context()
    mod = CudaModule(assemble(kernel(indexed), check_deps=False))
    out = mod.devmem_alloc(64)
    try:
        mod.device_write(out, bytes(64))
        mod.launch("hidx", grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        return struct.unpack("<4f", mod.device_read(out, 16))
    finally:
        mod.devmem_free(out)


plain = assemble_flat(
    "HMMA.16816.F32.BF16 {R40,R41,R42,R43}, {R16,R17,R18,R19}, "
    "{R20,R21}, {R40,R41,R42,R43}, UPT;[7:7:{}:1:0]")[0]
indexed = assemble_flat(
    "HMMA.16816.F32.BF16 R[UR4], {R16,R17,R18,R19}, "
    "{R20,R21}, R[UR4], UPT;[7:7:{}:1:0]")[0]
assert plain != indexed
assert indexed[0] & 0xfff == 0xe79

ref = run(False)
got = run(True)
print("fixed:  ", ref)
print("indexed:", got)
assert ref == (26.0, 27.0, 28.0, 29.0), ref
assert got == ref, (got, ref)
print("=== HMMA indexedRF functional test: ALL PASS ===")
