"""sassdbg M3v3 — multi-warp runtime breakpoints via per-warp blobs,
CALL.ABS + RPCMOV, and a SELF-CONSTRUCTED immediate RET.

Mechanism (proven by probe_callheap2/3.py and probe_mwarp.py):

  * Breakpoint = overwrite the site word with the CONSTANT word
    `CALL.ABS.NOINC PT, {R252,R253}, HANDLER_OFF`.  R252/R253 hold the
    PER-WARP blob base, so the same patch word serves every site AND
    every warp — no per-site relocation, no slots, no warp-id plumbing.
    The patch word is UNCONDITIONAL (@PT): a breakpoint fires when
    execution REACHES the site, before the original instruction's own
    predicate is evaluated (the original word — with its predicate — is
    restored and re-executed on resume).  Copying the site's predicate
    into the patch word would silently skip predicated-off sites and
    break the stepper's arm-the-successors model.
  * Per-warp BLOB (1 MiB device memory, warp_id = SR_TID.X>>5, grid=(1,)
    only): [0,0x20000) local backing, [0x40000,...) comms (generation /
    hit site VA), [0x80000,...) the handler CODE.  The prologue computes
    the warp's blob base into R252/R253 and runs SETLMEMBASE once,
    PERMANENTLY — the blob doubles as the warp's local-memory backing,
    so the handler spills/restores kernel registers with plain STL/LDL
    at fixed RZ+uImm24 slots (no scratch register needed to spill; the
    classic "need a register to save a register" bootstrap problem).
    RULE: SETLMEMBASE must be far from the first local access (the gate
    spin provides the distance — short NOP pads proved flaky, and
    host-prefill reads right after the switch can lane-split or 700).
  * Kernel register reservation: R252/R253 ONLY (plus UR60/UR61 are NOT
    needed — comms use DESC-LESS STG/LDG.STRONG.GPU, probe P2).  The
    handler's scratch R246-R251 and PR are spilled to local slots and
    restored before the RET.
  * The handler returns through a RET.ABS.NODEC RZ, imm word it BUILDS
    ITSELF: RPCMOV gives the site VA (= breakpoint identity), the
    handler composes the 128-bit RET word (imm field = va>>2, SCALE 4)
    and STG.E.128s it over its own last line, then the tail IVALL;
    NOP x32; IVALL makes the store visible to the fetch.  This frees
    the R246/R247 return-pair reservation v2 needed.  (RET's target is
    ALWAYS Ra + disp(bytes); with Ra=RZ the target is the imm itself.
    CALL.ABS imm form faults 700 on sm_120 — probe3 P4 — but the RET
    imm form works: probe P6b.)
  * Resume = restore the site word (patcher) + clear the hit word + bump
    the GENERATION of every warp parked at that site.  Each handler
    restores PR, re-fetches (hardened IVALL), and RETs to the SITE,
    re-executing the restored original instruction.  The breakpoint is
    CONSUMED (re-arm to break again).
  * SCOREBOARD RULE (probe3, hard-won): explicit barrier waits MUST go
    in the {req} bitset — the rd field does NOT reliably wait.  All
    cross-barrier consumers below use req.

ctrl buffer layout (shared, device memory, host polls via cuMemcpy):
  +0x00 u64 code base VA (target LEPC report; LEPC is prologue inst 1)
  +0x0c u32 start gate (host: 0 -> 1)
  +0x20 u64 blob base VA (host writes before launch; warps stride
        BLOB_SZ from it)
  +0x28 u32 warps per CTA (host writes at launch; warpid =
        SR_CTAID.X * ctawarps + SR_TID.X>>5)

per-warp comms (blob + COMMS):
  +0x08 u32 generation (host bumps to release that warp)
  +0x10 u64 hit site VA (handler writes, host clears on resume)
  +0x18 u32 command sequence (host bumps to dispatch a command — M7)
  +0x1c u32 command ack (handler echoes after the command RETs)
  +0x100 .. command result scratch (dump_regs targets)

spill slots (local addr LMEMHIOFF+4k, RZ+uImm24 — reach only the low
0x640 dwords of the local window, which is all we need):
  slot 0-5: R246-R251   slot 6: PR   slot 7: gen baseline
  slot 8: cmd_seq baseline

Host API (unchanged from v2):

    dbg = Debugger(source, max_warps=2)   # dialect source (e.g. lift)
    dbg.launch(args, block=(64,))         # target parks at the gate
    dbg.arm(inst_index)                   # inst_index = ORIGINAL source
    dbg.release()                         # gate open -> hits breakpoints
    bp = dbg.wait_hit()                   # bp.warp = hitting warp
    dbg.resume(bp)                        # continue; bp is consumed
    dbg.wait_done()
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
        self.mod = CudaModule(assemble(PATCHER_SRC, check_deps=True))
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
# layout constants (probe_mwarp.py)
# ---------------------------------------------------------------------------
LMEMHIOFF = 0x00fff9c0          # SR_LMEMHIOFF on sm_120
BLOB_SZ = 0x100000              # per-warp blob (1 MiB)
COMMS = 0x40000                 # comms offset inside a blob
HANDLER_OFF = 0x80000           # handler code offset inside a blob
CMD_OFF = 0x90000               # injected-command buffer offset in a blob
COMMS_SEQ = COMMS + 0x18        # u32 command sequence (host bumps)
COMMS_ACK = COMMS + 0x1c        # u32 command ack (handler echoes)
COMMS_RESULTS = COMMS + 0x100   # command result scratch (dump targets)


def _slot(k: int) -> str:
    """Local addr (RZ+uImm24 form) of spill slot k."""
    return f"[RZ+0x{LMEMHIOFF + 4 * k:x}]"


# ---------------------------------------------------------------------------
# source injection
# ---------------------------------------------------------------------------
# Debugger-reserved registers: the per-warp blob base ONLY.  Handler
# scratch (R246-R251) and PR are spilled to local slots; URs are free.
DBG_REGS = ["R252", "R253"]

# prologue: report base, compute the GLOBAL warp id
# (SR_CTAID.X * ctawarps + SR_TID.X>>5; ctawarps from ctrl+0x28, written
# by launch()) -> per-warp blob base, permanent SETLMEMBASE, park at the
# gate (which doubles as the SETLMEMBASE settling window), zero the
# scratch the prologue borrowed, hardened self-invalidate.
# LEPC stays at idx 1 (wait_base subtracts 1*16).
_PROLOGUE = """    LDC.64 {R252,R253}, #param(dbgctrl);[1:7:{}:8:0]
    LEPC {R246,R247};[7:7:{}:4:0]
    STG.E.64.STRONG.GPU [{R252,R253}], {R246,R247};[7:7:{1}:8:0]
    LDG.E.64.STRONG.GPU {R248,R249}, [{R252,R253}+0x20];[2:7:{1}:8:0]
    LDG.E.STRONG.GPU R250, [{R252,R253}+0x28];[3:7:{1}:8:0]
    MOV R246, R252;[7:7:{}:5:1]
    MOV R247, R253;[7:7:{}:5:1]
    S2R R251, SR_TID.X;[5:7:{}:5:1]
    SHF.R.U32.HI R251, RZ, 0x5, R251;[7:7:{5}:5:1]
    S2R R252, SR_CTAID.X;[4:7:{}:5:1]
    IMAD R250, R252, R250, R251;[7:7:{3,4}:5:1]
    IMAD.WIDE.U32 {R252,R253}, R250, 0x100000, {R248,R249};[7:7:{2}:13:1]
    SETLMEMBASE {R252,R253};[7:7:{}:5:1]
