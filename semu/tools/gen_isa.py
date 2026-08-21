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


def cident(name: str) -> str:
    """Mangle a SASS name into a valid, unique C++ enum identifier.

    SASS names may contain '.' (e.g. "UIADD3.64") and start with a digit;
    C++ enumerators cannot.  '.' and any other non-alnum char become '_'
    (colon names are already [A-Za-z0-9_], so this only changes mnemonics);
    a leading digit is prefixed with '_'.  Verified collision-free for the
    sm120 corpus (mnemonics and variant classes read back to distinct ids).
    """
    s = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if s and s[0].isdigit():
        s = "_" + s
    return s


def category_ids(values):
    """Return (sorted_unique, id_map) where id_map[n] = index+1 (1-based; 0
    is reserved for the kUnknown enum value).  Sorted order keeps the enum
    enumerators deterministic and stable across regenerations."""
    uniq = sorted(set(values))
    return uniq, {n: i + 1 for i, n in enumerate(uniq)}


def emit_category_enums(L, kind, uniq, ids):
    """Append one enum class + 1-based enumerator list to the header lines L."""
    L.append(f"enum class {kind} : std::uint16_t {{")
    L.append("    kUnknown = 0,")
    for name in uniq:
        L.append(f"    k{cident(name)} = {ids[name]},")
    L.append("};")
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


# ---------------------------------------------------------------------------
# Condition-predicate -> C++ emitter (compile-time hardening of kConds).
#
# Each legality condition's predicate string is translated here, at generation
# time, into the body of a C++ lambda `bool(const std::int64_t* CS)` where CS
# is a dense array of the decoded slot values indexed by a global, generated
# slot index.  The decoder therefore never tokenizes/parses/evaluates a string
# at runtime -- it calls the precompiled thunk, and %PARAM/$CONST/`Enum@val`
# are baked as integer literals.  DEFINED TABLES_*(...) / bare-table values
# compile to generated integer-tuple membership/value helpers.
#
# The grammar is a strict port of assembler/sass_cond.py (the reference
# evaluator), restricted to the operators that actually appear in the sm120
# corpus (== != <= && || -> ! & << + - %, slots, @attr, enums, params, consts,
# DEFINED tables).  Generation asserts each predicate compiles with all tokens
# consumed, so runtime decode can never hit an "unresolved" predicate (GAP-04
# totality is enforced at build time).
# ---------------------------------------------------------------------------

COND_ATTR_SUFFIX = {"not": "_not", "invert": "_invert",
                    "negate": "_negated", "absolute": "_abs"}


def cond_tokenize(predicate: str):
    toks = []
    i, n = 0, len(predicate)
    while i < n:
        c = predicate[i]
        if c.isspace():
            i += 1
            continue
        if c == "`":
            j = i + 1
            while j < n and (predicate[j].isalnum() or predicate[j] == "_"):
                j += 1
            typ = predicate[i + 1:j]
            if j < n and predicate[j] == "@":
                j += 1
            if j < n and predicate[j] == '"':
                j += 1
                start = j
                while j < n and predicate[j] != '"':
                    j += 1
                val = predicate[start:j]
                if j < n:
                    j += 1
            else:
                start = j
                while j < n and (predicate[j].isalnum() or predicate[j] in "_."):
                    j += 1
                val = predicate[start:j]
            toks.append(("ENUM", f"{typ}@{val}"))
            i = j
            continue
        two = predicate[i:i + 2]
        if two in ("==", "!=", "<=", ">=", "&&", "||", "->", "<<", ">>"):
            toks.append(("OP", two))
            i += 2
            continue
        if c == "%" and i + 1 < n and (predicate[i + 1].isalnum() or predicate[i + 1] == "_"):
            j = i + 1
            while j < n and (predicate[j].isalnum() or predicate[j] == "_"):
                j += 1
            toks.append(("PARAM", predicate[i + 1:j]))
            i = j
            continue
        if c == "$" and i + 1 < n and (predicate[i + 1].isalnum() or predicate[i + 1] == "_"):
            j = i + 1
            while j < n and (predicate[j].isalnum() or predicate[j] == "_"):
                j += 1
            toks.append(("CONST", predicate[i + 1:j]))
            i = j
            continue
        if c in "()+-*%<>!@,&?:":
            toks.append(("OP", c))
            i += 1
            continue
        if c.isdigit() or (c == "-" and i + 1 < n and predicate[i + 1].isdigit()):
            if predicate[i:i + 2].lower() == "0x":
                j = i + 2
                while j < n and predicate[j] in "0123456789abcdefABCDEF":
                    j += 1
            else:
                j = i + 1
                while j < n and predicate[j].isdigit():
                    j += 1
            toks.append(("NUM", predicate[i:j]))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i + 1
            while j < n and (predicate[j].isalnum() or predicate[j] == "_"):
                j += 1
            toks.append(("IDENT", predicate[i:j]))
            i = j
            continue
        raise ValueError(f"unclassifiable char {c!r} in condition {predicate!r}")
    return toks


def cpp_enum_value(db, literal: str) -> int:
    """Resolve `Type@Value or Type@\"Value\" to its integer (matching the
    reference evaluator's _enum, including AInteger-style `_64` aliasing)."""
    etype, _, value = literal.partition("@")
    value = value.strip('"')
    ev = db["enums"].get(etype, {})
    if value in ev:
        return int(ev[value])
    if value.startswith("_") and value[1:] in ev:
        return int(ev[value[1:]])
    if not value.startswith("_") and "_" + value in ev:
        return int(ev["_" + value])
    try:
        return int(value, 0)
    except ValueError:
        return 0


