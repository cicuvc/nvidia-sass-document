"""sassdbg M3 probe — runtime patching of a *running* kernel's SASS code.

Builds on poc_code_patch.cu (device-side STG to code VAs works, the icache
is non-coherent).  Probe findings baked into the design below:

  * cuModuleLoadData / first cuLaunchKernel of a module BLOCKS while another
    kernel spins on-device (lazy loading path serializes against running
    work).  Rig therefore warms up the patcher kernel once before the target
    starts.
  * CCTL.I.IVALL is SM-LOCAL: a patcher-side invalidate only reaches the
    target when both CTAs happen to land on the same SM.  There is no GPU
    scope on CCTL (spec: COP enum = IVALL/IVALLP/WBALL/WBALLP only).
    => the reliable mechanism is TARGET-SIDE invalidation.  The target
    kernel carries a debugger prologue: it reports its code base (LEPC),
    parks at a start gate, and runs CCTL.I.IVALL once after release so any
    patch applied while parked becomes visible on the very first fetch.
  * Icache prefetch crosses the gate: the payload line (adjacent 128B line)
    is fetched/cached while the target spins at the gate, so without the
    post-gate IVALL even a "cold" patch has no effect.

  exp1  patch while parked at the gate; post-gate IVALL -> patch visible
  exp2  mid-run patch, no target-side IVALL -> stale (negative control)
  exp3  mid-run patch, patcher-side IVALL -> SM-local, no effect
  exp4  mid-run patch, TIGHT loop + per-iteration target IVALL -> STILL
        stale: tight loops replay from a loop/fetch buffer that
        CCTL.I.IVALL (I, D, or both) does not flush.  A mid-run patch of
        an actively-executed tight loop is never seen.  (limitation)
  exp6  same patch, FAT loop (body padded to ~2KB): the loop refetches
        its lines every iteration and the per-iteration IVALL makes the
        patch visible within an iteration.
  exp5  park/continue breakpoint via a trampoline: patch the payload
        word with a single BRA into a park region appended to the target
        ([CCTL.I.IVALL; poll continue flag; jump back]).  A 16-byte
        aligned store is single-copy atomic, so patch-in and restore are
        each ONE word — no transient-pair hazard.  The park loop's own
        IVALL makes the restore visible on the jump back.

IVALL hardening: a lone CCTL.I.IVALL races in-flight instruction fills —
the very next fetch (e.g. the branch into a patched line) can still
deliver a stale line that was being filled when the IVALL executed (the
fill gets discarded from the icache, so only ONE stale execution is
observed, but that is enough to lose a patch).  The reliable prologue is
IVALL; ~32 NOPs (stall 8); IVALL; branch.  Verified: 30/30 exp1, 20/20
exp5 with the hardened prologue; unhardened exp1 showed 1 stale
iteration within a few runs.

Usage: python3 -m sassdbg.probe_patch [exp ...]   (default: all)
"""
from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler import assemble, assemble_flat, CudaModule            # noqa: E402
from sassdbg.patch import PATCHER_SRC, _bra_word                     # noqa: E402

# ---------------------------------------------------------------------------
# kernels
# ---------------------------------------------------------------------------
_BRK = "[7:7:{}:1:0]"
_BRK_LD = "[0:7:{}:1:0]"

# cmd buffer layout (device memory; host polls via cuMemcpy):
#   +0x00  u64 target code VA
#   +0x08  u64 new lo64
#   +0x10  u64 new hi64
#   +0x18  u32 flags (nonzero -> CCTL.I.IVALL after the store)
#   +0x1c  u32 ack   (host zeroes; patcher writes 1)
# (PATCHER_SRC lives in sassdbg/patch.py — imported above)

