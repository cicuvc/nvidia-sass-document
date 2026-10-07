#!/usr/bin/env python3
"""Index every sm_120 hardware measurement and where its numbers live.

The repo measured a lot of behaviour on an RTX 5090 (GB202, sm_120) while the instruction
reference lived at ``notes/sm90/`` (the *sm_90* ISA).  ``tools/sm120_notes_gen.py`` gives
each sm_120 instruction a note; this tool answers the other half of the question: *which
note holds the measured numbers for this instruction, and what was measured?*

It is deliberately an index, not a copy.  Duplicating numbers into a second file is how
this repo got into trouble in the first place, so the index points at the authoritative
note and summarises the kind of measurement it holds.

Usage
-----
    python3 tools/sm120_measurements_index.py                    # summary
    python3 tools/sm120_measurements_index.py --write            # write the index note
    python3 tools/sm120_measurements_index.py --check            # fail if stale
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes_audit as na   # noqa: E402

REPO_ROOT = na.REPO_ROOT
DEST = os.path.join(na.NOTES_DIR, "sm120", "measurements_index.md")
BEGIN = "<!-- generated:measurements-index:begin -->"
END = "<!-- generated:measurements-index:end -->"

#: Headings that mean "how we know this", used to summarise a measurement note.
RE_METHOD_HEADING = re.compile(
    r"(?im)^#{2,3}\s+.*\b(probe|method|measurement|reproduce|reproducer|result|matrix|"
    r"sweep|test|experiment|finding)\b.*$")


def measurement_notes() -> dict[str, list[dict]]:
    """``source tree`` -> records whose evidence came from sm_120 silicon."""
    out: dict[str, list[dict]] = defaultdict(list)
    for rec in na.collect():
        evidence = rec["status"].get("Evidence") or ""
        if "sm120" not in evidence:
            continue
        tree = "notes/sm90" if rec["path"].startswith("sm90/") else (
            "notes/sm120" if rec["path"].startswith("sm120/") else "notes/other")
        rec["_evidence"] = evidence
        out[tree].append(rec)
    for tree in out:
        out[tree].sort(key=lambda r: r["path"])
    return out


def measured_mnemonics() -> dict[str, str]:
    """``MNEMONIC`` -> the note that holds its sm_120 measurement."""
    out = {}
    for rec in na.collect():
        if "/instr/" not in rec["path"]:
            continue
        if "sm120" not in (rec["status"].get("Evidence") or ""):
            continue
        out[rec["path"].rsplit("/", 1)[-1][:-3].upper()] = rec["path"]
    return out


def first_method_headings(text: str, limit: int = 3) -> list[str]:
    seen, out = set(), []
    for match in RE_METHOD_HEADING.finditer(text):
        title = match.group(0).lstrip("# ").strip()
        if title.lower() in seen:
            continue
        seen.add(title.lower())
        out.append(title)
        if len(out) >= limit:
            break
    return out


def render(trees: dict[str, list[dict]], mnemonics: dict[str, str]) -> str:
    total = sum(len(v) for v in trees.values())
    lines = [
        "# sm_120 measurements — where the numbers are",
        "",
        "**Architecture:** RTX 5090 / GB202 (sm_120) unless a row says otherwise.  Compiled by",
        "`tools/sm120_measurements_index.py`; this is an **index**, not a copy — each row points",
        "at the note that produced the number.  Duplicating measurements is what made the notes",
        "ambiguous to begin with, so read the source note before quoting a figure.",
        "",
        f"Notes carrying sm_120 silicon evidence: **{total}**.",
        "The per-instruction sm_120 notes link back here; see also",
        "[`notes/sm120/index.md`](index.md) for the architecture notes.",
        "",
        BEGIN,
        "## Per-instruction measurements",
        "",
        "| instruction | sm_120 note | where the numbers live |",
        "|---|---|---|",
    ]
    for mnem in sorted(mnemonics):
        source = mnemonics[mnem]
        local = f"`instr/{mnem.lower()}.md`" if os.path.exists(
            os.path.join(na.NOTES_DIR, "sm120", "instr", f"{mnem.lower()}.md")) else "-"
        lines.append(f"| `{mnem}` | {local} | [`{source}`](../{source.replace('notes/', '')}) |")

    for tree, records in sorted(trees.items()):
        lines += ["", f"## Measurements recorded under `{tree}`", "",
                  "| note | evidence | open items | what it holds |",
                  "|---|---|---:|---|"]
        for rec in records:
            text = na.read(os.path.join(na.NOTES_DIR, rec["path"]))
            topics = first_method_headings(text)
            lines.append("| `{}` | {} | {} | {} |".format(
                rec["path"], rec["_evidence"], rec["open_question_sections"],
                "; ".join(t[:60] for t in topics) or "-"))
    lines += ["", END, ""]
    return "\n".join(lines)


def upsert(text: str) -> str:
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        return text[:start] + text[start:end] + text[end:]
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    trees = measurement_notes()
    mnemonics = measured_mnemonics()
    text = render(trees, mnemonics)

    if args.check:
        norm = lambda s: s.replace("\r\n", "\n").rstrip("\n")  # noqa: E731
        if not os.path.exists(DEST) or norm(na.read(DEST)) != norm(text):
            print(f"CHECK FAILED: {os.path.relpath(DEST, REPO_ROOT)} is stale", file=sys.stderr)
            return 1
        print("CHECK OK: measurements index up to date")
        return 0
    if args.write:
        os.makedirs(os.path.dirname(DEST), exist_ok=True)
        with open(DEST, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote {os.path.relpath(DEST, REPO_ROOT)} "
              f"({sum(len(v) for v in trees.values())} notes, {len(mnemonics)} instructions)")
        return 0

    print(f"sm_120 measurement notes: {sum(len(v) for v in trees.values())}")
    for tree in sorted(trees):
        print(f"  {tree:14s} {len(trees[tree])}")
    print(f"instructions with a measured note: {len(mnemonics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
