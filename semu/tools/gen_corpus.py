#!/usr/bin/env python3
"""Generate a per-variant encoding corpus from sm120.json for Phase 1.

For every one of the 1414 sm120 encoding variants this produces a *valid*
128-bit instruction word by invoking the reference assembler encoder
(assembler/sass_encoder.py) directly with a default slot map, then running an
iterative fixup that adjusts modifier/operand slot values until all legality
conditions hold and the encoder accepts the encoding.

Output (JSON): list of {lo, hi, mnemonic, variant_class, opcode}.
Also used by tests to drive encode -> decode -> encode round-trips.

Usage:
    python3 semu/tools/gen_corpus.py [--db sm120.json] [--out /tmp/corpus.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from assembler.operand import Sched  # noqa: E402
from assembler.sass_cond import ConditionEvaluator  # noqa: E402
from assembler.sass_encoder import SassEncoder  # noqa: E402
from assembler.sass_matcher import MatchResult  # noqa: E402

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
NUM_RE = re.compile(r"^(?:0x[0-9A-Fa-f]+|\d+)$")


def parse_default(db, slot):
    typ = slot["type"]
    dflt = slot.get("default")
    if dflt is None:
        return None
    if isinstance(dflt, int):
        return dflt
    s = str(dflt)
    nm = s.split("/")[0].strip().strip('"')
    if not nm:
        return None
    e = db["enums"].get(typ, {})
    for k, v in e.items():
        if (k == nm or k.lstrip("_") == nm.lstrip("_")) and v is not None:
            return v
    try:
        return int(nm, 0)
    except ValueError:
        return None


def safe_value(slot):
    typ = slot["type"]
    if typ in ("Register", "NonZeroRegister", "UniformRegister",
               "NonZeroUniformRegister"):
        return 0
    if typ in ("ZeroRegister", "ZeroUniformRegister"):
        return 255
    if typ in ("Predicate", "UniformPredicate", "UImm", "SImm", "RSImm",
               "F16Imm", "F32Imm", "F64Imm", "BITSET", "SpecialRegister",
               "BD", "Scoreboard", "C", "REQ", "WR", "RD"):
        return 0
    if typ in ("DESC", "GMMA"):
        return 1
    return 0


def build_defaults(db, variant):
    sm = {}
    # 1. Encoding fixed/star fields
    for f in variant["encoding"]:
        name, rhs, rk = f["name"], f["rhs"], f.get("rhs_kind", "")
        if name in sm:
            continue
        if rk == "star_num":
            try:
                sm[name] = int(rhs[1:], 0)
            except (ValueError, IndexError):
                sm[name] = 0
        elif rk == "num":
            try:
                sm[name] = int(rhs, 0)
            except ValueError:
                sm[name] = 0
    # 2. Format defaults
    for s in variant["format"]["slots"]:
        if s["name"] not in sm and s.get("default") is not None:
            v = parse_default(db, s)
            if v is not None:
                sm[s["name"]] = v
    # 3. Operand slots without defaults
    for s in variant["format"]["slots"]:
        if s["name"] not in sm:
            sm[s["name"]] = safe_value(s)
    # 4. attr flags
    for s in variant["format"]["slots"]:
        for attr in ("_not", "_negated", "_abs", "_invert"):
            sm.setdefault(s["name"] + attr, 0)
    return sm


def slot_names(db, variant):
    names = {s["name"] for s in variant["format"]["slots"]}
    for s in variant["format"]["slots"]:
        for attr in ("_not", "_negated", "_abs", "_invert"):
            names.add(s["name"] + attr)
    return names


def enum_alternatives(db, slot):
    e = db["enums"].get(slot["type"], {})
    vals = [v for k, v in e.items()
            if v is not None and v != -1
            and not str(k).startswith("INVALID")]
    vals = sorted(set(vals))
    return vals or [0]


def predicate_slots(db, variant, pred):
    names = slot_names(db, variant)
    out = []
    for m in IDENT_RE.finditer(pred):
        tok = m.group(0)
        if tok in names and not NUM_RE.match(tok):
            out.append(tok)
    return out


def solve(db, enc, variant, budget=600):
    """Return a slot_map that the encoder accepts, or None.

    Fixup pipeline (single pass, in order):
      1. defaults (no-op if they encode already);
      2. product search over every modifier slot referenced by any legality
         condition (union, so interdependent conditions resolve together);
      3. schedule-word fixup via the DEFINED TABLES_opex_* rows / bounded
         usched_info/batch_t values;
      4. register-operand fixup (alignment / NonZero / RZ constraints).
    ``budget`` bounds the total number of encode attempts per variant so the
    whole 1414-variant corpus stays fast.
    """
    import itertools

    sm = build_defaults(db, variant)
    enc._apply_sched(sm, Sched.default())
    mod_slots = {s["name"] for s in variant["format"]["slots"]
                 if s["modifier"]}
    slot_by_name = {s["name"]: s for s in variant["format"]["slots"]}

    # --- 0. discriminator fixup.  Two cases:
    # (a) star_slot fields whose RHS is `*slotname` pin the referenced FORMAT
    #     slot to one of its enum members; the encoder accepts *any* raw value,
    #     so build_defaults often leaves 0, which is not a member of the class's
    #     enum type (e.g. F2I's dstfmt=0 when the type is DSTFMT_U64_S64).
    # (b) plain slot fields whose enum type does not contain 0 (e.g. QMMA's
    #     col_B type COLONLY={COL:1}) — these are single-member discriminators
    #     too; safe_value leaves 0, which is not a legal member.
    # Normalize every enum-typed slot to a valid member.  This both produces
    # decodable corpus words and lets the decoder's discriminator check tell
    # the variants apart.  When the class allows any member (no conditions
    # constrain it) we pick the first valid one; the decoder accepts the whole
    # member set, so the word still round-trips.
    for f in variant["encoding"]:
        if f["rhs_kind"] == "star_slot":
            slot_name = f["rhs"].lstrip("*")
            if "(" not in slot_name:
                slot_by_name.setdefault(slot_name, None)
    for slot in variant["format"]["slots"]:
        slot_name = slot["name"]
        if slot["type"] not in db["enums"]:
            continue
        e = db["enums"][slot["type"]]
        valid = sorted({v for k, v in e.items()
                        if v is not None and v != -1
                        and not str(k).startswith("INVALID")})
        if not valid:
            continue
        cur = sm.get(slot_name)
        if cur not in valid:
            sm[slot_name] = valid[0]

    budget_left = [budget]
    last_sched = [Sched.default()]

    def try_encode(sched=None):
        if budget_left[0] <= 0:
            return False
        budget_left[0] -= 1
        try:
            s = sched or Sched.default()
            enc.encode(MatchResult(variant=variant, slot_map=sm), s)
            last_sched[0] = s
            return True
        except Exception:
            return False

    if try_encode():
        return sm, last_sched[0]

    ev = ConditionEvaluator(db, sm)
    ATTR_SUFFIX = {"negate": "negated", "absolute": "abs", "not": "not",
                   "invert": "invert"}

    def condition_refs(cond):
        """(modifier slots, attr keys, register slots) referenced by cond."""
        mods, attrs, regs = [], [], []
        for m in re.finditer(
                r"([A-Za-z_][A-Za-z0-9_]*)@(negate|absolute|not|invert)",
                cond):
            slot_name, attr = m.group(1), m.group(2)
            if slot_name in slot_by_name:
                attrs.append(f"{slot_name}_{ATTR_SUFFIX[attr]}")
        for n in predicate_slots(db, variant, cond):
            if n in mod_slots:
                mods.append(n)
            elif n in slot_by_name and slot_by_name[n]["type"] in (
                    "Register", "NonZeroRegister", "UniformRegister",
                    "NonZeroUniformRegister"):
                regs.append(n)
        return mods, attrs, regs

    # --- 1b. backtracking solver with early condition pruning.  Handles
    # variants with many cross-constrained modifier slots (TEX/TLD/FOOTPRINT)
    # where the capped product search overflows.  Assigns modifier slots one at
    # a time; a partial assignment is pruned as soon as a fully-bound
    # encoding-legality condition evaluates false.  Only the
    # ILLEGAL_INSTR_ENCODING_ERROR[_SASS_ONLY] conditions participate (they are
    # the ones that depend on modifier combinations); register-range guards are
    # already satisfied by the fixed defaults and are checked once at the end.
    # Bounded by a small node budget so pathological variants stay fast.
    def backtrack_search():
        legal_conds = [
            (c["predicate"], set(condition_refs(c["predicate"])[0]))
            for c in variant["conditions"]
            if c["error"] in ("ILLEGAL_INSTR_ENCODING_ERROR",
                              "ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR")]
        # candidate values per modifier slot, most-constrained first; ties
        # broken by slot name so iteration is deterministic; the format default
        # value first (the assembler's natural choice).
        names = sorted(mod_slots, key=lambda n: (
            -sum(1 for _, refs in legal_conds if n in refs), n))
        cands = {}
        for n in names:
            slot = slot_by_name[n]
            if slot["type"] in db["enums"]:
                alts = enum_alternatives(db, slot)
            else:
                alts = [0]
            dflt = parse_default(db, slot)
            if dflt in alts:
                alts = [dflt] + [a for a in alts if a != dflt]
            cands[n] = alts

        nodes = [0]
        max_nodes = 512

        def assign(idx):
            if nodes[0] >= max_nodes:
                return False
            if idx == len(names):
                if try_encode():
                    return True
                return False
            n = names[idx]
            for v in cands[n]:
                nodes[0] += 1
                old = sm.get(n, 0)
                sm[n] = v
                bound_names = set(names[:idx + 1])
                # prune fully-bound legality conditions
                ok = True
                for p, refs in legal_conds:
                    if refs - bound_names:
                        continue
                    if not ev.evaluate(p):
                        ok = False
                        break
                if ok and assign(idx + 1):
                    return True
                sm[n] = old
            return False

        if assign(0):
            return sm, last_sched[0]
        return None

    r = backtrack_search()
    if r:
        return r

    def product_search(names, alt_sets, cap=512):
        total = 1
        for a in alt_sets:
            total *= len(a)
            if total > cap:
                return
        for combo in itertools.product(*alt_sets):
            old = {n: sm[n] for n in names}
            for n, av in zip(names, combo):
                sm[n] = av
            if all(ev.evaluate(c["predicate"])
                   for c in variant["conditions"]) and try_encode():
                return sm, last_sched[0]
            for n, v in old.items():
                sm[n] = v

    # --- 2a. modifier-only product (fast; fixes most F2FP/QMMA/FOOTPRINT) ---
    refs = []
    seen = set()
    for c in variant["conditions"]:
        for n in predicate_slots(db, variant, c["predicate"]):
            if n in mod_slots and n not in seen:
                seen.add(n)
                refs.append(n)
    if refs:
        r = product_search(refs, [enum_alternatives(db, slot_by_name[n])
                                  for n in refs], cap=64)
        if r:
            return r

    # --- 2b. targeted product: slots referenced by the *currently-failing*
    # conditions (modifier slots, attr flags, enum operands, registers and
    # constrained immediates), plus the format-default-value-first ordering.
    # Unlike 2a's whole-condition union, this only touches what actually needs
    # changing, so the product stays small even for variants whose shared
    # opcode has many modifier slots (qmma_sp_ etc.).
    fails = ev.check_variant(variant)
    names, alts = [], []
    def add_name(n):
        if n not in names:
            names.append(n)
    for err, msg in fails:
        cond = None
        for c in variant["conditions"]:
            if c["error"] == err and c.get("message", "") == msg:
                cond = c
                break
        if cond is None:
            continue
        mods, attrs, regs = condition_refs(cond["predicate"])
        for n in mods + attrs + regs:
            add_name(n)
        # Immediate operands constrained by the predicate (e.g. `Sb == 3088`,
        # `size !=`Enum@INVALID): offer the constants named in the condition
        # plus the slot's enum values.
        for m in re.finditer(r"(\b\w+)\s*(==|!=)\s*(`[A-Za-z_][A-Za-z0-9_.]*@[^)\s]+|\d+)",
                             cond["predicate"]):
            slot_name = m.group(1)
            if slot_name not in slot_by_name:
                continue
            st = slot_by_name[slot_name]["type"]
            if st not in ("UImm", "SImm", "RSImm", "BITSET",
                          "F16Imm", "F32Imm", "F64Imm"):
                continue
            add_name(slot_name)
    for n in names:
        st = slot_by_name.get(n)
        stype = st["type"] if st else ""
        if n in mod_slots:
            alts.append(enum_alternatives(db, st))
        elif n.endswith(("_negated", "_abs", "_not", "_invert")):
            alts.append([0, 1])
        elif stype in ("UniformRegister", "NonZeroUniformRegister",
                       "ZeroUniformRegister"):
            alts.append([0, 8, 255])
        elif stype in ("Register", "NonZeroRegister", "ZeroRegister"):
            alts.append([0, 8, 255])
        elif stype and stype in db["enums"]:
            alts.append(enum_alternatives(db, st))
        else:
            # immediate slot: collect constants from the failing predicates
            vals = {0}
            for err, msg in fails:
                cond = None
                for c in variant["conditions"]:
                    if c["error"] == err and c.get("message", "") == msg:
                        cond = c
                        break
                if cond:
                    for m in re.finditer(
                            r"\b" + re.escape(n) +
                            r"\s*==\s*(`[A-Za-z_][A-Za-z0-9_.]*@[^)\s]+|\d+)",
                            cond["predicate"]):
                        lit = m.group(1)
                        if lit.startswith("`"):
                            etype, _, val = lit[1:].partition("@")
                            e = db["enums"].get(etype, {})
                            if val in e:
                                vals.add(int(e[val]))
                        else:
                            try:
                                vals.add(int(lit, 0))
                            except ValueError:
                                pass
            alts.append(sorted(vals))
    if names:
        r = product_search(names, alts, cap=512)
        if r:
            return r

    # --- 3. schedule-word fixup ---
    def sched_from(usched, batch_t, wr=7, rd=7):
        stall = usched - 16 if usched >= 16 else usched
        yield_val = 1 if usched < 16 else 0
        return Sched(wr_sb=wr, rd_sb=rd, stall=stall,
                     yield_val=yield_val, batch_t=batch_t)

    sched_ok = False
    for c in variant["conditions"]:
        m = re.match(r"DEFINED\s+(\w+)\(([^)]*)\)", c["predicate"])
        if not m:
            continue
        table_name = m.group(1)
        arg_names = [a.strip() for a in m.group(2).split(",")]
        if all(a in ("batch_t", "usched_info") for a in arg_names):
            tbl = db["tables"].get(table_name)
            if tbl:
                for row in tbl["rows"]:
                    try:
                        bt = int(row["in"][0], 0)
                        us = int(row["in"][1], 0)
                    except (ValueError, IndexError):
                        continue
                    if try_encode(sched_from(us, bt)):
                        return sm, last_sched[0]
                sched_ok = True
    if not sched_ok:
        for us in range(32):
            for bt in (0, 1, 2, 4, 8):
                if try_encode(sched_from(us, bt)):
                    return sm, last_sched[0]

    # --- 4. per-slot greedy fallback (large products skipped above) ---
    attr_keys = []
    seen = set()
    for c in variant["conditions"]:
        mods, attrs, regs = condition_refs(c["predicate"])
        for k in attrs:
            if k not in seen:
                seen.add(k)
                attr_keys.append(k)
    for key in attr_keys:
        if sm.get(key) == 1:
            continue
        old = sm.get(key, 0)
        sm[key] = 1
        if try_encode():
            return sm, last_sched[0]
        sm[key] = old
    for s in variant["format"]["slots"]:
        if s["type"] not in ("Register", "NonZeroRegister",
                             "UniformRegister", "NonZeroUniformRegister"):
            continue
        for alt in (8, 16, 32, 1, 255):
            if sm.get(s["name"]) == alt:
                continue
            old = sm[s["name"]]
            sm[s["name"]] = alt
            if try_encode():
                return sm, last_sched[0]
            sm[s["name"]] = old

    if try_encode():
        return sm, last_sched[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "sm120.json"))
    ap.add_argument("--out", default="/tmp/semu_corpus.json")
    ap.add_argument("--hpp", default=None,
                    help="also emit a C++ corpus header (isa_corpus.hpp)")
    args = ap.parse_args()

    db = json.load(open(args.db))
    enc = SassEncoder(db)
    rows = []
    fail = 0
    for v in db["variants"]:
        got = solve(db, enc, v)
        if got is None:
            fail += 1
            rows.append({"lo": 0, "hi": 0, "mnemonic": v["mnemonic"],
                         "variant_class": v["class"],
                         "opcode": int(v["opcode"]), "encoded": False})
            continue
        sm, sched = got
        lo, hi = enc.encode(MatchResult(variant=v, slot_map=sm), sched)
        rows.append({"lo": lo, "hi": hi, "mnemonic": v["mnemonic"],
                     "variant_class": v["class"], "opcode": int(v["opcode"]),
                     "encoded": True})
    Path(args.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    enc_ok = sum(1 for r in rows if r["encoded"])
    print(f"wrote {args.out}: {enc_ok}/{len(rows)} variants encoded "
          f"({fail} unsolved)")

    if args.hpp:
        L = ["// Generated file -- do not edit.  Regenerate with:",
             "//   python3 semu/tools/gen_corpus.py --hpp",
             "#pragma once", "",
             "#include <cstdint>", "",
             "namespace semu::corpus {",
             "struct Word { std::uint64_t lo, hi; const char* cls; };",
             "inline constexpr std::uint32_t kNumCorpus = %d;" % len(rows),
             "inline const Word kWords[kNumCorpus] = {"]
        for r in rows:
            L.append(f"    {{0x{r['lo'] & 0xFFFFFFFFFFFFFFFF:016x}ULL, "
                     f"0x{r['hi'] & 0xFFFFFFFFFFFFFFFF:016x}ULL, "
                     f"{json.dumps(r['variant_class'])}}},")
        L.append("};")
        L.append("")
        L.append("}  // namespace semu::corpus")
        L.append("")
        Path(args.hpp).write_text("\n".join(L), encoding="utf-8")
        print(f"wrote {args.hpp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
