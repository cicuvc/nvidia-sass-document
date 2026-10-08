#!/usr/bin/env python3
"""Per-architecture ISA coverage manifest and note generator (all dumps at once).

The sm_120 generator (`tools/sm120_notes_gen.py`) proved the shape: each per-instruction
note is derived from the ISA dump, states its evidence tier, and leaves a placeholder where
hardware measurements will go.  This tool does that for **every** architecture dump in the
repo, from one implementation, so the notes are comparable across architectures.

Which mnemonics count as *compute*: those whose variants sit on a compute pipe
(`int_pipe`, `fe_pipe`, `fmalighter_pipe`, `fp16_pipe`, `fma64lite/heavy_pipe`,
`udp_pipe`).  Memory, data-mover, control-flow and the tree-traversal unit are out of
scope, matching the sm_90 documentation effort.

Layout:

    notes/<arch>/instr/<mnem>.md      one note per compute mnemonic (generated)
    notes/<arch>/MEASUREMENTS.md      per-arch placeholder ledger for the hardware run

Usage
-----
    python3 tools/isa_coverage.py                     # coverage summary per arch
    python3 tools/isa_coverage.py --manifest out.json # full machine-readable manifest
    python3 tools/isa_coverage.py --list sm90         # one arch's compute mnemonics
    python3 tools/isa_coverage.py --write             # write notes + measurement ledgers
    python3 tools/isa_coverage.py --write --arch sm90 # only one architecture
    python3 tools/isa_coverage.py --check             # fail when the tree is stale
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES_DIR = os.path.join(REPO, "notes")

#: arch -> (db file, instruction dump, latencies dump or None, display name)
ARCHES: dict[str, tuple[str, str, str | None, str]] = {
    "sm70":  ("sm70.json",  "sm_70_instructions.txt",  None,                  "Volta"),
    "sm75":  ("sm75.json",  "sm_75_instructions.txt",  None,                  "Turing"),
    "sm80":  ("sm80.json",  "sm_80_instructions.txt",  None,                  "Ampere (GA100)"),
    "sm89":  ("sm89.json",  "sm_89_instructions.txt",  "sm_89_latencies.txt", "Ada (AD10x)"),
    "sm90":  ("sm90.json",  "sm_90_instructions.txt",  "sm_90_latencies.txt", "Hopper (GH100)"),
    "sm100": ("sm100.json", "sm100_instructions.txt",  "sm100_latencies.txt", "Blackwell (GB100)"),
    "sm103": ("sm103.json", "sm_103_instructions.txt", "sm_103_latencies.txt", "Blackwell (sm_103)"),
    "sm107": ("sm107.json", "sm_107_instructions.txt", "sm_107_latencies.txt", "Blackwell (sm_107)"),
    "sm120": ("sm120.json", "sm120_instructions.txt",  "sm120_latencies.txt", "Blackwell (GB20x)"),
}

#: Pipes that execute *compute* work.  Everything else (MIO/LSU, CBU, TTU) is a memory,
#: data-mover or control unit and is documented elsewhere.
COMPUTE_PIPES = {
    "int_pipe", "fe_pipe", "fmalighter_pipe", "fp16_pipe",
    "fma64lite_pipe", "fma64heavy_pipe", "udp_pipe",
}

#: Families excluded even when a variant names a compute pipe: the ISA dump lists some
#: graphics/surface ops against the MIO pipe, and a few pseudo-ops have no encoding.
NON_COMPUTE_MNEMONICS = re.compile(
    r"^(?:TLD4?|TLDS|TXD|TXQ|TXA|TEX|TEXS|TMML|SULD|SUST|SUATOM|SURED|SUQUERY|SUCCTL|"
    r"FOOTPRINT|VILD|PIXLD|ALD|AST|ISBERD|ISBEWR|TTU[A-Z]*|OUT|STP|CSMTEST|VOTE_VTG)$")

BEGIN = "<!-- generated:isa-notes:begin -->"
END = "<!-- generated:isa-notes:end -->"


def load_db(arch: str) -> dict:
    path = os.path.join(REPO, ARCHES[arch][0])
    if not os.path.exists(path):
        raise SystemExit(f"{path} missing -- run tools/parse_all_arch.py first")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def by_mnemonic(db: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for variant in db["variants"]:
        name = (variant.get("mnemonic") or "").upper()
        if name:
            out[name].append(variant)
    return dict(out)


def mnemonic_pipes(variants: list[dict]) -> set[str]:
    pipes: set[str] = set()
    for variant in variants:
        pipes.update(re.findall(r"\w*_pipe", variant.get("pipe_suffix") or ""))
    return pipes


def compute_mnemonics(arch: str) -> dict[str, dict]:
    """The compute mnemonics of one architecture, with why each is included."""
    db = load_db(arch)
    out: dict[str, dict] = {}
    for name, variants in by_mnemonic(db).items():
        pipes = mnemonic_pipes(variants)
        compute = pipes & COMPUTE_PIPES
        if not compute:
            continue
        if NON_COMPUTE_MNEMONICS.match(name):
            continue
        types = sorted({(v.get("properties") or {}).get("INSTRUCTION_TYPE", "?")
                        for v in variants})
        out[name] = {
            "pipes": sorted(compute),
            "all_pipes": sorted(pipes),
            "variants": len(variants),
            "instruction_types": types,
        }
    return out


def coverage() -> dict[str, dict]:
    return {arch: compute_mnemonics(arch) for arch in ARCHES}


# ---------------------------------------------------------------------------
# Note rendering (shared across architectures)
# ---------------------------------------------------------------------------

def opcode_text(variant: dict) -> str:
    op = variant.get("opcode")
    return f"`0x{op:x}`" if isinstance(op, int) else "-"


def operand_shape(variant: dict) -> str:
    raw = (variant.get("format") or {}).get("raw", "")
    body = raw.split("Opcode", 1)[-1]
    body = re.sub(r"\$\(.*?\)\$", "", body, flags=re.DOTALL)
    body = body.replace("\n", " ").replace(";", " ")
    body = re.sub(r"\s+", " ", body)
    body = re.sub(r"/[A-Za-z0-9_]+:(\w+)", r"[/\1]", body)
    body = re.sub(r"\b(?:Register|UniformRegister|Predicate|UniformPredicate|UImm|SImm|"
                  r"F32Imm|F64Imm|Constant|CBank|Opcode)\b(?:\([^)]*\))?(?:\"[^\"]*\")?",
                  "", body)
    body = body.replace("','", " ")
    body = re.sub(r"[,']+", " ", body)
    body = re.sub(r"\{[^{}]*\}", " ", body)
    return re.sub(r"\s+", " ", body).strip() or "-"


def render_variants(variants: list[dict]) -> str:
    rows = ["| CLASS | opcode | operands (FORMAT-derived) |", "|---|---|---|"]
    for variant in variants:
        alt = " *(ALT)*" if variant.get("is_alternate") else ""
        rows.append(f"| `{variant['class']}`{alt} | {opcode_text(variant)} | "
                    f"`{operand_shape(variant)}` |")
    return "\n".join(rows)


def render_encoding(variant: dict) -> str:
    rows = []
    for field in variant.get("encoding") or []:
        spans = "+".join(f"[{hi}:{lo}]" for hi, lo in field["targets"])
        rhs = field.get("rhs")
        rhs = f"`{rhs}`" if field.get("rhs_kind") == "slot" else (rhs or "fixed")
        rows.append(f"| {spans} | `{field['name']}` | {field['width']} | {rhs} |")
    if not rows:
        return "_(no BITS_ field map for this class)_"
    return "| bits | field | width | source |\n|---|---|---:|---|\n" + "\n".join(rows)


def render_properties(variants: list[dict]) -> str:
    seen: dict[str, set[str]] = defaultdict(set)
    for variant in variants:
        for src in ("properties", "predicates"):
            for key, value in (variant.get(src) or {}).items():
                seen[key].add(str(value))
    if not seen:
        return "_(no PROPERTIES block)_"
    rows = ["| property | value(s) |", "|---|---|"]
    for key in sorted(seen):
        values = sorted(seen[key])
        shown = ", ".join(f"`{v}`" for v in values[:5])
        if len(values) > 5:
            shown += f", … (+{len(values) - 5})"
        rows.append(f"| `{key}` | {shown} |")
    return "\n".join(rows)


def render_conditions(variants: list[dict]) -> str:
    rows = []
    for variant in variants:
        for cond in variant.get("conditions") or []:
            rows.append(f"| `{variant['class']}` | `{cond.get('error', '?')}` | "
                        f"{cond.get('message', '')} |")
    if not rows:
        return "_None recorded in the dump._"
    return "| CLASS | error | message |\n|---|---|---|\n" + "\n".join(rows)


def render_note(arch: str, mnem: str, variants: list[dict], info: dict,
                db: dict, cross: dict[str, list[str]]) -> str:
    display = ARCHES[arch][3]
    dump = ARCHES[arch][1]
    pipes = ", ".join(f"`{p}`" for p in info["pipes"]) or "-"
    types = ", ".join(f"`{t}`" for t in info["instruction_types"]) or "-"
    opcodes = sorted({v["opcode"] for v in variants if isinstance(v.get("opcode"), int)})
    op_txt = ", ".join(f"`0x{o:x}`" for o in opcodes) or "-"
    elsewhere = [a for a in sorted(ARCHES) if a != arch and mnem in cross.get(a, [])]

    other_arches = ("This mnemonic is also a compute instruction on: "
                    + ", ".join(f"`{a}`" for a in elsewhere) + ".") if elsewhere else \
                   "Not a compute instruction on any other architecture dump in this repo."

    return f"""# {mnem} — {arch} ({display}) compute instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** spec  
