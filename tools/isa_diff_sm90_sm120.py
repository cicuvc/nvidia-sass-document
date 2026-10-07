#!/usr/bin/env python3
"""Diff the sm_90 and sm_120 ISA databases mnemonic by mnemonic.

Answers the question the sm_120 notes need: *which* instructions exist on both parts,
which are Blackwell-only, which were dropped, and where the operand shapes or opcodes
differ between the two dumps.

Usage
-----
    python3 tools/isa_diff_sm90_sm120.py                      # human summary
    python3 tools/isa_diff_sm90_sm120.py --json out.json      # full machine-readable diff
    python3 tools/isa_diff_sm90_sm120.py --mnem LDG           # one mnemonic, both arches
    python3 tools/isa_diff_sm90_sm120.py --write-report notes/sm120/isa_diff_sm90.md

The databases are produced by ``parse_sm90.py`` / ``parse_sm120.py`` and are gitignored.
Stdlib only, like the rest of ``tools/``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name: str) -> dict:
    path = os.path.join(REPO_ROOT, name)
    if not os.path.exists(path):
        raise SystemExit(f"{name} missing -- run tools/parse_{name.replace('.json', '')}.py first")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def by_mnemonic(variants: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for variant in variants:
        out[(variant.get("mnemonic") or variant.get("class") or "?").upper()].append(variant)
    return dict(out)


def shapes(variants: list[dict]) -> set[str]:
    """The operand/format shapes a mnemonic takes, e.g. ``RRR``, ``RIR``, ``URa_Rc``.

    Taken from the CLASS name suffix, which is how the spec names the operand layout.
    """
    got = set()
    for variant in variants:
        cls = variant.get("class", "")
        got.add(cls.split("__", 1)[-1] if "__" in cls else cls)
    return got


def opcodes(variants: list[dict]) -> set[str]:
    got = set()
    for variant in variants:
        op = variant.get("opcode")
        if isinstance(op, int):
            got.add(f"0x{op:x}")
        elif op:
            got.add(str(op))
    return got


def compare(sm90: dict, sm120: dict) -> dict:
    m90, m120 = by_mnemonic(sm90["variants"]), by_mnemonic(sm120["variants"])
    both = sorted(set(m90) & set(m120))
    only120 = sorted(set(m120) - set(m90))
    only90 = sorted(set(m90) - set(m120))

    changed = {}
    for name in both:
        s90_shapes, s120_shapes = shapes(m90[name]), shapes(m120[name])
        s90_ops, s120_ops = opcodes(m90[name]), opcodes(m120[name])
        if s90_shapes != s120_shapes or s90_ops != s120_ops:
            changed[name] = {
                "sm90_variants": len(m90[name]),
                "sm120_variants": len(m120[name]),
                "shapes_only_sm90": sorted(s90_shapes - s120_shapes),
                "shapes_only_sm120": sorted(s120_shapes - s90_shapes),
                "opcodes_only_sm90": sorted(s90_ops - s120_ops),
                "opcodes_only_sm120": sorted(s120_ops - s90_ops),
            }
    return {
        "sm90_mnemonics": len(m90),
        "sm120_mnemonics": len(m120),
        "common": both,
        "only_sm120": only120,
        "only_sm90": only90,
        "changed": changed,
    }


def mnemonic_report(name: str, cmp: dict) -> None:
    """Everything both dumps say about one mnemonic."""
    sm90, sm120 = load("sm90.json"), load("sm120.json")
    for label, db in (("sm_90", sm90), ("sm_120", sm120)):
        variants = by_mnemonic(db["variants"]).get(name.upper(), [])
        print(f"== {name.upper()} in {label}: {len(variants)} variant(s)")
        for variant in variants:
            op = variant.get("opcode")
            op_txt = f"0x{op:x}" if isinstance(op, int) else str(op)
            props = variant.get("properties") or {}
            print(f"   {variant['class']:44s} op={op_txt:8s} "
                  f"fmt={str(variant.get('format'))[:56]:56s} "
                  f"type={props.get('INSTRUCTION_TYPE', '?')} "
                  f"dest={props.get('IDEST_SIZE', '?')} "
                  f"srcA={props.get('ISRC_A_SIZE', '?')}")


def write_report(cmp: dict, dest: str) -> None:
    lines = [
        "# sm_90 vs sm_120 mnemonic diff (generated)",
        "",
        "Produced by `tools/isa_diff_sm90_sm120.py --write-report`. **Do not hand-edit.**",
        "Source: the two nvdisasm ISA dumps via `sm90.json` / `sm120.json`. The diff is",
        "*structural*: it reports mnemonics present in one dump only, and opcodes/operand",
        "shapes that differ, not semantic differences (those need a probe).",
        "",
        f"- sm_90 mnemonics: **{cmp['sm90_mnemonics']}**",
        f"- sm_120 mnemonics: **{cmp['sm120_mnemonics']}**",
        f"- common: **{len(cmp['common'])}**, sm_120-only: **{len(cmp['only_sm120'])}**, "
        f"sm_90-only: **{len(cmp['only_sm90'])}**, structurally changed: **{len(cmp['changed'])}**",
        "",
        "## sm_120-only mnemonics",
        "",
        "```",
        " ".join(cmp["only_sm120"]),
        "```",
        "",
        "## sm_90-only mnemonics",
        "",
        "```",
        " ".join(cmp["only_sm90"]),
        "```",
        "",
        "## Changed operand shapes or opcodes (present in both)",
        "",
        "| mnemonic | sm90 var | sm120 var | shapes only sm90 | shapes only sm120 | opcodes only sm90 | opcodes only sm120 |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for name in sorted(cmp["changed"]):
        row = cmp["changed"][name]
        lines.append("| `{}` | {} | {} | {} | {} | {} | {} |".format(
            name, row["sm90_variants"], row["sm120_variants"],
            ", ".join(f"`{s}`" for s in row["shapes_only_sm90"]) or "-",
            ", ".join(f"`{s}`" for s in row["shapes_only_sm120"]) or "-",
            ", ".join(f"`{o}`" for o in row["opcodes_only_sm90"]) or "-",
            ", ".join(f"`{o}`" for o in row["opcodes_only_sm120"]) or "-"))
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {dest}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", metavar="PATH", help="write the full diff as JSON")
    ap.add_argument("--mnem", metavar="NAME", help="print both dumps' variants for one mnemonic")
    ap.add_argument("--write-report", metavar="PATH", help="write a markdown report")
    ap.add_argument("--list-only", choices=("sm120", "sm90"), help="print one-only mnemonics")
    args = ap.parse_args(argv)

    sm90, sm120 = load("sm90.json"), load("sm120.json")
    cmp = compare(sm90, sm120)

    if args.mnem:
        mnemonic_report(args.mnem, cmp)
    if args.list_only:
        names = cmp["only_sm120"] if args.list_only == "sm120" else cmp["only_sm90"]
        print(" ".join(names))
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(cmp, fh, indent=1, sort_keys=True)
        print(f"wrote {args.json}")
    if args.write_report:
        write_report(cmp, args.write_report)
    if not (args.mnem or args.json or args.write_report or args.list_only):
        print(f"sm_90 mnemonics        {cmp['sm90_mnemonics']}")
        print(f"sm_120 mnemonics       {cmp['sm120_mnemonics']}")
        print(f"common                 {len(cmp['common'])}")
        print(f"only in sm_120         {len(cmp['only_sm120'])}")
        print(f"only in sm_90          {len(cmp['only_sm90'])}")
        print(f"changed shapes/opcodes {len(cmp['changed'])}")
        print("\nonly in sm_120:")
        print("  " + " ".join(cmp["only_sm120"]))
        print("\nonly in sm_90:")
        print("  " + " ".join(cmp["only_sm90"]))
        top = Counter({k: len(v["shapes_only_sm120"]) + len(v["opcodes_only_sm120"])
                       for k, v in cmp["changed"].items()})
        print("\nmost-changed (by new shapes/opcodes):")
        for name, count in top.most_common(25):
            print(f"  {name:12s} +{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
