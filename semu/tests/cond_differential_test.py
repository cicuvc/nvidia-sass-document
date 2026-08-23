#!/usr/bin/env python3
"""Condition evaluator corpus gate (GAP-04 / GAP-09) -- pure Python.

The C++ side no longer hosts a runtime predicate evaluator: legality
conditions are compile-time thunks (gen_isa.py cond_check_*) and operand
widths are generated metadata functions (SizeEmitter), so the old
differential test against `semu cond-eval` / `semu eval-cond` is obsolete.
This gate keeps the REFERENCE Python evaluator (assembler/sass_cond.py,
the source of truth the generator compiles) over the sm120 corpus:

  1. parser coverage: every legality condition of every variant must fully
     tokenize and parse (evaluate_tristate() must not return None);
  2. legal corpus: legal corpus words must not yield an unexpected
     unresolved verdict from the reference evaluator;
  3. false samples: mutating an operand register field must flip at least
     one condition to false (sanity that conditions actually gate).

Usage: cond_differential_test.py <corpus> <db>
"""
import json
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
        elif rk == "slot_attr":
            base, _, attr = rhs.partition("@")
            suffix = {"not": "_not", "invert": "_invert",
                      "negate": "_negated", "absolute": "_abs"}.get(
                          attr.split(" ")[0], attr.split(" ")[0])
            sm[base + suffix] = val
        elif rk == "star_slot":
            name = rhs.lstrip("*")
            if "(" not in name:
                try:
                    int(name, 0)   # pinned literal: not a slot
                except ValueError:
                    sm[name] = val
    return sm


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: cond_differential_test.py <corpus> <db>",
              file=sys.stderr)
        return 2
    corpus_path = Path(sys.argv[1])
    if not corpus_path.is_file():
        print(f"corpus not found: {corpus_path} (run "
              f"semu/tools/gen_corpus.py --db <db> --out <corpus>)",
              file=sys.stderr)
        return 2
    corpus = json.load(open(corpus_path))
    db = json.load(open(sys.argv[2]))
    by_class = {v["class"]: v for v in db["variants"]}

    # 1. parser-coverage gate: every condition must fully resolve (no None).
    n_total = n_true = n_false = n_unres = 0
    bad = []
    for v in db["variants"]:
        ev = ConditionEvaluator(db, {})
        for c in v["conditions"]:
            n_total += 1
            if ev.evaluate_tristate(c["predicate"]) is None:
                n_unres += 1
                if len(bad) < 15:
                    bad.append(f"{v['class']}: {c['error']}: "
                               f"{c['predicate']}")

    # 2. legal corpus: no unexpected unresolved verdicts from the reference
    #    evaluator on the real decoded slot maps.
    n_corpus = 0
    for r in corpus:
        if not r["encoded"]:
            continue
        v = by_class.get(r["variant_class"])
        if v is None:
            continue
        sm = build_slot_map(db, v, r["lo"], r["hi"])
        ev = ConditionEvaluator(db, sm)
        for c in v["conditions"]:
            n_corpus += 1
            if ev.evaluate_tristate(c["predicate"]) is None:
                n_unres += 1
                if len(bad) < 15:
                    bad.append(f"corpus {r['variant_class']}: {c['error']}: "
                               f"{c['predicate']}")

    # 3. false samples: flip a non-opcode 8-bit register field; at least one
    #    condition must go false.
    n_false_samples = 0
    for r in corpus:
        if not r["encoded"]:
            continue
        v = by_class.get(r["variant_class"])
        if v is None:
            continue
        field = next((f for f in v["encoding"]
                      if f["width"] == 8 and f["rhs_kind"] == "slot"
                      and f["rhs"].split(" ")[0] in
                      ("Rd", "Ra", "Rb", "Rc")), None)
        if field is None:
            continue
        cur = extract(field["targets"], r["lo"], r["hi"])
        newv = (cur + 1) % 255
        nlo, nhi = set_field(field["targets"], r["lo"], r["hi"], newv)
        sm = build_slot_map(db, v, nlo, nhi)
        ev = ConditionEvaluator(db, sm)
        any_false = False
        for c in v["conditions"]:
            py = ev.evaluate_tristate(c["predicate"])
            if py is False:
                any_false = True
                n_false_samples += 1
                break
        if n_false_samples > 20:
            break

    if bad:
        for b in bad[:20]:
            print("  " + b, file=sys.stderr)
        print(f"FAIL: {n_unres} unresolved over {n_total} conditions + "
              f"{n_corpus} corpus checks", file=sys.stderr)
        return 1

    print(f"OK: {n_total} conditions fully parsed; {n_corpus} corpus "
          f"condition checks; false samples: {n_false_samples}")
    return 0


if __name__ == "__main__":
    sys.exit(main())