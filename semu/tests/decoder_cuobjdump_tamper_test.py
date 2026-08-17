#!/usr/bin/env python3
"""Cuobjdump gate mutation test (CTest 'decoder_cuobjdump_tamper', GAP-10).

The structured comparison in decoder_cuobjdump_test.py must FAIL when any
operand, modifier, register or branch target is tampered.  This test
mutates one field at a time in a copy of the fixture and asserts the gate
rejects the tampered copy, proving the gate is not vacuously passing.

Each tamper must flip exactly one comparison axis:
  - register operand change (R5 -> R6);
  - extra modifier (LDC -> LDC.BOGUS);
  - branch target displacement change;
  - extra trailing operand (append an immediate).
"""
import json
import subprocess
import sys
from pathlib import Path

TEST = (Path(__file__).resolve().parent / "decoder_cuobjdump_test.py")
FIXTURE = (Path(__file__).resolve().parent / "data" /
           "cuobj_vectors_sm120.json")


def run_gate(fixture_path: Path) -> int:
    p = subprocess.run([sys.executable, str(TEST),
                        sys.argv[1] if len(sys.argv) > 1 else
                        "semu/build/cli/semu", str(fixture_path)],
                       text=True, capture_output=True)
    return p.returncode


def make_tampered(mutator) -> Path:
    data = json.load(open(FIXTURE))
    vecs = data["vectors"]
    applied = mutator(vecs)
    if not applied:
        raise RuntimeError("mutator did not find a target vector")
    out = Path("/tmp") / "cuobj_tampered.json"
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return out


def mut_reg(vecs):
    for v in vecs:
        if "R5" in v["text"] and "STG" in v["text"]:
            v["text"] = v["text"].replace("R5", "R6", 1)
            return True
    return False


def mut_mod(vecs):
    for v in vecs:
        if "LDC R" in v["text"]:
            v["text"] = v["text"].replace("LDC R", "LDC.BOGUS R", 1)
            return True
    return False


def mut_branch(vecs):
    for v in vecs:
        if "BRA 0x1c0" in v["text"]:
            v["text"] = v["text"].replace("0x1c0", "0x1d0", 1)
            return True
    return False


def mut_extra_op(vecs):
    for v in vecs:
        if "LDC R" in v["text"]:
            v["text"] = v["text"].replace("0x37c", "0x37c, R9", 1)
            return True
    return False


def main() -> int:
    bad = 0
    for name, fn in [("register", mut_reg), ("modifier", mut_mod),
                     ("branch-target", mut_branch), ("extra-operand",
                                                     mut_extra_op)]:
        path = make_tampered(fn)
        rc = run_gate(path)
        status = "ok" if rc == 1 else "GATE PASSED (tamper not detected)"
        if rc != 1:
            bad += 1
        print(f"  tamper[{name}]: gate exit={rc} ({status})")
    path.unlink(missing_ok=True)
    if bad:
        print(f"FAIL: {bad} tamper(s) not detected by the cuobjdump gate",
              file=sys.stderr)
        return 1
    print("OK: all 4 tamper classes rejected by the cuobjdump gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
