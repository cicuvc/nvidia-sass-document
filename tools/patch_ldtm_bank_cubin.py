#!/usr/bin/env python3
"""Rewrite an nvcc LDTM.x1 kernel's physical destinations by RF parity.

This preserves nvcc's complete sm100 TMEM metadata/guardrail/atexit machinery.
All layouts reuse six registers at the same distance, so WAW pressure is held
constant; only destination-bank selection changes.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sassdbg.cubin import load_kernel  # noqa: E402


REGS = {
    "even": (8, 10, 12, 14, 16, 18),
    "odd": (7, 9, 11, 13, 15, 17),
    "alternating": (8, 9, 10, 11, 12, 13),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("layout", choices=tuple(REGS))
    parser.add_argument("output", type=Path)
    parser.add_argument("--function", default="ldtm_x1")
    ns = parser.parse_args()

    data = bytearray(ns.input.read_bytes())
    kernel = load_kernel(str(ns.input), ns.function)
    regs = REGS[ns.layout]
    patched = 0
    for i, (lo, _hi) in enumerate(kernel.words):
        # LDTM opcode: bit 91 plus low opcode bits; the .x1 function contains
        # no other member of the 0x19ee opcode family.
        if lo & 0xfff != 0x9ee:
            continue
        reg = regs[patched % len(regs)]
        lo = (lo & ~(0xff << 16)) | (reg << 16)
        struct.pack_into("<Q", data, kernel.file_off + i * 16, lo)
        patched += 1
    if not patched:
        raise RuntimeError(f"no LDTM instructions found in {ns.function}")
    ns.output.write_bytes(data)
    print(f"{ns.layout}: patched {patched} LDTM destinations -> {ns.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
