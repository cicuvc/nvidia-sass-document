from __future__ import annotations
import re
from typing import Any

from .sass_matcher import MatchResult

MASK64 = (1 << 64) - 1

# Fallback for common special registers (parser only partially resolved the enum)
SPECIAL_REG_FALLBACK = {
    "SR_LANEID": 0, "SR_CLOCK": 1, "SR_CLOCKLO": 1,
    "SR_TID.X": 32, "SR_TID.Y": 33, "SR_TID.Z": 34,
    "SR_CTAID.X": 37, "SR_CTAID.Y": 38, "SR_CTAID.Z": 39,
    "SR_NTID": 40,
}


class EncodeError(Exception):
    pass


from .operand import Sched

class SassEncoder:
    def __init__(self, db: dict):
        self.db = db
        self._table_cache: dict[str, dict] = {}
        for name, t in db.get("tables", {}).items():
            self._table_cache[name] = t

    # ------------------------------------------------------------------
    def _apply_sched(self, sm: dict, sched: Sched) -> None:
        """Set scheduling-related slots from the Sched object."""
        sm["usched_info"] = sched.usched_info
        sm["batch_t"] = 0
        # Encode req_bits as bitmask at [121:116]
        mask = 0
        for b in sched.req_bits:
            mask |= 1 << b
        sm["req_bit_set"] = mask
        sm["src_rel_sb"] = sched.rd_sb
        sm["dst_wr_sb"] = sched.wr_sb

    # ------------------------------------------------------------------
    def encode(self, result: MatchResult, sched: Sched | None = None) -> tuple[int, int]:
        lo = 0
        hi = 0
        variant = result.variant
        sm = dict(result.slot_map)  # copy

        # Override scheduling slots from the Sched object
        self._apply_sched(sm, sched or Sched.default())

        for field in variant.get("encoding", []):
            value = self._resolve(field, sm, variant)
            if value is None:
                raise EncodeError(
                    f"cannot resolve field {field['name']} "
                    f"(rhs={field['rhs']}, kind={field['rhs_kind']})"
                )
            lo, hi = self._set_bits(lo, hi, field["targets"], field["width"], value)

        return lo & MASK64, hi & MASK64

    # ------------------------------------------------------------------
    # Field resolution
    # ------------------------------------------------------------------
    def _resolve(self, field: dict, sm: dict, variant: dict) -> int | None:
        rk = field.get("rhs_kind", "")
        rhs = field["rhs"]
        name = field["name"]

        if rk == "slot":
            val = sm.get(rhs)
            # SpecialRegister fallback for unresolved enum values
            if val == 0 or val is None:
                for sr_name, sr_val in SPECIAL_REG_FALLBACK.items():
                    for sm_key, sm_val in sm.items():
                        if isinstance(sm_val, str) and sm_val.upper() == sr_name:
                            return sr_val
            return val

        if rk == "slot_attr":
            return self._resolve_slot_attr(rhs, sm)

        if rk == "opcode":
            op = variant.get("opcode")
            return op if op is not None else 0

        if rk == "num":
            try:
                return int(rhs, 0)
            except ValueError:
                return 0

        if rk == "star_num":
            try:
                return int(rhs[1:], 0)
            except (ValueError, IndexError):
                return 0

        if rk == "star_slot":
            slot_name = rhs[1:] if rhs.startswith("*") else rhs
            return sm.get(slot_name, 0)

        if rk == "table_fn":
            return self._eval_table_fn(rhs, sm)

        if rk == "other_fn":
            return self._eval_other_fn(rhs, sm, name)

        return None

    # ------------------------------------------------------------------
    def _resolve_slot_attr(self, rhs: str, sm: dict) -> int:
        """Handle slot_attr like Pg@not, Sb@negate, Sb@absolute."""
        match = re.match(r"(\w+)@(\w+)", rhs)
        if not match:
            return 0
        slot_name, attr = match.group(1), match.group(2)
        val = sm.get(slot_name, 0)
        if attr == "not":
            return 0  # parser doesn't handle @[!]Px prefix
        if attr == "negate":
            return sm.get(f"{slot_name}_negated", 0)
        if attr == "absolute":
            return sm.get(f"{slot_name}_abs", 0)
        return 0

    # ------------------------------------------------------------------
    # Table functions
    # ------------------------------------------------------------------
    def _eval_table_fn(self, rhs: str, sm: dict) -> int:
        match = re.match(r"(\w+)\((.+)\)", rhs)
        if not match:
            return 0
        table_name = match.group(1)
        args_str = match.group(2)
        args = [a.strip() for a in args_str.split(",")]

        resolved = []
        for a in args:
            if a in sm:
                resolved.append(str(sm[a]))
            else:
                resolved.append(a)

        if table_name.startswith("TABLES_opex_"):
            return self._opex(resolved)
        if table_name.startswith("TABLES_mem_"):
            return self._lookup_table(table_name, resolved)

        # Generic table lookup
        return self._lookup_table(table_name, resolved)

    def _opex(self, args: list[str]) -> int:
        """TABLES_opex_N(batch_t, usched_info)."""
        try:
            batch_t = int(args[0])
            usched = int(args[1])
        except (ValueError, IndexError):
            return 0
        # opex = (batch_t << 5) | usched_info
        return (batch_t << 5) | (usched & 0x1F)

    def _lookup_table(self, table_name: str, args: list[str]) -> int:
        table = self._table_cache.get(table_name)
        if table is None:
            return 0
        for row in table.get("rows", []):
            if row["in"] == args:
                try:
                    return int(row["out"], 0)
                except ValueError:
                    return 0
        return 0

    # ------------------------------------------------------------------
    # Other functions
    # ------------------------------------------------------------------
    def _eval_other_fn(self, rhs: str, sm: dict, field_name: str = "") -> int:
        match = re.match(r"(\w+)\((.+)\)", rhs)
        if not match:
            return 0
        fn_name = match.group(1)
        args_str = match.group(2)
        arg_names = [a.strip() for a in args_str.split(",")]

        resolved = [str(sm.get(a, a)) for a in arg_names]

        if fn_name == "VarLatOperandEnc":
            try:
                val = int(resolved[0], 0)
            except (ValueError, IndexError):
                return 0
            return val if val < 8 else 7

        if fn_name in ("ConstBankAddress0", "ConstBankAddress2"):
            # Returns value for the specific field: bank for Sa_bank, offset for Ra_offset
            try:
                bank = int(resolved[0], 0)
                offset = int(resolved[1], 0)
            except (ValueError, IndexError):
                return 0
            if "bank" in field_name.lower():
                return bank & 0x1F
            return offset & 0xFFFF

        return 0

    # ------------------------------------------------------------------
    # Bit setting
    # ------------------------------------------------------------------
    def _set_bits(self, lo: int, hi: int, targets: list[list[int]],
                  width: int, value: int) -> tuple[int, int]:
        """Set bits in lo/hi for the given target ranges.

        targets = [[hi1, lo1], [hi2, lo2], ...]
        The value is split across ranges MSB-first.
        """
        bits_remaining = width
        for hi_bit, lo_bit in targets:
            range_width = hi_bit - lo_bit + 1
            bits_remaining -= range_width
            if bits_remaining < 0:
                range_width += bits_remaining  # truncate
                bits_remaining = 0

            sub_val = (value >> bits_remaining) & ((1 << range_width) - 1)
            lo, hi = self._set_range(lo, hi, hi_bit, lo_bit, sub_val)

        return lo, hi

    def _set_range(self, lo: int, hi: int, hi_bit: int,
                   lo_bit: int, value: int) -> tuple[int, int]:
        width = hi_bit - lo_bit + 1
        masked = value & ((1 << width) - 1)

        # bits [63:0] = lo64, bits [127:64] = hi64
        if hi_bit < 64:
            lo = self._set_bits_64(lo, lo_bit, hi_bit, masked)
        elif lo_bit >= 64:
            hi = self._set_bits_64(hi, lo_bit - 64, hi_bit - 64, masked)
        else:
            lo_width = 64 - lo_bit
            lo_mask = masked & ((1 << lo_width) - 1)
            hi_mask = (masked >> lo_width) & ((1 << (hi_bit - 63)) - 1)
            lo = self._set_bits_64(lo, lo_bit, 63, lo_mask)
            hi = self._set_bits_64(hi, 0, hi_bit - 64, hi_mask)

        return lo, hi

    @staticmethod
    def _set_bits_64(word: int, lo: int, hi: int, value: int) -> int:
        width = hi - lo + 1
        mask = ((1 << width) - 1) << lo
        word = (word & ~mask) | ((value << lo) & mask)
        return word
