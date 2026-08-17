#!/usr/bin/env python3
"""Real cuobjdump structured differential test (CTest 'decoder_cuobjdump',
GAP-10).  Compares every real sm120 word's cuobjdump rendering against the
semu decode as a *normalized token structure*, not substring checks:

  - guard predicate (@P0/@!P0/@PT) parsed from both sides;
  - mnemonic base + modifier tokens compared as ordered lists;
  - operand tokens compared pairwise in position with normalizations:
      * register groups: `R2.64` <-> `{R2,R3}`, `UR4` (desc 64-bit) <-> `{UR4,UR5}`
      * immediate case: 0xB <-> 0xb, float forms (<-> 0f...)
      * `.reuse` decorations dropped (non-semantic scheduling hint);
      * branch target immediates compared PC-relative (cuobjdump prints the
        absolute target; semu prints the relative displacement).

Registers are compared bidirectionally per position (both directions must be
present), so an extra or missing register fails the gate.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

BRANCH_SET = {"BRA", "BRX", "BRXU", "BSSY", "BREAK", "BSYNC", "CALL",
              "BRB", "RTT", "JMP", "JMX", "RET"}


def norm_hex(token: str) -> str:
    """lowercase hex immediates; keep float/int forms recognizable."""
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", token):
        return token.lower()
    return token


def float_from_bits(bits: int) -> float:
    import struct
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def norm_float(token: str):
    """Normalize `0fXXXXXXXX` fp32 bit patterns and decimal floats to a
    comparable float value (returned as float), else the token unchanged."""
    m = re.fullmatch(r"0[fF]([0-9a-fA-F]{8})", token)
    if m:
        return float_from_bits(int(m.group(1), 16))
    if re.fullmatch(r"[+-]?INF", token, re.IGNORECASE):
        return float("inf") * (-1 if token.startswith("-") else 1)
    if re.fullmatch(r"[+-]?NAN", token, re.IGNORECASE):
        return float("nan")
    try:
        return float(token)
    except ValueError:
        return token


def expand_regs(token: str) -> list[str]:
    """Expand register-group / .64 forms to a canonical list of register
    names: R2.64 -> [R2,R3]; {R2,R3} -> [R2,R3]; UR4.64 -> [UR4,UR5]."""
    m = re.fullmatch(r"\{([UR]R?\d+(?:,[UR]R?\d+)*)\}", token)
    if m:
        return m.group(1).split(",")
    m = re.fullmatch(r"([UR]R?\d+)\.(64|128)", token)
    if m:
        base = m.group(1)
        n = 2 if m.group(2) == "64" else 4
        prefix = "UR" if base.startswith("UR") else "R"
        num = int(base[len(prefix):])
        return [f"{prefix}{num + k}" for k in range(n)]
    return [token]


def split_ops(rest: str) -> list[str]:
    """Split operand region on commas OUTSIDE brackets/braces (register groups
    and desc/mem operands contain internal commas)."""
    out = []
    depth = 0
    cur = []
    for ch in rest:
        if ch in "[{(":
            depth += 1
        elif ch in "]})":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return [x for x in out if x]


def parse_ops(text: str) -> tuple[str, list[str], list[str], list[str]]:
    """-> (guard, mnemonic_base, modifiers, operand_tokens)."""
    t = text.strip()
    guard = ""
    if t.startswith("@"):
        m = re.match(r"@(!)?(P\d+|PT)\s+", t)
        if m:
            guard = ("!" if m.group(1) else "") + m.group(2)
            t = t[m.end():]
    m = re.match(r"([A-Z0-9][A-Z0-9_.]*)", t)
    if not m:
        return guard, "", [], []
    mnem_full = m.group(1)
    parts = mnem_full.split(".")
    base = parts[0]
    mods = parts[1:]
    rest = t[m.end():].strip()
    ops = split_ops(rest)
    # cuobjdump sometimes space-separates operands (RET.REL.NODEC R8 0x0);
    # split whitespace-separated tokens inside each comma-delimited operand
    expanded = []
    for op in ops:
        if re.fullmatch(r"[UR]R?\d+\s+[0-9a-fA-Fx+-]+", op):
            expanded.extend(op.split())
        else:
            expanded.append(op)
    ops = expanded
    return guard, base, mods, ops


def norm_desc(op: str) -> str:
    """Normalize a desc[...][...] operand: expand scalar registers inside the
    brackets to explicit groups so cuobjdump/semu forms compare equal."""
    m = re.fullmatch(r"desc\[([^\]]*)\]\[([^\]]*)\]", op)
    if not m:
        return op
    ur, addr = m.group(1), m.group(2)

    def expand_reg_tokens(s: str) -> str:
        # R2.64 -> {R2,R3}; UR4 -> {UR4,UR5} when alone (desc UR is 64-bit);
        # {R2,R3} stays as-is.
        out = []
        for tok in re.split(r"([+\-])", s):
            if not tok or tok in "+-":
                out.append(tok)
                continue
            m2 = re.fullmatch(r"([UR]R?\d+)\.(64|128)", tok)
            if m2:
                n = 2 if m2.group(2) == "64" else 4
                out.append("{" + ",".join(
                    expand_scalar_to_group(m2.group(1), n)) + "}")
                continue
            m2 = re.fullmatch(r"([UR]R?\d+)", tok)
            if m2 and tok.startswith("UR"):
                # bare UR in desc position is a 64-bit uniform group
                out.append("{" + ",".join(
                    expand_scalar_to_group(tok, 2)) + "}")
                continue
            out.append(norm_hex(tok))
        return "".join(out)

    ur = expand_reg_tokens(ur)
    addr = expand_reg_tokens(addr)
    return f"desc[{ur}][{addr}]"


def norm_mem(op: str) -> str:
    """Normalize a memory-address operand: cuobjdump prints the scalar
    shorthand and omits an RZ base (`[UR4]` == `[RZ+UR4]`), while semu prints
    explicit groups and RZ.  Expand explicit-width registers (R2.64) and drop
    leading `RZ+`; bare UR is left scalar here and expanded during comparison
    to the other side's group width."""
    inner = op[1:-1]
    inner = re.sub(r"^RZ\+", "", inner)
    parts = re.split(r"([+\-])", inner)
    out = []
    for tok in parts:
        if not tok or tok in "+-":
            out.append(tok)
            continue
        m = re.fullmatch(r"([UR]R?\d+)\.(64|128)", tok)
        if m:
            n = 2 if m.group(2) == "64" else 4
            out.append("{" + ",".join(
                expand_scalar_to_group(m.group(1), n)) + "}")
            continue
        out.append(norm_hex(tok))
    return "[" + "".join(out) + "]"


