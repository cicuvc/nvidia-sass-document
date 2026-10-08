#!/usr/bin/env python3
"""Audit the research notes under ``notes/`` for stale / superseded / unverified content.

Why this exists
---------------
The notes grew by *appending* new measurements on top of older hypotheses.  A reader
can therefore no longer tell, from a sentence alone, whether it is

  * a spec-derived fact,
  * a silicon measurement (and on which GPU),
  * the original guess that was later confirmed or refuted.

This tool turns that implicit state into an explicit, machine-checkable one.  It is
read-only: it never edits a note.  ``--check`` returns a non-zero exit code when a
note violates the conventions, so it can gate a test run.

Usage
-----
    python3 tools/notes_audit.py                    # human summary to stdout
    python3 tools/notes_audit.py --json out.json    # machine-readable inventory
    python3 tools/notes_audit.py --check            # exit 1 on convention violations
    python3 tools/notes_audit.py --write-baseline notes/AUDIT_BASELINE.md

Only the standard library is used (repo convention: no third-party deps).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES_DIR = os.path.join(REPO_ROOT, "notes")

# ---------------------------------------------------------------------------
# Conventions (single source of truth for this tool)
# ---------------------------------------------------------------------------

#: Marker emitted by the canonical status block.  Kept as an HTML comment so it is
#: invisible in rendered markdown but greppable and stable.
STATUS_MARKER = "<!-- notes-status -->"

#: Legacy banner written by the sm120-archive commit; it is superseded by the status
#: block, and ``tools/notes_migrate.py`` rewrites it into that block.
LEGACY_BANNER = "<!-- arch-scope-banner -->"

#: Allowed ``Evidence:`` tiers inside a status block.  Written as ``<arch>-silicon``
#: (or ``<arch>+<arch>-silicon`` for a dual-site result) so the note states where the
#: measurement was made.
EVIDENCE_SIMPLE_TIERS = ("spec", "synthetic", "mixed", "unpinned")
EVIDENCE_ARCHES = ("sm70", "sm75", "sm80", "sm89", "sm90", "sm100", "sm103", "sm120")
EVIDENCE_TIERS = EVIDENCE_SIMPLE_TIERS + tuple(f"{a}-silicon" for a in EVIDENCE_ARCHES)


def is_valid_tier(tier: str) -> bool:
    """True for ``spec``/``synthetic``/``mixed``/``unpinned`` or a ``<arch>[+<arch>]-silicon``."""
    if tier in EVIDENCE_SIMPLE_TIERS:
        return True
    if not tier.endswith("-silicon"):
        return False
    parts = tier[: -len("-silicon")].split("+")
    return bool(parts) and all(p in EVIDENCE_ARCHES for p in parts) and len(set(parts)) == len(parts)

#: Allowed ``Status:`` fields inside a status block.
STATUS_FIELDS = ("active", "historical", "superseded", "stub")

#: Value used when a note's measurement host could not be established from its own text:
#: the block then says so instead of asserting a tier.
EVIDENCE_UNPINNED = "unpinned"

#: Every field the canonical block may carry, and whether ``--check`` requires it.
STATUS_FIELDS_SPEC = ("Status", "Evidence", "Tier confidence", "Last verified", "Probe",
                      "Open items", "Supersedes")

#: Canonical section headings introduced by the phase-2 partition.
SECTION_CONCLUSION = "## Conclusion"
SECTION_EVIDENCE = "## Evidence"
SECTION_HISTORY = "## History / retracted hypotheses"

#: Headings that record a *verification act on hardware*.  Legacy spellings:
#: ``## Resolved: ...``, ``## Silicon-verified ...``, ``## Verified ... (sm120, date)``.
#: Plain ``## Verified encodings`` sections are spec/cuobjdump vectors, not silicon
#: evidence, so they are deliberately excluded (a status block covers them instead).
#: A hardware token anywhere in the heading is what makes it a silicon claim; the
#: ``(?!encodings?\\b)`` guard keeps the toolchain-provenance sections out.
RE_VERIFIED_HEADING = re.compile(
    r"^#{2,3}\s+(?:\d+(?:\.\d+)*\s*[.)]?\s*)?(?!Verified\s+encodings?\b)"
    r"(?=.*\b(?:Resolved|Silicon[-\s]verified|Verified|Verified\b)\b)"
    r"(?=.*(?:\bsm[_ ]?\d{2,3}[a-z]?\b|\bH20\b|\bH100\b|\bH200\b|\bB200\b|\bB300\b|"
    r"\bGB20\d\b|\bGH100\b|RTX 5090|RTX 4090|\bA100\b|\bV100\b|silicon|bit-level|"
    r"empirical|hand-built))"
    r".*$",
    re.MULTILINE)
#: Explicit "where this was measured" header line, e.g.
#: ``Silicon: RTX 5090 (GB202, sm_120), 2026-09-16.  Reproducer: ...``
RE_SILICON_LINE = re.compile(
    r"(?im)^(?:>|\*{0,2})?\s*\*{0,2}(?:Silicon|Hardware|Platform|GPU|Measured on)\*{0,2}\s*[:\uFF1A]\s*(.+)$")
#: ``> **Status: silicon-verified on H20 (sm_90), 2026-08.**`` and friends.
RE_SILICON_PROSE = re.compile(
    r"(?i)silicon[- ]verified|verified on (?:real )?(?:silicon|hardware)|"
    r"on (?:the )?(?:RTX|H20|H100|B200|B300|GB202|GH100|Modal)")
#: Architecture tokens -> canonical arch label.
ARCH_TOKENS = (
    ("sm70", r"sm[_ ]?70|Volta"),
    ("sm80", r"sm[_ ]?80|GA100|A100"),
    ("sm89", r"sm[_ ]?89|Ada|AD10\d"),
    ("sm90", r"sm[_ ]?90|GH100|H100|H20|H800|Hopper"),
    ("sm100", r"sm[_ ]?100|GB100|B200"),
    ("sm103", r"sm[_ ]?103|B300"),
    ("sm120", r"sm[_ ]?120|GB20\d|RTX 5090"),
)
#: Hand-curated per-note overrides (tier/date/status/notes) used to correct or
#: confirm what the heuristics guessed.
OVERRIDES_PATH = os.path.join(NOTES_DIR, "notes_status_overrides.json")

#: Date stamp anywhere in a heading, e.g. ``(SM120, 2026-08)``.
RE_DATE = re.compile(r"20\d\d-\d\d(?:-\d\d)?")
#: ``## Open questions`` and friends.
RE_OPEN = re.compile(r"^#{2,4}\s+.*(Open questions|Open sub-questions|Open items|"
                                     r"Remaining open|Unresolved|TODO)\b.*$",
                     re.IGNORECASE | re.MULTILINE)
#: Markers that a *statement about the note* was later retracted.  Deliberately narrow:
#: bare hardware words ("superseded", "stale", "disproven") describe registers and queue
#: entries, not note provenance, and would produce mostly false positives.  Likewise,
#: "an earlier exploratory run ... is superseded" is *provenance attribution* inside a
#: current claim, not a retracted claim, so it must not be flagged.
RE_RETRACT = re.compile(r"(?i)("
                        r"\bretracted\b|\bretraction\b|"
                        r"(?:earlier|previous|original|older) (?:version|claim|note|hypothesis|"
                        r"conclusion|interpretation|theory|reading|guess|assumption|figure|number)"
                        r"[^.\n]{0,80}?\b(?:was|were|is|are|has been|have been)\b[^.\n]{0,20}?"
                        r"(?:wrong|incorrect|disproven|refuted|superseded|withdrawn|abandoned|"
                        r"obsolete)|"
                        r"\bwas (?:wrong|incorrect|disproven|refuted|superseded|withdrawn)\b|"
                        r"\bwere (?:wrong|incorrect|disproven|refuted|superseded|withdrawn)\b|"
                        r"has been superseded|is superseded by|now known to be"
                        r"|no longer holds|turned out to be"
                        r"|作废|此前(?:的)?(?:结论|假设|猜测|观察|数据|尝试)"
                        r")")
#: Explicit "this section is only round-trip tested" markers.
RE_SYNTHETIC = re.compile(r"(?i)\bSYNTHETIC\b")
#: Weak-claim language worth flagging for a status-tier review.
RE_HEDGE = re.compile(r"(?i)\b(likely|presumably|probably|we guess|assume|"
                      r"assumption|hypothesis|hypothes|speculat|unverified|unclear|"
                      r"not yet (?:verified|probed|confirmed)|appears to)\b")
#: A pointer that tells the reader another file supersedes this one.
RE_SUPERSEDE_POINTER = re.compile(r"(?i)(superseded by|supersedes|see `[^`]+`\s+instead|"
                                  r"replaced by|作废|已被.*取代)")
#: Machine-checked fields inside a status block.
def _field_regex(*names: str) -> str:
    """A ``**Name:** value`` matcher for the given status-block field names.

    The name is a capturing group and the value a second one, so callers can use both
    ``re.match`` (checking membership) and ``finditer`` (reading values).
    """
    return r"^\*\*(" + "|".join(re.escape(n) for n in names) + r"):\*\*"


#: Machine-checked fields inside a status block, in the order they are written.  The
#: block is derived from the note, so every consumer must agree on this list.
STATUS_BLOCK_FIELDS = ("Status", "Evidence", "Tier confidence", "Last verified", "Probe",
                       "Open items", "Supersedes", "Audit")
RE_STATUS_FIELD = re.compile(_field_regex(*STATUS_BLOCK_FIELDS) + r"\s*(.*)$", re.MULTILINE)
#: Same list as a free-standing pattern (for ``re.match`` on a single line).
RE_STATUS_FIELD_LINE = re.compile(_field_regex(*STATUS_BLOCK_FIELDS))
#: ``- [ ]`` checkbox that is still unticked in a tracking note.
RE_UNCHECKED = re.compile(r"^\s*[-*]\s+\[ \]")
#: Files under ``notes/`` that are not research notes and therefore carry no status block:
#: the audit's own baseline, the hand-curated override table, and the tracking ledgers
#: (whose bodies are historical prose but whose live content is the generated block).
NON_NOTE_FILES = {
    "AUDIT_BASELINE.md",
    "notes_status_overrides.json",
    "OPEN_QUESTIONS.md",
    "sm120/measurements_index.md",
}
#: Basenames that are generated ledgers for *every* architecture, so they are matched by
#: name rather than path (e.g. `notes/sm89/MEASUREMENTS.md`).
NON_NOTE_BASENAMES = {"MEASUREMENTS.md"}
LEDGER_FILES = {
    "sm120/silver-status.md",
    "sm90/arch/sm90_resilver_audit.md",
}


def rel(path: str) -> str:
    return os.path.relpath(path, NOTES_DIR).replace(os.sep, "/")


def note_kind(relpath: str) -> str:
    """Classify a note by where it lives."""
    parts = relpath.split("/")
    if len(parts) >= 3 and parts[-2] == "instr":
        return "instr"
    if len(parts) >= 3 and parts[-2] == "arch":
        return "arch"
    if len(parts) == 2:
        return "arch"
    return "top"


def arch_of(relpath: str) -> str:
    head = relpath.split("/")[0]
    return head if re.fullmatch(r"sm\d+", head) else "general"


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
        if line.strip():
            return line.strip()[:120]
    return ""


def parse_status_block(text: str) -> dict:
    """Return the parsed canonical status block, or ``{}`` when absent."""
    if STATUS_MARKER not in text:
        return {}
    # The block runs from the marker to the first blank line that is followed by a
    # non-field line (fields are ``**Name:** value`` or a continuation).
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines) if STATUS_MARKER in l), None)
    if idx is None:
        return {}
    block = []
    for line in lines[idx + 1:]:
        if RE_STATUS_FIELD.match(line):
            block.append(line)
        elif block and line.strip().startswith(("-", "  ")) and not line.startswith("#"):
            block.append(line)  # continuation of the previous field
        else:
            break
    fields = {}
    for match in RE_STATUS_FIELD.finditer("\n".join(block)):
        fields[match.group(1)] = match.group(2).strip()
    return fields


def archs_in(text: str) -> list[str]:
    """Architectures mentioned in ``text``, in canonical order."""
    return [name for name, pattern in ARCH_TOKENS if re.search(pattern, text)]


def probe_archs(probe: str) -> list[str]:
    """Architectures named in a ``Silicon:`` line (narrower than full-note search)."""
    return archs_in(probe)


#: Where each architecture's notes were actually measured.  ``notes/sm90/`` documents the
#: sm_90 ISA, but most of its probes ran on the locally available RTX 5090 (sm_120) --
#: that mismatch is the single largest source of misreadable evidence in this repo, so the
#: fallback below must never answer "sm90".
ARCH_MEASUREMENT_SITE = {
    "sm70": "sm70",
    "sm80": "sm120",
    "sm89": "sm120",
    "sm90": "sm120",
    "sm100": "sm100",
    "sm103": "sm103",
    "sm120": "sm120",
}
#: Hardware names that prove a note's own measurements were taken on that part.
ARCH_HARDWARE_NAMES = {
    "sm70": r"\bV100\b|GV100",
    "sm80": r"\bA100\b|GA100",
    "sm89": r"\bRTX 40\d0\b|AD10\d",
    "sm90": r"\bH20\b|\bH100\b|\bH200\b|\bH800\b|GH100",
    "sm100": r"\bB200\b|GB100",
    "sm103": r"\bB300\b",
    "sm120": r"\bRTX 5090\b|GB20\d",
}

#: Strong evidence markers, strongest first.  Each entry is (label, regex, tier_rule).
#: ``archs`` means "take the architecture named by the match"; ``fixed`` forces a tier.
STRONG_MARKERS: tuple[tuple[str, str], ...] = (
    ("Silicon: header line", r"(?im)^\s*>?\s*\*{0,2}(?:Silicon|Hardware|Platform|GPU)\*{0,2}\s*[:\uFF1A]"),
    ("Status: line naming hardware",
     r"(?im)^\s*>?\s*\*{0,2}Status\*{0,2}\s*[:\uFF1A][^\n]*"
     r"(?:silicon|RTX|H20|H100|H200|B200|B300|GB202|GH100|sm[_ ]?\d{2,3})"),
    ("'silicon-verified' attestation",
     r"(?i)silicon[-\s]verified|verified on (?:real )?(?:silicon|hardware)"),
    ("hardware named next to a verification verb",
     r"(?i)(?:verified|measured|probed|confirmed|reproduced|observed|run|ran|executed)[^.\n]{0,40}"
     r"(?:RTX 5090|GB202|H20|H100|H200|B200|B300|GH100)|"
     r"(?:RTX 5090|GB202|H20|H100|H200|B200|B300|GH100)[^.\n]{0,40}"
     r"(?:verified|measured|probed|confirmed|reproduced|observed|run|ran|executed)"),
)
#: Marker that a note measured something on hardware whose name it never states.
WEAK_GPU_MARKERS = (
    (r"(?i)\btests/asm_construct/(?:test|probe)_[a-z0-9_]+\.py", "asm_construct test/probe suite"),
    (r"(?i)cudaMemcpy|cuLaunchKernel|CudaModule|cuModuleLoad", "CUDA driver API usage"),
    (r"(?i)\b(?:silicon|on-GPU|on-device|GPU)\s+(?:run|result|verdict|evidence)", "GPU-run wording"),
    (r"(?i)RTX 5090|GB202", "names RTX 5090/GB202"),
    (r"(?i)\bH20\b|\bH100\b|GH100", "names H20/H100/GH100"),
    (r"(?i)\bB200\b|\bB300\b|Modal", "names B200/B300/Modal"),
)


def clean_probe(raw: str) -> str:
    """Turn a regex hit into a readable one-line provenance string.

    A hit that only repeats the tier word ("silicon-verified") carries no information
    beyond the tier itself, so it is dropped rather than shown as if it named a host.
    """
    one = re.sub(r"\s+", " ", raw).strip(" .*>`")
    if not one:
        return ""
    if re.fullmatch(r"(?i)silicon[-\s]verified|verified on (?:real )?hardware|"
                    r"verified|measured|probed|confirmed|reproduced|observed", one):
        return ""
    if len(one) > 160:
        one = one[:157].rstrip() + "..."
    return one


def strip_status_block(text: str) -> str:
    """Drop an existing canonical status block.

    Status blocks are *derived* from the note; letting one feed back into the derivation
    would make the audit (and therefore the migration) non-idempotent.
    """
    if STATUS_MARKER not in text:
        return text
    out, skipping = [], False
    for line in text.splitlines():
        if STATUS_MARKER in line:
            skipping = True
            continue
        if skipping:
            if RE_STATUS_FIELD_LINE.match(line):
                continue
            if not line.strip():
                skipping = False
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


def propose_evidence(text: str, relpath: str) -> dict:
    """Propose {tier, date, probe, basis, confidence} for one note.

    Precedence, strongest evidence first:

    1. an explicit ``Silicon:``/``Status:`` line naming the hardware;
    2. a "silicon-verified" attestation or a hardware name beside a verification verb;
    3. the note's own per-architecture directory (a note under ``notes/sm120/`` reports
       measurements made on that part);
    4. nothing at all -> ``spec`` (never guess "verified": over-claiming is the failure
       mode this whole exercise exists to remove).

    Anything but (1) and (2) is recorded as ``confidence: low`` so the override table can
    confirm or correct it before the status block is written.
    """
    probe = ""
    basis = ""
    confidence = "low"
    text = strip_status_block(text)

    # (1) explicit header / status line
    m = RE_SILICON_LINE.search(text)
    if m:
        probe = m.group(1).strip()
        basis = "explicit `Silicon:` header line"
        confidence = "high"
    else:
        for line in text.splitlines():
            if re.match(r"(?i)^\s*>?\s*\*{0,2}status\*{0,2}\s*[:\uFF1A]", line) and RE_SILICON_PROSE.search(line):
                probe = re.sub(r"^\s*>?\s*", "", line).strip()
                basis = "`Status:` line naming verified hardware"
                confidence = "high"
                break
    if not probe:
        for label, pattern in STRONG_MARKERS:
            hit = re.search(pattern, text)
            if hit:
                probe = hit.group(0).strip()
                basis = label
                confidence = "high" if label != "hardware named next to a verification verb" else "medium"
                break
    if not probe:
        # `**状态：**` / `**探针：**` style headers (the Chinese notes use these).
        m = re.search(r"(?im)^\*\*(?:状态|Status|探测|Silicon|硬件)\*\*\s*[:\uFF1A]\s*(.+)$", text)
        if m:
            probe = m.group(1).strip()
            basis = "`状态/Status` header line"
            confidence = "high"
    probe = clean_probe(probe)

    dates = RE_DATE.findall(text)
    date = max(dates) if dates else ""

    synthetic = bool(RE_SYNTHETIC.search(text))
    verified = bool(RE_VERIFIED_HEADING.search(strip_fenced(text)))

    archs: list[str] = []
    head = relpath.split("/")[0]
    if probe:
        archs = [a for a in probe_archs(probe)]
    if not archs:
        # (3) architecture named in a Resolved/Silicon-verified *heading* (a cross-reference
        # in the body is not evidence for this note).
        heading_archs: list[str] = []
        for line in text.splitlines():
            if line.startswith("##") and RE_VERIFIED_HEADING.match(line):
                heading_archs += archs_in(line)
        if heading_archs:
            archs = sorted(set(heading_archs), key=lambda a: [n for n, _ in ARCH_TOKENS].index(a))
            basis = basis or "architecture named in a Resolved/Silicon-verified heading"
            confidence = "medium"
        elif head in ARCH_MEASUREMENT_SITE:
            # (4) per-architecture directory.  Prefer hardware explicitly named in the note
            # over the folder's nominal part: notes/sm90/ was largely probed on an RTX 5090.
            named = [a for a, pattern in ARCH_HARDWARE_NAMES.items() if re.search(pattern, text)]
            if named:
                archs = sorted(set(named), key=lambda a: [n for n, _ in ARCH_TOKENS].index(a))
                basis = basis or f"hardware named in the note ({', '.join(archs)})"
                if len(archs) == 1:
                    confidence = "medium"
            else:
                archs = [ARCH_MEASUREMENT_SITE[head]]
                basis = basis or (f"lives under notes/{head}/; no part named, so the default "
                                  f"measurement site {ARCH_MEASUREMENT_SITE[head]} is assumed")
        elif not probe and not verified:
            archs = []

    # Fall back to the weakest marker only when a note claims measurement but names no part.
    if not archs and (verified or RE_SILICON_PROSE.search(text)):
        for pattern, label in WEAK_GPU_MARKERS:
            if re.search(pattern, text):
                basis = basis or f"claims a run ({label}); part unnamed"
                break

    # `synthetic` is reserved for notes whose *only* evidence is a constructed encoding:
    # a note that also carries a verification heading or names a part is not synthetic, and
    # saying so would understate it.
    if synthetic and not verified and not probe and not archs:
        return {"tier": "synthetic", "date": date, "probe": probe,
                "basis": basis or "SYNTHETIC section only; no measurement marker",
                "confidence": "medium"}
    if archs:
        tier = f"{archs[0]}-silicon" if len(archs) == 1 else "mixed"
        if len(archs) > 1:
            confidence = "low"
        return {"tier": tier, "date": date, "probe": probe, "basis": basis, "confidence": confidence}
    if probe or verified:
        return {"tier": "mixed", "date": date, "probe": probe,
                "basis": basis or "claims a run; part unnamed", "confidence": "low"}
    return {"tier": "spec", "date": date, "probe": probe, "basis": basis or "no measurement marker",
            "confidence": "medium"}


def provenance_note(lines: list[str], heading_line: int) -> str:
    """The ``<!-- provenance: ... -->`` note on the line after a heading, if any."""
    index = heading_line  # heading_line is 1-based, so this is the next line
    if 0 <= index < len(lines) and lines[index].strip().startswith("<!-- provenance"):
        return lines[index].strip()
    return ""


def count_open_items(lines: list[str], open_sections: list[tuple[int, str]]) -> int:
    """Count bullet lines inside every open-question section."""
    starts = [idx for idx, _ in open_sections]
    total = 0
    for start in starts:
        for line in lines[start:]:            # start is 1-based, so this is the line *after* the heading
            if re.match(r"^#{1,4}\s", line):
                break
            if line.startswith(("- ", "* ")):
                total += 1
    return total


def strip_fenced(text: str) -> str:
    """Drop fenced code blocks so quoted SASS/JSON cannot trip the prose heuristics."""
    out, inside = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    return "\n".join(out)


#: Boilerplate the migrator itself writes; counting it as note content would make the
#: audit measure its own scaffolding instead of the research.
RE_OWN_SCAFFOLD = re.compile(
    r"^(\*\*(?:Status|Evidence|Tier confidence|Last verified|Probe|Open items|Supersedes|"
    r"Audit):\*\*|## (?:Conclusion|Evidence)|## History / retracted hypotheses$|"
    r"> Claims below were|> for provenance\.|_\(no summary in the source note)")


def strip_own_scaffold(text: str) -> str:
    """Drop status-block fields, zone headings/disclaimers and the migrator's annotations."""
    return "\n".join(l for l in text.splitlines()
                     if not RE_OWN_SCAFFOLD.match(l.strip())
                     and not l.strip().startswith(("<!-- notes-status", "<!-- provenance",
                                                    "<!-- curated:", "<!-- note:")))


