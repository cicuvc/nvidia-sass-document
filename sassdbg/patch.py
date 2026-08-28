"""sassdbg M3 — runtime breakpoints in SASS code via device-side patching.

Mechanism (all proven by probe_patch.py experiments):

  * The patcher kernel below stores 16-byte instruction words into code
    memory (STG.E.128.STRONG.GPU, single-copy atomic).  It must be warmed
    up (launched once) before the target starts — first-use lazy module
    load blocks while another kernel spins.
  * CCTL.I.IVALL is SM-local, so the TARGET invalidates its own icache:
    the injected debugger prologue parks at a start gate and runs a
    hardened IVALL; NOP x32; IVALL sequence after release.  Breakpoints
    armed while parked are therefore visible on first fetch.
  * Breakpoint = overwrite the site word with `BRA slot_k`.  The slot
    parks the warp (CCTL.I.IVALL + STRONG LDG of a per-slot release
    flag), after notifying the host with a hit id.  Resume = restore the
    original site word, write the return VA to the ctrl buffer, set the
    slot's release flag; the slot then `BRX {R252,R253}` jumps back —
    the return address travels through DATA memory, so resume needs no
    code patch of a hot line at all (a patched BRA in the spin line
    races the loop's own refetches and can execute stale exactly once —
    fatal when the stale word is the placeholder branch).
  * Mid-run arming works for code that refetches (fat regions) but NOT
    for tight loops (loop/fetch buffer replay defeats IVALL) — arm at
    the gate for reliability.

Host API:

    dbg = Debugger(source)              # dialect source (e.g. from lift)
    dbg.launch(args)                    # target parks at the gate
    dbg.arm(inst_index)                 # inst_index = ORIGINAL source line
    dbg.release()                       # gate open -> hits breakpoints
    bp = dbg.wait_hit()                 # returns Breakpoint
    dbg.resume(bp)                      # continue; bp stays armed
    dbg.wait_done()

ctrl buffer layout (device memory, host polls via cuMemcpy):
  +0x00 u64 code base VA (target LEPC report)
  +0x08 u32 smid
  +0x0c u32 start gate (host: 0 -> 1)
  +0x10 u32 hit id (1-based bp id; slot writes, host clears on resume)
  +0x18 u64 return VA (host writes the bp site VA at resume)
  +0x20 + 4*slot  u32 per-slot release flag (host: 0 -> 1)

The release flag is PER-SLOT, one-shot: a shared flag plus slot-side
self-reset races (the parked warp can reach the next slot's first load
before the previous slot's reset store reaches L2 — STRONG loads bypass
L1 but stores drain asynchronously).  The host zeroes the slot's flag
when the slot is (re-)armed, i.e. when no warp can be inside it.
"""
from __future__ import annotations

import re
import struct
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler import assemble, assemble_kernel, CudaModule            # noqa: E402

_BRK = "[7:7:{}:1:0]"

# ---------------------------------------------------------------------------
# patcher kernel (shared with probe_patch.py)
# ---------------------------------------------------------------------------
# cmd buffer layout:
#   +0x00  u64 target code VA
#   +0x08  u64 new lo64
#   +0x10  u64 new hi64
#   +0x18  u32 flags (nonzero -> CCTL.I.IVALL after the store)
#   +0x1c  u32 ack   (host zeroes; patcher writes 1)
PATCHER_SRC = """#fn patcher(cmd<8>) {
    LDCU.64 {UR60,UR61}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(cmd);[1:7:{}:8:0]
    LDG.E.64 {R8,R9}, desc[{UR60,UR61}][{R4,R5}];[2:7:{0,1}:8:0]
    LDG.E.64 {R12,R13}, desc[{UR60,UR61}][{R4,R5}+0x8];[3:7:{0,1}:8:0]
    LDG.E.64 {R14,R15}, desc[{UR60,UR61}][{R4,R5}+0x10];[4:7:{0,1}:8:0]
    LDG.E R18, desc[{UR60,UR61}][{R4,R5}+0x18];[5:7:{0,1}:8:0]
    ISETP.NE.AND P0, PT, R18, 0x0, PT;[7:7:{5}:4:0]
    STG.E.128.STRONG.GPU desc[{UR60,UR61}][{R8,R9}], {R12,R13,R14,R15};[7:7:{0,2,3,4}:8:0]
    @P0 CCTL.I.IVALL;[7:7:{}:4:0]
    MOV32I R19, 0x1;[7:7:{}:4:0]
    STG.E.STRONG.GPU desc[{UR60,UR61}][{R4,R5}+0x1c], R19;[7:7:{0,1}:8:0]
    EXIT;[7:7:{}:4:0]
}
"""


