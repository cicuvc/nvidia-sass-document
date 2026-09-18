#!/usr/bin/env python3
"""Patch an nvcc TMEM kernel with a clean fixed-pipe writeback burst.

The input is ``rf_same_p0`` from ``tests/tcgen05_ldtm_fixed_rf_conflict.cu``.
Keeping nvcc's ELF avoids losing the TMEM allocator/capmerc metadata.  Only
the equal-sized contender basic block is replaced.  ``--phase`` inserts zero
to thirteen issue slots before the burst while preserving block length.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import assemble_flat  # noqa: E402
from sassdbg.cubin import load_kernel  # noqa: E402


FUNCTION = "rf_same_p0"
BLOCK_BEGIN = 0x420
BLOCK_END = 0x580
BLOCK_WORDS = (BLOCK_END - BLOCK_BEGIN) // 16


def encoded_block(active: bool, phase: int) -> list[tuple[int, int]]:
    if not 0 <= phase <= 13:
        raise ValueError("phase must be in [0, 13]")
    ops = ["NOP;[7:7:{}:1:0]"] * phase
    if active:
        ops += [
            f"FFMA R{8 + i}, R2, R3, 0f3f400000;"
            f"[7:7:{{}}:{5 if i == 7 else 1}:{1 if i == 7 else 0}]"
            for i in range(8)
        ]
    else:
        ops += ["NOP;[7:7:{}:1:1]"] * 7
        ops += ["NOP;[7:7:{}:5:1]"]
    # The original [0x420,0x580) block has 22 instruction slots.  R4 is
    # already the host-visible contender sink; its value is irrelevant.
    ops += ["NOP;[7:7:{}:1:0]"] * (BLOCK_WORDS - len(ops))
    assert len(ops) == BLOCK_WORDS
    return assemble_flat("\n".join(ops), arch="sm100a")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--target", choices=("same", "different"),
                    default="same")
    ap.add_argument("--phase", type=int, default=0)
    ns = ap.parse_args()

    data = bytearray(ns.input.read_bytes())
    kernel = load_kernel(str(ns.input), FUNCTION)
    if len(kernel.words) * 16 < BLOCK_END:
        raise RuntimeError("kernel is shorter than the expected basic block")
    # Fail closed if ptxas changes the skeleton: old block begins with IMAD
    # and the join begins with ISETP.
    if kernel.words[BLOCK_BEGIN // 16][0] & 0xfff != 0x824:
        raise RuntimeError("unexpected contender block start")
    if kernel.words[BLOCK_END // 16][0] & 0xfff != 0x80c:
        raise RuntimeError("unexpected contender block end")

    for i, (lo, hi) in enumerate(encoded_block(not ns.control, ns.phase)):
        struct.pack_into("<QQ", data,
                         kernel.file_off + BLOCK_BEGIN + 16 * i, lo, hi)

    if ns.target == "different":
        # ISETP.NE ... warp_id, 4 at 0x300 selects warp 4: same scheduler /
        # subcore as victim warp 0.  Re-encode it with immediate 1.
        off = 0x300
        old_lo = kernel.words[off // 16][0]
        if old_lo & 0xfff != 0x80c:
            raise RuntimeError("unexpected target-warp selector")
        [(lo, hi)] = assemble_flat(
            "ISETP.NE.AND P0, PT, R3, 0x1, PT;[7:7:{}:2:0]",
            arch="sm100a")
        struct.pack_into("<QQ", data, kernel.file_off + off, lo, hi)

    ns.output.write_bytes(data)
    kind = "control" if ns.control else "ffma"
    print(f"{kind}, target={ns.target}, phase={ns.phase} -> {ns.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
