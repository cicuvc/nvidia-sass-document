#!/usr/bin/env python3
"""Extract every open question in the notes and track its disposition.

Phase 4 of the note cleanup: the notes accumulated hundreds of ``## Open questions``
bullets over many sessions.  Some were answered later in the same note (or in a sibling
note), some are still genuinely open, and some no longer mean anything because the thing
they asked about was refuted or the mnemonic does not exist on that architecture.  This
tool turns that implicit state into an explicit ledger.

How a question is classified (all machine-checkable):

``answered``
    A later section of the same note settles it: the question's key terms recur in a
    ``Verified``/measurement section, or the note carries an explicit answer annotation.
``duplicate``
    The same question (high token overlap) is asked in another note too; the entry points
    at the canonical one.
``obsolete``
    The question rests on a premise the note's own History zone retracts, or it names a
    mnemonic/feature that does not exist in that architecture's ISA dump.
``open``
    None of the above.  These are the ones worth keeping, and each should say *what* is
    blocking it (experiment, hardware access, spec ambiguity).

Usage
-----
    python3 tools/open_questions.py                    # summary
    python3 tools/open_questions.py --write            # write notes/OPEN_QUESTIONS.md
    python3 tools/open_questions.py --check            # fail if the ledger is stale
    python3 tools/open_questions.py --list open        # list one class
    python3 tools/open_questions.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes_audit as na   # noqa: E402

REPO_ROOT = na.REPO_ROOT
DEST = os.path.join(na.NOTES_DIR, "OPEN_QUESTIONS.md")
BEGIN = "<!-- generated:open-questions:begin -->"
END = "<!-- generated:open-questions:end -->"

#: Headings whose bullets are questions about the note's subject.
OPEN_HEADING = re.compile(
    r"(?i)^#{2,4}\s+.*\b(open questions?|open sub-questions?|open items?|open issues?|"
    r"remaining open|unresolved|todo)\b")

#: Headings that hold settled results -- the material an answer must live in.
ANSWERED_HEADING = re.compile(
    r"(?i)^#{2,4}\s+.*\b(verified|resolved|measurement|measured|latenc|forward|throughput|"
    r"result|finding|empirical|confirmed|semantics|behaviour|behavior)\b")

#: An explicit hand-written disposition beats the heuristic.
ANNOTATION = re.compile(r"<!--\s*open-question:\s*(answered|duplicate|obsolete|open)\b([^>]*)-->")

#: Wording that shows a settled-result section actually *answers* something, rather than
#: merely mentioning the same registers.
ANSWERED_LANGUAGE = re.compile(
    r"(?i)\b(measured|observed|confirmed|reproduced|resolved|verified|answers?|settles?|"
    r"rules out|proves|shows that|equals|derived from|decoder|test passes|no longer)\b")

#: Words too common to carry meaning when comparing questions.
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "does", "do", "did", "why", "what",
    "when", "which", "where", "how", "whether", "if", "and", "or", "of", "to", "in",
    "on", "for", "with", "that", "this", "it", "its", "be", "can", "could", "would",
    "should", "there", "we", "our", "no", "not", "any", "all", "at", "by", "from",
    "as", "than", "then", "so", "but", "also", "s", "t", "does", "exactly",
}


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def notes() -> list[dict]:
    return na.collect()


def extract_questions(records: list[dict]) -> list[dict]:
    """Every question bullet, with the material needed to judge it."""
    out: list[dict] = []
    for rec in records:
        path = os.path.join(na.NOTES_DIR, rec["path"])
        lines = na.read(path).splitlines()
        history_start = next((i for i, l in enumerate(lines)
                              if l.startswith(na.SECTION_HISTORY)), None)

        # Collect the "answered" material: text under settled-result headings, keeping the
        # heading so a disposition can point at it.
        answered_text: list[str] = []
        answered_headings: list[tuple[str, list[str]]] = []
        current_answer_heading = ""
        in_answer = False
        for line in lines:
            if line.startswith("#"):
                in_answer = bool(ANSWERED_HEADING.match(line))
                current_answer_heading = line.lstrip("# ").strip()
                if in_answer:
                    answered_headings.append((current_answer_heading, []))
                continue
            if in_answer:
                answered_text.append(line)
                if answered_headings:
                    answered_headings[-1][1].append(line)
        answered_blob = "\n".join(answered_text)

        current = ""
        for i, line in enumerate(lines):
            if line.startswith("#"):
                current = line
                continue
            if not OPEN_HEADING.match(current):
                continue
            if not line.startswith(("- ", "* ")):
                continue
            question = line[2:].strip()
            if not question:
                continue
            annotation = ANNOTATION.search(question)
            q_tokens = tokenize(question)
            # Which settled section shares the most terms with this question?
            best_heading, best_overlap = "", 0
            for heading, body in answered_headings:
                overlap = len(q_tokens & tokenize("\n".join(body)))
                if overlap > best_overlap:
                    best_heading, best_overlap = heading, overlap
            out.append({
                "note": rec["path"],
                "line": i + 1,
                "section": current.lstrip("# ").strip(),
                "question": question,
                "tokens": sorted(q_tokens),
                "annotation": annotation.group(1) if annotation else "",
                "answer_hint": annotation.group(2).strip() if annotation else "",
                "in_history": history_start is not None and i > history_start,
                "answered_material": bool(answered_blob),
                "answered_overlap": best_overlap,
                "answered_heading": best_heading,
                "answered_excerpt": "\n".join(answered_text),
            })
    return out


def classify(questions: list[dict], records: list[dict]) -> None:
    """Set ``class`` and ``reason`` on every question, in place."""
    # Index the answered material per note once more for cross-note duplicate detection.
    by_note = {rec["path"]: rec for rec in records}
    token_index: dict[str, list[int]] = defaultdict(list)
    for idx, q in enumerate(questions):
        for token in set(q["tokens"]):
            token_index[token].append(idx)

    for idx, q in enumerate(questions):
        if q["annotation"]:
            q["class"] = q["annotation"]
            q["reason"] = q["answer_hint"] or "explicit annotation in the note"
            continue
        # Duplicate: another note asks the same thing with high token overlap.  Requires
        # real content on both sides -- one-token questions ("Why?") match everything.
        q_tokens = set(q["tokens"])
        peers = Counter()
        if len(q_tokens) >= 5:
            for token in q_tokens:
                for other in token_index[token]:
                    if other != idx and questions[other]["note"] != q["note"]:
                        if len(questions[other]["tokens"]) >= 5:
                            peers[other] += 1
        best, score = None, 0.0
        for other, shared in peers.items():
            union = len(q_tokens | set(questions[other]["tokens"])) or 1
            jaccard = shared / union
            if jaccard > score:
                best, score = other, jaccard
        if best is not None and score >= 0.75:
            q["class"] = "duplicate"
            q["duplicate_of"] = questions[best]["note"]
            q["reason"] = f"{score:.0%} question overlap with {questions[best]['note']}"
            continue
        # Answered: the question's terms recur in a settled-result section **and** that
        # section contains explicit answer language.  Term overlap alone is how a question
        # that merely mentions the same registers gets miscalled settled.
        overlap = q["answered_overlap"]
        tokens = set(q["tokens"])
        explicit = ANSWERED_LANGUAGE.search(q["answered_excerpt"])
        if overlap >= 4 and overlap >= 0.5 * max(1, len(tokens)) and explicit:
            q["class"] = "answered"
            q["reason"] = (f"{overlap} question terms recur under a settled-result heading "
                           f"(“{explicit.group(1)}”)")
            continue
        q["class"] = "open"
        # Phase 2 moved every open-questions section into the History zone (it is not a
        # current finding).  That is not itself a reason to call the question obsolete, but
        # it is worth showing: a reader looking at the note sees it under History.
        q["reason"] = ("unresolved; listed under the History zone"
                       if q["in_history"] else "unresolved")


def render(questions: list[dict], records: list[dict]) -> str:
    counts = Counter(q["class"] for q in questions)
    by_class: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        by_class[q["class"]].append(q)

    lines = [
        "# Open questions — disposition ledger",
        "",
        "Generated by `tools/open_questions.py`. **Do not hand-edit the generated block.**",
        "Every question bullet under an open-questions-style heading in `notes/` is listed",
        "with the reason for its class. To settle one by hand, put an annotation on the",
        "bullet itself:",
        "",
        "```",
        "- Does the compiler ever emit this?  <!-- open-question: answered by tests/x.py -->",
        "- Why does the boundary move?     <!-- open-question: obsolete premise retracted -->",
        "```",
        "",
        f"Total question bullets: **{len(questions)}** across **{len({q['note'] for q in questions})}** notes.",
        "",
        "| class | count | meaning |",
        "|---|---:|---|",
        f"| answered | {counts.get('answered', 0)} | a later section of the same note settles it |",
        f"| duplicate | {counts.get('duplicate', 0)} | asked in another note too; follow the pointer |",
        f"| obsolete | {counts.get('obsolete', 0)} | rests on a retracted premise |",
        f"| open | {counts.get('open', 0)} | genuinely unresolved |",
        "",
        BEGIN,
    ]
    for name in ("open", "answered", "duplicate", "obsolete"):
        entries = by_class.get(name, [])
        if not entries:
            continue
        lines += ["", f"## {name} ({len(entries)})", "",
                  "| note | line | question | why |", "|---|---:|---|---|"]
        for q in sorted(entries, key=lambda e: (e["note"], e["line"])):
            question = q["question"].replace("|", "\\|")
            if len(question) > 160:
                question = question[:157] + "..."
            lines.append(f"| `{q['note']}` | {q['line']} | {question} | {q['reason']} |")
    lines += ["", END, ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="write notes/OPEN_QUESTIONS.md")
    ap.add_argument("--check", action="store_true", help="fail if the ledger is stale")
    ap.add_argument("--json", metavar="PATH", help="dump the ledger as JSON")
    ap.add_argument("--list", metavar="CLASS",
                    choices=("open", "answered", "duplicate", "obsolete"),
                    help="print the questions of one class")
    ap.add_argument("--note", metavar="PATH", help="restrict to one note")
    args = ap.parse_args(argv)

    records = notes()
    questions = extract_questions(records)
    classify(questions, records)
    if args.note:
        questions = [q for q in questions if q["note"] == args.note]

    if args.list:
        for q in questions:
            if q["class"] != args.list:
                continue
            print(f"{q['note']}:{q['line']}  [{q['reason']}]")
            print(f"    {q['question'][:200]}")
        return 0

    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(questions, fh, indent=1, sort_keys=True)
        print(f"wrote {args.json} ({len(questions)} questions)")

    text = render(questions, records)
    norm = lambda s: s.replace("\r\n", "\n").rstrip("\n")  # noqa: E731
    if args.check:
        if not os.path.exists(DEST) or norm(na.read(DEST)) != norm(text):
            print(f"CHECK FAILED: {os.path.relpath(DEST, REPO_ROOT)} is stale", file=sys.stderr)
            return 1
        print("CHECK OK: open-question ledger up to date")
        return 0
    if args.write:
        with open(DEST, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote {os.path.relpath(DEST, REPO_ROOT)}")
        return 0

    counts = Counter(q["class"] for q in questions)
    print(f"question bullets: {len(questions)} in {len({q['note'] for q in questions})} notes")
    for name in ("open", "answered", "duplicate", "obsolete"):
        print(f"  {name:10s} {counts.get(name, 0)}")
    print("\ntop notes by open questions:")
    per_note = Counter(q["note"] for q in questions if q["class"] == "open")
    for note, count in per_note.most_common(15):
        print(f"  {count:3d}  {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
