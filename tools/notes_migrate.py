#!/usr/bin/env python3
"""Migrate the ``notes/`` tree to the explicit status/partition conventions.

Three jobs, each independently selectable:

``--status``   insert or refresh the canonical status block (phase 1)
``--sections`` partition each note into Conclusion / Evidence / History sections and
               normalise legacy ``## Resolved: ...`` headings (phases 1-2)
``--ledger``   regenerate the tracking ledgers from the status blocks (phase 3)

Every job is idempotent and every destructive-looking step is a pure text move, so a
re-run produces no diff.  ``--dry-run`` prints the intended result for a few notes
without touching the tree.

Design rules (agreed with the user):

* history is *kept*, never deleted -- retracted hypotheses move into an explicit
  ``## History / retracted hypotheses`` section instead of being silently dropped;
* a note never claims a measurement host it cannot substantiate: when the host is not
  derivable from the note, the block says ``unpinned`` and ``Tier confidence: unverified``
  rather than guessing;
* only the *first* H1 is the title, and the note body keeps its original order -- the
  partition only introduces grouping headings, it never reorders prose.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes_audit as na  # noqa: E402

REPO_ROOT = na.REPO_ROOT
NOTES_DIR = na.NOTES_DIR

# Sections that answer "what is true", in the order we want them to appear.
CONCLUSION_PREFIXES = ("conclusion", "summary", "result", "verdict", "bottom line",
                       "tl;dr", "status", "结论", "概要", "摘要", "总结")
# Sections that answer "how do we know".
EVIDENCE_PREFIXES = ("evidence", "method", "procedure", "reproduce", "reproduction",
                     "probe", "experiment", "measurement", "environment", "data",
                     "verification", "verified", "empirical", "corroboration",
                     "resolved", "探针", "方法", "复现", "实测", "验证")
# Sections that answer "what stopped being true".
HISTORY_PREFIXES = ("history", "retracted", "retraction", "superseded", "deprecated",
                    "errata", "erratum", "correction", "corrections", "prior",
                    "previous", "abandoned", "rejected", "历史", "作废", "已废弃")
# Sections that list what is still unknown -- they belong with history, not with results.
OPEN_PREFIXES = ("open question", "open sub-question", "open item", "open issue",
                 "remaining open", "unresolved", "todo", "未解", "待解决")

ZONE_CONCLUSION = "conclusion"
ZONE_EVIDENCE = "evidence"
ZONE_HISTORY = "history"
ZONE_REFERENCE = "reference"

#: Lines the migrator is allowed to introduce or remove.  Everything else must survive
#: a migration byte-for-byte (modulo blank lines and the `---` separators it may move),
#: which :func:`content_fingerprint` enforces.
ADDED_LINE_PATTERNS = (
    re.compile(r"^<!-- notes-status -->$"),
    re.compile(r"^<!-- provenance: .*-->$"),
    re.compile(r"^\*\*(Status|Evidence|Tier confidence|Last verified|Probe|Open items|"
               r"Supersedes|Audit):\*\*"),
    re.compile(r"^## (Conclusion|Evidence)$"),
    re.compile(r"^## History / retracted hypotheses$"),
    re.compile(r"^> Claims below were \*\*superseded, refuted, or never settled\*\* by later work; they are kept$"),
    re.compile(r"^> for provenance\. Do not cite them as current\.$"),
    re.compile(r"^_\(no summary in the source note; the sections below carry the durable facts\)_$"),
)


def content_fingerprint(text: str) -> list[str]:
    """Content lines that a migration must preserve, in order.

    Drops blank lines and ``---`` rules (pure layout), the lines the migrator itself
    introduces, and the legacy-banner comment, so a diff between two fingerprints proves
    that no prose was lost or reordered by accident.  Renames the migrator performs on
    purpose (``## Resolved`` -> ``## Verified``) are canonicalised away.
    """
    out = []
    for line in strip_legacy_comment(text, na.LEGACY_BANNER).split("\n"):
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue
        if any(p.match(stripped) for p in ADDED_LINE_PATTERNS):
            continue
        if stripped.startswith(("> **Arch scope:**", "> (sm_120)", "> the GPU-semantics",
                                "> uses sm_120 FORMAT", "> stall/NOP pattern",
                                "> Status and follow-up tracking:", "> `notes/",
                                "> > **Arch scope:**")):
            continue
        out.append(re.sub(r"\s+", " ", re.sub(r"^##\s+Resolved\b", "## Verified", stripped)))
    return out

HEADING_CONCLUSION = "## Conclusion"
HEADING_EVIDENCE = "## Evidence"
HEADING_HISTORY = "## History / retracted hypotheses"


def heading_zone(title: str) -> tuple[str, bool]:
    """Classify a level-2 heading as ``(zone, is_history_like)``.

    ``is_history_like`` covers both "this was true and is not any more" and "this was
    never settled" -- both belong below the current conclusions, not above them.
    """
    stripped = re.sub(r"^[\d.]+\s*", "", title).strip()
    low = stripped.lower()
    for prefix in OPEN_PREFIXES:
        if low.startswith(prefix):
            return ZONE_HISTORY, True
    for prefix in HISTORY_PREFIXES:
        if low.startswith(prefix):
            return ZONE_HISTORY, True
    for prefix in EVIDENCE_PREFIXES:
        if low.startswith(prefix):
            return ZONE_EVIDENCE, False
    for prefix in CONCLUSION_PREFIXES:
        if low.startswith(prefix):
            return ZONE_CONCLUSION, False
    return ZONE_REFERENCE, False


def is_history_heading(title: str) -> bool:
    """True for open-question / retraction / superseded headings."""
    return heading_zone(title)[1]


def is_open_heading(title: str) -> bool:
    """True for open-question-style headings (kept out of the History banner)."""
    low = re.sub(r"^[\d.]+\s*", "", title).strip().lower()
    return any(low.startswith(prefix) for prefix in OPEN_PREFIXES)


def normalise_verified_heading(title: str, date: str) -> str:
    """``## Resolved: X (SM120, 2026-08)`` -> ``## Verified: X (SM120, 2026-08)``."""
    fixed = re.sub(r"(?i)^(Resolved)\b", "Verified", title)
    if not na.RE_DATE.search(fixed) and date:
        fixed = f"{fixed} ({date})"
    return fixed


#: `## Verified ...` headings that record ISA encodings rather than a hardware run: they
#: get a provenance note instead of a verification date, because the date would say
#: nothing about silicon.  Matched against the heading text.
RE_ENCODING_HEADING = re.compile(
    r"(?i)\bverified\b.*\b(encodings?|cuobjdump|decoder|ptxas|nvcc|hi64|lo64|lo64\s*\+|"
    r"cublas|libcu)")


def git_date_for_text(path: str, needle: str) -> str:
    """First commit date (YYYY-MM) whose diff added ``needle`` in ``path``.

    Walks the file's history newest-first and stops at the first commit that no longer
    contains the needle, so the returned month is when the claim last changed.  Returns
    ``""`` when git cannot answer (shallow clone, untracked file).
    """
    if not needle.strip():
        return ""
    relpath = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
    try:
        log = subprocess.run(["git", "log", "--format=%H %ad", "--date=format:%Y-%m", "--", relpath],
                             cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
                             encoding="utf-8", errors="replace")
        if log.returncode != 0:
            return ""
        for line in log.stdout.splitlines():
            commit = line.split(" ", 1)[0]
            if not commit:
                continue
            blob = subprocess.run(["git", "show", f"{commit}:{relpath}"],
                                  cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
                                  encoding="utf-8", errors="replace")
            if blob.returncode != 0 or needle not in blob.stdout:
                return ""
            month = line.split(" ", 1)[1] if " " in line else ""
        return month
    except Exception:
        return ""


def sibling_date(text: str, title: str) -> str:
    """A date used by another verification heading in the same note.

    Verification sessions are batched: a note whose other ``Verified`` headings all carry
    the same month was almost certainly measured in that session.  Used only as a
    fallback, and the note says so in the provenance comment.
    """
    dates = set()
    for line in text.splitlines():
        if na.RE_VERIFIED_HEADING.match(line):
            found = na.RE_DATE.search(line)
            if found:
                dates.add(found.group(0))
    return next(iter(dates)) if len(dates) == 1 else ""


def annotate_undated_headings(text: str, apply: bool, relpath: str) -> str:
    """Add a provenance note under ``## Verified ...`` headings that carry no date.

    Idempotent: an existing provenance note is left untouched.  Heading bodies record ISA
    encodings get a fixed note instead of a fabricated date, and a heading with no
    discoverable date is left alone rather than being given one.
    """
    lines = text.split("\n")
    out: list[str] = []
    changed = False
    for i, line in enumerate(lines):
        out.append(line)
        match = re.match(r"^(#{2,3})\s+(.*)$", line)
        if not match or not na.RE_VERIFIED_HEADING.match(line):
            continue
        title = match.group(2).strip()
        if na.RE_DATE.search(title):
            continue
        existing = lines[i + 1] if i + 1 < len(lines) else ""
        if existing.strip().startswith("<!-- provenance"):
            continue
        note = ""
        if RE_ENCODING_HEADING.search(title):
            note = "<!-- provenance: ISA encodings from the toolchain; date not applicable -->"
        elif apply:
            legacy = re.sub(r"^Verified\b", "Resolved", title)
            month = git_date_for_text(os.path.join(NOTES_DIR, relpath), title)
            if not month:
                month = git_date_for_text(os.path.join(NOTES_DIR, relpath), legacy)
            if month:
                note = f"<!-- provenance: last changed {month} (git) -->"
            else:
                inherited = sibling_date(text, title)
                if inherited:
                    note = f"<!-- provenance: same measurement session as the other verified sections ({inherited}) -->"
        if note:
            out.append(note)
            changed = True
    return "\n".join(out) if changed else text


def strip_legacy_comment(text: str, marker: str) -> str:
    """Retire the legacy arch-scope prose now that the status block states the same facts.

    The banner's *content* is not lost: the status block records the tier and the probe,
    and the note's Evidence sections keep the full story.  What goes away is duplicated
    header prose that sat mid-document and read like a live caveat.

    Implemented line by line on purpose: a regular expression over blockquote runs is how
    an earlier revision of this function ate the H1 title of two notes.  Curation
    annotations (``<!-- curated:`` / ``<!-- note:``) are content, so they pass through.
    """
    out: list[str] = []
    dropping_banner = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("<!-- curated:", "<!-- note:")):
            out.append(line)
            continue
        if marker in line:
            dropping_banner = True
            continue
        if stripped.startswith("> **Arch scope:**"):
            dropping_banner = True
            continue
        if dropping_banner:
            if stripped.startswith(">"):
                continue          # continuation of the banner paragraph
            if not stripped:
                dropping_banner = False
                continue          # swallow the blank line that closed the banner
            dropping_banner = False
        if stripped.startswith("> Status and follow-up tracking:"):
            continue
        if stripped.startswith(("> `notes/sm120/silver-status.md`",
                                "> `notes/sm90/arch/sm90_resilver_audit.md`")):
            continue
        out.append(line)
    while out and not out[0].strip():
        out.pop(0)
    return drop_banner_leftovers("\n".join(out))


