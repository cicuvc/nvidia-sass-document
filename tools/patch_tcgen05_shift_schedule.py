#!/usr/bin/env python3
"""Patch nvcc UTCSHIFT scheduling while preserving TMEM ELF metadata.

With ``--bare``, replace every six-instruction PTX election/retry envelope by
consecutive raw UTCSHIFT instructions plus one branch over padding.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import assemble_flat  # noqa: E402
from sassdbg.cubin import load_kernel  # noqa: E402


COUNTS = (1, 2, 4, 8, 16, 32, 64, 128)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--stall", type=int, required=True)
    ap.add_argument("--bare", action="store_true")
    ns = ap.parse_args()
    if not 1 <= ns.stall <= 15:
        ap.error("stall must be in [1, 15]; encoded stall=0 is drain")

    [(new_lo, new_hi)] = assemble_flat(
        f"UTCSHIFT.DOWN tmem[UR6];[7:7:{{}}:{ns.stall}:1]",
        arch="sm100a")
    data = bytearray(ns.input.read_bytes())
    total = 0
    for count in COUNTS:
        name = f"shift_{count}"
        kernel = load_kernel(str(ns.input), name)
        indices = [i for i, (lo, _hi) in enumerate(kernel.words)
                   if lo & 0xfff == 0x9e6]
        found = len(indices)
        if found != count:
            raise RuntimeError(f"{name}: expected {count} UTCSHIFT, got {found}")
        if ns.bare:
            if any(b - a != 6 for a, b in zip(indices, indices[1:])):
                raise RuntimeError(f"{name}: envelopes are not six words apart")
            begin = indices[0] - 2
            span = 6 * count
            lines = [
                f"UTCSHIFT.DOWN tmem[UR6];[7:7:{{}}:{ns.stall}:1]"
                for _ in range(count)
            ]
            lines.append("BRA #label(done);[7:7:{}:5:0]")
            lines += ["NOP;[7:7:{}:1:0]"] * (span - count - 1)
            lines.append("#def_label(done)")
            encoded = assemble_flat("\n".join(lines), arch="sm100a")
            if len(encoded) != span:
                raise RuntimeError(f"{name}: bad replacement length")
            for i, (lo, hi) in enumerate(encoded):
                struct.pack_into("<QQ", data,
                                 kernel.file_off + 16 * (begin + i), lo, hi)
        else:
            for i in indices:
                # These kernels use a zero offset and UR6.  Replacing the
                # whole word is safer than hand-editing opex bits.
                struct.pack_into("<QQ", data, kernel.file_off + 16 * i,
                                 new_lo, new_hi)
        total += found
    ns.output.write_bytes(data)
    mode = "bare" if ns.bare else "enveloped"
    print(f"patched {total} {mode} UTCSHIFT instructions to stall={ns.stall}: "
          f"{ns.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
