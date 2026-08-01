from __future__ import annotations
import enum
from dataclasses import dataclass, field
from typing import Optional


class OperandKind(enum.Enum):
    REG = "REG"
    UREG = "UREG"
    PRED = "PRED"
    UPRED = "UPRED"
    IMM_U = "IMM_U"
    IMM_S = "IMM_S"
    IMM_F32 = "IMM_F32"
    SPECIAL_REG = "SPECIAL_REG"
    CONST_BANK = "CONST_BANK"
    MEM_DESC = "MEM_DESC"
    MEM_ADDR = "MEM_ADDR"
    LABEL = "LABEL"
    PARAM_REF = "PARAM_REF"
    PR = "PR"
    NP = "NP"
    BAR = "BAR"


@dataclass
class ParamDecl:
    name: str
    size: int = 4
    ordinal: int = 0

    @property
    def cbank_offset(self) -> int:
        return self.ordinal * 0  # filled later by layout


@dataclass
class KernelDecl:
    name: str
    params: list[ParamDecl] = field(default_factory=list)
    attributes: dict[str, str | int] = field(default_factory=dict)
    instructions: list[ParsedInstruction] = field(default_factory=list)
    param_base: int = 0x380

    def layout_params(self) -> None:
        off = 0
        for p in self.params:
            # align to at least 4, but also to natural alignment (size up to 8)
            align = min(p.size, 8)
            align = max(align, 4)
            off = (off + align - 1) & ~(align - 1)
            p.ordinal = off
            off += p.size

    @property
    def total_param_size(self) -> int:
        if not self.params:
            return 0
        last = self.params[-1]
        return last.ordinal + last.size


@dataclass
class Operand:
    kind: OperandKind
    value: int | str | float = 0
    width: int = 32
    negated: bool = False
    absolute: bool = False
    invert: bool = False
    lnot: bool = False
    offset: int = 0
    bank: int = 0
    addr_reg: int = 0
    iswz: int | None = None      # HFMA2/HADD2 lane swizzle (ISWZ* enum value)

    @staticmethod
    def reg(name: str, width: int = 32) -> Operand:
        v = 255 if name.upper() == "RZ" else int(name[1:])
        return Operand(OperandKind.REG, v, width=width)

    @staticmethod
    def ureg(name: str, width: int = 32) -> Operand:
        v = 255 if name.upper() == "URZ" else int(name[2:])
        return Operand(OperandKind.UREG, v, width=width)

    @staticmethod
    def pred(name: str) -> Operand:
        v = 7 if name.upper() == "PT" else int(name[1:])
        return Operand(OperandKind.PRED, v)

    @staticmethod
    def upred(name: str) -> Operand:
        v = 7 if name.upper() == "UPT" else int(name[2:])
        return Operand(OperandKind.UPRED, v)

    @staticmethod
    def imm_u(value: int) -> Operand:
        return Operand(OperandKind.IMM_U, value)

    @staticmethod
    def imm_s(value: int) -> Operand:
        return Operand(OperandKind.IMM_S, value)

    @staticmethod
    def imm_f32(value: float) -> Operand:
        return Operand(OperandKind.IMM_F32, value)

    @staticmethod
    def np(value: int) -> Operand:
        """FSWZADD swizzle pattern (NP enum 0-255, rendered as P/N/Z pairs)."""
        return Operand(OperandKind.NP, value)

    @staticmethod
    def const_bank(bank: int, offset: int) -> Operand:
        return Operand(OperandKind.CONST_BANK, bank, offset=offset)

    @staticmethod
    def mem_desc(ureg: Operand) -> Operand:
        return Operand(OperandKind.MEM_DESC, ureg.value)

    @staticmethod
    def mem_addr(base: Operand, offset: int = 0) -> Operand:
        return Operand(OperandKind.MEM_ADDR, base.value, offset=offset)


@dataclass
class Sched:
    wr_sb: int = 7
    rd_sb: int = 7
    req_bits: set[int] = field(default_factory=set)
    stall: int = 1
    yield_val: int = 0
    batch_t: int = 0

    @property
    def usched_info(self) -> int:
        return self.stall + 16 if self.yield_val == 0 else self.stall

    @property
    def opex(self) -> int:
        return (self.batch_t << 5) | (self.usched_info & 0x1F)

    @staticmethod
    def default() -> Sched:
        return Sched()

    @staticmethod
    def parse(text: str) -> Sched:
        s = text.strip().strip("[]")
        parts = [p.strip() for p in s.split(":")]
        if len(parts) not in (5, 6):
            raise ValueError(
                f"scheduling bracket needs 5 or 6 fields, got {len(parts)}: {text}")
        wr_sb = int(parts[0], 0)
        rd_sb = int(parts[1], 0)
        raw = parts[2].strip("{}")
        req_bits = set(int(x.strip(), 0) for x in raw.split(",") if x.strip()) if raw else set()
        stall = int(parts[3], 0)
        yield_val = int(parts[4], 0)
        batch_t = int(parts[5], 0) if len(parts) >= 6 else 0
        return Sched(wr_sb=wr_sb, rd_sb=rd_sb, req_bits=req_bits,
                     stall=stall, yield_val=yield_val, batch_t=batch_t)


@dataclass
class ParsedInstruction:
    mnemonic: str
    modifiers: list[str] = field(default_factory=list)
    operands: list[Operand] = field(default_factory=list)
    sched: Sched = field(default_factory=Sched.default)
    label: Optional[str] = None
    pred: Optional[int] = None  # guard predicate P0-P6 (None = PT/always)
    pred_not: bool = False      # True = @!Px