def drop_banner_leftovers(text: str) -> str:
    """Remove any blockquote line left over from the legacy banner paragraphs.

    The banner arrived in several spellings and line wrappings, so a line-by-line match is
    brittle.  Its remains are always blockquote prose *between the status block and the
    first section heading* (a note's own content never sits there), which makes this a
    safe, generic cleanup.
    """
    lines = text.split("\n")
    try:
        first_heading = next(i for i, l in enumerate(lines) if l.startswith("## "))
    except StopIteration:
        return text.rstrip("\n") + "\n"
    end_of_block = 0
    if na.STATUS_MARKER in text:
        end_of_block = next((i for i, l in enumerate(lines) if l.startswith("**Audit:**")), 0) + 1
    kept = lines[:end_of_block] + [l for l in lines[end_of_block:first_heading]
                                   if not l.lstrip().startswith(">")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept + lines[first_heading:])).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Status block
# ---------------------------------------------------------------------------

def build_status_block(rec: dict, proposal: dict, override: dict | None = None) -> str:
    """Render the canonical status block for one audited note."""
    override = override or {}
    tier = override.get("tier", proposal["tier"])
    confidence = override.get("confidence", proposal["confidence"])
    probe = override.get("probe", proposal["probe"])
    date = override.get("date", proposal["date"]) or "unknown"
    status = override.get("status", "active")
    open_items = override.get("open_items")
    if open_items is None:
        open_items = (f"{rec['open_question_items']} open item(s)"
                      if rec["open_question_items"] else "none")
    supersedes = override.get("supersedes", "")

    if tier == na.EVIDENCE_UNPINNED:
        confidence = "unverified"
    lines = [na.STATUS_MARKER,
             f"**Status:** {status}  ",
             f"**Evidence:** {tier}  ",
             f"**Tier confidence:** {confidence}  ",
             f"**Last verified:** {date}  ",
             f"**Probe:** {probe or 'not recorded in this note'}  ",
             f"**Open items:** {open_items}  "]
    if supersedes:
        lines.append(f"**Supersedes:** {supersedes}  ")
    lines.append(f"**Audit:** `tools/notes_audit.py` · basis: {proposal['basis']}")
    return "\n".join(lines)


