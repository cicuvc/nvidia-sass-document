#!/usr/bin/env python3
"""SM120 dense-HMMA Rb reuse-cache semantics and RMW hazard."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


def source(reuse: int) -> str:
    vals = {
        16: 0, 17: 0, 18: 0, 19: 0,
        20: 0x3F803F80, 21: 0x3F803F80,
        24: 0x41200000, 25: 0x41300000,
        26: 0x41400000, 27: 0x41500000,
        28: 0, 29: 0, 30: 0, 31: 0,
        32: 0x3F803F80, 33: 0x3F803F80,
        34: 0x3F803F80, 35: 0x3F803F80,
    }
    lines = [
        "#fn hreuse(out<8>) {",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
    ]
    for reg, val in vals.items():
        lines.append(f"    MOV32I R{reg}, 0x{val:08x};[7:7:{{}}:5:1]")
    # A=0 makes the first result equal C.  Its destination overwrites its own
    # B source R20/R21.  The next HMMA distinguishes a fresh RF read from the
    # old value retained by Rb.reuse.
    lines += [
        "    HMMA.16816.F32.BF16 {R20,R21,R22,R23}, "
        "{R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27};"
        f"[7:7:{{}}:1:0:{reuse}]",
        "    HMMA.16816.F32.BF16 {R40,R41,R42,R43}, "
        "{R32,R33,R34,R35}, {R20,R21}, {R28,R29,R30,R31};"
        "[7:7:{}:1:0]",
    ]
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(20)]
    lines += [
        "    STG.E.128.STRONG.GPU [{R2,R3}], {R40,R41,R42,R43};"
        "[7:1:{1}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(reuse: int) -> tuple[int, int, int, int]:
    reset_context()
    mod = CudaModule(assemble(source(reuse), check_deps=False))
    out = mod.devmem_alloc(512)
    try:
        mod.device_write(out, bytes(512))
        mod.launch("hreuse", grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        return struct.unpack_from("<4I", mod.device_read(out, 512), 0)
    finally:
        mod.devmem_free(out)


plain = assemble_flat(
    "HMMA.16816.F32.BF16 {R40,R41,R42,R43}, {R16,R17,R18,R19}, "
    "{R20,R21}, {R24,R25,R26,R27};[7:7:{}:1:0:0]")[0]
reuse_b = assemble_flat(
    "HMMA.16816.F32.BF16 {R40,R41,R42,R43}, {R16,R17,R18,R19}, "
    "{R20,R21}, {R24,R25,R26,R27};[7:7:{}:1:0:2]")[0]
assert plain != reuse_b, "Rb reuse must change the HMMA control word"

fresh = run(0)
cached = run(2)
expect_fresh = (0x42A80000,) * 4
expect_cached = (0x41800000,) * 4
print("HMMA no-reuse:", [f"0x{x:08x}" for x in fresh])
print("HMMA Rb.reuse:", [f"0x{x:08x}" for x in cached])
assert fresh == expect_fresh, (fresh, expect_fresh)
assert cached == expect_cached, (cached, expect_cached)
print("=== HMMA Rb reuse-cache semantics: ALL PASS ===")
