"""sassdbg M6 — interactive CLI frontend (stepper UI + reverse step).

Usage:
  python3 -m sassdbg.cli --sass kernel.sass [--grid G] [--block B]
  python3 -m sassdbg.cli --cubin x.cubin --func k [--grid G] [--block B]
  python3 -m sassdbg.cli --cubin x.cubin --trace        # reverse enabled

Commands (cmd.Cmd — also scriptable via stdin):
  b N / break N     arm breakpoint at instruction N (original numbering)
  d N / delete N    disarm
  info b            list breakpoints
  r / run           release the gate, run to first hit (or completion)
  c / continue      resume all parked warps, wait for the next hit
  s / step          single-step ALL parked warps (lockstep)
  w / warps         warp status (parked at / exited)
  p [w] / path [w]  executed path of warp w (or all)
  l [N] / list [N]  source listing around instruction N / current hits
  back [w]          reverse one step (needs --trace; warp 0 default)
  regs w lane Rx..  register values at the current replay point (--trace)
  q / quit          release everything still parked and exit

Semantics notes:
  * Instruction numbers are ORIGINAL-source indices (the Stepper/Cfg
    numbering; labels excluded).  With --trace the wtrace scaffolding is
    hidden — the CLI maps original idx -> instrumented idx internally.
  * A breakpoint is CONSUMED on hit (v3 semantics): re-arm with `b N`.
  * Do not mix manual `b` with `s`: step_all disarms the armed sites it
    armed itself; a foreign armed site may produce an "unexpected hit".
  * --trace (wtrace reverse) is single-CTA only (wtrace region indexing
    is tid>>5; no SR_CTAID term) and reverse replay is single-warp.
  * Args are auto-generated: 8-byte params get a 64 KiB scratch buffer,
    smaller params are zero-filled (same policy as sassdbg.tracer).
"""
import argparse
import cmd
import shlex
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import CudaModule, assemble_kernel     # noqa: E402
from sassdbg.stepper import Stepper                  # noqa: E402
from sassdbg.patch import Debugger            # noqa: E402
from sassdbg.wtrace import REGION_BYTES              # noqa: E402


def _parse_source(path: str) -> str:
    return Path(path).read_text()


def _lift_cubin(path: str, func: str | None) -> str:
    from sassdbg.lift import lift
    srcs = lift(path, func)
    if func:
        return srcs[func]
    return next(iter(srcs.values()))


