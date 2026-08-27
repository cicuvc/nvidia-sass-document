from __future__ import annotations
import enum
from dataclasses import dataclass, field
from typing import Optional

from . import arch


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
    SB = "SB"
    BITSET = "BITSET"


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
    param_base: int = field(default_factory=lambda: arch.current().param_base)

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
    addr_ureg: int | None = None   # LDS/STS uniform variant: [RZ + URb + off]
    iswz: int | None = None      # HFMA2/HADD2 lane swizzle (ISWZ* enum value)
    regs: list[int] | None = None  # explicit multi-reg list {Ra,Rb}/{Ra,Rb,Rc,Rd};
                                   # value == regs[0], width == len(regs)*32

    @staticmethod
    def reg(name: str, width: int = 32) -> Operand:
        v = 255 if name.upper() == "RZ" else int(name[1:])
        return Operand(OperandKind.REG, v, width=width)

    @staticmethod
    def ureg(name: str, width: int = 32) -> Operand:
        # UniformRegister.URZ == 63 in the ISA enum (GPR RZ uses 255; the
        # 6-bit field truncation previously masked this).  Matching the enum
        # matters because CLASS conditions compare URd==URZ numerically.
        v = 63 if name.upper() == "URZ" else int(name[2:])
        return Operand(OperandKind.UREG, v, width=width)

    @staticmethod
    def reg_group(regs: list[int], uniform: bool = False) -> Operand:
        """Explicit multi-register operand {Ra,Rb} / {Ra,Rb,Rc,Rd}.

        ``value`` = first register (drives the encoded base slot), ``width`` =
        len(regs)*32 (64/128).  The caller must ensure the list is same-class,
        consecutive and in-range; this helper just derives the derived fields.
        """
        kind = OperandKind.UREG if uniform else OperandKind.REG
        return Operand(kind, regs[0], width=len(regs) * 32, regs=list(regs))

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
    def bar(name: str) -> Operand:
        """BAR/BD bar register B0..B15."""
        return Operand(OperandKind.BAR, int(name[1:]))

    @staticmethod
    def sb(name: str) -> Operand:
        """DEPBAR scoreboard SB0..SB5."""
        return Operand(OperandKind.SB, int(name[2:]))

    @staticmethod
    def bitset(bit_indices: list[int]) -> Operand:
        """DEPBAR scoreboard_list bitset {0,2,4} -> bitmask."""
        mask = 0
        for b in bit_indices:
            mask |= 1 << b
        return Operand(OperandKind.BITSET, mask)

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
        # Hardware scoreboards are SB0..SB5.  wr/rd of 7 means "no
        # scoreboard"; 6 does not exist and must not be used.  req_bits is a
        # 6-bit BITSET, so bits beyond 5 cannot be encoded.
        for name, v in (("wr", wr_sb), ("rd", rd_sb)):
            if v == 6:
                raise ValueError(
                    f"scoreboard {name}=6 does not exist (valid: 0-5, 7=off)")
        for b in sorted(req_bits):
            if b > 5:
                raise ValueError(
                    f"req scoreboard bit {b} out of range (only SB0..SB5 exist)")
        return Sched(wr_sb=wr_sb, rd_sb=rd_sb, req_bits=req_bits,
                     stall=stall, yield_val=yield_val, batch_t=batch_t)


@dataclass
class ParsedInstruction:
    mnemonic: str
    modifiers: list[str] = field(default_factory=list)
    operands: list[Operand] = field(default_factory=list)
    sched: Sched = field(default_factory=Sched.default)
    label: Optional[str] = None
    line: int = 0          # source line number (for diagnostics)
    pred: Optional[int] = None  # guard predicate P0-P6 (None = PT/always)
    pred_not: bool = False      # True = @!Px
    pred_uniform: bool = False  # True = @UPx / @!UPx (uniform predicate)
