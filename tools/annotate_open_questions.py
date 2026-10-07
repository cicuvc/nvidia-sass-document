#!/usr/bin/env python3
"""Annotate open-question bullets with their disposition (phase 4 sweep).

``tools/open_questions.py`` finds and classifies the question bullets; this tool writes the
conclusion back onto the bullet, so a reader of the note sees it in place:

```
- Why does the boundary move by one cycle?  <!-- open-question: open blocked-by "needs an
  H100 session; the local part is an RTX 5090" -->
- Is the ALTERNATE ever emitted?             <!-- open-question: answered by the decoder
  round-trip recorded under Verified encodings -->
```

It is idempotent, never rewrites a bullet that already carries an annotation, and records
for every remaining open question *what is blocking it* -- inferred from the question's own
wording, and marked as such so a later session can correct it rather than trusting it.

Usage
-----
    python3 tools/annotate_open_questions.py --dry-run      # show what would change
    python3 tools/annotate_open_questions.py --apply
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes_audit as na        # noqa: E402
import open_questions as oq     # noqa: E402

#: Blocker classes, most specific first.  The first pattern that matches the question text
#: (plus its note's status block) wins.  Wording is deliberately concrete: "needs X" tells
#: the next session what to acquire, which "unknown" does not.
BLOCKERS: tuple[tuple[str, str], ...] = (
    (r"(?i)\b(sm_?90|H20|H100|H200|H800|GH100|hopper)\b",
     "needs a Hopper session (sm_90) -- no local part"),
    (r"(?i)\b(sm_?100|sm_?103|B200|B300|GB100|modal)\b",
     "needs a Blackwell-datacenter session (sm_100/sm_103)"),
    (r"(?i)\b(sm_?70|sm_?80|sm_?89|V100|A100|RTX 4090|AD10\d)\b",
     "needs the older part (sm_70/80/89)"),
    (r"(?i)\bncu\b|nsight|profiler|counter",
     "needs NCU / performance counters (unavailable on the remote parts)"),
    (r"(?i)ptxas|nvcc|cuobjdump|driver|toolchain|assembler|emitted by",
     "needs a toolchain run (ptxas/nvcc/cuobjdump) or assembler support"),
    (r"(?i)\bspec\b|undocumented|not documented|manual|ISA text",
     "the ISA dump does not define it; needs a probe or an external reference"),
    (r"(?i)\btest\b|\bprobe\b|measure|sweep|re-?test|verify|confirm|reproduce|empirical",
     "needs a new probe/test (no hardware blocker stated)"),
    (r"(?i)\bmodel\b|simulat|infer|theor",
     "needs a model or simulation, not hardware"),
)

#: Prefix for the blocker text, so a reader knows it was inferred rather than observed.
INFERRED = "blocker (inferred): "

#: Used when no rule above matches.  Still actionable: it names the two ways such a
#: question gets settled, and asks the next session to say which one it is.
UNCLASSIFIED = (INFERRED + "settle by dumping the driver/compiler output or by a targeted "
                "probe; no blocker was stated")
LEGACY_UNCLASSIFIED = "not classified; needs a judgment call on what to acquire"


def blocker_for(question: str, status: dict) -> str:
    haystack = question + " " + " ".join(str(v) for v in status.values())
    for pattern, reason in BLOCKERS:
        if re.search(pattern, haystack):
            return INFERRED + reason
    return UNCLASSIFIED


def answer_for(q: dict) -> str:
    """A concrete pointer for an answered question.

    Says *where* in the note the answer lives (the closest heading match), because
    "somewhere above" is not actionable.
    """
    heading = q.get("answered_heading") or "the settled sections above"
    return f'answered by "§{heading}" in this note'


def duplicate_for(q: dict) -> str:
    return f"asked in full in {q.get('duplicate_of', 'another note')}"


def sweep(apply: bool) -> int:
    records = oq.notes()
    questions = oq.extract_questions(records)
    oq.classify(questions, records)
    stat = {rec["path"]: rec["status"] for rec in records}
    by_note: dict[str, list[dict]] = {}
    for q in questions:
        if not q["annotation"]:
            by_note.setdefault(q["note"], []).append(q)

    changed = 0
    counts: Counter = Counter()
    for relpath, items in sorted(by_note.items()):
        path = os.path.join(na.NOTES_DIR, relpath)
        original = na.read(path)
        lines = original.split("\n")
        # Annotate from the bottom up so earlier line numbers stay valid.
        for q in sorted(items, key=lambda e: -e["line"]):
            index = q["line"] - 1
            if index >= len(lines) or not lines[index].strip().startswith(("- ", "* ")):
                continue
            if oq.ANNOTATION.search(lines[index]):
                continue
            kind = q["class"]
            counts[kind] += 1
            if kind == "answered":
                payload = answer_for(q)
            elif kind == "duplicate":
                payload = duplicate_for(q)
            elif kind == "obsolete":
                payload = "premise no longer holds"
            else:
                payload = f'blocked-by "{blocker_for(q["question"], stat.get(relpath, {}))}"'
            lines[index] = lines[index].rstrip() + f"  <!-- open-question: {kind} {payload} -->"
        text = "\n".join(lines)
        if text == original:
            continue
        changed += 1
        if apply:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
    print(f"{'annotated' if apply else 'would annotate'}: {changed} note(s)")
    for kind, count in counts.most_common():
        print(f"  {count:4d}  {kind}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return sweep(args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
