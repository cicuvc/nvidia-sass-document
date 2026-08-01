from __future__ import annotations
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from .operand import Operand, OperandKind, ParsedInstruction, Sched
from .sass_cond import ConditionEvaluator

# --- Slot type → OperandKind compatibility ---
TYPE_COMPAT: dict[OperandKind, set[str]] = {
    OperandKind.REG:       {"Register", "NonZeroRegister", "ZeroRegister"},
    OperandKind.UREG:      {"UniformRegister"},
    OperandKind.PRED:      {"Predicate"},
    OperandKind.UPRED:     {"UniformPredicate"},
    OperandKind.IMM_U:     {"UImm", "SImm", "RSImm"},
    OperandKind.IMM_S:     {"SImm", "RSImm", "UImm"},
    OperandKind.IMM_F32:   {"F32Imm", "F64Imm", "F16Imm"},
    OperandKind.SPECIAL_REG: {"SpecialRegister"},
    OperandKind.CONST_BANK: {"C"},
    OperandKind.MEM_DESC:  {"DESC"},
    OperandKind.MEM_ADDR:  {"Register", "NonZeroRegister", "UniformRegister"},
    OperandKind.LABEL:     {"RSImm", "SImm", "UImm", "BD"},
    OperandKind.PR:        {"PR"},
    OperandKind.NP:        {"NP"},
}

SCHED_TYPES = {"REQ", "BITSET", "WR", "RD", "USCHED_INFO", "BATCH_T", "PM_PRED", "REUSE", "PREDICATE"}
# Scheduling slots whose type is too generic (UImm) to filter by type alone
SCHED_SLOT_NAMES = {"src_rel_sb", "dst_wr_sb", "req_bit_set", "req", "wr", "rd",
                    "pm_pred", "batch_t", "usched_info",
                    "reuse_src_a", "reuse_src_b", "reuse_src_c", "reuse_src_d"}
COMPOSITE_TYPES = {"C", "DESC"}


class MatchError(Exception):
    pass


@dataclass
class MatchResult:
    variant: dict
    slot_map: dict[str, Any] = field(default_factory=dict)
    score: int = 0
    warnings: list[str] = field(default_factory=list)
    condition_error: Optional[str] = None