class Shell(cmd.Cmd):
    intro = ("sassdbg CLI — type 'help' for commands.  The kernel is "
             "parked at the entry gate.")
    prompt = "(sassdbg) "

    def __init__(self, args):
        super().__init__()
        self.args = args
        self.trace_mode = args.trace
        self.ik = None
        cubin_dbg = None
        if args.sass:
            src = _parse_source(args.sass)
        elif self.trace_mode:
            # trace instruments the SOURCE and re-assembles — keep the
            # M2 lift+inject path for --cubin --trace
            src = _lift_cubin(args.cubin, args.func)
        else:
            # M10 real-cubin path: patch the entry trampoline in the
            # cubin image; no lift-inject-reassemble round trip
            from sassdbg.real import CubinDebugger
            cubin_dbg = "pending"
            src = None
        n_warps = args.grid * ((args.block + 31) // 32)
        max_warps = max(args.max_warps, n_warps)
        if cubin_dbg is not None:
            cubin_dbg = CubinDebugger(args.cubin, args.func,
                                      max_bps=32, max_warps=max_warps)
            src = cubin_dbg.source
        self.user_src = src
        if self.trace_mode:
            from sassdbg.wtrace import instrument_warp
            if args.grid != 1:
                raise ValueError("--trace is single-CTA only")
            self.ik = instrument_warp(src)
            src = self.ik.source
            self._orig2inst = self._build_idx_map(self.ik)
        self.st = Stepper(src, max_warps=max_warps, dbg=cubin_dbg)
        self.dbg: Debugger = self.st.dbg
        # auto args from the kernel's param list
        names = self._param_names(self.user_src)
        if cubin_dbg is not None:
            params = cubin_dbg.params       # (ordinal, offset, size)
        else:
            res = assemble_kernel(self.dbg.info.source, check_deps=True)
            params = [p for p in res.params][:len(names)]
        self._scratch: list[int] = []
        argv: list = []
        # params in declaration order; the dbgctrl param is appended by
        # launch() itself (source path only), and __trace by us below
        for i, (_, off, sz) in enumerate(params):
            if sz >= 8:
                buf = self.dbg.mod.devmem_alloc(0x10000)
                self.dbg.mod.device_write(buf, bytes(0x10000))
                self._scratch.append(buf)
                argv.append(buf)
                print(f"  param {i} ({names[i] if i < len(names) else '?'},"
                      f" {sz}B) -> scratch {hex(buf)}")
            else:
                argv.append(bytes(sz))
                print(f"  param {i} ({names[i] if i < len(names) else '?'},"
                      f" {sz}B) -> 0")
        if self.ik is not None:
            self.tracebuf = self.dbg.mod.devmem_alloc(REGION_BYTES)
            self.dbg.mod.device_write(self.tracebuf, bytes(REGION_BYTES))
            argv.append(self.tracebuf)
        self.st.launch(argv, grid=(args.grid,), block=(args.block,))
        self._parked: dict[int, list[tuple[int, int]]] = {}
        # user view: warp -> [(inst idx, lane mask)] — one entry per
        # parked GROUP (M8: divergent groups park independently)
        self._exited: set[int] = set()
        self._state = {}                       # warp -> replay state
        self._released = False
        print(f"launched: grid=({args.grid},) block=({args.block},), "
              f"{self.dbg.n_warps} warp(s) parked at the gate")

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _param_names(src: str) -> list[str]:
        import re
        m = re.search(r"#fn\s+\w+\(([^)]*)\)", src)
        if not m or not m.group(1).strip():
            return []
        return [p.split("<")[0].strip() for p in m.group(1).split(",")]

    def _build_idx_map(self, ik) -> dict[int, int]:
        """original step idx -> instruction index in the instrumented
        source (Debugger/SITE numbering: non-label instructions)."""
        from assembler.sass_parser import Lexer, Parser
        decl = Parser(Lexer(ik.source).tokenize()).parse_kernel()
        texts = []
        lines = ik.source.splitlines()
        for inst in decl.instructions:
            if inst.mnemonic == "_label_":
                continue
            texts.append(lines[inst.line - 1].strip()
                         if 0 < inst.line <= len(lines) else inst.mnemonic)
        mapping = {}
        pos = 0
        for s in ik.steps:
            # find the first instruction at/after pos whose text matches
            for j in range(pos, len(texts)):
                if texts[j].startswith(s.text.split(";")[0].strip()[:24]):
                    mapping[s.idx] = j
                    pos = j + 1
                    break
            else:
                raise ValueError(f"cannot map step {s.idx} ({s.text!r}) "
                                 "into the instrumented source")
        return mapping

    def _site(self, n: int) -> int:
        return self._orig2inst[n] if self.ik is not None else n

    def _unlabelled_src(self) -> list[str]:
        out = []
        for ln in self.user_src.splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#def_label") \
                    and not ln.startswith("#fn") and ln != "}":
                out.append(ln)
        return out

    def _user_idx(self, site_idx: int) -> int:
        if self.ik is not None:
            inv = {v: k for k, v in self._orig2inst.items()}
            return int(inv.get(site_idx, site_idx))
        return int(site_idx)

    def _all_groups(self) -> list:
        """Authoritative parked-group list: [(warp, _Group)].  The
        debugger's _groups are dropped on release and created on hit,
        so they always reflect what is parked RIGHT NOW (unlike the
        stepper's _parked, which manual b/c commands desync)."""
        return [(w, g) for w in range(self.dbg.max_warps)
                for g in self.dbg._groups[w]]

    def _show_group_hit(self, w: int, g) -> None:
        """Record and print a parked group (M8: a warp may park as
        several divergent groups — each gets its own lanes mask)."""
        user_idx = self._user_idx(g.bp.orig_index)
        lines = self._unlabelled_src()
        text = lines[user_idx] if 0 <= user_idx < len(lines) else "?"
        extra = "" if g.mask == 0xFFFFFFFF \
            else f"  [lanes {g.mask:#010x}]"
        print(f"hit: warp {w} at inst {user_idx}: {text}{extra}")
        lst = [(i, m) for i, m in self._parked.get(w, [])
               if i != user_idx]
        lst.append((user_idx, g.mask))
        self._parked[w] = lst
        if self.ik is not None and w == 0:
            self._update_replay(w)

    def _update_replay(self, w: int) -> None:
        from sassdbg.reverse import WarpReplay
        assert self.ik is not None
        rp = WarpReplay(self.ik.sidecar(),
                        bytes(self.dbg.mod.device_read(self.tracebuf,
                                                       REGION_BYTES)),
                        warp=w)
        self._rp = rp
        self._state[w] = rp.replay()

    # -- commands ------------------------------------------------------------
    def do_b(self, a: str) -> None:
        """b N — arm a breakpoint at original instruction N."""
        n = int(a.strip())
        bp = self.dbg.arm(self._site(n))
        print(f"armed bp#{bp.id} at inst {n}")

    def do_break(self, a: str) -> None:
        self.do_b(a)

    def do_d(self, a: str) -> None:
        """d N — disarm the breakpoint at original instruction N."""
        n = int(a.strip())
        site = self._site(n)
        bp = self.dbg._by_index.get(site)
        if bp is None:
            print(f"no bp armed at inst {n}")
            return
        self.dbg.disarm(bp)
        print(f"disarmed inst {n}")

    def do_delete(self, a: str) -> None:
        self.do_d(a)

    def do_info(self, a: str) -> None:
        """info b — list breakpoints."""
        if a.strip() != "b":
            print("usage: info b")
            return
        for bp in sorted(self.dbg._bps.values(), key=lambda b: b.id):
            print(f"  bp#{bp.id} inst={bp.orig_index} armed={bp.armed}"
                  f" warp={bp.warp}")

    def do_r(self, a: str) -> None:
        """r — release the gate and park every warp at instruction 0."""
        if self._released:
            print("already released")
            return
        self._released = True
        self.st.run_to_entry_all()
        for w, g in sorted(self.st._parked):
            self._show_group_hit(w, g)

    def do_run(self, a: str) -> None:
        self.do_r(a)

    def _wait_next(self) -> None:
        if len(self._exited) == self.dbg.n_warps and not self._parked:
            print("kernel finished")
            return
        try:
            w, g = self.dbg.wait_group_hit(timeout=5.0)
        except TimeoutError:
            if CudaModule.stream_query(self.dbg.stream):
                print("kernel finished")
            else:
                print("(no hit within 5s; warps still running)")
            return
        self._show_group_hit(w, g)
        # drain any other already-queued hits (a divergent sibling
        # often parks in the same resume window)
        while True:
            try:
                w, g = self.dbg.wait_group_hit(timeout=0.2)
            except TimeoutError:
                break
            self._show_group_hit(w, g)
        if not self._all_groups() \
                and CudaModule.stream_query(self.dbg.stream):
            print("kernel finished")

    def do_c(self, a: str) -> None:
        """c — resume everything parked, wait for the next hit."""
        groups = self._all_groups()
        if not groups:
            print("nothing parked")
            return
        seen = set()
        for w, g in groups:
            if g.bp.id in seen:
                continue
            seen.add(g.bp.id)
            self.dbg.resume(g.bp)    # releases ALL groups at the site
        # drop the resumed sites from the user view; re-hits come
        # through _wait_next / the next command
        for w, g in groups:
            ui = self._user_idx(g.bp.orig_index)
            self._parked[w] = [(i, m) for i, m in self._parked.get(w, [])
                               if i != ui]
            if not self._parked[w]:
                del self._parked[w]
        self._wait_next()

    def do_continue(self, a: str) -> None:
        self.do_c(a)

    def do_s(self, a: str) -> None:
        """s — single-step ALL parked groups (lockstep, M8 group-aware)."""
        self.st._parked = self._all_groups()   # re-sync (c/b desync it)
        groups = self.st._parked
        if not groups:
            print("nothing parked (use 'r' first)")
            return
        out = self.st.step_groups(groups)
        self._parked.clear()
        for w, g in out:
            self._show_group_hit(w, g)
        for w in {w for w, _ in groups} - {w for w, _ in out}:
            self._exited.add(w)
            print(f"warp {w}: exited")

    def do_step(self, a: str) -> None:
        self.do_s(a)

    def do_w(self, a: str) -> None:
        """w — warp status (one line per parked GROUP; M8: a divergent
        warp parks as several groups, each with its own lane mask)."""
        for w in range(self.dbg.n_warps):
            if w in self._parked:
                for idx, m in self._parked[w]:
                    n = bin(m).count("1")
                    print(f"  warp {w}: parked at inst {idx}"
                          f"  lanes {m:#010x} ({n})")
            elif w in self._exited:
                print(f"  warp {w}: exited")
            else:
                done = CudaModule.stream_query(self.dbg.stream)
                print(f"  warp {w}: {'exited' if done else 'running / gate'}")

    def do_warps(self, a: str) -> None:
        self.do_w(a)

    def do_p(self, a: str) -> None:
        """p [w] — executed path of warp w (or all)."""
        a = a.strip()
        if a:
            print(f"warp {a}: {self.st.paths.get(int(a), [])}")
        else:
            for w, p in sorted(self.st.paths.items()):
                print(f"  warp {w}: {p}")

    def do_path(self, a: str) -> None:
        self.do_p(a)

    def do_l(self, a: str) -> None:
        """l [N] — list source around instruction N (or parked sites)."""
        lines = self._unlabelled_src()
        marks = {idx for lst in self._parked.values() for idx, _ in lst}
        if a.strip():
            n = int(a.strip())
        elif marks:
            n = min(marks)
        else:
            n = 0
        lo, hi = max(0, n - 3), min(len(lines), n + 4)
        for i in range(lo, hi):
            arrow = "=>" if i in marks else (" *" if i == n else "  ")
            print(f"{arrow} {i:4}  {lines[i]}")

    def do_list(self, a: str) -> None:
        self.do_l(a)

    def do_back(self, a: str) -> None:
        """back [w] — reverse one step for warp w (default 0). --trace only."""
        if self.ik is None:
            print("reverse needs --trace")
            return
        w = int(a.strip() or "0")
        st = self._state.get(w)
        if st is None:
            print(f"no replay state for warp {w} (hit a bp first)")
            return
        self._rp.step_back(st)
        print(f"warp {w}: replay pc = {st.pc} "
              f"({self.ik.steps[st.pc].text if 0 <= st.pc < len(self.ik.steps) else '?'})")

    def do_regs(self, a: str) -> None:
        """regs w lane R N [R M ...] — register dump at the replay point."""
        if self.ik is None:
            print("needs --trace")
            return
        toks = shlex.split(a)
        w = int(toks[0]) if toks else 0
        lane = int(toks[1]) if len(toks) > 1 else 0
        st = self._state.get(w)
        if st is None:
            print(f"no replay state for warp {w}")
            return
        for t in toks[2:]:
            r = int(t.upper().lstrip("R"))
            v = st.reg(lane, r)
            print(f"  w{w} lane{lane} R{r} = {hex(v)}")
        if len(toks) <= 2:
            print(f"  warp {w} lane {lane}: "
                  + " ".join(f"R{r}={hex(st.reg(lane, r))}"
                             for r in sorted(st.regs[lane])))

    def do_dump(self, a: str) -> None:
        """dump w [lane] Rx [Ry ...] — live registers of the PARKED warp (M7)."""
        toks = shlex.split(a)
        if not toks:
            print(self.do_dump.__doc__)
            return
        w = int(toks[0])
        if not any(gw == w for gw, _ in self._all_groups()):
            print(f"warp {w} is not parked (hit a breakpoint first)")
            return
        i = 1
        lane = 0
        if i < len(toks) and not toks[i].upper().startswith(("R", "PR")):
            lane = int(toks[i]); i += 1
        regs = toks[i:] or ["R0"]
        vals = self.dbg.dump_regs(w, regs, lane=lane)
        for k, v in vals.items():
            print(f"  w{w} lane{lane} {k} = {hex(v)}")

    def do_set(self, a: str) -> None:
        """set w [lane] Rx value — write a register of the PARKED warp."""
        toks = shlex.split(a)
        if len(toks) < 3:
            print(self.do_set.__doc__)
            return
        w = int(toks[0])
        if not any(gw == w for gw, _ in self._all_groups()):
            print(f"warp {w} is not parked (hit a breakpoint first)")
            return
        i = 1
        lane = 0
        if not toks[i].upper().startswith(("R", "PR")):
            lane = int(toks[i]); i += 1
        val = int(toks[i + 1], 0)
        self.dbg.set_reg(w, toks[i].upper(), val, lane=lane)
        print(f"  w{w} lane{lane} {toks[i].upper()} <- {hex(val)}")

    def do_exec(self, a: str) -> None:
        """exec w <sass line> — run one instruction on the PARKED warp (M7).

        Straight-line code only; R0/R1 (frame pointer) write-protected;
        R2-R7/P0-P6 are scratch. Include the scheduling bracket yourself."""
        toks = a.strip().split(None, 1)
        if len(toks) < 2:
            print(self.do_exec.__doc__)
            return
        w = int(toks[0])
        if not any(gw == w for gw, _ in self._all_groups()):
            print(f"warp {w} is not parked (hit a breakpoint first)")
            return
        try:
            self.dbg.exec_cmd(w, [toks[1]])
            print("  done")
        except ValueError as e:
            print(f"  rejected: {e}")

    def do_q(self, a: str) -> bool:
        """q — release anything still parked and quit."""
        groups = self._all_groups()
        if groups:
            print(f"releasing {len(groups)} parked group(s)...")
            seen = set()
            for w, g in groups:
                if g.bp.id not in seen:
                    seen.add(g.bp.id)
                    self.dbg.resume(g.bp)
            try:
                self.dbg.wait_done(timeout=10.0)
                print("kernel completed")
            except TimeoutError:
                print("WARNING: kernel did not finish; CUDA context may "
                      "be wedged (process exit will reset it)")
        return True

    def do_quit(self, a: str) -> bool:
        return self.do_q(a)

    def do_EOF(self, a: str) -> bool:
        print()
        return self.do_q(a)


def main() -> None:
    ap = argparse.ArgumentParser(prog="sassdbg.cli")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sass", help="dialect source file")
    src.add_argument("--cubin", help="cubin file (lifted to dialect)")
    ap.add_argument("--func", help="function name in the cubin")
    ap.add_argument("--grid", type=int, default=1)
    ap.add_argument("--block", type=int, default=32)
    ap.add_argument("--max-warps", type=int, default=1)
    ap.add_argument("--trace", action="store_true",
                    help="wtrace-instrument for reverse stepping "
                         "(single CTA, single warp replay)")
    args = ap.parse_args()
    Shell(args).cmdloop()


if __name__ == "__main__":
    main()
