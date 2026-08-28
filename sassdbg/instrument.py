"""sassdbg — dynamic SASS instrumentation built on the repo assembler.

M1: full-state tracing of assembler-dialect kernels.

Instead of dumping all 256 GPRs after every instruction, we exploit the fact
that an instruction's *architectural write set* is statically known from its
matched encoding variant (slot map + IDEST_SIZE): each traced instruction only
stores the state it actually changes — destination GPRs (with width), written
predicates (one P2R snapshot), written uniform regs, and memory writes
(address + data, optional pre-instruction old-value load for undo/reverse
execution).  The host replays the per-step records from a known initial state
to reconstruct the full architectural state at any step.

Trace buffer record format (32 bytes, fixed):
    +0   u32  header = kind(8) | aux(24)
    +4   u32  reserved (0)
    +8   u64  address (MEM / MEMOLD only)
    +16  4xu32 data payload
kinds: 1=STEP (aux=instr idx), 2=REG (aux=reg idx), 3=PRED (d0=P2R),
       4=UREG (aux=ureg idx), 5=MEM (aux=size bytes), 6=MEMOLD (aux=size)

Reserved tracer registers (kernels must not touch them, checked):
    R240-R243  undo staging (LDG destination for MEMOLD)
    R248,R249  per-thread trace base pointer
    R250       32-bit write-offset counter within the thread region
    R251       scratch (header constant / P2R / UR read / MEMOLD 32-bit)
    R252,R253  address scratch (IMAD.WIDE dest)
    UR60,UR61  global cache descriptor for the tracer's own STG/LDG
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler.sass_parser import Lexer, Parser            # noqa: E402
from assembler.sass_matcher import SassMatcher, MatchError  # noqa: E402

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
REC_SIZE = 32
KIND_STEP, KIND_REG, KIND_PRED, KIND_UREG, KIND_MEM, KIND_MEMOLD = 1, 2, 3, 4, 5, 6

TRACER_REG_LO = 240          # R240..R254 reserved
TRACER_URS = (60, 61)        # UR60/UR61 reserved
PER_THREAD_BYTES = 1 << 20   # 1 MiB trace per thread (records wrap nowhere; sized generously)

MEM_WRITE_MNEMONICS = {"STG", "STS", "STL", "ATOM", "ATOMG", "RED", "REDG"}
NO_TRAIL_MNEMONICS = {"EXIT", "RET", "BRA", "BRX", "BRXU", "JMP", "JMPX", "KILL"}
# predicate-destination slot names (Pg=guard, Pp/Pr=ISETP bop sources)
PRED_DEST_SLOTS = {"Pu", "Pv", "Pd"}
PRED_WRITE_MNEMONICS = {"R2P"}   # writes the whole PR file

_SZ_TO_BYTES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 8, 6: 16}
_SZ_TO_MOD = {1: ".U8", 2: ".U16", 4: "", 8: ".64", 16: ".128"}


@dataclass
class Record:
    kind: int
    aux: int = 0
    # payload generation hints (used by the code emitter)
    reg: int | None = None         # REG: GPR base index
    nregs: int = 1                 # REG: consecutive count (1/2/4)
    ureg: int | None = None        # UREG
    addr_reg: int | None = None    # MEM*: address base register
    addr_ureg: int | None = None   # MEM*: descriptor/uniform UR (if any)
    addr_off: int = 0              # MEM*: immediate offset
    addr_64: bool = True           # MEM*: 64-bit address form (.E)
    data_reg: int | None = None    # MEM: data base register
    size: int = 4                  # MEM*: access size in bytes
    desc_ur: int | None = None     # MEMOLD: desc[URx] used by the original
    is_shared: bool = False        # MEM*: STS/LDS (shared memory)

    def header(self) -> int:
        return self.kind | (self.aux << 8)


@dataclass
class Step:
    idx: int
    text: str                       # original source line
    records: list[Record] = field(default_factory=list)
    pre_records: list[Record] = field(default_factory=list)  # MEMOLD etc.


@dataclass
class InstrumentedKernel:
    source: str
    steps: list[Step]
    kernel_name: str
    per_thread_bytes: int = PER_THREAD_BYTES

    def sidecar(self) -> str:
        return json.dumps({
            "kernel": self.kernel_name,
            "per_thread_bytes": self.per_thread_bytes,
            "steps": [
                {
                    "idx": s.idx,
                    "text": s.text,
                    "records": [
                        {
                            "kind": r.kind, "aux": r.aux, "reg": r.reg,
                            "nregs": r.nregs, "ureg": r.ureg,
                            "addr_off": r.addr_off, "size": r.size,
                            "is_shared": r.is_shared,
                        }
                        for r in ([Record(KIND_STEP, s.idx)] + s.pre_records + s.records)
                    ],
                }
                for s in self.steps
            ],
        }, indent=1)


# ---------------------------------------------------------------------------
# write-set analysis
# ---------------------------------------------------------------------------
class _Analyzer:
    def __init__(self, db: dict):
        self.matcher = SassMatcher(db)

    @staticmethod
    def _lit_size(pred: str | None) -> int | None:
        if pred is None:
            return None
        try:
            return int(pred)
        except (TypeError, ValueError):
            return None

    def analyze(self, inst) -> tuple[list[Record], list[Record]]:
        """Return (pre_records, post_records) for one parsed instruction."""
        mn = inst.mnemonic.upper()
        try:
            m = self.matcher.match(inst)
        except MatchError:
            return [], []          # unknown — still gets a STEP marker
        v = m.variant
        slots = {s["name"]: s["type"] for s in v["format"]["slots"]}
        sm = m.slot_map
        pre: list[Record] = []
        post: list[Record] = []

        # ---- GPR destination ----
        if "Rd" in slots and slots["Rd"] not in ("ZeroRegister",):
            rd = sm.get("Rd")
            if rd is not None and rd != 255:
                nbits = self._lit_size(v.get("predicates", {}).get("IDEST_SIZE"))
                if nbits is None and inst.operands:
                    nbits = inst.operands[0].width
                nregs = max(1, (nbits or 32) // 32)
                post.append(Record(KIND_REG, aux=rd, reg=rd, nregs=nregs))

        # ---- uniform destination ----
        if "URd" in slots:
            urd = sm.get("URd")
            if urd is not None and urd != 63:
                nbits = self._lit_size(v.get("predicates", {}).get("IDEST_SIZE"))
                if nbits is None and inst.operands:
                    nbits = inst.operands[0].width
                post.append(Record(KIND_UREG, aux=urd, ureg=urd,
                                   nregs=max(1, (nbits or 32) // 32)))

        # ---- predicate destinations ----
        wrote_pred = any(
            s in slots and sm.get(s) not in (None, 7) for s in PRED_DEST_SLOTS
        ) or mn in PRED_WRITE_MNEMONICS
        if wrote_pred:
            post.append(Record(KIND_PRED))

        # ---- memory writes ----
        if mn in MEM_WRITE_MNEMONICS:
            sz = _SZ_TO_BYTES.get(sm.get("sz", 4), 4)
            is256 = sm.get("sz") == 1 and "256" in str(slots.get("sz", ""))
            is256 = "256" in v["class"]
            # 64-bit address?  .E covers the generic-pointer forms; shared/
            # uniform-address classes pin it via an ONLY64 slot instead.
            addr_64 = bool(sm.get("e", 0)) or any(
                s["type"] == "ONLY64" for s in v["format"]["slots"])
            ra = sm.get("Ra")
            rb = sm.get("Rb")
            rec = Record(
                KIND_MEM, aux=sz,
                addr_reg=ra if ra != 255 else None,
                addr_ureg=sm.get("Ra_URc"),
                addr_off=sm.get("Ra_offset", 0) or 0,
                addr_64=addr_64,
                data_reg=rb,
                size=sz,
                is_shared=mn in ("STS",),
            )
            if not is256:
                post.append(rec)
                # undo (reverse execution): old value.  ATOM returns the old
                # value in Rd (already covered by the REG record); plain
                # stores need a pre-instruction load.
                if mn in ("STG", "STS", "STL"):
                    old = Record(
                        KIND_MEMOLD, aux=sz,
                        addr_reg=rec.addr_reg, addr_ureg=rec.addr_ureg,
                        addr_off=rec.addr_off, addr_64=rec.addr_64,
                        size=sz, desc_ur=rec.addr_ureg,
                        is_shared=rec.is_shared,
                    )
                    pre.append(old)
        return pre, post


# ---------------------------------------------------------------------------
# code emitter
# ---------------------------------------------------------------------------
_BRK_DATA = "[7:7:{0,1,2,3,4,5}:8:0]"   # STG: waits for every scoreboard,
                                         # no SB claims (wr/rd=7) -> no
                                         # anti-dep retarget hazards
_BRK_ALU = "[7:7:{}:8:0]"               # fixed-latency, generous stall
_BRK_LDG = "[5:7:{0,1,2,3,4}:8:0]"      # undo load -> wr SB5


def _emit_record_lines(rec: Record, guard: str) -> list[str]:
    """SASS lines realising one 32-byte record.  `guard` is '' or '@P0 ' etc."""
    g = guard
    out = [
        f"{g}MOV32I R251, 0x{rec.header():x};{_BRK_ALU}",
        f"{g}IMAD.WIDE.U32 {{R252,R253}}, R250, 1, {{R248,R249}};{_BRK_ALU}",
        f"{g}STG.E desc[{{UR60,UR61}}][{{R252,R253}}+0x0], R251;{_BRK_DATA}",
    ]
    stg = lambda off, src: (f"{g}STG.E desc[{{UR60,UR61}}][{{R252,R253}}+0x{off:x}], "
                            f"{src};{_BRK_DATA}")
    if rec.kind == KIND_REG:
        assert rec.reg is not None
        r = rec.reg
        if rec.nregs == 1:
            out.append(stg(0x10, f"R{r}"))
        elif rec.nregs == 2:
            out.append(f"{g}STG.E.64 desc[{{UR60,UR61}}][{{R252,R253}}+0x10], "
                       f"{{R{r},R{r + 1}}};{_BRK_DATA}")
        elif rec.nregs == 4:
            out.append(f"{g}STG.E.128 desc[{{UR60,UR61}}][{{R252,R253}}+0x10], "
                       f"{{R{r},R{r + 1},R{r + 2},R{r + 3}}};{_BRK_DATA}")
    elif rec.kind == KIND_PRED:
        out.append(f"{g}P2R R251, PR;{_BRK_ALU}")
        out.append(stg(0x10, "R251"))
    elif rec.kind == KIND_UREG:
        assert rec.ureg is not None
        for i in range(rec.nregs):
            out.append(f"{g}MOV R251, UR{rec.ureg + i};{_BRK_ALU}")
            out.append(stg(0x10 + 4 * i, "R251"))
    elif rec.kind in (KIND_MEM, KIND_MEMOLD):
        # address
        if rec.addr_reg is not None:
            if rec.addr_64:
                out.append(f"{g}STG.E.64 desc[{{UR60,UR61}}][{{R252,R253}}+0x8], "
                           f"{{R{rec.addr_reg},R{rec.addr_reg + 1}}};{_BRK_DATA}")
            else:
                out.append(stg(0x8, f"R{rec.addr_reg}"))
                out.append(stg(0xc, "RZ"))      # keep the Q field deterministic
        elif rec.addr_ureg is not None:
            out.append(f"{g}MOV R251, UR{rec.addr_ureg};{_BRK_ALU}")
            out.append(stg(0x8, "R251"))
            out.append(stg(0xc, "RZ"))
        # data payload
        if rec.kind == KIND_MEM and rec.data_reg is not None:
            mod = _SZ_TO_MOD.get(rec.size, "")
            if rec.size <= 4:
                out.append(stg(0x10, f"R{rec.data_reg}"))
            elif rec.size == 8:
                out.append(f"{g}STG.E.64 desc[{{UR60,UR61}}][{{R252,R253}}+0x10], "
                           f"{{R{rec.data_reg},R{rec.data_reg + 1}}};{_BRK_DATA}")
            elif rec.size == 16:
                d = rec.data_reg
                out.append(f"{g}STG.E.128 desc[{{UR60,UR61}}][{{R252,R253}}+0x10], "
                           f"{{R{d},R{d + 1},R{d + 2},R{d + 3}}};{_BRK_DATA}")
    out.append(f"{g}IADD3 R250, R250, 0x{REC_SIZE:x}, RZ;{_BRK_ALU}")
    return out


def _emit_memold_load(rec: Record, guard: str) -> tuple[str, str] | None:
    """Pre-instruction load of the memory about to be overwritten.

    Returns (load_line, payload_store_line) or None if unsupported."""
    g = guard
    mod = _SZ_TO_MOD.get(rec.size, "")
    op = "LDS" if rec.is_shared else "LDG.E"
    if rec.addr_reg is None:
        return None                       # UR-based address: skip undo (M1)
    base = (f"[{{R{rec.addr_reg},R{rec.addr_reg + 1}}}+0x{rec.addr_off:x}]"
            if rec.addr_64 else f"[R{rec.addr_reg}+0x{rec.addr_off:x}]")
    if not rec.is_shared and rec.desc_ur is not None:
        base = f"desc[{{UR{rec.desc_ur},UR{rec.desc_ur + 1}}}]{base}"
    if rec.size <= 4:
        return (f"{g}{op}{mod} R240, {base};{_BRK_LDG}",
                f"{g}STG.E desc[{{UR60,UR61}}][{{R252,R253}}+0x10], R240;{_BRK_DATA}")
    if rec.size == 8:
        return (f"{g}{op}{mod} {{R240,R241}}, {base};{_BRK_LDG}",
                f"{g}STG.E.64 desc[{{UR60,UR61}}][{{R252,R253}}+0x10], "
                f"{{R240,R241}};{_BRK_DATA}")
    if rec.size == 16:
        return (f"{g}{op}{mod} {{R240,R241,R242,R243}}, {base};{_BRK_LDG}",
                f"{g}STG.E.128 desc[{{UR60,UR61}}][{{R252,R253}}+0x10], "
                f"{{R240,R241,R242,R243}};{_BRK_DATA}")
    return None


# ---------------------------------------------------------------------------
# top-level instrumenter
# ---------------------------------------------------------------------------
def instrument(source: str, *, undo: bool = True,
               per_thread: int = PER_THREAD_BYTES) -> InstrumentedKernel:
    """Instrument the (single) kernel in `source` (assembler dialect)."""
    db = json.load(open(_REPO / "sm120.json"))
    analyzer = _Analyzer(db)

    decl = Parser(Lexer(source).tokenize()).parse_kernel()
    src_lines = source.splitlines()

    # reserved-register check
    for inst in decl.instructions:
        if inst.mnemonic == "_label_":
            continue
        for op in inst.operands:
            regs = op.regs or ([op.value] if isinstance(op.value, int) else [])
            if op.kind.name == "REG" and any(TRACER_REG_LO <= r < 255 for r in regs):
                raise ValueError(f"line {inst.line}: kernel uses R{regs[0]}+ which "
                                 f"collides with tracer registers (R240-R254)")
            if op.kind.name == "UREG" and any(r in TRACER_URS for r in regs):
                raise ValueError(f"line {inst.line}: kernel uses UR{regs[0]} which "
                                 f"collides with tracer registers (UR60/UR61)")

    body: list[str] = []
    steps: list[Step] = []

    # ---- prologue ----
    body += [
        "LDCU.64 {UR60,UR61}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "LDC.64 {R248,R249}, #param(__trace);[1:7:{}:1:0]",
        "S2R R250, SR_TID.X;[0:7:{}:5:1]",
        f"IMAD.WIDE.U32 {{R248,R249}}, R250, 0x{per_thread:x}, {{R248,R249}};[7:7:{{0,1}}:8:0]",
        "MOV32I R250, 0x0;[7:7:{}:8:0]",
    ]

    idx = 0
    for inst in decl.instructions:
        if inst.mnemonic == "_label_":
            body.append(f"#def_label({inst.label})")
            continue
        text = src_lines[inst.line - 1].strip() if 0 < inst.line <= len(src_lines) \
            else inst.mnemonic
        guard = ""
        if inst.pred is not None:
            guard = f"@{'!' if inst.pred_not else ''}P{inst.pred} "

        pre, post = analyzer.analyze(inst)
        step = Step(idx=idx, text=text, records=post,
                    pre_records=pre if undo else [])
        steps.append(step)

        # STEP marker
        body += _emit_record_lines(Record(KIND_STEP, aux=idx), "")
        # pre-instruction records (MEMOLD): load first, then the record
        for rec in step.pre_records:
            ldg = _emit_memold_load(rec, guard)
            rec_lines = _emit_record_lines(rec, guard)
            if ldg is not None:
                ld_line, st_line = ldg
                body.append(ld_line)            # LDG old value -> staging
                body += rec_lines[:-1]          # header+addr+header store(+addr payload)
                body.append(st_line)            # data payload store
                body.append(rec_lines[-1])      # offset advance
            else:
                body += rec_lines
        # the original instruction, verbatim
        body.append(text)
        # post-instruction records
        mn = inst.mnemonic.upper()
        if not (mn in NO_TRAIL_MNEMONICS and inst.pred is None):
            for rec in post:
                body += _emit_record_lines(rec, guard)
        idx += 1

    # ---- reassemble source ----
    params = ", ".join([f"{p.name}<{p.size}>" for p in decl.params] +
                       ["__trace<8>"])
    lines = [f"#fn {decl.name}({params}) {{"]
    for k, v in decl.attributes.items():
        lines.append(f"    #pragma {k}({v})")
    lines += ["    " + b for b in body]
    lines.append("}")
    return InstrumentedKernel("\n".join(lines), steps, decl.name, per_thread)