class CondEmitter:
    """Recursive-descent emitter: predicate -> C++ int64 expression over the
    dense cond-slot array `CS` (indexed by `slot_idx[slotkey]`)."""

    def __init__(self, db, slot_idx):
        self.db = db
        self.slot_idx = slot_idx
        self.tables = set(db["tables"].keys())
        self.table_helpers = {}
        self.toks = []
        self.pos = 0

    def emit(self, predicate: str) -> str:
        self.toks = cond_tokenize(predicate)
        self.pos = 0
        expr = self.impl()
        if self.pos != len(self.toks):
            raise ValueError(f"unconsumed tokens in condition {predicate!r}")
        return expr

    def slot_ref(self, key):
        """Emit the C++ reference for a slot key: a local `s_<pos>` bound in
        the merged per-variant lambda from its packed slot array."""
        return f"s_{self.slot_idx[key]}"

    def _peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def _peek2(self):
        return self.toks[self.pos + 1] if self.pos + 1 < len(self.toks) else None

    def _eat_op(self, *ops):
        t = self._peek()
        if t and t[0] == "OP" and t[1] in ops:
            self.pos += 1
            return t[1]
        return None

    def impl(self):
        left = self.or_expr()
        if self._eat_op("?"):
            then_e = self.impl()
            if not self._eat_op(":"):
                raise ValueError("missing ':' in ternary condition")
            els_e = self.impl()
            return f"({left} ? ({then_e}) : ({els_e}))"
        if self._eat_op("->"):
            right = self.or_expr()
            return f"(({left}) ? (({right}) ? 1 : 0) : 1)"  # !left || right
        return left

    def or_expr(self):
        v = self.and_expr()
        while self._eat_op("||"):
            r = self.and_expr()
            v = f"(({v}) || ({r}) ? 1 : 0)"
        return v

    def and_expr(self):
        v = self.bitand()
        while self._eat_op("&&"):
            r = self.bitand()
            v = f"(({v}) && ({r}) ? 1 : 0)"
        return v

    def bitand(self):
        v = self.cmp()
        while self._eat_op("&"):
            r = self.cmp()
            v = f"(({v}) & ({r}))"
        return v

    def cmp(self):
        left = self.shift()
        t = self._peek()
        if t and t[0] == "OP" and t[1] in ("==", "!=", "<=", ">=", "<", ">"):
            op = t[1]
            self.pos += 1
            right = self.shift()
            return f"(({left}) {op} ({right}) ? 1 : 0)"
        return left

    def shift(self):
        v = self.add()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("<<", ">>"):
                self.pos += 1
                r = self.add()
                op = t[1]
                # guard: avoid UB / match Python exactly within int64 range
                v = f"(({r}) < 0 || ({r}) >= 64 ? 0 : ({v}) {op} ({r}))"
            else:
                return v

    def add(self):
        v = self.mul()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("+", "-"):
                self.pos += 1
                r = self.mul()
                v = f"(({v}) + ({r}))" if t[1] == "+" else f"(({v}) - ({r}))"
            else:
                return v

    def mul(self):
        v = self.unary()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("%", "*", "/"):
                self.pos += 1
                r = self.unary()
                if t[1] == "%":
                    v = f"(({r}) ? (({v}) % ({r})) : 0)"
                elif t[1] == "*":
                    v = f"(({v}) * ({r}))"
                else:
                    v = f"(({r}) ? (({v}) / ({r})) : 0)"
            else:
                return v

    def unary(self):
        t = self._peek()
        if t and t[0] == "OP" and t[1] == "!":
            self.pos += 1
            return f"(({self.unary()}) ? 0 : 1)"
        if t and t[0] == "OP" and t[1] == "-":
            self.pos += 1
            return f"(-({self.unary()}))"
        if t and t[0] == "OP" and t[1] == "(":
            self.pos += 1
            v = self.impl()
            self._eat_op(")")
            return f"({v})"
        return self.atom()

    def atom(self):
        t = self._peek()
        if not t:
            return "0"
        k, v = t
        if k == "IDENT" and v == "DEFINED":
            return self.defined()
        nxt = self._peek2()
        if k == "IDENT" and nxt and nxt[0] == "OP" and nxt[1] == "@":
            self.pos += 2
            attr = self._peek()
            self.pos += 1
            base = v
            suffix = COND_ATTR_SUFFIX.get(attr[1] if attr else "", attr[1] if attr else "")
            key = base + suffix
            # `X@attr` is a 0/1 predicate flag: normalize the (possibly
            # multi-bit) slot value to 0/1, matching slot_attr's `val ? 1 : 0`.
            return f"(({self.slot_ref(key)}) ? 1 : 0)"
        if k == "IDENT":
            self.pos += 1
            nxt2 = self._peek()
            if nxt2 and nxt2[0] == "OP" and nxt2[1] == "(" and v in self.tables:
                return self.table_value(v)
            return self.slot_ref(v)
        if k == "PARAM":
            self.pos += 1
            return str(int(self.db["parameters"].get(v, 0)))
        if k == "CONST":
            self.pos += 1
            return str(int(self.db["constants"].get(v, 0)))
        if k == "ENUM":
            self.pos += 1
            return str(cpp_enum_value(self.db, v))
        if k == "NUM":
            self.pos += 1
            return str(int(v, 0))
        self.pos += 1
        return "0"

    def resolve_arg(self):
        t = self._peek()
        if not t:
            return "0"
        k, v = t
        if k in ("PARAM", "CONST", "ENUM", "NUM", "IDENT"):
            return self.atom()
        self.pos += 1
        return "0"

    def parse_table_args(self):
        self._eat_op("(")
        args = []
        while True:
            args.append(self.resolve_arg())
            if not self._eat_op(","):
                break
        self._eat_op(")")
        return args

    def defined(self):
        self.pos += 1  # DEFINED
        name_t = self._peek()
        self.pos += 1
        if not name_t or name_t[0] != "IDENT":
            return "0"
        table_name = name_t[1]
        args = self.parse_table_args()
        self.remember_table(table_name, len(args))
        return f"tbl_defined_{table_name}({', '.join(args)})"

    def table_value(self, table_name):
        args = self.parse_table_args()
        self.remember_table(table_name, len(args))
        return f"tbl_value_{table_name}({', '.join(args)})"

    def remember_table(self, table_name, argc):
        self.table_helpers.setdefault(table_name, argc)


