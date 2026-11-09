#!/usr/bin/env python3
"""Build compact browser data for the SASS instruction viewer.

The source of truth remains ``sm*.json`` plus the Markdown notes.  Raw databases
are never copied wholesale into the web application.  This script emits:

* ``manifest.json``: all architecture and instruction summaries;
* ``details/<arch>/<mnemonic>.json``: lazy-loaded encoding and note detail.

Usage:
    python3 tools/build_viewer_data.py
    python3 tools/build_viewer_data.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes_audit as na  # noqa: E402
from isa_coverage import ARCHES, compute_mnemonics  # noqa: E402

REPO_ROOT = Path(na.REPO_ROOT)
DEFAULT_OUT = REPO_ROOT / "viewer" / "public" / "data"
SCHEMA_VERSION = 1

ARCH_META = {
    "sm70": ("Volta", "sm_70"),
    "sm75": ("Turing", "sm_75"),
    "sm80": ("Ampere", "sm_80"),
    "sm89": ("Ada", "sm_89"),
    "sm90": ("Hopper", "sm_90"),
    "sm100": ("Blackwell", "sm_100"),
    "sm103": ("Blackwell", "sm_103"),
    "sm107": ("Rubin", "sm_107"),
    "sm120": ("Blackwell RTX", "sm_120"),
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "instruction"


def note_metadata(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    status = na.parse_status_block(text)
    return {
        "title": na.first_heading(text) or path.stem.upper(),
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "status": status.get("Status", ""),
        "evidence": status.get("Evidence", ""),
        "confidence": status.get("Tier confidence", ""),
        "lastVerified": status.get("Last verified", ""),
        "openItems": status.get("Open items", ""),
        "markdown": na.strip_status_block(text),
    }


def instruction_types(variants: list[dict]) -> list[str]:
    values = {
        str(variant.get("properties", {}).get("INSTRUCTION_TYPE", ""))
        for variant in variants
    }
    return sorted(value for value in values if value)


def variant_pipes(variants: list[dict]) -> list[str]:
    values = {
        str(variant.get("pipe_suffix", ""))
        for variant in variants
        if variant.get("pipe_suffix")
    }
    return sorted(values)


def compact_variant(variant: dict) -> dict:
    return {
        "class": variant.get("class"),
        "alternate": bool(variant.get("is_alternate")),
        "parent": variant.get("parent"),
        "opcode": variant.get("opcode"),
        "opcodeBin": variant.get("opcode_bin"),
        "format": variant.get("format", {}).get("raw", ""),
        "slots": variant.get("format", {}).get("slots", []),
        "pipeSuffix": variant.get("pipe_suffix", ""),
        "encoding": variant.get("encoding", []),
        "properties": variant.get("properties", {}),
        "predicates": variant.get("predicates", {}),
        "conditions": variant.get("conditions", []),
        "remap": variant.get("remap"),
    }


def build_arch(arch: str) -> tuple[dict, dict[str, dict]]:
    db_path = REPO_ROOT / ARCHES[arch][0]
    if not db_path.exists():
        raise SystemExit(f"{db_path} missing -- run the architecture parser first")
    db = json.loads(db_path.read_text(encoding="utf-8"))
    compute_set = set(compute_mnemonics(arch))

    by_mnemonic: dict[str, list[dict]] = defaultdict(list)
    for variant in db.get("variants", []):
        mnemonic = (variant.get("mnemonic") or "").upper()
        if mnemonic:
            by_mnemonic[mnemonic].append(variant)

    notes_dir = REPO_ROOT / "notes" / arch / "instr"
    notes = {}
    if notes_dir.is_dir():
        for path in sorted(notes_dir.glob("*.md")):
            notes[path.stem.upper()] = note_metadata(path)

    instructions = []
    details = {}
    used_slugs: set[str] = set()
    for mnemonic in sorted(by_mnemonic):
        variants = by_mnemonic[mnemonic]
        slug = slugify(mnemonic)
        if slug in used_slugs:
            raise SystemExit(f"slug collision in {arch}: {mnemonic} -> {slug}")
        used_slugs.add(slug)

        note = notes.get(mnemonic)
        pipes = sorted(set(db.get("pipes", {}).get(mnemonic, [])) |
                       set(variant_pipes(variants)))
        opcodes = sorted({
            variant["opcode"]
            for variant in variants
            if isinstance(variant.get("opcode"), int)
        })
        opcode_text = [f"0x{opcode:x}" for opcode in opcodes]
        classes = sorted({variant.get("class", "") for variant in variants})
        types = instruction_types(variants)
        compute = mnemonic in compute_set

        summary = {
            "id": f"{arch}:{mnemonic}",
            "mnemonic": mnemonic,
            "slug": slug,
            "title": note["title"] if note else mnemonic,
            "pipe": pipes,
            "instructionTypes": types,
            "compute": compute,
            "variantCount": len(variants),
            "opcodes": opcode_text,
            "classes": classes,
            "hasNote": note is not None,
            "noteStatus": note["status"] if note else "",
            "evidence": note["evidence"] if note else "",
            "confidence": note["confidence"] if note else "",
        }
        instructions.append(summary)
        details[slug] = {
            "schemaVersion": SCHEMA_VERSION,
            "arch": arch,
            "summary": summary,
            "source": {
                "database": db_path.relative_to(REPO_ROOT).as_posix(),
                "note": note["path"] if note else "",
                "headers": db.get("meta", {}),
            },
            "variants": [compact_variant(variant) for variant in variants],
            "note": note,
        }

    display, canon = ARCH_META[arch]
    arch_record = {
        "id": arch,
        "canonical": canon,
        "displayName": display,
        "source": db_path.relative_to(REPO_ROOT).as_posix(),
        "counts": {
            "instructions": len(instructions),
            "documented": sum(item["hasNote"] for item in instructions),
            "compute": sum(item["compute"] for item in instructions),
            "variants": db.get("meta", {}).get("counts", {}).get("variants", 0),
            "mnemonics": db.get("meta", {}).get("counts", {}).get("mnemonics", 0),
        },
        "instructions": instructions,
    }
    return arch_record, details


def build() -> tuple[dict, dict[str, dict[str, dict]]]:
    architectures = []
    detail_tree: dict[str, dict[str, dict]] = {}
    for arch in sorted(ARCHES, key=lambda item: int(item[2:])):
        record, details = build_arch(arch)
        architectures.append(record)
        detail_tree[arch] = details
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "title": "NVIDIA SASS ISA",
        "architectures": architectures,
    }
    return manifest, detail_tree


def render(manifest: dict, detail_tree: dict[str, dict[str, dict]]) -> dict[Path, str]:
    files = {
        Path("manifest.json"): json.dumps(
            manifest, ensure_ascii=False, separators=(",", ":")) + "\n"
    }
    for arch, details in detail_tree.items():
        for slug, detail in details.items():
            files[Path("details") / arch / f"{slug}.json"] = json.dumps(
                detail, ensure_ascii=False, separators=(",", ":")) + "\n"
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    manifest, detail_tree = build()
    files = render(manifest, detail_tree)
    out_root = Path(args.out)

    if args.check:
        stale = []
        for relpath, content in files.items():
            path = out_root / relpath
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(relpath.as_posix())
        if stale:
            print(f"CHECK FAILED: {len(stale)} stale or missing file(s): "
                  f"{', '.join(stale[:12])}", file=sys.stderr)
            return 1
        print(f"CHECK OK: {len(files)} viewer data file(s) up to date")
        return 0

    for relpath, content in files.items():
        path = out_root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    instruction_count = sum(
        arch["counts"]["instructions"] for arch in manifest["architectures"])
    print(f"wrote {len(files)} files under {out_root}")
    print(f"  architectures: {len(manifest['architectures'])}")
    print(f"  instruction pages: {instruction_count}")
    print(f"  manifest bytes: {len(files[Path('manifest.json')])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