def insert_status_block(text: str, block: str) -> str:
    """Insert or replace the status block, immediately after the H1 title."""
    lines = text.split("\n")
    if not lines or not lines[0].startswith("# "):
        return text
    if na.STATUS_MARKER in text:
        start = next(i for i, l in enumerate(lines) if na.STATUS_MARKER in l)
        end = start
        for i in range(start + 1, len(lines)):
            if na.RE_STATUS_FIELD_LINE.match(lines[i]):
                end = i
            else:
                break
        # Keep the blank line that separated the block from the body.
        rest = lines[:start]
        while end + 1 < len(lines) and not lines[end + 1].strip():
            end += 1
        rest += lines[end + 1:]
        while rest and not rest[-1].strip():
            rest.pop()
        lines = rest
    head, rest = lines[0], lines[1:]
    while rest and not rest[0].strip():
        rest.pop(0)
    return "\n".join([head, "", block, ""] + rest) + "\n"


# ---------------------------------------------------------------------------
# Section partition
# ---------------------------------------------------------------------------

def split_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    """Split ``body`` into (preamble, [(heading, section_text), ...]).

    Only level-2 headings split; a trailing preamble with no heading is returned first.
    Fenced code blocks are respected so ``# comment`` inside SASS never splits anything.
    """
    preamble: list[str] = []
    sections: list[tuple[str, str]] = []
    inside = False
    current: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, current
        if current is not None:
            sections.append((current, "\n".join(buf).strip("\n")))
        elif buf:
            preamble.extend(buf)
        buf = []

    for line in lines:
        if line.lstrip().startswith("```"):
            inside = not inside
        if not inside and re.match(r"^##\s", line):
            flush()
            current = line[3:].strip()
            buf = []
            continue
        buf.append(line)
    flush()
    return "\n".join(preamble).strip("\n"), sections