def variant_cond_slots(conds, tables):
    """Ordered (first-appearance) list of slot keys referenced by one variant's
    conditions: bare base slots + @attr-suffixed keys (e.g. `Sb@negate` ->
    "Sb_negated").  Table names / DEFINED are excluded (not slot reads)."""
    slots = []
    seen = set()
    for c in conds:
        toks = cond_tokenize(c["predicate"])
        i = 0
        while i < len(toks):
            k, val = toks[i]
            if k == "IDENT":
                if val == "DEFINED" or val in tables:
                    i += 1
                    continue
                if i + 1 < len(toks) and toks[i + 1][0] == "OP" and \
                        toks[i + 1][1] == "@":
                    attr = toks[i + 2][1] if i + 2 < len(toks) else ""
                    key = val + COND_ATTR_SUFFIX.get(attr, attr)
                    if key not in seen:
                        seen.add(key)
                        slots.append(key)
                    i += 3
                    continue
                if val not in seen:
                    seen.add(val)
                    slots.append(val)
            i += 1
    return slots


def emit_table_helpers(db, table_helpers):
    """Generate the shared table membership/value helpers (deduped by table
    name; the integer tuples are baked at generation time)."""
    helper_lines = []
    for tname in sorted(table_helpers):
        argc = table_helpers[tname]
        t = db["tables"][tname]
        rows = t["rows"]
        ins = []
        outs = []
        for row in rows:
            ins.append([int(str(a), 0) for a in row["in"]])
            try:
                outs.append(int(str(row["out"]), 0))
            except ValueError:
                outs.append(0)
        if argc < 1:
            raise ValueError(
                f"condition table {tname} has unsupported arg width {argc}")
        params = ", ".join(f"std::int64_t a{i}" for i in range(argc))
        eq = f" && ".join(f"r[{i}] == a{i}" for i in range(argc))
        rows_def = [f"{{{', '.join(str(ins[i][j]) for j in range(argc))}}}"
                    for i in range(len(ins))]
        helper_lines.append(
            f"[[maybe_unused]] inline bool tbl_defined_{tname}({params}) {{"
            f"  static const std::int64_t k[][{argc}] = "
            f"{{{', '.join(rows_def)}}};"
            f"  for (auto& r : k) if ({eq}) return true;"
            f"  return false;"
            f"}}")
        rows_val = [
            "{" + ", ".join(str(ins[i][j]) for j in range(argc)) +
            f", {outs[i]}" + "}" for i in range(len(ins))]
        helper_lines.append(
            f"[[maybe_unused]] inline std::int64_t tbl_value_{tname}"
            f"({params}) {{"
            f"  static const std::int64_t k[][{argc + 1}] = "
            f"{{{', '.join(rows_val)}}};"
            f"  for (auto& r : k) if ({eq}) return r[{argc}];"
            f"  return 0;"
            f"}}")
    return helper_lines


def compile_variant_conds(db, variants):
    """Compile legality conditions into ONE merged lambda per variant (no
    cross-variant dedup; L1i-friendly single call per CLASS).  Returns
    (var_meta, shared_table_helper_lines, max_cond_slots) where var_meta[i] is
    None (no conditions) or
        {slot_names: [...], pairs: [(cpp_expr, error, message), ...]}.
    The lambda's slots read `s_<pos>` locals bound from `slots[<pos>]`."""
    tables = set(db["tables"].keys())
    em = CondEmitter(db, {})
    var_meta = []
    max_cond_slots = 0
    for v in variants:
        conds = v["conds"]
        if not conds:
            var_meta.append(None)
            continue
        slots = variant_cond_slots(conds, tables)
        max_cond_slots = max(max_cond_slots, len(slots))
        em.slot_idx = {s: i for i, s in enumerate(slots)}
        pairs = []
        for c in conds:
            expr = em.emit(c["predicate"])
            pairs.append((expr, c["error"], c["message"]))
        var_meta.append({"slot_names": slots, "pairs": pairs})
    return var_meta, emit_table_helpers(db, em.table_helpers), max_cond_slots