**Tier confidence:** high  
**Last verified:** unknown (ISA dump, not a probe)  
**Probe:** `{dump}` via `{ARCHES[arch][0]}`; no hardware measurement recorded yet  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · basis: generated by `tools/isa_coverage.py`

## Conclusion

`{mnem}` — {types}, compute pipe(s) {pipes}; opcode(s) {op_txt}, **{len(variants)} CLASS**
in the `{arch}` dump.  Everything below is read out of the ISA description: the encoding,
the operand shape and the legal-encoding conditions are the dump's claims, not measured
behaviour.  Hardware results go in *Measurement* (placeholder) and stay out of this
section until they exist.

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

Compute pipe(s): {pipes}.  Latency tables (true/output/anti dependency) are not transcribed
here; the dump's own latency section is the reference.

## Measurement (placeholder)

> **No measurement yet.** This section is reserved for the real-hardware run: record the
> host (which part, which driver), the probe or test that produced the number, and the
> measured latency/throughput/behaviour.  Until then the note's evidence tier stays `spec`.
> The per-architecture queue, including pointers to any note that already holds measured
> numbers, is [`../MEASUREMENTS.md`](../MEASUREMENTS.md).

| field | value |
|---|---|
| host | _pending_ |
| probe / test | _pending_ |
| measured behaviour | _pending_ |
| evidence tier after the run | _pending_ |