def partition(text: str, date: str) -> str:
    """Introduce the explicit zones, preserving the note's original section order.

    What this does, and deliberately does not do:

    * ``## Conclusion`` is inserted before the first section when the note's lead text
      (preamble) carries the durable summary -- i.e. whenever the note has any section
      at all.  A note that already concludes into a summary section keeps that section
      where it is.
    * ``## Evidence`` is inserted before the first measurement section, **only if the
      note has one**.  An empty zone heading is worse than no heading.
    * retracted/superseded/open-question sections move to the end, under
      ``## History / retracted hypotheses`` -- the one move that changes order, because
      leaving refuted claims above current ones is exactly the misreading this work
      exists to prevent.
    * everything else (Semantics, Variants, Bit layout, Latency, ...) stays in place and
      keeps its heading level, so the diff stays reviewable.

    Idempotent: a note that already carries ``## Conclusion`` is returned unchanged, and
    ``## Resolved: ...`` headings are renamed to ``## Verified: ...`` so the verification
    act is visible at a glance.
    """
    lines = text.split("\n")
    if not lines or not lines[0].startswith("# "):
        return text
    title = lines[0]
    body_lines = [re.sub(r"^(##\s+)Resolved\b", r"\1Verified", l) for l in lines[1:]]

    if any(l.startswith(HEADING_CONCLUSION) for l in body_lines):
        renamed = "\n".join([title] + body_lines)
        return renamed if renamed != text else text  # already migrated

    # Locate the level-2 section starts (fenced code blocks excluded).
    starts: list[tuple[int, str]] = []
    inside = False
    for i, line in enumerate(body_lines):
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside and re.match(r"^##\s", line):
            starts.append((i, line[3:].strip()))
    if not starts:
        # A short note with no sections at all: its whole body is the conclusion.
        body = "\n".join(body_lines).strip("\n")
        if not body:
            return text
        return "\n".join([title, "", HEADING_CONCLUSION, "", body, ""])

    history_idx = [i for i, (_, h) in enumerate(starts) if heading_zone(h)[0] == ZONE_HISTORY]
    evidence_idx = [i for i, (_, h) in enumerate(starts) if heading_zone(h)[0] == ZONE_EVIDENCE]
    # Open questions are *not* history: phase 2 used to park them under the History banner,
    # which put live questions under a "do not cite current" disclaimer.  They get their
    # own block at the end of the note instead.
    open_idx = [i for i, (_, h) in enumerate(starts) if is_open_heading(h)]

    # Preamble = everything before the first section, minus trailing separators.
    first_start = starts[0][0]
    preamble = body_lines[:first_start]
    while preamble and (not preamble[-1].strip() or preamble[-1].strip() == "---"):
        preamble.pop()
    while preamble and not preamble[0].strip():
        preamble.pop(0)

    # Slice the body into per-section line ranges, then emit kept sections in order and
    # history sections at the end.
    bounds = [s[0] for s in starts] + [len(body_lines)]
    blocks = [(starts[i][1], body_lines[bounds[i]:bounds[i + 1]]) for i in range(len(starts))]

    kept: list[list[str]] = []
    history: list[list[str]] = []
    open_items: list[list[str]] = []
    evidence_at: int | None = None
    for idx, (heading, block) in enumerate(blocks):
        # Blocks are emitted verbatim and joined with exactly one blank line, so a second
        # pass reproduces the same bytes (no re-trimming that could drop a blank line).
        if idx in open_idx:
            open_items.append(list(block))
            continue
        if idx in history_idx:
            history.append(list(block))
            continue
        if idx in evidence_idx and evidence_at is None:
            evidence_at = len(kept)
        kept.append(list(block))

    def emit(block: list[str]) -> list[str]:
        """One section: its lines, trailing blanks normalised to a single separator."""
        out = list(block)
        while out and not out[-1].strip():
            out.pop()
        return out + [""]

    pieces: list[str] = [title, ""]
    if preamble or kept:
        pieces += [HEADING_CONCLUSION, ""]
        pieces += emit(preamble) if any(l.strip() for l in preamble) else \
            ["_(no summary in the source note; the sections below carry the durable facts)_", ""]
    if evidence_at is not None:
        kept.insert(evidence_at, [HEADING_EVIDENCE, ""])
    for block in kept:
        pieces += emit(block)
    if history:
        pieces += [HEADING_HISTORY, "",
                   "> Claims below were **superseded, refuted, or never settled** by later "
                   "work; they are kept",
                   "> for provenance. Do not cite them as current.", ""]
        for block in history:
            pieces += emit(block)
    for block in open_items:
        pieces += emit(block)

    return "\n".join(pieces).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Ledger generation (phase 3)
