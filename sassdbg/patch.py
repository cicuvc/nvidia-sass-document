"""sassdbg debugger — runtime SASS breakpoints with ZERO register
reservation (M9 engine; replaces the M3v3 per-warp-blob design).

Motivation: real cubins have a compile-time register budget — a kernel
may legitimately use every register, so no reservation is safe (ptxas
guarantees >= 24 registers, so R0-R21 always exist and may be borrowed
with spill/restore).  SETLMEMBASE/LMEM is abandoned entirely (the base
is warp-shared and disturbs sibling execution groups' local memory —
see tests/asm_construct/probe_setlmembase_lanes.py).

Architecture (probe_stub.py / probe_stub2.py verified):

  * patch word = per-site constant `JMP <stub_va>` (JMP IMM 0x94a,
    UImm(57) SCALE 4 — absolute, preserves RPC).
  * per-bp STUB (0x200 slot, shared across warps; borrows R0/R1 via
    RPC spill — RPCMOV Rpc.LO/HI write forms, probe_rpc_write.py):
    spills kernel R2/R3 + R0/R1 (from RPC) + the baked site VA into the
    lane's FRAME, then CALL.ABS {R2,R3} into the PER-WARP handler copy
    (gwarp recovered from the frame address; CALL clobbers RPC — dead
    by then).  f = CTAID*(ctawarps*32) + TID is the global lane-frame
    index (gwarp*32+lane == ctaid*(ctawarps*32)+tid).
  * per-warp HANDLER copy (borrows R2-R7 + P0, spill-restored through
    the frame): spills R4-R7+PR, reads the release baseline BEFORE the
    hit report (host race), leader-only (FLO(MACTIVE)) hit-slot RMW
    into the GLOBAL HSLOTS[slot = leader's f], spins on
    NANOSLEEP 0x100 + per-lane release generation (+ M7 command poll),
    on release: loads the thunk VA from the frame, composes a
    `RET.ABS.NODEC RZ, <thunk_va>` over its OWN last line (bit surgery,
    hardened IVALL — M3v3 machinery, per-warp copy = no retline
    sharing), restores PR/R2-R7 (LDG chain on SB2), self-restores
    kernel R0/R1 with one `LDG.E.64 {R0,R1}, [{R0,R1}+0x20]` +
    `MOV R1, R1` req-wait, and falls into the composed RET -> thunk.
  * THUNK (per release, host-built, global bump arena): `replay … ;
    JMP <target>` — target = site+0x10 (plain resume; the site stays
    patched = persistent bp, M8a) or an armed successor's site VA
    (stepper).  The replay carries req{2} covering every restore LDG.

Probe-phase lessons baked in (see AGENTS.md M9 section):
  NON_BLOCKING stream for parked launches; 8B-aligned 64-bit frame
  slots; R2P/ISETP need yield=1 at stall 13; baseline-before-report;
  code-fetch VAs 16B-aligned; assert every code image fits its slot.
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
from assembler import arch as _arch                          # noqa: E402

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
# layout
# ---------------------------------------------------------------------------
FRAME = 0x80                    # per (gwarp, lane) frame in the pool
F_R2 = 0x00                     # R2..R7 spill (6 x 4B, through +0x14)
F_PR = 0x18                     # P2R PR snapshot
F_R01 = 0x20                    # kernel R0/R1 (8B — 8B-aligned, fault 716)
F_SITE = 0x28                   # site VA (8B, stub-baked)
F_RELEASE = 0x30                # u32 per-lane release generation
F_F = 0x34                      # u32 global lane-frame index
F_RTGT = 0x38                   # u64 thunk VA for the pending release
F_CMD = 0x40                    # u32 per-lane command baseline
F_RELBASE = 0x44                # u32 release-baseline save across an
F_GOBASE = 0x48                 #   injected command (commands may
                                #   clobber R2-R7; F_GOBASE at 0x48)

STUB_OFF = 0x100                # after the ctrl block
STUB_SZ = 0x200                 # per-bp stub slot (32 insts; stub ~24)
HANDLER_STRIDE = 0x1000         # per-warp handler copy (256 insts max)
THUNK_ARENA = 0x10000
THUNK_STRIDE = 0x100            # 16 insts per thunk slot
THUNK_MAX_INSTS = THUNK_STRIDE // 16
CMDBUF_SZ = 0x400               # per-warp command buffer (64 insts)
RESULTS_SZ = 0x400              # per-warp command result window


class Layout:
    """Arena offsets derived from (max_bps, max_warps)."""

    def __init__(self, max_bps: int, max_warps: int):
        self.max_bps = max_bps
        self.max_warps = max_warps
        self.handler_off = STUB_OFF + max_bps * STUB_SZ
        self.thunk_off = self.handler_off + max_warps * HANDLER_STRIDE
        self.comms = self.thunk_off + THUNK_ARENA
        self.hslots = self.comms                 # mw*32 x 16B hit slots
        self.go = self.hslots + max_warps * 32 * 16  # mw x 16B; the
        # per-warp GO word (at +0) releases a whole warp's parked lanes
        # in ONE poll window — host bumps per-lane F_RELEASE/F_RTGT
        # first, GO last; lanes then check their own F_RELEASE in the
        # same converged poll, so a released group exits TOGETHER (no
        # per-lane drip -> no fragmented thunk BAR/WARPSYNC arrivals).
        # cmdseq entries are 16B so cmdbuf stays 16-ALIGNED (an 8-aligned
        # command-buffer VA faults the dispatch CALL with 718 INVALID_PC
        # — instruction fetch requires 16B alignment)
        self.cmdseq = self.go + max_warps * 16   # mw x 16B
        self.cmdbuf = self.cmdseq + max_warps * 16
        self.results = self.cmdbuf + max_warps * CMDBUF_SZ
        self.pool = self.results + max_warps * RESULTS_SZ
        self.total = self.pool + max_warps * 32 * FRAME

    def handler_va(self, arena: int, warp: int) -> int:
        return arena + self.handler_off + warp * HANDLER_STRIDE

    def frame_va(self, arena: int, f: int) -> int:
        return arena + self.pool + f * FRAME


# ctrl block (arena+0): the dbgctrl param points at the arena base
CTRL_BASE = 0x00                # u64 code-base report (LEPC)
CTRL_GATE = 0x08                # u32 start-gate flag

# ---------------------------------------------------------------------------
# prologue (no register reservation; entry state is architecturally
# undefined, so the prologue may clobber R4-R9 outright)
# ---------------------------------------------------------------------------
_PROLOGUE = """    LDC.64 {R4,R5}, #param(dbgctrl);[1:7:{}:8:0]
    LEPC {R8,R9};[7:7:{}:4:0]
    STG.E.64.STRONG.GPU [{R4,R5}], {R8,R9};[7:7:{1}:8:0]