class Patcher:
    """Device-side instruction-word patcher (one warm-up launch required
    before any spinning target exists)."""

    def __init__(self):
        self.mod = CudaModule(assemble(PATCHER_SRC, check_deps=False))
        self.cmd = self.mod.devmem_alloc(0x20)
        self.stream = CudaModule.stream_create()
        self.scratch = self.mod.devmem_alloc(64)
        # warm-up: defeat the first-launch lazy-load block
        self._launch(self.scratch, (0, 0), cctl=False)
        CudaModule.stream_sync(self.stream)

    def _launch(self, va: int, word: tuple[int, int], cctl: bool) -> None:
        lo, hi = word
        self.mod.device_write(
            self.cmd, struct.pack("<QQQI", va, lo, hi, 1 if cctl else 0))
        self.mod.device_write(self.cmd + 0x1c, struct.pack("<I", 0))
        self.mod.launch("patcher", grid=(1,), block=(1,),
                        args=[self.cmd], stream=self.stream)

    def patch(self, va: int, word: tuple[int, int], cctl: bool = False,
              timeout: float = 5.0) -> None:
        """Store one 128-bit instruction word at va; wait for the ack."""
        self._launch(va, word, cctl)
        t0 = time.time()
        while struct.unpack("<I", self.mod.device_read(
                self.cmd + 0x1c, 4))[0] == 0:
            if time.time() - t0 > timeout:
                raise TimeoutError("patcher did not ack")
            time.sleep(0.0005)


# ---------------------------------------------------------------------------
# source injection
# ---------------------------------------------------------------------------
# Debugger-reserved registers (disjoint from the tracer's R240-R245 band
# is NOT guaranteed — a kernel under the debugger must not use any of
# R240-R253 / UR60/UR61, same rule as instrument.py).
DBG_REGS = [f"R{r}" for r in range(246, 254)] + ["UR60", "UR61"]

# prologue: report base+smid, park at the gate, hardened self-invalidate
_PROLOGUE = """    LDCU.64 {UR60,UR61}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R246,R247}, #param(dbgctrl);[1:7:{}:8:0]
    LEPC {R248,R249};[7:7:{}:4:0]
    STG.E.64.STRONG.GPU desc[{UR60,UR61}][{R246,R247}], {R248,R249};[7:7:{0,1}:8:0]
    S2R R250, SR_VIRTUALSMID;[2:7:{}:8:0]
    STG.E.STRONG.GPU desc[{UR60,UR61}][{R246,R247}+0x8], R250;[7:7:{0,1,2}:8:0]
#def_label(dbggate)
    LDG.E.STRONG.GPU R250, desc[{UR60,UR61}][{R246,R247}+0xc];[5:7:{0,1}:8:0]
    ISETP.NE.AND P0, PT, R250, 0x0, PT;[7:7:{5}:4:0]
    @!P0 BRA #label(dbggate);[7:7:{}:6:0]
    CCTL.I.IVALL;[7:7:{}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + """    CCTL.I.IVALL;[7:7:{}:4:0]
"""
PROLOGUE_LEN = 43           # instruction count of _PROLOGUE

# one breakpoint slot: notify, park (self-refreshing spin on the slot's
# own release word), load the return VA, hardened self-invalidate, JMX
# back to the site.  JMX (absolute indirect jump, target = Ra + off,
# verified in notes/sm90/instr/jmx.md — BRX is the RELATIVE twin) keeps
# the resume path entirely in data memory — no code patch of a line the
# spin loop keeps refetching.
SLOT_WORDS = 42
_SLOT_TMPL = """#def_label(dbgslot{k})
    MOV32I R251, {kid};[7:7:{{0,1,2,3,4,5}}:4:0]
    STG.E.STRONG.GPU desc[{{UR60,UR61}}][{{R246,R247}}+0x10], R251;[7:7:{{}}:8:0]
#def_label(dbgspin{k})
    CCTL.I.IVALL;[7:7:{{}}:4:0]
    LDG.E.STRONG.GPU R250, desc[{{UR60,UR61}}][{{R246,R247}}+{rel}];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R250, 0x0, PT;[7:7:{{5}}:4:0]
    @!P0 BRA #label(dbgspin{k});[7:7:{{}}:6:0]
    LDG.E.64.STRONG.GPU {{R252,R253}}, desc[{{UR60,UR61}}][{{R246,R247}}+0x18];[4:7:{{}}:8:0]
    CCTL.I.IVALL;[7:7:{{}}:4:0]
""" + "    NOP;[7:7:{{}}:8:0]\n" * 32 + """    CCTL.I.IVALL;[7:7:{{}}:4:0]
    JMX {{R252,R253}};[7:7:{{4}}:4:0]
