#!/usr/bin/env python3
"""Query the extracted sm_90 SASS ISA DB (sm90.json).

Subcommands:
  mnem   <NAME>          list all encoding variants of a mnemonic
  class  <name> [-v]     show one variant (full detail with -v)
  opcode <hex|0b..|int>  list classes whose 13-bit opcode matches
  layout <class>         128-bit ASCII field map for a variant
  fields <regex>         find encoding field names across all classes
  enum   <Name>          show a modifier value-map
  table  <Name>          show a decode TABLES_* table
  pipe   <MNEMONIC>      functional-unit (pipe) membership
  stats                  DB summary

Reads sm90.json next to the repo root by default. Stdlib only.
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "sm100.json"


def load(db_path):
    with open(db_path, encoding="utf-8") as fh:
        return json.load(fh)


def by_class(db):
    return {v["class"]: v for v in db["variants"]}


def fmt_opcode(v):
    return f"0b{v['opcode_bin']} (0x{v['opcode']:x}, {v['opcode']})" if v["opcode"] is not None else "-"


# --------------------------------------------------------------------------
def cmd_mnem(db, args):
    hits = [v for v in db["variants"] if (v["mnemonic"] or "").upper() == args.name.upper()]
    if not hits:
        print(f"no variants for mnemonic {args.name!r}")
        return 1
    print(f"{args.name.upper()}: {len(hits)} variant(s), pipes={db['pipes'].get(args.name.upper(), [])}")
    for v in hits:
        alt = " [ALT]" if v["is_alternate"] else ""
        print(f"  {fmt_opcode(v):<28} {v['class']}{alt}")
        print(f"      {v['format']['raw'][:110]}")
    return 0


def cmd_class(db, args):
    bc = by_class(db)
    matches = [c for c in bc if args.name.lower() in c.lower()]
    if not matches:
        print(f"no class matching {args.name!r}")
        return 1
    if len(matches) > 1 and args.name not in bc:
        print(f"{len(matches)} classes match {args.name!r}:")
        for c in matches[:40]:
            print("  " + c)
        return 0
    name = args.name if args.name in bc else matches[0]
    v = bc[name]
    print(f"CLASS {v['class']}" + (" (ALTERNATE)" if v["is_alternate"] else ""))
    if v["parent"]:
        print(f"  parent: {v['parent']}")
    print(f"  mnemonic: {v['mnemonic']}   pipe_suffix: {v['pipe_suffix']}   opcode: {fmt_opcode(v)}")
    print(f"  pipes: {db['pipes'].get(v['mnemonic'], [])}")
    if v.get("remap"):
        print(f"  REMAP: {v['remap'][:120]}")
    print(f"\n  FORMAT: {v['format']['raw']}")
    print("  slots:")
    for s in v["format"]["slots"]:
        kind = "mod" if s["modifier"] else "opd"
        d = f' = "{s["default"]}"' if s["default"] is not None else ""
        print(f"    [{kind}] {s['name']:<16} {s['type']}{d}")
    print(f"\n  PROPERTIES: INSTRUCTION_TYPE={v['properties'].get('INSTRUCTION_TYPE')}  "
          f"VIRTUAL_QUEUE={v['predicates'].get('VIRTUAL_QUEUE')}")
    for k in ("IDEST_SIZE", "ISRC_A_SIZE", "ISRC_B_SIZE", "ISRC_C_SIZE", "ISRC_E_SIZE"):
        if k in v["predicates"]:
            print(f"    {k} = {v['predicates'][k]}")
    if args.verbose:
        print("\n  CONDITIONS:")
        for c in v["conditions"]:
            print(f"    [{c['error']}] {c['message']}")
            print(f"        {c['predicate']}")
    print("\n  ENCODING:")
    for f in sorted(v["encoding"], key=lambda f: -f["targets"][0][0] if f["targets"] else 0):
        tg = ",".join(f"[{hi}:{lo}]" for hi, lo in f["targets"])
        sh = " (+)" if f["shared"] else ""
        print(f"    {tg:<20} w{f['width']:<3} {f['name']:<22} <= {f['rhs']}  <{f['rhs_kind']}>{sh}")
    return 0


def cmd_opcode(db, args):
    tok = args.value
    try:
        val = int(tok, 0) if not re.fullmatch(r"[01]+", tok) or tok.startswith("0b") else int(tok, 2)
    except ValueError:
        val = int(tok, 2)
    hits = [v for v in db["variants"] if v["opcode"] == val]
    print(f"opcode 0x{val:x} (0b{val:b}, {val}): {len(hits)} class(es)")
    for v in hits:
        alt = " [ALT]" if v["is_alternate"] else ""
        print(f"  {v['mnemonic']:<14} {v['class']}{alt}")
    return 0 if hits else 1


def cmd_layout(db, args):
    bc = by_class(db)
    if args.name not in bc:
        m = [c for c in bc if args.name.lower() in c.lower()]
        if len(m) != 1:
            print(f"specify exactly one class ({len(m)} match)")
            for c in m[:30]:
                print("  " + c)
            return 1
        args.name = m[0]
    v = bc[args.name]
    grid = [None] * 128
    for f in v["encoding"]:
        for hi, lo in f["targets"]:
            for b in range(lo, hi + 1):
                grid[b] = f["name"]
    print(f"{v['class']}  opcode={fmt_opcode(v)}  ({v['mnemonic']})")
    print("bit  field")
    for f in sorted(v["encoding"], key=lambda f: -(f["targets"][0][0] if f["targets"] else 0)):
        tg = ",".join(f"[{hi}:{lo}]" for hi, lo in f["targets"])
        print(f"  {tg:<20} {f['name']:<22} <= {f['rhs']}")
    # compact 128-bit occupancy strip (127 -> 0, MSB left)
    strip = "".join("." if grid[b] is None else "#" for b in range(127, -1, -1))
    print("\n127" + " " * 58 + "0")
    for i in range(0, 128, 64):
        print("  " + strip[i:i + 64])
    return 0


def cmd_fields(db, args):
    rx = re.compile(args.regex, re.I)
    seen = {}
    for v in db["variants"]:
        for f in v["encoding"]:
            if rx.search(f["name"]):
                seen.setdefault(f["name"], set()).add((tuple(map(tuple, f["targets"])), f["rhs_kind"]))
    for name in sorted(seen):
        variants = seen[name]
        print(f"{name}: {len(variants)} distinct (bits,kind)")
        for tg, kind in sorted(variants)[:6]:
            print("   " + ",".join(f"[{hi}:{lo}]" for hi, lo in tg) + f"  <{kind}>")
    print(f"\n{len(seen)} matching field name(s)")
    return 0 if seen else 1


def cmd_enum(db, args):
    e = db["enums"].get(args.name)
    if e is None:
        m = [n for n in db["enums"] if args.name.lower() in n.lower()]
        print(f"no exact enum {args.name!r}." + (f" similar: {m[:20]}" if m else ""))
        return 1
    print(f"enum {args.name} ({len(e)} values):")
    for k, val in sorted(e.items(), key=lambda kv: (kv[1] is None, kv[1])):
        print(f"  {str(val):<6} {k}")
    return 0


def cmd_table(db, args):
    t = db["tables"].get(args.name)
    if t is None:
        m = [n for n in db["tables"] if args.name.lower() in n.lower()]
        print(f"no exact table {args.name!r}." + (f" similar: {m[:20]}" if m else ""))
        return 1
    print(f"table {args.name}  inputs={t['inputs']}  illegal={t['illegal']}  rows={len(t['rows'])}")
    for r in t["rows"][:args.limit]:
        print("  " + " ".join(r["in"]) + " -> " + r["out"])
    if len(t["rows"]) > args.limit:
        print(f"  ... ({len(t['rows']) - args.limit} more; use --limit)")
    return 0


def cmd_pipe(db, args):
    mn = args.name.upper()
    print(f"{mn}: pipes = {db['pipes'].get(mn, [])}")
    return 0


def cmd_stats(db, args):
    for k, v in db["meta"]["counts"].items():
        print(f"  {k}: {v}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("mnem"); p.add_argument("name"); p.set_defaults(fn=cmd_mnem)
    p = sub.add_parser("class"); p.add_argument("name"); p.add_argument("-v", "--verbose", action="store_true"); p.set_defaults(fn=cmd_class)
    p = sub.add_parser("opcode"); p.add_argument("value"); p.set_defaults(fn=cmd_opcode)
    p = sub.add_parser("layout"); p.add_argument("name"); p.set_defaults(fn=cmd_layout)
    p = sub.add_parser("fields"); p.add_argument("regex"); p.set_defaults(fn=cmd_fields)
    p = sub.add_parser("enum"); p.add_argument("name"); p.set_defaults(fn=cmd_enum)
    p = sub.add_parser("table"); p.add_argument("name"); p.add_argument("--limit", type=int, default=40); p.set_defaults(fn=cmd_table)
    p = sub.add_parser("pipe"); p.add_argument("name"); p.set_defaults(fn=cmd_pipe)
    p = sub.add_parser("stats"); p.set_defaults(fn=cmd_stats)

    args = ap.parse_args()
    db = load(args.db)
    return args.fn(db, args)


if __name__ == "__main__":
    sys.exit(main())
