"""sassdbg M5 — source-level single-stepping on top of the M3 debugger.

Stepping model: the warp is parked at a breakpoint (M3 slot).  To
advance one source instruction, the stepper

  1. computes the static successor set of the parked instruction
     (`next_pcs`: fall-through, plus the label target for a predicated
     branch; unconditional BRA has only its target),
  2. arms breakpoints on all of them (while the warp is still parked —
     patching other lines is safe, and the slot's hardened IVALL on the
     resume path makes the patches visible),
  3. resumes; whichever breakpoint hits is the path taken,
  4. disarms the survivors.

The hit sequence therefore IS the executed control-flow path (in
original-source instruction indices).

CFG rules (dialect source parsed with assembler.sass_parser):
  BRA #label           -> {target} (+ fall-through when predicated)
  BSSY Bn, #label      -> {fall-through}   (pushes, continues linearly)
  BSYNC Bn             -> {matching BSSY's label}  (nested stack scan)
  EXIT / RET / KILL    -> {}               (thread ends)
  BRX / JMX / CALL     -> unsupported (dynamic target) — step() raises
  anything else        -> {fall-through}

Known limits:
  * self-referential steps (next_pcs contains the parked index itself,
    i.e. a 1-instruction loop) arm AFTER resume — a best-effort race,
    since resume() restores the site word; tight loops are replay-
    buffered anyway (probe exp4).  Prefer breaking at the loop top.
  * divergence: a breakpoint parks the GROUP that hits it; other groups
    keep running.  Stepping is group-agnostic (the hit sequence may
    interleave groups).  Keep stepped regions warp-uniform for now.
  * reverse-from-breakpoint is a composition, not a class: run a
    wtrace-instrumented + debugger-injected kernel
    (inject_debugger(..., allow_cdesc_urs=True)), break, then feed the
    trace region to reverse.WarpReplay — the replayed state is the
    pre-breakpoint architectural state; step_back() walks backwards.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler.sass_parser import Lexer, Parser            # noqa: E402
from sassdbg.patch import Debugger, Breakpoint             # noqa: E402

# branch instructions whose LABEL operand is the taken target
_BR_LABEL = {"BRA", "BSSY", "CALL"}
_TERMINAL = {"EXIT", "RET", "KILL"}
_INDIRECT = {"BRX", "BRXU", "JMX", "JMXU", "JMP", "JMPX"}


@dataclass
class CfgInst:
    idx: int
    mnemonic: str
    predicated: bool
    label: str | None          # LABEL operand of a branch, if any


class Cfg:
    """Static control flow of one dialect-source kernel, in original
    instruction indices (labels are not instructions)."""

    def __init__(self, source: str):
        decl = Parser(Lexer(source).tokenize()).parse_kernel()
        self.insts: list[CfgInst] = []
        self.labels: dict[str, int] = {}
        for inst in decl.instructions:
            if inst.mnemonic == "_label_":
                self.labels[inst.label] = len(self.insts)
                continue
            lbl = next((op.value for op in inst.operands
                        if op.kind.name == "LABEL"), None)
            self.insts.append(CfgInst(
                idx=len(self.insts), mnemonic=inst.mnemonic.upper(),
                predicated=inst.pred is not None, label=lbl))
        # BSYNC -> matching BSSY target (nearest unmatched BSSY, nested)
        self._bsync_target: dict[int, int] = {}
        stack: list[tuple[int, int]] = []      # (bssy idx, target idx)
        for ci in self.insts:
            if ci.mnemonic == "BSSY" and ci.label is not None:
                stack.append((ci.idx, self.labels[ci.label]))
            elif ci.mnemonic == "BSYNC":
                if stack:
                    self._bsync_target[ci.idx] = stack.pop()[1]

    def target(self, label: str) -> int:
        return self.labels[label]

    def next_pcs(self, idx: int) -> list[int]:
        """Static successors of instruction idx (original indices)."""
        ci = self.insts[idx]
        mn = ci.mnemonic
        if mn in _INDIRECT or (mn == "CALL"):
            raise ValueError(f"step over dynamic/indirect {mn} at {idx} "
                             f"is unsupported")
        if mn in _TERMINAL:
            return []
        fall = idx + 1 if idx + 1 < len(self.insts) else None
        if mn == "BRA" and ci.label is not None:
            tgt = self.labels[ci.label]
            if ci.predicated:
                return [x for x in (fall, tgt) if x is not None]
            return [tgt]
        if mn == "BSYNC":
            tgt = self._bsync_target.get(idx, fall)
            return [tgt] if tgt is not None else []
        # BSSY / CALL-as-fallthrough / ordinary instructions
        return [fall] if fall is not None else []


class Stepper:
    """Single-step a dialect-source kernel via M3 breakpoints.

    Usage:
        st = Stepper(source)
        st.launch(args)                       # parks at the gate
        bp = st.run_to_entry()                # break before inst 0
        while bp is not None:
            ... inspect bp.orig_index ...
            bp = st.step(bp)
        st.dbg.wait_done()
    """

    def __init__(self, source: str, func: str | None = None,
                 max_bps: int = 32):
        self.cfg = Cfg(source)
        self.dbg = Debugger(source, func=func, max_bps=max_bps)
        self.path: list[int] = []

    def launch(self, args: list, grid=(1,), block=(32,)) -> None:
        self.dbg.launch(args, grid=grid, block=block)
        self.dbg.wait_base()

    def run_to_entry(self, timeout: float = 30.0) -> Breakpoint:
        bp = self.dbg.arm(0)
        self.dbg.release()
        hit = self.dbg.wait_hit(timeout)
        self.path.append(hit.orig_index)
        return hit

    def step(self, bp: Breakpoint, timeout: float = 30.0
             ) -> Breakpoint | None:
        """Execute exactly the parked instruction; returns the next hit
        (None when the instruction was terminal — kernel finished)."""
        idx = bp.orig_index
        nxt = self.cfg.next_pcs(idx)
        if not nxt:
            self.dbg.resume(bp)
            return None
        # arm before resume (safe: warp is parked); a self-edge must be
        # armed AFTER resume because resume restores the site word
        deferred = idx in nxt
        armed = [self.dbg.arm(i) for i in nxt if i != idx]
        self.dbg.resume(bp)
        if deferred:
            armed.append(self.dbg.arm(idx))
        hit = self.dbg.wait_hit(timeout)
        for b in armed:
            if b.id != hit.id:
                self.dbg.disarm(b)
        self.path.append(hit.orig_index)
        return hit

    def run(self, bp: Breakpoint | None, max_steps: int = 100000) -> None:
        """Step until the kernel exits (or max_steps)."""
        n = 0
        while bp is not None:
            bp = self.step(bp)
            n += 1
            if n > max_steps:
                raise RuntimeError("step budget exhausted")
        self.dbg.wait_done()