"""

_EPILOGUE_GUARD = "    EXIT;[7:7:{}:4:0]\n"

_FN_RE = re.compile(r"^(#fn\s+\w+)\(([^)]*)\)\s*\{\s*$")


def _bra_word(delta_insts: int) -> tuple[int, int]:
    """Encoding of `BRA` branching delta_insts from its own position
    (label self-calibration inside a dummy function)."""
    pad = "NOP;" + _BRK + "\n"
    if delta_insts > 0:
        src = ("#fn x() {\nBRA #label(p);" + _BRK + "\n"
               + pad * (delta_insts - 1)
               + "#def_label(p)\nNOP;" + _BRK + "\n}\n")
        return assemble_kernel(src, check_deps=False).encoded[0]
    if delta_insts < 0:
        src = ("#fn x() {\n#def_label(p)\n"
               + pad * (-delta_insts - 1)
               + "BRA #label(p);" + _BRK + "\n}\n")
        return assemble_kernel(src, check_deps=False).encoded[-1]
    raise ValueError("zero-length branch")


class DebugInfo:
    """Layout metadata of an injected source."""
    def __init__(self, source: str, n_body: int, max_bps: int):
        self.source = source            # injected dialect source
        self.n_body = n_body            # original instruction count
        self.max_bps = max_bps

    def injected_index(self, orig_index: int) -> int:
        """Original-source instruction index -> injected-source index."""
        if not 0 <= orig_index < self.n_body:
            raise IndexError(orig_index)
        return orig_index + PROLOGUE_LEN

    def slot_index(self, slot: int) -> int:
        """Injected index of slot k's first word."""
        return PROLOGUE_LEN + self.n_body + 1 + slot * SLOT_WORDS


def inject_debugger(source: str, max_bps: int = 32) -> DebugInfo:
    """Inject the debugger prologue + breakpoint slots into a single-
    function dialect source.  The function gains a trailing `dbgctrl<8>`
    parameter the host must pass (device-memory ctrl buffer)."""
    lines = source.splitlines()
    fn_at = None
    for i, ln in enumerate(lines):
        if _FN_RE.match(ln.strip()):
            if fn_at is not None:
                raise ValueError("multi-function sources not supported")
            fn_at = i
    if fn_at is None:
        raise ValueError("no #fn header found")
    body = "\n".join(lines[fn_at:])
    for r in DBG_REGS:
        if re.search(rf"\b{r}\b", body):
            raise ValueError(f"kernel uses debugger-reserved {r}")
    for lbl in ("dbggate", "dbgslot", "dbgspin"):
        if lbl in body:
            raise ValueError(f"label collision: {lbl}")

    m = _FN_RE.match(lines[fn_at].strip())
    assert m
    params = m.group(2).strip()
    new_hdr = f"{m.group(1)}({params}, dbgctrl<8>) {{" if params \
        else f"{m.group(1)}(dbgctrl<8>) {{"

    out = lines[:fn_at] + [new_hdr, _PROLOGUE.rstrip("\n")] \
        + lines[fn_at + 1:]
    # instruction count of the ORIGINAL body (for index mapping)
    n_body = len(assemble_kernel(source, check_deps=False).encoded)
    slots = "".join(_SLOT_TMPL.format(k=k, kid=k + 1,
                                      rel=hex(0x20 + 4 * k))
                    for k in range(max_bps))
    # insert a safety EXIT + the slots before the final closing brace
    text = "\n".join(out)
    close = text.rstrip().rfind("}")
    text = (text[:close] + _EPILOGUE_GUARD + slots + text[close:])
    info = DebugInfo(text, n_body, max_bps)
    # validate the whole thing assembles, and self-check the layout
    enc = assemble_kernel(text, check_deps=False).encoded
    assert len(enc) == info.slot_index(max_bps - 1) + SLOT_WORDS, \
        "injected layout mismatch"
    return info


# ---------------------------------------------------------------------------
# host-side debugger
# ---------------------------------------------------------------------------
class Breakpoint:
    def __init__(self, dbg: "Debugger", bp_id: int, slot: int,
                 orig_index: int, orig_word: tuple[int, int]):
        self.dbg = dbg
        self.id = bp_id                 # 1-based; written to ctrl+0x10
        self.slot = slot
        self.orig_index = orig_index    # index in the ORIGINAL source
        self.orig_word = orig_word
        self.armed = True


