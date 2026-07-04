#!/usr/bin/env python3
"""Extract the sm_90 (Hopper) SASS ISA description into a queryable JSON DB.

Reads:  sm_90_instructions.txt, sm_90_latencies.txt
Writes: sm90.json  (default: repo root)

This captures the "known knowns": header params/constants, modifier enum
value-maps, decode TABLES (incl. illegal-encoding rejection tables), the
FUNIT uC control-bit masks, per-mnemonic functional-unit (pipe) membership,
and every CLASS / ALTERNATE CLASS encoding variant (1588 total).

Stdlib only. See AGENTS.md for the file-format notes this parser relies on.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTR = REPO / "sm_90_instructions.txt"
LAT = REPO / "sm_90_latencies.txt"

# The nine base functional-unit pipes (latency file OPERATION SETS).
BASE_PIPES = [
    "int_pipe", "mio_pipe", "fe_pipe", "fmalighter_pipe", "fp16_pipe",
    "cbu_pipe", "fma64lite_pipe", "fma64heavy_pipe", "udp_pipe",
]
# Ordered longest-first so suffix stripping is greedy-correct.
PIPE_SUFFIXES = sorted(BASE_PIPES, key=len, reverse=True)

ERR_RE = re.compile(r"^[A-Z][A-Z0-9_]*_(ERROR|WARNING|INFO)$")


def read_lines(path):
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def find_line(lines, pred, start=0):
    for i in range(start, len(lines)):
        if pred(lines[i]):
            return i
    return -1


# --------------------------------------------------------------------------
# Header: PARAMETERS / CONSTANTS
# --------------------------------------------------------------------------
def parse_kv_block(lines, start, end):
    out = {}
    kv = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S+)")
    for i in range(start, end):
        m = kv.match(lines[i])
        if not m:
            continue
        key, raw = m.group(1), m.group(2).rstrip(";")
        try:
            out[key] = int(raw, 0)
        except ValueError:
            out[key] = raw
    return out


# --------------------------------------------------------------------------
# Modifier enum value-maps:  Name "str"=num , "str"=num ;
# (multiple defs may share a physical line, separated by ';')
# --------------------------------------------------------------------------
def parse_enums(lines, start, end):
    enums = {}
    def_re = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s+("?.*)$')
    pair_re = re.compile(r'"([^"]*)"\s*(?:=\s*(-?(?:0[bx])?[0-9A-Fa-f_]+))?')
    blob = "\n".join(lines[start:end])
    # split on ';' but keep it simple: statements are ';'-terminated
    for stmt in blob.split(";"):
        stmt = stmt.strip()
        if not stmt or '"' not in stmt:
            continue
        m = def_re.match(stmt.replace("\n", " "))
        if not m:
            continue
        name, body = m.group(1), m.group(2)
        vals = {}
        for pm in pair_re.finditer(body):
            mnem, val = pm.group(1), pm.group(2)
            if val is None:
                vals[mnem] = None
            else:
                try:
                    vals[mnem] = int(val.replace("_", ""), 0)
                except ValueError:
                    vals[mnem] = val
        if vals:
            enums[name] = vals
    return enums


# --------------------------------------------------------------------------
# TABLES_* decode/illegal tables.  Rows are  "<in> <in> ... -> <out>".
# --------------------------------------------------------------------------
def parse_tables(lines, start, end):
    tables = {}
    name = None
    rows = []
    name_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*$")
    def flush():
        nonlocal name, rows
        if name is not None:
            tables[name] = {
                "illegal": name.endswith("_illegal_encodings"),
                "rows": rows,
            }
        name, rows = None, []
    for i in range(start, end):
        line = lines[i].rstrip()
        if not line.strip():
            continue
        if "->" in line:
            lhs, rhs = line.split("->", 1)
            inputs = lhs.split()
            rows.append({"in": inputs, "out": rhs.strip().rstrip(";").strip()})
            continue
        nm = name_re.match(line)
        if nm and nm.group(1) != "TABLES":
            flush()
            name = nm.group(1)
    flush()
    for t in tables.values():
        widths = {len(r["in"]) for r in t["rows"]}
        t["inputs"] = (widths.pop() if len(widths) == 1 else sorted(widths))
    return tables


# --------------------------------------------------------------------------
# FUNIT uC control-bit masks:  Name '<128-char mask>'   (X = set bit, MSB-left)
# --------------------------------------------------------------------------
def mask_to_ranges(mask):
    """Return list of [hi, lo] runs. Leftmost char is the MSB (bit width-1)."""
    w = len(mask)
    idx = [w - 1 - i for i, c in enumerate(mask) if c == "X"]  # bit numbers, desc
    ranges = []
    for b in idx:
        if ranges and ranges[-1][1] - 1 == b:
            ranges[-1][1] = b
        else:
            ranges.append([b, b])
    return ranges


def parse_funit(lines, start, end):
    fields = {}
    fre = re.compile(r"^\s*(\S+)\s+'([.X]+)'\s*$")
    for i in range(start, end):
        m = fre.match(lines[i])
        if not m:
            continue
        name, mask = m.group(1), m.group(2)
        ranges = mask_to_ranges(mask)
        fields[name] = {
            "bits": ranges,
            "width": sum(hi - lo + 1 for hi, lo in ranges),
            "mask_width": len(mask),
        }
    return fields


# --------------------------------------------------------------------------
# Latency file: OPERATION SETS -> per-mnemonic base-pipe membership.
# --------------------------------------------------------------------------
def parse_pipes(lat_lines):
    # join first OPERATION SETS block into statements
    try:
        start = next(i for i, l in enumerate(lat_lines) if l.strip() == "OPERATION SETS")
    except StopIteration:
        return {}
    stmts = []
    buf = ""
    for line in lat_lines[start + 1:]:
        s = line.strip()
        if not s or s[0].isupper() and "=" not in buf and "=" not in s and s.isupper():
            # a bare section header like HARD RESOURCE ends the block
            if s in ("HARD RESOURCE", "CONNECTOR NAMES"):
                break
        buf += " " + line
        if ";" in line:
            stmts.append(buf.strip())
            buf = ""
        if s in ("HARD RESOURCE",):
            break
    pipes = {}
    setdef = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{([^}]*)\}\s*;?")
    for stmt in stmts:
        m = setdef.match(stmt)
        if not m:
            continue
        name, body = m.group(1), m.group(2)
        if name not in BASE_PIPES:
            continue
        for tok in body.split(","):
            tok = tok.strip()
            if not tok:
                continue
            base = strip_pipe_suffix(tok)
            pipes.setdefault(base, set()).add(name)
    return {k: sorted(v) for k, v in pipes.items()}


def strip_pipe_suffix(name):
    for suf in PIPE_SUFFIXES:
        if name.endswith(suf) and name != suf:
            return name[: -len(suf)]
    return name


# --------------------------------------------------------------------------
# CLASS / ALTERNATE CLASS encoding variants
# --------------------------------------------------------------------------
CLASS_RE = re.compile(r'^(ALTERNATE CLASS|CLASS)\s+"([^"]*)"')
BLOCK_RE = re.compile(r'(?:^|[\n;])[ \t]*(ALTERNATE CLASS|CLASS)\s+"([^"]*)"')
HDR_RE = re.compile(
    r"(?:^|[\n;])[ \t]*(FORMAT|CONDITIONS|PROPERTIES|PREDICATES|OPCODES|ENCODING)(?=\W|$)"
)
SUBSECTIONS = ["FORMAT", "CONDITIONS", "PROPERTIES", "PREDICATES", "OPCODES", "ENCODING"]

SLOT_RE = re.compile(
    r"(/)?"                              # modifier marker
    r"([A-Za-z_][A-Za-z0-9_]*)"          # Type
    r"(?:\(([^)]*)\))?"                  # (default)
    r"\*?"                               # optional *
    r":([A-Za-z_][A-Za-z0-9_.]*)"        # :name
)


def split_blocks(lines, start):
    text = "\n".join(lines[start:])
    matches = list(BLOCK_RE.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append({
            "kind": m.group(1), "name": m.group(2),
            "text": text[m.end():end],
        })
    return blocks


def carve_subsections(text):
    marks = []
    for m in HDR_RE.finditer(text):
        name = m.group(1)
        if not any(name == n for n, _ in marks):
            marks.append((name, m.end()))
    out = {}
    for i, (name, pos) in enumerate(marks):
        end = len(text)
        if i + 1 < len(marks):
            # next header may start after ';'/newline preceding it; find its keyword start
            nxt = marks[i + 1]
            # locate the actual keyword start before nxt[1]
            end = text.rfind(nxt[0], pos, nxt[1])
            if end < 0:
                end = nxt[1]
        out[name] = text[pos:end]
    return out


def parse_format(text):
    raw = " ".join(text.split()).strip()
    slots = []
    seen = set()
    for m in SLOT_RE.finditer(raw):
        modifier, typ, default, name = m.groups()
        if name in seen:
            continue
        seen.add(name)
        if default is not None:
            default = default.strip().strip('"')
        slots.append({
            "name": name, "type": typ, "default": default,
            "modifier": bool(modifier),
        })
    return {"raw": raw, "slots": slots}


def parse_conditions(text):
    sec = text.splitlines()
    conds = []
    i, n = 0, len(sec)
    while i < n:
        head = sec[i].strip()
        if ERR_RE.match(head):
            error = head
            i += 1
            pred_parts, message = [], None
            while i < n:
                s = sec[i].strip()
                if s.startswith('"'):
                    message = s.strip().strip('"')
                    i += 1
                    break
                if ERR_RE.match(s):
                    break
                pred_parts.append(s)
                i += 1
            predicate = " ".join(pred_parts).strip()
            if predicate.endswith(":"):
                predicate = predicate[:-1].strip()
            conds.append({"error": error, "predicate": predicate, "message": message})
        else:
            i += 1
    return conds


def parse_kv_section(text):
    out = {}
    for s in text.split(";"):
        s = s.strip()
        if "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_opcodes(text):
    entries = []
    ore = re.compile(r"([A-Za-z0-9_.]+)\s*=\s*0b([01]+)\s*;")
    for m in ore.finditer(text):
        entries.append((m.group(1), int(m.group(2), 2), m.group(2)))
    mnemonic, pipe_suffix, opcode, opcode_bin = None, None, None, None
    for name, val, bits in entries:
        opcode, opcode_bin = val, bits
        base = strip_pipe_suffix(name)
        if base == name:
            mnemonic = name
        else:
            pipe_suffix = name[len(base):]
            if mnemonic is None:
                mnemonic = base
    return {
        "mnemonic": mnemonic, "pipe_suffix": pipe_suffix,
        "opcode": opcode, "opcode_bin": opcode_bin,
        "raw": [{"name": n, "opcode": v} for n, v, _ in entries],
    }


BITS_RE = re.compile(r"^BITS_(\d+(?:_\d+)*)_([A-Za-z_][A-Za-z0-9_.]*)$")


def parse_bits_token(tok, warnings, ctx):
    """BITS_<width>_<hi>_<lo>[_<hi2>_<lo2>...]_<name> -> (name, targets, width)."""
    assert tok.startswith("BITS_")
    rest = tok[len("BITS_"):]
    parts = rest.split("_")
    width = int(parts[0])
    targets = []
    acc = 0
    i = 1
    while i + 1 < len(parts) and parts[i].isdigit() and parts[i + 1].isdigit() and acc < width:
        hi, lo = int(parts[i]), int(parts[i + 1])
        if hi < lo or hi > 127:
            break
        targets.append([hi, lo])
        acc += hi - lo + 1
        i += 2
    name = "_".join(parts[i:])
    if acc != width:
        warnings.append(f"{ctx}: width {width} != span {acc} in {tok}")
    return name, targets, width


def classify_rhs(rhs):
    r = rhs.strip()
    if r == "Opcode":
        return "opcode"
    if r.startswith("*"):
        return "star_num" if r[1:2].isdigit() else "star_slot"
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(", r)
    if m:
        return "table_fn" if m.group(1).startswith("TABLES_") else "other_fn"
    if "@" in r:
        return "slot_attr"
    if re.fullmatch(r"-?\d+", r):
        return "num"
    return "slot"


def parse_encoding(text, warnings, ctx):
    fields = []
    unused = None
    remap = None
    for s in text.split(";"):
        s = s.strip()
        if not s:
            continue
        if s.startswith("!"):
            unused = s[1:].strip()
            continue
        if s.startswith("REMAP"):
            remap = s
            continue
        if "=" not in s:
            continue
        lhs, rhs = s.split("=", 1)
        rhs = rhs.strip()
        kind = classify_rhs(rhs)
        targets_all = []
        names = []
        widths = []
        ok = True
        for tgt in lhs.split(","):
            tgt = tgt.strip()
            if not tgt.startswith("BITS_"):
                ok = False
                break
            name, targets, width = parse_bits_token(tgt, warnings, ctx)
            names.append(name)
            widths.append(width)
            targets_all.append(targets)
        if not ok:
            warnings.append(f"{ctx}: unparsed encoding line: {s}")
            continue
        for name, targets, width in zip(names, targets_all, widths):
            fields.append({
                "name": name, "targets": targets, "width": width,
                "rhs": rhs, "rhs_kind": kind,
                "shared": len(names) > 1,
            })
    return fields, unused, remap


def parse_variants(lines, start):
    blocks = split_blocks(lines, start)
    variants = []
    warnings = []
    parent = None
    for b in blocks:
        is_alt = b["kind"] == "ALTERNATE CLASS"
        if not is_alt:
            parent = None
        sub = carve_subsections(b["text"])
        ctx = b["name"]
        rec = {
            "class": b["name"],
            "is_alternate": is_alt,
            "parent": parent,
        }
        rec["format"] = parse_format(sub.get("FORMAT", ""))
        rec["conditions"] = parse_conditions(sub.get("CONDITIONS", ""))
        rec["properties"] = parse_kv_section(sub.get("PROPERTIES", ""))
        rec["predicates"] = parse_kv_section(sub.get("PREDICATES", ""))
        op = parse_opcodes(sub.get("OPCODES", ""))
        rec.update({
            "mnemonic": op["mnemonic"],
            "pipe_suffix": op["pipe_suffix"],
            "opcode": op["opcode"],
            "opcode_bin": op["opcode_bin"],
            "opcodes_raw": op["raw"],
        })
        enc, unused, remap = parse_encoding(sub.get("ENCODING", ""), warnings, ctx)
        rec["encoding"] = enc
        rec["unused_marker"] = unused
        rec["remap"] = remap
        variants.append(rec)
        if not is_alt:
            parent = b["name"]
    return variants, warnings


# --------------------------------------------------------------------------
def validate(db):
    v = db["variants"]
    errs, warns = [], list(db.get("_warnings", []))
    n = len(v)
    if n != 1589:
        warns.append(f"expected 1589 variants, got {n}")
    mnems = {x["mnemonic"] for x in v if x["mnemonic"]}
    if len(mnems) != 238:
        warns.append(f"expected 238 mnemonics, got {len(mnems)}")
    for x in v:
        if x.get("remap"):
            continue  # pseudo-instruction: REMAP directive, no bit encoding
        if x["opcode"] is None:
            errs.append(f"{x['class']}: no opcode")
        has_op = any(f["rhs_kind"] == "opcode" for f in x["encoding"])
        if not has_op:
            errs.append(f"{x['class']}: no opcode field in ENCODING")
        for f in x["encoding"]:
            for hi, lo in f["targets"]:
                if not (0 <= lo <= hi <= 127):
                    errs.append(f"{x['class']}.{f['name']}: bad range {hi}:{lo}")
            span = sum(hi - lo + 1 for hi, lo in f["targets"])
            if f["targets"] and span != f["width"]:
                errs.append(f"{x['class']}.{f['name']}: width {f['width']} != span {span}")
    return errs, warns


def main():
    ap = argparse.ArgumentParser(description="Extract sm_90 SASS ISA -> JSON")
    ap.add_argument("-o", "--out", default=str(REPO / "sm90.json"))
    ap.add_argument("--indent", type=int, default=1)
    args = ap.parse_args()

    lines = read_lines(INSTR)
    lat_lines = read_lines(LAT)

    i_params = find_line(lines, lambda l: l.rstrip() == "PARAMETERS")
    i_consts = find_line(lines, lambda l: l.rstrip() == "CONSTANTS")
    i_strmap = find_line(lines, lambda l: l.rstrip() == "STRING_MAP")
    i_regs = find_line(lines, lambda l: l.rstrip() == "REGISTERS")
    i_tables = find_line(lines, lambda l: l.rstrip() == "TABLES")
    i_opprops = find_line(lines, lambda l: l.rstrip() == "OPERATION PROPERTIES")
    i_funit = find_line(lines, lambda l: l.rstrip() == "FUNIT uC")
    i_class = find_line(lines, lambda l: CLASS_RE.match(l) is not None)

    db = {}
    db["meta"] = {
        "source": INSTR.name,
        "arch_header": lines[0].strip(),
        "encoding_width": 128,
        "note": "Header says WORD_SIZE 64 / Volta, but sm_90 instructions are 128-bit.",
    }
    db["parameters"] = parse_kv_block(lines, i_params + 1, i_consts)
    db["constants"] = parse_kv_block(lines, i_consts + 1, i_strmap if i_strmap > 0 else i_regs)
    db["enums"] = parse_enums(lines, i_regs + 1, i_tables)
    db["tables"] = parse_tables(lines, i_tables + 1, i_opprops)
    db["funit_uc"] = parse_funit(lines, i_funit + 1, i_class)
    db["pipes"] = parse_pipes(lat_lines)

    variants, warnings = parse_variants(lines, i_class)
    db["variants"] = variants
    db["_warnings"] = warnings

    errs, warns = validate(db)
    db["meta"]["counts"] = {
        "variants": len(variants),
        "mnemonics": len({x["mnemonic"] for x in variants if x["mnemonic"]}),
        "enums": len(db["enums"]),
        "tables": len(db["tables"]),
        "funit_fields": len(db["funit_uc"]),
        "pipes": len(db["pipes"]),
    }

    out = Path(args.out)
    out.write_text(json.dumps(db, indent=args.indent), encoding="utf-8")

    print(f"wrote {out}  ({out.stat().st_size/1e6:.1f} MB)")
    for k, val in db["meta"]["counts"].items():
        print(f"  {k}: {val}")
    if warns:
        print(f"\n{len(warns)} soft warning(s):")
        for w in warns[:20]:
            print("  ! " + w)
    if errs:
        print(f"\n{len(errs)} HARD error(s):", file=sys.stderr)
        for e in errs[:30]:
            print("  X " + e, file=sys.stderr)
        return 1
    print("\nvalidation OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
