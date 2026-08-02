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
    OperandKind.BAR:       {"BD", "CBU_STATE", "CBU_STATE_NONBAR"},
    OperandKind.SPECIAL_REG: {"SpecialRegister", "CBU_STATE", "CBU_STATE_NONBAR", "ATEXIT_PCONLY"},
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
    op_sizes: list[Optional[int]] = field(default_factory=list)


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
        used_groups = self._match_operand_groups(op_groups, inst.operands, slot_map)
        if used_groups is None:
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
        enc_names = set()
        for f in variant.get("encoding", []):
            for nm in re.findall(r"\b[A-Za-z_][A-Za-z0-9_.]*\b", f.get("rhs", "")):
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
        for grp, op in zip(used_groups, inst.operands):
            want = self._operand_expected_size(grp, variant, slot_map)
            op_sizes.append(want)
            if want is None or op.kind not in (OperandKind.REG, OperandKind.UREG):
                continue
            if op.regs is not None:
                got = len(op.regs) * 32
                if got != want:
                    self._cond_errors.append(
                        f"{inst.mnemonic}: {op.kind.name} group {op.regs} is "
                        f"{got}-bit but the matched variant expects a "
                        f"{want}-bit operand (check the .64/.128/size "
                        f"modifier)")
                    return None
            elif want > 32:
                rv = int(op.value)
                self._cond_errors.append(
                    f"{inst.mnemonic}: operand {op.value} is a single "
                    f"{op.kind.name.lower()} register but this variant "
                    f"expects a {want}-bit operand — list every register "
                    f"explicitly, e.g. {{R{rv},R{rv + 1}}}")
                return None

        # 5. Check CONDITIONS — reject if any hard condition predicate is FALSE.
        cond_err = self._check_conditions(variant, slot_map)
        if cond_err is not None:
            if cond_err not in self._cond_errors:
                self._cond_errors.append(cond_err)
            return None

        score = self._compute_score(variant, inst)
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
                              slot_map: dict) -> Optional[list[list[dict]]]:
        """Match parsed operands to groups.  Optional groups (with defaults)
        can be skipped to make the count align.  Returns the group used for
        each operand, or None on failure."""
        if len(groups) == len(operands):
            return self._match_positional(groups, operands, slot_map)

        if len(groups) < len(operands):
            return None  # more operands than slots — impossible

        # groups > operands: try skipping optional groups
        return self._match_with_skips(groups, operands, 0, 0, slot_map)

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
        if st == "BD":
            return v if isinstance(v, int) else None
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
        for s in group:
            if s["name"] not in slot_map and s.get("default") is not None:
                slot_map[s["name"]] = self._parse_default(s["default"], s["type"])

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
                for mod in remaining[:]:
                    if mod.upper() in enum_vals:
                        result[name] = enum_vals[mod.upper()]
                        remaining.remove(mod)
                        matched = True
                        break
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
