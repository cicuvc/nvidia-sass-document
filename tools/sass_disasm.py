#!/usr/bin/env python3
"""SASS disassembler — 128-bit instruction → assembler-dialect SASS.

Design (solver): for a 128-bit instruction we decode every bit field back to a
modifier/operand, render SASS text in the assembler dialect, and VERIFY by
re-assembling with ``assemble_flat`` that the result reproduces the exact
(lo, hi).  Because the assembler's MODIFIER→bits maps are functions, any valid
inverse render is acceptable — we do not chase cuobjdump-exactness.  The
verification step makes round-trip the hard guarantee: if a variant/modifier
choice would encode differently, it is rejected.

Scheduling bracket `[wr:rd:{req}:stall:yield[:x6]]`:
  wr  = dst_wr_sb  (bits [112:110], 7 = no scoreboard)
  rd  = src_rel_sb (bits [115:113], 7 = none)
  req = req_bit_set (bits [121:116], bitmask)
  x6  = opex[7:5] (bits [124:122]) — batch_t, or reuse_a/b/c when the variant
        has reuse_src_* slots (reuse_a=bit0, reuse_b=bit1, reuse_c=bit2)
  stall/yield from opex[4:0] (bits [109:105]): usched = stall + 16*yield_off,
        yield = 0 iff usched >= 16, stall = usched & 0xF
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assembler import assemble_flat  # noqa: E402
from assembler.sass_cond import ConditionEvaluator  # noqa: E402

# Format slots that are schedule-bracket inputs (never rendered as operands).
SCHED_NAMES = {
    "req", "req_bit_set", "usched_info", "batch_t", "pm_pred",
    "reuse_src_a", "reuse_src_b", "reuse_src_c", "reuse_src_d",
    "rd", "wr", "src_rel_sb", "dst_wr_sb",
}

# operand slot name → size-predicate key (matches assembler matcher)
SLOT_PRED = {
    "Rd": "IDEST_SIZE", "Rd2": "IDEST2_SIZE", "Re": "ISRC_E_SIZE",
    "Ra": "ISRC_A_SIZE", "Rb": "ISRC_B_SIZE", "Rc": "ISRC_C_SIZE",
    "Rh": "ISRC_H_SIZE", "Ri": "ISRC_I_SIZE",
    "Ra_URb": "ILABEL_Ra_URb_SIZE", "Ra_URc": "ILABEL_Ra_URc_SIZE",
    "Ra_URd": "ILABEL_Ra_URd_SIZE", "URe": "ILABEL_URe_SIZE",
    "URa": "ILABEL_URa_SIZE", "URb": "ILABEL_URb_SIZE",
    "URc": "ILABEL_URc_SIZE", "URd": "ILABEL_URd_SIZE",
}

IMM_TYPES = {"UImm", "SImm", "RSImm", "F16Imm", "F32Imm", "F64Imm"}

# branch instructions whose relative target must become a #label (resolved at
# the kernel level, so per-instruction round-trip verification is skipped)
BRANCH_SET = {"BRA", "BRX", "BRXU", "BSSY", "BREAK", "BSYNC", "CALL"}

# modifier slots that are address-size constraints (implied, never printed:
# LDG/STG's input_reg_sz_64_dist, etc.)
ADDR_SIZE_SLOTS = {"input_reg_sz_64_dist", "input_reg_sz_64_bit75_dist",
                   "input_reg_sz_64_bit75"}


class SASSDisasm:
    def __init__(self, db: dict):
        self.db = db
        self.enums = db["enums"]
        self.by_op: dict[int, list[dict]] = {}
        for v in db["variants"]:
            if not v.get("is_alternate"):
                self.by_op.setdefault(v["opcode"], []).append(v)
        self.opcode_targets = [[91, 91], [11, 0]]

    # ------------------------------------------------------------------
    # bit helpers
    # ------------------------------------------------------------------
    @staticmethod
    def extract(targets, lo: int, hi: int) -> int:
        """Extract bit ranges MSB-first.  Each target [h,l] is a contiguous
        range of *width* bits ending at bit h — the integer value of bits
        l..h is obtained by shifting down by *l* (NOT by h: ``x>>h`` grabs
        bits h..h+w-1, the wrong bits)."""
        val = 0
        for h, l in targets:
            w = h - l + 1
            mask = (1 << w) - 1
            if l >= 64:
                part = (hi >> (l - 64)) & mask
            elif h < 64:
                part = (lo >> l) & mask
            else:
                # spans the 64-bit boundary: lo bits l..63, then hi bits 0..
                lo_w = 64 - l
                part = ((lo >> l) & ((1 << lo_w) - 1)) | (
                    (hi & ((1 << (w - lo_w)) - 1)) << lo_w)
            val = (val << w) | part
        return val

    def opcode_of(self, lo: int, hi: int) -> int:
        return self.extract(self.opcode_targets, lo, hi)

    # ------------------------------------------------------------------
    # encoding-field lookup
    # ------------------------------------------------------------------
    def field_for(self, v: dict, rhs: str) -> dict | None:
        for f in v["encoding"]:
            tok = f["rhs"].split(" ")[0]
            if f["rhs"] == rhs or tok == rhs:
                return f
            # star_slot (*size/*reliability): a fixed-name reference that
            # encodes the named slot's value.  star_num (*7/*1) is a literal.
            if f["rhs_kind"] == "star_slot" and tok.lstrip("*") == rhs:
                return f
        return None

    def field_by_name(self, v: dict, name: str) -> dict | None:
        for f in v["encoding"]:
            if f["name"] == name:
                return f
        return None

    def field_for_slot(self, v: dict, name: str) -> dict | None:
        """Field encoding a format slot: by field name, by rhs token, or by
        rhs substring (ConstBankAddress0(Sa_bank,Sa_offset) → Sa_offset)."""
        f = self.field_by_name(v, name)
        if f is not None:
            return f
        f = self.field_for(v, name)
        if f is not None:
            return f
        for f in v["encoding"]:
            if name in f["rhs"]:
                return f
        return None

    def slot_value(self, v: dict, fields: list, name: str):
        """fields is a list of (field, value); duplicate field NAMES (two `sz`
        fields, fmt and Rc@negate) are disambiguated by matching targets."""
        f = self.field_for(v, name)
        if f is not None:
            for ff, val in fields:
                if ff["name"] == f["name"] and ff["targets"] == f["targets"]:
                    return val
            return None
        # table_fn reverse: TABLES_mem_1(sem,sco,private) → out, inverted back
        for ff, val in fields:
            if ff["rhs_kind"] == "table_fn" and "(" in ff["rhs"]:
                tn, inner = ff["rhs"].split("(", 1)
                args = inner.rstrip(")").split(",")
                if name in args:
                    tbl = self.db["tables"].get(tn)
                    if tbl is not None and val is not None:
                        for row in tbl["rows"]:
                            if int(row["out"], 0) == val:
                                return int(row["in"][args.index(name)])
        # composite fields (e.g. ConstBankAddress0(Sa_bank,Ra_offset)) carry
        # the slot name as the encoding-field name
        for ff, val in fields:
            if ff["name"] == name:
                return val
        return None

    def slot_attr(self, v: dict, fields: list, name: str, attr: str) -> int:
        f = self.field_for(v, f"{name}@{attr}")
        if f is not None:
            for ff, val in fields:
                if ff["name"] == f["name"] and ff["targets"] == f["targets"]:
                    return val
            return 0
        # TABLES_Pnz_N(name@not, name) reverse lookup (HGMMA's UPp@not)
        if attr == "not":
            for ff, val in fields:
                if ff["rhs_kind"] == "table_fn" and f"({name}@not" in ff["rhs"]:
                    tbl = self.db["tables"].get(ff["rhs"].split("(")[0])
                    if tbl is not None and val is not None:
                        for row in tbl["rows"]:
                            if int(row["out"], 0) == val:
                                return int(row["in"][0])
        return 0

    # ------------------------------------------------------------------
    # enums / defaults
    # ------------------------------------------------------------------
    def enum_value(self, etype: str, name):
        e = self.enums.get(etype, {})
        if name is None:
            return None
        if isinstance(name, int):
            return name
        nm = str(name).split("/")[0].strip().strip('"')
        for k, val in e.items():
            if (k == nm or k.lstrip("_") == nm.lstrip("_")) and val is not None:
                return val
        return None

    def enum_name(self, etype: str, val):
        e = self.enums.get(etype, {})
        if e is None:
            return None
        if val is None:
            names = [nm for nm, v in e.items()
                     if v is not None and not nm.startswith("no")
                     and "INVALID" not in nm]
            if names:
                return names[0].lstrip("_")
            # value-less enums (RelOpt {REL: None}): "present means print"
            names = [nm for nm, v in e.items()
                     if not nm.startswith("no") and "INVALID" not in nm]
            return names[0].lstrip("_") if names else None
        for nm, v in e.items():
            if v == val and v is not None:
                if re.match(r"^E\d+M\d+$", nm):
                    continue  # fp8 formats (E8M7/E8M10/E6M9) share values with
                # BF16/TF32/F16 — prefer the human-readable non-fp8 name
                return nm.lstrip("_")
        for nm, v in e.items():
            if v == val and v is not None:
                return nm.lstrip("_")
        return None

    def default_of(self, slot: dict):
        """(default_value, always_print).  Parses 'PT"/PRINT' etc.  For enum
        types an int default is an enum NAME (sz default=32 → encoding 4)."""
        d = slot["default"]
        if d is None:
            return None, False
        if isinstance(d, int):
            enum = self.enums.get(slot["type"], {})
            for name, v in enum.items():
                if str(name) == str(d) and v is not None:
                    return v, False
            return d, False
        s = str(d)
        pprint = "/PRINT" in s
        nm = s.split("/")[0].strip().strip('"')
        if not nm:
            return None, pprint
        val = self.enum_value(slot["type"], nm)
        if val is None:
            try:
                val = int(nm, 0)
            except ValueError:
                pass
        return val, pprint

    # ------------------------------------------------------------------
    # size / register-group
    # ------------------------------------------------------------------
    def slot_map(self, v: dict, fields: list) -> dict:
        sm = {}
        for f in v["encoding"]:
            if f["rhs_kind"] == "slot":
                name = f["rhs"].split(" ")[0]
                sm[name] = fields.get(f["name"])
        return sm

    def size_of(self, v: dict, sm: dict, name: str, default: int = 32) -> int:
        preds = v.get("predicates", {})
        key = SLOT_PRED.get(name)
        if key is None or key not in preds:
            if name.startswith("Rd") or name.startswith("URd"):
                key = "IDEST_SIZE"
            elif name.startswith("UR"):
                key = "IDEST_SIZE"
            else:
                key = None
        if key in preds:
            w = ConditionEvaluator(self.db, sm).eval_int(preds[key])
            if w is not None:
                return w
        return default

    def slot_is_ureg(self, v: dict, name: str) -> bool:
        """Some Register-typed slots encode a UR in RRU/RUR variants (the
        presence of ILABEL_UR*_SIZE reveals it)."""
        base = name[2:] if name.startswith("UR") else name
        if len(base) < 2 or base in ("URb",):
            return False
        if base[0] == "R" and len(base) >= 2:
            key = "ILABEL_UR" + base[1].lower() + "_SIZE"
            if key in v.get("predicates", {}):
                return True
        return False

    def reg_text(self, base: int, width: int, ureg: bool = False) -> str:
        prefix = "UR" if ureg else "R"
        if base == (255 if ureg else 255):
            return "URZ" if ureg else "RZ"
        if width <= 32:
            return f"{prefix}{base}"
        n = width // 32
        return "{" + ",".join(f"{prefix}{base + k}" for k in range(n)) + "}"

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def render_pred(self, v: dict, fields: list) -> str:
        pg = self.slot_value(v, fields, "Pg")
        if pg is None:
            return ""
        not_ = self.slot_attr(v, fields, "Pg", "not")
        slot = {"type": "Predicate", "default": "PT"}
        default, pprint = self.default_of(slot)
        if pg == default and not not_ and not pprint:
            return ""
        name = "PT" if pg == 7 else f"P{pg}"
        return f"@{'!' if not_ else ''}{name} "

    @staticmethod
    def _field_val(fields: list, f: dict):
        for ff, val in fields:
            if ff["name"] == f["name"] and ff["targets"] == f["targets"]:
                return val
        return None

    def _pinned_by_star(self, v: dict, name: str) -> bool:
        for f in v["encoding"]:
            if f["rhs_kind"] in ("star_slot", "star_num") and name in f["rhs"]:
                return True
        return False

    def render_mods(self, v: dict, fields: list) -> str:
        out = []
        for s in v["format"]["slots"]:
            if not s["modifier"] or s["name"] in SCHED_NAMES:
                continue
            val = self.slot_value(v, fields, s["name"])
            default, pprint = self.default_of(s)
            if val is None:
                # variant-implied modifier: show only when the default doesn't
                # already fix it (IMAD.LO has default LO → hidden) and the enum
                # name is a real identifier (BAR's barmode → .SYNC; LDG's
                # input_reg_sz_64_dist → "64", hidden).
                if default is not None and not pprint:
                    continue
                if self._pinned_by_star(v, s["name"]):
                    nm = self.enum_name(s["type"], None)
                    if nm and not nm.lstrip("_").isdigit():
                        out.append("." + nm)
                    continue
                nm = self.enum_name(s["type"], None)
                if nm and not nm.lstrip("_").isdigit():
                    out.append("." + nm)
                continue
            if not pprint and default is not None and val == default:
                continue
            if s["name"] in ADDR_SIZE_SLOTS or s["name"].startswith("input_reg_sz"):
                continue
            nm = self.enum_name(s["type"], val)
            if nm:
                out.append("." + nm)
        return "".join(out)

    @staticmethod
    def _fp16_to_float(h: int) -> float:
        s = (h >> 15) & 1
        e = (h >> 10) & 0x1F
        m = h & 0x3FF
        if e == 0:
            v = m * 2.0 ** -24
        elif e == 31:
            v = float("inf") if m == 0 else float("nan")
        else:
            v = (1.0 + m / 1024.0) * (2.0 ** (e - 15))
        return -v if s else v

    @staticmethod
    def _bf16_to_float(h: int) -> float:
        import struct
        return struct.unpack(">f", struct.pack(">I", h << 16))[0]

    def render_imm(self, s: dict, val: int, v: dict) -> str:
        import struct
        t = s["type"]
        if t == "SImm" or t == "RSImm":
            f = self.field_for_slot(v, s["name"])
            width = sum(h - l + 1 for h, l in f["targets"]) if f else 32
            val = self._signed(val, width)
            scale = 1
            if f and "SCALE" in f["rhs"]:
                try:
                    scale = int(f["rhs"].split("SCALE")[1].split()[0])
                except (ValueError, IndexError):
                    pass
            off = val * scale
            if off < 0:
                return f"-0x{-off:X}"
            return f"0x{off:X}"
        if t == "F16Imm":
            # emit the fp16 value's float32 bit pattern in 0f form; the
            # assembler's convertFloatType rounds it back to the same fp16.
            fx = struct.unpack(">I", struct.pack(">f", self._fp16_to_float(val & 0xFFFF)))[0]
            return f"0f{fx:08X}"
        if t in ("F32Imm", "F64Imm"):
            f = self.field_for_slot(v, s["name"])
            width = sum(h - l + 1 for h, l in f["targets"]) if f else (
                64 if t == "F64Imm" else 32)
            if width == 16:
                # HFMA2's Sc/Sb: 16-bit fp16/bf16 slot written as a float32
                return f"0f{struct.unpack('>I', struct.pack('>f', self._fp16_to_float(val & 0xFFFF)))[0]:08X}"
            if width == 32:
                return f"0f{val & 0xFFFFFFFF:08X}"
            return f"0f{val & 0xFFFFFFFFFFFFFFFF:016X}"
        return f"0x{val:X}"

    @staticmethod
    def _signed(val: int, width: int) -> int:
        if val & (1 << (width - 1)):
            val -= 1 << width
        return val

    def render_single(self, s: dict, v: dict, fields: list, sm: dict, used: set) -> str:
        name = s["name"]
        if name in used or name in SCHED_NAMES:
            return None
        t = s["type"]
        val = self.slot_value(v, fields, name)
        default, pprint = self.default_of(s)

        not_ = self.slot_attr(v, fields, name, "not")

        if not pprint and default is not None and not not_ \
                and (val is None or val == default):
            # immediate operands render even when == default (IMAD's Sb=32
            # must not vanish or the imm→noimm variant is mismatched); other
            # operand kinds skip their defaulted value (LDC's Ra_offset=0).
            if t in ("SImm", "UImm", "RSImm") and val is not None:
                pass
            else:
                return None

        neg = self.slot_attr(v, fields, name, "negate")
        abs_ = self.slot_attr(v, fields, name, "absolute")

        if t == "C":
            bank = 0
            off = 0
            for s2 in v["format"]["slots"]:
                if s2["name"].endswith("_bank") and s2["type"] == "UImm":
                    bv = self.slot_value(v, fields, s2["name"])
                    if bv is not None:
                        bank = bv
                elif (s2["name"].endswith("_offset") or s2["name"].endswith("_addr")) \
                        and s2["type"] == "SImm":
                    ov = None
                    f2 = None
                    for f in v["encoding"]:
                        if s2["name"] in f["rhs"] and (
                                f["name"].endswith("_offset")
                                or f["name"].endswith("_addr")):
                            f2 = f
                            break
                    if f2 is not None:
                        ov = self._field_val(fields, f2)
                    if ov is not None:
                        w = sum(h - l + 1 for h, l in f2["targets"]) if f2 else 32
                        off = self._signed(ov, w)
            txt = f"c[0x{bank:x}][0x{off:x}]"
            # consume the bank/offset/address register slots that encode with
            # this constant-bank operand (LDC's Ra/Ra_offset, LDCU's URa/...)
            used.add(name)
            for s2 in v["format"]["slots"]:
                if s2["name"].endswith("_bank") or s2["name"].endswith("_offset"):
                    used.add(s2["name"])
                if s2["name"] in ("Ra", "Ra_URb", "URa", "URb", "URc") and s2["type"] in (
                        "Register", "NonZeroRegister", "UniformRegister"):
                    used.add(s2["name"])
        elif t in ("Register", "NonZeroRegister"):
            width = self.size_of(v, sm, name)
            txt = self.reg_text(val, width, ureg=self.slot_is_ureg(v, name))
        elif t == "UniformRegister":
            width = self.size_of(v, sm, name)
            txt = self.reg_text(val, width, ureg=True)
        elif t == "ZeroRegister":
            txt = "RZ"
        elif t == "Predicate":
            if val == 7:
                txt = "PT"
            else:
                txt = f"P{val}"
        elif t == "UniformPredicate":
            if val == 7:
                txt = "UPT"
            else:
                txt = f"UP{val}"
        elif t == "BITSET":
            bits = ",".join(str(i) for i in range(8) if val & (1 << i))
            txt = "{" + bits + "}"
        elif t == "SpecialRegister":
            nm = self.enum_name(t, val)
            txt = nm if nm else f"SR{val}"
        elif t == "BD":
            txt = f"B{val}"
        elif t in ("GSB0ONLY", "OPTIONAL_GSB"):
            nm = self.enum_name(t, val)
            txt = nm if nm else f"gsb{val}"
        elif t in IMM_TYPES:
            txt = self.render_imm(s, val, v)
        elif t == "Scoreboard":
            txt = f"gsb{val}"
        else:
            raise ValueError(f"unhandled operand type {t} (slot {name})")
        if neg:
            txt = "-" + txt
        if abs_:
            txt = "|" + txt + "|"
        if not_:
            txt = "!" + txt
        used.add(name)
        return txt

    def render_ops(self, v: dict, fields: list, sm: dict) -> list[str]:
        ops = []
        slots = [s for s in v["format"]["slots"] if s["name"] not in SCHED_NAMES]
        used = set()
        i = 0
        while i < len(slots):
            s = slots[i]
            name = s["name"]
            if s["modifier"] or name == "Pg" or name in used:
                i += 1
                continue
            # composite: DESC → desc[UR][R.64+off]
            if s["type"] == "DESC" or name == "memoryDescriptor":
                txt = self.render_desc(slots, i, v, fields, sm, used)
                if txt:
                    ops.append(txt)
                    i += 1
                    continue
            # composite: GMMA → gdesc[UR] (HGMMA/QMMA descriptor)
            if s["type"] == "GMMA" or name == "gdesc":
                txt = self.render_gdesc(slots, i, v, fields, sm, used)
                if txt:
                    ops.append(txt)
                    i += 1
                    continue
            if name == "Ra_URb" or name == "URa" or name == "Ra":
                # memory-address composite [R.64+off] / [UR+off] (when followed
                # by an offset slot and not part of a desc group)
                if not self._is_memaddr(v, slots, i):
                    txt = self.render_single(s, v, fields, sm, used)
                    if txt:
                        ops.append(txt)
                    i += 1
                    continue
                txt = self.render_memaddr(slots, i, v, fields, sm, used)
                if txt:
                    ops.append(txt)
                i += 1
                continue
            txt = self.render_single(s, v, fields, sm, used)
            if txt:
                ops.append(txt)
            i += 1
        return ops

    def _is_memaddr(self, v: dict, slots: list[dict], i: int) -> bool:
        s = slots[i]
        if s["type"] == "DESC":
            return False
        # a register slot is part of a memory-address composite only when a
        # *_offset slot follows it (Ra_offset etc.); an ordinary SImm operand
        # (IMAD's Sb) is NOT an address.
        j = i + 1
        while j < len(slots) and j <= i + 3:
            sj = slots[j]
            if sj["modifier"] or sj["name"] in ("Pu", "Pv", "Pp", "Pq", "Pnz"):
                j += 1
                continue
            if sj["type"] == "SImm":
                return sj["name"].endswith("_offset")
            if sj["type"] == "UniformRegister":
                j += 1
                continue
            if sj["type"] in ("Register", "NonZeroRegister",
                              "Predicate", "UImm"):
                return False
            j += 1
        return False

    def render_gdesc(self, slots, i, v, fields, sm, used):
        """gdesc[UR] composite: the GMMA slot followed by a UniformRegister
        (HGMMA/QMMA descriptor operand)."""
        # find the UniformRegister following the GMMA slot
        ureg_s = None
        for j in range(i + 1, len(slots)):
            sj = slots[j]
            if sj["modifier"] or sj["name"] in SCHED_NAMES:
                continue
            if sj["type"] == "UniformRegister":
                ureg_s = sj
                break
        if ureg_s is None:
            return None
        uval = self.slot_value(v, fields, ureg_s["name"])
        utxt = self.reg_text(uval, 32, ureg=True)
        used.add(slots[i]["name"])
        used.add(ureg_s["name"])
        return f"gdesc[{utxt}]"

    def render_desc(self, slots, i, v, fields, sm, used):
        desc_val = self.slot_value(v, fields, slots[i]["name"])
        # find UR + Reg + offset following the DESC slot
        ureg_s = reg_s = off_s = None
        for j in range(i + 1, len(slots)):
            sj = slots[j]
            if sj["modifier"] or sj["name"] in SCHED_NAMES:
                continue
            if sj["type"] == "UniformRegister" and ureg_s is None:
                ureg_s = sj
            elif sj["type"] in ("Register", "NonZeroRegister") and reg_s is None:
                reg_s = sj
            elif sj["type"] == "SImm":
                off_s = sj
                break
        if reg_s is None:
            return None
        ureg_txt = ""
        if ureg_s is not None:
            w = self.size_of(v, sm, ureg_s["name"], 32)
            uval = self.slot_value(v, fields, ureg_s["name"])
            ureg_txt = self.reg_text(uval, w, ureg=True)
        rw = self.size_of(v, sm, reg_s["name"], 64)
        rval = self.slot_value(v, fields, reg_s["name"])
        rtxt = self.reg_text(rval, rw, ureg=False)
        off = 0
        if off_s is not None:
            f = self.field_for_slot(v, off_s["name"])
            w = sum(h - l + 1 for h, l in f["targets"])
            o = self.slot_value(v, fields, off_s["name"])
            if o & (1 << (w - 1)):
                o -= 1 << w
            off = o
        used.add(slots[i]["name"])
        for s in (ureg_s, reg_s, off_s):
            if s is not None:
                used.add(s["name"])
        offtxt = f"+0x{off:X}" if off > 0 else (f"-0x{-off:X}" if off < 0 else "")
        return f"desc[{ureg_txt}][{rtxt}{offtxt}]"

    def render_memaddr(self, slots, i, v, fields, sm, used):
        reg_s = slots[i]
        off_s = ureg_s = None
        for j in range(i + 1, len(slots)):
            sj = slots[j]
            if sj["modifier"] or sj["name"] in SCHED_NAMES:
                continue
            if sj["type"] == "UniformRegister" and ureg_s is None:
                ureg_s = sj
            elif sj["type"] == "SImm":
                off_s = sj
                break
        rval = self.slot_value(v, fields, reg_s["name"])
        rw = self.size_of(v, sm, reg_s["name"], 64)
        ureg = reg_s["type"] == "UniformRegister"
        if rval == 255 and rw <= 32:
            rtxt = "URZ" if ureg else "RZ"
        else:
            rtxt = self.reg_text(rval, rw, ureg=ureg)
        off = 0
        if off_s is not None:
            f = self.field_for_slot(v, off_s["name"])
            w = sum(h - l + 1 for h, l in f["targets"])
            o = self.slot_value(v, fields, off_s["name"])
            if o & (1 << (w - 1)):
                o -= 1 << w
            off = o
        used.add(reg_s["name"])
        if ureg_s is not None:
            used.add(ureg_s["name"])
        if off_s is not None:
            used.add(off_s["name"])
        offtxt = f"+0x{off:X}" if off > 0 else (f"-0x{-off:X}" if off < 0 else "")
        base = rtxt
        if ureg_s is not None:
            uval = self.slot_value(v, fields, ureg_s["name"])
            uw = self.size_of(v, sm, ureg_s["name"], 32)
            utxt = self.reg_text(uval, uw, ureg=True)
            base = f"{rtxt}+{utxt}"
        return f"[{base}{offtxt}]"

    def render_bracket(self, v: dict, fields: list) -> str:
        wr = fields.get("dst_wr_sb", 7)
        rd = fields.get("src_rel_sb", 7)
        req = fields.get("req_bit_set", 0)
        opex = fields.get("opex", 0)
        usched = opex & 0x1F
        stall = usched & 0xF
        yield_ = 0 if usched >= 16 else 1
        x6 = opex >> 5
        reqs = ",".join(str(i) for i in range(6) if req & (1 << i))
        s = f"[{wr}:{rd}:{{{reqs}}}:{stall}:{yield_}"
        if x6:
            s += f":{x6}"
        return s + "]"

    # ------------------------------------------------------------------
    # top level
    # ------------------------------------------------------------------
    def render(self, v: dict, lo: int, hi: int) -> str:
        fields = [(f, self.extract(f["targets"], lo, hi))
                  for f in v["encoding"]]
        fd = {f["name"]: val for f, val in fields}
        sm = self.slot_map(v, fd)
        pred = self.render_pred(v, fields)
        mnem = v["mnemonic"]
        mods = self.render_mods(v, fields)
        ops = self.render_ops(v, fields, sm)
        br = self.render_bracket(v, fd)
        opstr = ", ".join(o for o in ops if o is not None)
        return f"{pred}{mnem}{mods} {opstr} ; {br}"

    def disasm(self, lo: int, hi: int):
        """Return (sass_text, class) verified to round-trip, or (None, None).

        Branch instructions (BRANCH_SET) keep a fallback render but still try
        assemble_flat first — a numeric target may assemble, letting us pick
        the right variant (BSSY vs BSSY.RECONVERGENT) before the caller turns
        the target into a #label."""
        opc = self.opcode_of(lo, hi)
        fallback = None
        for v in self.by_op.get(opc, []):
            try:
                text = self.render(v, lo, hi)
            except Exception:
                continue
            is_branch = v["mnemonic"] in BRANCH_SET
            if is_branch and fallback is None:
                fallback = (text, v["class"])
            try:
                enc = assemble_flat(text)
            except Exception:
                continue
            if enc and enc[0] == (lo, hi):
                return text, v["class"]
        return fallback if fallback else (None, None)


def load_db(path: str | Path) -> dict:
    return json.load(open(path))


if __name__ == "__main__":
    import os
    db_path = os.environ.get("SASS_DB", "sm120.json")
    d = load_db(db_path)
    ds = SASSDisasm(d)
    fails = 0
    n = 0
    for lo, hi in [tuple(int(x, 0) for x in line.split())
                   for line in sys.stdin.read().splitlines() if line.strip()]:
        n += 1
        text, cls = ds.disasm(lo, hi)
        if text is None:
            print(f"FAIL 0x{hi:016X} 0x{lo:016X}")
            fails += 1
        else:
            print(f"OK   {text}")
    print(f"\n{n - fails}/{n} decoded")
