from __future__ import annotations
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from .operand import Operand, OperandKind, ParsedInstruction, Sched
from .sass_cond import ConditionEvaluator

# Cross-arch mnemonic aliases (resolved only if the target exists in the db):
#   LDCU = sm_120's name for sm_90's ULDC (uniform load from const bank).
_MNEMONIC_ALIASES = {"LDCU": "ULDC", "ULDC": "LDCU"}

# --- Slot type → OperandKind compatibility ---
TYPE_COMPAT: dict[OperandKind, set[str]] = {
    OperandKind.REG:       {"Register", "NonZeroRegister", "ZeroRegister"},
    OperandKind.UREG:      {"UniformRegister", "ZeroUniformRegister",
                            "NonZeroUniformRegister"},
    OperandKind.PRED:      {"Predicate"},
    OperandKind.UPRED:     {"UniformPredicate"},
    OperandKind.IMM_U:     {"UImm", "SImm", "RSImm", "OPTIONAL_GSB", "GSB0ONLY"},
    OperandKind.IMM_S:     {"SImm", "RSImm", "UImm"},
    OperandKind.IMM_F32:   {"F32Imm", "F64Imm", "F16Imm"},
    OperandKind.SPECIAL_REG: {"SpecialRegister"},
    OperandKind.CONST_BANK: {"C"},
    OperandKind.MEM_DESC:  {"DESC"},
    OperandKind.MEM_ADDR:  {"Register", "NonZeroRegister", "UniformRegister"},
    OperandKind.LABEL:     {"RSImm", "SImm", "UImm", "BD"},
    OperandKind.BAR:       {"BD", "CBU_STATE", "CBU_STATE_NONBAR"},
    OperandKind.SPECIAL_REG: {"SpecialRegister", "CBU_STATE", "CBU_STATE_NONBAR",
                              "ATEXIT_PCONLY", "UPRONLY", "PC_REG"},
    OperandKind.PR:        {"PR"},
    OperandKind.NP:        {"NP"},
    OperandKind.BAR:       {"BD", "CBU_STATE", "CBU_STATE_NONBAR"},
    OperandKind.SB:        {"Scoreboard"},
    OperandKind.BITSET:    {"BITSET"},
}

SCHED_TYPES = {"REQ", "BITSET", "WR", "RD", "USCHED_INFO", "BATCH_T", "PM_PRED", "REUSE", "PREDICATE"}
# Scheduling slots whose type is too generic (UImm) to filter by type alone
SCHED_SLOT_NAMES = {"src_rel_sb", "dst_wr_sb", "req_bit_set", "req", "wr", "rd",
                    "pm_pred", "batch_t", "usched_info",
                    "reuse_src_a", "reuse_src_b", "reuse_src_c", "reuse_src_d"}
COMPOSITE_TYPES = {"C", "DESC", "GMMA", "TMA"}


class MatchError(Exception):
    pass


@dataclass
class MatchResult:
    variant: dict
    slot_map: dict[str, Any] = field(default_factory=dict)
    score: int = 0
    warnings: list[str] = field(default_factory=list)
    condition_error: Optional[str] = None
    op_sizes: list[Optional[int]] = field(default_factory=list)