#def_label(dbggate)
    LDG.E.STRONG.GPU R250, [{R246,R247}+0xc];[5:7:{}:8:0]
    ISETP.NE.AND P0, PT, R250, 0x0, PT;[7:7:{5}:13:1]
    @!P0 BRA #label(dbggate);[7:7:{}:6:0]
    MOV32I R246, 0x0;[7:7:{}:5:1]
    MOV32I R247, 0x0;[7:7:{}:5:1]
    MOV32I R248, 0x0;[7:7:{}:5:1]
    MOV32I R249, 0x0;[7:7:{}:5:1]
    MOV32I R250, 0x0;[7:7:{}:5:1]
    MOV32I R251, 0x0;[7:7:{}:5:1]
    CCTL.I.IVALL;[7:7:{}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + """    CCTL.I.IVALL;[7:7:{}:4:0]
"""
PROLOGUE_LEN = sum(1 for ln in _PROLOGUE.splitlines() if ";[" in ln)

_FN_RE = re.compile(r"^(#fn\s+\w+)\(([^)]*)\)\s*\{\s*$")


def _call_word() -> tuple[int, int]:
    """Encoding of the breakpoint patch word
    `CALL.ABS.NOINC PT, {R252,R253}, HANDLER_OFF` — the SAME word for
    every site and every warp (the per-warp handler VA comes from the
    per-warp R252/R253 blob base)."""
    src = ("#fn x() {\nCALL.ABS.NOINC PT, {R252,R253}, "
           f"0x{HANDLER_OFF:x};[7:7:{{}}:5:1]\n}}\n")
    return assemble_kernel(src, check_deps=True).encoded[0]


# ---------------------------------------------------------------------------
# handler: spill, report site VA, compose the imm-RET word over its own
# last line, park on the generation, restore, hardened IVALL, fall into
# the constructed RET (Ra=RZ -> target = imm = the site VA; resume has
# restored the original instruction there).
# ---------------------------------------------------------------------------
def _ret_template() -> tuple[int, int]:
    """(lo64, hi64) of `RET.ABS.NODEC PT, RZ, 0x0` carrying the FINAL
    bracket (req of the 6 restore LDLs) so the runtime-composed word
    inherits it."""
    return assemble_flat(
        "    RET.ABS.NODEC PT, RZ, 0x0;[7:7:{0,1,2,3,4,5}:8:1]\n")[0]


def compose_ret_word(va: int) -> tuple[int, int]:
    """(lo64, hi64) of `RET.ABS.NODEC PT, RZ, <va>` by bit surgery.
    va is the BYTE return address (16-aligned).  imm field = va>>2
    (SCALE 4): field[7:0]->lo[23:16], field[37:8]->lo[63:34],
    field[55:38]->hi[17:0].  (Mirrored in probe_mwarp.py P6a.)"""
    assert va % 16 == 0
    t_lo, t_hi = _ret_template()
    f = va >> 2
    lo = t_lo | ((f & 0xFF) << 16) | (((f >> 8) & 0x3FFFFFFF) << 34)
    hi = t_hi | ((f >> 38) & 0x3FFFF)
    return lo, hi


def _handler_src(retline: int, cmdret: int) -> str:
    t_lo, t_hi = _ret_template()
    t00, t01 = t_lo & 0xFFFFFFFF, t_lo >> 32
    t10, t11 = t_hi & 0xFFFFFFFF, t_hi >> 32
    assert t01 == 0, "template lo_hi expected 0"
    return f"""\
    STL {_slot(0)}, R246;[7:7:{{}}:2:0]
    STL {_slot(1)}, R247;[7:7:{{}}:2:0]
    STL {_slot(2)}, R248;[7:7:{{}}:2:0]
    STL {_slot(3)}, R249;[7:7:{{}}:2:0]
    STL {_slot(4)}, R250;[7:7:{{}}:2:0]
    STL {_slot(5)}, R251;[7:7:{{}}:2:0]
    P2R R246, PR;[7:7:{{}}:4:0]
    STL {_slot(6)}, R246;[7:7:{{}}:2:0]
    RPCMOV.32 R246, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R247, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64.STRONG.GPU [{{R252,R253}}+0x{COMMS + 0x10:x}], {{R246,R247}};[7:7:{{0}}:8:0]
    SHF.R.U32.HI R248, RZ, 0x2, R246;[7:7:{{}}:5:1]
    SHF.L.U32 R250, R247, 0x1E, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R250, R250, R248, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.R.U32.HI R251, RZ, 0x2, R247;[7:7:{{}}:5:1]
    SHF.L.U32 R248, R250, 0x10, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R248, R248, 0xFF0000, RZ, 0xC0;[7:7:{{}}:5:1]
    LOP3.LUT R248, R248, 0x{t00:08x}, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.R.U32.HI R249, RZ, 0x8, R250;[7:7:{{}}:5:1]
    SHF.L.U32 R246, R251, 0x18, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R249, R249, R246, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.L.U32 R249, R249, 0x2, RZ;[7:7:{{}}:5:1]
    SHF.R.U32.HI R250, RZ, 0x6, R251;[7:7:{{}}:5:1]
    LOP3.LUT R250, R250, 0x{t10:08x}, RZ, 0xFC;[7:7:{{}}:5:1]
    MOV32I R251, 0x{t11:08x};[7:7:{{}}:5:1]
    STG.E.128.STRONG.GPU [{{R252,R253}}+0x{retline:x}], {{R248,R249,R250,R251}};[7:7:{{}}:8:0]
    LDG.E.STRONG.GPU R250, [{{R252,R253}}+0x{COMMS + 0x8:x}];[3:7:{{}}:8:0]
    STL {_slot(7)}, R250;[7:7:{{3}}:2:0]
    LDG.E.STRONG.GPU R250, [{{R252,R253}}+0x{COMMS_SEQ:x}];[3:7:{{}}:8:0]
    STL {_slot(8)}, R250;[7:7:{{3}}:2:0]
#def_label(dbgspin)
    LDL R248, {_slot(7)};[0:7:{{}}:4:0]
    LDG.E.STRONG.GPU R249, [{{R252,R253}}+0x{COMMS + 0x8:x}];[1:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R249, R248, PT;[7:7:{{0,1}}:13:1]
    @P0 BRA #label(dbgresume);[7:7:{{}}:6:0]
    LDL R248, {_slot(8)};[0:7:{{}}:4:0]
    LDG.E.STRONG.GPU R249, [{{R252,R253}}+0x{COMMS_SEQ:x}];[1:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R249, R248, PT;[7:7:{{0,1}}:13:1]
    @!P0 BRA #label(dbgspin);[7:7:{{}}:6:0]
    STL {_slot(8)}, R249;[7:7:{{}}:2:0]
    CCTL.I.IVALL;[7:7:{{}}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + f"""    CCTL.I.IVALL;[7:7:{{}}:4:0]
    CALL.ABS.NOINC PT, {{R252,R253}}, 0x{CMD_OFF:x};[7:7:{{}}:6:0]
    BRA #label(dbgspin);[7:7:{{}}:6:0]
#def_label(dbgresume)
    LDL R248, {_slot(6)};[0:7:{{}}:4:0]
    R2P PR, R248;[7:7:{{0}}:13:1]
    LDL R246, {_slot(0)};[0:7:{{}}:4:0]
    LDL R247, {_slot(1)};[1:7:{{}}:4:0]
    LDL R248, {_slot(2)};[2:7:{{}}:4:0]
    LDL R249, {_slot(3)};[3:7:{{}}:4:0]
    LDL R250, {_slot(4)};[4:7:{{}}:4:0]
    LDL R251, {_slot(5)};[5:7:{{}}:4:0]
    CCTL.I.IVALL;[7:7:{{}}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + """    CCTL.I.IVALL;[7:7:{}:4:0]
    RET.ABS.NODEC PT, RZ, 0x0;[7:7:{0,1,2,3,4,5}:8:1]
"""


def _handler_anchors(src: str) -> tuple[int, int]:
    """(retline, cmdret) blob-relative byte offsets for a handler source.
    retline = the final RET (self-overwritten); cmdret = the instruction
    the injected-command buffer RETs to (the BRA right after the CALL,
    which re-enters the spin)."""
    n = 0
    cmdret = None
    for ln in src.splitlines():
        ln = ln.strip()
        if ln.startswith("#def_label"):
            continue
        if ln.startswith("BRA #label(dbgspin)"):
            cmdret = HANDLER_OFF + n * 16
        n += 1
    assert cmdret is not None
    return HANDLER_OFF + (n - 1) * 16, cmdret


def _handler_words() -> tuple[bytes, int, int]:
    """(handler image, retline off, cmdret off).  Two-pass: the STG that
    rewrites the RET line and the command buffer's RET disp both need
    offsets that depend on the instruction count."""
    retline, cmdret = _handler_anchors(_handler_src(0, 0))
    src = _handler_src(retline, cmdret)
    enc = assemble_flat(src)
    retline2, cmdret2 = _handler_anchors(src)
    assert (retline2, cmdret2) == (retline, cmdret)
    assert len(enc) * 16 <= CMD_OFF - HANDLER_OFF, "handler too big"
    return (b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc),
            retline, cmdret)


_EPILOGUE_GUARD = "    EXIT;[7:7:{}:4:0]\n"


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

    max_bps: accepted for v1 API compatibility; since v2 there are no
    slots, so the number of concurrently armed breakpoints is unlimited.

    allow_cdesc_urs: v3 no longer touches ANY uniform register (comms
    are desc-less), so this is accepted for API compatibility and is a
    no-op — wtrace-instrumented sources (UR60/UR61 = default cdesc)
    compose freely."""
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
    n_body = len(assemble_kernel(source, check_deps=True).encoded)
    # safety EXIT before the closing brace (fall-through guard)
    text = "\n".join(out)
    close = text.rstrip().rfind("}")
    text = (text[:close] + _EPILOGUE_GUARD + text[close:])
    info = DebugInfo(text, n_body)
    # validate the whole thing assembles, and self-check the layout
    enc = assemble_kernel(text, check_deps=True).encoded
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
        self.warp: int | None = None    # set by wait_hit


class Debugger:
    """Runtime breakpoints for a dialect-source kernel, multi-warp.

    The kernel is launched with its normal args plus the dbgctrl buffer;
    it parks at the entry gate until release().  Arm breakpoints before
    release (reliable) — mid-run arming works only for code that
    refetches (not tight loops, loop/fetch-buffer replay defeats IVALL).

    Multi-warp / multi-CTA: launch with block=(32*N,), grid=(G,); each
    warp gets its own blob (warpid = SR_CTAID.X*ctawarps + SR_TID.X>>5,
    ctawarps passed via ctrl+0x28).  Every warp arms the same sites (the
    patch word is warp-generic); hits report the hitting warp via
    bp.warp; resume(bp) releases exactly the warps parked at that bp's
    site.
    """

    CTRL_BYTES = 0x30

    def __init__(self, source: str, func: str | None = None,
                 max_bps: int = 0, allow_cdesc_urs: bool = False,
                 max_warps: int = 1):
        self.info = inject_debugger(source, max_bps,
                                    allow_cdesc_urs=allow_cdesc_urs)
        self.mod = CudaModule(assemble(self.info.source, check_deps=True))
        self.encoded = assemble_kernel(self.info.source,
                                       check_deps=True).encoded
        self.func = func or self._only_function()
        self.patcher = Patcher()
        self.max_warps = max_warps
        self.ctrl = self.mod.devmem_alloc(self.CTRL_BYTES)
        self.mod.device_write(self.ctrl, bytes(self.CTRL_BYTES))
        self.blobs = self.mod.devmem_alloc(max_warps * BLOB_SZ)
        words, self.retline_off, self.cmdret_off = _handler_words()
        for w in range(max_warps):
            base = self.blobs + w * BLOB_SZ
            self.mod.device_write(base + COMMS, bytes(0x20))
            self.mod.device_write(base + HANDLER_OFF, words)
        self._wr64(0x20, self.blobs)    # prologue loads the blob base
        self.stream = CudaModule.stream_create()
        self._bps: dict[int, Breakpoint] = {}
        self._by_index: dict[int, Breakpoint] = {}
        self._next_id = 1
        self._gens = [0] * max_warps
        self._cmds = [0] * max_warps
        self._parked: dict[int, Breakpoint] = {}    # warp -> bp
        self._patch_base = _call_word()

    def _only_function(self) -> str:
        m = re.search(r"#fn\s+(\w+)", self.info.source)
        assert m
        return m.group(1)

    def _blob(self, warp: int) -> int:
        return self.blobs + warp * BLOB_SZ

    # -- lifecycle -----------------------------------------------------------
    def launch(self, args: list, grid=(1,), block=(32,)) -> None:
        """Launch the target (args = the kernel's normal args); it parks
        at the gate.  dbgctrl is appended automatically.  1-D grid/block;
        multi-CTA capable (warpid = CTAID.X*ctawarps + tid.x>>5).
        HARD constraint: all CTAs must be CO-RESIDENT — parked warps
        never exit, so a grid exceeding the GPU's resident capacity
        deadlocks at the gate."""
        if tuple(grid[1:]) not in ((), (1, 1)) or \
                tuple(block[1:]) not in ((), (1, 1)):
            raise ValueError("only 1-D grid/block supported")
        warps_per_cta = (block[0] + 31) // 32
        warps = grid[0] * warps_per_cta
        if warps > self.max_warps:
            raise ValueError(f"launch needs {warps} warps, "
                             f"max_warps={self.max_warps}")
        self.n_warps = warps
        self.warps_per_cta = warps_per_cta
        self._wr32(0x28, warps_per_cta)
        for w in range(warps):
            self.mod.device_write(self._blob(w) + COMMS, bytes(0x20))
            self._gens[w] = 0
        self._parked.clear()
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

    def _hit(self, warp: int) -> int:
        return struct.unpack("<Q", self.mod.device_read(
            self._blob(warp) + COMMS + 0x10, 8))[0]

    def wait_base(self, timeout: float = 5.0) -> int:
        t0 = time.time()
        while True:
            lo, hi = self._rd32(0x0), self._rd32(0x4)
            if lo or hi:
                break
            if time.time() - t0 > timeout:
                raise TimeoutError("target did not report its code base")
            time.sleep(0.001)
        return ((hi << 32) | lo) - 1 * 16      # LEPC = prologue inst 1

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
        """Patch the site word with the CALL into the blob handler."""
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

    def _bp_for_va(self, va: int) -> Breakpoint:
        inj = (va - self.base()) // 16
        orig = inj - PROLOGUE_LEN
        bp = self._by_index.get(orig)
        if bp is None:
            raise RuntimeError(
                f"hit from unarmed site {hex(va)} (orig {orig})")
        return bp

    def wait_hit(self, timeout: float = 30.0) -> Breakpoint:
        """Wait until a breakpoint parks a warp; returns the bp with
        bp.warp set.  Records ALL currently-parked warps, so a following
        wait_hit returns other warps' already-pending hits."""
        t0 = time.time()
        while True:
            for w in range(self.max_warps):
                if w in self._parked:
                    continue
                va = self._hit(w)
                if va:
                    bp = self._bp_for_va(va)
                    bp.warp = w
                    self._parked[w] = bp
                    return bp
            if time.time() - t0 > timeout:
                raise TimeoutError("no breakpoint hit")
            time.sleep(0.001)

    # -- command injection (M7) ----------------------------------------------
    def exec_cmd(self, warp: int, insts: list[str],
                 timeout: float = 5.0, _trusted: bool = False) -> None:
        """Assemble `insts` (dialect lines) into the warp's command
        buffer (blob+CMD_OFF), and have the PARKED handler execute them
        (CALL/RET round-trip, hardened IVALL covers the refetch), then
        return to the park spin.  Repeatable any number of times until
        resume().

        Contract for command code:
          * R246-R251 and P0-P6 are free scratch (the kernel's values
            live in local spill slots 0-6; the kernel's R246-R251 / PR
            are dumped or set by LD[ST]L on those slots, see
            dump_regs/set_reg).
          * MUST NOT touch R252/R253 (blob base; the handler's comms
            and the command's own RET depend on it).
          * Straight-line only: no BRA/CALL/RET/JMX/BRX/EXIT/BSSY/BSYNC.
          * Read results back via STG.E.STRONG.GPU to
            [{R252,R253}+0x{COMMS_RESULTS:x}+...] and device_read.
        """
        import time as _time
        if warp not in self._parked:
            raise RuntimeError(f"warp {warp} not parked")
        if not _trusted:
            for ln in insts:
                body_ln = re.sub(r"^\s*@!?P[T0-6]\s*", "", ln).strip()
                # R252/R253 as a WRITE destination is fatal (blob base);
                # read-only use (e.g. STG address base) is fine
                parts = body_ln.split(None, 1)
                dest = parts[1].split(",")[0].strip() if len(parts) > 1 \
                    else ""
                if re.fullmatch(r"\{?R25[23]\}?", dest):
                    raise ValueError(
                        f"command may not write R252/R253: {ln}")
                if re.match(r"(BRA|CALL|RET|JMX|BRX|EXIT|KILL|BSSY|BSYNC)\b",
                            body_ln):
                    raise ValueError(f"no control flow in commands: {ln}")
        if len(insts) > 60:
            raise ValueError("command too long (max 60 instructions)")
        body = "\n".join(f"    {ln}" for ln in insts)
        src = f"""{body}
    LDG.E.STRONG.GPU R246, [{{R252,R253}}+0x{COMMS_SEQ:x}];[2:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R252,R253}}+0x{COMMS_ACK:x}], R246;[7:7:{{2}}:8:0]
    RET.ABS.NODEC PT, {{R252,R253}}, 0x{self.cmdret_off:x};[7:7:{{}}:5:1]
"""
        enc = assemble_flat(src)
        assert enc, "command assembled to nothing"
        blob = self._blob(warp)
        self.mod.device_write(blob + CMD_OFF,
                              b"".join(struct.pack("<QQ", lo, hi)
                                       for lo, hi in enc))
        self._cmds[warp] += 1
        seq = self._cmds[warp]
        self.mod.device_write(blob + COMMS_SEQ, struct.pack("<I", seq))
        t0 = _time.time()
        while struct.unpack("<I", self.mod.device_read(
                blob + COMMS_ACK, 4))[0] != seq:
            if _time.time() - t0 > timeout:
                raise TimeoutError(f"command ack timeout (warp {warp})")
            _time.sleep(0.001)

    def cmd_read(self, warp: int, off: int, size: int) -> bytes:
        """Read the command result scratch (COMMS_RESULTS+off)."""
        return bytes(self.mod.device_read(self._blob(warp)
                                          + COMMS_RESULTS + off, size))

    _LANE_PRELUDE = [
        "S2R R250, SR_TID.X;[5:7:{}:5:1]",
        "LOP3.LUT R250, R250, 0x1F, RZ, 0xC0;[7:7:{}:5:1]",
        "IMAD R248, R250, 0x4, R252;[7:7:{}:5:1]",   # low blob VA + lane*4
        "MOV R249, R253;[7:7:{}:5:1]",               # {R248,R249} addr pair
    ]

    def dump_regs(self, warp: int, regs: list[str],
                  lane: int = 0) -> dict[str, int]:
        """Dump register values from a parked warp (one lane).  R246-R251
        and PR are transparently read from the per-lane local spill slots
        (the live registers hold handler scratch while parked); everything
        else is read directly.  Returns {name: value}."""
        if not 0 <= lane < 32:
            raise ValueError("lane out of range")
        insts: list[str] = list(self._LANE_PRELUDE)
        out: dict[str, int] = {}
        for i, r in enumerate(regs):
            dst_s = f"0x{COMMS + 0x100 + 4 * (i * 32):x}"
            m = re.fullmatch(r"R(\d+)", r.upper())
            if r.upper() == "PR":
                insts += [
                    f"LDL R251, {_slot(6)};[2:7:{{}}:13:1]",
                    f"STG.E.STRONG.GPU [{{R248,R249}}+{dst_s}], R251;"
                    f"[7:7:{{2}}:8:0]",
                ]
            elif m and 246 <= int(m.group(1)) <= 251:
                k = int(m.group(1)) - 246
                insts += [
                    f"LDL R251, {_slot(k)};[2:7:{{}}:13:1]",
                    f"STG.E.STRONG.GPU [{{R248,R249}}+{dst_s}], R251;"
                    f"[7:7:{{2}}:8:0]",
                ]
            elif m:
                insts.append(
                    f"STG.E.STRONG.GPU [{{R248,R249}}+{dst_s}], "
                    f"{r.upper()};[7:7:{{}}:8:0]")
            else:
                raise ValueError(f"cannot dump {r!r} (use exec_cmd)")
        self.exec_cmd(warp, insts, _trusted=True)
        data = self.cmd_read(warp, 0, 4 * 32 * len(regs))
        for i, r in enumerate(regs):
            off = 4 * (i * 32 + lane)
            out[r.upper()] = struct.unpack("<I", data[off:off + 4])[0]
        return out

    def set_reg(self, warp: int, reg: str, val: int, lane: int = 0) -> None:
        """Set a register of a parked warp (one lane).  R246-R251 / PR
        write the spill slot (the resume path restores from there);
        anything else writes the live register directly."""
        if not 0 <= lane < 32:
            raise ValueError("lane out of range")
        r = reg.upper()
        m = re.fullmatch(r"R(\d+)", r)
        pre = self._LANE_PRELUDE[:2] + [
            f"ISETP.EQ.AND P0, PT, R250, {lane}, PT;[7:7:{{}}:13:1]"]
        if r == "PR":
            insts = pre + [f"MOV32I R249, 0x{val:x};[7:7:{{}}:5:1]",
                           f"@P0 STL {_slot(6)}, R249;[7:7:{{}}:2:0]"]
        elif m and 246 <= int(m.group(1)) <= 251:
            insts = pre + [f"MOV32I R249, 0x{val:x};[7:7:{{}}:5:1]",
                           f"@P0 STL {_slot(int(m.group(1)) - 246)}, R249;"
                           f"[7:7:{{}}:2:0]"]
        elif m:
            if int(m.group(1)) in (252, 253):
                raise ValueError("R252/R253 are debugger-reserved")
            insts = pre + [f"@P0 MOV32I {r}, 0x{val:x};[7:7:{{}}:5:1]"]
        else:
            raise ValueError(f"cannot set {reg!r} (use exec_cmd)")
        self.exec_cmd(warp, insts, _trusted=True)

    def resume(self, bp: Breakpoint) -> None:
        """Restore the site, then bump the generation of every warp
        parked at this bp's site: each parked handler restores the
        kernel's PRs and registers, self-invalidates, and RETs back to
        the site, re-executing the restored original instruction.  The
        breakpoint is CONSUMED (site keeps its original word) — to break
        again, re-arm.  Re-arming mid-run against a tight loop is
        unreliable (loop replay); prefer arming at the gate."""
        site = self._site_va(bp.orig_index)
        self.patcher.patch(site, bp.orig_word)           # restore
        for w, wbp in list(self._parked.items()):
            if wbp is bp:
                self.mod.device_write(self._blob(w) + COMMS + 0x10,
                                      struct.pack("<Q", 0))
                self._gens[w] += 1
                self.mod.device_write(self._blob(w) + COMMS + 0x8,
                                      struct.pack("<I", self._gens[w]))
                del self._parked[w]
        bp.armed = False
        del self._bps[bp.id]
        del self._by_index[bp.orig_index]