## Architecture relationship

{other_arches}

## Open questions

Program-wide items (decoder round-trip, printed form) are tracked once per architecture in
[`../MEASUREMENTS.md`](../MEASUREMENTS.md); anything specific to this mnemonic belongs here.
{END}
"""


def measurement_notes(arch: str) -> dict[str, list[str]]:
    """``MNEMONIC`` -> notes whose own evidence came from that silicon, for this arch.

    Reads the status blocks (the same data ``tools/notes_audit.py`` reports), so a note
    that already holds measured numbers is pointed at instead of duplicated.
    """
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import notes_audit as na  # noqa: PLC0415
    out: dict[str, list[str]] = defaultdict(list)
    for rec in na.collect():
        evidence = rec["status"].get("Evidence") or ""
        if arch not in evidence:
            continue
        if "/instr/" in rec["path"]:
            out[rec["path"].rsplit("/", 1)[-1][:-3].upper()].append(rec["path"])
    return out


def render_measurements_ledger(arch: str, table: dict[str, dict], db: dict) -> str:
    display = ARCHES[arch][3]
    dump = ARCHES[arch][1]
    lat = ARCHES[arch][2] or "(no latency dump for this architecture)"
    counts = (db.get("meta") or {}).get("counts") or {}
    measured = measurement_notes(arch)
    rows = ["| mnemonic | compute pipe(s) | CLASS | opcode(s) | measured? |",
            "|---|---|---:|---|---|"]
    for name in sorted(table):
        info = table[name]
        variants = [v for v in db["variants"]
                    if (v.get("mnemonic") or "").upper() == name]
        opcodes = sorted({v["opcode"] for v in variants if isinstance(v.get("opcode"), int)})
        op_txt = ", ".join(f"`0x{o:x}`" for o in opcodes) or "-"
        have = measured.get(name) or []
        where = ", ".join(f"[`{p}`](../{p})" for p in have) if have else "_no_"
        rows.append(f"| [`{name.lower()}.md`](instr/{name.lower()}.md) | "
                    f"{', '.join('`' + p + '`' for p in info['pipes'])} | {info['variants']} | "
                    f"{op_txt} | {where} |")
    with_numbers = sum(1 for name in table if measured.get(name))
    return f"""# {arch} ({display}) compute instructions — measurement queue

Generated by `tools/isa_coverage.py`. **Do not hand-edit the block below.**

This is the per-architecture hardware-run queue.  Every entry is a compute instruction whose
encodings are read out of `{dump}` (`{lat}`); the `measured?` column points at a note that
already holds measured numbers for that mnemonic, or says `no`.

