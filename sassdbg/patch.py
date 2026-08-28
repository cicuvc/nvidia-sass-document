"""sassdbg M3v2 — runtime breakpoints via CALL.ABS + RPCMOV (slot-less).

Mechanism (all proven by probe_callheap2.py / probe_callheap3.py):

  * Breakpoint = overwrite the site word with the CONSTANT word
    `CALL.ABS.NOINC PT, {R252,R253}, 0x0` (the injected prologue preloads
    R252/R253 with the handler VA).  Same word for every site — no
    per-site relocation, no slots, no slot-count limit, no slot-recycling
    hit-id aliasing.  The patch word is UNCONDITIONAL (@PT): a breakpoint
    fires when execution REACHES the site, before the original
    instruction's own predicate is evaluated (the original word — with
    its predicate — is restored and re-executed on resume).  Copying the
    site's predicate into the patch word would silently skip predicated-
    off sites and break the stepper's arm-the-successors model.
  * The handler is HEAP-RESIDENT: plain device memory written by the host
    with cuMemcpy (the GPU fetches/executes SASS from devmem fine — fresh
    pages, no icache staleness).  No patcher involvement, no code-space
    writes beyond the site itself.
  * The handler reads RPC with RPCMOV.32 — RPC = VA of the CALL
    instruction itself => the breakpoint identity is the site VA, no id
    plumbing at all.  It saves the kernel's PR (its own spin ISETP would
    clobber P0), reports the site VA, parks in a spin on a GENERATION
    counter (a shared one-shot flag + slot-side self-reset races; a
    generation compare has no reset race at all).
  * Resume = restore the site word (patcher) + clear the hit word + bump
    the generation.  The handler then restores PR, runs the hardened
    IVALL; NOP x32; IVALL and `RET.ABS.NODEC PT, {site}, 0x0` back to the
    SITE, re-executing the restored original instruction.  The return
    address lives in REGISTERS (RPCMOV result), not in data memory, and
    the RET target line is cold (the warp was parked in the heap) — no
    hot-line patch race at all.
  * RET's target is ALWAYS Ra + disp(bytes): CALL_DEPTH.INC /
    RET_DEPTH.DEC only maintain a hardware call-depth counter — they
    neither save nor restore the PC (probe3 matrix S4: nested INC/DEC
    with correct register VAs works; RZ faults 700).  RPCMOV after a
    CALL.REL read 0 in probe3 S3 (only CALL.ABS populates RPC — open
    question, we only use CALL.ABS).
  * Divergent CALL works (probe3 P3b): a divergent group enters the
    handler with its own RPC.  Multi-group hits share one handler: the
    generation bump releases all parked groups; each re-executes its
    site, so a still-armed site simply re-reports.  (grid=(1,) single-
    warp focus, same as v1.)
  * SCOREBOARD RULE (probe3, hard-won): explicit barrier waits MUST go in
    the {req} bitset — the rd field does NOT reliably wait (rd=2 on a
    MOV32I did not wait; req={2} did; an rd=1-only STG.64 read a garbage
    LDC address pair -> 700; an unwaited CALL target register -> 718
    INVALID_PC).  The RPCMOVs re-claim SB0 so the report STG's
    req={0,1} covers LDCU + both RPCMOVs + the LDC ctrl pair.

Host API (unchanged from v1):

    dbg = Debugger(source)              # dialect source (e.g. from lift)
    dbg.launch(args)                    # target parks at the gate
    dbg.arm(inst_index)                 # inst_index = ORIGINAL source line
    dbg.release()                       # gate open -> hits breakpoints
    bp = dbg.wait_hit()                 # returns Breakpoint
    dbg.resume(bp)                      # continue; bp is consumed (re-arm)
    dbg.wait_done()

ctrl buffer layout (device memory, host polls via cuMemcpy):
  +0x00 u64 code base VA (target LEPC report)
  +0x08 u32 generation (host bumps to release a parked handler)
  +0x0c u32 start gate (host: 0 -> 1)
  +0x10 u64 hit site VA (handler writes, host clears on resume)
  +0x18 u32 kernel-predicate save (P2R on handler entry, R2P before RET)
  +0x20 u64 handler VA (host writes before launch; prologue loads it
        into R252/R253)
"""
from __future__ import annotations