def normalize_side(guard, base, mods, ops, pc=None):
    """Normalize into a comparable structure."""
    mods = [m for m in mods if m != "reuse"]
    out_ops = []
    for op_raw in ops:
        # strip decorations that are scheduling hints
        op = re.sub(r"\.reuse$", "", op_raw)
        op = re.sub(r"\.H\d_\w+$", "", op)  # half-selector on register
        neg = op.startswith("-")
        abs_ = op.startswith("|") and op.endswith("|")
        op_stripped = op.lstrip("-").strip("|")
        op = norm_hex(op_stripped)
        # float immediates carry their sign inside the value; do not use the
        # neg flag for them (cuobjdump prints -1.5..., semu prints 0fBF...)
        is_float = bool(re.fullmatch(
            r"0[fF][0-9a-fA-F]{8}|[+-]?\d+\.\d+[eE]?[+-]?\d*|[+-]?(INF|NAN|inf|nan)",
            op_stripped))
        if is_float:
            neg = False
        # expand register groups
        regs = expand_regs(op)
        if len(regs) > 1 or regs != [op]:
            out_ops.append(("REG_GROUP", regs, neg, abs_))
            continue
        if re.fullmatch(r"[UR]R?\d+", op):
            out_ops.append(("REG", op, neg, abs_))
        elif re.fullmatch(r"URZ|RZ", op):
            out_ops.append(("REG", op, neg, abs_))
        elif re.fullmatch(r"P\d+|PT|UP\d+|UPT", op):
            out_ops.append(("PRED", op, neg, False))
        elif re.fullmatch(r"c\[0x[0-9a-f]+\]\[[^\]]*\]", op):
            # const operand: normalize URZ offset to 0x0
            out_ops.append(("CONST", op.replace("[URZ]", "[0x0]")
                            .replace("[RZ]", "[0x0]"), False, False))
        elif re.fullmatch(r"desc\[[^\]]*\]\[[^\]]*\]", op):
            out_ops.append(("DESC", norm_desc(op), False, False))
        elif re.fullmatch(r"\[[^\]]*\]", op):
            out_ops.append(("MEM", norm_mem(op), False, False))
        elif re.fullmatch(r"SR_[A-Za-z0-9.]+", op):
            out_ops.append(("SR", op, False, False))
        elif re.fullmatch(r"0x[0-9a-f]+", op):
            val = int(op, 16)
            out_ops.append(("IMM", -val if neg else val, False, False))
        elif re.fullmatch(r"B\d+", op):
            out_ops.append(("BD", op, False, False))
        elif re.fullmatch(r"0[fF][0-9a-fA-F]{8}", op):
            out_ops.append(("FLOAT", norm_float(op), neg, abs_))
        elif re.fullmatch(r"[+-]?\d+\.\d+[eE]?[+-]?\d*|[+-]?(INF|NAN)", op,
                          re.IGNORECASE):
            # use the sign-carrying original token (op had '-' stripped)
            signed = op if op.startswith("-") or op.startswith("+") \
                else op_raw.lstrip("|").strip()
            out_ops.append(("FLOAT", norm_float(signed), neg, abs_))
        elif re.fullmatch(r"[+-]?\d+", op_raw.strip()):
            out_ops.append(("IMM", int(op_raw.strip(), 10), False, False))
        elif re.fullmatch(r"[0-9a-fA-F]+", op):
            # bare hex integer without 0x: semu prints floats as 0f... so a
            # bare hex token here is an integer (matches cuobjdump decimal
            # only when it has no a-f digits; decimal handled above).
            out_ops.append(("IMM", int(op, 16), False, False))
        else:
            # float or mixed token: compare as normalized string
            out_ops.append(("OTHER", op, neg, abs_))
    return {"guard": guard, "base": base, "mods": mods, "ops": out_ops}


