#!/usr/bin/env python3
"""Fixture reproducibility gate (CTest 'cuobj_regen', GAP-11).

Rebuilds the sm120 cuobjdump vector fixture from repo content:
  - committed reviewed cubins (tests/*.cubin, gitignored-exempt) for
    pmtrig/tma kernels;
  - the committed regen CUDA sources (semu/tests/data/regen/*.cu), compiled
    with nvcc on the fly.

The rebuilt word set must equal the committed fixture's word set.  When the
local CUDA toolchain differs from the one that produced the committed cubins,
the vecmix/vecmix2 words must still match (they are compiled fresh here), and
the tma/pmtrig words come from the committed cubins byte-for-byte.

Skipped (exit 0 with a note) when nvcc/cuobjdump are unavailable.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REBUILD = REPO / "semu" / "tools" / "rebuild_cuobj_fixture.py"
FIXTURE = REPO / "semu" / "tests" / "data" / "cuobj_vectors_sm120.json"


def main() -> int:
    nvcc = Path("/usr/local/cuda/bin/nvcc")
    cuobjdump = Path("/usr/local/cuda/bin/cuobjdump")
    if not nvcc.is_file() or not cuobjdump.is_file():
        print("SKIP: nvcc/cuobjdump unavailable; fixture stays committed")
        return 0
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path("/tmp") / "cuobj_fixture_rebuild.json"
    p = subprocess.run([sys.executable, str(REBUILD), "--out", str(out)],
                       text=True, capture_output=True)
    if p.returncode != 0:
        print("FAIL: rebuild script error:\n" + p.stderr[-1000:],
              file=sys.stderr)
        return 1
    committed = json.load(open(FIXTURE))
    rebuilt = json.load(open(out))
    cset = {(v["lo"], v["hi"]) for v in committed["vectors"]}
    rset = {(v["lo"], v["hi"]) for v in rebuilt["vectors"]}
    if cset != rset:
        only_c = len(cset - rset)
        only_r = len(rset - cset)
        print(f"FAIL: rebuilt word set differs from committed fixture "
              f"({only_c} only-committed, {only_r} only-rebuilt)", file=sys.stderr)
        return 1
    print(f"OK: {len(cset)} words reproducible from repo content "
          f"(committed cubins + regen sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
