#!/usr/bin/env python3
"""Distinguish implicit SM120 HMMA Ra reuse from ordinary RAW visibility."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


OLD = [0x3F803F80] * 4
NEW = [0x41200000, 0x41300000, 0x41400000, 0x41500000]


def source(mode: str, gap: int = 0) -> str:
    vals = {
        20: 0, 21: 0,
        24: NEW[0], 25: NEW[1], 26: NEW[2], 27: NEW[3],
        28: 0x3F803F80, 29: 0x3F803F80,
        32: 0, 33: 0, 34: 0, 35: 0,
    }
    for i, val in enumerate(NEW if mode == "new" else OLD):
        vals[16 + i] = val
    lines = [
        "#fn hradefault(out<8>) {",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
    ]
    for reg, val in sorted(vals.items()):
        lines.append(f"    MOV32I R{reg}, 0x{val:08x};[7:7:{{}}:5:1]")
    if mode == "hazard":
        # B=0 makes D=C, overwriting the instruction's own Ra group.  If Ra
        # were implicitly reused, the following HMMA would see OLD instead.
        lines.append(
            "    HMMA.16816.F32.BF16 {R16,R17,R18,R19}, "
            "{R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27};"
            "[7:7:{}:1:0]")
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
    lines.append(
        "    HMMA.16816.F32.BF16 {R40,R41,R42,R43}, "
        "{R16,R17,R18,R19}, {R28,R29}, {R32,R33,R34,R35};"
        "[7:7:{}:1:0]")
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(20)]
    lines += [
        "    STG.E.128.STRONG.GPU [{R2,R3}], {R40,R41,R42,R43};"
        "[7:1:{1}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(mode: str, gap: int = 0) -> tuple[int, int, int, int]:
    reset_context()
    mod = CudaModule(assemble(source(mode, gap), check_deps=False))
    out = mod.devmem_alloc(512)
    try:
        mod.device_write(out, bytes(512))
        mod.launch("hradefault", grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        return struct.unpack_from("<4I", mod.device_read(out, 512), 0)
    finally:
        mod.devmem_free(out)


old = run("old")
new = run("new")
print("old Ra reference:", [f"0x{x:08x}" for x in old])
print("new Ra reference:", [f"0x{x:08x}" for x in new])
assert old == (0x41800000,) * 4
assert new == (0x42B00000, 0x42B00000, 0x42C00000, 0x42C00000)
rows = []
for gap in range(21):
    got = run("hazard", gap)
    rows.append(got)
    kind = "OLD" if got == old else "NEW" if got == new else "MIX"
    print(f"Rd==Ra gap={gap:2d} {kind}:", [f"0x{x:08x}" for x in got])
assert rows[-1] == new, "large-gap HMMA consumer must observe the new Ra"
print("=== HMMA Ra implicit-reuse / RAW-visibility sweep: ALL PASS ===")