#def_label(dbggate)
    LDG.E.STRONG.GPU R6, [{R4,R5}+0x8];[2:7:{}:8:0]
    ISETP.NE.AND P0, PT, R6, 0x0, PT;[7:7:{2}:13:1]
    @!P0 BRA #label(dbggate);[7:7:{}:6:0]
    CCTL.I.IVALL;[7:7:{}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + """    CCTL.I.IVALL;[7:7:{}:4:0]
"""
PROLOGUE_LEN = sum(1 for ln in _PROLOGUE.splitlines() if ";[" in ln)

_FN_RE = re.compile(r"^(#fn\s+\w+)\(([^)]*)\)\s*\{\s*$")

_EPILOGUE_GUARD = "    EXIT;[7:7:{}:4:0]\n"


class DebugInfo:
    """Layout metadata of an injected source."""
    def __init__(self, source: str, n_body: int):
        self.source = source
        self.n_body = n_body

    def injected_index(self, orig_index: int) -> int:
        if not 0 <= orig_index < self.n_body:
            raise IndexError(orig_index)
        return orig_index + PROLOGUE_LEN


def inject_debugger(source: str, max_bps: int = 0,
                    allow_cdesc_urs: bool = False) -> DebugInfo:
    """Inject the debugger prologue into a single-function dialect source.

    The function gains a trailing `dbgctrl<8>` parameter the host must
    pass (the arena base VA).  M9 reserves NO registers — every kernel
    register is preserved through breakpoints (R0/R1 via the RPC spill
    in the stub, R2-R7/PR via the per-lane frame)."""
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
    n_body = len(assemble_kernel(source, check_deps=True).encoded)
    text = "\n".join(out)
    close = text.rstrip().rfind("}")
    text = (text[:close] + _EPILOGUE_GUARD + text[close:])
    info = DebugInfo(text, n_body)
    enc = assemble_kernel(text, check_deps=True).encoded
    assert len(enc) == PROLOGUE_LEN + n_body + 1, "injected layout mismatch"
    return info


# ---------------------------------------------------------------------------
# stub (per bp, shared across warps): spill R0/R1 (via RPC) + R2/R3 +
# the baked site VA into the lane's frame, then CALL.ABS into the
# PER-WARP handler copy (gwarp recovered from the frame address).
# ---------------------------------------------------------------------------
def _stub_src(site_va: int, k: int, pool: int, h0: int) -> str:
    """k = ctawarps*32, pool = pool base VA, h0 = handler area base VA
    (0x1000-aligned).  pool_lo + (mw*32-1)*FRAME must not carry."""
    return f"""\
    RPCMOV Rpc.LO, R0;[3:7:{{}}:9:0]
    RPCMOV Rpc.HI, R1;[4:7:{{}}:9:0]
    S2R R0, SR_CTAID.X;[5:7:{{}}:5:1]
    IMAD R0, R0, 0x{k:x}, RZ;[7:7:{{5}}:5:1]
    S2R R1, SR_TID.X;[5:7:{{}}:5:1]
    IADD3 R0, R0, R1, RZ;[7:7:{{5}}:5:1]
    MOV32I R1, 0x{pool & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    IMAD R0, R0, 0x{FRAME:x}, R1;[7:7:{{5}}:5:1]
    MOV32I R1, 0x{pool >> 32:08x};[7:7:{{}}:5:1]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2:x}], R2;[7:1:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 4:x}], R3;[7:1:{{}}:8:0]
    RPCMOV R2, Rpc.LO;[2:7:{{1,3}}:9:0]
    RPCMOV R3, Rpc.HI;[2:7:{{1,4}}:9:0]
    STG.E.64.STRONG.GPU [{{R0,R1}}+0x{F_R01:x}], {{R2,R3}};[7:1:{{2}}:8:0]
    MOV32I R2, 0x{site_va & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R3, 0x{site_va >> 32:08x};[7:7:{{}}:5:1]
    STG.E.64.STRONG.GPU [{{R0,R1}}+0x{F_SITE:x}], {{R2,R3}};[7:1:{{}}:8:0]
    MOV32I R2, 0x{pool & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    IADD3 R2, R0, -R2, RZ;[7:7:{{}}:5:1]
    SHF.R.U32.HI R2, RZ, 0xC, R2;[7:7:{{}}:5:1]
    SHF.L.U32 R2, R2, 0xC, RZ;[7:7:{{}}:5:1]
    IADD3 R2, R2, 0x{h0 & 0xFFFFFFFF:08x}, RZ;[7:7:{{}}:13:1]
    MOV32I R3, 0x{h0 >> 32:08x};[7:7:{{}}:13:1]
    CALL.ABS.NOINC PT, {{R2,R3}}, 0x0;[7:7:{{}}:6:0]
"""


# ---------------------------------------------------------------------------
# handler (one copy per warp; borrows R2-R7 + P0, spill-restored via the
# frame; RPC is DEAD on entry — the stub already stashed kernel R0/R1)
# ---------------------------------------------------------------------------
def _ret_template() -> tuple[int, int]:
    """(lo64, hi64) of `RET.ABS.NODEC PT, RZ, 0x0` — the runtime-composed
    word inherits everything but the imm field."""
    return assemble_flat(
        "    RET.ABS.NODEC PT, RZ, 0x0;[7:7:{}:5:1]\n")[0]


def _ret_surgery(t00: int, t10: int, t11: int) -> str:
    """Compose the RET-imm word from the 64-bit VA in R2 (lo) / R3 (hi)
    into {R4,R5,R6,R7}.  Clobbers R2-R7.  (imm = va>>2, SCALE 4:
    field[7:0]->lo[23:16], [37:8]->lo[63:34], [55:38]->hi[17:0].)"""
    return f"""\
    SHF.R.U32.HI R4, RZ, 0x2, R2;[7:7:{{2}}:5:1]
    SHF.L.U32 R6, R3, 0x1E, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R6, R6, R4, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.R.U32.HI R7, RZ, 0x2, R3;[7:7:{{}}:5:1]
    SHF.L.U32 R4, R6, 0x10, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R4, R4, 0xFF0000, RZ, 0xC0;[7:7:{{}}:5:1]
    LOP3.LUT R4, R4, 0x{t00:08x}, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.R.U32.HI R5, RZ, 0x8, R6;[7:7:{{}}:5:1]
    SHF.L.U32 R2, R7, 0x18, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R5, R5, R2, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.L.U32 R5, R5, 0x2, RZ;[7:7:{{}}:5:1]
    SHF.R.U32.HI R6, RZ, 0x6, R7;[7:7:{{}}:5:1]
    LOP3.LUT R6, R6, 0x{t10:08x}, RZ, 0xFC;[7:7:{{}}:5:1]
    MOV32I R7, 0x{t11:08x};[7:7:{{}}:5:1]
"""


def _handler_src(lay: Layout, arena: int, warp: int,
                 retline: int, cmdret: int) -> str:
    pool = arena + lay.pool
    hslots = arena + lay.hslots
    go = arena + lay.go + warp * 16
    cmdseq = arena + lay.cmdseq + warp * 16
    cmdbuf = arena + lay.cmdbuf + warp * CMDBUF_SZ
    self_va = lay.handler_va(arena, warp)
    t_lo, t_hi = _ret_template()
    t00, t01 = t_lo & 0xFFFFFFFF, t_lo >> 32
    t10, t11 = t_hi & 0xFFFFFFFF, t_hi >> 32
    assert t01 == 0, "template lo_hi expected 0"
    ret_va = self_va + retline
    return f"""\
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 8:x}], R4;[7:0:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 0xC:x}], R5;[7:0:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 0x10:x}], R6;[7:0:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 0x14:x}], R7;[7:0:{{}}:8:0]
    P2R R2, PR;[2:7:{{1}}:6:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_PR:x}], R2;[7:0:{{2}}:8:0]
    LDG.E.STRONG.GPU R6, [{{R0,R1}}+0x{F_RELEASE:x}];[2:7:{{0}}:8:0]
    MOV32I R4, 0x{go & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R5, 0x{go >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R7, [{{R4,R5}}];[3:1:{{}}:8:0]
    LDG.E.64.STRONG.GPU {{R2,R3}}, [{{R0,R1}}+0x{F_SITE:x}];[4:7:{{}}:8:0]
    MOV32I R4, 0x{pool & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    IADD3 R4, R0, -R4, RZ;[7:7:{{}}:5:1]
    SHF.R.U32.HI R4, RZ, 0x7, R4;[7:7:{{}}:5:1]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_F:x}], R4;[7:1:{{}}:8:0]
    ELECT P6, URZ, PT;[7:7:{{}}:13:1]
    MOV32I R5, 0x{hslots & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    IMAD R4, R4, 0x10, R5;[7:7:{{1}}:5:1]
    MOV32I R5, 0x{hslots >> 32:08x};[7:7:{{}}:5:1]
    @P6 STG.E.STRONG.GPU [{{R4,R5}}+0x4], R2;[7:1:{{4}}:8:0]
    @P6 STG.E.STRONG.GPU [{{R4,R5}}+0x8], R3;[7:1:{{}}:8:0]
    @P6 BMOV R2, MACTIVE;[4:7:{{1}}:8:0]
    @P6 STG.E.STRONG.GPU [{{R4,R5}}], R2;[7:1:{{4}}:8:0]
    @P6 LDG.E.STRONG.GPU R3, [{{R4,R5}}+0xC];[4:1:{{1}}:8:0]
    @P6 IADD3 R3, R3, 0x1, RZ;[7:7:{{4}}:5:1]
    @P6 STG.E.STRONG.GPU [{{R4,R5}}+0xC], R3;[7:1:{{4}}:8:0]
#def_label(dbgspin)
    NANOSLEEP 0x100;[7:7:{{}}:5:1]
    MOV32I R4, 0x{go & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R5, 0x{go >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R2, [{{R4,R5}}];[3:1:{{}}:8:0]
    ISETP.NE.AND P0, PT, R2, R7, PT;[7:7:{{3}}:13:1]
    @!P0 BRA #label(dbgcmd);[7:7:{{}}:6:0]
    MOV R7, R2;[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_RELEASE:x}];[2:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R2, R6, PT;[7:7:{{2}}:13:1]
    @P0 BRA #label(dbgresume);[7:7:{{}}:6:0]
    BRA #label(dbgspin);[7:7:{{}}:6:0]
#def_label(dbgcmd)
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_CMD:x}];[2:7:{{}}:8:0]
    MOV32I R4, 0x{cmdseq & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R5, 0x{cmdseq >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R3, [{{R4,R5}}];[3:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R3, R2, PT;[7:7:{{2,3}}:13:1]
    @!P0 BRA #label(dbgspin);[7:7:{{}}:6:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_CMD:x}], R3;[7:1:{{3}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_RELBASE:x}], R6;[7:1:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_GOBASE:x}], R7;[7:1:{{}}:8:0]
    CCTL.I.IVALL;[7:7:{{}}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + f"""    CCTL.I.IVALL;[7:7:{{}}:4:0]
    MOV32I R2, 0x{cmdbuf & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{cmdbuf >> 32:08x};[7:7:{{}}:13:1]
    CALL.ABS.NOINC PT, {{R2,R3}}, 0x0;[7:7:{{}}:6:0]
    LDG.E.STRONG.GPU R6, [{{R0,R1}}+0x{F_RELBASE:x}];[2:7:{{1}}:8:0]
    LDG.E.STRONG.GPU R7, [{{R0,R1}}+0x{F_GOBASE:x}];[3:7:{{}}:8:0]
    BRA #label(dbgspin);[7:7:{{}}:6:0]
#def_label(dbgresume)
    LDG.E.64.STRONG.GPU {{R2,R3}}, [{{R0,R1}}+0x{F_RTGT:x}];[2:7:{{}}:8:0]
""" + _ret_surgery(t00, t10, t11) + f"""\
    MOV32I R2, 0x{ret_va & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{ret_va >> 32:08x};[7:7:{{}}:5:1]
    STG.E.128.STRONG.GPU [{{R2,R3}}], {{R4,R5,R6,R7}};[7:1:{{}}:8:0]
    CCTL.I.IVALL;[7:7:{{}}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + f"""    CCTL.I.IVALL;[7:7:{{}}:4:0]
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_PR:x}];[2:7:{{1}}:8:0]
    R2P PR, R2, 0x7F;[7:7:{{2}}:13:1]
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_R2:x}];[2:7:{{}}:8:0]
    LDG.E.STRONG.GPU R3, [{{R0,R1}}+0x{F_R2 + 4:x}];[2:7:{{}}:8:0]
    LDG.E.STRONG.GPU R4, [{{R0,R1}}+0x{F_R2 + 8:x}];[2:7:{{}}:8:0]
    LDG.E.STRONG.GPU R5, [{{R0,R1}}+0x{F_R2 + 0xC:x}];[2:7:{{}}:8:0]
    LDG.E.STRONG.GPU R6, [{{R0,R1}}+0x{F_R2 + 0x10:x}];[2:7:{{}}:8:0]
    LDG.E.STRONG.GPU R7, [{{R0,R1}}+0x{F_R2 + 0x14:x}];[2:7:{{}}:8:0]
    LDG.E.64.STRONG.GPU {{R0,R1}}, [{{R0,R1}}+0x{F_R01:x}];[2:7:{{}}:8:0]
    MOV R1, R1;[7:7:{{2}}:5:1]
    RET.ABS.NODEC PT, RZ, 0x0;[7:7:{{}}:5:1]
"""


def _handler_anchors(src: str) -> tuple[int, int]:
    """(retline, cmdret) handler-relative byte offsets.  retline = the
    final RET (self-overwritten); cmdret = the first instruction after
    the command CALL (reloads the release/GO baselines the command may
    have clobbered, then re-enters the spin)."""
    n = 0
    cmdret = None
    prev_call = False
    for ln in src.splitlines():
        ln = ln.strip()
        if ln.startswith("#def_label"):
            continue
        if prev_call and cmdret is None:
            cmdret = n * 16
        prev_call = ln.startswith("CALL.ABS")
        n += 1
    assert cmdret is not None
    return (n - 1) * 16, cmdret


def _handler_image(lay: Layout, arena: int, warp: int,
                   ) -> tuple[bytes, int, int]:
    """(image, retline off, cmdret off) — two-pass: the baked retline VA
    depends on the instruction count."""
    retline, cmdret = _handler_anchors(
        _handler_src(lay, arena, warp, 0, 0))
    src = _handler_src(lay, arena, warp, retline, cmdret)
    enc = assemble_flat(src)
    anchors2 = _handler_anchors(src)
    assert anchors2 == (retline, cmdret)
    assert len(enc) * 16 <= HANDLER_STRIDE, "handler too big"
    return (b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc),
            retline, cmdret)


# ---------------------------------------------------------------------------
# host-side debugger
# ---------------------------------------------------------------------------
class Breakpoint:
    def __init__(self, dbg: "Debugger", bp_id: int, orig_index: int,
                 orig_word: tuple[int, int], slot: int):
        self.dbg = dbg
        self.id = bp_id
        self.orig_index = orig_index    # index in the ORIGINAL source
        self.orig_word = orig_word
        self.slot = slot                # stub slot (site identity in code)
        self.armed = True
        self.warp: int | None = None    # set by wait_hit


class _Group:
    """One parked execution group of a warp.  Identity = (warp, leader
    slot); parked groups of a warp have pairwise-disjoint lane masks."""
    __slots__ = ("mask", "bp", "slot", "reported")

    def __init__(self, mask: int, bp: Breakpoint, slot: int):
        self.mask = mask
        self.bp = bp
        self.slot = slot            # leader's global lane-frame index
        self.reported = False


class Debugger:
    """Runtime breakpoints for a dialect-source kernel — zero register
    reservation (M9).

    The kernel is launched with its normal args plus dbgctrl (the arena
    base, appended automatically); it parks at the entry gate until
    release().  Arm breakpoints before release (reliable) — mid-run
    arming works only for code that refetches (loop/fetch-buffer replay
    defeats IVALL in tight loops).

    Multi-warp / multi-CTA: launch with block=(32*N,), grid=(G,);
    f = CTAID*(ctawarps*32) + TID indexes frames/hit slots globally.
    HARD constraint: all CTAs must be CO-RESIDENT — parked warps never
    exit, so a grid exceeding resident capacity deadlocks at the gate.
    """

    def __init__(self, source: str, func: str | None = None,
                 max_bps: int = 16, allow_cdesc_urs: bool = False,
                 max_warps: int = 1):
        self.info = inject_debugger(source, max_bps,
                                    allow_cdesc_urs=allow_cdesc_urs)
        self.mod = CudaModule(assemble(self.info.source, check_deps=True))
        res = assemble_kernel(self.info.source, check_deps=True)
        self.encoded = res.encoded
        self.res_params = res.params
        self.func = func or self._only_function()
        self.patcher = Patcher()
        self.max_warps = max_warps
        self.lay = Layout(max_bps, max_warps)
        self.arena = self.mod.devmem_alloc(self.lay.total)
        assert self.arena % 16 == 0, "arena base must be 16-aligned"
        pool = self.arena + self.lay.pool
        assert (pool & 0xFFFFFFFF) + max_warps * 32 * FRAME \
            < 0x100000000, "pool lo32 carry — realign"
        # zero the lot (frames' release/cmd/rtgt state, hit slots, ctrl)
        self.mod.device_write(self.arena, bytes(self.lay.total))
        # per-warp handler copies (retline restored on every launch too)
        self._hdl = [self._write_handler(w) for w in range(max_warps)]
        self.stream = CudaModule.stream_create()
        self._bps: dict[int, Breakpoint] = {}
        self._by_index: dict[int, Breakpoint] = {}
        self._free_slots = list(range(max_bps))
        self._next_id = 1
        self._groups: dict[int, list[_Group]] = \
            {w: [] for w in range(max_warps)}
        self._seen = [0] * (max_warps * 32)
        self._rlgen = [[0] * 32 for _ in range(max_warps)]
        self._cmds = [0] * max_warps
        self._go = [0] * max_warps
        self._thunk_next = 0
        self._thunk_cache: dict[tuple, int] = {}
        self.n_warps = 0
        self.warps_per_cta = 1

    # -- setup helpers --------------------------------------------------------
    def _only_function(self) -> str:
        m = re.search(r"#fn\s+(\w+)", self.info.source)
        assert m
        return m.group(1)

    def _write_handler(self, warp: int) -> tuple[int, int]:
        img, retline, cmdret = _handler_image(self.lay, self.arena, warp)
        self.mod.device_write(self.lay.handler_va(self.arena, warp), img)
        return retline, cmdret

    def _stub_va(self, slot: int) -> int:
        return self.arena + STUB_OFF + slot * STUB_SZ

    def _write_stub(self, bp: Breakpoint) -> None:
        site = self._site_va(bp.orig_index)
        k = self.warps_per_cta * 32
        h0 = self.arena + self.lay.handler_off
        src = _stub_src(site, k, self.arena + self.lay.pool, h0)
        enc = assemble_flat(src)
        assert 0 < len(enc) <= STUB_SZ // 16, "stub too big"
        self.mod.device_write(
            self._stub_va(bp.slot),
            b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc))

    def _jmp_word(self, va: int) -> tuple[int, int]:
        # req={0..5}: the patch word must wait for ALL outstanding
        # scoreboarded producers before transferring control — the
        # original instruction's bracket only covered ITS sources, but
        # the stub spills R0-R7+PR wholesale, and an in-flight LDG/LDC/
        # S2R into ANY of them would otherwise be captured pre-write
        # (observed: FFMA bp hit with the a[i] LDG still in flight ->
        # R2 spilled as the pre-LDG address; m3w: handler spilled R4/R5
        # before the param LDC landed -> resume restored garbage -> 700).
        enc = assemble_flat(f"    JMP 0x{va:x};[7:7:{{0,1,2,3,4,5}}:6:0]\n")
        assert len(enc) == 1
        return enc[0]

    def _rd32(self, off: int) -> int:
        return struct.unpack("<I", self.mod.device_read(
            self.arena + off, 4))[0]

    def _wr32(self, off: int, val: int) -> None:
        self.mod.device_write(self.arena + off, struct.pack("<I", val))

    # -- lifecycle -----------------------------------------------------------
    def launch(self, args: list, grid=(1,), block=(32,)) -> None:
        """Launch the target (args = the kernel's normal args); it parks
        at the gate.  dbgctrl is appended automatically."""
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
        # reset comms/frame state
        self.mod.device_write(self.arena, bytes(0x100))
        self.mod.device_write(self.arena + self.lay.hslots,
                              bytes(self.lay.results - self.lay.hslots
                                    + self.max_warps * RESULTS_SZ))
        self.mod.device_write(self.arena + self.lay.pool,
                              bytes(self.max_warps * 32 * FRAME))
        for w in range(max(warps, 1)):
            self._write_handler(w)          # restore the retline word
        for bp in self._bps.values():       # ctawarps may have changed
            self._write_stub(bp)
        self._groups = {w: [] for w in range(self.max_warps)}
        self._seen = [0] * (self.max_warps * 32)
        self._rlgen = [[0] * 32 for _ in range(self.max_warps)]
        self._cmds = [0] * self.max_warps
        self._go = [0] * self.max_warps
        self._thunk_cache.clear()
        self.mod.launch(self.func, grid=grid, block=block,
                        args=args + [self.arena], stream=self.stream)

    def wait_base(self, timeout: float = 5.0) -> int:
        t0 = time.time()
        while True:
            lo = self._rd32(CTRL_BASE)
            hi = self._rd32(CTRL_BASE + 4)
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
        self._wr32(CTRL_GATE, 1)

    def wait_done(self, timeout: float = 120.0) -> None:
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
        """Patch the site word with a JMP into the bp's stub slot.
        The site STAYS patched for the bp's whole lifetime (persistent,
        gdb-style; resume goes through a thunk — no restore race)."""
        if orig_index in self._by_index:
            raise RuntimeError(f"breakpoint already armed at {orig_index}")
        if not self._free_slots:
            raise RuntimeError("out of stub slots (max_bps)")
        inj = self.info.injected_index(orig_index)
        site = self.base() + inj * 16
        orig = self.encoded[inj]
        slot = self._free_slots.pop(0)
        bp = Breakpoint(self, self._next_id, orig_index, orig, slot)
        self._next_id += 1
        self._write_stub(bp)
        self.patcher.patch(site, self._jmp_word(self._stub_va(slot)))
        self._bps[bp.id] = bp
        self._by_index[orig_index] = bp
        return bp

    def disarm(self, bp: Breakpoint) -> None:
        """Restore the original word (only when NOT parked at this bp)."""
        self.patcher.patch(self._site_va(bp.orig_index), bp.orig_word)
        bp.armed = False
        self._free_slots.append(bp.slot)
        self._free_slots.sort()
        del self._bps[bp.id]
        del self._by_index[bp.orig_index]
        for k in [k for k in self._thunk_cache if k[0] == bp.orig_index]:
            del self._thunk_cache[k]

    def _bp_for_va(self, va: int) -> Breakpoint:
        inj = (va - self.base()) // 16
        orig = inj - PROLOGUE_LEN
        bp = self._by_index.get(orig)
        if bp is None:
            raise RuntimeError(
                f"hit from unarmed site {hex(va)} (orig {orig})")
        return bp

    # -- group hit reporting ----------------------------------------------------
    def _poll_groups(self) -> tuple[int, _Group] | None:
        """Scan all hit slots; register newly-parked groups.  Returns
        (warp, group) for the first group not yet reported."""
        raw = self.mod.device_read(self.arena + self.lay.hslots,
                                   self.max_warps * 32 * 16)
        for slot in range(self.max_warps * 32):
            mask, va_lo, va_hi, seq = struct.unpack_from(
                "<4I", raw, slot * 16)
            if seq == self._seen[slot]:
                continue
            self._seen[slot] = seq
            w, lane = divmod(slot, 32)
            bp = self._bp_for_va(va_lo | (va_hi << 32))
            for g in self._groups[w]:
                if g.bp is bp:              # pile-up at the same site
                    g.mask |= mask
                    g.slot = min(g.slot, slot)
                    g.reported = False
                    break
            else:
                self._groups[w].append(_Group(mask, bp, slot))
        for w in range(self.max_warps):
            for g in self._groups[w]:
                if not g.reported:
                    g.reported = True
                    g.bp.warp = w     # report-time: the bp object is
                    return w, g       # shared across warps' groups
        return None

    def wait_hit(self, timeout: float = 30.0) -> Breakpoint:
        """Wait until a breakpoint parks an execution group; returns the
        bp with bp.warp set."""
        t0 = time.time()
        while True:
            r = self._poll_groups()
            if r is not None:
                return r[1].bp
            if time.time() - t0 > timeout:
                raise TimeoutError("no breakpoint hit")
            time.sleep(0.001)

    def wait_group_hit(self, timeout: float = 30.0,
                       ) -> tuple[int, _Group]:
        """Like wait_hit but returns (warp, group) with the parked
        group's lane mask."""
        t0 = time.time()
        while True:
            r = self._poll_groups()
            if r is not None:
                return r
            if time.time() - t0 > timeout:
                raise TimeoutError("no breakpoint hit")
            time.sleep(0.001)

    # -- resume machinery ---------------------------------------------------------
    def _thunk_alloc(self) -> int:
        """Bump-allocate a 128B thunk slot in the global arena (wraps;
        the handler's hardened exit IVALL makes reuse safe)."""
        n = THUNK_ARENA // THUNK_STRIDE
        i = self._thunk_next % n
        self._thunk_next += 1
        return self.arena + self.lay.thunk_off + i * THUNK_STRIDE

    def build_thunk(self, insts: list[str], fallthrough_va: int,
                    ) -> list[tuple[int, int]]:
        """Encode a thunk: `insts` followed by an absolute JMP IMM back
        to `fallthrough_va`.  Callers emulate control-flow INST1
        themselves (conditional BRA -> `@P0 JMP T` + fall-through jump)."""
        src = "\n".join(insts + [f"JMP 0x{fallthrough_va:x};[7:7:{{}}:6:0]"])
        enc = assemble_flat(src)
        assert 0 < len(enc) <= THUNK_MAX_INSTS, f"thunk too big: {len(enc)}"
        return enc

    def _thunk_for(self, bp: Breakpoint, insts: list[str],
                   target_va: int) -> int:
        """(site, insts, target)-cached thunk VA — groups released with
        the same insts share the VA (barrier same-PC rendezvous)."""
        key = (bp.orig_index, tuple(insts), target_va)
        va = self._thunk_cache.get(key)
        if va is None:
            enc = self.build_thunk(insts, target_va)
            va = self._thunk_alloc()
            self.mod.device_write(
                va, b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc))
            self._thunk_cache[key] = va
        return va

    def _release_lanes(self, w: int, mask: int, thunk_va: int) -> None:
        """Release exactly `mask`'s lanes of warp w: set their per-lane
        thunk VA (F_RTGT first!), then bump their release generations."""
        for lane in range(32):
            if mask >> lane & 1:
                fva = self.lay.frame_va(self.arena, w * 32 + lane)
                self.mod.device_write(fva + F_RTGT,
                                      struct.pack("<Q", thunk_va))
                self._rlgen[w][lane] += 1
                self.mod.device_write(fva + F_RELEASE,
                                      struct.pack("<I", self._rlgen[w][lane]))
        # GO broadcast LAST: wakes every parked lane of the warp in one
        # converged poll; each then checks its own F_RELEASE (already
        # written above) and the released group exits together.
        self._go[w] += 1
        self._wr32(self.lay.go + w * 16, self._go[w])

    def _drop_group(self, w: int, g: _Group) -> None:
        self._groups[w].remove(g)

    def _groups_at(self, bp: Breakpoint) -> list[tuple[int, _Group]]:
        return [(w, g) for w in range(self.max_warps)
                for g in self._groups[w] if g.bp is bp]

    def resume_thunk(self, bp: Breakpoint, insts: list[str]) -> None:
        """Release EVERY group parked at this bp's site with a thunk
        holding `insts` (normally the original instruction) + a JMP back
        to site+0x10.  The site STAYS PATCHED (persistent bp — to break
        again, do nothing; to remove, disarm at a parked boundary)."""
        site = self._site_va(bp.orig_index)
        va = self._thunk_for(bp, insts, site + 0x10)
        for w, g in self._groups_at(bp):
            self._release_lanes(w, g.mask, va)
            self._drop_group(w, g)

    def release_group(self, warp: int, group: _Group,
                      insts: list[str]) -> None:
        """Release exactly one parked group with its thunk (other groups
        of the same warp stay parked)."""
        site = self._site_va(group.bp.orig_index)
        va = self._thunk_for(group.bp, insts, site + 0x10)
        self._release_lanes(warp, group.mask, va)
        self._drop_group(warp, group)

    def resume(self, bp: Breakpoint) -> None:
        """LEGACY semantics: restore the site word and release every
        group parked there with a bare `JMP site` thunk (the original
        instruction re-executes IN PLACE); the bp is CONSUMED.
        Caveat (M8a): the restore races in-flight refetches of running
        groups — prefer resume_thunk (persistent bps) when any other
        group may be running."""
        site = self._site_va(bp.orig_index)
        self.patcher.patch(site, bp.orig_word)           # restore
        va = self._thunk_for(bp, [], site)               # JMP site
        for w, g in self._groups_at(bp):
            self._release_lanes(w, g.mask, va)
            self._drop_group(w, g)
        bp.armed = False
        self._free_slots.append(bp.slot)
        self._free_slots.sort()
        del self._bps[bp.id]
        del self._by_index[bp.orig_index]

    # -- command injection (M7 semantics, M9 frame-based) ----------------------
    def exec_cmd(self, warp: int, insts: list[str],
                 timeout: float = 5.0, _trusted: bool = False) -> None:
        """Assemble `insts` (dialect lines) into the warp's command
        buffer and have the PARKED handler(s) execute them, then return
        to the park spin.  Repeatable until resume.

        Contract for command code:
          * R2-R7 and P0-P6 are free scratch (the kernel's values live
            in the frame; dumped/set via dump_regs/set_reg).
          * MUST NOT write R0/R1 (the lane's frame pointer).
          * Straight-line only: no BRA/CALL/RET/JMX/BRX/EXIT/BSSY/BSYNC.
          * Read results back via STG.E.STRONG.GPU to the per-warp
            results window (see dump_regs' lane prelude) + device_read.
        """
        if not any(self._groups[warp]):
            raise RuntimeError(f"warp {warp} not parked")
        if not _trusted:
            for ln in insts:
                body_ln = re.sub(r"^\s*@!?P[T0-6]\s*", "", ln).strip()
                parts = body_ln.split(None, 1)
                dest = parts[1].split(",")[0].strip() if len(parts) > 1 \
                    else ""
                if re.fullmatch(r"\{?R[01]\}?", dest):
                    raise ValueError(
                        f"command may not write R0/R1 (frame ptr): {ln}")
                if re.match(r"(BRA|CALL|RET|JMX|BRX|EXIT|KILL|BSSY|BSYNC)\b",
                            body_ln):
                    raise ValueError(f"no control flow in commands: {ln}")
        if len(insts) > 56:
            raise ValueError("command too long (max 56 instructions)")
        cmdseq = self.arena + self.lay.cmdseq + warp * 16
        hdl = self.lay.handler_va(self.arena, warp)
        _, cmdret = self._hdl[warp]
        body = "\n".join(f"    {ln}" for ln in insts)
        src = f"""{body}
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_CMD:x}];[2:7:{{1}}:8:0]
    MOV32I R4, 0x{cmdseq & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R5, 0x{cmdseq >> 32:08x};[7:7:{{}}:5:1]
    STG.E.STRONG.GPU [{{R4,R5}}+0x4], R2;[7:1:{{2}}:8:0]
    MOV32I R2, 0x{hdl & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{hdl >> 32:08x};[7:7:{{}}:13:1]
    RET.ABS.NODEC PT, {{R2,R3}}, 0x{cmdret:x};[7:7:{{}}:5:1]
"""
        enc = assemble_flat(src)
        assert enc, "command assembled to nothing"
        assert len(enc) * 16 <= CMDBUF_SZ, "command image too big"
        self.mod.device_write(
            self.arena + self.lay.cmdbuf + warp * CMDBUF_SZ,
            b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc))
        self._cmds[warp] += 1
        seq = self._cmds[warp]
        self.mod.device_write(cmdseq, struct.pack("<I", seq))
        t0 = time.time()
        while struct.unpack("<I", self.mod.device_read(
                cmdseq + 4, 4))[0] != seq:
            if time.time() - t0 > timeout:
                raise TimeoutError(f"command ack timeout (warp {warp})")
            time.sleep(0.001)

    def cmd_read(self, warp: int, off: int, size: int) -> bytes:
        """Read the warp's command result window (+off)."""
        return bytes(self.mod.device_read(
            self.arena + self.lay.results + warp * RESULTS_SZ + off, size))

    def _lane_prelude(self, warp: int) -> list[str]:
        """{R2,R3} = results(warp) + lane*4 (lane = f & 31)."""
        results = self.arena + self.lay.results + warp * RESULTS_SZ
        return [
            f"LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_F:x}];[2:7:{{}}:8:0]",
            "LOP3.LUT R2, R2, 0x1F, RZ, 0xC0;[7:7:{2}:5:1]",
            f"MOV32I R3, 0x{results & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]",
            "IMAD R2, R2, 0x4, R3;[7:7:{}:5:1]",
            f"MOV32I R3, 0x{results >> 32:08x};[7:7:{{}}:5:1]",
        ]

    _FRAME_SLOT = {"PR": F_PR, "R0": F_R01, "R1": F_R01 + 4,
                   **{f"R{k}": F_R2 + 4 * (k - 2) for k in range(2, 8)}}

    def dump_regs(self, warp: int, regs: list[str],
                  lane: int = 0) -> dict[str, int]:
        """Dump register values from a parked warp (one lane).  R0-R7
        and PR are read from the frame (the live registers hold handler
        scratch while parked); everything else is read directly."""
        if not 0 <= lane < 32:
            raise ValueError("lane out of range")
        insts: list[str] = self._lane_prelude(warp)
        out: dict[str, int] = {}
        for i, r in enumerate(regs):
            dst_s = f"0x{4 * (i * 32):x}"
            ru = r.upper()
            if ru in self._FRAME_SLOT:
                insts += [
                    f"LDG.E.STRONG.GPU R4, [{{R0,R1}}+0x"
                    f"{self._FRAME_SLOT[ru]:x}];[2:7:{{1}}:8:0]",
                    f"STG.E.STRONG.GPU [{{R2,R3}}+{dst_s}], R4;"
                    f"[7:1:{{2}}:8:0]",
                ]
            elif re.fullmatch(r"R\d+", ru):
                insts.append(
                    f"STG.E.STRONG.GPU [{{R2,R3}}+{dst_s}], {ru};"
                    f"[7:7:{{}}:8:0]")
            else:
                raise ValueError(f"cannot dump {r!r} (use exec_cmd)")
        self.exec_cmd(warp, insts, _trusted=True)
        data = self.cmd_read(warp, 0, 4 * 32 * len(regs))
        for i, r in enumerate(regs):
            off = 4 * (i * 32 + lane)
            out[r.upper()] = struct.unpack("<I", data[off:off + 4])[0]
        return out

    def set_reg(self, warp: int, reg: str, val: int, lane: int = 0) -> None:
        """Set a register of a parked warp (one lane).  R0-R7 / PR write
        the frame slot (the resume path restores from there); anything
        else writes the live register directly."""
        if not 0 <= lane < 32:
            raise ValueError("lane out of range")
        r = reg.upper()
        pre = [
            f"LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_F:x}];[2:7:{{}}:8:0]",
            "LOP3.LUT R2, R2, 0x1F, RZ, 0xC0;[7:7:{2}:5:1]",
            f"ISETP.EQ.AND P0, PT, R2, {lane}, PT;[7:7:{{}}:13:1]",
        ]
        if r in self._FRAME_SLOT:
            insts = pre + [
                f"MOV32I R3, 0x{val:x};[7:7:{{}}:5:1]",
                f"@P0 STG.E.STRONG.GPU [{{R0,R1}}+0x"
                f"{self._FRAME_SLOT[r]:x}], R3;[7:1:{{}}:8:0]",
            ]
        elif re.fullmatch(r"R\d+", r):
            insts = pre + [f"@P0 MOV32I {r}, 0x{val:x};[7:7:{{}}:5:1]"]
        else:
            raise ValueError(f"cannot set {reg!r} (use exec_cmd)")
        self.exec_cmd(warp, insts, _trusted=True)