# ctrl buffer layout (device memory; host polls via cuMemcpy):
#   +0x00  u64 code base VA (target writes its LEPC value here)
#   +0x08  u32 smid
#   +0x0c  u32 start gate (host: 0 -> 1 releases the target)
#   +0x10  u32 per-iteration CCTL flag (exp4; set before release)
#   +0x14  u32 progress (iteration counter, target writes every iteration)
#   +0x18  u32 done flag
#   +0x1c  u32 N iterations (host sets before launch)
#   +0x24  u32 dbg continue flag (exp5: 1 lets the park region jump back)
#   +0x40  u32 out[N] payload values
#
# Debugger prologue: the target reports LEPC/SMID, spins at the gate
# (backward branch, line 2), and after release executes one
# CCTL.I.IVALL before entering the payload loop — patches applied while
# parked are therefore guaranteed visible on first fetch.
TARGET_SRC = """#fn target(ctrl<8>) {
    LDCU.64 {UR60,UR61}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(ctrl);[1:7:{}:8:0]
    LEPC {R6,R7};[7:7:{}:4:0]
    STG.E.64.STRONG.GPU desc[{UR60,UR61}][{R4,R5}], {R6,R7};[7:7:{0,1}:8:0]
    S2R R8, SR_VIRTUALSMID;[2:7:{}:8:0]
    STG.E.STRONG.GPU desc[{UR60,UR61}][{R4,R5}+0x8], R8;[7:7:{0,1,2}:8:0]
    BRA #label(gate);[7:7:{}:4:0]
    NOP;[7:7:{}:1:0]
#def_label(loop)
    IADD3 R10, RZ, 0x1, RZ;[7:7:{}:4:0]
    IMAD.WIDE.U32 {R22,R23}, R20, 0x4, {R4,R5};[7:7:{1}:6:0]
    STG.E desc[{UR60,UR61}][{R22,R23}+0x40], R10;[7:7:{0}:8:0]
    STG.E.STRONG.GPU desc[{UR60,UR61}][{R4,R5}+0x14], R20;[7:7:{0,1}:8:0]
    IADD3 R20, R20, 0x1, RZ;[7:7:{}:4:0]
    ISETP.LT.U32.AND P0, PT, R20, R28, PT;[7:7:{3}:4:0]
    @P1 CCTL.I.IVALL;[7:7:{}:4:0]
    @P0 BRA #label(loop);[7:7:{}:6:0]
    MOV32I R26, 0x1;[7:7:{}:4:0]
    STG.E.STRONG.GPU desc[{UR60,UR61}][{R4,R5}+0x18], R26;[7:7:{0,1}:8:0]
    EXIT;[7:7:{}:4:0]
#def_label(gate)
    LDG.E.STRONG.GPU R9, desc[{UR60,UR61}][{R4,R5}+0xc];[5:7:{0,1}:8:0]
    LDG.E R28, desc[{UR60,UR61}][{R4,R5}+0x1c];[3:7:{0,1}:8:0]
    LDG.E R18, desc[{UR60,UR61}][{R4,R5}+0x10];[4:7:{0,1}:8:0]
    ISETP.NE.AND P1, PT, R18, 0x0, PT;[7:7:{4}:4:0]
    ISETP.NE.AND P0, PT, R9, 0x0, PT;[7:7:{5}:4:0]
    @!P0 BRA #label(gate);[7:7:{}:6:0]
    MOV R20, RZ;[7:7:{}:4:0]
    CCTL.I.IVALL;[7:7:{}:4:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    CCTL.I.IVALL;[7:7:{}:4:0]
    BRA #label(loop);[7:7:{}:4:0]
#def_label(dbgpark)
    CCTL.I.IVALL;[7:7:{}:4:0]
    LDG.E.STRONG.GPU R9, desc[{UR60,UR61}][{R4,R5}+0x24];[5:7:{0,1}:8:0]
    ISETP.NE.AND P0, PT, R9, 0x0, PT;[7:7:{5}:4:0]
    @!P0 BRA #label(dbgpark);[7:7:{}:6:0]
    CCTL.I.IVALL;[7:7:{}:4:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    NOP;[7:7:{}:8:0]
    CCTL.I.IVALL;[7:7:{}:4:0]
    BRA #label(loop);[7:7:{}:4:0]
}
"""

# exp6 target: same protocol, but the payload loop is fattened with 120
# NOPs (~2KB span) so it cannot replay from the loop/fetch buffer — every
# iteration genuinely refetches the payload line.
FAT_TARGET_SRC = TARGET_SRC.replace(
    "    @P1 CCTL.I.IVALL;[7:7:{}:4:0]\n    @P0 BRA #label(loop);"
    "[7:7:{}:6:0]",
    "    @P1 CCTL.I.IVALL;[7:7:{}:4:0]\n"
    + "    NOP;[7:7:{}:1:0]\n" * 120
    + "    @P0 BRA #label(loop);[7:7:{}:6:0]")
assert FAT_TARGET_SRC != TARGET_SRC