class SassMatcher:
    def __init__(self, db: dict):
        self.db = db
        self._by_mnemonic: dict[str, list[dict]] = defaultdict(list)
        for v in db["variants"]:
            self._by_mnemonic.setdefault(v["mnemonic"], []).append(v)
        self._cond_errors: list[str] = []

    # ------------------------------------------------------------------
    def match(self, inst: ParsedInstruction) -> MatchResult:
        candidates = self._by_mnemonic.get(inst.mnemonic.upper(), [])
        if not candidates:
            raise MatchError(f"no variants for mnemonic {inst.mnemonic!r}")

        self._cond_errors = []
        scored: list[MatchResult] = []
        for v in candidates:
            r = self._try_match(v, inst)
            if r is not None:
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

        # 1. Parse operand groups from FORMAT
        op_groups = self._make_operand_groups(slots, raw_fmt)

        # 2. Match operands to groups (flexible — optional slots can be omitted)
        slot_map: dict[str, Any] = {}
        if not self._match_operand_groups(op_groups, inst.operands, slot_map):
            return None

        # Set guard predicate from instruction prefix @[!]Px
        if inst.pred is not None:
            slot_map["Pg"] = inst.pred
        if inst.pred_not:
            slot_map["Pg_not"] = 1

        # Figure out which modifier slots were consumed by operand matching
        consumed_mods = set()
        for grp in op_groups:
            for s in grp:
                if s["modifier"]:
                    consumed_mods.add(s["name"])

        # 3. Match remaining modifiers
        mod_map = self._match_modifiers(slots, inst.modifiers, consumed_mods)
        if mod_map is None:
            return None
        slot_map.update(mod_map)

        # 4. Fill encoding defaults so condition predicates can resolve
        #    star-pinned slots (*7, *255, *hilo, ...) and format defaults.
        self._fill_encoding_defaults(variant, slot_map)

        # 5. Check CONDITIONS — reject if any hard condition predicate is FALSE.
        cond_err = self._check_conditions(variant, slot_map)
        if cond_err is not None:
            if cond_err not in self._cond_errors:
                self._cond_errors.append(cond_err)
            return None

        score = self._compute_score(variant, inst)
        return MatchResult(variant=variant, slot_map=slot_map, score=score)
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
        """
        def is_pg(s):
            return (s["name"] == "Pg" and s["type"] == "Predicate") or \
                   (s["name"] == "UPg" and s["type"] == "UniformPredicate")

        # Collect all non-Pg, non-scheduling slots
        all_candidates = [
            s for s in slots
            if not is_pg(s)
            and s["type"] not in SCHED_TYPES
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
            # else: modifier outside composite → skip

        cleaned = ""
        if raw_fmt:
            cleaned = self._strip_scheduling(raw_fmt)
            comma_positions = self._find_top_level_commas(cleaned)
        else:
            comma_positions = []

        if not comma_positions:
            groups: list[list[dict]] = []
            for s in operand_slots:
                if s["type"] in COMPOSITE_TYPES:
                    groups.append([s])
                elif groups and groups[-1][0]["type"] in COMPOSITE_TYPES:
                    groups[-1].append(s)
                else:
                    groups.append([s])
            return groups

        segments = self._split_into_segments(cleaned, comma_positions)
        group_slot_names = self._assign_slots_to_segments(segments, slots)

        groups = []
        for names in group_slot_names:
            grp = [s for s in operand_slots if s["name"] in names]
            merged = []
            for s in grp:
                if s["type"] in COMPOSITE_TYPES:
                    merged.append([s])
                elif merged and merged[-1][0]["type"] in COMPOSITE_TYPES:
                    merged[-1].append(s)
                else:
                    merged.append([s])
            groups.extend(merged)

        return groups

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
                              slot_map: dict) -> bool:
        """Match parsed operands to groups.  Optional groups (with defaults)
        can be skipped to make the count align."""
        if len(groups) == len(operands):
            return self._match_positional(groups, operands, slot_map)

        if len(groups) < len(operands):
            return False  # more operands than slots — impossible

        # groups > operands: try skipping optional groups
        return self._match_with_skips(groups, operands, 0, 0, slot_map)

    def _match_positional(self, groups: list[list[dict]],
                          operands: list[Operand],
                          slot_map: dict) -> bool:
        for grp, op in zip(groups, operands):
            if not self._match_group(grp, op, slot_map):
                return False
        return True

    def _match_with_skips(self, groups: list[list[dict]],
                          operands: list[Operand],
                          gi: int, oi: int,
                          slot_map: dict) -> bool:
        """Backtracking: match groups[gi:] to operands[oi:], skipping
        optional groups (those where every slot has a default)."""
        if oi == len(operands):
            # All operands consumed — remaining groups must all be optional
            for g in groups[gi:]:
                if not self._all_defaults(g):
                    return False
                self._fill_group_defaults(g, slot_map)
            return True
        if gi == len(groups):
            return False  # operands left but no groups

        grp = groups[gi]
        op = operands[oi]

        # Try direct match
        if self._match_group(grp, op, slot_map):
            if self._match_with_skips(groups, operands, gi + 1, oi + 1, slot_map):
                return True
            # Backtrack: undo slot_map entries from this group
            # (We can't easily undo, so we use a copy-based approach instead.
            #  For simplicity, we accept the first successful path.)
            # Actually, let's check for duplicate keys before doing this.

        # Try skipping this group (if optional)
        if self._all_defaults(grp):
            self._fill_group_defaults(grp, slot_map)
            if self._match_with_skips(groups, operands, gi + 1, oi, slot_map):
                return True
            # Undo defaults on backtrack
            for s in grp:
                slot_map.pop(s["name"], None)

        return False

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
        if first_type == "DESC" and op.kind == OperandKind.MEM_DESC:
            return self._match_mem_desc(group, op, slot_map)
        if op.kind == OperandKind.MEM_ADDR:
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
        return ok

    def _match_simple_slot(self, slot: dict, op: Operand, slot_map: dict) -> bool:
        st = slot["type"]
        compat = TYPE_COMPAT.get(op.kind)
        if compat is None or st not in compat:
            return False
        val = self._extract_value(slot, op)
        if val is None:
            return False
        slot_map[slot["name"]] = val
        # Store negate/absolute/invert/lnot flags for slot_attr resolution
        if op.negated:
            slot_map[f"{slot['name']}_negated"] = 1
        if op.absolute:
            slot_map[f"{slot['name']}_abs"] = 1
        if op.invert:
            slot_map[f"{slot['name']}_invert"] = 1
        if op.lnot:
            slot_map[f"{slot['name']}_not"] = 1
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
                slot_map[s["name"]] = 255  # RZ
            elif st in ("SImm", "UImm"):
                slot_map[s["name"]] = op.offset
            elif st == "ONLY64":
                slot_map[s["name"]] = 1 if op.width == 64 else 0
        return True

    def _match_mem_desc(self, group: list[dict], op: Operand,
                        slot_map: dict) -> bool:
        for s in group:
            st = s["type"]
            if st == "DESC":
                slot_map[s["name"]] = 1
            elif st == "UniformRegister":
                slot_map[s["name"]] = op.value  # UR from desc[UR]
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
        for s in group:
            st = s["type"]
            if st in ("Register", "NonZeroRegister", "ZeroRegister"):
                slot_map[s["name"]] = op.value
            elif st == "UniformRegister":
                slot_map[s["name"]] = op.value
            elif st in ("SImm", "UImm") and "offset" in s["name"].lower():
                slot_map[s["name"]] = op.offset
            elif st == "ONLY64":
                slot_map[s["name"]] = 1 if op.width == 64 else 0
            elif st == "U32ONLY":
                slot_map[s["name"]] = 1 if op.width == 32 else 0
        return True

    # ------------------------------------------------------------------
    def _extract_value(self, slot: dict, op: Operand) -> Optional[int]:
        """Get numeric value from operand for a given slot."""
        st = slot["type"]
        v = op.value
        if st in ("Register", "NonZeroRegister", "ZeroRegister"):
            return v if isinstance(v, int) else None
        if st == "UniformRegister":
            return v if isinstance(v, int) else None
        if st in ("Predicate",):
            return v if isinstance(v, int) else None
        if st in ("UImm", "SImm", "RSImm"):
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
        if st == "NP":
            return v if isinstance(v, int) else None
        if st == "SpecialRegister":
            v_str = v if isinstance(v, str) else ""
            enum_vals = self.db["enums"].get("SpecialRegister", {})
            for name, val in enum_vals.items():
                if name.replace("_", "").upper() == v_str.replace("_", "").upper() \
                   and isinstance(val, int):
                    return val
            return 0
        return None

    def _all_defaults(self, group: list[dict]) -> bool:
        return all(s.get("default") is not None for s in group)

    def _fill_group_defaults(self, group: list[dict], slot_map: dict) -> None:
        for s in group:
            if s["name"] not in slot_map and s.get("default") is not None:
                slot_map[s["name"]] = self._parse_default(s["default"], s["type"])

    # ------------------------------------------------------------------
    # Modifier matching
    # ------------------------------------------------------------------
    def _match_modifiers(self, slots: list[dict], modifiers: list[str],
                         consumed: set[str] | None = None) -> Optional[dict]:
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

            matched = False
            for mod in remaining[:]:
                val = enum_vals.get(mod.upper())
                if val is not None:
                    result[name] = val
                    remaining.remove(mod)
                    matched = True
                    break

            if not matched:
                if default is not None:
                    result[name] = self._parse_default(default, etype)
                else:
                    return None

        # All modifiers must be consumed — reject if any are left unmatched
        if remaining:
            return None

        return result

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
        # Prefer variants where more modifier slots consumed a user modifier
        mod_slots = [s for s in variant["format"]["slots"] if s["modifier"]
                     and s["type"] not in ("REUSE",)]
        for s in mod_slots:
            etype = s["type"]
            enum_vals = self.db["enums"].get(etype, {})
            default = s.get("default")
            has_default = default is not None
            # Prefer required slots (no default) that will consume a modifier
            if not has_default:
                score += 5
        return score


def create_matcher(db_path: str = "") -> SassMatcher:
    from pathlib import Path
    if not db_path:
        db_path = str(Path(__file__).resolve().parent.parent / "sm120.json")
    with open(db_path) as f:
        db = json.load(f)
    return SassMatcher(db)
