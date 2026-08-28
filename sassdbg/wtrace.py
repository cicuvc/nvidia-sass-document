"""sassdbg M4 — warp-oriented trace format (instrumenter v2).

M1 (instrument.py) wrote one 32-byte record per THREAD per event.  M4
switches to WARP-unit records, per the design decision that launches are
always whole warps (blockDim multiple of 32; smaller cases simply waste
space):

  * one record = the warp's 32 lane values stored contiguously, so each
    record payload is ONE coalesced STG.E / STG.E.64 / STG.E.128 per lane
  * four sections per warp region (separate "buffers" as requested):
      MAIN  — STEP / REG (VGPR) / MEM / MEMOLD records
      SGPR  — UREG records (uniform regs, warp-uniform values)
      PRED  — PRED records (full P2R dump, 7 bits per lane)
      UP    — UP records (UP2UR dump of the uniform predicate file)
  * every record starts with a 32-lane TAG subblock (lanes x 4B):
    active lanes all store 0x5A000000 | kind<<16 | aux; inactive lanes
    leave zeros.  Self-describing -> predicated-off records simply
    vanish and the decoder resyncs on the next tag.
  * STEP records carry BMOV MACTIVE (the executing group's lane mask),
    which both identifies valid payload lanes and tracks divergence.

DIVERGENCE-SAFE STREAM ALLOCATION
---------------------------------
A per-lane register byte counter CANNOT survive divergence: split groups
execute different numbers of records, their counters drift apart, and at
reconvergence a REDUX.MAX over the *active* group only reconciles the
group with itself — the two groups then write overlapping records and
the stream is torn (verified experiment: divergent if/else lost the
branch-body records entirely).

Instead, every instrumented instruction CLAIMS its frame bytes with an
atomic RMW on a per-section header counter in the trace region itself:

    P2R  Rprsave, PR                     ; save kernel predicates
    BMOV Rmact, MACTIVE                  ; this group's lane mask
    FLO.U32 Rflo, PT, Rmact              ; one fixed lane of the group
    ISETP.EQ.AND P6, PT, Rlane, Rflo, PT ; (stall 13: pred->ATOMG)
    @P6 ATOMG.E.ADD.STRONG.GPU PT, Rslot, desc[..][hdr], Rbytes
    SHFL.IDX PT, Rslot, Rslot, Rflo, Rflo; broadcast claimed base
    R2P  PR, Rprsave                     ; restore kernel predicates

The single-lane atomic is a real read-modify-write, so concurrent
groups can never observe a stale counter; claim order == issue order
across divergent groups (the STEP stream IS the control-flow history —
the predecessor PC of a branch-target step is the previous STEP, and
reverse execution walks the stream backwards).  Section headers are the
first word of each section; record data starts at section_base+0x80.

Tracer registers R224-R245 + UR59,UR60,UR61 are reserved; they are
deliberately disjoint from the M3 debugger's R246-R253 so a kernel can
be traced AND breakpointed at the same time.  UR60/61 hold the default
cache descriptor in both.

Record layouts (per warp, per executed instruction instance):
  STEP   tag(lanes*4, aux=inst idx) ; mask(lanes*4)  = BMOV MACTIVE
  REG    tag(lanes*4, aux=reg|nlog2<<8) ; payload lanes*width (4/8/16B)
  MEM    tag(lanes*4, aux=size)     ; addr lanes*8 ; data lanes*size
  MEMOLD same layout as MEM (data = pre-instruction old value)
  UREG   tag(lanes*4, aux=ureg) ; idx(lanes*4) ; payload lanes*4
  PRED   tag(lanes*4, aux=inst idx) ; payload lanes*4 (P2R PR dump)
  UP     tag(lanes*4, aux=inst idx) ; payload lanes*4 (UP2UR UPR dump)

Limitations: grid=(1,) only (warp id = tid.x>>5); kernels must not use
R224-R245 / UR59-UR61 (M3 additionally reserves R246-R253).
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
KIND_STEP, KIND_REG, KIND_PRED, KIND_UREG, KIND_MEM, KIND_MEMOLD, KIND_UP = \
    1, 2, 3, 4, 5, 6, 7
TAG_BASE = 0x5A000000        # magic byte at [31:24]; kind [23:16]; aux [15:0]

# per-warp region layout: one 32-bit claim counter at each section base,
# record data from section_base+HDR_SIZE
HDR_SIZE = 0x80
SEC_MAIN = 0x180000          # 1.5 MiB
SEC_SGPR = 0x040000          # 256 KiB
SEC_PRED = 0x040000
SEC_UP = 0x010000            # 64 KiB
REGION_BYTES = SEC_MAIN + SEC_SGPR + SEC_PRED + SEC_UP
OFF_SGPR = SEC_MAIN
OFF_PRED = SEC_MAIN + SEC_SGPR
OFF_UP = SEC_MAIN + SEC_SGPR + SEC_PRED
SEC_OFF = {"main": 0, "sgpr": OFF_SGPR, "pred": OFF_PRED, "up": OFF_UP}
SEC_ORDER = ("main", "sgpr", "pred", "up")

# tracer register map (R224-R245; M3 debugger owns R246-R253)
RB_ = ("R224", "R225")       # warp region base
RLANE = "R226"
RMACT = "R227"               # BMOV MACTIVE
RFLO = "R228"                # FLO result: a fixed active lane of the group
RADD = "R230"                # claim addend (frame bytes)
RPRS = "R232"                # P2R/R2P predicate save
RTAG = "R235"
RBASE = ("R236", "R237")     # record base pair
RA_ = ("R238", "R239")       # scratch pair A / MEMOLD staging lo
RC_ = ("R240", "R241")       # scratch pair B / MEMOLD staging hi
RSLOT = {"main": "R229", "sgpr": "R243", "pred": "R244", "up": "R245"}
# scoreboard the SHFL of each section claims (FLO uses SB3, freed before
# the first SHFL because the ISETP reqs it; ATOMGs use SB5, each freed by
# its own SHFL before the next section's ATOMG claims it again)
SLOT_SB = {"main": 4, "sgpr": 3, "pred": 2, "up": 1}

TRACER_REG_LO = 224          # R224..R245 reserved
TRACER_URS = (59, 60, 61)

MEM_WRITE_MNEMONICS = {"STG", "STS", "STL", "ATOM", "ATOMG", "RED", "REDG"}
NO_TRAIL_MNEMONICS = {"EXIT", "RET", "BRA", "BRX", "BRXU", "JMP", "JMPX",
                      "KILL", "JMX", "JMXU"}
PRED_DEST_SLOTS = {"Pu", "Pv", "Pd"}
PRED_WRITE_MNEMONICS = {"R2P"}
UPRED_WRITE_MNEMONICS = {"UISETP", "R2UR"}   # conservative: dump UPR after these
_SZ_TO_BYTES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 8, 6: 16}
_SZ_TO_MOD = {1: ".U8", 2: ".U16", 4: "", 8: ".64", 16: ".128"}


@dataclass
class WRecord:
    kind: int
    aux: int = 0
    reg: int | None = None         # REG: GPR base
    nregs: int = 1                 # REG: 1/2/4 (aux = reg | nlog2<<8)
    ureg: int | None = None        # UREG
    step_idx: int = -1             # UREG: owning step (idx subblock)
    addr_reg: int | None = None    # MEM*: address base register
    addr_off: int = 0
    addr_64: bool = True
    data_reg: int | None = None    # MEM: data base register
    size: int = 4                  # MEM*: bytes
    desc_ur: int | None = None     # MEMOLD: desc UR pair of the original
    is_shared: bool = False
    guarded: bool = False          # emitted under the instruction's guard

    def tag(self) -> int:
        return TAG_BASE | (self.kind << 16) | (self.aux & 0xFFFF)

    def section(self) -> str:
        return {KIND_STEP: "main", KIND_REG: "main", KIND_MEM: "main",
                KIND_MEMOLD: "main", KIND_UREG: "sgpr", KIND_PRED: "pred",
                KIND_UP: "up"}[self.kind]

    def bytes(self) -> int:
        if self.kind == KIND_STEP:
            return 0x100
        if self.kind == KIND_REG:
            return 0x80 + 32 * (4 * self.nregs)
        if self.kind in (KIND_MEM, KIND_MEMOLD):
            return 0x180 + 32 * self.size
        if self.kind == KIND_UREG:
            return 0x180           # tag + idx subblock + payload
        return 0x100               # PRED / UP


@dataclass
class WStep:
    idx: int
    text: str
    records: list[WRecord] = field(default_factory=list)
    pre_records: list[WRecord] = field(default_factory=list)


@dataclass
class WInstrumentedKernel:
    source: str
    steps: list[WStep]
    kernel_name: str
    region_bytes: int = REGION_BYTES

    def sidecar(self) -> str:
        return json.dumps({
            "format": "wtrace2",
            "kernel": self.kernel_name,
            "region_bytes": self.region_bytes,
            "hdr_size": HDR_SIZE,
            "sections": {"main": 0, "sgpr": OFF_SGPR, "pred": OFF_PRED,
                         "up": OFF_UP},
            "steps": [
                {"idx": s.idx, "text": s.text,
                 "records": [
                     {"kind": r.kind, "aux": r.aux, "nregs": r.nregs,
                      "size": r.size, "guarded": r.guarded,
                      "step_idx": r.step_idx}
                     for r in s.records],
                 "pre_records": [
                     {"kind": r.kind, "aux": r.aux, "size": r.size,
                      "guarded": r.guarded}
                     for r in s.pre_records]}
                for s in self.steps],
        }, indent=1)


# ---------------------------------------------------------------------------
# write-set analysis (same model as instrument.py)
# ---------------------------------------------------------------------------
class _Analyzer:
    def __init__(self, db: dict):
        self.matcher = SassMatcher(db)

    @staticmethod
    def _lit_size(pred) -> int | None:
        try:
            return int(pred)
        except (TypeError, ValueError):
            return None

    def analyze(self, inst, guard: str, step_idx: int) -> tuple[list[WRecord], list[WRecord]]:
        mn = inst.mnemonic.upper()
        try:
            m = self.matcher.match(inst)
        except MatchError:
            return [], []
        v = m.variant
        slots = {s["name"]: s["type"] for s in v["format"]["slots"]}
        sm = m.slot_map
        pre: list[WRecord] = []
        post: list[WRecord] = []
        g = bool(guard)

        if "Rd" in slots and slots["Rd"] not in ("ZeroRegister",):
            rd = sm.get("Rd")
            if rd is not None and rd != 255:
                nbits = self._lit_size(v.get("predicates", {}).get("IDEST_SIZE"))
                if nbits is None and inst.operands:
                    nbits = inst.operands[0].width
                nregs = max(1, (nbits or 32) // 32)
                nlog = {1: 0, 2: 1, 4: 2}[nregs]
                post.append(WRecord(KIND_REG, aux=rd | (nlog << 8), reg=rd,
                                    nregs=nregs, guarded=g))

        if "URd" in slots:
            urd = sm.get("URd")
            if urd is not None and urd != 63:
                nbits = self._lit_size(v.get("predicates", {}).get("IDEST_SIZE"))
                if nbits is None and inst.operands:
                    nbits = inst.operands[0].width
                for i in range(max(1, (nbits or 32) // 32)):
                    post.append(WRecord(KIND_UREG, aux=urd + i,
                                        ureg=urd + i, step_idx=step_idx,
                                        guarded=g))

        wrote_pred = any(
            s in slots and sm.get(s) not in (None, 7) for s in PRED_DEST_SLOTS
        ) or mn in PRED_WRITE_MNEMONICS
        if wrote_pred:
            post.append(WRecord(KIND_PRED, aux=step_idx, guarded=g))

        if mn in UPRED_WRITE_MNEMONICS:
            post.append(WRecord(KIND_UP, aux=step_idx, guarded=g))

        if mn in MEM_WRITE_MNEMONICS and "256" not in v["class"]:
            sz = _SZ_TO_BYTES.get(sm.get("sz", 4), 4)
            addr_64 = bool(sm.get("e", 0)) or any(
                s["type"] == "ONLY64" for s in v["format"]["slots"])
            ra = sm.get("Ra")
            rec = WRecord(
                KIND_MEM, aux=sz,
                addr_reg=ra if ra not in (None, 255) else None,
                addr_off=sm.get("Ra_offset", 0) or 0,
                addr_64=addr_64, data_reg=sm.get("Rb"), size=sz,
                is_shared=mn == "STS", guarded=g,
            )
            post.append(rec)
            if mn in ("STG", "STS", "STL") and rec.addr_reg is not None:
                pre.append(WRecord(
                    KIND_MEMOLD, aux=sz, addr_reg=rec.addr_reg,
                    addr_off=rec.addr_off, addr_64=rec.addr_64, size=sz,
                    desc_ur=sm.get("Ra_URc"), is_shared=rec.is_shared,
                    guarded=g))
        return pre, post


# ---------------------------------------------------------------------------
# code emitter
# ---------------------------------------------------------------------------
_B_ALU = "[7:7:{}:8:0]"                 # fixed-latency, generous stall
_B_DATA = "[7:7:{0,1,2,3,4,5}:8:0]"     # stores: wait all scoreboards
_B_LDG = "[5:7:{}:8:0]"                 # staging load claims SB5
_B_REDUX = "[5:7:{}:8:0]"               # UP2UR (URF writer) claims SB5
_B_URRD = "[7:7:{5}:8:0]"               # MOV Rd, UR59 waits on SB5
_B_DRAIN = "[7:7:{0,1,2,3,4,5}:4:0]"    # NOP: drain before claiming SB5


def _addr(rec_base: tuple[str, str], lane_mul: int, g: str) -> str:
    """scratch A = rec_base + lane*lane_mul"""
    return (f"{g}IMAD.WIDE.U32 {{{RA_[0]},{RA_[1]}}}, {RLANE}, {lane_mul}, "
            f"{{{rec_base[0]},{rec_base[1]}}};{_B_ALU}")


def _emit_claims(sections: dict[str, int]) -> list[str]:
    """Claim frame space in every section this instruction touches.

    sections: {section_name: total_record_bytes}.  One atomic RMW per
    section on the section's header word, single-lane + SHFL broadcast,
    so divergent groups allocate disjoint, issue-ordered frames."""
    out = [
        f"P2R {RPRS}, PR;{_B_ALU}",
        f"BMOV {RMACT}, MACTIVE;{_B_ALU}",
        f"FLO.U32 {RFLO}, PT, {RMACT};[3:7:{{}}:5:1]",
        f"ISETP.EQ.AND P6, PT, {RLANE}, {RFLO}, PT;[7:7:{{3}}:13:1]",
    ]
    for sec in SEC_ORDER:
        nbytes = sections.get(sec)
        if not nbytes:
            continue
        slot, sb = RSLOT[sec], SLOT_SB[sec]
        out += [
            f"MOV32I {RADD}, 0x{nbytes:x};[7:7:{{}}:4:0]",
            f"MOV32I {RA_[0]}, 0x{SEC_OFF[sec]:x};[7:7:{{}}:4:0]",
            f"IMAD.WIDE.U32 {{{RA_[0]},{RA_[1]}}}, {RA_[0]}, 0x1, "
            f"{{{RB_[0]},{RB_[1]}}};{_B_ALU}",
            f"@P6 ATOMG.E.ADD.STRONG.GPU PT, {slot}, "
            f"desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}], {RADD};"
            f"[5:7:{{}}:8:1]",
            f"SHFL.IDX PT, {slot}, {slot}, {RFLO}, {RFLO};"
            f"[{sb}:7:{{5}}:5:1]",
        ]
    out.append(f"R2P PR, {RPRS};[7:7:{{}}:13:1]")
    return out


def _rec_base(rec: WRecord, local_off: int) -> list[str]:
    """record base pair = region base + section data + claimed slot."""
    sec = rec.section()
    rel = SEC_OFF[sec] + HDR_SIZE + local_off
    sb = SLOT_SB[sec]
    return [
        f"IADD3 {RA_[0]}, {RSLOT[sec]}, 0x{rel:x}, RZ;[7:7:{{{sb}}}:8:0]",
        f"IMAD.WIDE.U32 {{{RBASE[0]},{RBASE[1]}}}, {RA_[0]}, 0x1, "
        f"{{{RB_[0]},{RB_[1]}}};{_B_ALU}",
    ]


def _emit_record(rec: WRecord, g: str, local_off: int) -> list[str]:
    """Emit one warp-collective record; g = '' or '@P0 ' guard."""
    out = [*_rec_base(rec, local_off),
           f"{g}MOV32I {RTAG}, 0x{rec.tag():x};{_B_ALU}",
           _addr(RBASE, 4, g),
           f"{g}STG.E desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}], "
           f"{RTAG};{_B_DATA}"]

    if rec.kind == KIND_STEP:
        out += [
            f"{g}MOV {RTAG}, {RMACT};{_B_ALU}",
            _addr(RBASE, 4, g),
            f"{g}STG.E desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}+0x80], "
            f"{RTAG};{_B_DATA}",
        ]
    elif rec.kind == KIND_REG:
        r, w = rec.reg, 4 * rec.nregs
        out.append(_addr(RBASE, w, g))
        if rec.nregs == 1:
            out.append(f"{g}STG.E desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}"
                       f"+0x80], R{r};{_B_DATA}")
        elif rec.nregs == 2:
            out.append(f"{g}STG.E.64 desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}"
                       f"+0x80], {{R{r},R{r + 1}}};{_B_DATA}")
        else:
            out.append(f"{g}STG.E.128 desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}"
                       f"+0x80], {{R{r},R{r + 1},R{r + 2},R{r + 3}}};{_B_DATA}")
    elif rec.kind == KIND_UREG:
        # idx subblock lets the decoder associate the record with its
        # step even when guarded-off instances vanish from the stream
        out += [
            f"{g}MOV32I {RTAG}, 0x{rec.step_idx:x};{_B_ALU}",
            _addr(RBASE, 4, g),
            f"{g}STG.E desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}+0x80], "
            f"{RTAG};{_B_DATA}",
            f"{g}MOV {RTAG}, UR{rec.ureg};{_B_ALU}",
            _addr(RBASE, 4, g),
            f"{g}STG.E desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}+0x100], "
            f"{RTAG};{_B_DATA}",
        ]
    elif rec.kind == KIND_PRED:
        out += [
            f"{g}P2R {RTAG}, PR;{_B_ALU}",
            _addr(RBASE, 4, g),
            f"{g}STG.E desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}+0x80], "
            f"{RTAG};{_B_DATA}",
        ]
    elif rec.kind == KIND_UP:
        out += [
            f"{g}NOP;{_B_DRAIN}",
            f"{g}UP2UR {URX}, UPR, URZ, 0x0;{_B_REDUX}",
            f"{g}MOV {RTAG}, {URX};{_B_URRD}",
            _addr(RBASE, 4, g),
            f"{g}STG.E desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}+0x80], "
            f"{RTAG};{_B_DATA}",
        ]
    elif rec.kind == KIND_MEM:
        # addr subblock (lanes*8) then data subblock (lanes*size)
        if rec.addr_reg is not None:
            out.append(_addr(RBASE, 8, g))
            if rec.addr_64:
                out.append(
                    f"{g}STG.E.64 desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}"
                    f"+0x80], {{R{rec.addr_reg},R{rec.addr_reg + 1}}};{_B_DATA}")
            else:
                out.append(
                    f"{g}IMAD.WIDE.U32 {{{RC_[0]},{RC_[1]}}}, "
                    f"R{rec.addr_reg}, 1, RZ;{_B_ALU}")
                out.append(
                    f"{g}STG.E.64 desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}"
                    f"+0x80], {{{RC_[0]},{RC_[1]}}};{_B_DATA}")
        if rec.data_reg is not None:
            d = rec.data_reg
            # data address goes into RBASE itself (base no longer needed)
            out.append(f"{g}IMAD.WIDE.U32 {{{RBASE[0]},{RBASE[1]}}}, {RLANE}, "
                       f"{rec.size}, {{{RBASE[0]},{RBASE[1]}}};{_B_ALU}")
            mod = _SZ_TO_MOD.get(rec.size, "")
            if rec.size <= 4:
                out.append(f"{g}STG.E{mod} desc[{{UR60,UR61}}]"
                           f"[{{{RBASE[0]},{RBASE[1]}}}+0x180], R{d};{_B_DATA}")
            elif rec.size == 8:
                out.append(f"{g}STG.E.64 desc[{{UR60,UR61}}]"
                           f"[{{{RBASE[0]},{RBASE[1]}}}+0x180], "
                           f"{{R{d},R{d + 1}}};{_B_DATA}")
            else:
                out.append(f"{g}STG.E.128 desc[{{UR60,UR61}}]"
                           f"[{{{RBASE[0]},{RBASE[1]}}}+0x180], "
                           f"{{R{d},R{d + 1},R{d + 2},R{d + 3}}};{_B_DATA}")
    return out


def _emit_memold(rec: WRecord, g: str, local_off: int) -> list[str]:
    """MEMOLD = record tag+addr, pre-load old value, store it as data."""
    assert rec.addr_reg is not None
    base = (f"[{{R{rec.addr_reg},R{rec.addr_reg + 1}}}+0x{rec.addr_off:x}]"
            if rec.addr_64 else f"[R{rec.addr_reg}+0x{rec.addr_off:x}]")
    if not rec.is_shared and rec.desc_ur is not None:
        base = f"desc[{{UR{rec.desc_ur},UR{rec.desc_ur + 1}}}]{base}"
    op = "LDS" if rec.is_shared else "LDG.E"
    mod = _SZ_TO_MOD.get(rec.size, "")
    out = [*_rec_base(rec, local_off),
           f"{g}MOV32I {RTAG}, 0x{rec.tag():x};{_B_ALU}",
           _addr(RBASE, 4, g),
           f"{g}STG.E desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}], "
           f"{RTAG};{_B_DATA}",
           _addr(RBASE, 8, g)]
    if rec.addr_64:
        out.append(f"{g}STG.E.64 desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}"
                   f"+0x80], {{R{rec.addr_reg},R{rec.addr_reg + 1}}};{_B_DATA}")
    else:
        out.append(f"{g}IMAD.WIDE.U32 {{{RC_[0]},{RC_[1]}}}, "
                   f"R{rec.addr_reg}, 1, RZ;{_B_ALU}")
        out.append(f"{g}STG.E.64 desc[{{UR60,UR61}}][{{{RA_[0]},{RA_[1]}}}"
                   f"+0x80], {{{RC_[0]},{RC_[1]}}};{_B_DATA}")
    if rec.size <= 4:
        out.append(f"{g}{op}{mod} {RA_[0]}, {base};{_B_LDG}")
    elif rec.size == 8:
        out.append(f"{g}{op}{mod} {{{RA_[0]},{RA_[1]}}}, {base};{_B_LDG}")
    else:
        out.append(f"{g}{op}{mod} {{{RA_[0]},{RA_[1]},{RC_[0]},{RC_[1]}}}, "
                   f"{base};{_B_LDG}")
    # data subblock: data address into RBASE (base no longer needed)
    out.append(f"{g}IMAD.WIDE.U32 {{{RBASE[0]},{RBASE[1]}}}, {RLANE}, "
               f"{rec.size}, {{{RBASE[0]},{RBASE[1]}}};{_B_ALU}")
    if rec.size <= 4:
        out.append(f"{g}STG.E{mod} desc[{{UR60,UR61}}]"
                   f"[{{{RBASE[0]},{RBASE[1]}}}+0x180], {RA_[0]};{_B_DATA}")
    elif rec.size == 8:
        out.append(f"{g}STG.E.64 desc[{{UR60,UR61}}]"
                   f"[{{{RBASE[0]},{RBASE[1]}}}+0x180], "
                   f"{{{RA_[0]},{RA_[1]}}};{_B_DATA}")
    else:
        out.append(f"{g}STG.E.128 desc[{{UR60,UR61}}]"
                   f"[{{{RBASE[0]},{RBASE[1]}}}+0x180], "
                   f"{{{RA_[0]},{RA_[1]},{RC_[0]},{RC_[1]}}};{_B_DATA}")
    return out


URX = "UR59"                 # UP2UR staging
URC = ("UR60", "UR61")       # default cache descriptor


# ---------------------------------------------------------------------------
# top-level instrumenter
# ---------------------------------------------------------------------------
def instrument_warp(source: str, *, undo: bool = True) -> WInstrumentedKernel:
    """Instrument the (single) kernel in `source` (assembler dialect)
    with the warp-oriented M4 trace format."""
    db = json.load(open(_REPO / "sm120.json"))
    analyzer = _Analyzer(db)

    decl = Parser(Lexer(source).tokenize()).parse_kernel()
    src_lines = source.splitlines()

    for inst in decl.instructions:
        if inst.mnemonic == "_label_":
            continue
        for op in inst.operands:
            regs = op.regs or ([op.value] if isinstance(op.value, int) else [])
            if op.kind.name == "REG" and any(TRACER_REG_LO <= r < 246
                                             for r in regs):
                raise ValueError(f"line {inst.line}: kernel uses R{regs[0]} "
                                 f"(tracer reserves R224-R245)")
            if op.kind.name == "UREG" and any(r in TRACER_URS for r in regs):
                raise ValueError(f"line {inst.line}: kernel uses UR{regs[0]} "
                                 f"(tracer reserves UR59-UR61)")

    body: list[str] = [
        "LDCU.64 {UR60,UR61}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "LDC.64 {R224,R225}, #param(__trace);[1:7:{}:8:0]",
        "S2R R226, SR_LANEID;[0:7:{}:8:0]",
        "S2R R235, SR_TID.X;[0:7:{}:8:0]",
        "SHF.R.U32 R235, R235, 0x5, RZ;[7:7:{0}:8:0]",
        f"IMAD.WIDE.U32 {{R224,R225}}, R235, 0x{REGION_BYTES:x}, "
        "{R224,R225};[7:7:{}:8:0]",
    ]
    steps: list[WStep] = []
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

        pre, post = analyzer.analyze(inst, guard, idx)
        mn = inst.mnemonic.upper()
        trail = [] if (mn in NO_TRAIL_MNEMONICS and inst.pred is None) else post
        steps.append(WStep(idx=idx, text=text, records=post,
                           pre_records=pre if undo else []))

        # frame layout: STEP first, then pre- and post-records, each
        # section claimed as one atomic frame
        frame: list[tuple[str, WRecord]] = [("", WRecord(KIND_STEP, aux=idx))]
        if undo:
            frame += [(guard, r) for r in pre]
        frame += [(guard, r) for r in trail]
        sections: dict[str, int] = {}
        for _g, r in frame:
            sections[r.section()] = sections.get(r.section(), 0) + r.bytes()

        body += _emit_claims(sections)
        # emit: STEP + pre-records BEFORE the instruction, post after
        local: dict[str, int] = {}
        emitted_pre: list[str] = []
        emitted_post: list[str] = []
        for g, r in frame:
            sec = r.section()
            off = local.get(sec, 0)
            local[sec] = off + r.bytes()
            if r.kind == KIND_STEP or r.kind == KIND_MEMOLD:
                emitted_pre += (_emit_memold(r, g, off)
                                if r.kind == KIND_MEMOLD
                                else _emit_record(r, g, off))
            else:
                emitted_post += _emit_record(r, g, off)
        body += emitted_pre
        body.append(text)
        body += emitted_post
        idx += 1

    params = ", ".join([f"{p.name}<{p.size}>" for p in decl.params] +
                       ["__trace<8>"])
    lines = [f"#fn {decl.name}({params}) {{"]
    for k, v in decl.attributes.items():
        lines.append(f"    #pragma {k}({v})")
    lines += ["    " + b for b in body]
    lines.append("}")
    return WInstrumentedKernel("\n".join(lines), steps, decl.name)
