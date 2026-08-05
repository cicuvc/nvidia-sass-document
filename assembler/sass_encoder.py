from __future__ import annotations
import re
from typing import Any

from .sass_matcher import MatchResult

MASK64 = (1 << 64) - 1


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
        sm["usched_info"] = sched.usched_info
        # The 6th bracket element is a 3-bit field overloaded as
        # batch_t (classes without reusable sources) OR the reuse bitfield
        # {reuse_a=bit0, reuse_b=bit1, reuse_c=bit2} (classes with reusable
        # register sources).  In the reuse context batch_t is conceptually 0.
        has_reuse = any(k in sm for k in
                        ("reuse_src_a", "reuse_src_b", "reuse_src_c", "reuse_src_d"))
        if has_reuse:
            sm["batch_t"] = 0
            if "reuse_src_a" in sm:
                sm["reuse_src_a"] = (sched.batch_t >> 0) & 1
            if "reuse_src_b" in sm:
                sm["reuse_src_b"] = (sched.batch_t >> 1) & 1
            if "reuse_src_c" in sm:
                sm["reuse_src_c"] = (sched.batch_t >> 2) & 1
        else:
            sm["batch_t"] = sched.batch_t
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

        # Authoritative condition check with the real scheduling word applied.
        # The matcher deferred TABLES_opex legality to here.
        failures = self._check_conditions(variant, sm)
        if failures:
            err, msg = failures[0]
            raise EncodeError(
                f"{err}: {msg}" if msg else f"{err}"
            )

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
    def _check_conditions(self, variant: dict, sm: dict) -> list[tuple[str, str]]:
        """Return [(error_type, message), ...] for every FALSE condition
        (all error types, including TABLES_opex legality)."""
        from .sass_cond import ConditionEvaluator
        return ConditionEvaluator(self.db, sm).check_variant(variant)

    # ------------------------------------------------------------------
    # Field resolution
    # ------------------------------------------------------------------
    def _resolve(self, field: dict, sm: dict, variant: dict) -> int | None:
        rk = field.get("rhs_kind", "")
        rhs = field["rhs"]
        name = field["name"]

        if rk == "slot":
            return self._resolve_slot(rhs, sm)

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
            # If the slot name looks like a number, treat it as a literal
            try:
                return int(slot_name, 0)
            except ValueError:
                pass
            return sm.get(slot_name, 0)

        if rk == "table_fn":
            return self._eval_table_fn(rhs, sm)

        if rk == "other_fn":
            return self._eval_other_fn(rhs, sm, name)

        return None

    # ------------------------------------------------------------------
    def _resolve_slot(self, rhs: str, sm: dict) -> int | None:
        """Resolve a FORMAT slot to its numeric value, applying any
        `` SCALE <n>`` suffix on the ENCODING RHS (e.g. ``Sa SCALE 4``).

        ``SCALE`` is a *decode* scale: logical value = field value * scale,
        so encoding divides the logical (byte) value by the scale.
        """
        m = re.match(r"^(.+?)(?:\s+SCALE\s+(\d+))?$", rhs)
        name = (m.group(1) or rhs).strip()
        scale = int(m.group(2)) if m and m.group(2) else 1
        v = sm.get(name)
        if v is None:
            return None
        return v // scale if scale != 1 else v

    # ------------------------------------------------------------------
    def _resolve_slot_attr(self, rhs: str, sm: dict) -> int:
        """Handle slot_attr like Pg@not, Sb@negate, or Sb convertFloatType(...)."""
        # Simple case: slot@attr
        m = re.match(r"(\w+)@(\w+)$", rhs)
        if m:
            slot_name, attr = m.group(1), m.group(2)
            if attr == "not":
                return sm.get(f"{slot_name}_not", 0)
            if attr == "negate":
                return sm.get(f"{slot_name}_negated", 0)
            if attr == "absolute":
                return sm.get(f"{slot_name}_abs", 0)
            if attr == "invert":
                return sm.get(f"{slot_name}_invert", 0)
            return 0

        # Complex case: slot convertFloatType(condition, fmt_true, fmt_false)
        m = re.match(r"(\w+)\s+(\w+)\((.*)\)$", rhs)
        if m:
            slot_name, fn_name, args_str = m.group(1), m.group(2), m.group(3)
            if fn_name == "convertFloatType":
                return self._eval_convert_float(slot_name, args_str, sm)

        return 0

    def _eval_convert_float(self, slot_name: str, args: str,
                            sm: dict) -> int:
        """Evaluate convertFloatType(modifier_check, fmt_true, fmt_false).

        Args: 'modifier == `ENUM_TYPE@VALUE, fmt_true, fmt_false'
        Returns 16-bit FP16 or BF16 value.
        """
        import struct

        val = sm.get(slot_name, 0)
        if isinstance(val, float):
            f32 = val
        else:
            # Already a 32-bit integer representing the float bits
            f32 = struct.unpack(">f", struct.pack(">I", val & 0xFFFFFFFF))[0]

        # Parse condition: modifier_name == `ENUM_TYPE@VALUE
        cond_match = re.match(
            r"(\w+)\s*==\s*`(\w+)@(\w+)", args)
        if not cond_match:
            return self._float_to_fp16(f32)  # default to FP16

        mod_name = cond_match.group(1)
        enum_type = cond_match.group(2)
        enum_value = cond_match.group(3)

        # Lookup enum value
        enum_vals = self.db["enums"].get(enum_type, {})
        target_val = enum_vals.get(enum_value)
        if target_val is None:
            return self._float_to_fp16(f32)

        # nvcc evidence (HFMA2 ofmt=F16_V2 constant 0x0003 = fp16 1.78e-07,
        # sm120 mini kernel): the convertFloatType condition is `X==BF16_*`,
        # so X==target ⇒ the constant is BF16; otherwise FP16.  An
        # unconditional `1==1` (F2I/FRND/...) means plain FP16.
        mod_val = sm.get(mod_name)
        if mod_name == "1":
            return self._float_to_fp16(f32)
        if mod_val == target_val:
            return self._float_to_bf16(f32)
        else:
            return self._float_to_fp16(f32)

    @staticmethod
    def _float_to_fp16(f: float) -> int:
        import struct
        try:
            return struct.unpack(">H", struct.pack(">e", f))[0]
        except struct.error:
            # Manual conversion if >e not available
            bits = struct.unpack(">I", struct.pack(">f", f))[0]
            sign = (bits >> 31) & 1
            exp = (bits >> 23) & 0xFF
            mant = bits & 0x7FFFFF
            if exp == 0xFF:
                return (sign << 15) | 0x7C00 | (1 if mant else 0)
            if exp == 0:
                return sign << 15
            new_exp = exp - 127 + 15
            if new_exp >= 31:
                return (sign << 15) | 0x7C00
            if new_exp <= 0:
                return sign << 15
            return (sign << 15) | (new_exp << 10) | (mant >> 13)

    @staticmethod
    def _float_to_bf16(f: float) -> int:
        import struct
        bits = struct.unpack(">I", struct.pack(">f", f))[0]
        return bits >> 16

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
        names = []
        for a in args:
            names.append(a)
            if a in sm:
                resolved.append(str(sm[a]))
            elif re.match(r"^\w+@\w+$", a):
                resolved.append(str(self._resolve_slot_attr(a, sm)))
            else:
                resolved.append(a)

        if table_name.startswith("TABLES_opex_"):
            return self._opex(names, resolved)
        if table_name.startswith("TABLES_mem_"):
            return self._lookup_table(table_name, resolved)

        # Generic table lookup
        return self._lookup_table(table_name, resolved)

    def _opex(self, names: list[str], args: list[str]) -> int:
        """TABLES_opex_N(batch_t, usched_info[, reuse_src_*...]).

        Reuse flags pack into the SAME [124:122] bits that carry batch_t when
        there is no reuse: reuse_src_a -> opex[5] (+32, bit 122), b -> opex[6]
        (+64, bit 123), c -> opex[7] (+128, bit 124).  In the reuse context
        batch_t is always 0.  With no reuse: opex = (batch_t << 5) | usched.
        """
        try:
            batch_t = int(args[0])
            usched = int(args[1])
        except (ValueError, IndexError):
            return 0
        bit = {"reuse_src_a": 5, "reuse_src_b": 6, "reuse_src_c": 7,
               "reuse_src_d": 8}
        reuse = 0
        for n, a in zip(names[2:], args[2:]):
            if n in bit:
                try:
                    reuse |= int(a) << bit[n]
                except (ValueError, IndexError):
                    pass
        if reuse:
            return (usched & 0x1F) | reuse
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