import re
import struct
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler import assemble, assemble_flat, assemble_kernel, CudaModule  # noqa: E402

# ---------------------------------------------------------------------------
# patcher kernel (unchanged from v1 — host cuMemcpy cannot write module
# code space, so a device kernel stores the 16-byte site word)
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
# Debugger-reserved registers (disjoint from the wtrace band R224-R245).
#   R246/R247  ctrl buffer VA          (prologue, persistent)
#   R252/R253  handler VA              (prologue, persistent; the site
#                                      CALL reads them)
#   R248-R251  handler scratch (RPC site VA, PR save, generation)
#   UR60/UR61  default global cache descriptor
DBG_REGS = [f"R{r}" for r in range(246, 254)] + ["UR60", "UR61"]

# prologue: report base, load the handler VA, park at the gate, hardened
# self-invalidate.  LEPC stays at idx 2 (wait_base subtracts 2*16).
_PROLOGUE = """    LDCU.64 {UR60,UR61}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R246,R247}, #param(dbgctrl);[1:7:{}:8:0]
    LEPC {R248,R249};[7:7:{}:4:0]
    STG.E.64.STRONG.GPU desc[{UR60,UR61}][{R246,R247}], {R248,R249};[7:7:{0,1}:8:0]
    LDG.E.64.STRONG.GPU {R252,R253}, desc[{UR60,UR61}][{R246,R247}+0x20];[4:7:{0,1}:8:0]
#def_label(dbggate)
    LDG.E.STRONG.GPU R250, desc[{UR60,UR61}][{R246,R247}+0xc];[5:7:{0,1}:8:0]
    ISETP.NE.AND P0, PT, R250, 0x0, PT;[7:7:{5}:13:1]
    @!P0 BRA #label(dbggate);[7:7:{}:6:0]
    MOV32I R250, 0x0;[7:7:{4}:5:1]
    CCTL.I.IVALL;[7:7:{}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + """    CCTL.I.IVALL;[7:7:{}:4:0]
"""
PROLOGUE_LEN = 43           # instruction count of _PROLOGUE

# heap-resident breakpoint handler: RPCMOV the site VA, report it, save
# the kernel's PR, snapshot the generation, spin until it changes,
# restore PR, hardened IVALL, RET to the site (re-executes the restored
# original instruction).  Runs in the hitting warp's context with the
# prologue-established R246/R247 (ctrl) and UR60/UR61 (cdesc).
_HANDLER = """    RPCMOV.32 R248, Rpc.LO;[0:7:{}:13:1]
    RPCMOV.32 R249, Rpc.HI;[0:7:{}:13:1]
    STG.E.64.STRONG.GPU desc[{UR60,UR61}][{R246,R247}+0x10], {R248,R249};[7:7:{0,1}:8:0]
    P2R R250, PR;[7:7:{}:4:0]
    STG.E.STRONG.GPU desc[{UR60,UR61}][{R246,R247}+0x18], R250;[7:7:{}:8:0]
    LDG.E.STRONG.GPU R251, desc[{UR60,UR61}][{R246,R247}+0x8];[3:7:{}:8:0]
