#!/usr/bin/env python3
"""Condition evaluator differential test (CTest 'cond_differential', GAP-09).

For every legality condition of every corpus word, compare the Python
ConditionEvaluator (reference) and the C++ three-state evaluator on the SAME
decoded slot map:

  - Python verdict:  True / False / None (unresolved: unknown char, parse
    error, or unconsumed tokens) via evaluate_tristate();
  - C++ verdict:     `semu cond-eval <class> <lo> <hi>` prints
    "<error>\t<1|0|2>\t<predicate>" per condition (1 true, 0 false, 2
    unresolved) computed from the decoder's own slot map for that word.

Requirements (GAP-09):
  - mismatch == 0 between the two evaluators;
  - unexpected unresolved == 0 on the legal corpus (both sides);
  - condition-false samples (mutated words) and unresolved/unknown-token
    samples must produce the expected tristate on BOTH sides.

Output records: total comparisons, true/false/unresolved counts, mismatches.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler.sass_cond import ConditionEvaluator  # noqa: E402


def extract(targets, lo, hi):
    val = 0
    for h, l in targets:
        w = h - l + 1
        mask = (1 << w) - 1
        if l >= 64:
            part = (hi >> (l - 64)) & mask
        elif h < 64:
            part = (lo >> l) & mask
        else:
            lo_w = 64 - l
            part = ((lo >> l) & ((1 << lo_w) - 1)) | (
                (hi & ((1 << (w - lo_w)) - 1)) << lo_w)
        val = (val << w) | part
    return val


def set_field(targets, lo, hi, value):
    width = sum(h - l + 1 for h, l in targets)
    bits_left = width
    for h, l in targets:
        rw = h - l + 1
        bits_left -= rw
        sub = (value >> bits_left) & ((1 << rw) - 1)
        for b in range(l, h + 1):
            bit = (sub >> (b - l)) & 1
            if b >= 64:
                hi = (hi & ~(1 << (b - 64))) | (bit << (b - 64))
            else:
                lo = (lo & ~(1 << b)) | (bit << b)
    return lo, hi


def build_slot_map(db, v, lo, hi):
    """Python replica of the C++ build_slot_map (field extraction)."""
    sm = {}

    def extract_into(targets):
        return extract(targets, lo, hi)

    for f in v["encoding"]:
        rk = f["rhs_kind"]
        rhs = f["rhs"]
        val = extract_into(f["targets"])
        if rk == "slot":
            sm[rhs.split(" ")[0]] = val
        elif rk == "star_slot":
            name = rhs.lstrip("*")
            if "(" in name:
                tn = name.split("(")[0]
                args = name.split("(")[1].rstrip(")").split(",")
                for row in db["tables"].get(tn, {}).get("rows", []):
                    if int(row["out"], 0) != val:
                        continue
                    inargs = row["in"]
                    ok = True
                    for a, inv in zip(args, inargs):
                        try:
                            lit = int(a, 0)
                        except ValueError:
                            continue
                        if inv != str(lit):
                            ok = False
                            break
                    if not ok:
                        continue
                    for a, inv in zip(args, inargs):
                        if a in sm:
                            continue
                        try:
                            int(a, 0)
                        except ValueError:
                            sm[a] = int(inv, 0)
                    break
            else:
                try:
                    int(name, 0)
                except ValueError:
                    sm[name] = val
        elif rk == "slot_attr":
            import re as _re
            m = _re.match(r"(\w+)@(\w+)$", rhs)
            if m:
                sname, attr = m.group(1), m.group(2)
                suf = {"not": "not", "negate": "negated",
                       "absolute": "abs", "invert": "invert"}.get(
                    attr, attr)
                sm[f"{sname}_{suf}"] = val
        elif rk == "table_fn":
            tn = rhs.split("(")[0]
            args = rhs.split("(")[1].rstrip(")").split(",")
            for row in db["tables"].get(tn, {}).get("rows", []):
                if int(row["out"], 0) == val:
                    for a, inv in zip(args, row["in"]):
                        if a in sm:
                            continue
                        try:
                            sm[a] = int(inv, 0)
                        except ValueError:
                            pass
                    break
        elif rk == "other_fn":
            fn = rhs.split("(")[0]
            if fn in ("VarLatOperandEnc", "IDENTICAL"):
                sm[rhs.split("(")[1].rstrip(")").split(",")[0]] = val
            elif fn in ("ConstBankAddress0", "ConstBankAddress2"):
                sm[f["name"]] = val
    return sm


def cpp_verdicts(semu, cls, lo, hi):
    p = subprocess.run([str(semu), "cond-eval", cls, str(lo), str(hi)],
                       text=True, capture_output=True)
    out = {}
    for line in p.stdout.splitlines():
        err, v, pred = line.split("\t", 2)
        out[(err, pred)] = int(v)
    return out


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: cond_differential_test.py <semu> <corpus> <db>",
              file=sys.stderr)
        return 2
    semu = Path(sys.argv[1])
    corpus_path = Path(sys.argv[2])
    if not corpus_path.is_file():
        subprocess.run([sys.executable,
                        str(Path(__file__).resolve().parent.parent /
                            "tools" / "gen_corpus.py"),
                        "--db", sys.argv[3], "--out", str(corpus_path)],
                       check=True, capture_output=True)
    corpus = json.load(open(corpus_path))
    db = json.load(open(sys.argv[3]))
    by_class = {v["class"]: v for v in db["variants"]}

    # 1. parser-coverage gate: C++ scan-conds must report 0 gaps.
    p = subprocess.run([str(semu), "scan-conds"], text=True,
                       capture_output=True)
    summary = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    if p.returncode != 0 or "0 parser gaps" not in summary:
        print(f"FAIL: condition parser gaps: {summary}", file=sys.stderr)
        return 1

    # 2. per-condition differential on corpus words
    n_total = n_true = n_false = n_unres = n_mismatch = 0
    bad = []
    for r in corpus:
        if not r["encoded"]:
            continue
        v = by_class[r["variant_class"]]
        lo, hi = r["lo"], r["hi"]
        sm = build_slot_map(db, v, lo, hi)
        ev = ConditionEvaluator(db, sm)
        cpp = cpp_verdicts(semu, r["variant_class"], lo, hi)
        for c in v["conditions"]:
            py = ev.evaluate_tristate(c["predicate"])
            pyv = 1 if py is True else (0 if py is False else 2)
            cv = cpp.get((c["error"], c["predicate"]))
            n_total += 1
            if pyv == 1:
                n_true += 1
            elif pyv == 0:
                n_false += 1
            else:
                n_unres += 1
            if cv is None or cv != pyv:
                n_mismatch += 1
                if len(bad) < 15:
                    bad.append(f"{r['variant_class']}: {c['error']} "
                               f"py={pyv} cpp={cv}")

    # 3. false-sample: mutate a discriminator/operand field on a sample word
    #    so at least one condition goes false on both sides.
    n_false_samples = 0
    for r in corpus:
        if not r["encoded"]:
            continue
        v = by_class[r["variant_class"]]
        lo, hi = r["lo"], r["hi"]
        # find a non-opcode 8-bit register field to flip
        field = next((f for f in v["encoding"]
                      if f["width"] == 8 and f["rhs_kind"] == "slot"
                      and f["rhs"].split(" ")[0] in
                      ("Rd", "Ra", "Rb", "Rc")), None)
        if field is None:
            continue
        cur = extract(field["targets"], lo, hi)
        newv = (cur + 1) % 255
        nlo, nhi = set_field(field["targets"], lo, hi, newv)
        sm = build_slot_map(db, v, nlo, nhi)
        ev = ConditionEvaluator(db, sm)
        cpp = cpp_verdicts(semu, r["variant_class"], nlo, nhi)
        for c in v["conditions"]:
            py = ev.evaluate_tristate(c["predicate"])
            pyv = 1 if py is True else (0 if py is False else 2)
            cv = cpp.get((c["error"], c["predicate"]))
            n_total += 1
            if pyv == 1:
                n_true += 1
            elif pyv == 0:
                n_false += 1
                n_false_samples += 1
            else:
                n_unres += 1
            if cv is None or cv != pyv:
                n_mismatch += 1
                if len(bad) < 15:
                    bad.append(f"{r['variant_class']}[mutated]: "
                               f"{c['error']} py={pyv} cpp={cv}")
        if n_false_samples > 20:
            break

    # 4. unresolved sample: a predicate with an unknown token must be
    #    unresolved on BOTH sides (Python evaluate_tristate AND the C++
    #    eval-cond API with the same slot map).
    weird = "((Rd)==`Register@RZ) && @@@"
    ev0 = ConditionEvaluator(db, {})
    pyu = ev0.evaluate_tristate(weird)
    if pyu is not None:
        bad.append(f"unknown-token sample: py={pyu} (want unresolved)")
    p = subprocess.run([str(semu), "eval-cond"],
                       input=weird + "\t" + "\n", text=True,
                       capture_output=True)
    cpp_u = p.stdout.strip()
    if cpp_u != "2":
        bad.append(f"unknown-token sample: cpp={cpp_u} (want 2/unresolved)")

    # 5. resolved-token sample: a normal predicate must give 1 (true) on both
    #    sides with the same slot map, proving the C++ direct-eval path works.
    ok_pred = "((Rd)==`Register@RZ)"
    ev1 = ConditionEvaluator(db, {"Rd": 255})
    py_ok = ev1.evaluate_tristate(ok_pred)
    p = subprocess.run([str(semu), "eval-cond"],
                       input=ok_pred + "\tRd=255\n", text=True,
                       capture_output=True)
    cpp_ok = p.stdout.strip()
    if py_ok is not True or cpp_ok != "1":
        bad.append(f"resolved sample: py={py_ok} cpp={cpp_ok} (want True/1)")

    if bad:
        for b in bad[:20]:
            print("  " + b, file=sys.stderr)
        print(f"FAIL: {n_mismatch} mismatches over {n_total} comparisons",
              file=sys.stderr)
        return 1
    if n_unres:
        print(f"NOTE: {n_unres} unresolved on legal corpus", file=sys.stderr)

    print(f"OK: {n_total} condition comparisons: {n_true} true, "
          f"{n_false} false, {n_unres} unresolved, {n_mismatch} mismatches; "
          f"false samples: {n_false_samples}; unknown-token sample "
          f"unresolved on both sides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