When a run happens, for each mnemonic: record host + probe + result in that note's
*Measurement* section, and upgrade the note's `Evidence` tier.  `notes/notes_audit.py
--check` enforces the tier field, so a tier upgrade without a recorded measurement is
visible in review.

| metric | value |
|---|---:|
| compute mnemonics | {len(table)} |
| variants in the dump (all types) | {counts.get('variants', '-')} |
| mnemonics in the dump (all types) | {counts.get('mnemonics', '-')} |
| mnemonics with a measured note somewhere | {with_numbers} |

{BEGIN}
## Queue

{chr(10).join(rows)}
{END}
"""


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

#: Architectures whose per-instruction notes already exist and are hand-maintained (sm90,
#: sm120) or partially so (sm100).  `--write` never regenerates an existing note there;
#: `--fill-gaps` adds only the mnemonics that have no note at all yet.
HAND_MAINTAINED = {"sm90", "sm100", "sm120"}

GENERATED_PREFIX = "instr/"


def write_arch(arch: str, apply: bool, check: bool, fill_gaps: bool = False) -> tuple[int, list[str]]:
    table = compute_mnemonics(arch)
    db = load_db(arch)
    cross = {}
    for other in ARCHES:
        if other != arch:
            cross[other] = compute_mnemonics(other)
    out_dir = os.path.join(NOTES_DIR, arch, "instr")
    written, stale = 0, []
    existing = ([f for f in os.listdir(out_dir) if f.endswith(".md")]
                if os.path.isdir(out_dir) else [])
    existing_stems = {f[:-3].upper() for f in existing}
    # In a hand-maintained architecture a note that exists is owned by a human: never
    # rewrite it.  `--fill-gaps` writes only the mnemonics with no note at all.
    skip_notes = arch in HAND_MAINTAINED and bool(existing) and not fill_gaps
    if apply and not skip_notes:
        os.makedirs(out_dir, exist_ok=True)
    for name in sorted(table):
        if skip_notes:
            continue
        if fill_gaps and name in existing_stems:
            continue
        variants = [v for v in db["variants"]
                    if (v.get("mnemonic") or "").upper() == name]
        text = render_note(arch, name, variants, table[name], db, cross)
        path = os.path.join(out_dir, f"{name.lower()}.md")
        if check:
            normal = lambda s: s.replace("\r\n", "\n")  # noqa: E731
            if not os.path.exists(path) or normal(open(path, encoding="utf-8").read()) != normal(text):
                stale.append(f"{arch}/{name}")
            continue
        if apply:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            written += 1
    ledger = render_measurements_ledger(arch, table, db)
    lpath = os.path.join(NOTES_DIR, arch, "MEASUREMENTS.md")
    if check:
        normal = lambda s: s.replace("\r\n", "\n")  # noqa: E731
        if not os.path.exists(lpath) or normal(open(lpath, encoding="utf-8").read()) != normal(ledger):
            stale.append(f"{arch}/MEASUREMENTS.md")
    elif apply:
        with open(lpath, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(ledger)
    return written, stale


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arch", action="append", choices=sorted(ARCHES))
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--fill-gaps", action="store_true",
                    help="in hand-maintained architectures, write only mnemonics with no "
                         "note yet (never rewrites an existing note)")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--manifest", metavar="PATH")
    ap.add_argument("--list", metavar="ARCH")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(argv)

    archs = args.arch or sorted(ARCHES)

    if args.list:
        table = compute_mnemonics(args.list)
        print(f"{args.list}: {len(table)} compute mnemonic(s)")
        print(" ".join(sorted(table)))
        return 0

    if args.manifest:
        data = {a: compute_mnemonics(a) for a in archs}
        with open(args.manifest, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        print(f"wrote {args.manifest}")

    if args.write or args.check:
        total, stale = 0, []
        for arch in archs:
            written, arch_stale = write_arch(arch, args.write, args.check, args.fill_gaps)
            total += written
            stale += arch_stale
            if args.write:
                print(f"{arch}: wrote {written} note(s) + MEASUREMENTS.md")
        if args.check:
            if stale:
                print(f"CHECK FAILED: {len(stale)} stale item(s): "
                      f"{', '.join(stale[:12])}", file=sys.stderr)
                return 1
            print("CHECK OK: ISA notes up to date")
        else:
            print(f"{total} note(s) written")
        return 0

    # summary
    print(f"{'arch':7s} {'compute':>8s} {'variants':>9s} {'notes now':>10s}  mode")
    grand = 0
    for arch in archs:
        table = compute_mnemonics(arch)
        grand += len(table)
        have = 0
        d = os.path.join(NOTES_DIR, arch, "instr")
        if os.path.isdir(d):
            have = len([f for f in os.listdir(d) if f.endswith(".md")])
        db = load_db(arch)
        counts = (db.get("meta") or {}).get("counts") or {}
        mode = "hand-maintained (skip notes)" if arch in HAND_MAINTAINED and have \
            else "generate"
        print(f"{arch:7s} {len(table):8d} {counts.get('variants', '-'):>9} {have:>10d}  {mode}")
    print(f"{'TOTAL':7s} {grand:8d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
