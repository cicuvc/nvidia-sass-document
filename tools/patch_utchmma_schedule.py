#!/usr/bin/env python3
"""Rotate UTCHMMA read scoreboards in an nvcc cubin.

ptxas normally assigns every static UTCHMMA in a basic block rd=SB0 with an
empty request mask.  Its PTX compatibility lowering places req={0} on the
ELECT/PLOP retry branch three instructions later.  This patch rotates that
compiler-generated pair through SB0..SB5; it does not model a hardware
requirement for hand-written U-path SASS, which can issue naked UTCHMMA.

Earlier versions incorrectly put req={sb} on UTCHMMA itself and left the retry
branch waiting SB0.  Results produced by that version do not establish whether
read-scoreboard reuse limits throughput.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sassdbg.cubin import load_kernel  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--function", required=True)
    ns = ap.parse_args()

    data = bytearray(ns.input.read_bytes())
    kernel = load_kernel(str(ns.input), ns.function)
    indices = []
    for i, (lo, hi) in enumerate(kernel.words):
        opcode = (((hi >> 27) & 1) << 12) | (lo & 0xfff)
        if opcode in (0x15ea, 0x19ea):
            indices.append(i)
    if len(indices) < 6:
        raise RuntimeError(f"expected an unrolled UTCHMMA body, got {len(indices)}")

    rd_mask = 0x7 << 49       # architectural bits [115:113]
    req_mask = 0x3f << 52     # architectural bits [121:116]
    for n, i in enumerate(indices):
        lo, hi = kernel.words[i]
        sb = n % 6
        hi = (hi & ~rd_mask) | (sb << 49)
        hi &= ~req_mask
        struct.pack_into("<QQ", data, kernel.file_off + 16 * i, lo, hi)

        # ptxas lowering is:
        #   UTCHMMA rd=SBx; @P ELECT-close; PLOP3; @P BRA.U.ANY req={SBx}
        # Keep the read-release wait on the retry branch.  Validate the local
        # shape before touching it so a compiler scheduling change fails loud.
        bi = i + 3
        if bi >= len(kernel.words):
            raise RuntimeError(f"UTCHMMA at {i} has no retry branch")
        blo, bhi = kernel.words[bi]
        bop = (((bhi >> 27) & 1) << 12) | (blo & 0xfff)
        if bop != 0x947:  # BRA
            raise RuntimeError(
                f"expected BRA three instructions after UTCHMMA {i}, "
                f"got opcode {bop:#x}")
        bhi = (bhi & ~req_mask) | ((1 << sb) << 52)
        struct.pack_into("<QQ", data, kernel.file_off + 16 * bi, blo, bhi)

    ns.output.write_bytes(data)
    print(f"patched {len(indices)} UTCHMMA/retry pairs in {ns.function} "
          f"to rotating SB0..SB5 -> {ns.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