class SassMatcher:
    def __init__(self, db: dict):
        self.db = db
        self._by_mnemonic: dict[str, list[dict]] = defaultdict(list)
        for v in db["variants"]:
            self._by_mnemonic.setdefault(v["mnemonic"], []).append(v)
            # Pre-parse each variant's operand groups once (FORMAT is static);
            # this is the hot path in match().
            v["_op_groups"] = self._make_operand_groups(
                v["format"]["slots"], v["format"]["raw"])
        self._cond_errors: list[str] = []

    # ------------------------------------------------------------------
    def match(self, inst: ParsedInstruction) -> MatchResult:
        mn = inst.mnemonic.upper()
        # Some classes carry a modifier in the db mnemonic itself
        # (UIADD3.64 — a distinct opcode, not a modifier slot).  A dotted
        # prefix that exists in the db consumes those modifiers for ITS
        # candidates only; plain-mnemonic candidates still see (and must
        # account for) every written modifier.
        dotted: list[dict] = []
        dotted_inst = inst
        if inst.modifiers:
            for k in range(len(inst.modifiers), 0, -1):
                dmn = mn + "." + ".".join(inst.modifiers[:k])
                if dmn in self._by_mnemonic:
                    dotted = self._by_mnemonic[dmn]
                    dotted_inst = ParsedInstruction(
                        mnemonic=mn, modifiers=inst.modifiers[k:],
                        operands=inst.operands, pred=inst.pred,
                        pred_not=inst.pred_not,
                        pred_uniform=inst.pred_uniform, sched=inst.sched,
                        label=inst.label)
                    break
        candidates = self._by_mnemonic.get(mn, [])
        if not candidates and not dotted:
            # cross-arch mnemonic aliases: LDCU is the sm_120 name of sm_90's
            # ULDC.  Resolved only when the target mnemonic exists in this db.
            alias = _MNEMONIC_ALIASES.get(mn)
            if alias:
                candidates = self._by_mnemonic.get(alias, [])
        if not candidates:
            raise MatchError(f"no variants for mnemonic {inst.mnemonic!r}")

        self._cond_errors = []
        scored: list[MatchResult] = []
        for v in candidates:
            r = self._try_match(v, inst)
            if r is not None:
                scored.append(r)
        for v in dotted:
            r = self._try_match(v, dotted_inst)
            if r is not None:
                r.score += 1  # the dotted mnemonic literally wrote the modifier
                scored.append(r)

        if not scored:
            msg = (f"no matching variant for {inst.mnemonic} "
                   f"(operands={[o.kind.name for o in inst.operands]}, "
                   f"modifiers={inst.modifiers})")
            if self._cond_errors:
                msg += f"; conditions rejected: {'; '.join(self._cond_errors[:3])}"
            raise MatchError(msg)

        scored.sort(key=lambda r: (-r.score, r.variant["is_alternate"]))
        return scored[0]

    # ------------------------------------------------------------------
    def _try_match(self, variant: dict, inst: ParsedInstruction) -> Optional[MatchResult]:
        slots = variant["format"]["slots"]
        raw_fmt = variant["format"]["raw"]

        # 1. Parse operand groups from FORMAT (precomputed in __init__)
        op_groups = variant.get("_op_groups") or self._make_operand_groups(slots, raw_fmt)

        # 2. Match operands to groups (flexible — optional slots can be omitted)
        slot_map: dict[str, Any] = {}
        used_groups = self._match_operand_groups(op_groups, inst.operands, slot_map)
        if used_groups is None:
            return None

        # Set guard predicate from instruction prefix @[!]Px.  Uniform
        # instructions guard on a UniformPredicate slot named UPg (regular
        # instructions use Pg) — key the slot map by whichever the class uses.
        pred_slot = "Pg"
        for s in slots:
            if s.get("name") in ("Pg", "UPg") and \
                    s.get("type") in ("Predicate", "UniformPredicate"):
                pred_slot = s["name"]
                break
        if inst.pred is not None:
            slot_map[pred_slot] = inst.pred
        if inst.pred_not:
            slot_map[f"{pred_slot}_not"] = 1

        # Uniform-datapath instructions guard on a UniformPredicate slot
        # (UPg); a regular @Px guard on them is a semantic error even though
        # the bits encode identically (predicate field [15:12] is the same
        # width).  Likewise a uniform @UPx on a regular-Pg instruction is
        # wrong.  The predicate *slot type* is the discriminator (not the
        # pipe: e.g. VOTEU is udp_pipe yet takes a regular Pg input, and
        # SYNCS has both Pg and UPg variants).
        if (inst.pred is not None or inst.pred_not) and \
                inst.pred_uniform != (pred_slot == "UPg"):
            def _pname(uniform: bool) -> str:
                u = "U" if uniform else ""
                n = f"{u}PT" if inst.pred == 7 else f"{u}P{inst.pred}"
                return f"!{n}" if inst.pred_not else n
            if pred_slot == "UPg":
                self._cond_errors.append(
                    f"{inst.mnemonic}: uniform-datapath instruction requires "
                    f"a uniform predicate (@UPx), got @{_pname(inst.pred_uniform)}")
            else:
                self._cond_errors.append(
                    f"{inst.mnemonic}: non-uniform instruction does not take "
                    f"a uniform predicate (@UPx); use @{_pname(False)}")
            return None

        # Figure out which modifier slots were consumed by operand matching
        # (width pins ONLY64/U32ONLY excluded: they bind from the operand
        # width, but the written `.64` modifier must still be consumed by
        # modifier matching below)
        consumed_mods = set()
        for grp in op_groups:
            for s in grp:
                if s["modifier"] and s["type"] not in ("ONLY64", "U32ONLY"):
                    consumed_mods.add(s["name"])
        # Operand byte-select suffix (.B0-.B3 on a UREG, UR2UP/P2UR) binds
        # the B3B0-typed modifier slot; mark it consumed so modifier
        # matching doesn't reset it to the default.
        for op in inst.operands:
            if op.bsel is not None:
                bslot = next((s for s in slots if s["type"] == "B3B0"), None)
                if bslot is None:
                    return None
                slot_map[bslot["name"]] = op.bsel
                consumed_mods.add(bslot["name"])

        # 3. Match remaining modifiers
        enc_names = set()
        for f in variant.get("encoding", []):
            for nm in re.findall(r"\b[A-Za-z_][A-Za-z0-9_.]*\b",
                                 f.get("rhs", "")):
                enc_names.add(nm)
        mod_map = self._match_modifiers(slots, inst.modifiers, consumed_mods, enc_names)
        if mod_map is None:
            return None
        for k, v in mod_map.items():
            # iswz* values come from operand .H0_H0/.H1_H1 suffixes when present;
            # don't let the modifier default (0) clobber an operand-derived value.
            if k.startswith("iswz") and k in slot_map and slot_map[k] != 0:
                continue
            slot_map[k] = v

        # 4. Fill encoding defaults so condition predicates can resolve
        #    star-pinned slots (*7, *255, *hilo, ...) and format defaults.
        self._fill_encoding_defaults(variant, slot_map)

        # 4b. Validate explicit register groups ({Ra,Rb}) against the matched
        #     variant's per-operand size predicates (IDEST/ISRC_*_SIZE).
        #     Catches e.g. MOV {R0,R1}, R2 (32-bit variant) or LDCU.64 {UR4}
        #     (single-reg group) — a group that doesn't match the operand's
        #     real size would silently reuse/overwrite a register.
        op_sizes: list[Optional[int]] = []
        for oi, (grp, op) in enumerate(zip(used_groups, inst.operands)):
            want = self._operand_expected_size(grp, variant, slot_map)
            op_sizes.append(want)
            if want is None or op.kind not in (OperandKind.REG, OperandKind.UREG):
                continue
            if op.regs is not None:
                got = len(op.regs) * 32
                if got != want:
                    pfx = "UR" if op.kind == OperandKind.UREG else "R"
                    base = op.regs[0]
                    sugg = ",".join(f"{pfx}{base + i}"
                                    for i in range(want // 32))
                    self._cond_errors.append(
                        f"{inst.mnemonic}: operand #{oi} "
                        f"({{{','.join(f'{pfx}{r}' for r in op.regs)}}}) is "
                        f"{got}-bit but this variant expects a "
                        f"{want}-bit operand — list every register "
                        f"explicitly, e.g. {{{sugg}}}")
                    return None
            elif want > 32:
                # RZ as a wide operand means "none/empty" (e.g. HGMMA's
                # second accumulator Rc=RZ encodes 0); allow it.  UR-domain
                # Z is 255 (UniformRegister enum; 63 is the legacy sm_90
                # 6-bit alias), also a legal placeholder.
                if int(op.value) == 255 or (op.kind == OperandKind.UREG
                                            and int(op.value) in (63, 255)):
                    continue
                rv = int(op.value)
                pfx = "UR" if op.kind == OperandKind.UREG else "R"
                sugg = ",".join(f"{pfx}{rv + i}" for i in range(want // 32))
                self._cond_errors.append(
                    f"{inst.mnemonic}: operand #{oi} ({pfx}{rv}) is a "
                    f"single {op.kind.name.lower()} register but this "
                    f"variant expects a {want}-bit operand — list every "
                    f"register explicitly, e.g. {{{sugg}}}")
                return None

        # 5. Check CONDITIONS — reject if any hard condition predicate is FALSE.
        cond_err = self._check_conditions(variant, slot_map)
        if cond_err is not None:
            if cond_err not in self._cond_errors:
                self._cond_errors.append(cond_err)
            return None

        score = self._compute_score(variant, inst)
        # Prefer variants that bind the first operand group: when a single
        # register can serve as group #1 of one class (BAR IR form: barrier
        # id immediate skipped) or group #0 of another (RI form: id register
        # used), nvcc's encoding is the latter.
        if used_groups:
            for gi, g in enumerate(op_groups):
                if g is used_groups[0]:
                    score -= gi
                    break
        return MatchResult(variant=variant, slot_map=slot_map, score=score,
                           op_sizes=op_sizes)

    # ------------------------------------------------------------------
    def _operand_expected_size(self, group: list[dict], variant: dict,
                               slot_map: dict) -> Optional[int]:
        """Expected bit-size of an operand group from the variant's size
        predicates (IDEST_SIZE / ISRC_A/B/C/E_SIZE).  None = not a plain
        register operand (composite/modifier) or unresolvable — no check."""
        preds = variant.get("predicates", {})
        if not preds:
            return None
        key = None
        for s in group:
            if s["modifier"]:
                continue
            name = s["name"]
            if name in ("Ra",):        key = "ISRC_A_SIZE"
            elif name in ("Rb",):      key = "ISRC_B_SIZE"
            elif name in ("Rc",):      key = "ISRC_C_SIZE"
            elif name in ("Re",):      key = "ISRC_E_SIZE"
            elif name.startswith("Rd") or name.startswith("URd"):
                key = "IDEST_SIZE"
            break  # primary (first non-modifier) slot decides
        if key is None or key not in preds:
            return None
        return ConditionEvaluator(self.db, slot_map).eval_int(preds[key])
    # ------------------------------------------------------------------
    # Operand grouping — no comma parsing needed
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_scheduling(raw: str) -> str:
        result = []
        depth = 0
        i = 0
        while i < len(raw):
            if raw[i] == "$" and i + 1 < len(raw) and raw[i + 1] == "(":
                depth += 1
                i += 2
                continue
            if raw[i] == ")" and i + 1 < len(raw) and raw[i + 1] == "$":
                if depth > 0:
                    depth -= 1
                    i += 2
                    continue
                i += 1
                continue
            if depth == 0:
                result.append(raw[i])
            i += 1
        return "".join(result)

    @staticmethod
    def _find_top_level_commas(s: str) -> list[int]:
        positions = []
        depth_bracket = 0
        depth_paren = 0
        depth_brace = 0
        for i, ch in enumerate(s):
            if ch == "[":
                depth_bracket += 1
            elif ch == "]":
                depth_bracket -= 1
            elif ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren -= 1
            elif ch == "{":
                depth_brace += 1
            elif ch == "}":
                depth_brace -= 1
            elif ch == "," and depth_bracket == 0 and depth_paren == 0 and depth_brace == 0:
                positions.append(i)
        return positions

    def _make_operand_groups(self, slots: list[dict], raw_fmt: str = "") -> list[list[dict]]:
        """Group operand slots by top-level comma boundaries in the FORMAT.

        Slots that belong to a DESC/C composite bracket are merged.
        A trailing `FORMAT_ALIAS x = FN(...)` section (e.g. IMAD's
        GetPseudoOpRIR) is disassembler metadata, not an operand — it must
        not contribute a group.
        """
        if "FORMAT_ALIAS" in raw_fmt:
            raw_fmt = raw_fmt.split("FORMAT_ALIAS", 1)[0]
        def is_pg(s):
            return (s["name"] == "Pg" and s["type"] == "Predicate") or \
                   (s["name"] == "UPg" and s["type"] == "UniformPredicate")

        # Collect all non-Pg, non-scheduling slots
        all_candidates = [
            s for s in slots
            if not is_pg(s)
            and (s["type"] not in SCHED_TYPES
                 or (s["type"] == "BITSET" and s["name"] not in SCHED_SLOT_NAMES))
            and s["name"] not in SCHED_SLOT_NAMES
        ]
        if not all_candidates:
            return []

        # Find the first non-modifier slot — everything before it is
        # instruction-level modifiers (skip). Everything from it onward
        # is operand slots (including sub-operand modifiers like ONLY64).
        # If ALL candidates are modifiers, treat them all as instruction-level.
        first_op = None
        for idx, s in enumerate(all_candidates):
            if not s["modifier"] or s["type"] in COMPOSITE_TYPES:
                first_op = idx
                break
        if first_op is None:
            return []  # all modifiers → no operand groups
        # Include everything from first_op onward, but filter out modifier slots
        # unless they belong to a composite group (C, DESC).
        raw_candidates = all_candidates[first_op:]
        operand_slots = []
        in_composite = False
        for s in raw_candidates:
            if s["type"] in COMPOSITE_TYPES:
                in_composite = True
                operand_slots.append(s)
            elif in_composite:
                operand_slots.append(s)  # everything inside composite group
            elif not s["modifier"]:
                operand_slots.append(s)
            elif s["type"] in ("ONLY64", "U32ONLY"):
                # address-width pin inside a plain address bracket — keep it
                # with the operand group so matching can reject width
                # mismatches (ATOMG [R2.64] must not take the U32ONLY class)
                operand_slots.append(s)
            # else: modifier outside composite → skip

        cleaned = ""
        if raw_fmt:
            cleaned = self._strip_scheduling(raw_fmt)
            comma_positions = self._find_top_level_commas(cleaned)
        else:
            comma_positions = []

        if not comma_positions:
            depths = self._slot_bracket_depths(raw_fmt)
            groups: list[list[dict]] = []
            for s in operand_slots:
                if s["type"] in COMPOSITE_TYPES:
                    groups.append([s])
                elif groups and (groups[-1][0]["type"] in COMPOSITE_TYPES
                                 or (depths.get(groups[-1][0]["name"], 0) > 0
                                     and depths.get(groups[-1][0]["name"], 0)
                                     == depths.get(s["name"], 0))):
                    groups[-1].append(s)
                else:
                    groups.append([s])
            return groups

        segments = self._split_into_segments(cleaned, comma_positions)
        group_slot_names = self._assign_slots_to_segments(segments, slots)
        depths = self._slot_bracket_depths(raw_fmt)

        groups = []
        for names in group_slot_names:
            grp = [s for s in operand_slots if s["name"] in names]
            merged = []
            for s in grp:
                if s["type"] in COMPOSITE_TYPES:
                    merged.append([s])
                elif merged and (merged[-1][0]["type"] in COMPOSITE_TYPES
                                 or (depths.get(merged[-1][0]["name"], 0) > 0
                                     and depths.get(merged[-1][0]["name"], 0)
                                     == depths.get(s["name"], 0))):
                    merged[-1].append(s)
                else:
                    merged.append([s])
            groups.extend(merged)

        return groups

    def _slot_bracket_depths(self, raw_fmt: str) -> dict[str, int]:
        """Slot name -> bracket nesting depth in the FORMAT (0 = not inside
        any [...]; >=1 = inside a bracket).  Used to merge LDS/STS address
        slots [Ra + Ra_offset] into one operand group."""
        depths: dict[str, int] = {}
        depth = 0
        for m in re.finditer(r":([A-Za-z_][A-Za-z0-9_]*)", raw_fmt or ""):
            d = 0
            for ch in raw_fmt[:m.start()]:
                if ch == "[":
                    d += 1
                elif ch == "]":
                    d -= 1
            depths[m.group(1)] = max(d, 0)
        return depths

    def _split_into_segments(self, cleaned: str, commas: list[int]) -> list[str]:
        """Split cleaned format string at comma positions into segments."""
        segments = []
        start = 0
        for cp in commas:
            segments.append(cleaned[start:cp])
            start = cp + 1
        segments.append(cleaned[start:])
        return segments

    def _assign_slots_to_segments(self, segments: list[str], slots: list[dict]) -> list[list[str]]:
        """Assign each slot name to the segment containing it."""
        # Find slot name positions in segments
        result: list[list[str]] = [[] for _ in segments]
        for s in slots:
            name = s["name"]
            for idx, seg in enumerate(segments):
                if ":" + name in seg or "(" + name + ")" in seg:
                    result[idx].append(name)
                    break
            else:
                # fallback: find colon+name anywhere in full string
                full = "".join(segments)
                pos = full.find(":" + name)
                if pos >= 0:
                    # Count commas before position
                    c = sum(1 for cp in self._find_top_level_commas(full) if cp < pos)
                    if c < len(result):
                        result[c].append(name)
        return result

    # ------------------------------------------------------------------
    # Flexible operand matching
    # ------------------------------------------------------------------
    def _match_operand_groups(self, groups: list[list[dict]],
                              operands: list[Operand],
                              slot_map: dict) -> Optional[list[list[dict]]]:
        """Match parsed operands to groups.  Optional groups (with defaults)
        can be skipped to make the count align.  Returns the group used for
        each operand, or None on failure."""
        paired = self._match_imm_pair(groups, operands, slot_map)
        if paired is not None:
            return paired

        if len(groups) == len(operands):
            return self._match_positional(groups, operands, slot_map)

        if len(groups) < len(operands):
            return None  # more operands than slots — impossible

        # groups > operands: try skipping optional groups
        return self._match_with_skips(groups, operands, 0, 0, slot_map)

    def _match_imm_pair(self, groups: list[list[dict]],
                        operands: list[Operand],
                        slot_map: dict) -> Optional[list[list[dict]]]:
        """f16x2/bf16x2 packed-immediate pair (HFMA2/HADD2/HMUL2/HMNMX2/
        HSET2/HSETP2 imm forms): the FORMAT has two adjacent F64Imm
        half-slots (Sc/Sc1, Sb/Sb1), but the assembly text carries the
        packed 32-bit pair as ONE immediate operand (raw 0fXXXXXXXX).
        Bind the single immediate to both half-slots; the encoder splits
        it by field target.  Returns the used-group list or None (fall
        through to generic matching)."""
        pair = [s for grp in groups for s in grp
                if s["type"] == "F64Imm" and not s["modifier"]]
        if len(pair) != 2 or len(operands) != len(groups) - 1:
            return None
        pair_names = {s["name"] for s in pair}
        pair_first_gi = next(
            i for i, g in enumerate(groups)
            if any(s["name"] in pair_names for s in g))
        # Exactly one immediate operand in the text, at the pair's group
        # position — cuobjdump prints FORMAT order, so the immediate's text
        # index disambiguates imm-middle (RIR) from imm-last (RRI) classes.
        imm_idx = [i for i, o in enumerate(operands)
                   if o.kind == OperandKind.IMM_F32
                   or (o.kind in (OperandKind.IMM_U, OperandKind.IMM_S)
                       and o.value == 0)]
        if len(imm_idx) != 1 or imm_idx[0] != pair_first_gi:
            return None
        ii = imm_idx[0]
        rest_ops = operands[:ii] + operands[ii + 1:]
        rest_grps = [g for g in groups
                     if not any(s["type"] == "F64Imm" and not s["modifier"]
                                for s in g)]
        if len(rest_ops) != len(rest_grps):
            return None
        trial = dict(slot_map)
        used: list[list[dict]] = []
        for grp, op in zip(rest_grps, rest_ops):
            if not self._match_group(grp, op, trial):
                return None
            used.append(grp)
        op = operands[ii]
        val = self._extract_value(pair[0], op)
        if val is None:
            return None
        for s in pair:
            trial[s["name"]] = val
            if op.raw32 is not None:
                trial[f"{s['name']}_raw32"] = op.raw32
        slot_map.clear()
        slot_map.update(trial)
        pair_groups = [g for g in groups
                       if any(s["type"] == "F64Imm" and not s["modifier"]
                              for s in g)]
        return used + pair_groups

    def _match_positional(self, groups: list[list[dict]],
                          operands: list[Operand],
                          slot_map: dict) -> Optional[list[list[dict]]]:
        used: list[list[dict]] = []
        for grp, op in zip(groups, operands):
            if not self._match_group(grp, op, slot_map):
                return None
            used.append(grp)
        return used

    def _match_with_skips(self, groups: list[list[dict]],
                          operands: list[Operand],
                          gi: int, oi: int,
                          slot_map: dict) -> Optional[list[list[dict]]]:
        """Backtracking: match groups[gi:] to operands[oi:], skipping
        optional groups (those where every slot has a default).
        Returns the used-group list or None."""
        if oi == len(operands):
            # All operands consumed — remaining groups must all be optional
            for g in groups[gi:]:
                if not self._all_defaults(g):
                    return None
                self._fill_group_defaults(g, slot_map)
            return []
        if gi == len(groups):
            return None  # operands left but no groups

        grp = groups[gi]
        op = operands[oi]

        # Try direct match
        if self._match_group(grp, op, slot_map):
            rest = self._match_with_skips(groups, operands, gi + 1, oi + 1, slot_map)
            if rest is not None:
                return [grp] + rest
            # Backtrack: undo slot_map entries from this group
            # (We can't easily undo, so we use a copy-based approach instead.
            #  For simplicity, we accept the first successful path.)
            # Actually, let's check for duplicate keys before doing this.

        # Try skipping this group (if optional)
        if self._all_defaults(grp):
            self._fill_group_defaults(grp, slot_map)
            rest = self._match_with_skips(groups, operands, gi + 1, oi, slot_map)
            if rest is not None:
                return rest
            # Undo defaults on backtrack
            for s in grp:
                slot_map.pop(s["name"], None)

        return None

    # ------------------------------------------------------------------
    def _match_group(self, group: list[dict], op: Operand, slot_map: dict) -> bool:
        if not group:
            return False

        # Find the first non-modifier slot (the "primary" slot for matching)
        primary = None
        for s in group:
            if not s["modifier"]:
                primary = s
                break

        if primary is None:
            # Group has only modifier slots — fill from defaults
            for s in group:
                if s.get("default") is not None:
                    slot_map[s["name"]] = self._parse_default(s["default"], s["type"])
            return True

        first_type = primary["type"]

        if first_type == "C" and op.kind == OperandKind.CONST_BANK:
            return self._match_const_bank(group, op, slot_map)
        if first_type in ("DESC", "GMMA", "TMA") and op.kind in (
                OperandKind.MEM_DESC, OperandKind.UREG):
            return self._match_mem_desc(group, op, slot_map)
        if op.kind == OperandKind.MEM_ADDR:
            # a plain [Ra+off] operand must not match a desc[...]-composite
            # group (e.g. STL's memdesc variant pins memdesc=1 even though
            # the text carries no descriptor)
            if any(s["type"] in COMPOSITE_TYPES for s in group):
                return False
            return self._match_mem_addr(group, op, slot_map)

        if len(group) == 1:
            return self._match_simple_slot(group[0], op, slot_map)

        # Multi-slot simple group:
        # — first non-modifier slot is the primary, rest are sub-fields
        ok = self._match_simple_slot(primary, op, slot_map)
        if ok:
            for s in group:
                if s["modifier"] and s["name"] not in slot_map and s.get("default") is not None:
                    slot_map[s["name"]] = self._parse_default(s["default"], s["type"])
                # space-separated reg+offset operand (RET.REL.NODEC R2-0x340):
                # the offset slot shares the register's operand group
                if not s["modifier"] and "offset" in s["name"].lower() and \
                        s["type"] in ("SImm", "RSImm", "UImm") and \
                        s["name"] not in slot_map:
                    slot_map[s["name"]] = op.offset
        return ok

    def _match_simple_slot(self, slot: dict, op: Operand, slot_map: dict) -> bool:
        st = slot["type"]
        compat = TYPE_COMPAT.get(op.kind)
        if compat is None or st not in compat:
            # cuobjdump prints a float immediate of exactly 0.0 as "0"
            # (IMM_U); zero is the same bit pattern in float and int, so it
            # is the one unambiguous coercion.  Non-zero ints stay rejected
            # ("1" as f32 1.0 vs bit pattern 1 would be ambiguous).
            if not (st in ("F32Imm", "F64Imm", "F16Imm")
                    and op.kind in (OperandKind.IMM_U, OperandKind.IMM_S)
                    and op.value == 0):
                return False
        val = self._extract_value(slot, op)
        if val is None:
            return False
        slot_map[slot["name"]] = val
        # register with PC-relative offset (RET.REL.NODEC R2-0x340): stash
        # for the trailing offset group consumed by _fill_group_defaults
        if op.offset and st in ("Register", "UniformRegister",
                                "NonZeroRegister", "ZeroRegister"):
            slot_map["_pending_offset"] = op.offset
        # Store negate/absolute/invert/lnot flags for slot_attr resolution
        if op.negated:
            slot_map[f"{slot['name']}_negated"] = 1
        if op.absolute:
            slot_map[f"{slot['name']}_abs"] = 1
        if op.invert:
            slot_map[f"{slot['name']}_invert"] = 1
        if op.lnot:
            slot_map[f"{slot['name']}_not"] = 1
        # HFMA2/HADD2 lane swizzle: an operand .H0_H0/.H1_H1/.F32/.H0_NH1
        # maps to the matching iswz<X> modifier slot (Ra->iswzA, Rb->iswzB,
        # Rc->iswzC; note iswzC is also typed ISWZA; HADD2 names its C-operand
        # swizzle slot iswzB_as_C instead of iswzC).
        if op.iswz is not None:
            base = slot["name"].upper().rstrip("0123456789")
            key = {"RA": "iswzA", "RB": "iswzB", "RC": "iswzC"}.get(base)
            if key:
                slot_map[key] = op.iswz
                if key == "iswzC":
                    slot_map["iswzB_as_C"] = op.iswz
        return True

    # ------------------------------------------------------------------
    # Composite operand expansion
    # ------------------------------------------------------------------
    def _match_const_bank(self, group: list[dict], op: Operand,
                          slot_map: dict) -> bool:
        for s in group:
            st = s["type"]
            if st == "C":
                slot_map[s["name"]] = 1
            elif st in ("UImm",) and ("bank" in s["name"].lower() or "Sa_bank" == s["name"]):
                slot_map[s["name"]] = op.value  # bank number
            elif st in ("SImm", "UImm") and "offset" in s["name"].lower():
                slot_map[s["name"]] = op.offset
            elif st in ("Register", "NonZeroRegister", "ZeroRegister"):
                # register-indexed const bank c[bank][Rr+off]; plain
                # c[bank][off] encodes the index register as RZ
                slot_map[s["name"]] = op.cbank_reg if op.cbank_reg is not None else 255
            elif st == "UniformRegister":
                slot_map[s["name"]] = op.addr_ureg if op.addr_ureg is not None else 255
            elif st in ("SImm", "UImm"):
                slot_map[s["name"]] = op.offset
            elif st == "ONLY64":
                slot_map[s["name"]] = 1 if op.width == 64 else 0
        return True

    def _match_mem_desc(self, group: list[dict], op: Operand,
                        slot_map: dict) -> bool:
        # Same width-pin rule as _match_mem_addr: the ONLY64/U32ONLY slot
        # inside the DESC composite pins the address width (LDGSTS .E vs
        # .E.64 descriptor forms).
        for s in group:
            if s["type"] == "ONLY64" and op.width != 64:
                return False
            if s["type"] == "U32ONLY" and op.width != 32:
                return False
        for s in group:
            st = s["type"]
            if st in ("DESC", "GMMA", "TMA"):
                slot_map[s["name"]] = 1
            elif st == "UniformRegister":
                slot_map[s["name"]] = op.value  # UR from desc[UR] / gdesc[UR]
            elif st in ("Register", "NonZeroRegister"):
                slot_map[s["name"]] = op.addr_reg  # Ra from [Ra+offset]
            elif st in ("SImm", "UImm") and "offset" in s["name"].lower():
                slot_map[s["name"]] = op.offset
            elif st in ("SImm", "UImm"):
                slot_map[s["name"]] = op.offset
            elif st == "ONLY64":
                slot_map[s["name"]] = 1 if op.width == 64 else 0
            elif st == "U32ONLY":
                slot_map[s["name"]] = 1 if op.width == 32 else 0
        return True

    def _match_mem_addr(self, group: list[dict], op: Operand,
                        slot_map: dict) -> bool:
        # A memory address carries exactly one of: a GPR base ([Ra+off]) or
        # an explicit uniform-register index ([RZ+URb+off]).  The matched
        # variant must consume the form actually written: variants with a
        # UniformRegister slot would otherwise either silently drop the UR
        # index (encoding a different address) or fabricate a URb value from
        # the GPR base.
        has_ur_slot = any(s["type"] == "UniformRegister" for s in group)
        if has_ur_slot and op.addr_ureg is None:
            # UR-index slot with an "absent" default (URZ): plain [Ra+off]
            # matches, binding the default (STAS/REDAS `[{R2,R3}]`).
            ur_slot = next(s for s in group if s["type"] == "UniformRegister")
            ur_def = ur_slot.get("default")
            if ur_def is None or \
                    self._parse_default(ur_def, "UniformRegister") != 255:
                return False
            slot_map[ur_slot["name"]] = 255
        elif not has_ur_slot and op.addr_ureg is not None:
            return False
        # Address-width pins: a 64-bit address ([{R2,R3}+...]) must not match
        # a class pinned U32ONLY (and vice versa) — the pin bit is part of
        # the encoding, matching the wrong class silently drops it.
        for s in group:
            if s["type"] == "ONLY64" and op.width != 64:
                return False
            if s["type"] == "U32ONLY" and op.width != 32:
                return False
        for s in group:
            st = s["type"]
            if st in ("Register", "NonZeroRegister", "ZeroRegister"):
                slot_map[s["name"]] = op.value
            elif st == "UniformRegister":
                if op.addr_ureg is not None:
                    slot_map[s["name"]] = op.addr_ureg
            elif st in ("SImm", "UImm") and "offset" in s["name"].lower():
                slot_map[s["name"]] = op.offset
            elif st == "ONLY64":
                slot_map[s["name"]] = 1
            elif st == "U32ONLY":
                slot_map[s["name"]] = 0
        return True

    # ------------------------------------------------------------------
    def _extract_value(self, slot: dict, op: Operand) -> Optional[int]:
        """Get numeric value from operand for a given slot."""
        st = slot["type"]
        v = op.value
        if st in ("Register", "NonZeroRegister", "ZeroRegister"):
            return v if isinstance(v, int) else None
        if st in ("UniformRegister", "ZeroUniformRegister",
                  "NonZeroUniformRegister"):
            return v if isinstance(v, int) else None
        if st in ("Predicate", "UniformPredicate"):
            return v if isinstance(v, int) else None
        if st in ("UImm", "SImm", "RSImm", "OPTIONAL_GSB", "GSB0ONLY"):
            return v if isinstance(v, int) else None
        if st in ("F32Imm", "F64Imm", "F16Imm"):
            import struct
            if isinstance(v, float):
                return struct.unpack(">I", struct.pack(">f", v))[0]
            if isinstance(v, int):
                return v & 0xFFFFFFFF
            return None
        if st == "PR":
            return 0
        if st == "Scoreboard":
            return v if isinstance(v, int) else None
        if st == "BITSET":
            return v if isinstance(v, int) else None
        if st == "BD":
            return v if isinstance(v, int) else None
        if st == "NP":
            return v if isinstance(v, int) else None
        if st in ("SpecialRegister", "UPRONLY", "PC_REG"):
            v_str = v if isinstance(v, str) else ""
            enum_vals = self.db["enums"].get(st, {})
            for name, val in enum_vals.items():
                if name.replace("_", "").upper() == v_str.replace("_", "").upper() \
                   and isinstance(val, int):
                    return val
            return 0
        if st in ("CBU_STATE", "CBU_STATE_NONBAR"):
            # bar register B0..B15 -> numeric 0..15; named state (MACTIVE,
            # MEXITED, ATEXIT_PC.LO, ...) -> enum lookup
            if isinstance(v, int):
                return v
            if isinstance(v, str):
                v_str = v.replace("_", "").upper()
                for name, val in self.db["enums"].get(st, {}).items():
                    if name.replace("_", "").upper() == v_str and isinstance(val, int):
                        return val
                return None
            return None
        if st == "ATEXIT_PCONLY":
            # fixed-token constraint operand (e.g. `ATEXIT_PC`); not encoded,
            # so accept any string that names one of the enum's values.
            if isinstance(v, str):
                v_str = v.replace("_", "").upper()
                for name in self.db["enums"].get(st, {}):
                    if name.replace("_", "").upper() == v_str:
                        return 0
            return None
        return None

    def _all_defaults(self, group: list[dict]) -> bool:
        return all(s.get("default") is not None for s in group)

    def _fill_group_defaults(self, group: list[dict], slot_map: dict) -> None:
        # A register operand carrying a PC-relative offset (RET.REL.NODEC
        # R2-0x340) binds its trailing all-default immediate "offset" group
        # even though the text has no separate operand for it.
        if "_pending_offset" in slot_map and group and all(
                "offset" in s["name"].lower() and s.get("default") is not None
                for s in group):
            for s in group:
                if s["name"] not in slot_map:
                    slot_map[s["name"]] = slot_map.pop("_pending_offset")
            return
        for s in group:
            if s["name"] not in slot_map and s.get("default") is not None:
                slot_map[s["name"]] = self._parse_default(s["default"], s["type"])
                # A negatable predicate slot ([!]Predicate, e.g. sm90 LDG's
                # Pnz) that was omitted defaults to PT with the negate bit
                # CLEAR.  Without this, conditions like
                # DEFINED TABLES_Pnz_0(Pnz@not,Pnz) fail because Pnz@not is
                # missing from slot_map.
                if s["type"] == "Predicate" and f"{s['name']}_not" not in slot_map:
                    slot_map[f"{s['name']}_not"] = 0

    # ------------------------------------------------------------------
    # Modifier matching
    # ------------------------------------------------------------------
    def _match_modifiers(self, slots: list[dict], modifiers: list[str],
                         consumed: set[str] | None = None,
                         encoded_slots: set[str] | None = None) -> Optional[dict]:
        consumed = consumed or set()
        mod_slots = [s for s in slots if s["modifier"] and s["name"] not in consumed]
        result: dict[str, Any] = {}
        remaining = list(modifiers)

        for s in mod_slots:
            etype = s["type"]
            enum_vals = self.db["enums"].get(etype, {})
            default = s.get("default")
            name = s["name"]

            if not enum_vals:
                if default is not None:
                    result[name] = self._parse_default(default, etype)
                continue

            # Pure-constraint modifier (e.g. sz:ONLY32, whose size is implied by
            # the opcode, not encoded in any field): consume it if present,
            # otherwise optional — skip.
            if default is None and encoded_slots is not None and name not in encoded_slots:
                hit = self._consume_enum(remaining, enum_vals)
                if hit is not None:
                    result[name], remaining = hit
                continue

            matched = False
            hit = self._consume_enum(remaining, enum_vals)
            if hit is not None:
                result[name], remaining = hit
                matched = True

            if not matched:
                if default is not None:
                    result[name] = self._parse_default(default, etype)
                elif (not remaining and
                        "ONLY" in etype and any(c.isdigit() for c in etype)):
                    # Width-constraint slot (ONLY64/ONLY256/ONLY32, U32ONLY,
                    # S32ONLY) with no default: its value is implied by the
                    # operand width, not by a user modifier.  Record the enum
                    # value so the encoder's `*size` star field resolves
                    # (IADD.64 encodes sz=*size=1).  Pure-letter flags like
                    # UONLY/EONLY/XONLY are NOT width constraints and must not
                    # be auto-set.
                    for k, v in enum_vals.items():
                        if isinstance(v, int) and not k.startswith("no") \
                                and "INVALID" not in k:
                            result[name] = v
                            break
                    continue
                else:
                    return None

        # All modifiers must be consumed — reject if any are left unmatched
        if remaining:
            return None

        return result

    @staticmethod
    def _consume_enum(remaining: list[str], enum_vals: dict) -> Optional[tuple[int, list[str]]]:
        """Match a slot's enum value against the front of `remaining`, trying
        a single modifier first, then dot-joined sequences (e.g. F2F.F16.F32
        -> ['F16','F32'] joined to enum value 'F16.F32').  Returns (value,
        remaining) or None."""
        # Spec enum names are mixed-case (e.g. "U16x2"), so match
        # case-insensitively (same normalization used by _parse_default).
        upper_map = {k.upper(): v for k, v in enum_vals.items()
                     if isinstance(v, int)}
        # value-less enums (RelOpt {REL: None}, ABSONLY {ABS: None}): a name
        # match consumes the modifier, value = None (variant implied, no bits).
        no_val = [k.upper() for k, v in enum_vals.items()
                  if v is None and not k.startswith("no")
                  and "INVALID" not in k.upper()]
        for i in range(len(remaining)):
            for k in range(1, min(4, len(remaining) - i) + 1):
                cand = ".".join(remaining[i:i + k])
                val = upper_map.get(cand.upper())
                if val is not None:
                    new_remaining = list(remaining)
                    del new_remaining[i:i + k]
                    return val, new_remaining
                if cand.upper() in no_val:
                    new_remaining = list(remaining)
                    del new_remaining[i:i + k]
                    return None, new_remaining
        return None

    def _parse_default(self, default: str, etype: str) -> int:
        # Format: "value" (e.g. "32", "S32", "PT", "noreuse"),
        #         "width/value" (e.g. "6/0x0000" → 0x0000, "24/0" → 0),
        #         "enum"/annotation (e.g. "PT"/PRINT → "PT")
        if "/" in default:
            parts = default.split("/", 1)
            # For "width/value": try value (second) first, then width (first)
            # For "enum/annotation": try first part first
            candidates = [parts[1], parts[0]]
        else:
            candidates = [default]

        for c in candidates:
            c = c.strip().strip('"\'')
            enum_vals = self.db["enums"].get(etype, {})
            # Prefer enum lookup (e.g. "32" → 4 for size enums)
            if c in enum_vals:
                return enum_vals[c]
            cu = c.upper()
            if cu in enum_vals:
                return enum_vals[cu]
            # Fallback: parse as integer
            try:
                return int(c, 0)
            except ValueError:
                pass

        return 0

    # ------------------------------------------------------------------
    # Conditions
    # ------------------------------------------------------------------
    # Hard errors: a FALSE predicate means the encoding is illegal.
    # ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR is also checked here (it mostly
    # disambiguates RZ-vs-nonRZ variants); only TABLES_opex legality is
    # deferred to the encoder (depends on the real scheduling word).
    _HARD_COND_ERRORS = {
        "OOR_REG_ERROR",
        "ILLEGAL_INSTR_ENCODING_ERROR",
        "ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR",
        "MISALIGNED_REG_ERROR",
        "INVALID_CONST_ADDR_ERROR",
        "ILLEGAL_INSTR_PARAM_ERROR",
        "UNPREDICTABLE_BEHAVIOR_WARNING",
    }

    def _check_conditions(self, variant: dict, slot_map: dict) -> Optional[str]:
        """Evaluate the variant's CONDITIONS against the slot_map.

        Returns None if every hard condition holds, else a message describing
        the first failing condition. ``TABLES_opex_*`` predicates are deferred
        to the encoder (they depend on the real scheduling word, which is not
        applied until encode time).
        """
        evaluator = ConditionEvaluator(self.db, slot_map)
        for c in variant.get("conditions", []):
            err = c["error"]
            pred = c["predicate"]
            # opex legality depends on the real usched/batch_t — checked in
            # SassEncoder after _apply_sched.
            if "TABLES_opex" in pred:
                continue
            if err not in self._HARD_COND_ERRORS:
                continue
            if not evaluator.evaluate(pred):
                msg = c.get("message", err)
                return f"{err}: {msg}" if msg else err
        return None

    # ------------------------------------------------------------------
    # Encoding defaults
    # ------------------------------------------------------------------
    def _fill_encoding_defaults(self, variant: dict, slot_map: dict) -> None:
        for f in variant["encoding"]:
            name = f["name"]
            if name in slot_map:
                continue
            rhs = f["rhs"]
            rk = f.get("rhs_kind", "")
            if rk == "star_num":
                try:
                    slot_map[name] = int(rhs[1:], 0)
                except ValueError:
                    slot_map[name] = 0
            elif rk == "num":
                try:
                    slot_map[name] = int(rhs, 0)
                except ValueError:
                    slot_map[name] = 0
            elif rk == "star_slot":
                star = rhs[1:] if rhs.startswith("*") else rhs
                try:
                    slot_map[name] = int(star, 0)
                except ValueError:
                    slot_map[name] = self._find_slot_default(variant, star)
            elif rk == "slot" and name not in slot_map:
                slot_map[name] = self._find_slot_default(variant, name)

        # Also fill FORMAT slots that are encoding inputs (e.g. batch_t, usched_info)
        for s in variant["format"]["slots"]:
            if s["name"] not in slot_map and s.get("default") is not None:
                slot_map[s["name"]] = self._parse_default(s["default"], s["type"])

    def _find_slot_default(self, variant: dict, slot_name: str) -> int:
        for s in variant["format"]["slots"]:
            if s["name"] == slot_name and s.get("default") is not None:
                return self._parse_default(s["default"], s["type"])
        return 0

    # ------------------------------------------------------------------
    def _compute_score(self, variant: dict, inst: ParsedInstruction) -> int:
        score = 100
        if variant.get("is_alternate"):
            score -= 50
        # Prefer variants whose modifiers the user explicitly wrote; when the
        # user wrote no modifier, prefer variants whose modifiers carry a
        # default (plain `IMAD`/`UIMAD` → LO, not the optional-HI variant;
        # `IMAD.U32` → plain imad, not imad_hi).
        mod_slots = [s for s in variant["format"]["slots"] if s["modifier"]
                     and s["type"] not in ("REUSE",)]
        consumed = 0
        for s in mod_slots:
            etype = s["type"]
            enum_vals = self.db["enums"].get(etype, {})
            default = s.get("default")
            has_default = default is not None
            if has_default and (etype in inst.modifiers
                                or str(default).split("/")[0]
                                .strip().strip('"') in inst.modifiers):
                consumed += 1
        if not inst.modifiers:
            if inst.mnemonic.upper() in ("IMAD", "UIMAD"):
                # nvcc emits plain IMAD/UIMAD as LO (imad 0x824 / uimad
                # 0x12a4 — both print without a modifier in cuobjdump);
                # the HI variant is only reachable with an explicit .HI.
                score += sum(1 for s in mod_slots
                             if s.get("default") is not None)
            else:
                # Historical sm_120 behavior: a plain form picks the variant
                # whose distinguishing modifier has NO default — IADD.64's
                # width slot is optional, etc.
                score += sum(1 for s in mod_slots
                             if s.get("default") is None)
        elif inst.mnemonic.upper() in ("IMAD", "UIMAD") and \
                not any(m.upper() == "HI" for m in inst.modifiers):
            # Same rule with modifiers present: IMAD.SHL/.IADD/.MOV/.ISCADD
            # (pseudo-opcode aliases, all encoding pseudo_opcode=0) without an
            # explicit .HI are the LO form (0x824); the HI-pseudo class
            # (0x827) must not win the tie.
            score += sum(2 for s in mod_slots if s["type"] == "LOOnly")
        return score + consumed * 5


def create_matcher(db_path: str = "") -> SassMatcher:
    from pathlib import Path
    if not db_path:
        from . import arch
        db_path = str(arch.db_path())
    with open(db_path) as f:
        db = json.load(f)
    return SassMatcher(db)
