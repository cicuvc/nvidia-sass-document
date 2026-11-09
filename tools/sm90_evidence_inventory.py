#!/usr/bin/env python3
"""Inventory sm_120-origin evidence stored under ``notes/sm90``.

The sm90 directory describes the sm_90 ISA, but much of its silicon evidence was
collected on an RTX 5090 (sm_120).  A note-level ``Evidence`` field cannot by
itself tell a reader which individual sections came from which part, so this
tool records both levels:

* the host set declared by the canonical status block;
* headings and prose lines that explicitly identify sm_120 as the place where a
  result was measured or verified.

It writes a human-readable ledger and a JSON sidecar.  It never edits notes.

Usage
-----
    python3 tools/sm90_evidence_inventory.py
    python3 tools/sm90_evidence_inventory.py --write
    python3 tools/sm90_evidence_inventory.py --check
    python3 tools/sm90_evidence_inventory.py --json /tmp/sm90-evidence.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes_audit as na  # noqa: E402

REPO_ROOT = Path(na.REPO_ROOT)
SM90_ROOT = Path(na.NOTES_DIR) / "sm90"
REPORT_PATH = SM90_ROOT / "SM120_EVIDENCE.md"
JSON_PATH = SM90_ROOT / "sm120_evidence.json"

HARDWARE_RE = re.compile(
    r"\b(?:sm[_ ]?120(?:a)?|RTX\s+5090|GB20\d)\b",
    re.IGNORECASE,
)
VERIFY_RE = re.compile(
    r"\b(?:verified|measured|probed|confirmed|reproduced|observed|"
    r"pass(?:es|ed)|silicon[- ]verified|bit-exact|device-verified|empirically)\b",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$")
NON_EVIDENCE_HEADING_RE = re.compile(
    r"\b(?:comparison|compare|differences?|relationship|also runs on|versus|vs\.?)\b",
    re.IGNORECASE,
)
NON_EVIDENCE_LINE_RE = re.compile(
    r"\b(?:twice|half|same as|compared (?:to|with)|differs? from|difference|"
    r"versus|vs\.?|unlike)\b",
    re.IGNORECASE,
)
AUDIT_LINE_RE = re.compile(r"^\*\*(?:Probe|Audit):\*\*")
STATUS_LINE_RE = re.compile(r"^\*\*[A-Z][^*]+:\*\*")
GENERATED_REPORT_NAMES = {"SM120_EVIDENCE.md"}
GENERATED_LEDGERS = {
    "sm90/MEASUREMENTS.md",
    "sm90/arch/sm90_resilver_audit.md",
}


def relpath(path: Path) -> str:
    return path.relative_to(na.NOTES_DIR).as_posix()


def declared_hosts(tier: str) -> list[str]:
    """Return silicon hosts encoded in a canonical evidence tier."""
    if not tier.endswith("-silicon"):
        return []
    return [part for part in tier[: -len("-silicon")].split("+") if part]


def fenced_mask(lines: list[str]) -> list[bool]:
    """True for lines inside fenced code blocks (including fence delimiters)."""
    out: list[bool] = []
    inside = False
    for line in lines:
        fence = line.lstrip().startswith(("```", "~~~"))
        out.append(inside or fence)
        if fence:
            inside = not inside
    return out


def heading_locations(lines: list[str], fenced: list[bool]) -> dict[int, str]:
    """Map zero-based line index to the nearest preceding level-2+ heading."""
    locations: dict[int, str] = {}
    current = ""
    for index, line in enumerate(lines):
        if not fenced[index]:
            match = HEADING_RE.match(line)
            if match:
                current = match.group(2).strip()
        locations[index] = current
    return locations


def evidence_heading(heading: str) -> bool:
    """Whether a heading explicitly marks sm_120 as a verification host."""
    return bool(
        HARDWARE_RE.search(heading)
        and VERIFY_RE.search(heading)
        and not NON_EVIDENCE_HEADING_RE.search(heading)
    )


def evidence_line(line: str) -> bool:
    """Whether prose explicitly identifies sm_120 as the place work was done."""
    stripped = line.strip()
    if not stripped or stripped.startswith(("<!--", "| `")):
        return False
    if STATUS_LINE_RE.match(stripped) or AUDIT_LINE_RE.match(stripped):
        return False
    if NON_EVIDENCE_LINE_RE.search(stripped):
        return False
    return bool(HARDWARE_RE.search(stripped) and VERIFY_RE.search(stripped))


def classify(note: dict) -> str:
    hosts = set(note["status_hosts"])
    has_sm120 = "sm120" in hosts
    has_sm90 = "sm90" in hosts
    has_section_evidence = bool(note["evidence_sections"] or note["evidence_lines"])
    evidence = note["status_evidence"]

    if has_sm120 and has_sm90:
        return "sm90+sm120"
    if has_sm120 and hosts == {"sm120"}:
        return "sm120-only-status"
    if has_sm120:
        return "sm120+other"
    if evidence == "mixed" and has_section_evidence:
        return "mixed-status"
    if has_section_evidence:
        return "section-only"
    if note["mention_lines"]:
        return "mention-only"
    return "none"


def inspect_note(path: Path) -> dict:
    text = na.read(str(path))
    lines = text.splitlines()
    fenced = fenced_mask(lines)
    locations = heading_locations(lines, fenced)
    status = na.parse_status_block(text)
    tier = status.get("Evidence", "")
    hosts = declared_hosts(tier)

    sections: list[dict] = []
    current_heading = ""
    current: dict | None = None
    for index, line in enumerate(lines):
        if fenced[index]:
            continue
        match = HEADING_RE.match(line)
        if match:
            if current is not None:
                sections.append(current)
            current_heading = match.group(2).strip()
            current = {
                "line": index + 1,
                "level": len(match.group(1)),
                "heading": current_heading,
                "evidence": evidence_heading(current_heading),
                "lines": [],
            }
            continue
        if current is not None and evidence_line(line):
            current["lines"].append(index + 1)
    if current is not None:
        sections.append(current)

    evidence_sections = [
        {
            "line": section["line"],
            "heading": section["heading"],
            "evidence_lines": section["lines"],
        }
        for section in sections
        if section["evidence"]
    ]
    evidence_lines = []
    for index, line in enumerate(lines):
        if fenced[index] or not evidence_line(line):
            continue
        evidence_lines.append(
            {
                "line": index + 1,
                "section": locations[index],
                "text": line.strip(),
            }
        )

    note = {
        "path": relpath(path),
        "kind": na.note_kind(relpath(path)),
        "target_arch": "sm90",
        "title": na.first_heading(text),
        "status": status.get("Status", ""),
        "status_evidence": tier or "(no status block)",
        "status_confidence": status.get("Tier confidence", "unverified"),
        "status_last_verified": status.get("Last verified", ""),
        "status_probe": status.get("Probe", ""),
        "status_open_items": status.get("Open items", ""),
        "status_audit": status.get("Audit", ""),
        "status_hosts": hosts,
        "evidence_sections": evidence_sections,
        "evidence_lines": evidence_lines,
        "mentions": [],
        "mention_lines": 0,
    }
    mentions = []
    for index, line in enumerate(lines):
        if fenced[index] or not HARDWARE_RE.search(line):
            continue
        stripped = line.strip()
        if STATUS_LINE_RE.match(stripped):
            kind = "status"
        elif evidence_line(line):
            kind = "evidence"
        elif line.startswith("#") and evidence_heading(stripped.lstrip("#").strip()):
            kind = "evidence"
        else:
            kind = "mention"
        row = {
            "line": index + 1,
            "section": locations[index],
            "kind": kind,
            "text": stripped,
        }
        note["mentions"].append(row)
        if kind != "status":
            mentions.append(row)
    note["mention_lines"] = len(mentions)
    note["classification"] = classify(note)
    note["has_explicit_evidence"] = bool(evidence_sections or evidence_lines)
    note["relocation_candidate"] = (
        note["kind"] == "arch"
        and note["status_hosts"] == ["sm120"]
        and relpath(path) != "sm90/arch/sm90_resilver_audit.md"
    )
    return note


def collect() -> list[dict]:
    notes = []
    for path in sorted(SM90_ROOT.rglob("*.md")):
        if path.name in GENERATED_REPORT_NAMES or relpath(path) in GENERATED_LEDGERS:
            continue
        notes.append(inspect_note(path))
    return notes


def escape_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def location_text(note: dict) -> str:
    parts = []
    for section in note["evidence_sections"]:
        parts.append(f"L{section['line']} {section['heading']}")
    for claim in note["evidence_lines"]:
        if any(claim["line"] == section["line"] for section in note["evidence_sections"]):
            continue
        parts.append(f"L{claim['line']} claim")
    return "<br>".join(escape_cell(part) for part in parts) or "-"


def render_table(notes: list[dict], include_title: bool = False) -> str:
    if include_title:
        rows = [
            "| note | title | declared evidence | confidence | locations |",
            "|---|---|---|---|---|",
        ]
        for note in notes:
            rows.append(
                f"| [`{note['path']}`](../{note['path']}) | {escape_cell(note['title'])} | "
                f"`{escape_cell(note['status_evidence'])}` | "
                f"`{escape_cell(note['status_confidence'])}` | {location_text(note)} |"
            )
        return "\n".join(rows)

    rows = [
        "| note | declared evidence | confidence | evidence sites | sm120 mentions |",
        "|---|---|---|---:|---:|",
    ]
    for note in notes:
        rows.append(
            f"| [`{note['path']}`](../{note['path']}) | "
            f"`{escape_cell(note['status_evidence'])}` | "
            f"`{escape_cell(note['status_confidence'])}` | {location_text(note)} | "
            f"{note['mention_lines']} |"
        )
    return "\n".join(rows)


def render_markdown(notes: list[dict]) -> str:
    counts = Counter(note["classification"] for note in notes)
    kinds = Counter((note["kind"], note["classification"]) for note in notes)
    dual = [note for note in notes if note["classification"] == "sm90+sm120"]
    sm120_only = [note for note in notes if note["classification"] in
                  ("sm120-only-status", "sm120+other")]
    section_only = [note for note in notes if note["classification"] in
                    ("section-only", "mixed-status")]
    mention_only = [note for note in notes if note["classification"] == "mention-only"]
    relocation = [note for note in notes if note["relocation_candidate"]]
    sm120_status = [
        note for note in notes
        if "sm120" in note["status_hosts"]
    ]
    status_without_sites = [
        note for note in sm120_status if not note["has_explicit_evidence"]
    ]

    lines = [
        "# sm_120 evidence inside notes/sm90",
        "",
        "<!-- generated:sm90-sm120-evidence:begin -->",
        "> Generated by `python3 tools/sm90_evidence_inventory.py --write`.",
        "> Do not hand-edit this file.  The source notes remain authoritative.",
        "",
        "## Scope",
        "",
        "Every note here **targets the sm_90 ISA because of its path**, but its",
        "silicon evidence may have been collected on an RTX 5090 (`sm_120`).",
        "This ledger makes target architecture and evidence architecture separate",
        "facts.  A `sm120-silicon` row does not mean the instruction is Blackwell-only:",
        "it means the note currently has no recorded silicon confirmation on sm_90.",
        "",
        "Evidence locations are explicit sm120 verification headings and prose lines.",
        "A plain cross-architecture comparison or link is counted only as a mention and",
        "is not treated as sm120 evidence.",
        "",
        "## Summary",
        "",
        "| classification | notes | explicit sites | status only | instr | arch |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    classes = [
        "sm120-only-status",
        "sm120+other",
        "sm90+sm120",
        "mixed-status",
        "section-only",
        "mention-only",
        "none",
    ]
    for category in classes:
        total = counts.get(category, 0)
        if not total:
            continue
        explicit = sum(note["has_explicit_evidence"] for note in notes
                       if note["classification"] == category)
        lines.append(
            f"| `{category}` | {total} | {explicit} | {total - explicit} | "
            f"{kinds.get(('instr', category), 0)} | {kinds.get(('arch', category), 0)} |"
        )
    lines += [
        "",
        "`explicit sites` means the note contains an sm120 verification heading or",
        "prose line. `status only` means the status block claims sm120 but this scan",
        "found no locatable sm120 verification statement; many of those are",
        "folder-default assumptions and must be confirmed before migration.",
        "",
        "### Status confidence",
        "",
        "| confidence | sm120 status notes | explicit sites | status only |",
        "|---|---:|---:|---:|",
    ]
    for confidence in ("high", "medium", "low", "unverified"):
        subset = [note for note in sm120_status
                  if note["status_confidence"] == confidence]
        if not subset:
            continue
        explicit = sum(note["has_explicit_evidence"] for note in subset)
        lines.append(
            f"| `{confidence}` | {len(subset)} | {explicit} | {len(subset) - explicit} |"
        )
    lines += [
        "",
        "The migration order is deliberate:",
        "",
        "1. Preserve notes with independent sm90 and sm120 evidence as dual-site records.",
        "2. Move a note's authoritative claims to `sm120/` when the concrete semantics",
        "   have only been established on sm120.",
        "3. For dual-site material, keep one architecture-specific record under each",
        "   tree and link the counterparts.",
        "4. Promote cross-architecture syntheses with no single target ISA to top-level",
        "   `notes/*.md`.",
        "",
        "## Dual-site evidence",
        "",
        "These notes contain both sm_90 and sm_120 evidence. They must not be collapsed",
        "to either a hoisted `sm90-silicon` or `sm120-silicon` tier.",
        "",
        render_table(dual, include_title=True),
        "",
        "## Status-block sm120 claims",
        "",
        "The status block declares sm120 as the only silicon host.  For instruction",
        "notes, this is usually an sm_90 ISA note whose measurements still need a",
        "Hopper rerun; for architecture notes, it may also mean the file belongs under",
        "`notes/sm120/` after review.  A low-confidence row without an evidence site is",
        "not proof of an sm120 measurement yet.",
        "",
        render_table(sm120_only),
        "",
    ]
    if section_only:
        lines += [
            "## Section-level evidence not declared by the status block",
            "",
            "These are cleanup targets because a reader looking only at `Evidence:`",
            "would miss a section that came from sm_120.",
            "",
            render_table(section_only),
            "",
        ]
    lines += [
        "## Status claims with no locatable evidence site",
        "",
        "These notes claim sm120 in their status block, but no explicit sm120 verification",
        "heading or sentence was found by this inventory.  They are the first candidates",
        "for correcting the status block rather than moving prose.",
        "",
        "<details>",
        "<summary>Show status-only sm120 notes</summary>",
        "",
        "| note | declared evidence | confidence | sm120 mentions |",
        "|---|---|---|---:|",
    ]
    for note in status_without_sites:
        lines.append(
            f"| [`{note['path']}`](../{note['path']}) | "
            f"`{escape_cell(note['status_evidence'])}` | "
            f"`{escape_cell(note['status_confidence'])}` | {note['mention_lines']} |"
        )
    lines += [
        "",
        "</details>",
        "",
        "## Architecture-note relocation review",
        "",
        "These architecture notes currently declare sm120 as their only silicon host.",
        "They are candidates for moving to `notes/sm120/arch/`, but each needs a manual",
        "scope check: a common sm_90/sm_120 mechanism can legitimately stay under sm90.",
        "",
        render_table(relocation, include_title=True),
        "",
        "## Mention-only references",
        "",
        "These files mention sm120 but contain no explicit sm120 verification statement.",
        "They are not evidence contamination by this inventory's rules.",
        "",
        "<details>",
        "<summary>Show mention-only files</summary>",
        "",
        "| note | declared evidence | sm120 mentions |",
        "|---|---|---:|",
    ]
    for note in mention_only:
        lines.append(
            f"| [`{note['path']}`](../{note['path']}) | "
            f"`{escape_cell(note['status_evidence'])}` | {note['mention_lines']} |"
        )
    lines += [
        "",
        "</details>",
        "",
        "## Machine-readable data",
        "",
        "The same inventory is written to",
        "[`sm120_evidence.json`](sm120_evidence.json).  It records exact line numbers and",
        "declared hosts for the future web catalog and migration tooling.",
        "<!-- generated:sm90-sm120-evidence:end -->",
        "",
    ]
    return "\n".join(lines)


def inventory_document(notes: list[dict]) -> dict:
    return {
        "schema": 1,
        "target_arch": "sm90",
        "source_root": "notes/sm90",
        "classification_rule": (
            "Target architecture is the directory; evidence hosts come from the "
            "canonical Evidence tier plus explicit sm120 verification headings/lines."
        ),
        "summary": dict(sorted(Counter(n["classification"] for n in notes).items())),
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the ledger and JSON")
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    parser.add_argument("--json", help="write only the JSON inventory to this path")
    args = parser.parse_args(argv)

    notes = collect()
    payload = inventory_document(notes)
    markdown = render_markdown(notes)
    json_text = json.dumps(payload, indent=2, sort_keys=False) + "\n"

    if args.json:
        Path(args.json).write_text(json_text, encoding="utf-8")
        print(f"wrote {args.json}")
        return 0

    if args.write:
        REPORT_PATH.write_text(markdown, encoding="utf-8")
        JSON_PATH.write_text(json_text, encoding="utf-8")
        print(f"wrote {REPORT_PATH.relative_to(REPO_ROOT)}")
        print(f"wrote {JSON_PATH.relative_to(REPO_ROOT)}")
        print(f"notes: {len(notes)}  classifications: {dict(payload['summary'])}")
        return 0

    stale = []
    if not REPORT_PATH.exists() or REPORT_PATH.read_text(encoding="utf-8") != markdown:
        stale.append(str(REPORT_PATH.relative_to(REPO_ROOT)))
    if not JSON_PATH.exists() or JSON_PATH.read_text(encoding="utf-8") != json_text:
        stale.append(str(JSON_PATH.relative_to(REPO_ROOT)))
    if args.check and stale:
        print("stale: " + ", ".join(stale))
        return 1
    print(f"notes: {len(notes)}  classifications: {dict(payload['summary'])}")
    if stale:
        print("stale: " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
