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
import re
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler.sass_parser import Lexer, Parser            # noqa: E402
from assembler.arch import spec_const_map                  # noqa: E402
from sassdbg.patch import Debugger, Breakpoint             # noqa: E402

# branch instructions whose LABEL operand is the taken target
_BR_LABEL = {"BRA", "BSSY", "CALL"}
_TERMINAL = {"EXIT", "RET", "KILL"}
_INDIRECT = {"BRX", "BRXU", "JMX", "JMXU", "JMP", "JMPX"}
# barrier-class: a thunk replay of these BLOCKS until sibling lanes
# arrive at the same barrier — the barrier assist watches for groups
# released FROM these sites (M8d probe_bar: BAR.SYNC arrival is
# PC-agnostic; WARPSYNC/BSYNC rendezvous via the shared thunk VA)
_BARRIER = {"BSYNC", "WARPSYNC", "BAR"}


@dataclass
class CfgInst:
    idx: int
    mnemonic: str
    predicated: bool
    label: str | None          # LABEL operand of a branch, if any
    text: str = ""             # raw source line (for thunk replay)


class Cfg:
    """Static control flow of one dialect-source kernel, in original
    instruction indices (labels are not instructions)."""

    def __init__(self, source: str):
        decl = Parser(Lexer(source).tokenize()).parse_kernel()
        srclines = source.splitlines()
        self.param_names: list[str] = [p.name for p in decl.params]
        self.insts: list[CfgInst] = []
        self.labels: dict[str, int] = {}
        for inst in decl.instructions:
            if inst.mnemonic == "_label_":
                self.labels[inst.label] = len(self.insts)
                continue
            lbl = next((op.value for op in inst.operands
                        if op.kind.name == "LABEL"), None)
            text = (srclines[inst.line - 1].strip()
                    if 0 < inst.line <= len(srclines) else "")
            self.insts.append(CfgInst(
                idx=len(self.insts), mnemonic=inst.mnemonic.upper(),
                predicated=inst.pred is not None, label=lbl, text=text))
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

    Usage (single warp):
        st = Stepper(source)
        st.launch(args)                       # parks at the gate
        bp = st.run_to_entry()                # break before inst 0
        while bp is not None:
            ... inspect bp.orig_index ...
            bp = st.step(bp)
        st.dbg.wait_done()

    Multi-warp (block=(32*N,)): run_to_entry_all() / step_all(state)
    drive EVERY parked warp one instruction at a time (lockstep of the
    parked set); per-warp executed paths land in self.paths[warp].

    M8: divergence-aware.  Stepping uses PERSISTENT breakpoints +
    per-group thunk replay (the site word is never restored, so there
    is no restore-vs-refetch race and loop re-hits need no re-arm).
    A warp may split into several parked GROUPS at different sites;
    step_groups() advances a set of (warp, group) pairs and returns
    the new set (a hit whose mask covers several released groups is
    a merge — the groups reconverged at that site).  step()/step_all()
    are the non-divergent compat wrappers (they raise if a warp is
    parked as more than one group).
    """

    def __init__(self, source: str, func: str | None = None,
                 max_bps: int = 32, max_warps: int = 1):
        self.cfg = Cfg(source)
        self.dbg = Debugger(source, func=func, max_bps=max_bps,
                            max_warps=max_warps)
        self.path: list[int] = []           # single-warp view (= paths[0])
        self.paths: dict[int, list[int]] = {}
        self.n_warps = 1
        self._parked: list[tuple[int, object]] = []   # (warp, _Group)

    def launch(self, args: list, grid=(1,), block=(32,)) -> None:
        self.dbg.launch(args, grid=grid, block=block)
        self.n_warps = self.dbg.n_warps
        self.paths = {w: [] for w in range(self.n_warps)}
        self.path = self.paths[0]
        self.dbg.wait_base()

    def _group_of(self, w: int, bp: Breakpoint):
        for gw, g in self._parked:
            if gw == w and g.bp is bp:
                return g
        raise RuntimeError(f"no parked group of warp {w} at "
                           f"inst {bp.orig_index}")

    def _replay_insts(self, idx: int) -> list[str]:
        """Thunk INST1 for the instruction at idx.  Plain instructions
        replay verbatim.  BRA is PC-relative (can't reach the kernel
        from the blob) so it becomes absolute JMP(s) — predicated BRA
        keeps its guard predicate on the target JMP, and build_thunk's
        appended fall-through JMP completes the emulation.  BSSY's Sa
        is architecturally inert (probe-verified), so it replays with a
        thunk-local label."""
        ci = self.cfg.insts[idx]
        if ci.mnemonic == "BRA" and ci.label is not None:
            tgt = self.dbg._site_va(self.cfg.target(ci.label))
            jmp = f"JMP 0x{tgt:x};[7:7:{{}}:6:0]"
            if not ci.predicated:
                return [jmp]
            return [f"{ci.text.split()[0]} {jmp}"]
        text = ci.text
        # thunk assembly has no #fn context: resolve the const-bank
        # directives to absolute c[0x0][...] addresses
        text = re.sub(
            r"#param\((\w+)\)",
            lambda m: "c[0x0][0x%x]" % self.dbg.res_params[
                self.cfg.param_names.index(m.group(1))][1],
            text)
        text = re.sub(
            r"#spec_const\((\w+)\)",
            lambda m: "c[0x%x][0x%x]" % spec_const_map()[m.group(1)],
            text)
        if "#label(" in text:               # BSSY: thunk-local label
            text = re.sub(r"#label\([^)]*\)", "#label(tk)", text)
            return [text, "#def_label(tk)"]
        return [text]

    def step_groups(self, groups: list, timeout: float = 30.0) -> list:
        """Advance each parked (warp, group) by exactly one instruction;
        returns the new list of (warp, group).  Groups whose parked
        instruction is terminal drop out (they run to completion).
        Several groups landing on the same site merge into one returned
        group (combined lane mask)."""
        succ_sites: set[int] = set()
        live: list[tuple[int, object, list[int]]] = []
        terminal: list[Breakpoint] = []
        for w, g in groups:
            nxt = self.cfg.next_pcs(g.bp.orig_index)
            if nxt:
                live.append((w, g, nxt))
                succ_sites.update(nxt)
            elif g.bp not in terminal:
                # resume() releases EVERY group parked at the site (all
                # warps) and consumes the bp — do it once per site
                terminal.append(g.bp)
        for bp in terminal:
            self.dbg.resume(bp)              # terminal: run to exit
        # persistent bps: arm successors not already armed (parked
        # sites stay armed; self-edges are already armed)
        already = {b.orig_index for b in self.dbg._bps.values()}
        for s in sorted(succ_sites - already):
            self.dbg.arm(s)
        for w, g, _nxt in live:
            self.dbg.release_group(w, g,
                                   self._replay_insts(g.bp.orig_index))
        # collect: pending entries track the REMAINING unaccounted lane
        # mask of each released group — a hit may deliver a subset
        # (the group SPLIT) or lanes of several groups at once (they
        # MERGED at the site).  An entry completes when all its lanes
        # have been accounted by hits at its successor sites.  p[4]
        # marks groups released FROM a barrier-class site: their thunk
        # replays the barrier, so they may be blocked in it waiting for
        # lanes still in flight — only then is the assist needed.
        pending = [[w, g, set(nxt), g.mask,
                    self.cfg.insts[g.bp.orig_index].mnemonic in _BARRIER]
                   for w, g, nxt in live]
        out: list[tuple[int, object]] = []
        while pending:
            hw, hg = self.dbg.wait_group_hit(timeout)
            site = hg.bp.orig_index
            hits = [(p, hg.mask & p[3]) for p in pending
                    if p[0] == hw and site in p[2]]
            hits = [(p, inter) for p, inter in hits if inter]
            if not hits:
                raise RuntimeError(
                    f"unexpected hit from warp {hw} at "
                    f"orig {site} mask {hg.mask:#x}")
            for p, inter in hits:
                p[3] &= ~inter
            if (self.cfg.insts[site].mnemonic in _BARRIER
                    and any(p[3] and p[4] for p in pending)):
                # BARRIER ASSIST: a released group is blocked inside its
                # thunk's BSYNC waiting for the lanes that just parked
                # here.  Release the parked group immediately (same
                # cached thunk VA -> same-PC rendezvous) so the barrier
                # can complete; the just-parked lanes are in flight
                # again and will re-hit at a successor of the barrier.
                nxt2 = set(self.cfg.next_pcs(site))
                already = {b.orig_index for b in self.dbg._bps.values()}
                for s in sorted(nxt2 - already):
                    self.dbg.arm(s)
                self.dbg.release_group(hw, hg, self._replay_insts(site))
                for p, inter in hits:
                    p[2] |= nxt2
                    p[3] |= inter
                continue
            pending = [p for p in pending if p[3]]
            if not any(g is hg for _, g in out):
                out.append((hw, hg))
                self.paths[hw].append(site)
        # boundary invariant: armed sites == parked sites (disarm the
        # sites nobody took — safe: everything is parked now)
        parked = {g.bp.orig_index for _, g in out}
        for b in list(self.dbg._bps.values()):
            if b.orig_index not in parked:
                self.dbg.disarm(b)
        self._parked = out
        return out

    def run_to_entry(self, timeout: float = 30.0) -> Breakpoint:
        bp = self.dbg.arm(0)
        self.dbg.release()
        w, g = self.dbg.wait_group_hit(timeout)
        self._parked = [(w, g)]
        self.paths[w].append(g.bp.orig_index)
        return g.bp

    def step(self, bp: Breakpoint, timeout: float = 30.0
             ) -> Breakpoint | None:
        """Execute exactly the parked instruction; returns the next hit
        (None when the instruction was terminal — kernel finished).
        Non-divergent compat wrapper over step_groups."""
        w = bp.warp if bp.warp is not None else 0
        out = self.step_groups([(w, self._group_of(w, bp))], timeout)
        if not out:
            return None
        if len(out) > 1:
            raise RuntimeError(
                f"warp {w} diverged into {len(out)} groups: "
                f"use step_groups()")
        return out[0][1].bp

    def run(self, bp: Breakpoint | None, max_steps: int = 100000) -> None:
        """Step until the kernel exits (or max_steps)."""
        n = 0
        while bp is not None:
            bp = self.step(bp)
            n += 1
            if n > max_steps:
                raise RuntimeError("step budget exhausted")
        self.dbg.wait_done()

    # -- multi-warp (M3v3) ---------------------------------------------------
    # Invariant at step boundaries: the set of armed sites == the set of
    # sites where a warp is currently parked.
    def run_to_entry_all(self, timeout: float = 30.0
                         ) -> dict[int, Breakpoint]:
        """Arm inst 0, open the gate, and park EVERY warp; returns
        {warp: bp}."""
        self.dbg.arm(0)
        self.dbg.release()
        state: dict[int, Breakpoint] = {}
        self._parked = []
        while len(state) < self.n_warps:
            w, g = self.dbg.wait_group_hit(timeout)
            state[w] = g.bp
            self._parked.append((w, g))
            self.paths[w].append(g.bp.orig_index)
        return state

    def step_all(self, state: dict[int, Breakpoint],
                 timeout: float = 30.0) -> dict[int, Breakpoint]:
        """Advance every parked warp by exactly one instruction; returns
        the new {warp: bp} (warps that executed a terminal instruction
        drop out — they run to completion).  Non-divergent compat
        wrapper: raises when a warp is parked as several groups."""
        groups = [(w, self._group_of(w, bp)) for w, bp in state.items()]
        out = self.step_groups(groups, timeout)
        new_state: dict[int, Breakpoint] = {}
        for w, g in out:
            if w in new_state:
                raise RuntimeError(
                    f"warp {w} diverged into multiple groups: "
                    f"use step_groups()")
            new_state[w] = g.bp
        return new_state

    def run_all(self, state: dict[int, Breakpoint],
                max_steps: int = 100000) -> None:
        """step_all until every warp exited (or max_steps)."""
        n = 0
        while state:
            state = self.step_all(state)
            n += 1
            if n > max_steps:
                raise RuntimeError("step budget exhausted")
        self.dbg.wait_done()
