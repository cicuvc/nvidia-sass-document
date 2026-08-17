#!/usr/bin/env python3
"""Manifest regeneration gate (CTest 'manifest_regen').

Verifies the Phase 0 exit condition that the capability manifest is
regenerable byte-identical:

  1. running semu/tools/gen_capability.py twice produces byte-identical
     capability_data.{hpp,cpp};
  2. the committed build inputs (semu/generated/) are exactly what the
     generator produces right now.

Usage:
    manifest_regen_test.py <sm120.json path> <committed generated dir>
"""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
GEN = HERE.parent / "tools" / "gen_capability.py"


def run(args, **kw):
    return subprocess.run(args, check=True, text=True,
                         capture_output=True, **kw)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: manifest_regen_test.py <db> <generated-dir>", file=sys.stderr)
        return 2
    db = pathlib.Path(sys.argv[1])
    committed = pathlib.Path(sys.argv[2])

    files = ["capability_data.hpp", "capability_data.cpp"]

    with tempfile.TemporaryDirectory() as td:
        t1 = pathlib.Path(td) / "run1"
        t2 = pathlib.Path(td) / "run2"
        for t in (t1, t2):
            run([sys.executable, str(GEN), "--db", str(db),
                 "--output-dir", str(t)])
            for f in files:
                p = t / f
                if not p.is_file():
                    print(f"FAIL: generator did not produce {p}", file=sys.stderr)
                    return 1

        for f in files:
            a = (t1 / f).read_bytes()
            b = (t2 / f).read_bytes()
            if a != b:
                print(f"FAIL: {f} differs between two identical generator runs",
                      file=sys.stderr)
                return 1

        for f in files:
            a = (t1 / f).read_bytes()
            b = (committed / f).read_bytes()
            if a != b:
                print(f"FAIL: committed {committed / f} is stale "
                      f"(regenerate with {GEN})", file=sys.stderr)
                return 1

    print("OK: capability manifest regenerates byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