def audit_file(path: str) -> dict:
    relpath = rel(path)
    text = read(path)
    lines = text.splitlines()
    prose = strip_own_scaffold(strip_fenced(text))
    verified = [(ln, l.lstrip("# ").strip()) for ln, l in
                ((i + 1, l) for i, l in enumerate(lines) if l.startswith("##"))
                if RE_VERIFIED_HEADING.match(l)]
    open_sections = [(i + 1, l.strip()) for i, l in enumerate(lines) if RE_OPEN.match(l)]
    retracts = [(i + 1, l.strip()) for i, l in enumerate(prose.splitlines()) if RE_RETRACT.search(l)]
    hedges = len(RE_HEDGE.findall(prose))
    unchecked = len(RE_UNCHECKED.findall(text))
    status = parse_status_block(text)
    proposal = propose_evidence(text, relpath)
    # An explicit `Evidence:` field is a human/generator decision and outranks the
    # heuristic; the heuristic is only recorded as the second opinion.
    tier = status.get("Evidence") or proposal["tier"]
    tier_reasons = [f"status block says {tier}"] if status.get("Evidence") \
        else ([proposal["basis"]] if proposal["basis"] else [])
    # A heading counts as dated when it carries a date, or when the migrator placed a
    # provenance note directly underneath it.
    redacted = [h for ln, h in verified
                if not RE_DATE.search(h) and not provenance_note(lines, ln)]
    has_history = SECTION_HISTORY in text
    has_conclusion = SECTION_CONCLUSION in text
    has_evidence_sec = SECTION_EVIDENCE in text
    strikethrough = prose.count("~~") // 2

    issues = []
    is_ledger = relpath in LEDGER_FILES
    if not status and not is_ledger:
        issues.append("no-status-block")
    if not has_conclusion and note_kind(relpath) in ("instr", "arch") and not is_ledger:
        issues.append("no-conclusion-section")
    # A retraction is "partitioned" when it lives under the History zone, or when the note
    # explicitly declares that it quotes the retraction in place to justify the current
    # finding (the visible retraction note written by tools/notes_curate_retractions.py).
    curated = "**Retraction note:**" in text
    if not has_history and (retracts or strikethrough) and not curated:
        issues.append("retractions-unpartitioned")
    if redacted:
        issues.append(f"undated-verified-heading({len(redacted)})")
    if not open_sections and note_kind(relpath) == "instr":
        issues.append("no-open-questions-section")
    if RE_SUPERSEDE_POINTER.search("\n".join(lines[:15])) and "Supersedes" not in status:
        issues.append("supersede-pointer-without-field")
    if is_ledger:
        issues.append("ledger-needs-regeneration")
    if status and status.get("Evidence") and not is_valid_tier(status["Evidence"]):
        issues.append("bad-evidence-tier")
    if status and status.get("Status") and status["Status"] not in STATUS_FIELDS:
        issues.append("bad-status-field")

    return {
        "path": relpath,
        "kind": note_kind(relpath),
        "arch": arch_of(relpath),
        "title": first_heading(text),
        "words": len(text.split()),
        "lines": len(lines),
        "status": status,
        "inferred_evidence": tier,
        "infer_reasons": tier_reasons,
        "evidence_confidence": proposal["confidence"],
        "probe": proposal["probe"],
        "date": proposal["date"],
        "legacy_banner": LEGACY_BANNER in text,
        "verified_headings": len(verified),
        "undated_verified_headings": redacted,
        "open_question_items": count_open_items(lines, open_sections),
        "open_question_sections": len(open_sections),
        "retract_markers": len(retracts),
        "strikethrough_spans": strikethrough,
        "hedge_words": hedges,
        "unchecked_boxes": unchecked,
        "has_conclusion_section": has_conclusion,
        "has_evidence_section": has_evidence_sec,
        "has_history_section": has_history,
        "issues": issues,
    }


