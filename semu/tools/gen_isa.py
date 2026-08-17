#!/usr/bin/env python3
"""Generate semu's compiled-in C++ ISA tables from sm120.json.

Deterministic generator: identical repo state -> byte-identical outputs.  It
produces the build inputs

    semu/generated/isa_data.hpp
    semu/generated/isa_data.cpp

containing compact tables for every one of the 1414 sm120 encoding variants
(fields, format slots, legality conditions, size predicates), the modifier
enums, decode tables and pipe names.  The C++ decoder (src/decoder/) consumes
only these generated tables -- never the raw dump -- satisfying the Phase 1
exit criterion that backends depend only on generated IR.

Usage:
    python3 semu/tools/gen_isa.py [--db PATH] [--output-dir DIR]
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARCH = "sm120"

RHS_KIND = {"slot": 0, "slot_attr": 1, "opcode": 2, "num": 3, "star_num": 4,
            "star_slot": 5, "table_fn": 6, "other_fn": 7}

SCALE_RE = re.compile(r"(.*?)(?:\s+SCALE\s+(\d+))?$")


def cq(s: str) -> str:
    """C string literal (escape backslash, quote, control chars)."""
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def parse_int(s: str):
    try:
        return int(s, 0)
    except ValueError:
        return None


def field_rows(db):
    """Flatten all tables into a deterministic row list.

    Rows keep their original (dump/JSON) order within each table so the
    decoder's first-match reverse lookup agrees with the reference encoder's
    ``_lookup_table`` (also first-match).  Only the table grouping itself is
    sorted by name for determinism."""
    rows = []
    for name in sorted(db["tables"]):
        t = db["tables"][name]
        for r in t["rows"]:
            in_str = ",".join(str(a) for a in r["in"])
            rows.append((name, in_str, str(r["out"]), bool(t.get("illegal"))))
    return rows


def enum_rows(db):
    rows = []
    for tname in sorted(db["enums"]):
        e = db["enums"][tname]
        for k in sorted(e, key=lambda x: (str(x),)):
            v = e[k]
            rows.append((tname, k, -1 if v is None else int(v)))
    rows.sort()
    return rows


def variant_fields(v):
    """Deterministic field list: name -> (ranges, width, rhs_kind, rhs, scale)."""
    out = []
    for f in v["encoding"]:
        targets = f["targets"]
        ranges = []
        for hi, lo in targets:
            ranges.append((int(hi), int(lo)))
        rhs = f["rhs"]
        scale = 1
        m = SCALE_RE.match(rhs)
        if m and m.group(2):
            scale = int(m.group(2))
            rhs = m.group(1)
        out.append({
            "name": f["name"],
            "ranges": ranges,
            "width": int(f["width"]),
            "rhs_kind": RHS_KIND[f["rhs_kind"]],
            "rhs": rhs,
            "scale": scale,
        })
    return out


def variant_slots(v):
    out = []
    for s in v["format"]["slots"]:
        out.append({
            "name": s["name"],
            "type": s["type"],
            "default": s.get("default"),
            "modifier": bool(s.get("modifier", False)),
        })
    return out


def variant_conds(v):
    out = []
    for c in v["conditions"]:
        out.append({
            "error": c["error"],
            "predicate": c["predicate"],
            "message": c.get("message", ""),
        })
    return out


def build_variants(db):
    vs = []
    for v in db["variants"]:
        vs.append({
            "mnemonic": v["mnemonic"],
            "class": v["class"],
            "opcode": int(v["opcode"]),
            "pipe": v["pipe_suffix"],
            "alternate": bool(v.get("is_alternate", False)),
            "fields": variant_fields(v),
            "slots": variant_slots(v),
            "conds": variant_conds(v),
            "preds": [(k, str(val)) for k, val in
                      sorted(v.get("predicates", {}).items())],
        })
    vs.sort(key=lambda v: (v["opcode"], v["mnemonic"], v["class"]))
    return vs


def emit_hpp(out: Path) -> None:
    L = [
        "// Generated file -- do not edit.  Regenerate with:",
        "//   python3 semu/tools/gen_isa.py",
        "#pragma once",
        "",
        "#include <cstdint>",
        "",
        "namespace semu::isa {",
        "",
        "// Modifier/operand enums.",
        "struct EnumEntry {",
        "    const char* name;",
        "    std::int32_t value;   // -1 = valueless (presence means print)",
        "};",
        "struct EnumDef {",
        "    const char* name;",
        "    std::uint32_t n;",
        "    const EnumEntry* entries;",
        "};",
        "",
        "// Decode tables (rows' `in` args comma-joined; `out` raw string).",
        "struct TableDef {",
        "    const char* name;",
        "    std::uint32_t n;",
        "    const char* const* in;",
        "    const char* const* out;",
        "    bool illegal;          // *_illegal_encodings rejection table",
        "};",
        "",
        "// Encoding field: one or more disjoint bit ranges (MSB-first).",
        "struct Field {",
        "    const char* name;",
        "    std::uint8_t width;",
        "    std::uint8_t nranges;",
        "    const std::uint8_t* ranges;   // flattened [hi,lo] pairs",
        "    const char* rhs;",
        "    std::uint8_t rhs_kind;        // 0 slot,1 slot_attr,2 opcode,",
        "                                 // 3 num,4 star_num,5 star_slot,",
        "                                 // 6 table_fn,7 other_fn",
        "    std::uint8_t scale;           // decode scale (logical = field*scale)",
        "};",
        "// Format slot.",
        "struct Slot {",
        "    const char* name;",
        "    const char* type;",
        "    const char* dflt;             // raw default string, may be null",
        "    bool modifier;",
        "};",
        "// Legality condition.",
        "struct Cond {",
        "    const char* error;",
        "    const char* predicate;",
        "    const char* message;",
        "};",
        "// Size/pipe predicate (IDEST_SIZE, ISRC_*_SIZE, VIRTUAL_QUEUE, ...).",
        "struct Pred {",
        "    const char* key;",
        "    const char* value;",
        "};",
        "",
        "struct Variant {",
        "    const char* mnemonic;",
        "    const char* variant_class;",
        "    std::uint16_t opcode;",
        "    std::uint16_t pipe;",
        "    std::uint16_t nslots;   const Slot* slots;",
        "    std::uint16_t nfields;  const Field* fields;",
        "    std::uint16_t nconds;   const Cond* conds;",
        "    std::uint16_t npreds;   const Pred* preds;",
        "    bool alternate;         // ALTERNATE CLASS (not a decode candidate)",
        "};",
        "",
        "// Flat storage (all rows in one array for locality).",
        "extern const EnumDef kEnums[];       extern const std::uint32_t kNumEnums;",
        "extern const TableDef kTables[];      extern const std::uint32_t kNumTables;",
        "extern const Variant kVariants[];     extern const std::uint32_t kNumVariants;",
        "// Opcode candidate index: for each of the 8192 13-bit opcodes, the",
        "// [kOpcodeStart[op], kOpcodeStart[op+1]) slice of kVariants.",
        "extern const std::uint32_t kOpcodeStart[8193];",
        "extern const char* const kPipes[];    extern const std::uint32_t kNumPipes;",
        "extern const char* const kParameters[]; extern const std::int64_t kParameterVals[];",
        "extern const std::uint32_t kNumParameters;",
        "extern const char* const kConstants[]; extern const std::int64_t kConstantVals[];",
        "extern const std::uint32_t kNumConstants;",
        "",
        "}  // namespace semu::isa",
        "",
    ]
    out.write_text("\n".join(L), encoding="utf-8")


def emit_cpp(out: Path, db: dict, variants: list) -> None:
    lines = [
        "// Generated file -- do not edit.  Regenerate with:",
        "//   python3 semu/tools/gen_isa.py",
        "#include \"isa_data.hpp\"",
        "",
        "namespace semu::isa {",
    ]

    # ---- enums ----
    erows = enum_rows(db)
    enum_names = sorted({r[0] for r in erows})
    by_enum = {n: [r for r in erows if r[0] == n] for n in enum_names}
    lines.append("")
    lines.append("namespace {")
    lines.append("constexpr EnumEntry kEnumEntries[] = {")
    for n in enum_names:
        for _, k, v in by_enum[n]:
            lines.append(f"    {{{cq(k)}, {v}}},")
    lines.append("};")
    lines.append("}")
    lines.append("")
    lines.append(f"const EnumDef kEnums[] = {{")
    off = 0
    for n in enum_names:
        lines.append(
            f"    {{{cq(n)}, {len(by_enum[n])}, &kEnumEntries[{off}]}},")
        off += len(by_enum[n])
    lines.append("};")
    lines.append(f"const std::uint32_t kNumEnums = {len(enum_names)};")
    lines.append("")

    # ---- tables ----
    trows = field_rows(db)
    table_names = sorted({r[0] for r in trows})
    by_table = {n: [r for r in trows if r[0] == n] for n in table_names}
    in_all = []
    out_all = []
    for n in table_names:
        in_all += [r[1] for r in by_table[n]]
        out_all += [r[2] for r in by_table[n]]
    lines.append("namespace {")
    lines.append("constexpr const char* kTableIn[] = {")
    for s in in_all:
        lines.append(f"    {cq(s)},")
    lines.append("};")
    lines.append("constexpr const char* kTableOut[] = {")
    for s in out_all:
        lines.append(f"    {cq(s)},")
    lines.append("};")
    lines.append("}")
    lines.append("")
    lines.append(f"const TableDef kTables[] = {{")
    off = 0
    for n in table_names:
        rows = by_table[n]
        lines.append(
            f"    {{{cq(n)}, {len(rows)}, &kTableIn[{off}], "
            f"&kTableOut[{off}], {'true' if db['tables'][n].get('illegal') else 'false'}}},")
        off += len(rows)
    lines.append("};")
    lines.append(f"const std::uint32_t kNumTables = {len(table_names)};")
    lines.append("")

    # ---- pipes ----
    pipes = sorted({v["pipe"] for v in variants})
    lines.append("namespace {")
    lines.append("constexpr const char* kPipeNames[] = {")
    for p in pipes:
        lines.append(f"    {cq(p)},")
    lines.append("};")
    lines.append("}")
    lines.append("")
    lines.append("const char* const kPipes[] = {")
    for p in pipes:
        lines.append(f"    {cq(p)},")
    lines.append("};")
    lines.append(f"const std::uint32_t kNumPipes = {len(pipes)};")
    pipe_idx = {p: i for i, p in enumerate(pipes)}
    lines.append("")

    # ---- parameters / constants ----
    pkeys = sorted(db["parameters"])
    lines.append("namespace {")
    lines.append("constexpr const char* kParamKeys[] = {")
    for k in pkeys:
        lines.append(f"    {cq(k)},")
    lines.append("};")
    lines.append("}")
    lines.append("const char* const kParameters[] = {")
    for k in pkeys:
        lines.append(f"    {cq(k)},")
    lines.append("};")
    lines.append("const std::int64_t kParameterVals[] = {")
    for k in pkeys:
        lines.append(f"    {int(db['parameters'][k])},")
    lines.append("};")
    lines.append(f"const std::uint32_t kNumParameters = {len(pkeys)};")
    lines.append("")

    ckeys = sorted(db["constants"])
    lines.append("namespace {")
    lines.append("constexpr const char* kConstKeys[] = {")
    for k in ckeys:
        lines.append(f"    {cq(k)},")
    lines.append("};")
    lines.append("}")
    lines.append("const char* const kConstants[] = {")
    for k in ckeys:
        lines.append(f"    {cq(k)},")
    lines.append("};")
    lines.append("const std::int64_t kConstantVals[] = {")
    for k in ckeys:
        lines.append(f"    {int(db['constants'][k])},")
    lines.append("};")
    lines.append(f"const std::uint32_t kNumConstants = {len(ckeys)};")
    lines.append("")

    # ---- variants ----
    lines.append("namespace {")
    # field ranges storage
    all_ranges = []
    lines.append("constexpr std::uint8_t kFieldRanges[] = {")
    for v in variants:
        for f in v["fields"]:
            for hi, lo in f["ranges"]:
                all_ranges.append((hi, lo))
    for hi, lo in all_ranges:
        lines.append(f"    {hi}, {lo},")
    lines.append("};")
    lines.append("")

    # field structs
    lines.append("constexpr Field kFields[] = {")
    roff = 0
    for v in variants:
        for f in v["fields"]:
            n = len(f["ranges"])
            lines.append(
                f"    {{{cq(f['name'])}, {f['width']}, {n}, "
                f"&kFieldRanges[{roff}], {cq(f['rhs'])}, {f['rhs_kind']}, "
                f"{f['scale']}}},")
            roff += 2 * n
    lines.append("};")
    lines.append("")

    # slot structs
    lines.append("constexpr Slot kSlots[] = {")
    for v in variants:
        for s in v["slots"]:
            dflt = cq(str(s["default"])) if s["default"] is not None else "nullptr"
            lines.append(
                f"    {{{cq(s['name'])}, {cq(s['type'])}, {dflt}, "
                f"{'true' if s['modifier'] else 'false'}}},")
    lines.append("};")
    lines.append("")

    # cond structs
    lines.append("constexpr Cond kConds[] = {")
    for v in variants:
        for c in v["conds"]:
            lines.append(
                f"    {{{cq(c['error'])}, {cq(c['predicate'])}, "
                f"{cq(c['message'])}}},")
    lines.append("};")
    lines.append("")

    # pred structs
    lines.append("constexpr Pred kPreds[] = {")
    for v in variants:
        for k, val in v["preds"]:
            lines.append(f"    {{{cq(k)}, {cq(val)}}},")
    lines.append("};")
    lines.append("}")  # anonymous namespace
    lines.append("")

    # variant structs
    lines.append(f"const Variant kVariants[] = {{")
    foff = soff = coff = poff = 0
    for v in variants:
        nf = len(v["fields"])
        ns = len(v["slots"])
        nc = len(v["conds"])
        np_ = len(v["preds"])
        lines.append(
            f"    {{{cq(v['mnemonic'])}, {cq(v['class'])}, {v['opcode']}, "
            f"{pipe_idx[v['pipe']]}, {ns}, &kSlots[{soff}], {nf}, "
            f"&kFields[{foff}], {nc}, &kConds[{coff}], {np_}, "
            f"&kPreds[{poff}], {'true' if v['alternate'] else 'false'}}},")
        foff += nf
        soff += ns
        coff += nc
        poff += np_
    lines.append("};")
    lines.append(f"const std::uint32_t kNumVariants = {len(variants)};")
    lines.append("")

    # opcode index
    opcode_starts = [0] * 8193
    i = 0
    for op in range(8192):
        opcode_starts[op] = i
        while i < len(variants) and variants[i]["opcode"] == op:
            i += 1
    opcode_starts[8192] = len(variants)
    lines.append("const std::uint32_t kOpcodeStart[8193] = {")
    for row in range(0, 8193, 16):
        chunk = opcode_starts[row:row + 16]
        lines.append("    " + ", ".join(str(x) for x in chunk) + ",")
    lines.append("};")

    lines.append("")
    lines.append("}  // namespace semu::isa")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "sm120.json"))
    ap.add_argument("--output-dir", default=str(REPO / "semu" / "generated"))
    args = ap.parse_args()

    db = json.load(open(args.db))
    variants = build_variants(db)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    emit_hpp(out_dir / "isa_data.hpp")
    emit_cpp(out_dir / "isa_data.cpp", db, variants)

    multi = sum(1 for op in range(8192)
                if opcode_count(variants, op) > 1)
    print(f"wrote {out_dir / 'isa_data.hpp'} / isa_data.cpp")
    print(f"  variants: {len(variants)} / {len(db['variants'])} "
          f"(expected 1414)")
    print(f"  enums: {len({r[0] for r in enum_rows(db)})} / "
          f"tables: {len({r[0] for r in field_rows(db)})} / "
          f"pipes: {len({v['pipe'] for v in variants})}")
    print(f"  opcodes with >1 candidate: {multi}")
    return 0


def opcode_count(variants, op):
    return sum(1 for v in variants if v["opcode"] == op)


if __name__ == "__main__":
    sys.exit(main())