# ---------------------------------------------------------------------------

LEDGER_BEGIN = "<!-- ledger:generated:begin -->"
LEDGER_END = "<!-- ledger:generated:end -->"

LEDGER_PROSE = """## Generated status ledger

Regenerated by `python3 tools/notes_migrate.py --ledger`; **do not hand-edit the block
below**.  `Evidence` records where the measurement was made; `Tier confidence` says how
well that was established from the note itself (`unverified` = the host is not
derivable from the note text, so the row is a pointer to be confirmed, not proof).

"""


def render_ledger(records: list[dict]) -> str:
    """The generated table, wrapped in markers so it can be replaced in place."""
    rows = []
    for rec in sorted(records, key=lambda r: r["path"]):
        status = rec["status"]
        if not status:
            continue
        rows.append("| `{}` | {} | {} | {} | {} |".format(
            rec["path"], status.get("Evidence", "-"), status.get("Tier confidence", "-"),
            status.get("Last verified", "-"), status.get("Status", "-")))
    return (LEDGER_BEGIN + "\n"
            + "| note | evidence | tier confidence | last verified | status |\n"
            + "|---|---|---|---|---|\n" + "\n".join(rows) + "\n" + LEDGER_END + "\n")


def upsert_ledger(path: str, generated: str) -> str:
    """Replace the generated block in ``path``, or append section + block when absent.

    The result always ends with exactly one newline, so re-running the ledger step is a
    no-op (the original block could be followed by a blank line that would otherwise
    accumulate one byte per run).
    """
    text = na.read(path)
    if LEDGER_BEGIN in text and LEDGER_END in text:
        start = text.index(LEDGER_BEGIN)
        end = text.index(LEDGER_END) + len(LEDGER_END)
        updated = text[:start] + generated + text[end:]
    else:
        updated = text.rstrip("\n") + "\n\n" + LEDGER_PROSE + generated
    return updated.rstrip("\n") + "\n"

# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def load_overrides() -> dict:
    if not os.path.exists(na.OVERRIDES_PATH):
        return {}
    with open(na.OVERRIDES_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    table = data.get("notes", data)
    bad = []
    for relpath, entry in table.items():
        if relpath.startswith("_"):
            continue
        tier = entry.get("tier")
        if tier and not na.is_valid_tier(tier):
            bad.append(f"{relpath}: bad tier {tier!r}")
        status = entry.get("status")
        if status and status not in na.STATUS_FIELDS:
            bad.append(f"{relpath}: bad status {status!r}")
    if bad:
        raise SystemExit("invalid overrides in notes_status_overrides.json:\n  " + "\n  ".join(bad))
    return table


#: The two tracking ledgers.  Their bodies are historical prose, so the zone partition is
#: meaningless for them (and previously ate their H1); only the generated block is
#: maintained, which :func:`upsert_ledger` splices in place.
LEDGER_FILES = ("sm90/arch/sm90_resilver_audit.md", "sm120/silver-status.md")


#: Notes owned by a generator: touching them here would make the generator's `--check`
#: fail (and the generator already writes the status block and zones).
GENERATED_FILES_PREFIXES = tuple(f"sm{a}/instr/" for a in
                                 ("70", "75", "80", "89", "90", "100", "103", "107", "120"))


def is_generated(relpath: str) -> bool:
    return relpath.startswith(GENERATED_FILES_PREFIXES)


def migrate(apply: bool, do_status: bool, do_sections: bool, do_ledger: bool,
            limit: int = 0, show: int = 0) -> int:
    overrides = load_overrides()
    records = na.collect()
    changed = 0
    shown = 0
    pending: list[tuple[str, str]] = []
    for rec in records:
        path = os.path.join(NOTES_DIR, rec["path"])
        if rec["path"] in LEDGER_FILES or is_generated(rec["path"]):
            continue  # handled by the ledger step / the sm120 note generator
        original = na.read(path)
        migrated = na.STATUS_MARKER in original and HEADING_CONCLUSION in original
        text = original
        if rec["path"].endswith(".md"):
            stripped = strip_legacy_comment(text, na.LEGACY_BANNER)
            # Compare with trailing blank lines ignored: dropping a blank line at EOF is
            # not worth rewriting a file, and keeping that promise is what makes the dry
            # run able to report a clean "nothing to do".
            if stripped.rstrip("\n") == original.rstrip("\n"):
                text = original
            else:
                text = stripped

        if do_sections:
            if not migrated:
                text = partition(text, rec["date"])
            # Provenance notes also apply to notes migrated by an earlier run.
            text = annotate_undated_headings(text, apply, rec["path"])

        if do_status:
            fresh = na.audit_file(path)
            fresh["path"] = rec["path"]
            block = build_status_block(fresh, na.propose_evidence(text, rec["path"]),
                                       overrides.get(rec["path"]))
            text = insert_status_block(text, block)

        # Safety gate: a migration may add structure, never lose prose -- and never the
        # title, which is what identifies the note.
        if not text.startswith("# "):
            raise SystemExit(f"title check failed for {rec['path']}: first line is "
                             f"{text.splitlines()[0][:80]!r}" if text.splitlines() else
                             f"title check failed for {rec['path']}: empty")
        before, after = content_fingerprint(original), content_fingerprint(text)
        if sorted(before) != sorted(after):
            from collections import Counter
            lost = Counter(before) - Counter(after)
            added = Counter(after) - Counter(before)
            raise SystemExit(
                f"content check failed for {rec['path']} "
                f"({len(before)} -> {len(after)} lines)\n"
                + "".join(f"  lost: {l[:120]}\n" for l in list(lost)[:10])
                + "".join(f"  added: {l[:120]}\n" for l in list(added)[:10]))

        if text.rstrip("\n") != original.rstrip("\n"):
            changed += 1
            pending.append((path, text))
            if show and shown < show and apply:
                print(f"--- {rec['path']} ---")
                print("\n".join(text.splitlines()[:40]))
                shown += 1
        if limit and changed >= limit:
            break

    # Write only after every note validated: a failure must not leave a half-migrated tree.
    if apply:
        for path, text in pending:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

    if do_ledger and apply:
        # Re-collect: the two ledger files may have just received their status blocks.
        ledger = render_ledger(na.collect())
        for rel_path in LEDGER_FILES:
            target = os.path.join(NOTES_DIR, rel_path)
            if os.path.exists(target):
                with open(target, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(upsert_ledger(target, ledger))
                print(f"ledger updated: {rel_path}")
    print(f"{'applied' if apply else 'would change'}: {changed} note(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--status", action="store_true", help="insert/refresh the status block")
    ap.add_argument("--sections", action="store_true", help="partition into zones")
    ap.add_argument("--ledger", action="store_true", help="regenerate the tracking ledgers")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N changed notes")
    ap.add_argument("--show", type=int, default=0, help="print N rewritten notes")
    args = ap.parse_args(argv)
    if not (args.status or args.sections or args.ledger):
        ap.error("pick at least one of --status/--sections/--ledger")
    return migrate(args.apply, args.status, args.sections, args.ledger, args.limit, args.show)


if __name__ == "__main__":
    raise SystemExit(main())
