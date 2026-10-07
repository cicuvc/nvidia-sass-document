"""One-shot curation for the residual retractions the zone partition cannot fix.

The migrator is deliberately conservative: it only moves whole sections whose heading is
retraction-like.  A handful of notes keep a retracted claim inline, inside a section whose
heading is still current.  This script performs that last targeted move and is idempotent.

Run order: `notes_migrate.py --status --sections --apply` first (the annotations are
written *after* the status block), then this, then `notes_migrate.py --ledger --apply`.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "tools")
import notes_audit as na       # noqa: E402
import notes_migrate as nm     # noqa: E402

HISTORY = nm.HEADING_HISTORY
#: A visible line, not an HTML comment: it must survive the migrator and be greppable.
RETRACTION_NOTE = ("> **Retraction note:** this page quotes a retracted claim *in place* "
                   "because it justifies\n> the current conclusion; the retracted claim "
                   "itself is not current.")

#: The whole section is a record of abandoned experiments.
MOVE_SECTIONS = {
    "sm100/arch/tcgen05_tooling_checkpoint.md": ["旧原型：不能引用的实验"],
}
#: Notes that quote a retraction deliberately.
INLINE_RETRACTIONS = (
    "sm120/icache_topology.md",
    "sm120/subcore_compute_conflict.md",
    "sm90/arch/assembler_sm90_port.md",
    "sm90/arch/shared_bank_conflicts.md",
)
#: Notes whose struck-through items were disproved and belong in history.
MOVE_STRIKETHROUGH = ("sm90/arch/sm_memory_microarch_synthesis.md",)


def split_history(text: str, section_titles: list[str], moved_lines: list[str]) -> str:
    """Append ``## History`` carrying the named sections and/or the given lines."""
    if HISTORY in text:
        return text
    lines = text.split("\n")
    body, tail = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if any(line.startswith(f"## {t}") for t in section_titles):
            start = i
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            tail.append("\n".join(lines[start:i]).rstrip("\n"))
            continue
        body.append(line)
        i += 1
    if not tail and not moved_lines:
        return text
    out = "\n".join(body).rstrip("\n") + "\n\n" + HISTORY + "\n\n" + \
        "> Claims below were **superseded, refuted, or never settled** by later work; they " \
        "are kept\n> for provenance. Do not cite them as current.\n\n"
    out += "\n\n".join(tail)
    if moved_lines:
        out += "\n\n### Retracted or disproven items relocated from the sections above\n\n"
        out += "\n".join(moved_lines)
    return re.sub(r"\n{3,}", "\n\n", out).rstrip("\n") + "\n"


def add_retraction_note(text: str) -> str:
    """Insert the visible retraction note at the top of the Conclusion section.

    It goes *inside* the section, not above it: the migrator owns everything between the
    status block and the first heading, and would drop a note placed there.
    """
    if RETRACTION_NOTE in text:
        return text
    lines = text.split("\n")
    anchor = next((i for i, l in enumerate(lines) if l.startswith("## ")), None)
    if anchor is None:
        return text
    lines.insert(anchor + 1, "")
    lines.insert(anchor + 2, RETRACTION_NOTE)
    return "\n".join(lines)


def main() -> int:
    changes = 0
    for relpath, titles in MOVE_SECTIONS.items():
        path = os.path.join(na.NOTES_DIR, relpath)
        text = na.read(path)
        if HISTORY in text:
            continue
        new = split_history(text, titles, [])
        if new != text:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(new)
            changes += 1
            print("moved section to history:", relpath)

    for relpath in MOVE_STRIKETHROUGH:
        path = os.path.join(na.NOTES_DIR, relpath)
        text = na.read(path)
        if HISTORY in text:
            continue
        struck = [l for l in text.splitlines() if "~~" in l and not l.startswith("##")]
        if not struck:
            continue
        new = text
        for line in struck:
            new = new.replace(line + "\n", "")
        new = split_history(new, [], struck)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        changes += 1
        print(f"moved {len(struck)} struck-through item(s) to history:", relpath)

    for relpath in INLINE_RETRACTIONS:
        path = os.path.join(na.NOTES_DIR, relpath)
        text = na.read(path)
        new = add_retraction_note(text)
        if new != text:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(new)
            changes += 1
            print("annotated in-place retraction:", relpath)

    print("curation changes:", changes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
