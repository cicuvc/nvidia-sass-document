"""sassdbg M4 — wtrace decoder + forward/backward state replay.

Decodes the warp-oriented trace written by wtrace.py and reconstructs
the full architectural state (per-lane GPRs, predicates, warp-uniform
URs/UPRs, sparse memory) at any point, with O(1)-ish backward stepping:

  * forward replay applies each record to a State and pushes undo info
    onto per-(lane,reg) / per-ureg / memory history stacks
  * backward stepping pops one STEP-frame of undo info: REG/PRED/UREG/UP
    restore the previous value from the history stack; MEM restores the
    MEMOLD old-bytes (ATOM/RED have no MEMOLD: the old memory value is
    the pre-instruction value of the atom's destination register, which
    the REG undo restores first)
  * the control-flow predecessor of a branch target needs no explicit
    record: the warp's STEP stream IS the execution order, so the
    reverse PC chain is just the STEP sequence walked backwards
    (divergent groups interleave in true issue order; each STEP carries
    its group's MACTIVE mask)

Usage:
    rp = WarpReplay(ik.sidecar(), trace_bytes, warp=0)
    st = rp.replay()                  # final state
    while st.step_back(): ...         # walk backwards one step at a time
"""
from __future__ import annotations

import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from sassdbg.wtrace import (                         # noqa: E402
    KIND_STEP, KIND_REG, KIND_PRED, KIND_UREG, KIND_MEM, KIND_MEMOLD,
    KIND_UP, REGION_BYTES, HDR_SIZE,
    OFF_SGPR, OFF_PRED, OFF_UP)

_KIND_NAME = {1: "STEP", 2: "REG", 3: "PRED", 4: "UREG", 5: "MEM",
              6: "MEMOLD", 7: "UP"}


@dataclass
class TRec:
    kind: int
    aux: int
    off: int                       # record offset within its section
    lanes: list[int]               # active lane indices (tag != 0)
    # decoded payloads (only lanes in .lanes are valid)
    mask: int = 0                  # STEP
    idx: int = -1                  # STEP / PRED / UP (aux) / UREG (subblock)
    reg: int = 0                   # REG
    nregs: int = 0                 # REG
    vals: list[list[int]] = field(default_factory=list)   # REG: per lane words
    size: int = 0                  # MEM*
    addrs: list[int] = field(default_factory=list)        # MEM*: per lane
    data: list[bytes] = field(default_factory=list)       # MEM*: per lane
    ureg: int = 0                  # UREG
    uval: int = 0                  # UREG / UP (warp-uniform)
    pvals: list[int] = field(default_factory=list)        # PRED: per lane

    def name(self) -> str:
        return _KIND_NAME.get(self.kind, f"?{self.kind}")


def _rec_size(kind: int, aux: int) -> int:
    if kind == KIND_STEP:
        return 0x100
    if kind == KIND_REG:
        return 0x80 + 32 * 4 * (1 << ((aux >> 8) & 3))
    if kind in (KIND_MEM, KIND_MEMOLD):
        return 0x180 + 32 * aux
    if kind == KIND_UREG:
        return 0x180
    return 0x100                   # PRED / UP


def parse_section(buf: bytes) -> list[TRec]:
    """Parse one section stream; tolerates zero gaps left by counter
    reconciliation at reconvergence."""
    out: list[TRec] = []
    off = 0
    n = len(buf)
    while off + 0x80 <= n:
        tagblk = struct.unpack_from("<32I", buf, off)
        lanes = [i for i, t in enumerate(tagblk) if t]
        if not lanes:
            off += 4
            continue
        tags = {tagblk[i] for i in lanes}
        if len(tags) != 1 or (tagblk[lanes[0]] >> 24) != 0x5A:
            off += 4               # payload mistaken for a tag: resync
            continue
        tag = tagblk[lanes[0]]
        kind, aux = (tag >> 16) & 0xFF, tag & 0xFFFF
        if kind not in _KIND_NAME:
            off += 4
            continue
        rec = TRec(kind=kind, aux=aux, off=off, lanes=lanes)
        if kind == KIND_STEP:
            masks = struct.unpack_from("<32I", buf, off + 0x80)
            rec.mask = masks[lanes[0]]
            rec.idx = aux
        elif kind == KIND_REG:
            rec.reg = aux & 0xFF
            rec.nregs = 1 << ((aux >> 8) & 3)
            w = 4 * rec.nregs
            for ln in lanes:
                rec.vals.append(list(struct.unpack_from(
                    f"<{rec.nregs}I", buf, off + 0x80 + ln * w)))
        elif kind in (KIND_MEM, KIND_MEMOLD):
            rec.size = aux
            for ln in lanes:
                rec.addrs.append(struct.unpack_from(
                    "<Q", buf, off + 0x80 + ln * 8)[0])
                rec.data.append(buf[off + 0x180 + ln * rec.size:
                                    off + 0x180 + (ln + 1) * rec.size])
        elif kind == KIND_UREG:
            idxs = struct.unpack_from("<32I", buf, off + 0x80)
            vals = struct.unpack_from("<32I", buf, off + 0x100)
            rec.idx = idxs[lanes[0]]
            rec.ureg = aux
            rec.uval = vals[lanes[0]]
        elif kind in (KIND_PRED, KIND_UP):
            rec.idx = aux
            vals = struct.unpack_from("<32I", buf, off + 0x80)
            if kind == KIND_PRED:
                rec.pvals = [vals[ln] for ln in lanes]
            else:
                rec.uval = vals[lanes[0]]
        out.append(rec)
        off += _rec_size(kind, aux)
    return out


# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------
@dataclass
class State:
    """Full architectural state of one warp at one point in time."""
    regs: list[dict[int, int]] = field(
        default_factory=lambda: [dict() for _ in range(32)])
    pr: list[int] = field(default_factory=lambda: [0] * 32)
    urs: dict[int, int] = field(default_factory=dict)
    upr: int = 0
    mem: dict[int, int] = field(default_factory=dict)   # byte map
    mask: int = 0
    pc: int = -1
    _undo: list = field(default_factory=list, repr=False)
    _pc_hist: list = field(default_factory=list, repr=False)

    def reg(self, lane: int, r: int) -> int:
        return self.regs[lane].get(r, 0)

    def mem32(self, addr: int) -> int:
        return sum(self.mem.get(addr + i, 0) << (8 * i) for i in range(4))


class WarpReplay:
    def __init__(self, sidecar: str, trace: bytes, warp: int = 0):
        self.meta = json.loads(sidecar)
        base = warp * REGION_BYTES
        region = trace[base:base + REGION_BYTES]
        streams = {
            "main": parse_section(region[HDR_SIZE:OFF_SGPR]),
            "sgpr": parse_section(region[OFF_SGPR + HDR_SIZE:OFF_PRED]),
            "pred": parse_section(region[OFF_PRED + HDR_SIZE:OFF_UP]),
            "up": parse_section(region[OFF_UP + HDR_SIZE:REGION_BYTES]),
        }
        # merge: attach aux-section records to their step (stream order
        # matches main-stream execution order per group)
        self.frames: list[list[TRec]] = []
        aux_streams = [streams["sgpr"], streams["pred"], streams["up"]]
        for rec in streams["main"]:
            if rec.kind == KIND_STEP:
                self.frames.append([rec])
                for st in aux_streams:
                    while st and st[0].idx == rec.idx:
                        self.frames[-1].append(st.pop(0))
            else:
                if not self.frames:
                    self.frames.append([])
                self.frames[-1].append(rec)

        self.steps = self.meta["steps"]

    # -- forward -------------------------------------------------------------
    def replay(self, n_frames: int | None = None,
               state: State | None = None) -> State:
        """Replay frames (resuming from a state that already has undo
        history) and return the state with step_back() support."""
        st = state or State()
        done = len(st._pc_hist)
        end = len(self.frames) if n_frames is None else min(
            n_frames, len(self.frames))
        for fr in self.frames[done:end]:
            st._pc_hist.append((st.pc, st.mask))
            undo = []
            for rec in fr:
                self._apply(rec, st, undo)
            st._undo.append(undo)
        return st

    def _apply(self, rec: TRec, st: State, undo: list) -> None:
        if rec.kind == KIND_STEP:
            st.pc = rec.idx
            st.mask = rec.mask
        elif rec.kind == KIND_REG:
            for ln, vals in zip(rec.lanes, rec.vals):
                for i, v in enumerate(vals):
                    r = rec.reg + i
                    undo.append(("reg", ln, r, st.regs[ln].get(r)))
                    st.regs[ln][r] = v
        elif rec.kind == KIND_PRED:
            for ln, v in zip(rec.lanes, rec.pvals):
                undo.append(("pr", ln, st.pr[ln]))
                st.pr[ln] = v
        elif rec.kind == KIND_UREG:
            undo.append(("ur", rec.ureg, st.urs.get(rec.ureg)))
            st.urs[rec.ureg] = rec.uval
        elif rec.kind == KIND_UP:
            undo.append(("upr", st.upr))
            st.upr = rec.uval
        elif rec.kind == KIND_MEM:
            undo.append(("mem", rec))
            for ln, addr, data in zip(rec.lanes, rec.addrs, rec.data):
                for i, b in enumerate(data):
                    st.mem[addr + i] = b

    # -- backward --------------------------------------------------------------
    def step_back(self, st: State) -> bool:
        """Undo one STEP-frame.  Returns False when at the start."""
        if not st._undo:
            return False
        undo = st._undo.pop()
        st.pc, st.mask = st._pc_hist.pop()
        # REG/PR/UR/UPR undos first so that an ATOM's restored Rd (old
        # memory value) is available when the MEM undo runs
        mems = [u for u in undo if u[0] == "mem"]
        for u in undo:
            if u[0] == "reg":
                _, ln, r, old = u
                if old is None:
                    st.regs[ln].pop(r, None)
                else:
                    st.regs[ln][r] = old
            elif u[0] == "pr":
                _, ln, old = u
                st.pr[ln] = old
            elif u[0] == "ur":
                _, ur, old = u
                if old is None:
                    st.urs.pop(ur, None)
                else:
                    st.urs[ur] = old
            elif u[0] == "upr":
                st.upr = u[1]
        for _, rec in mems:
            oldrec = self._find_memold(rec)
            for ln, addr, data in zip(rec.lanes, rec.addrs, rec.data):
                if oldrec is not None:
                    old = oldrec.data[oldrec.lanes.index(ln)] \
                        if ln in oldrec.lanes else None
                    if old is not None:
                        for i, b in enumerate(old):
                            st.mem[addr + i] = b
                        continue
                # no MEMOLD (ATOM/RED or undo disabled): drop the bytes
                for i in range(len(data)):
                    st.mem.pop(addr + i, None)
        return True

    def _find_memold(self, mem_rec: TRec) -> TRec | None:
        for fr in self.frames:
            if mem_rec in fr:
                for r in fr:
                    if r.kind == KIND_MEMOLD:
                        return r
        return None

    # -- inspection ------------------------------------------------------------
    def pc_chain(self) -> list[int]:
        """Forward execution order of instruction indices (the reverse
        PC chain is this list walked backwards)."""
        return [fr[0].idx for fr in self.frames if fr and
                fr[0].kind == KIND_STEP]
