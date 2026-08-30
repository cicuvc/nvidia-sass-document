#!/usr/bin/env python3
"""Extract the sm_75 / sm_80 SASS ISA dumps into queryable JSON DBs.

There are no sm_75/sm_80 latencies dumps, so this driver reuses
parse_sm90.py's machinery verbatim (the dump format is identical — the
parser runs with 0 errors / 0 warnings on both files) and derives the
`pipes` section from the pipe suffixes in each variant's OPCODES names
instead of an OPERATION SETS block (informational only).

Reads:  sm_75_instructions.txt, sm_80_instructions.txt
Writes: sm75.json, sm80.json  (repo root; regenerable, keep gitignored)

See notes/ARCH_DIFF.md for what these DBs are used for.
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import parse_sm90 as P  # noqa: E402


def build(instr_name, out_name):
    P.INSTR = REPO / instr_name
    lines = P.read_lines(P.INSTR)

    i_params = P.find_line(lines, lambda l: l.rstrip() == "PARAMETERS")
    i_consts = P.find_line(lines, lambda l: l.rstrip() == "CONSTANTS")
    i_strmap = P.find_line(lines, lambda l: l.rstrip() == "STRING_MAP")
    i_regs = P.find_line(lines, lambda l: l.rstrip() == "REGISTERS")
    i_tables = P.find_line(lines, lambda l: l.rstrip() == "TABLES")
    i_opprops = P.find_line(lines, lambda l: l.rstrip() == "OPERATION PROPERTIES")
    i_funit = P.find_line(lines, lambda l: l.rstrip() == "FUNIT uC")
    i_class = P.find_line(lines, lambda l: P.CLASS_RE.match(l) is not None)

    variants, warnings = P.parse_variants(lines, i_class)

    # pipes: derive from opcodes_raw names' pipe suffixes (no latencies file)
    sufs = sorted(P.PIPE_SUFFIXES, key=len, reverse=True)
    pipes = {}
    for x in variants:
        for e in (x.get("opcodes_raw") or []):
            nm = e["name"]
            for suf in sufs:
                if nm.endswith(suf) and nm != suf:
                    pipes.setdefault(nm[:-len(suf)], set()).add(suf[:-5])
                    break
    pipes = {k: sorted(v) for k, v in pipes.items()}

    db = {
        "meta": {
            "source": instr_name,
            "arch_header": lines[0].strip(),
            "encoding_width": 128,
            "note": ("header says Volta / WORD_SIZE 64 (stale); "
                     "BITS_13_91_91_11_0_opcode proves 128-bit encoding"),
        },
        "parameters": P.parse_kv_block(lines, i_params + 1, i_consts),
        "constants": P.parse_kv_block(lines, i_consts + 1,
                                      i_strmap if i_strmap > 0 else i_regs),
        "enums": P.parse_enums(lines, i_regs + 1, i_tables),
        "tables": P.parse_tables(lines, i_tables + 1, i_opprops),
        "funit_uc": P.parse_funit(lines, i_funit + 1, i_class),
        "pipes": pipes,
        "variants": variants,
        "_warnings": warnings,
    }

    # structural validation (arch-agnostic part of P.validate)
    errs = []
    for x in variants:
        if x.get("remap"):
            continue  # pseudo-instruction: REMAP directive, no bit encoding
        if x["opcode"] is None:
            errs.append(f"{x['class']}: no opcode")
        if not any(f["rhs_kind"] == "opcode" for f in x["encoding"]):
            errs.append(f"{x['class']}: no opcode field in ENCODING")
        for f in x["encoding"]:
            for hi, lo in f["targets"]:
                if not (0 <= lo <= hi <= 127):
                    errs.append(f"{x['class']}.{f['name']}: bad range {hi}:{lo}")
            span = sum(hi - lo + 1 for hi, lo in f["targets"])
            if f["targets"] and span != f["width"]:
                errs.append(f"{x['class']}.{f['name']}: "
                            f"width {f['width']} != span {span}")

    db["meta"]["counts"] = {
        "variants": len(variants),
        "mnemonics": len({x["mnemonic"] for x in variants if x["mnemonic"]}),
        "enums": len(db["enums"]), "tables": len(db["tables"]),
        "funit_fields": len(db["funit_uc"]), "pipes": len(pipes),
    }
    out = REPO / out_name
    out.write_text(json.dumps(db, indent=1), encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size/1e6:.1f} MB)")
    for k, v in db["meta"]["counts"].items():
        print(f"  {k}: {v}")
    for e in errs:
        print("  ERR", e)
    for w in warnings:
        print("  WARN", w)
    return len(errs)


def main():
    ap = argparse.ArgumentParser(
        description="Extract sm_75/sm_80 SASS ISA -> JSON (parse_sm90 backend)")
    ap.add_argument("--indent", type=int, default=1)
    args = ap.parse_args()
    n = 0
    n += build("sm_75_instructions.txt", "sm75.json")
    n += build("sm_80_instructions.txt", "sm80.json")
    if n:
        sys.exit(f"{n} structural errors")


if __name__ == "__main__":
    main()
