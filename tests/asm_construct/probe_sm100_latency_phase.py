#!/usr/bin/env python3
"""Dump raw repetition values for phase-sensitive B200 forwarding cells."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_alulite_latency as base  # noqa: E402
import probe_aluheavy_latency as ah  # noqa: E402
import probe_fmaheavy_latency as fh  # noqa: E402
import probe_fmaheavy_wide_latency as fw  # noqa: E402
import probe_fp16_latency as fp16  # noqa: E402


def main() -> int:
    base.GAPS = [1, 2, 3, 4]
    cases = (
        ("IADD->FADD", lambda: base.gpr_source("IADD", "fmalite", False),
         "lat"),
        ("ISCADD->FADD", lambda: ah.gpr_source("ISCADD", "fmalite", False),
         "hlat"),
        ("IMAD->IADD3", lambda: fh.source("IMAD", "aluheavy", False),
         "hflat"),
        ("HFMA2_32I->IADD3",
         lambda: fp16.source("HFMA2_32I", "aluheavy", False), "fplat"),
        ("IMAD.WIDE.lo->IADD3",
         lambda: fw.source("IMAD.WIDE", "lo", "aluheavy", False),
         "hwide"),
    )
    for name, builder, fn in cases:
        reps = base.run_source(builder(), fn, 12)
        print(name)
        for gap_i, gap in enumerate(base.GAPS):
            vals = [row[gap_i] for row in reps]
            print(f"  gap={gap}: " + " ".join(f"{x:08x}" for x in vals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