def emit_hpp(out: Path, mnemonics, classes, pipes,
              mnemonic_id, class_id, pipe_id, max_cond_slots) -> None:
    L = [
        "// Generated file -- do not edit.  Regenerate with:",
        "//   python3 semu/tools/gen_isa.py",
        "#pragma once",
        "",
        "#include <cstdint>",
        "#include <optional>",
        "",
        "namespace semu { struct Word128; }  // forward decl (word.hpp)",
        "",
        "namespace semu::isa {",
        "",
        "// Instruction-category enums (1-based; kUnknown=0 reserved).",
        "// DecodedInstruction spans the same enums so execution backends can",
        "// dispatch on cheap integral values instead of strings.",
    ]
    emit_category_enums(L, "Mnemonic", mnemonics, mnemonic_id)
    L.append("")
    emit_category_enums(L, "VariantClass", classes, class_id)
    L.append("")
    emit_category_enums(L, "Pipe", pipes, pipe_id)
    L.append("")
    L += [
        f"inline constexpr std::uint32_t kNumMnemonics = {len(mnemonics)};",
        f"inline constexpr std::uint32_t kNumVariantClasses = {len(classes)};",
        f"inline constexpr std::uint32_t kNumPipes = {len(pipes)};",
        "",
        "// Enum-value -> name tables (index 0 = kUnknown -> \"\").",
        "extern const char* const kMnemonicNames[];",
        "extern const char* const kVariantClassNames[];",
        "extern const char* const kPipeNames[];",
        "",
        "inline const char* mnemonic_name(Mnemonic m) {",
        "    const std::uint32_t i = static_cast<std::uint32_t>(m);",
        "    return i <= kNumMnemonics ? kMnemonicNames[i] : \"\";",
        "}",
        "inline const char* variant_class_name(VariantClass v) {",
        "    const std::uint32_t i = static_cast<std::uint32_t>(v);",
        "    return i <= kNumVariantClasses ? kVariantClassNames[i] : \"\";",
        "}",
        "inline const char* pipe_name(Pipe p) {",
        "    const std::uint32_t i = static_cast<std::uint32_t>(p);",
        "    return i <= kNumPipes ? kPipeNames[i] : \"\";",
        "}",
        "",
        "// Name -> enum lookup (\"\" / unknown -> kUnknown).  Defined in the .cpp.",
        "Mnemonic mnemonic_from_name(const char* name);",
        "VariantClass variant_class_from_name(const char* name);",
        "Pipe pipe_from_name(const char* name);",
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
        "// Per-variant LEGALITY-CHECK RESULT: the first failing condition's",
        "// error type + message, or nullopt when every condition passes.",
        "struct CondResult {",
        "    const char* error_type;",
        "    const char* message;",
        "};",
        "",
        "// Merged per-variant legality check (one lambda per CLASS, L1i-friendly):",
        "// takes the raw instruction word plus THIS variant's own packed",
        "// condition-slot array (length = kVariants[i].ncondslots, keys listed in",
        "// kVariants[i].condslots), and returns the first failing condition's",
        "// CondResult or nullopt.  Compiled from the predicate strings at",
        "// generation time (tools/gen_isa.py): decode never runtime-parses a",
        "// predicate and evaluates all of a variant's conditions in one call.",
        "using CondCheck = std::optional<CondResult> (*)(const semu::Word128&,",
        "                                                const std::int64_t* slots);",
        "",
        "// Legality condition (spec-derived).  `predicate` string kept for",
        "// diagnostics/tests; evaluation happens via the variant's merged CondCheck.",
        "struct Cond {",
        "    const char* error;",
        "    const char* predicate;",
        "    const char* message;",
        "};",
        "",
    ]
    L.append(
        f"inline constexpr std::uint32_t kMaxCondSlots = {max_cond_slots};")
    L += [

        "// Size/pipe predicate (IDEST_SIZE, ISRC_*_SIZE, VIRTUAL_QUEUE, ...).",
        "struct Pred {",
        "    const char* key;",
        "    const char* value;",
        "};",
        "",
        "struct Variant {",
        "    Mnemonic mnemonic;",
        "    VariantClass variant_class;",
        "    std::uint16_t opcode;",
        "    Pipe pipe;",
        "    std::uint16_t nslots;   const Slot* slots;",
        "    std::uint16_t nfields;  const Field* fields;",
        "    std::uint16_t nconds;   const Cond* conds;",
        "    CondCheck check;                    // merged legality check (nullptr: none)",
        "    std::uint16_t ncondslots;           // packed condition-slot count",
        "    const char* const* condslots;       // this variant's condition slot names",
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
        "extern const char* const kParameters[]; extern const std::int64_t kParameterVals[];",
        "extern const std::uint32_t kNumParameters;",
        "extern const char* const kConstants[]; extern const std::int64_t kConstantVals[];",
        "extern const std::uint32_t kNumConstants;",
        "",
        "}  // namespace semu::isa",
        "",
    ]
    out.write_text("\n".join(L), encoding="utf-8")