class Debugger:
    """Runtime breakpoints for a dialect-source kernel.

    The kernel is launched with its normal args plus the dbgctrl buffer;
    it parks at the entry gate until release().  Arm breakpoints before
    release (reliable) — mid-run arming works only for code that
    refetches (not tight loops).
    """

    def __init__(self, source: str, func: str | None = None,
                 max_bps: int = 32):
        self.info = inject_debugger(source, max_bps)
        self.mod = CudaModule(assemble(self.info.source, check_deps=False))
        self.encoded = assemble_kernel(self.info.source,
                                       check_deps=False).encoded
        self.func = func or self._only_function()
        self.patcher = Patcher()
        self.ctrl = self.mod.devmem_alloc(0x20 + 4 * max_bps)
        self.mod.device_write(self.ctrl, bytes(0x20 + 4 * max_bps))
        self.stream = CudaModule.stream_create()
        self._bps: dict[int, Breakpoint] = {}
        self._free_slots = list(range(max_bps))
        self._next_id = 1

    def _only_function(self) -> str:
        m = re.search(r"#fn\s+(\w+)", self.info.source)
        assert m
        return m.group(1)

    # -- lifecycle -----------------------------------------------------------
    def launch(self, args: list, grid=(1,), block=(1,)) -> None:
        """Launch the target (args = the kernel's normal args); it parks
        at the gate.  dbgctrl is appended automatically.  Breakpoints
        park the whole warp (the site BRA is warp-uniform)."""
        self.mod.launch(self.func, grid=grid, block=block,
                        args=args + [self.ctrl], stream=self.stream)

    def _rd32(self, off: int) -> int:
        return struct.unpack("<I", self.mod.device_read(
            self.ctrl + off, 4))[0]

    def _wr32(self, off: int, val: int) -> None:
        self.mod.device_write(self.ctrl + off, struct.pack("<I", val))

    def wait_base(self, timeout: float = 5.0) -> int:
        t0 = time.time()
        while True:
            lo, hi = self._rd32(0x0), self._rd32(0x4)
            if lo or hi:
                break
            if time.time() - t0 > timeout:
                raise TimeoutError("target did not report its code base")
            time.sleep(0.001)
        return ((hi << 32) | lo) - 2 * 16

    def base(self) -> int:
        if not hasattr(self, "_base"):
            self._base = self.wait_base()
        return self._base

    def release(self) -> None:
        """Open the start gate.  The prologue self-invalidates, so every
        breakpoint armed while parked is live from the first fetch."""
        self._wr32(0x0c, 1)

    def wait_done(self, timeout: float = 120.0) -> None:
        # poll stream_query: the target exits normally; if a breakpoint
        # is still parked this would block forever, so time out loudly
        t0 = time.time()
        while not CudaModule.stream_query(self.stream):
            if time.time() - t0 > timeout:
                raise TimeoutError("target still running "
                                   "(parked breakpoint not resumed?)")
            time.sleep(0.01)

    # -- breakpoints -----------------------------------------------------------
    def _site_va(self, orig_index: int) -> int:
        return self.base() + self.info.injected_index(orig_index) * 16

    def arm(self, orig_index: int) -> Breakpoint:
        """Patch the site word with BRA into a free slot."""
        if not self._free_slots:
            raise RuntimeError("no free breakpoint slots")
        slot = self._free_slots.pop(0)
        bp_id = self._next_id
        self._next_id += 1
        self._wr32(0x20 + 4 * slot, 0)   # release flag low (slot is empty)
        inj = self.info.injected_index(orig_index)
        site = self.base() + inj * 16
        slot_idx = self.info.slot_index(slot)
        bra = _bra_word(slot_idx - inj)
        self.patcher.patch(site, bra)
        bp = Breakpoint(self, bp_id, slot, orig_index, self.encoded[inj])
        self._bps[bp_id] = bp
        return bp

    def disarm(self, bp: Breakpoint) -> None:
        """Restore the original word (only when NOT parked at this bp)."""
        self.patcher.patch(self._site_va(bp.orig_index), bp.orig_word)
        bp.armed = False
        self._free_slots.append(bp.slot)
        del self._bps[bp.id]

    def wait_hit(self, timeout: float = 30.0) -> Breakpoint:
        """Wait until a breakpoint parks the target; returns the bp."""
        t0 = time.time()
        while True:
            hid = self._rd32(0x10)
            if hid:
                bp = self._bps.get(hid)
                if bp is None:
                    raise RuntimeError(f"unknown hit id {hid}")
                return bp
            if time.time() - t0 > timeout:
                raise TimeoutError("no breakpoint hit")
            time.sleep(0.001)

    def resume(self, bp: Breakpoint) -> None:
        """Restore the site, point the slot's return BRA at the site, and
        release the parked warp.  The breakpoint is CONSUMED (site keeps
        its original word; the slot is freed) — to break again, re-arm.
        Re-arming mid-run against a tight loop is unreliable (loop
        replay, see probe exp4); prefer arming at the gate."""
        site = self._site_va(bp.orig_index)
        self.patcher.patch(site, bp.orig_word)           # restore
        self.mod.device_write(self.ctrl + 0x18,
                              struct.pack("<Q", site))   # return VA
        self._wr32(0x10, 0)                              # clear hit
        self._wr32(0x20 + 4 * bp.slot, 1)                # release the slot
        bp.armed = False
        self._free_slots.append(bp.slot)
        del self._bps[bp.id]