def collect() -> list[dict]:
    records = []
    for root, _dirs, files in os.walk(NOTES_DIR):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            relpath = rel(os.path.join(root, name))
            if relpath in NON_NOTE_FILES or name in NON_NOTE_BASENAMES:
                continue
            records.append(audit_file(os.path.join(root, name)))
    records.sort(key=lambda r: r["path"])
    return records


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def summarise(records: list[dict]) -> dict:
    issue_counts = Counter()
    for rec in records:
        for issue in rec["issues"]:
            issue_counts[re.sub(r"\(\d+\)", "(N)", issue)] += 1
    return {
        "notes": len(records),
        "words": sum(r["words"] for r in records),
        "by_kind": dict(Counter(r["kind"] for r in records)),
        "by_arch": dict(Counter(r["arch"] for r in records)),
        "with_status_block": sum(1 for r in records if r["status"]),
        "legacy_banners": sum(1 for r in records if r["legacy_banner"]),
        "inferred_evidence": dict(Counter(r["inferred_evidence"] for r in records)),
        "verified_headings": sum(r["verified_headings"] for r in records),
        "undated_verified_headings": sum(len(r["undated_verified_headings"]) for r in records),
        "open_question_sections": sum(r["open_question_sections"] for r in records),
        "retract_markers": sum(r["retract_markers"] for r in records),
        "strikethrough_spans": sum(r["strikethrough_spans"] for r in records),
        "hedge_words": sum(r["hedge_words"] for r in records),
        "unchecked_boxes": sum(r["unchecked_boxes"] for r in records),
        "issue_counts": dict(issue_counts.most_common()),
    }