def expand_scalar_to_group(token: str, n: int) -> list[str]:
    prefix = "UR" if token.startswith("UR") else "R"
    num = int(token[len(prefix):])
    return [f"{prefix}{num + k}" for k in range(n)]


def ops_equal(a, b) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x[0] != y[0]:
            # scalar-vs-group register equivalence (cuobjdump prints the
            # scalar shorthand `UR4`, semu the explicit group `{UR4,UR5}`)
            if {x[0], y[0]} == {"REG", "REG_GROUP"}:
                scalar = x if x[0] == "REG" else y
                group = y if x[0] == "REG" else x
                gs = set(group[1])
                expanded = set(expand_scalar_to_group(scalar[1], len(gs)))
                if expanded == gs and scalar[2] == group[2] and \
                        scalar[3] == group[3]:
                    continue
                return False
            # MEM containing a single scalar register == bare REG_GROUP
            # (UTMALDG tmem: cuobjdump `[UR8]`, semu `{UR8,UR9,UR10,UR11}`)
            if {x[0], y[0]} == {"MEM", "REG_GROUP"}:
                mem = x if x[0] == "MEM" else y
                grp = y if x[0] == "MEM" else x
                inner = mem[1][1:-1]
                if re.fullmatch(r"[UR]R?\d+", inner):
                    expanded = set(
                        expand_scalar_to_group(inner, len(grp[1])))
                    if expanded == set(grp[1]) and mem[2] == grp[2]:
                        continue
                return False
            # IMM (cuobjdump integer form) == FLOAT (semu 0f... bit pattern)
            # when the float value is integral (e.g. 105615 vs 0f47CE4780)
            if {x[0], y[0]} == {"IMM", "FLOAT"}:
                imm = x if x[0] == "IMM" else y
                flt = y if x[0] == "IMM" else x
                if abs(flt[1] - float(imm[1])) < 1e-6 * max(
                        1.0, abs(flt[1]), float(imm[1])):
                    continue
                return False
            return False
        if x[0] == "REG" or x[0] == "REG_GROUP":
            # bidirectional register set equality
            xs = set(x[1]) if x[0] == "REG_GROUP" else {x[1]}
            ys = set(y[1]) if y[0] == "REG_GROUP" else {y[1]}
            if xs != ys or x[2] != y[2] or x[3] != y[3]:
                return False
        elif x[0] == "IMM":
            if x[1] != y[1] or x[2] != y[2]:
                return False
        elif x[0] == "FLOAT":
            if abs(x[1] - y[1]) > 1e-9 * max(1.0, abs(x[1]), abs(y[1])) \
                    or x[2] != y[2]:
                return False
        else:
            if x[1] != y[1] or x[2] != y[2] or x[3] != y[3]:
                return False
    return True


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: decoder_cuobjdump_test.py <semu> <fixture>",
              file=sys.stderr)
        return 2
    semu = Path(sys.argv[1])
    data = json.load(open(sys.argv[2]))
    vecs = data["vectors"] if isinstance(data, dict) else data

    words = "\n".join(f"{v['lo']} {v['hi']}" for v in vecs) + "\n"
    proc = subprocess.run([str(semu), "disasm"], input=words, text=True,
                          capture_output=True)
    lines = proc.stdout.splitlines()
    if len(lines) != len(vecs):
        print(f"FAIL: decoder output {len(lines)} != fixture {len(vecs)}",
              file=sys.stderr)
        return 1

    n_ok = 0
    bad = []
    coverage = {}
    for v, line in zip(vecs, lines):
        parts = line.split("\t")
        if parts[0] != "OK":
            bad.append(f"{v['cubin']}@{v['pc']:#x}: {parts[0]} "
                       f"(want {v['text'][:50]})")
            continue
        semu_txt = parts[2].strip()
        # strip the schedule bracket from semu text
        semu_txt = re.sub(r"\s*;\s*\[.*\]\s*$", "", semu_txt).strip()
        cuobj_txt = v["text"].strip()
        # cuobjdump may have trailing schedule text (&wr=... ?trans)
        cuobj_txt = re.sub(r"\s*(&\w+=.*|\?\w+.*|;.*)?$", "",
                           cuobj_txt).strip()

        g1, b1, m1, o1 = parse_ops(cuobj_txt)
        g2, b2, m2, o2 = parse_ops(semu_txt)
        n1 = normalize_side(g1, b1, m1, o1)
        n2 = normalize_side(g2, b2, m2, o2)

        # branch targets: cuobjdump prints absolute PC target, semu prints the
        # relative displacement; compare only the register/predicate operands
        # and the mnemonic/predicate, and skip the numeric target.
        is_branch = n1["base"] in BRANCH_SET

        if n1["guard"] != n2["guard"]:
            bad.append(f"{v['cubin']}@{v['pc']:#x}: guard {n1['guard']} != "
                       f"{n2['guard']} ({cuobj_txt[:40]} vs {semu_txt[:40]})")
            continue
        if n1["base"] != n2["base"]:
            bad.append(f"{v['cubin']}@{v['pc']:#x}: mnemonic {n2['base']} != "
                       f"{n1['base']} ({cuobj_txt[:40]})")
            continue
        # modifiers: bidirectional comparison (GAP-10).  cuobjdump omits
        # default size/half-selector modifiers that semu prints explicitly
        # (.32, .H0_H0); and cuobjdump renders the sm90-era IMAD.SHL form
        # which the sm120 spec (and the reference disassembler) model as
        # plain IMAD.  After those explicit allowlists, the modifier sets
        # must be EQUAL in both directions.
        m1s, m2s = set(n1["mods"]), set(n2["mods"])
        # cuobjdump-only .SHL on IMAD (sm120 has no IMAD.SHL variant)
        if "SHL" in m1s and n1["base"] == "IMAD":
            m1s = m1s - {"SHL"}
        # semu-only default size / half-selector modifiers: strip them from
        # the semu side only when cuobjdump does NOT carry the same modifier
        # (LDC vs LDC.32).  When both sides have .64/.32 it is a semantic
        # width and must match.
        _default_mods = {"32", "64", "128", "16", "H0_H0", "H1_H0",
                         "H1_H1", "H0_NH1"}
        m2s = m2s - (_default_mods - m1s)
        if m1s != m2s:
            missing = m1s - m2s
            extra = m2s - m1s
            bad.append(f"{v['cubin']}@{v['pc']:#x}: modifier mismatch "
                       f"(semu missing {sorted(missing)}, semu extra "
                       f"{sorted(extra)}) ({cuobj_txt[:40]})")
            continue
        # operands
        o1, o2 = n1["ops"], n2["ops"]
        if is_branch:
            # GAP-10: compare branch targets PC-relatively.  cuobjdump prints
            # the absolute target address; semu prints the relative
            # displacement.  SASS semantics: target = pc + 16 + displacement
            # (displacement is relative to the NEXT instruction).
            bad_target = False
            if len(o1) == len(o2) and o1 and o2:
                tgt1 = o1[-1] if o1[-1][0] == "IMM" else None
                tgt2 = o2[-1] if o2[-1][0] == "IMM" else None
                if tgt1 is not None and tgt2 is not None:
                    expected_disp = tgt1[1] - v["pc"] - 16
                    if tgt2[1] != expected_disp:
                        bad.append(
                            f"{v['cubin']}@{v['pc']:#x}: branch target "
                            f"displacement {tgt2[1]:#x} != expected "
                            f"{expected_disp:#x} (target {tgt1[1]:#x}) "
                            f"({cuobj_txt[:40]})")
                        bad_target = True
                    o1, o2 = o1[:-1], o2[:-1]
            if not bad_target and not ops_equal(o1, o2):
                bad.append(f"{v['cubin']}@{v['pc']:#x}: branch operands "
                           f"differ ({cuobj_txt[:40]} vs {semu_txt[:40]})")
                continue
            if bad_target:
                continue
        else:
            # semu may render trailing default-valued immediates that
            # cuobjdump omits (MOV's 0xF pixel mask, BAR's 0x0 barrier id).
            # Drop matching trailing IMM operands from the longer side.
            o1, o2 = n1["ops"], n2["ops"]
            while len(o2) > len(o1) and o2 and o2[-1][0] == "IMM" and \
                    o2[-1][1] in (0, 15):
                o2 = o2[:-1]
            while len(o1) > len(o2) and o1 and o1[-1][0] == "IMM" and \
                    o1[-1][1] in (0, 15):
                o1 = o1[:-1]
            if not ops_equal(o1, o2):
                bad.append(f"{v['cubin']}@{v['pc']:#x}: operands differ "
                           f"({cuobj_txt[:50]} vs {semu_txt[:50]})")
                continue
        n_ok += 1
        key = "branch" if is_branch else (
            "desc" if any(o[0] == "DESC" for o in o1) else
            ("const" if any(o[0] == "CONST" for o in o1) else
             ("mem" if any(o[0] == "MEM" for o in o1) else
              ("guard" if n1["guard"] else "plain"))))
        coverage[key] = coverage.get(key, 0) + 1

    if bad:
        for b in bad[:25]:
            print("  " + b, file=sys.stderr)
        print(f"FAIL: {len(bad)}/{len(vecs)} cuobjdump vectors disagreed",
              file=sys.stderr)
        return 1
    cov = ", ".join(f"{k}={v}" for k, v in sorted(coverage.items()))
    print(f"OK: {n_ok}/{len(vecs)} real cuobjdump vectors pass structured "
          f"comparison; coverage: {cov}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