# instruction indices in TARGET_SRC (16 bytes each)
INST_LEPC = 2
INST_PAYLOAD = 8                  # the IADD3 R10, RZ, 0x1, RZ line
PAYLOAD_OFFSET = INST_PAYLOAD * 16
INST_DBGPARK = 61                 # first instruction of the park region

PAYLOAD_A = "IADD3 R10, RZ, 0x1, RZ;" + _BRK
PAYLOAD_B = "IADD3 R10, RZ, 0x100, RZ;" + _BRK
# _bra_word (label-self-calibrating BRA encoding) imported from patch.py

VAL_A, VAL_B = 0x1, 0x100


class Rig:
    """Patcher + target modules, device-memory ctrl/cmd buffers, 2 streams."""

    def __init__(self, n_iters: int, target_cctl: bool = False,
                 target_src: str = TARGET_SRC,
                 inst_payload: int = INST_PAYLOAD,
                 inst_dbgpark: int | None = INST_DBGPARK):
        self.patcher_mod = CudaModule(assemble(PATCHER_SRC, check_deps=False))
        self.target_mod = CudaModule(assemble(target_src, check_deps=False))
        self.inst_payload = inst_payload
        self.n = n_iters
        self.ctrl = self.target_mod.devmem_alloc(0x40 + n_iters * 4)
        self.cmd = self.target_mod.devmem_alloc(0x20)
        self.s_target = CudaModule.stream_create()
        self.s_patcher = CudaModule.stream_create()
        import struct as _st
        self.target_mod.device_write(self.ctrl,
                                     bytes(0x40 + n_iters * 4))
        self.target_mod.device_write(self.ctrl + 0x1c, _st.pack("<I", n_iters))
        self.target_mod.device_write(self.ctrl + 0x10,
                                     _st.pack("<I", 1 if target_cctl else 0))
        self.word_a = assemble_flat(PAYLOAD_A)[0]
        self.word_b = assemble_flat(PAYLOAD_B)[0]
        # original word at the patch site (+ sanity-check the layout)
        from assembler import assemble_kernel
        enc = assemble_kernel(target_src, check_deps=False).encoded
        self.orig_word = enc[inst_payload]
        if inst_dbgpark is not None:
            self.bra_dbg = _bra_word(inst_dbgpark - inst_payload)
            assert len(enc) == inst_dbgpark + 39, \
                f"dbgpark layout drifted: {len(enc)} instructions"
        # Warm up the patcher kernel: the first cuLaunchKernel of a module
        # (lazy load) blocks while another kernel spins on-device, so the
        # patcher must have run once before the target starts.
        self.scratch = self.target_mod.devmem_alloc(64)
        lo, hi = self.word_b
        self.patcher_mod.device_write(
            self.cmd, struct.pack("<QQQI", self.scratch, lo, hi, 0))
        self.patcher_mod.launch("patcher", grid=(1,), block=(1,),
                                args=[self.cmd], stream=self.s_patcher)
        CudaModule.stream_sync(self.s_patcher)

    # -- target control -----------------------------------------------------
    def launch_target(self):
        self.target_mod.launch("target", grid=(1,), block=(1,),
                               args=[self.ctrl], stream=self.s_target)

    def _rd32(self, off: int) -> int:
        return struct.unpack("<I", self.target_mod.device_read(
            self.ctrl + off, 4))[0]

    def _wr32(self, off: int, val: int) -> None:
        self.target_mod.device_write(self.ctrl + off, struct.pack("<I", val))

    def wait_base(self, timeout: float = 5.0) -> int:
        t0 = time.time()
        while True:
            lo, hi = self._rd32(0x0), self._rd32(0x4)
            if lo or hi:
                break
            if time.time() - t0 > timeout:
                raise TimeoutError("target did not report its code base")
            time.sleep(0.001)
        lepc = (hi << 32) | lo
        return lepc - INST_LEPC * 16

    def release(self):
        self._wr32(0x0c, 1)

    def progress(self) -> int:
        return self._rd32(0x14)

    def wait_done(self, timeout: float = 120.0) -> None:
        t0 = time.time()
        while self._rd32(0x18) == 0:
            if time.time() - t0 > timeout:
                raise TimeoutError(
                    f"target did not finish (progress={self.progress()})")
            time.sleep(0.005)

    def smid(self) -> int:
        return self._rd32(0x08)

    def out(self) -> list[int]:
        raw = self.target_mod.device_read(self.ctrl + 0x40, self.n * 4)
        return list(struct.unpack(f"<{self.n}I", raw))

    # -- patcher ------------------------------------------------------------
    def patch(self, va: int, word: tuple[int, int], cctl: bool,
              timeout: float = 5.0) -> None:
        """Patch one 128-bit instruction word at va; wait for the ack."""
        lo, hi = word
        self.patcher_mod.device_write(
            self.cmd, struct.pack("<QQQI", va, lo, hi, 1 if cctl else 0))
        self.patcher_mod.device_write(self.cmd + 0x1c, struct.pack("<I", 0))
        self.patcher_mod.launch("patcher", grid=(1,), block=(1,),
                                args=[self.cmd], stream=self.s_patcher)
        t0 = time.time()
        while struct.unpack("<I", self.patcher_mod.device_read(
                self.cmd + 0x1c, 4))[0] == 0:
            if time.time() - t0 > timeout:
                raise TimeoutError("patcher did not ack")
            time.sleep(0.0005)

    def patch_pair(self, va: int, words: list[tuple[int, int]],
                   cctl: bool, order: str = "word1_first") -> None:
        """Patch two adjacent instruction words.

        Order matters while the target may be executing/refetching the
        line — never let a transient pair spin on a BRA with no IVALL:
          * park   (install [CCTL; BRA self]): word0 first.  Transient
            [CCTL; orig] just re-invalidates; [orig; BRA self] would
            deadlock (no IVALL in the loop).
          * restore (orig pair back):        word1 first.  Transient
            [CCTL; orig] keeps the self-refreshing property.
        """
        if order == "word1_first":
            self.patch(va + 16, words[1], cctl=False)
            self.patch(va, words[0], cctl=cctl)
        else:
            self.patch(va, words[0], cctl=False)
            self.patch(va + 16, words[1], cctl=cctl)


