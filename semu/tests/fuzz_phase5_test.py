#!/usr/bin/env python3
"""Phase 5 fuzz acceptance gate (CTest target).

Runs the random-operand fuzz of the semu interpreter against the independent
host reference oracle (no GPU needed) and the mutation gate.  Both must pass:

  * fuzz: every generated case matches the reference oracle (never an
    automatic PASS; cases with neither a reference nor a GPU are SKIP, which
    also fails this gate).
  * mutation: every tampered semu result word is detected as a FAIL.

Usage: python3 fuzz_phase5_test.py <path-to-semu> <path-to-fuzz_phase5.py>
"""

import json
import os
import subprocess
import sys
from pathlib import Path

def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    if len(sys.argv) < 3:
        print("usage: fuzz_phase5_test.py <semu> <fuzz_phase5.py>")
        return 2
    semu = Path(sys.argv[1]).resolve()
    fuzz_py = Path(sys.argv[2]).resolve()
    if not semu.exists():
        fail(f"semu binary not found: {semu}")
    if not fuzz_py.exists():
        fail(f"fuzz harness not found: {fuzz_py}")

    env = dict(os.environ)
    # Make `from assembler import ...` and `import fuzz_phase5` resolvable.
    repo = fuzz_py.parent
    env["PYTHONPATH"] = str(repo)
    env["SEMU_BIN"] = str(semu)

    # The fuzz harness calls the semu binary via its own SEMU constant; we
    # inject the binary path by pointing PYTHONPATH at the harness and
    # overriding nothing else.  Run with a modest case count for CI speed.
    n = "40"
    seed = "20260813"

    # 1) Non-GPU fuzz against the reference oracle.
    r = subprocess.run(
        [sys.executable, str(fuzz_py), "-n", n, "--seed", seed],
        capture_output=True, text=True, env=env)
    if r.returncode != 0:
        fail(f"fuzz (reference) failed:\n{r.stdout}\n{r.stderr}")
    if "skipped" in r.stdout and " 0 skipped" not in r.stdout:
        fail(f"fuzz produced skipped (unverified) cases:\n{r.stdout}")

    # 2) Mutation gate: a tampered word must be flagged.
    r = subprocess.run(
        [sys.executable, str(fuzz_py), "--mutation"],
        capture_output=True, text=True, env=env)
    if r.returncode != 0:
        fail(f"mutation gate failed:\n{r.stdout}\n{r.stderr}")
    if "detected by the reference gate" not in r.stdout:
        fail(f"mutation gate output unexpected:\n{r.stdout}")
    # The mutation report must assert detected == total (every tampered word
    # caught) with 0 semu errors — the exit code alone is not enough.
    mut_report = Path("/tmp/fuzz_phase5_mutation.json")
    if not mut_report.exists():
        fail("mutation JSON report missing: /tmp/fuzz_phase5_mutation.json")
    mrep = json.loads(mut_report.read_text())
    m = mrep.get("mutation", {})
    detected, total, errors = m.get("detected", 0), m.get("total", 0), m.get("errors", 0)
    if total <= 0:
        fail(f"mutation report has no verified cases: {m}")
    if detected != total:
        fail(f"mutation gate missed tampered words: detected={detected} "
             f"total={total}")
    if errors != 0:
        fail(f"mutation gate had {errors} semu errors (unverified cases): {m}")

    # 3) The JSON report must record gpu/seed/case counts and show 0 skipped.
    report_path = Path("/tmp/fuzz_phase5_report.json")
    if report_path.exists():
        rep = json.loads(report_path.read_text())
        if "seed" not in rep or "gpu" not in rep or "cases" not in rep:
            fail(f"report missing keys: {rep}")
        if rep.get("skipped", 0) != 0:
            fail(f"report has skipped cases: {rep['skipped']}")

    print(f"PASS fuzz_phase5 (n={n}, seed={seed}) + mutation gate "
          f"({detected}/{total}, 0 errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