def print_summary(records: list[dict], summary: dict) -> None:
    print("== notes audit ==")
    for key in ("notes", "words", "with_status_block", "legacy_banners",
                "verified_headings", "undated_verified_headings",
                "open_question_sections", "retract_markers",
                "strikethrough_spans", "hedge_words", "unchecked_boxes"):
        print(f"  {key:28s} {summary[key]}")
    print(f"  {'by_kind':28s} {summary['by_kind']}")
    print(f"  {'by_arch':28s} {summary['by_arch']}")
    print(f"  {'inferred_evidence':28s} {summary['inferred_evidence']}")
    print("\n== issue counts ==")
    for issue, count in summary["issue_counts"].items():
        print(f"  {count:4d}  {issue}")

    print("\n== worst notes (by weighted cleanup cost) ==")
    weighted = sorted(
        records,
        key=lambda r: -(3 * len(r["undated_verified_headings"]) + 4 * r["retract_markers"]
                        + 2 * r["strikethrough_spans"] + 6 * ("no-status-block" in r["issues"])
                        + 3 * ("retractions-unpartitioned" in r["issues"])),
    )
    for rec in weighted[:25]:
        flags = ",".join(rec["issues"]) or "-"
        print(f"  {rec['path']:48s} retract={rec['retract_markers']:2d} "
              f"strike={rec['strikethrough_spans']:2d} undated={len(rec['undated_verified_headings']):2d} "
              f"| {flags}")


