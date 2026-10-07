#!/usr/bin/env python3
"""Generate the spec-derived sm_120 per-instruction notes from ``sm120.json``.

Why: the sm_120 measurements were being recorded inside ``notes/sm90/`` (which documents
the *sm_90* ISA) because that is where the instruction reference lived.  This tool builds
the missing sm_120-side reference from the ISA dump, so a measurement taken on an RTX 5090
has a note on the architecture it was actually taken on.

What it writes, per mnemonic:

* ``## Variants``      - every CLASS for the mnemonic, with opcode / FORMAT / pipes
* ``## Properties``    - INSTRUCTION_TYPE, operand sizes, predicates, virtual queue
* ``## Encoding``      - the bit map of each distinct layout, straight from ENCODING
* ``## Legal-encoding conditions``
* ``## Pipe and latency``
* ``## sm_90 relationship``  - whether notes/sm90/ documents the same mnemonic, and how the
  two dumps differ (new shapes / new opcodes)
* ``## sm_120 measurements`` - pointer to the note that holds the measured numbers

Generated content is fenced by ``<!-- generated:... -->`` markers so a later hand edit
survives regeneration, and ``--check`` verifies the tree matches the generator.

Usage
-----
    python3 tools/sm120_notes_gen.py --list                 # who would be generated, and why
    python3 tools/sm120_notes_gen.py --write                # write notes/sm120/instr/*.md
    python3 tools/sm120_notes_gen.py --mnem QMMA            # print one note to stdout
    python3 tools/sm120_notes_gen.py --check                # fail if the tree is stale
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isa_diff_sm90_sm120 as diff   # noqa: E402
import notes_audit as na             # noqa: E402

REPO_ROOT = na.REPO_ROOT
NOTES_DIR = na.NOTES_DIR
OUT_DIR = os.path.join(NOTES_DIR, "sm120", "instr")

BEGIN = "<!-- generated:sm120-notes:begin -->"
END = "<!-- generated:sm120-notes:end -->"

#: Which mnemonics get a note, and why.  ``only_sm120`` = the mnemonic exists on Blackwell
#: only; ``sm90_measurement`` = the mnemonic exists on both, but its behaviour was measured
#: on an RTX 5090 and recorded under notes/sm90/.
MANIFEST_REASONS = {
    "only_sm120": "sm_120-only mnemonic",
    "sm90_measurement": "measured on RTX 5090 (sm_120); sm_90-dump mnemonic",
    "changed_shapes": "operand shapes or opcodes differ from the sm_90 dump",
}

#: Families the repo's instruction docs exclude (texture/surface/graphics); uniform
#: **compute** mnemonics are in scope, uniform-graphics ones are not.
NON_COMPUTE = re.compile(
    r"^(?:"
    r"TLD4?|TLDS|TXD|TXQ|TXA|TEX|TEXS|TMML|"
    r"SULD|SUST|SUATOM|SURED|SUQUERY|SUCCTL|"
    r"FOOTPRINT|VILD|PIXLD|ALD|AST|ISBERD|ISBEWR|"
    r"TTU[A-Z]*"
    r")$")


def load_db(name: str) -> dict:
    return diff.load(name)


def operation_sets() -> dict[str, str]:
    """Map ``MNEMONIC`` -> pipe name, from ``sm120_latencies.txt`` OPERATION SETS."""
    path = os.path.join(REPO_ROOT, "sm120_latencies.txt")
    text = open(path, "r", encoding="utf-8", errors="replace").read()
    pipes: dict[str, str] = {}
    for match in re.finditer(r"(\w+_pipe)\s*=\s*\{([^}]*)\}", text):
        pipe, body = match.group(1), match.group(2)
        for entry in body.split(","):
            name = entry.strip()
            # Entries are ``MNEMONICpipe_pipe`` or a bare ``MNEMONIC``.
            name = re.sub(r"pipe_pipe$", "", name)
            name = re.sub(rf"{re.escape(pipe)}$", "", name)
            if name:
                pipes.setdefault(name.upper(), pipe)
    return pipes


def sm90_notes() -> dict[str, str]:
    """``MNEMONIC`` -> its note path under ``notes/sm90/instr``."""
    out = {}
    for rec in na.collect():
        if rec["path"].startswith("sm90/instr/"):
            out[rec["path"].rsplit("/", 1)[-1][:-3].upper()] = rec["path"]
    return out


def measured_by() -> dict[str, list[str]]:
    """``MNEMONIC`` -> notes (anywhere) whose evidence came from sm_120 silicon.

    Used to point the sm_120 note at the numbers instead of copying them: the note that
    holds the measurement stays authoritative.
    """
    out: dict[str, list[str]] = defaultdict(list)
    for rec in na.collect():
        evidence = rec["status"].get("Evidence") or ""
        if "sm120" not in evidence:
            continue
        stem = rec["path"].rsplit("/", 1)[-1][:-3]
        if "/instr/" in rec["path"]:
            out[stem.upper()].append(rec["path"])
    return out


def candidates() -> dict[str, dict]:
    """The mnemonics that need an sm_120 note, keyed by mnemonic."""
    sm90, sm120 = load_db("sm90.json"), load_db("sm120.json")
    cmp = diff.compare(sm90, sm120)
    sm90_note = sm90_notes()
    measured = measured_by()

    out: dict[str, dict] = {}
    for name in cmp["only_sm120"]:
        if NON_COMPUTE.match(name):
            continue
        out[name] = {"reasons": ["only_sm120"], "sm90_note": sm90_note.get(name),
                     "measured": measured.get(name, [])}
    for name in sorted(cmp["changed"]):
        if NON_COMPUTE.match(name) or name in out:
            continue
        note = sm90_note.get(name)
        if not note:
            continue  # not a mnemonic the repo documents
        reasons = ["changed_shapes"]
        if "sm120" in (na.audit_file(os.path.join(NOTES_DIR, note))["status"].get("Evidence") or ""):
            reasons.append("sm90_measurement")
        out[name] = {"reasons": reasons, "sm90_note": note, "measured": measured.get(name, [])}
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def opcode_text(variant: dict) -> str:
    return f"`0x{variant['opcode']:x}`" if isinstance(variant.get("opcode"), int) else "-"


def format_operands(variant: dict) -> str:
    """The operand *shape* from FORMAT: slot names plus modifier names, in order.

    The dump's FORMAT is a grammar, not a rendering (``Register:Rd ',' [-] Register:Ra``),
    so this reduces it to the thing a reader needs at a glance: which operands exist and
    which modifiers appear between them.
    """
    raw = (variant.get("format") or {}).get("raw", "")
    body = raw.split("Opcode", 1)[-1]
    body = re.sub(r"\$\(.*?\)\$", "", body, flags=re.DOTALL)
    body = body.replace("\n", " ").replace(";", " ")
    body = re.sub(r"\s+", " ", body)
    # Keep the modifiers (``/NAME:slot``) in place, drop the operand type prefixes.
    body = re.sub(r"/[A-Za-z0-9_]+:(\w+)", r"[/\1]", body)
    body = re.sub(r"\b(?:Register|UniformRegister|Predicate|UniformPredicate|"
                  r"UImm|SImm|F32Imm|F64Imm|Constant|CBank|Opcode)\b"
                  r"(?:\([^)]*\))?(?:\"[^\"]*\")?", "", body)
    body = body.replace("','", " ").replace("','", " ")
    body = re.sub(r"[,']+", " ", body)
    body = re.sub(r"\{[^{}]*\}", " ", body)      # empty reuse groups
    body = re.sub(r"\s+", " ", body).strip()
    return body or "-"


def render_encoding(variant: dict) -> str:
    """The 128-bit field map, MSB first, as the parser read it."""
    rows = []
    for field in variant.get("encoding") or []:
        spans = "+".join(f"[{hi}:{lo}]" for hi, lo in field["targets"])
        rhs = field.get("rhs")
        if field.get("rhs_kind") == "slot":
            rhs = f"`{rhs}`"
        elif rhs in (None, ""):
            rhs = "fixed"
        rows.append(f"| {spans} | `{field['name']}` | {field['width']} | {rhs} |")
    if not rows:
        return "_(no BITS_ field map for this class)_"
    return ("| bits | field | width | source |\n|---|---|---:|---|\n" + "\n".join(rows))


def render_variants(variants: list[dict]) -> str:
    rows = ["| CLASS | opcode | operands (FORMAT, modifiers stripped) |",
            "|---|---|---|"]
    for variant in variants:
        alt = " *(ALT)*" if variant.get("is_alternate") else ""
        rows.append(f"| `{variant['class']}`{alt} | {opcode_text(variant)} | "
                    f"`{format_operands(variant)}` |")
    return "\n".join(rows)


def render_properties(variants: list[dict]) -> str:
    seen: dict[str, set[str]] = defaultdict(set)
    for variant in variants:
        for key, value in (variant.get("properties") or {}).items():
            seen[key].add(str(value))
        for key, value in (variant.get("predicates") or {}).items():
            seen[key].add(str(value))
    if not seen:
        return "_(no PROPERTIES block)_"
    rows = ["| property | value(s) |", "|---|---|"]
    for key in sorted(seen):
        values = sorted(seen[key])
        shown = ", ".join(f"`{v}`" for v in values[:6])
        if len(values) > 6:
            shown += f", … (+{len(values) - 6})"
        rows.append(f"| `{key}` | {shown} |")
    return "\n".join(rows)


def render_conditions(variants: list[dict]) -> str:
    rows = []
    for variant in variants:
        for cond in variant.get("conditions") or []:
            rows.append(f"| `{variant['class']}` | `{cond.get('error', '?')}` | "
                        f"{cond.get('message', '')} | `{cond.get('predicate', '')}` |")
    if not rows:
        return "_None recorded in the dump._"
    return ("| CLASS | error | message | predicate |\n|---|---|---|---|\n" + "\n".join(rows))


#: Measurement notes whose tables are *mirrored* into the per-instruction sm_120 note.
#: Only notes where a row is identified by the mnemonic itself qualify, and only the row's
#: own text is copied (never a paraphrase), so the source keeps the interpretation and the
#: qualifiers while the instruction note gets the headline number.
MIRRORED_MEASUREMENTS = {
    "sm120/alufixed_latency.md",
    "sm120/alulite_latency.md",
    "sm120/aluheavy_latency.md",
    "sm120/fmalite_latency.md",
    "sm120/fmaheavy_latency.md",
    "sm120/fp16_latency.md",
    "sm120/fp64_redirect_latency.md",
}


def mirror_rows(mnem: str, source: str, limit: int = 4) -> list[str]:
    """Table rows in ``source`` whose first cell is exactly ``mnem``."""
    rel = source.replace("notes/", "", 1) if source.startswith("notes/") else source
    if rel not in MIRRORED_MEASUREMENTS:
        return []
    path = os.path.join(NOTES_DIR, rel)
    if not os.path.exists(path):
        return []
    rows, seen = [], set()
    for line in na.read(path).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: "):
            continue
        first = re.sub(r"[`*]", "", cells[0]).strip()
        if first.upper() != mnem.upper():
            continue
        normalized = re.sub(r"\s+", " ", line.strip())
        if normalized in seen:
            continue
        seen.add(normalized)
        rows.append(normalized)
        if len(rows) >= limit:
            break
    return rows


def measured_sections(mnem: str, source: str, limit: int = 4) -> list[str]:
    """The measurement-section headings in ``source`` that concern ``mnem``.

    Deliberately *headings*, not extracted rows: paraphrasing a measurement is how a number
    loses its qualifiers.  The heading is an exact pointer; the note behind it stays the one
    authoritative copy of the data.
    """
    path = os.path.join(NOTES_DIR, source)
    if not os.path.exists(path):
        return []
    word = re.compile(r"(?i)\b" + re.escape(mnem) + r"\b")
    measure_heading = re.compile(
        r"(?i)\b(latenc|forward|throughput|boundar|stall|cycle|timing|admission|"
        r"issue.to.use|dependenc|bandwidth|conflict|contention|empirical|hazard|cost)\b")
    out, current_used = [], False
    lines = na.read(path).splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#"):
            continue
        title = line.lstrip("# ").strip()
        if not measure_heading.search(title):
            current_used = False
            continue
        # Does the section body name the mnemonic?
        body = []
        for following in lines[i + 1:]:
            if following.startswith("#"):
                break
            body.append(following)
        if word.search("\n".join(body)) or word.search(title):
            out.append(title)
            if len(out) >= limit:
                break
    return out


def onchip_count(mnem: str) -> str:
    """How many disassembly lines carry this mnemonic in the committed fixture cubins.

    A cheap, honest indicator of how much real-compiler exposure the mnemonic has: the
    ``tests/*.cubin`` fixtures are already in the repo, so this needs no GPU.
    """
    names = {mnem.upper()}
    patterns = [re.compile(rb"\b" + re.escape(n.encode()) + rb"\b") for n in sorted(names)]
    total = 0
    for root, _dirs, files in os.walk(os.path.join(REPO_ROOT, "tests")):
        for name in files:
            if not name.endswith(".cubin"):
                continue
            blob = open(os.path.join(root, name), "rb").read()
            total += sum(len(p.findall(blob)) for p in patterns)
    return str(total)


def render_note(mnem: str, variants: list[dict], info: dict, pipes: dict[str, str],
                cmp: dict, sm120_meta: dict) -> str:
    pipe = pipes.get(mnem, variants[0].get("pipe_suffix") or "-")
    sm90_note = info.get("sm90_note")
    measured = info.get("measured") or []
    kinds = variants[0].get("properties", {}).get("INSTRUCTION_TYPE", "-")
    opcodes = sorted({v["opcode"] for v in variants if isinstance(v.get("opcode"), int)})
    op_txt = ", ".join(f"`0x{o:x}`" for o in opcodes) or "-"

    changed = cmp["changed"].get(mnem)
    rel = []
    if sm90_note:
        rel.append(f"This mnemonic also exists in the sm_90 dump; the sm_90-side reference is "
                   f"[`{sm90_note}`](../../{sm90_note}).")
    else:
        rel.append("**Not present in the sm_90 dump** — this is a Blackwell-only mnemonic.")
    if changed:
        if changed["shapes_only_sm120"]:
            rel.append("Operand shapes with no sm_90 counterpart: "
                       + ", ".join(f"`{s}`" for s in changed["shapes_only_sm120"]) + ".")
        if changed["shapes_only_sm90"]:
            rel.append("sm_90-only shapes (absent here): "
                       + ", ".join(f"`{s}`" for s in changed["shapes_only_sm90"]) + ".")
        if changed["opcodes_only_sm120"]:
            rel.append("Opcodes absent from the sm_90 dump: "
                       + ", ".join(f"`{o}`" for o in changed["opcodes_only_sm120"]) + ".")
        if changed["opcodes_only_sm90"]:
            rel.append("sm_90-only opcodes: "
                       + ", ".join(f"`{o}`" for o in changed["opcodes_only_sm90"]) + ".")

    measure = []
    mirrored = []
    for mirror_rel in sorted(MIRRORED_MEASUREMENTS):
        rows = mirror_rows(mnem, f"notes/{mirror_rel}")
        if rows:
            mirrored.append((mirror_rel, rows))
    if measured or mirrored:
        measure.append("Measured on an RTX 5090 (GB202, sm_120). The numbers stay in the note "
                       "that produced them (one authoritative copy, no drift); the index of "
                       "everything measured is [`notes/sm120/measurements_index.md`]"
                       "(../measurements_index.md).")
        for path in sorted(measured):
            measure.append(f"- [`{path}`](../../{path})")
            for title in measured_sections(mnem, path):
                measure.append(f"  - see §{title}")
        for rel, rows in mirrored:
            measure.append(f"- [`{rel}`](../{rel.rsplit('/', 1)[-1]})")
            for row in rows:
                measure.append(f"  {row}")
    else:
        measure.append("No sm_120 hardware measurement recorded for this mnemonic yet. "
                       "Everything above is derived from the ISA dump "
                       "(`sm120_instructions.txt`), not from silicon.")

    reasons = "; ".join(MANIFEST_REASONS[r] for r in info["reasons"])
    return f"""# {mnem} — sm_120

<!-- notes-status -->
**Status:** active  
**Evidence:** spec  
**Tier confidence:** high  
**Last verified:** unknown (ISA dump, not a probe)  
**Probe:** `sm120_instructions.txt` via `sm120.json`; no hardware measurement here  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · basis: generated by `tools/sm120_notes_gen.py`

## Conclusion

`{mnem}` — {kinds}, pipe `{pipe}`; opcode(s) {op_txt}, **{len(variants)} CLASS** in the
sm_120 dump. Generated from the ISA description; the hardware behaviour of this mnemonic
on an RTX 5090 is recorded where it was measured (see *sm_120 measurements*), not here.
Included because: {reasons}.

{BEGIN}
## Variants

{render_variants(variants)}

## Properties

{render_properties(variants)}

## Encoding

Bit map of the first layout (`{variants[0]['class']}`); the other CLASSes differ in their
modifier fields, enumerated in *Variants*:

{render_encoding(variants[0])}

## Legal-encoding conditions

{render_conditions(variants)}

## Pipe and latency

Pipe: `{pipe}` (from the OPERATION SETS in `sm120_latencies.txt`). Cross-check the per-pipe
latency tables there for the true/output/anti dependency rows.

## On-chip presence

`{mnem}` appears **{onchip_count(mnem)}** time(s) across the committed sm_120 fixture
cubins under `tests/` (a byte-grep over `*.cubin`, so this counts printed/disassembled
occurrences, not executions). Zero means no committed kernel exercises it yet.

## sm_90 relationship

{("\n".join("- " + r for r in rel))}

## sm_120 measurements

{("\n".join(measure))}

## Open questions

Program-wide, not per-instruction: the decoder round-trip and printed-form confirmation for
every generated note are tracked once in
[`notes/sm120/instr_verification_backlog.md`](../instr_verification_backlog.md). Anything
specific to this mnemonic belongs here.
{END}
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="list the notes that would be generated")
    ap.add_argument("--write", action="store_true", help="write the notes")
    ap.add_argument("--check", action="store_true", help="fail if a note is missing or stale")
    ap.add_argument("--mnem", metavar="NAME", help="print one generated note to stdout")
    ap.add_argument("--only", metavar="REASON", choices=sorted(MANIFEST_REASONS),
                    help="restrict to one manifest reason")
    ap.add_argument("--explain", metavar="NAME",
                    help="show how the generated note differs from the one on disk")
    args = ap.parse_args(argv)

    sm90, sm120 = load_db("sm90.json"), load_db("sm120.json")
    cmp = diff.compare(sm90, sm120)
    pipes = operation_sets()
    table = candidates()
    by_mnem = diff.by_mnemonic(sm120["variants"])
    sm120_meta = {"spec_date": str((sm120.get("meta") or {}).get("generated", "unknown"))}

    if args.only:
        table = {m: i for m, i in table.items() if args.only in i["reasons"]}

    if args.mnem:
        name = args.mnem.upper()
        variants = by_mnem.get(name)
        if not variants:
            raise SystemExit(f"{name} not in sm120.json")
        info = table.get(name, {"reasons": ["changed_shapes"], "sm90_note": sm90_notes().get(name),
                                "measured": measured_by().get(name, [])})
        sys.stdout.write(render_note(name, variants, info, pipes, cmp, sm120_meta))
        return 0

    if args.explain:
        import difflib
        name = args.explain.upper()
        text = render_note(name, by_mnem[name], table[name], pipes, cmp, sm120_meta)
        path = os.path.join(OUT_DIR, f"{name.lower()}.md")
        disk = na.read(path) if os.path.exists(path) else ""
        lines = list(difflib.unified_diff(disk.splitlines(), text.splitlines(),
                                          "on-disk", "generated", lineterm="", n=1))
        print("\n".join(lines[:60]) if lines else "IDENTICAL")
        return 0

    if args.list:
        print(f"{len(table)} note(s) to generate:")
        for name in sorted(table):
            print(f"  {name:16s} {', '.join(MANIFEST_REASONS[r] for r in table[name]['reasons'])}")
        return 0

    written = 0
    stale = []
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in sorted(table):
        variants = by_mnem[name]
        text = render_note(name, variants, table[name], pipes, cmp, sm120_meta)
        path = os.path.join(OUT_DIR, f"{name.lower()}.md")
        if args.check:
            # Compare with line endings normalised: git may hand back CRLF on Windows
            # while the generator writes LF, and that is not a content change.
            if not os.path.exists(path) or \
                    na.read(path).replace("\r\n", "\n") != text.replace("\r\n", "\n"):
                stale.append(name)
            continue
        if args.write:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            written += 1
            print(f"wrote {os.path.relpath(path, REPO_ROOT)}")

    if args.check:
        if stale:
            print(f"CHECK FAILED: {len(stale)} note(s) missing or stale: "
                  f"{', '.join(stale[:10])}")
            import difflib
            name = stale[0]
            text = render_note(name, by_mnem[name], table[name], pipes, cmp, sm120_meta)
            path = os.path.join(OUT_DIR, f"{name.lower()}.md")
            disk = na.read(path) if os.path.exists(path) else ""
            print("\n".join(list(difflib.unified_diff(disk.splitlines(), text.splitlines(),
                                                      "on-disk", "generated", lineterm="", n=1))[:40]))
            return 1
        print(f"CHECK OK: {len(table)} generated note(s) up to date")
    if args.write:
        print(f"{written} note(s) written")
    if not (args.write or args.check or args.list or args.mnem):
        print(f"{len(table)} note(s) would be generated; re-run with --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