def emit_cpp(out: Path, db: dict, variants: list,
             mnemonics, classes, pipes, mnemonic_id, class_id, pipe_id,
             var_cond_meta, cond_table_helpers) -> None:
    lines = [
        "// Generated file -- do not edit.  Regenerate with:",
        "//   python3 semu/tools/gen_isa.py",
        "#include \"isa_data.hpp\"",
        "",
        "#include <cstring>",
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

    # ---- mnemonic / variant-class / pipe name tables (enum-value indexed;
    # index 0 = kUnknown -> "") ----
    lines.append("const char* const kMnemonicNames[] = {")
    lines.append('    "",')
    for n in mnemonics:
        lines.append(f"    {cq(n)},")
    lines.append("};")
    lines.append("")
    lines.append("const char* const kVariantClassNames[] = {")
    lines.append('    "",')
    for n in classes:
        lines.append(f"    {cq(n)},")
    lines.append("};")
    lines.append("")
    lines.append("const char* const kPipeNames[] = {")
    lines.append('    "",')
    for n in pipes:
        lines.append(f"    {cq(n)},")
    lines.append("};")
    lines.append("")

    # ---- name -> enum reverse lookups ----
    lines.append("namespace {")
    lines.append("std::int32_t lookup_name(const char* const* names, "
                 "std::uint32_t n, const char* name) {")
    lines.append("    if (!name) return 0;")
    lines.append("    for (std::uint32_t i = 1; i <= n; ++i)")
    lines.append("        if (std::strcmp(names[i], name) == 0) "
                 "return static_cast<std::int32_t>(i);")
    lines.append("    return 0;  // unknown")
    lines.append("}")
    lines.append("}")
    lines.append("")
    lines.append("Mnemonic mnemonic_from_name(const char* name) {")
    lines.append("    return static_cast<Mnemonic>(lookup_name("
                 "kMnemonicNames, kNumMnemonics, name));")
    lines.append("}")
    lines.append("VariantClass variant_class_from_name(const char* name) {")
    lines.append("    return static_cast<VariantClass>(lookup_name("
                 "kVariantClassNames, kNumVariantClasses, name));")
    lines.append("}")
    lines.append("Pipe pipe_from_name(const char* name) {")
    lines.append("    return static_cast<Pipe>(lookup_name("
                 "kPipeNames, kNumPipes, name));")
    lines.append("}")
    lines.append("")

    # ---- parameters / constants ----
    pkeys = sorted(db["parameters"])
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
    # shared condition-table membership/value helpers (integer tuples,
    # deduped by table name)
    for h in cond_table_helpers:
        lines.append(h)
    # per-variant merged legality checks (one lambda per CLASS; no dedup) and
    # their per-variant packed condition-slot name arrays
    for i, meta in enumerate(var_cond_meta):
        if meta is None:
            continue
        lines.append("")
        lines.append(f"static const char* const kVarCondSlots_{i}[] = {{")
        for s in meta["slot_names"]:
            lines.append(f"    {cq(s)},")
        lines.append("};")
        lines.append("")
        lines.append(f"static std::optional<CondResult> cond_check_{i}("
                     f"const semu::Word128& w, const std::int64_t* slots) {{")
        lines.append("    (void)w;")
        # bind locals s_<pos> = slots[<pos>]
        for pos in range(len(meta["slot_names"])):
            lines.append(f"    const std::int64_t s_{pos} = slots[{pos}];")
        for expr, err, msg in meta["pairs"]:
            lines.append(f"    if (!(({expr}) != 0))")
            lines.append(f"        return CondResult{{{cq(err)}, {cq(msg)}}};")
        lines.append("    return std::nullopt;")
        lines.append("}")
    lines.append("")
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

    # cond structs (spec data; no eval pointer -- legality is evaluated via the
    # per-variant merged cond_check_<i> thunks)
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
    for i, v in enumerate(variants):
        nf = len(v["fields"])
        ns = len(v["slots"])
        nc = len(v["conds"])
        np_ = len(v["preds"])
        meta = var_cond_meta[i]
        if meta is not None:
            chk = f"&cond_check_{i}"
            ncslots = len(meta["slot_names"])
            cslots = f"kVarCondSlots_{i}"
        else:
            chk = "nullptr"
            ncslots = 0
            cslots = "nullptr"
        lines.append(
            f"    {{static_cast<Mnemonic>({mnemonic_id[v['mnemonic']]}), "
            f"static_cast<VariantClass>({class_id[v['class']]}), "
            f"{v['opcode']}, static_cast<Pipe>({pipe_id[v['pipe']]}), "
            f"{ns}, &kSlots[{soff}], {nf}, "
            f"&kFields[{foff}], {nc}, &kConds[{coff}], {chk}, "
            f"{ncslots}, {cslots}, {np_}, "
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


_CPP_KEYWORDS = set("""alignas alignof and and_eq asm auto bitand bitor bool break case catch char
char8_t char16_t char32_t class compl concept const consteval constexpr constinit const_cast
continue co_await co_return co_yield decltype default delete do double dynamic_cast else enum
explicit export extern false float for friend goto if inline int long mutable namespace new
noexcept not not_eq nullptr operator or or_eq private protected public register reinterpret_cast
requires return short signed sizeof static static_assert static_cast struct switch template this
thread_local throw true try typedef typeid typename union unsigned using virtual void volatile
wchar_t while xor xor_eq""".split())

SCHED = {"req", "req_bit_set", "usched_info", "batch_t", "pm_pred",
         "reuse_src_a", "reuse_src_b", "reuse_src_c", "reuse_src_d",
         "rd", "wr", "src_rel_sb", "dst_wr_sb"}

OPERAND_KIND = {
    "Register": "kRegister", "NonZeroRegister": "kRegister",
    "ZeroRegister": "kRegister",
    "UniformRegister": "kUniformRegister",
    "NonZeroUniformRegister": "kUniformRegister",
    "ZeroUniformRegister": "kUniformRegister",
    "Predicate": "kPredicate", "UniformPredicate": "kUniformPredicate",
    "SImm": "kSImm", "RSImm": "kSImm",
    "UImm": "kUImm",
    "F32Imm": "kFImm32", "F64Imm": "kFImm64", "F16Imm": "kFImm16",
    "DESC": "kDesc", "TMA": "kDesc",
}


def shape_operand_roles(v):
    """Positional (display-order) operand roles for a variant: distinct
    non-modifier, non-schedule, non-Pg FORMAT slot names, first appearance."""
    roles = []
    seen = set()
    for s in v["slots"]:
        n = s["name"]
        if n == "Pg" or n in SCHED or s["modifier"]:
            continue
        if n in seen:
            continue
        seen.add(n)
        roles.append(s)
    return roles


def shape_modifier_slots(v):
    return [s for s in v["slots"] if s["modifier"] and s["name"] not in SCHED]


# ---------------------------------------------------------------------------
# Polyvalent-group splitting (arch-specific injection).
#
# The (mnemonic, nops) groups listed in shapes_poly_config.py reuse one
# ops[] position for operands of different meaning across their variants
# (see docs/ops-array-polyvalence.md).  For those groups the generator emits
# one `Decoded<Mnemonic><Nops>_<k>` struct PER KIND-COLLAPSED ROLE
# SIGNATURE: the variant role order with kind-only slots collapsed
# ({Rb,Sb,URb} etc. share one key), so every split struct is
# position-unambiguous.  Automatic detection is deliberately NOT used -- the
# list is curated per arch and injected at generation time.
# ---------------------------------------------------------------------------

# Kind-collapse: FORMAT slot names that are the SAME operand role differing
# only in kind (register / uniform register / immediate).  Two slots in one
# collapse family are never semantically distinct; slots NOT listed keep
# their own key and therefore force a split.
KIND_COLLAPSE = {
    "Rb": "b", "Sb": "b", "URb": "b",
    "Rc": "c", "Sc": "c", "URc": "c",
    "Ra": "a", "URa": "a",
    "Ra_offset": "off", "Sa_offset": "off", "URa_offset": "off",
    "Rb2": "b2", "Sc2": "c2",
}


def load_poly_groups():
    """Arch-specific polyvalent (mnemonic, nops) group set.  Missing config
    or import failure degrades to an empty set (no splits)."""
    try:
        from shapes_poly_config import POLY_GROUPS
        return set(POLY_GROUPS)
    except Exception:
        return set()


def split_signature(roles):
    """Kind-collapsed role signature of a variant (tuple of canonical keys)."""
    return tuple(KIND_COLLAPSE.get(r["name"], r["name"]) for r in roles)


def shape_type_name(key):
    """Decoded<Mnemonic><Nops>[_k] for a (mn, nops[, split]) group key."""
    name = f"Decoded{cident(key[0])}{key[1]}"
    if len(key) > 2:
        name += f"_{key[2]}"
    return name


def build_shape_groups(variants):
    """Group variants into decoded-struct groups.  Keys are (mnemonic,
    operand-count) normally, or (mnemonic, operand-count, split-k) for the
    polyvalent groups declared in shapes_poly_config.py (split by
    kind-collapsed role signature, k = sorted-signature index).  Returns
    (groups, order, vid2gid, variant_split) where groups[key] =
    [(variant_idx, v, roles)...], order = keys in first-appearance order,
    vid2gid[variant_idx] = group index, variant_split[variant_idx] = split
    ordinal or -1 (no split)."""
    from collections import OrderedDict
    poly = load_poly_groups()
    raw = OrderedDict()
    for i, v in enumerate(variants):
        roles = shape_operand_roles(v)
        key = (v["mnemonic"], len(roles))
        raw.setdefault(key, []).append((i, v, roles))
    groups = OrderedDict()
    order = []
    vi_key = {}  # variant idx -> group key
    for key, members in raw.items():
        if key in poly:
            # split by kind-collapsed signature; k = sorted-signature index
            # (deterministic across regenerations).
            subs = OrderedDict()
            for m in members:
                sg = split_signature(m[2])
                subs.setdefault(sg, []).append(m)
            for k, (_sg, sub) in enumerate(sorted(subs.items())):
                gkey = (key[0], key[1], k)
                groups[gkey] = sub
                order.append(gkey)
                for m in sub:
                    vi_key[m[0]] = gkey
        else:
            groups[key] = members
            order.append(key)
            for m in members:
                vi_key[m[0]] = key
    gid = {k: n for n, k in enumerate(order)}
    vid2gid = [gid[vi_key[i]] for i in range(len(variants))]
    variant_split = [k[2] if len(k) > 2 else -1 for k in
                     (vi_key[i] for i in range(len(variants)))]
    return groups, order, vid2gid, variant_split


def shape_members(group_members, enum_types):
    """Union of typed modifier members across a group's variants.  Returns an
    OrderedDict member_name -> (type_cident_or_'std::uint8_t', source_slot_name),
    with the same collision handling as the type declaration (SAT_/private_)."""
    from collections import OrderedDict
    out = OrderedDict()
    for _i, v, _roles in group_members:
        for s in shape_modifier_slots(v):
            ty = s["type"]
            tyid = cident(ty) if ty in enum_types else "std::uint8_t"
            mn = cident(s["name"])
            if mn == tyid or mn in _CPP_KEYWORDS:
                mn += "_"
            if mn in out:
                continue
            out[mn] = (tyid, s["name"])
    return out


def emit_shapes_hpp(out: Path, db: dict, variants: list) -> None:
    """Emit isa_shapes.hpp: the typed decoded-IR schema (design review + later
    migration).  Pure addition -- does NOT replace the existing DecodedInstruction.
    Groups decoded types by (mnemonic, operand-count); operands are a positional
    union array; modifiers are reusable enums as typed members."""
    L = []
    L.append("// Generated file -- do not edit.  Regenerate with:")
    L.append("//   python3 semu/tools/gen_isa.py --shapes")
    L.append("//")
    L.append("// Typed decoded-IR schema used by the decoder's main storage path.")
    L.append("#pragma once")
    L.append("")
    L.append("#include <cstdint>")
    L.append("#include <cstring>")
    L.append("#include <optional>")
    L.append("#include <memory>")
    L.append("#include <semu/decoded_base.hpp>")
    L.append("#ifdef NAN")
    L.append("#undef NAN")
    L.append("#endif")
    L.append("")
    L.append("namespace semu::shape {")

    # ---- OperandKind + OperandValue ----
    L.append("")
    L.append("enum class OperandKind : std::uint8_t {")
    for k in ("kRegister", "kUniformRegister", "kPredicate",
              "kUniformPredicate", "kSImm", "kUImm", "kFImm16", "kFImm32",
              "kFImm64", "kDesc", "kSpecial"):
        L.append(f"    {k},")
    L.append("};")
    L.append("")
    L.append("struct OperandValue {")
    L.append("    std::uint8_t kind;   // OperandKind")
    L.append("    std::uint8_t flags;  // bit0 negate, bit1 absolute, bit2 pred_not")
    L.append("    union {")
    L.append("        std::uint64_t uimm64;  std::int64_t simm64;")
    L.append("        std::uint32_t uimm32;  std::int32_t simm32;")
    L.append("        float fimm32;          double dimm64;")
    L.append("        std::uint16_t uimm16;  std::uint8_t uimm8;")
    L.append("        std::int16_t simm16;   std::int8_t simm8;")
    L.append("        std::int32_t reg_idx;  std::int32_t ureg_idx;")
    L.append("        std::uint8_t pred_idx; std::uint64_t desc;")
    L.append("    } v;")
    L.append("};")  # == 0 if C++ reserves padding

    # ---- reusable modifier enums (deduped by modifier FORMAT type).  A type
    # whose enum has no int-valued entries (e.g. ABSONLY) yields no enum; the
    # corresponding struct member degrades to std::uint8_t.
    modtypes = set()
    for v in variants:
        for s in shape_modifier_slots(v):
            modtypes.add(s["type"])
    enum_types = {t for t in modtypes
                  if any(v is not None for v in db["enums"].get(t, {}).values())}
    L.append("")
    L.append("// Reusable modifier enums (one per modifier FORMAT type).")
    for t in sorted(enum_types):
        enum = db["enums"][t]
        entries = [(str(n), enum[n]) for n in enum if enum[n] is not None]
        L.append(f"enum class {cident(t)} : std::int32_t {{")
        used = set()
        for name, val in sorted(entries, key=lambda x: (str(x[1]), x[0])):
            mid = f"k{cident(str(name))}"
            if mid in used:
                continue
            used.add(mid)
            L.append(f"    {mid} = {int(val)},")
        L.append("};")

    # ---- group variants by (mnemonic, operand-count) ----
    groups, order, vid2gid, variant_split = build_shape_groups(variants)

    L.append("")
    L.append("// Derived decoded types: one per (mnemonic, operand-count); the")
    L.append("// polyvalent groups declared in shapes_poly_config.py emit one")
    L.append("// Decoded<Mnemonic><N>_<k> per kind-collapsed role signature, so")
    L.append("// every struct's ops[] positions are unambiguous.  Operands are")
    L.append("// positional in the mnemonic's canonical role order; modifiers")
    L.append("// are typed enum members specific to each instruction.")
    for key in order:
        members = groups[key]
        type_name = shape_type_name(key)
        operand_count = key[1]
        L.append(f"struct {type_name} : DecodedInstruction {{")
        L.append("    std::unique_ptr<DecodedInstruction> clone() const override {")
        L.append(f"        return std::make_unique<{type_name}>(*this);")
        L.append("    }")
        if operand_count:
            L.append(f"    OperandValue ops[{operand_count}];")
        modseen = shape_members(members, enum_types)
        for mname, (tyid, _src) in modseen.items():
            L.append(f"    {tyid} {mname};")
        # 2b-3 plan-b: subclass flags set at fill time from the variant CLASS
        # name (X/wide/hi/imm64/fp traits), so the interpreter can dispatch
        # without string or slot-id lookups.
        L.append("    std::uint8_t subclass;  // generated semantic flags")
        if key[0] == "BAR":
            # The barrier-id encoding (barname field) is not a FORMAT slot;
            # expose it as a typed member for do_bar.
            L.append("    std::uint8_t barname;  // unsurfaced barrier-id field")
        L.append("};")

    # Per-variant split ordinal (-1 = single struct).  The interpreter uses
    # this to pick the concrete split type of a decoded instruction.
    L.append("")
    L.append("// kShapeSplitByVariant[vi]: split ordinal of the variant's decoded")
    L.append("// struct within its (mnemonic, nops) group; -1 = no split.")
    L.append("inline constexpr std::int8_t kShapeSplitByVariant[] = {")
    L.append("    " + ", ".join(str(s) for s in variant_split))
    L.append("};")

    # ---- per-variant operand-role manifest (aligned to kVariants index) ----
    # Each operand slot of a variant -> (position in ops[], OperandKind).  This
    # is what decode uses to fill a derived Decoded* ops[] positionally from the
    # decoded slot map.
    L.append("")
    L.append("// Per-variant operand-role manifest (indexed by isa_data kVariants")
    L.append("// index).  pos = position in the derived type's ops[] array.")
    L.append("struct ShapeOpRole {")
    L.append("    const char* slot;   // FORMAT slot name (e.g. \"Rd\", \"Rb\")")
    L.append("    std::uint8_t pos;   // position in ops[]")
    L.append("    OperandKind kind;   // OperandKind")
    L.append("};")
    L.append("static_assert(sizeof(ShapeOpRole) <= 16);")
    L.append("static_assert(sizeof(OperandValue) <= 16);")
    L.append("struct ShapeManifest {")
    L.append("    std::uint16_t n_ops;             // number of operand roles")
    L.append("    const ShapeOpRole* ops;          // role list, or nullptr")
    L.append("};")  # == n_ops or pointer padding
    roles_arrays = []
    manifests = []
    for i, v in enumerate(variants):
        roles = shape_operand_roles(v)
        if not roles:
            manifests.append("    {0, nullptr},")
            continue
        arr_name = f"kShapeRoles_{i}"
        roles_arrays.append((arr_name, roles))
        manifests.append(f"    {{{len(roles)}, {arr_name}}},")
    for arr_name, roles in roles_arrays:
        rows = ", ".join(
            f"{{ {cq(r['name'])}, {k}, "
            f"OperandKind::{OPERAND_KIND.get(r['type'], 'kSpecial')} }}"
            for k, r in enumerate(roles))
        L.append(f"inline const ShapeOpRole {arr_name}[] = {{ {rows} }};")
    L.append("")
    L.append("inline const ShapeManifest kShapeManifests[] = {")
    L.extend(manifests)
    L.append("};")
    L.append("")
    L.append("}  // namespace semu::shape")
    L.append("")
    out.write_text("\n".join(L), encoding="utf-8")


# Semantic subclass bits injected into the typed Decoded* at fill time (2b-3
# plan b): variants whose CLASS name carries a dispatch-relevant trait that has
# no FORMAT-slot/typed-member representation get a compile-time-set flag.  The
# interpreter reads `inst.subclass & <bit>` -- no string/int lookup.
_lookup_subclass = {
    "_x": 1,
    "wide": 2,
    "hi": 4,
    "imm64": 8,
    "_fp": 16,
}


def variant_subclass(cls: str) -> int:
    bits = 0
    for key, bit in _lookup_subclass.items():
        if key in cls:
            bits |= bit
    return bits


def emit_shapes_fill(out: Path, db: dict, variants: list) -> None:
    """Emit isa_shapes_fill.hpp: per-variant fillers that populate a typed
    Decoded<Mnemonic><Ops> (ops[] positional + typed modifier members) from an
    opaque FillIn source.  Dispatch is by isa_data kVariants index; this is 2a's
    equivalence path -- the decoder still uses the generic DecodedInstruction."""
    enum_types = {t for t in
                  (s["type"] for v in variants for s in shape_modifier_slots(v))
                  if any(val is not None for val in
                         db["enums"].get(t, {}).values())}
    groups, order, vid2gid, _split = build_shape_groups(variants)

    L = []
    L.append("// Generated file -- do not edit.  Regenerate with:")
    L.append("//   python3 semu/tools/gen_isa.py --shapes")
    L.append("#pragma once")
    L.append("")
    L.append("#include <cstdint>")
    L.append("#ifdef NAN")
    L.append("#undef NAN")
    L.append("#endif")
    L.append("#include \"isa_shapes.hpp\"")
    L.append("#include <semu/shape_in.hpp>")
    L.append("")
    L.append("namespace semu::shape {")
    L.append("")
    L.append("// Per-group modifier filler (cast void_out to Decoded<Mnemonic><N>).")
    grp_has_mods = {}
    for g, key in enumerate(order):
        members = groups[key]
        modseen = shape_members(members, enum_types)
        grp_has_mods[g] = bool(modseen)
        if not modseen:
            continue
        type_name = shape_type_name(key)
        L.append(f"inline void shape_fill_mods_grp{g}("
                 f"const FillIn& in, void* void_out) {{")
        L.append(f"    auto& out = *static_cast<{type_name}*>(void_out);")
        for mname, (_tyid, src) in modseen.items():
            L.append(f"    out.{mname} = static_cast<{_tyid}>("
                     f"in.value({cq(src)}));")
        L.append("}")
    L.append("")
    L.append("// Fill a typed Decoded* (allocated by the caller) for variant index")
    L.append("// vi (== isa_data kVariants index) from a decoded slot source.")
    L.append("inline void fill_by_variant(std::uint32_t vi, "
             "const FillIn& in, void* void_out) {")
    L.append("    switch (vi) {")
    for vi, v in enumerate(variants):
        g = vid2gid[vi]
        type_name = shape_type_name(order[g])
        roles = shape_operand_roles(v)
        L.append(f"    case {vi}: {{")
        L.append(f"        auto& out = *static_cast<{type_name}*>(void_out);")
        if grp_has_mods[g]:
            L.append(f"        shape_fill_mods_grp{g}(in, void_out);")
        L.append(f"        out.subclass = {variant_subclass(v['class'])};")
        if order[g][0] == "BAR":
            L.append(f"        out.barname = static_cast<std::uint8_t>("
                     f"in.value(\"barname\"));")
        for p, r in enumerate(roles):
            kind = OPERAND_KIND.get(r["type"], "kSpecial")
            L.append(f"        out.ops[{p}].kind = static_cast<std::uint8_t>("
                     f"OperandKind::{kind});")
            L.append(f"        out.ops[{p}].flags = in.flags({cq(r['name'])});")
            L.append(f"        operand_set_value(out.ops[{p}], "
                     f"OperandKind::{kind}, in.value({cq(r['name'])}));")
        L.append("        break;")
        L.append("    }")
    L.append("    }")
    L.append("}")
    L.append("")
    L.append("// Read a typed modifier or operand slot by name.  This is the")
    L.append("// temporary 2b bridge used by the interpreter while call sites")
    L.append("// migrate from the generic vector representation.")
    L.append("inline std::optional<std::uint64_t> slot_value_by_variant(")
    L.append("    std::uint32_t vi, const DecodedInstruction* inst, const char* name) {")
    L.append("    switch (vi) {")
    for vi, v in enumerate(variants):
        g = vid2gid[vi]
        type_name = shape_type_name(order[g])
        roles = shape_operand_roles(v)
        actual_mods = shape_modifier_slots(v)
        modseen = shape_members(groups[order[g]], enum_types)
        member_by_src = {src: mname for mname, (_ty, src) in modseen.items()}
        L.append(f"    case {vi}: {{")
        if roles or actual_mods:
            L.append(f"        const auto& out = *static_cast<const {type_name}*>(inst);")
        for p, r in enumerate(roles):
            L.append(f"        if (std::strcmp(name, {cq(r['name'])}) == 0)")
            L.append(f"            return static_cast<std::uint64_t>(operand_value_as_i64(out.ops[{p}]));")
        for s in actual_mods:
            mname = member_by_src.get(s["name"])
            if mname is None:
                continue
            L.append(f"        if (std::strcmp(name, {cq(s['name'])}) == 0)")
            L.append(f"            return static_cast<std::uint64_t>(out.{mname});")
        L.append("        return std::nullopt;")
        L.append("    }")
    L.append("    default: return std::nullopt;")
    L.append("    }")
    L.append("}")
    L.append("")
    L.append("// Allocate the concrete generated shape for a variant index.")
    L.append("inline std::unique_ptr<DecodedInstruction> make_by_variant(std::uint32_t vi) {")
    L.append("    switch (vi) {")
    for vi, _v in enumerate(variants):
        g = vid2gid[vi]
        type_name = shape_type_name(order[g])
        L.append(f"    case {vi}: return std::make_unique<{type_name}>();")
    L.append("    default: return nullptr;")
    L.append("    }")
    L.append("}")
    L.append("")
    L.append("// Return the positional operand array of a typed decoded shape.")
    L.append("inline const OperandValue* operand_values_by_variant(")
    L.append("    std::uint32_t vi, const DecodedInstruction* inst) {")
    L.append("    switch (vi) {")
    for vi, _v in enumerate(variants):
        g = vid2gid[vi]
        type_name = shape_type_name(order[g])
        if order[g][1]:
            L.append(f"    case {vi}: return static_cast<const {type_name}*>(inst)->ops;")
        else:
            L.append(f"    case {vi}: return nullptr;")
    L.append("    default: return nullptr;")
    L.append("    }")
    L.append("}")
    L.append("")
    L.append("}  // namespace semu::shape")
    L.append("")
    out.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "sm120.json"))
    ap.add_argument("--shapes", action="store_true",
                    help="also emit isa_shapes{,.fill}.hpp (typed-IR schema/2a fill)")
    ap.add_argument("--output-dir", default=str(REPO / "semu" / "generated"))
    args = ap.parse_args()

    db = json.load(open(args.db))
    variants = build_variants(db)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mnemonics, mnemonic_id = category_ids(v["mnemonic"] for v in variants)
    classes, class_id = category_ids(v["class"] for v in variants)
    pipes, pipe_id = category_ids(v["pipe"] for v in variants)
    var_cond_meta, cond_table_helpers, max_cond_slots = \
        compile_variant_conds(db, variants)
    emit_hpp(out_dir / "isa_data.hpp", mnemonics, classes, pipes,
             mnemonic_id, class_id, pipe_id, max_cond_slots)
    emit_cpp(out_dir / "isa_data.cpp", db, variants,
             mnemonics, classes, pipes, mnemonic_id, class_id, pipe_id,
             var_cond_meta, cond_table_helpers)
    if args.shapes:
        emit_shapes_hpp(out_dir / "isa_shapes.hpp", db, variants)
        emit_shapes_fill(out_dir / "isa_shapes_fill.hpp", db, variants)
        print(f"wrote {out_dir / 'isa_shapes.hpp'} + isa_shapes_fill.hpp (schema/2a)")

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
