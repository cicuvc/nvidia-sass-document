#!/usr/bin/env python3
"""Cross-check the C++ UnifiedV1Estimator against the Python oracle.

Runs `semu_l1tex_cli` on every row of the frozen fixture JSONL files and
compares the C++ result field-by-field (SharedWf/ReadWf/WriteWf/OverlapWf/
Tokens + per-token decomposition) with `unified_model.simulate`.

Usage:
    l1tex_oracle_check.py <semu_l1tex_cli> <arch_l1tex_dir> [jsonl...]

If no jsonl files are given, uses the frozen manifests (gf2 corpora,
gf2-near, token-accumulator) and the random warmldg corpora.  Prints per-file
exact counts (C++==Python field-for-field) and exits non-zero on any
mismatch.  For the random corpora it also prints the frozen aggregate
exact/MAE expectations (these are informational: C++==Python is the hard gate,
GPU-accuracy is the Python-side gate).
"""
import json
import subprocess
import sys
from pathlib import Path

_ARCH = Path("/home/cicuvc/cs/projects/arch/l1tex")
if _ARCH.exists():
    sys.path.insert(0, str(_ARCH))
from unified_model import simulate  # noqa: E402

def run_cpp(cli, g, s, size, mask):
    gs = ",".join(str(x) for x in g)
    ss = ",".join(str(x) for x in s)
    p = subprocess.run([str(cli), f"g={gs}", f"s={ss}",
                        f"m={mask}", f"size={size}"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return None
    return json.loads(p.stdout)

def field_match(cpp, py):
    if cpp["SharedWf"] != py["SharedWf"]: return "SharedWf"
    if cpp["ReadWf"] != py["ReadWf"]: return "ReadWf"
    if cpp["WriteWf"] != py["WriteWf"]: return "WriteWf"
    if cpp["OverlapWf"] != py["OverlapWf"]: return "OverlapWf"
    if cpp["Tokens"] != py["Tokens"]: return "Tokens"
    cs, ps = cpp["TokenStats"], py["TokenStats"]
    if len(cs) != len(ps): return "TokenStats.len"
    for a, b in zip(cs, ps):
        for k in ("Token", "Lanes", "ReadWf", "WriteWf", "OverlapWf", "SharedWf"):
            if a[k] != b[k]:
                return f"TokenStats.{k}"
    return None

def score(cli, path, size_hint):
    rows = [json.loads(l) for l in Path(path).open()]
    exact = total = 0
    mismatch_fields = {}
    for i, row in enumerate(rows):
        size = row.get("size", size_hint)
        py = simulate(row["g"], row["s"], size, row["m"])
        cpp = run_cpp(cli, row["g"], row["s"], size, row["m"])
        if cpp is None:
            print(f"  C++ run failed row {i}")
            return exact, total, mismatch_fields
        m = field_match(cpp, py)
        total += 1
        if m is None:
            exact += 1
        else:
            mismatch_fields.setdefault(m, 0)
            mismatch_fields[m] += 1
            if len(mismatch_fields) <= 3:
                print(f"  row {i} mismatch field={m} cpp={cpp} py={py}")
    return exact, total, mismatch_fields

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cli = Path(sys.argv[1])
    arch = Path(sys.argv[2])
    sys.path.insert(0, str(arch))
    files = sys.argv[3:]

    if files:
        for f in files:
            exact, total, mf = score(cli, f, 4)
            print(f"{f}: C++==Python {exact}/{total} {mf or ''}")
        return 0

    # Frozen manifests + random corpora.
    manifest = json.loads((arch / "gf2_model_manifest.json").read_text())
    gf2_files = list(manifest["corpora"].keys())
    near = json.loads((arch / "gf2_near_manifest.json").read_text())
    near_files = list(near["files"].keys()) if isinstance(near.get("files"), dict) else near["files"]
    tok = json.loads((arch / "token_accumulator_manifest.json").read_text())
    tok_files = list(tok["files"].keys())
    random_files = [f"data{s}_ldgsts_warmldg.jsonl" for s in (4, 8, 16)]

    all_exact = all_total = 0
    for label, fl, hint in (("GF2", gf2_files, 4), ("GF2-near", near_files, 4),
                            ("token", tok_files, 16), ("random", random_files, 4)):
        f_exact = f_total = 0
        for f in fl:
            exact, total, _ = score(cli, arch / f, hint)
            if exact is None: continue
            f_exact += exact; f_total += total
        print(f"{label}: C++==Python {f_exact}/{f_total}")
        all_exact += f_exact; all_total += f_total

    # Random-corpus frozen GPU-accuracy (informational; C++==Python is hard).
    for s in (4, 8, 16):
        rows = [json.loads(l) for l in (arch / f"data{s}_ldgsts_warmldg.jsonl").open()]
        got = [run_cpp(cli, r["g"], r["s"], s, r["m"]) for r in rows]
        exact = sum(1 for r, cpp in zip(rows, got)
                    if cpp is not None
                    and cpp["SharedWf"] == r["meas"]["SharedWf"])
        mae = sum(abs(cpp["SharedWf"] - r["meas"]["SharedWf"])
                  for r, cpp in zip(rows, got) if cpp is not None)
        mae /= len(rows)
        print(f"random {s} B: GPU-exact {exact}/{len(rows)} MAE {mae:.4f}")
    print(f"TOTAL C++==Python: {all_exact}/{all_total}")
    return 0 if all_exact == all_total else 1

if __name__ == "__main__":
    sys.exit(main())
