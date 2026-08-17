#!/usr/bin/env python3
"""ISA data regeneration gate (CTest 'isa_regen').

Verifies the Phase 1 generator determinism exit criterion:

  1. running semu/tools/gen_isa.py twice produces byte-identical
     isa_data.{hpp,cpp};
  2. the committed build inputs (semu/generated/) are exactly what the
     generator produces right now;
  3. the 1414-variant corpus is reproducible from sm120.json (same word per
     variant on every run) via semu/tools/gen_corpus.py.

Usage:
    isa_regen_test.py <sm120.json path> <committed generated dir>
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
GEN_ISA = HERE.parent / "tools" / "gen_isa.py"
GEN_CORPUS = HERE.parent / "tools" / "gen_corpus.py"

FILES = ["isa_data.hpp", "isa_data.cpp"]


def run(args, **kw):
    return subprocess.run(args, check=True, text=True,
                          capture_output=True, **kw)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: isa_regen_test.py <db> <generated-dir>", file=sys.stderr)
        return 2
    db = pathlib.Path(sys.argv[1])
    committed = pathlib.Path(sys.argv[2])

    # 1+2. gen_isa determinism + committed-match
    with tempfile.TemporaryDirectory() as td:
        t1 = pathlib.Path(td) / "run1"
        t2 = pathlib.Path(td) / "run2"
        for t in (t1, t2):
            run([sys.executable, str(GEN_ISA), "--db", str(db),
                 "--output-dir", str(t)])
        for f in FILES:
            a = (t1 / f).read_bytes()
            b = (t2 / f).read_bytes()
            if a != b:
                print(f"FAIL: {f} differs between identical generator runs",
                      file=sys.stderr)
                return 1
            c = (committed / f).read_bytes()
            if a != c:
                print(f"FAIL: committed {committed / f} is stale "
                      f"(regenerate with {GEN_ISA})", file=sys.stderr)
                return 1

    # 3. corpus reproducibility: run gen_corpus twice, require identical words.
    with tempfile.TemporaryDirectory() as td:
        c1 = pathlib.Path(td) / "c1.json"
        c2 = pathlib.Path(td) / "c2.json"
        run([sys.executable, str(GEN_CORPUS), "--db", str(db),
             "--out", str(c1)])
        run([sys.executable, str(GEN_CORPUS), "--db", str(db),
             "--out", str(c2)])
        j1 = json.load(open(c1))
        j2 = json.load(open(c2))
        if len(j1) != len(j2):
            print(f"FAIL: corpus size differs ({len(j1)} vs {len(j2)})",
                  file=sys.stderr)
            return 1
        for a, b in zip(j1, j2):
            if (a["variant_class"], a["lo"], a["hi"], a["encoded"]) != \
               (b["variant_class"], b["lo"], b["hi"], b["encoded"]):
                print(f"FAIL: corpus word differs for {a['variant_class']}",
                      file=sys.stderr)
                return 1
        encoded = sum(1 for r in j1 if r["encoded"])
        print(f"OK: gen_isa deterministic + committed; corpus reproducible "
              f"({encoded}/{len(j1)} encoded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