#def_label(dbgspin)
    LDG.E.STRONG.GPU R250, desc[{UR60,UR61}][{R246,R247}+0x8];[5:7:{}:8:0]
    ISETP.NE.AND P0, PT, R250, R251, PT;[7:7:{3,5}:13:1]
    @!P0 BRA #label(dbgspin);[7:7:{}:6:0]
    LDG.E.STRONG.GPU R250, desc[{UR60,UR61}][{R246,R247}+0x18];[2:7:{}:8:0]
    R2P PR, R250;[7:7:{2}:13:1]
    CCTL.I.IVALL;[7:7:{}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + """    CCTL.I.IVALL;[7:7:{}:4:0]
    RET.ABS.NODEC PT, {R248,R249}, 0x0;[7:7:{}:8:1]
"""

_EPILOGUE_GUARD = "    EXIT;[7:7:{}:4:0]\n"

_FN_RE = re.compile(r"^(#fn\s+\w+)\(([^)]*)\)\s*\{\s*$")


def _call_word() -> tuple[int, int]:
    """Encoding of the breakpoint patch word
    `CALL.ABS.NOINC PT, {R252,R253}, 0x0` (target VA in R252/R253)."""
    src = "#fn x() {\nCALL.ABS.NOINC PT, {R252,R253}, 0x0;[7:7:{}:5:1]\n}\n"
    return assemble_kernel(src, check_deps=False).encoded[0]


class DebugInfo:
    """Layout metadata of an injected source."""
    def __init__(self, source: str, n_body: int):
        self.source = source            # injected dialect source
        self.n_body = n_body            # original instruction count

    def injected_index(self, orig_index: int) -> int:
        """Original-source instruction index -> injected-source index."""
        if not 0 <= orig_index < self.n_body:
            raise IndexError(orig_index)
        return orig_index + PROLOGUE_LEN


def inject_debugger(source: str, max_bps: int = 0,
                    allow_cdesc_urs: bool = False) -> DebugInfo:
    """Inject the debugger prologue into a single-function dialect source.
    The function gains a trailing `dbgctrl<8>` parameter the host must
    pass (device-memory ctrl buffer).

    max_bps: accepted for v1 API compatibility; v2 has no slots, so the
    number of concurrently armed breakpoints is unlimited.

    allow_cdesc_urs: skip the UR60/UR61 rejection — safe only when the
    source uses UR60/UR61 exclusively for the default global cache
    descriptor (e.g. wtrace-instrumented sources, which load the same
    cdesc the debugger prologue/handler rely on)."""
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
        if allow_cdesc_urs and r in ("UR60", "UR61"):
            continue
        if re.search(rf"\b{r}\b", body):
            raise ValueError(f"kernel uses debugger-reserved {r}")
    for lbl in ("dbggate", "dbgspin"):
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
    # safety EXIT before the closing brace (fall-through guard)
    text = "\n".join(out)
    close = text.rstrip().rfind("}")
    text = (text[:close] + _EPILOGUE_GUARD + text[close:])
    info = DebugInfo(text, n_body)
    # validate the whole thing assembles, and self-check the layout
    enc = assemble_kernel(text, check_deps=False).encoded
    assert len(enc) == PROLOGUE_LEN + n_body + 1, "injected layout mismatch"
    return info


# ---------------------------------------------------------------------------
# host-side debugger
# ---------------------------------------------------------------------------
class Breakpoint:
    def __init__(self, dbg: "Debugger", bp_id: int,
                 orig_index: int, orig_word: tuple[int, int]):
        self.dbg = dbg
        self.id = bp_id                 # host-side, monotonically increasing
        self.orig_index = orig_index    # index in the ORIGINAL source
        self.orig_word = orig_word
        self.armed = True


class Debugger:
    """Runtime breakpoints for a dialect-source kernel.

    The kernel is launched with its normal args plus the dbgctrl buffer;
    it parks at the entry gate until release().  Arm breakpoints before
    release (reliable) — mid-run arming works only for code that
    refetches (not tight loops, loop/fetch-buffer replay defeats IVALL).
    """

    CTRL_BYTES = 0x28

    def __init__(self, source: str, func: str | None = None,
                 max_bps: int = 0, allow_cdesc_urs: bool = False):
        self.info = inject_debugger(source, max_bps,
                                    allow_cdesc_urs=allow_cdesc_urs)
        self.mod = CudaModule(assemble(self.info.source, check_deps=False))
        self.encoded = assemble_kernel(self.info.source,
                                       check_deps=False).encoded
        self.func = func or self._only_function()
        self.patcher = Patcher()
        self.ctrl = self.mod.devmem_alloc(self.CTRL_BYTES)
        self.mod.device_write(self.ctrl, bytes(self.CTRL_BYTES))
        # heap-resident handler: plain device memory, host-written
        self.handler = self.mod.devmem_alloc(0x400)
        words = b"".join(struct.pack("<QQ", lo, hi)
                         for lo, hi in assemble_flat(_HANDLER))
        self.mod.device_write(self.handler, words)
        self._wr64(0x20, self.handler)      # prologue loads this into R252/3
        self.stream = CudaModule.stream_create()
        self._bps: dict[int, Breakpoint] = {}
        self._by_index: dict[int, Breakpoint] = {}
        self._next_id = 1
        self._gen = 0
        self._patch_base = _call_word()

    def _only_function(self) -> str:
        m = re.search(r"#fn\s+(\w+)", self.info.source)
        assert m
        return m.group(1)

    # -- lifecycle -----------------------------------------------------------
    def launch(self, args: list, grid=(1,), block=(1,)) -> None:
        """Launch the target (args = the kernel's normal args); it parks
        at the gate.  dbgctrl is appended automatically."""
        self.mod.launch(self.func, grid=grid, block=block,
                        args=args + [self.ctrl], stream=self.stream)

    def _rd32(self, off: int) -> int:
        return struct.unpack("<I", self.mod.device_read(
            self.ctrl + off, 4))[0]

    def _wr32(self, off: int, val: int) -> None:
        self.mod.device_write(self.ctrl + off, struct.pack("<I", val))

    def _rd64(self, off: int) -> int:
        return struct.unpack("<Q", self.mod.device_read(
            self.ctrl + off, 8))[0]

    def _wr64(self, off: int, val: int) -> None:
        self.mod.device_write(self.ctrl + off, struct.pack("<Q", val))

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
        """Patch the site word with the CALL into the heap handler."""
        if orig_index in self._by_index:
            raise RuntimeError(f"breakpoint already armed at {orig_index}")
        inj = self.info.injected_index(orig_index)
        site = self.base() + inj * 16
        orig = self.encoded[inj]
        self.patcher.patch(site, self._patch_base)
        bp = Breakpoint(self, self._next_id, orig_index, orig)
        self._next_id += 1
        self._bps[bp.id] = bp
        self._by_index[orig_index] = bp
        return bp

    def disarm(self, bp: Breakpoint) -> None:
        """Restore the original word (only when NOT parked at this bp)."""
        self.patcher.patch(self._site_va(bp.orig_index), bp.orig_word)
        bp.armed = False
        del self._bps[bp.id]
        del self._by_index[bp.orig_index]

    def wait_hit(self, timeout: float = 30.0) -> Breakpoint:
        """Wait until a breakpoint parks the target; returns the bp."""
        t0 = time.time()
        while True:
            va = self._rd64(0x10)
            if va:
                inj = (va - self.base()) // 16
                orig = inj - PROLOGUE_LEN
                bp = self._by_index.get(orig)
                if bp is None:
                    raise RuntimeError(
                        f"hit from unarmed site {hex(va)} (orig {orig})")
                return bp
            if time.time() - t0 > timeout:
                raise TimeoutError("no breakpoint hit")
            time.sleep(0.001)

    def resume(self, bp: Breakpoint) -> None:
        """Restore the site, then bump the generation: the parked handler
        restores the kernel's PRs, self-invalidates, and RETs back to the
        site, re-executing the restored original instruction.  The
        breakpoint is CONSUMED (site keeps its original word) — to break
        again, re-arm.  Re-arming mid-run against a tight loop is
        unreliable (loop replay); prefer arming at the gate."""
        site = self._site_va(bp.orig_index)
        self.patcher.patch(site, bp.orig_word)           # restore
        self._wr64(0x10, 0)                              # clear hit
        self._gen += 1
        self._wr32(0x08, self._gen)                      # release
        bp.armed = False
        del self._bps[bp.id]
        del self._by_index[bp.orig_index]