def git_date(path: str) -> str:
    """Last commit date (YYYY-MM-DD) that touched ``path``; '' when git is unusable."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ad", "--date=short", "--", path],
                             cwd=REPO_ROOT, capture_output=True, text=True, timeout=20)
        return out.stdout.strip()
    except Exception:
        return ""


def write_baseline(records: list[dict], summary: dict, dest: str) -> None:
    lines = [
        "# Notes audit baseline",
        "",
        "Generated by `tools/notes_audit.py --write-baseline`. **Do not hand-edit.**",
        "This is the frozen pre-cleanup snapshot: every later phase diffs against it.",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        if key in ("by_kind", "by_arch", "inferred_evidence", "issue_counts"):
            continue
        lines.append(f"| {key} | {value} |")
    for key in ("by_kind", "by_arch", "inferred_evidence"):
        lines.append(f"| {key} | " + ", ".join(f"{k}={v}" for k, v in sorted(summary[key].items())) + " |")
    lines += ["", "## Issue counts", "", "| count | issue |", "|---:|---|"]
    for issue, count in summary["issue_counts"].items():
        lines.append(f"| {count} | `{issue}` |")

    lines += ["", "## Per-note inventory", "",
              "`ev` = evidence tier inferred from the note text; `retr` = retraction/supersede"
              " markers; `strike` = struck-through spans; `undated` = verified headings without a"
              " date; `hedge` = speculative-language hits; `open` = open-question lines.",
              "",
              "| note | kind | words | ev | status | ev-block | retr | strike | undated | hedge | open | issues |",
              "|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for rec in records:
        ev_block = rec["status"].get("Evidence", "-") if rec["status"] else "-"
        lines.append("| `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            rec["path"], rec["kind"], rec["words"], rec["inferred_evidence"],
            (rec["status"].get("Status", "-") if rec["status"] else "-"), ev_block,
            rec["retract_markers"], rec["strikethrough_spans"],
            len(rec["undated_verified_headings"]), rec["hedge_words"],
            rec["open_question_sections"],
            ", ".join(f"`{i}`" for i in rec["issues"]) or "-"))
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {dest} ({len(records)} notes)")


def print_tier_report(records: list[dict]) -> None:
    """One line per note: proposed tier, confidence and the basis for it."""
    for rec in sorted(records, key=lambda r: (r["inferred_evidence"], r["path"])):
        basis = rec["infer_reasons"][0] if rec["infer_reasons"] else "-"
        print(f"{rec['inferred_evidence']:20s} {rec['evidence_confidence']:6s} "
              f"{rec['path']:46s} | {basis}")


def print_basis_report(records: list[dict]) -> None:
    """Histogram of why each tier was proposed -- shows where the guesses concentrate."""
    print("\n== basis of every proposal ==")
    for basis, count in Counter(
            (r["infer_reasons"][0] if r["infer_reasons"] else "-") for r in records
    ).most_common():
        print(f"  {count:4d}  {basis}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", metavar="PATH", help="write the full inventory as JSON")
    ap.add_argument("--write-baseline", metavar="PATH",
                    help="write the frozen markdown baseline (default notes/AUDIT_BASELINE.md)")
    ap.add_argument("--check", action="store_true",
                    help="fail (exit 1) when a note violates the conventions")
    ap.add_argument("--tiers", action="store_true",
                    help="print the proposed evidence tier and its basis for every note")
    ap.add_argument("--bases", action="store_true",
                    help="print a histogram of the basis behind every proposal")
    ap.add_argument("--undated", action="store_true",
                    help="list every verified heading that still has no date or provenance")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    records = collect()
    summary = summarise(records)

    if not args.quiet:
        print_summary(records, summary)
    if args.tiers:
        print("\n== proposed evidence tiers ==")
        print_tier_report(records)
    if args.bases:
        print_basis_report(records)
    if args.undated:
        print("\n== verified headings without a date or provenance note ==")
        for rec in records:
            for heading in rec["undated_verified_headings"]:
                print(f"  {rec['path']:44s} | {heading}")
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"summary": summary, "notes": records}, fh, indent=1, sort_keys=True)
        print(f"wrote {args.json}")
    if args.write_baseline:
        write_baseline(records, summary, args.write_baseline)

    if args.check:
        # Only conventions that phase 1-3 establish are enforced here.
        fatal = [r for r in records
                 if "no-status-block" in r["issues"] or "bad-evidence-tier" in r["issues"]
                 or "bad-status-field" in r["issues"]]
        if fatal:
            print(f"\nCHECK FAILED: {len(fatal)} note(s) violate the conventions", file=sys.stderr)
            for rec in fatal[:20]:
                print(f"  {rec['path']}: {', '.join(rec['issues'])}", file=sys.stderr)
            return 1
        print("\nCHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