# ---------------------------------------------------------------------------
# experiments
# ---------------------------------------------------------------------------
def _transitions(vals: list[int]) -> list[tuple[int, int, int]]:
    """(index, from, to) for every change between consecutive values."""
    return [(i, a, b) for i, (a, b) in enumerate(zip(vals, vals[1:]))
            if a != b]


def exp1() -> bool:
    """Patch while parked at the gate; post-gate IVALL makes it visible.

    This is the core M3 mechanism: the patcher stores the new word (no
    patcher-side CCTL needed), the target invalidates its OWN icache once
    after the gate, and the first fetch of the payload line sees the
    patched instruction.
    """
    rig = Rig(1024)
    rig.launch_target()
    base = rig.wait_base()
    rig.patch(base + PAYLOAD_OFFSET, rig.word_b, cctl=False)
    rig.release()
    rig.wait_done()
    vals = set(rig.out())
    ok = vals == {VAL_B}
    print(f"exp1 patch-at-gate + post-gate IVALL: payload values = "
          f"{sorted(hex(v) for v in vals)} (smid {rig.smid()}) -> "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def exp2() -> bool:
    """Runtime patch WITHOUT any CCTL — expect no effect (stale icache)."""
    rig = Rig(1 << 18)
    rig.launch_target()
    base = rig.wait_base()
    rig.release()
    while rig.progress() < rig.n // 2:
        time.sleep(0.0005)
    rig.patch(base + PAYLOAD_OFFSET, rig.word_b, cctl=False)
    rig.wait_done()
    tr = _transitions(rig.out())
    ok = len(tr) == 0
    print(f"exp2 patch w/o CCTL: transitions = {len(tr)}"
          f" (smid {rig.smid()}) -> {'OK (stale line confirmed)' if ok else 'FAIL — patch leaked into icache without invalidate'}")
    return ok


def exp3() -> bool:
    """Runtime patch, patcher-side CCTL.I.IVALL — does it reach the
    target's SM?"""
    rig = Rig(1 << 18)
    rig.launch_target()
    base = rig.wait_base()
    rig.release()
    while rig.progress() < rig.n // 2:
        time.sleep(0.0005)
    rig.patch(base + PAYLOAD_OFFSET, rig.word_b, cctl=True)
    rig.wait_done()
    tr = _transitions(rig.out())
    print(f"exp3 patcher-side CCTL: transitions = {len(tr)}"
          f"{'' if not tr else f' first at iter {tr[0][0]}'}"
          f" (smid {rig.smid()})")
    # either outcome is a finding; report, don't fail
    print("     -> patcher-side IVALL is "
          + ("GPU-WIDE (target saw the patch)" if tr else
             "SM-LOCAL (target kept the stale line)"))
    return True


def exp4() -> bool:
    """Mid-run patch, TIGHT loop, target-side per-iteration CCTL.I.IVALL.

    FINDING (limitation): the tight loop replays from a loop/fetch buffer
    that IVALL does not flush — the patch is never seen.  (Also verified:
    CCTL.D.IVALL and I+D together do not help.)  exp6 shows the fat-loop
    counterpart does pick the patch up.  A mid-run patch of an
    actively-executed tight loop is therefore unreliable; breakpoints
    must be armed before the loop is entered (gate/trampoline, exp5).
    """
    rig = Rig(1 << 12, target_cctl=True)
    rig.launch_target()
    base = rig.wait_base()
    rig.release()
    while rig.progress() < rig.n // 2:
        time.sleep(0.001)
    rig.patch(base + PAYLOAD_OFFSET, rig.word_b, cctl=False)
    rig.wait_done()
    tr = _transitions(rig.out())
    ok = len(tr) == 0
    print(f"exp4 tight-loop per-iter IVALL: transitions = {len(tr)}"
          f" (smid {rig.smid()}) -> {'OK (loop-replay limitation confirmed)' if ok else 'UNEXPECTED — tight loop saw the patch'}")
    return ok


def exp6() -> bool:
    """Mid-run patch, FAT loop (2KB body), per-iteration CCTL.I.IVALL —
    the loop refetches its lines, IVALL works, patch becomes visible."""
    rig = Rig(1 << 12, target_cctl=True, target_src=FAT_TARGET_SRC,
              inst_dbgpark=None)
    rig.launch_target()
    base = rig.wait_base()
    rig.release()
    while rig.progress() < rig.n // 2:
        time.sleep(0.001)
    rig.patch(base + PAYLOAD_OFFSET, rig.word_b, cctl=False)
    rig.wait_done()
    tr = _transitions(rig.out())
    ok = len(tr) == 1 and tr[0][2] == VAL_B
    print(f"exp6 fat-loop per-iter IVALL: transitions = {len(tr)}"
          f"{'' if not tr else f' at iter {tr[0][0]}'}"
          f" (smid {rig.smid()}) -> {'OK' if ok else 'FAIL'}")
    return ok


def exp5() -> bool:
    """Park/continue breakpoint via the trampoline region.

    While the target is parked at the gate, patch the payload word with a
    single BRA into the dbgpark region (one 16B store — atomic).  After
    release the post-gate IVALL makes the patched fetch visible and the
    warp parks in the self-refreshing dbgpark loop.  Resume = restore the
    original word (again one atomic store) then set the continue flag;
    the park loop's IVALL before the jump back guarantees the restored
    instruction is refetched.
    """
    rig = Rig(1 << 12)
    rig.launch_target()
    base = rig.wait_base()
    site = base + PAYLOAD_OFFSET
    rig.patch(site, rig.bra_dbg, cctl=False)
    rig.release()
    time.sleep(0.05)
    p1 = rig.progress()
    time.sleep(0.05)
    p2 = rig.progress()
    parked = (p1 == p2 == 0)
    print(f"exp5 park: progress {p1}->{p2} -> "
          f"{'parked' if parked else 'NOT PARKED'}")
    if not parked:
        return False
    # resume: restore the payload word, then let the park loop jump back
    rig.patch(site, rig.orig_word, cctl=False)
    rig._wr32(0x24, 1)
    rig.wait_done()
    vals = rig.out()
    ok = all(v == VAL_A for v in vals)
    print(f"exp5 continue: restored, target finished; out all A: {ok} -> "
          f"{'OK' if ok else 'FAIL'}")
    return ok and parked


EXPS = {"exp1": exp1, "exp2": exp2, "exp3": exp3, "exp4": exp4,
        "exp5": exp5, "exp6": exp6}


def main() -> int:
    names = sys.argv[1:] or list(EXPS)
    ok = True
    for n in names:
        try:
            ok = EXPS[n]() and ok
        except Exception as e:
            ok = False
            print(f"{n}: EXCEPTION {type(e).__name__}: {e}")
    print("\n== probe_patch:", "done", "==" )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
