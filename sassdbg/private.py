"""M11c-M11f warp-private heap-code bootstrap and mutation backend.

`PrivateKernel.from_source()` preserves the original parameter offsets and
appends the debugger-control argument; `.from_cubin()` preserves the target
ABI exactly.  Both replace the entry with an immutable LEPC+JMP trampoline.  A
shared heap dispatcher computes the global warp id and jumps to that warp's
full private copy of the canonical function image.

M11d adds direct per-warp heap breakpoints and transactional code epochs. M11e
filters breakpoints by execution-group masks, transparently replays unselected
groups, and switches parked warps explicitly between cooperative collection and
tight freeze.

M11f adds masked command injection with per-lane generations, frame-aware
dump/set helpers, and a command return path that reconstructs handler-private
state before resuming the polling loop.
"""
from __future__ import annotations

import struct
import time
import re
from dataclasses import dataclass
from pathlib import Path

from assembler import (CudaModule, assemble, assemble_flat, assemble_kernel)
from assembler.sass_elf import CubinBuilder
from assembler.sass_parser import parse_kernel

from .cubin import load_kernel
from .warpcode import (Breakpoint as WarpBreakpoint, CodeTemplate, Layout,
                       OverlayBatch, PrivateCodeSet, ScopeError, WarpState,
                       _OPCODE_INDEX, _set_field_value)


# ctrl (Layout.ctrl == 0)
CTRL_MODULE_BASE = 0x00          # u64: entry LEPC (identical lane stores)
CTRL_GATE = 0x08                 # u32: host opens after every warp reports
CTRL_WARPS_PER_CTA = 0x0C        # u32: launch-time block warp count
CTRL_ACTIVE_WARPS = 0x10         # u32: diagnostic/bounds value

# Per-warp report in Layout.freeze_ctl + warp*FREEZE_STRIDE.  M11d owns the
# rest of that cache-line-separated slot.
DISPATCH_SELECTED = 0x00         # u64: actual JMX target loaded from table
DISPATCH_SEEN = 0x08             # u32: sequence-last ready flag

# M11d reuses each warp's freeze_ctl slot after the entry gate.  The dispatch
# report at +0/+8 is no longer needed once release() opens the gate.
FC_SITE = 0x00                   # u64 private site VA
FC_MASK = 0x08                   # u32 MACTIVE of the stopped group
FC_HIT = 0x0C                    # u32 0/1 publication flag (last)
FC_RELEASE = 0x10                # u32 host release generation
FC_COMMIT = 0x14                 # u32 host executable-code commit generation
FC_ACK = 0x18                    # u32 handler-acked commit generation

# Per-warp park-mode handshake (Layout.park_mode, 16 bytes per warp).
PM_MODE = 0x00                   # u32: MODE_FROZEN / MODE_COOPERATIVE
PM_GEN = 0x04                    # u32 host request generation
PM_ACK = 0x08                    # u32 handler observed generation
MODE_FROZEN = 0
MODE_COOPERATIVE = 1

# Per-lane spill frame.  F_CODEBASE is initialized by the host, which lets a
# shared logical stub derive code_base[warp]+orig_index*16 without reserving a
# scratch register before R2/R3 have been saved.
F_R2 = 0x00                      # R2..R7, six u32s
F_PR = 0x18
F_R01 = 0x20                    # u64, naturally aligned
F_SITE = 0x28                   # u64
F_CODEBASE = 0x30               # u64 immutable launch metadata
F_EPILOGUE = 0x38               # u64 restore + site-specific replay target
F_COMMIT_BASE = 0x40            # u32 handler-local generation baseline
F_RELEASE_BASE = 0x44           # u32 handler-local generation baseline
F_CMD_BASE = 0x48               # u32 last command generation observed
F_CMD_ACK = 0x4C                # u32 last command generation completed

THUNK_STRIDE = 0x100
THUNK_MAX_INSTS = THUNK_STRIDE // 16
BP_THUNK_STRIDE = 0x200


class BootstrapError(RuntimeError):
    """Warp-private dispatcher/bootstrap failure."""


@dataclass(frozen=True)
class PrivateHit:
    """One reported execution group at a logical private breakpoint."""
    warp: int
    bp: WarpBreakpoint
    site: int
    mask: int
    slot: int = 0
    seq: int = 0


def _pack(words) -> bytes:
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in words)


def _trampoline_src(dispatcher_va: int) -> str:
    return f"""\
    LEPC {{R4,R5}};[7:7:{{}}:4:0]
    JMP 0x{dispatcher_va:x};[7:7:{{}}:6:0]
"""


def _dispatcher_src(lay: Layout, arena: int) -> str:
    """Immutable shared dispatcher.  R4/R5 arrive from the trampoline.

    It uses only R0-R5 (inside even an 8-register cubin's usable window),
    publishes the selected private base per warp, waits at a uniform gate,
    restores the architectural predicate baseline, then JMXes to original
    instruction zero in the private image.
    """
    table = arena + lay.code_base_table
    reports = arena + lay.freeze_ctl
    # M11c writes the same canonical image on relaunch, but M11d may change
    # persistent overlays and wpc-dependent shared stubs at the same heap VAs.
    # Invalidate once on the target warp after the gate in breakpoint-capable
    # instances.  No padding/double-IVALL is required: none of those lines has
    # been fetched during this launch, and M11a validated the shortest frozen
    # handoff sequence.
    launch_ivall = ("    CCTL.I.IVALL;[7:7:{}:4:0]\n"
                    if lay.max_bps else "")
    return f"""\
    MOV32I R2, 0x{arena & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{arena >> 32:08x};[7:7:{{}}:5:1]
    S2R R0, SR_CTAID.X;[5:7:{{}}:5:1]
    S2R R1, SR_TID.X;[4:7:{{}}:5:1]
    STG.E.64.STRONG.GPU [{{R2,R3}}+0x{CTRL_MODULE_BASE:x}], {{R4,R5}};[7:0:{{}}:8:0]
    LDG.E.STRONG.GPU R4, [{{R2,R3}}+0x{CTRL_WARPS_PER_CTA:x}];[2:1:{{0}}:8:0]
    SHF.R.U32.HI R1, RZ, 0x5, R1;[7:7:{{4}}:5:1]
    IMAD R0, R0, R4, R1;[7:7:{{2,5}}:5:1]
    MOV32I R2, 0x{table & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R3, 0x{table >> 32:08x};[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R2,R3}}, R0, 0x8, {{R2,R3}};[7:7:{{}}:5:1]
    LDG.E.64.STRONG.GPU {{R4,R5}}, [{{R2,R3}}];[2:1:{{}}:8:0]
    MOV32I R2, 0x{reports & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R3, 0x{reports >> 32:08x};[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R2,R3}}, R0, 0x{lay.FREEZE_STRIDE:x}, {{R2,R3}};[7:7:{{}}:5:1]
    STG.E.64.STRONG.GPU [{{R2,R3}}+0x{DISPATCH_SELECTED:x}], {{R4,R5}};[7:0:{{2}}:8:0]
    MOV32I R1, 0x1;[7:7:{{0}}:5:1]
    STG.E.STRONG.GPU [{{R2,R3}}+0x{DISPATCH_SEEN:x}], R1;[7:1:{{}}:8:0]
#def_label(dispatch_gate)
    NANOSLEEP 0x100;[7:7:{{}}:5:1]
    MOV32I R2, 0x{arena & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R3, 0x{arena >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R1, [{{R2,R3}}+0x{CTRL_GATE:x}];[2:1:{{}}:8:0]
    ISETP.EQ.AND P1, PT, R1, RZ, PT;[7:7:{{2}}:13:1]
    @P1 BRA #label(dispatch_gate);[7:7:{{}}:6:0]
    R2P PR, RZ, 0x7F;[7:7:{{}}:13:1]
""" + launch_ivall + f"""    JMX {{R4,R5}}, 0x0;[7:7:{{}}:6:0]
"""


def _m11d_stub_src(lay: Layout, arena: int, orig_index: int,
                   stub_slot: int, warps_per_cta: int) -> str:
    """Shared logical-breakpoint stub with M11e group-mask filtering.

    R0/R1 are bootstrapped through RPC exactly as in M9.  The host seeds each
    lane frame's F_CODEBASE, so after R2/R3 are safe the stub derives the
    current warp-private site and selects the per-warp handler from the frame
    address.  The 32-bit address additions are constructor-checked not to
    carry into the high half.
    """
    frames = arena + lay.frames
    handlers = arena + lay.handlers
    masks = arena + lay.bp_masks + stub_slot * 4
    epilogues = arena + lay.bp_thunks + stub_slot * 8
    lanes_per_cta = warps_per_cta * 32
    site_off = orig_index * 16
    return f"""\
    RPCMOV Rpc.LO, R0;[3:7:{{}}:9:0]
    RPCMOV Rpc.HI, R1;[4:7:{{}}:9:0]
    S2R R0, SR_CTAID.X;[5:7:{{}}:5:1]
    IMAD R0, R0, 0x{lanes_per_cta:x}, RZ;[7:7:{{5}}:5:1]
    S2R R1, SR_TID.X;[5:7:{{}}:5:1]
    IADD3 R0, R0, R1, RZ;[7:7:{{5}}:5:1]
    MOV32I R1, 0x{frames & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    IMAD R0, R0, 0x{lay.FRAME:x}, R1;[7:7:{{}}:5:1]
    MOV32I R1, 0x{frames >> 32:08x};[7:7:{{}}:5:1]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2:x}], R2;[7:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 4:x}], R3;[7:7:{{}}:8:0]
    RPCMOV R2, Rpc.LO;[2:7:{{1,3}}:9:0]
    RPCMOV R3, Rpc.HI;[2:7:{{1,4}}:9:0]
    STG.E.64.STRONG.GPU [{{R0,R1}}+0x{F_R01:x}], {{R2,R3}};[7:7:{{2}}:8:0]
    LDG.E.64.STRONG.GPU {{R2,R3}}, [{{R0,R1}}+0x{F_CODEBASE:x}];[2:1:{{1}}:8:0]
    IADD3 R2, R2, 0x{site_off:x}, RZ;[7:7:{{2}}:5:1]
    STG.E.64.STRONG.GPU [{{R0,R1}}+0x{F_SITE:x}], {{R2,R3}};[7:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 8:x}], R4;[7:7:{{1}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 0xC:x}], R5;[7:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 0x10:x}], R6;[7:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 0x14:x}], R7;[7:7:{{3}}:8:0]
    P2R R2, PR;[2:7:{{0}}:6:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_PR:x}], R2;[7:7:{{2}}:8:0]
    MOV32I R2, 0x{frames & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    IADD3 R2, R0, -R2, RZ;[7:7:{{}}:5:1]
    SHF.R.U32.HI R4, RZ, 0xC, R2;[7:7:{{}}:5:1]
    MOV32I R2, 0x{masks & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{masks >> 32:08x};[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R2,R3}}, R4, 0x{lay.max_bps * 4:x}, {{R2,R3}};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R6, [{{R2,R3}}];[2:1:{{}}:8:0]
    BMOV R7, MACTIVE;[3:7:{{}}:8:0]
    LOP3.LUT R6, R6, R7, RZ, 0xC0;[7:7:{{2,3}}:5:1]
    MOV32I R2, 0x{epilogues & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{epilogues >> 32:08x};[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R2,R3}}, R4, 0x{lay.max_bps * 8:x}, {{R2,R3}};[7:7:{{}}:5:1]
    LDG.E.64.STRONG.GPU {{R2,R3}}, [{{R2,R3}}];[2:1:{{}}:8:0]
    STG.E.64.STRONG.GPU [{{R0,R1}}+0x{F_EPILOGUE:x}], {{R2,R3}};[7:7:{{2}}:8:0]
    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{{}}:13:1]
    @P0 JMX {{R2,R3}}, 0x0;[7:7:{{}}:6:0]
    SHF.L.U32 R2, R4, 0xC, RZ;[7:7:{{}}:5:1]
    IADD3 R2, R2, 0x{handlers & 0xFFFFFFFF:08x}, RZ;[7:7:{{}}:13:1]
    MOV32I R3, 0x{handlers >> 32:08x};[7:7:{{}}:13:1]
    JMX {{R2,R3}}, 0x0;[7:7:{{}}:6:0]
"""


def _m11d_handler_src(lay: Layout, arena: int, warp: int) -> str:
    """Per-warp M11e handler with cooperative/tight mode polling.

    COMMIT is polled independently of RELEASE.  Each commit executes a
    hardened target-side IVALL/drain/IVALL sequence and publishes ACK while
    remaining frozen.  Thus the host can wait for executable visibility
    before allowing any group to leave the handler.
    """
    ctl = arena + lay.freeze_ctl + warp * lay.FREEZE_STRIDE
    mode = arena + lay.park_mode + warp * lay.PARK_MODE_SZ
    hslots = arena + lay.hslots + warp * 32 * 16
    cmdseq = arena + lay.cmdseq + warp * 16
    cmdbuf = arena + lay.cmdbuf + warp * lay.CMDBUF_SZ
    frames = arena + lay.frames
    # A cooperative sibling may have fetched the soon-to-be-patched successor
    # immediately before the freeze acknowledgement.  Drain that in-flight
    # fill between invalidates; this is the M3 hardened sequence, applied only
    # to executable commits (ordinary release remains data-only).
    ivall = ("    CCTL.I.IVALL;[7:7:{}:4:0]\n"
             + "    NOP;[7:7:{}:8:0]\n" * 32
             + "    CCTL.I.IVALL;[7:7:{}:4:0]")
    return f"""\
    BMOV R2, MACTIVE;[4:7:{{1}}:8:0]
    FLO.U32 R3, PT, R2;[3:7:{{4}}:5:1]
    MOV32I R4, 0x{hslots & 0xFFFFFFFF:08x};[7:7:{{3}}:5:1]
    MOV32I R5, 0x{hslots >> 32:08x};[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R4,R5}}, R3, 0x10, {{R4,R5}};[7:7:{{}}:13:1]
    LDG.E.STRONG.GPU R3, [{{R4,R5}}+0xc];[3:1:{{}}:8:0]
    IADD3 R3, R3, 0x1, RZ;[7:7:{{3}}:5:1]
    STG.E.STRONG.GPU [{{R4,R5}}], R2;[7:7:{{}}:8:0]
    LDG.E.64.STRONG.GPU {{R6,R7}}, [{{R0,R1}}+0x{F_SITE:x}];[4:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R4,R5}}+0x4], R6;[7:7:{{4}}:8:0]
    STG.E.STRONG.GPU [{{R4,R5}}+0x8], R7;[7:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R4,R5}}+0xc], R3;[7:7:{{}}:8:0]
    MOV32I R4, 0x{ctl & 0xFFFFFFFF:08x};[7:7:{{0}}:5:1]
    MOV32I R5, 0x{ctl >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R6, [{{R4,R5}}+0x{FC_COMMIT:x}];[2:1:{{}}:8:0]
    LDG.E.STRONG.GPU R7, [{{R4,R5}}+0x{FC_RELEASE:x}];[3:1:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_COMMIT_BASE:x}], R6;[7:7:{{2}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_RELEASE_BASE:x}], R7;[7:7:{{3}}:8:0]
    MOV32I R2, 0x{cmdseq & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{cmdseq >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R6, [{{R2,R3}}];[2:1:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_CMD_BASE:x}], R6;[7:7:{{2}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_CMD_ACK:x}], R6;[7:7:{{}}:8:0]
#def_label(m11d_spin)
    LDG.E.STRONG.GPU R2, [{{R4,R5}}+0x{FC_COMMIT:x}];[2:1:{{1}}:8:0]
    LDG.E.STRONG.GPU R3, [{{R0,R1}}+0x{F_COMMIT_BASE:x}];[3:1:{{}}:8:0]
    ISETP.NE.AND P0, PT, R2, R3, PT;[7:7:{{2,3}}:13:1]
    @P0 BRA #label(m11d_commit);[7:7:{{}}:6:0]
    LDG.E.STRONG.GPU R2, [{{R4,R5}}+0x{FC_RELEASE:x}];[2:1:{{1}}:8:0]
    LDG.E.STRONG.GPU R3, [{{R0,R1}}+0x{F_RELEASE_BASE:x}];[3:1:{{}}:8:0]
    ISETP.NE.AND P0, PT, R2, R3, PT;[7:7:{{2,3}}:13:1]
    @P0 BRA #label(m11d_resume);[7:7:{{}}:6:0]
    MOV32I R2, 0x{cmdseq & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{cmdseq >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R6, [{{R2,R3}}];[2:1:{{}}:8:0]
    LDG.E.STRONG.GPU R7, [{{R0,R1}}+0x{F_CMD_BASE:x}];[3:1:{{}}:8:0]
    ISETP.NE.AND P0, PT, R6, R7, PT;[7:7:{{2,3}}:13:1]
    @P0 BRA #label(m11f_cmd);[7:7:{{}}:6:0]
    MOV32I R2, 0x{mode & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{mode >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R6, [{{R2,R3}}+0x{PM_MODE:x}];[2:1:{{}}:8:0]
    LDG.E.STRONG.GPU R7, [{{R2,R3}}+0x{PM_GEN:x}];[3:1:{{}}:8:0]
    STG.E.STRONG.GPU [{{R2,R3}}+0x{PM_ACK:x}], R7;[7:7:{{3}}:8:0]
    ISETP.NE.AND P0, PT, R6, RZ, PT;[7:7:{{2}}:13:1]
    @P0 BRA #label(m11d_coop);[7:7:{{}}:6:0]
    BRA #label(m11d_spin);[7:7:{{}}:6:0]
#def_label(m11d_coop)
    NANOSLEEP 0x100;[7:7:{{}}:5:1]
    BRA #label(m11d_spin);[7:7:{{}}:6:0]
#def_label(m11d_commit)
{ivall}
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_COMMIT_BASE:x}], R2;[7:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R4,R5}}+0x{FC_ACK:x}], R2;[7:7:{{}}:8:0]
    BRA #label(m11d_spin);[7:7:{{}}:6:0]
#def_label(m11f_cmd)
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_CMD_BASE:x}], R6;[7:7:{{}}:8:0]
    MOV32I R2, 0x{cmdseq & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{cmdseq >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R7, [{{R2,R3}}+0x4];[3:1:{{}}:8:0]
    MOV32I R2, 0x{frames & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    IADD3 R2, R0, -R2, RZ;[7:7:{{}}:5:1]
    SHF.R.U32.HI R2, RZ, 0x7, R2;[7:7:{{}}:5:1]
    LOP3.LUT R2, R2, 0x1F, RZ, 0xC0;[7:7:{{}}:5:1]
    SHF.R.U32.HI R7, RZ, R2, R7;[7:7:{{3}}:5:1]
    LOP3.LUT R7, R7, 0x1, RZ, 0xC0;[7:7:{{}}:5:1]
    ISETP.NE.AND P6, PT, R7, RZ, PT;[7:7:{{}}:13:1]
    MOV32I R2, 0x{cmdseq & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{cmdseq >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R7, [{{R2,R3}}+0x4];[3:1:{{}}:8:0]
    BMOV R2, MACTIVE;[4:7:{{}}:8:0]
    LOP3.LUT R7, R7, R2, RZ, 0xC0;[7:7:{{3,4}}:5:1]
    ISETP.NE.AND P0, PT, R7, RZ, PT;[7:7:{{}}:13:1]
    MOV32I R2, 0x{cmdbuf & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{cmdbuf >> 32:08x};[7:7:{{}}:5:1]
    @!P0 BRA #label(m11f_cmdret);[7:7:{{}}:6:0]
    CALL.ABS.NOINC PT, {{R2,R3}}, 0x0;[7:7:{{}}:6:0]
#def_label(m11f_cmdret)
    LDG.E.STRONG.GPU R6, [{{R0,R1}}+0x{F_CMD_BASE:x}];[2:1:{{1}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_CMD_ACK:x}], R6;[7:7:{{2}}:8:0]
    MOV32I R4, 0x{ctl & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R5, 0x{ctl >> 32:08x};[7:7:{{}}:5:1]
    BRA #label(m11d_spin);[7:7:{{}}:6:0]
#def_label(m11d_resume)
    LDG.E.64.STRONG.GPU {{R2,R3}}, [{{R0,R1}}+0x{F_EPILOGUE:x}];[2:1:{{1}}:8:0]
    JMX {{R2,R3}}, 0x0;[7:7:{{2}}:6:0]
"""


def _m11d_handler_image(lay: Layout, arena: int, warp: int) \
        -> tuple[bytes, int]:
    src = _m11d_handler_src(lay, arena, warp)
    words = _checked_words(src, f"__m11d_handler_{warp}")
    if len(words) * 16 > lay.HANDLER_STRIDE:
        raise BootstrapError("M11d handler exceeds per-warp slot")
    n = 0
    cmdret = None
    for line in src.splitlines():
        stripped = line.strip()
        if stripped == "#def_label(m11f_cmdret)":
            cmdret = n * 16
        elif stripped and not stripped.startswith("#def_label"):
            n += 1
    if cmdret is None:
        raise BootstrapError("M11f command-return anchor missing")
    return _pack(words), cmdret


def _restore_epilogue_src(replay_va: int) -> str:
    """Restore the stub-spilled architectural state, then replay the site."""
    return f"""\
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
    JMP 0x{replay_va:x};[7:7:{{}}:6:0]
"""


def _checked_words(body: str, name: str) -> list[tuple[int, int]]:
    src = f"#fn {name}() {{\n{body}}}\n"
    return assemble_kernel(src, check_deps=True).encoded


def _patch_cubin_entry(data: bytes, file_off: int,
                       dispatcher_va: int) -> bytes:
    """Return a module image with only its two-word entry window changed."""
    tramp = assemble_flat(_trampoline_src(dispatcher_va))
    if len(tramp) != 2:
        raise BootstrapError("entry trampoline is not two words")
    if file_off < 0 or file_off + 32 > len(data):
        raise BootstrapError(
            f"entry window {file_off:#x}..{file_off + 32:#x} "
            f"outside cubin of size {len(data):#x}")
    patched = bytearray(data)
    struct.pack_into("<QQ", patched, file_off, *tramp[0])
    struct.pack_into("<QQ", patched, file_off + 16, *tramp[1])
    return bytes(patched)


def _render_pragma(name: str, value) -> str:
    return f"    #pragma {name}({value})"


def _source_wrapper(source: str, dispatcher_va: int,
                    target_words: list[tuple[int, int]]) -> tuple[str, str]:
    decl = parse_kernel(source)
    original_param_src = [f"{p.name}<{p.size}>" for p in decl.params]
    params = ", ".join(original_param_src + ["dbgctrl<8>"])
    tramp = _trampoline_src(dispatcher_va)
    # Keep the source-debugger launch ABI (trailing dbgctrl) even though M11c's
    # immutable dispatcher has its arena VA baked after allocation.  M11d will
    # consume the same control argument for mutable breakpoint metadata.
    # Do not scan dispatcher/trampoline absolute immediates: the cubin
    # builder's intentionally simple field heuristic can read their address
    # bytes as R255 and inflate REGCOUNT to 256.  The dispatcher is audited to
    # use only R0-R5, whose allocation window is 8; scan only canonical target
    # words (the same input the ordinary source builder understands).
    computed = max(8, CubinBuilder._compute_regcount(target_words))
    declared = int(decl.attributes.get("MAXREG_COUNT", 0))
    attrs = dict(decl.attributes)
    attrs["MAXREG_COUNT"] = max(computed, declared)
    pragmas = "\n".join(_render_pragma(k, v)
                          for k, v in attrs.items())
    wrapper = f"#fn {decl.name}({params}) {{\n{pragmas}\n{tramp}}}\n"

    # Appending dbgctrl must not move any existing constant-bank offset.  The
    # private canonical words retain the original LDC immediates.
    original_params = assemble_kernel(source, check_deps=True).params
    wrapper_params = assemble_kernel(wrapper, check_deps=True).params
    if wrapper_params[:len(original_params)] != original_params:
        raise BootstrapError(
            f"wrapper parameter ABI changed: {original_params} -> "
            f"{wrapper_params}")
    if (len(wrapper_params) != len(original_params) + 1
            or wrapper_params[-1][2] != 8):
        raise BootstrapError(
            f"wrapper did not append an 8-byte dbgctrl: {wrapper_params}")
    return wrapper, decl.name


class PrivateKernel:
    """M11c no-breakpoint runtime for source kernels and real cubins."""

    def __init__(self, template: CodeTemplate, *, max_warps: int,
                 max_bps: int, budget: int | None, module_builder,
                 func: str, append_dbgctrl: bool):
        self.template = template
        self.max_warps = max_warps
        self.func = func
        self._append_dbgctrl = append_dbgctrl
        self.lay = Layout(max_bps, max_warps, template.size, budget=budget)
        self.codes = PrivateCodeSet(template, max_warps, max_bps=max_bps)

        # Establish the process-global context and allocate executable storage
        # before loading the target module: the trampoline bakes dispatcher_va.
        self.owner = CudaModule(assemble(
            "#fn __sassdbg_owner() {\n"
            "    EXIT;[7:7:{}:5:0]\n}\n"))
        self.arena = self.owner.devmem_alloc(self.lay.total)
        if self.arena % 0x100:
            raise BootstrapError(
                f"arena base {self.arena:#x} is not 0x100-aligned")
        self.owner.devmem_set(self.arena, 0, self.lay.total // 4)
        self.exec_write_log: list[tuple[int, int]] = []

        for w, inst in enumerate(self.codes.instances):
            inst.stride = self.lay.code_stride
            inst.place(self.lay.code_va(self.arena, w))
        frames = self.arena + self.lay.frames
        handlers = self.arena + self.lay.handlers
        if ((frames & 0xFFFFFFFF)
                + max_warps * 32 * self.lay.FRAME >= 1 << 32):
            raise BootstrapError("frame arena crosses a 32-bit carry boundary")
        if ((handlers & 0xFFFFFFFF)
                + max_warps * self.lay.HANDLER_STRIDE >= 1 << 32):
            raise BootstrapError("handler arena crosses a 32-bit carry boundary")
        self.codes._patch_word_fn = self._patch_word_for_slot

        dsrc = _dispatcher_src(self.lay, self.arena)
        self.dispatcher_words = _checked_words(dsrc, "__dispatch_check")
        if not 0 < len(self.dispatcher_words) * 16 <= self.lay.DISPATCHER_SZ:
            raise BootstrapError("dispatcher exceeds reserved slot")
        self._write_dispatcher()
        self._write_code_images(range(max_warps))
        self._write_code_base_table()

        module_bytes = module_builder(
            self.arena + self.lay.dispatcher,
            list(self.dispatcher_words) + list(template.words))
        self.mod = CudaModule(module_bytes)
        self.stream = CudaModule.stream_create()
        self.n_warps = 0
        self.warps_per_cta = 0
        self._module_base: int | None = None
        self._commit_gen = [0] * max_warps
        self._release_gen = [0] * max_warps
        self._mode_gen = [0] * max_warps
        self._cmd_gen = [0] * max_warps
        self._hits: dict[tuple[int, int], PrivateHit] = {}
        self._hslot_seq = [[0] * 32 for _ in range(max_warps)]
        self._thunk_next = [0] * max_warps
        self._thunk_cache: dict[tuple[int, int], int] = {}
        self._handler_cmdret = [0] * max_warps

    @classmethod
    def from_source(cls, source: str, func: str | None = None, *,
                    max_warps: int = 1, max_bps: int = 0,
                    budget: int | None = None) -> "PrivateKernel":
        decl = parse_kernel(source)
        if func is not None and func != decl.name:
            raise BootstrapError(
                f"source defines {decl.name!r}, not requested {func!r}")
        template = CodeTemplate.from_source(source, decl.name)

        def build(dispatcher_va, _executable_words):
            wrapper, _ = _source_wrapper(
                source, dispatcher_va, list(template.words))
            return assemble(wrapper, check_deps=True)

        obj = cls(template, max_warps=max_warps, max_bps=max_bps,
                  budget=budget, module_builder=build, func=decl.name,
                  append_dbgctrl=True)
        obj.source = source
        obj.params = assemble_kernel(source, check_deps=True).params
        obj.res_params = obj.params
        return obj

    @classmethod
    def from_cubin(cls, cubin_path: str | Path, func: str | None = None, *,
                   max_warps: int = 1, max_bps: int = 0,
                   budget: int | None = None) -> "PrivateKernel":
        path = str(cubin_path)
        kt = load_kernel(path, func)
        template = CodeTemplate.from_cubin(path, kt.func)

        def build(dispatcher_va, _executable_words):
            return _patch_cubin_entry(
                Path(path).read_bytes(), kt.file_off, dispatcher_va)

        obj = cls(template, max_warps=max_warps, max_bps=max_bps,
                  budget=budget, module_builder=build, func=kt.func,
                  append_dbgctrl=False)
        from .lift import extract_params
        obj.cubin_path = path
        obj._kt = kt
        obj.source = "\n".join(template.source_lines) + "\n"
        obj.params = extract_params(Path(path).read_bytes(), kt.func)
        # Lifted cubin operands already carry absolute constant-bank offsets;
        # this is retained only for the Stepper/backend compatibility surface.
        obj.res_params = []
        return obj

    def _padded_image(self, warp: int) -> bytes:
        words = list(self.template.materialize(
            self.codes.instances[warp].base))
        nop = assemble_flat("NOP;[7:7:{}:8:0]")[0]
        n = self.lay.code_stride // 16
        words.extend([nop] * (n - len(words)))
        return _pack(words)

    def _write_code_images(self, warps) -> None:
        for w in warps:
            self._write_executable(
                self.codes.instances[w].base, self._padded_image(w))

    def _write_code_base_table(self) -> None:
        raw = b"".join(struct.pack("<Q", i.base)
                       for i in self.codes.instances)
        self.owner.device_write(
            self.arena + self.lay.code_base_table, raw)

    def _write_dispatcher(self) -> None:
        nop = assemble_flat("NOP;[7:7:{}:8:0]")[0]
        words = list(self.dispatcher_words)
        words.extend([nop] * (self.lay.DISPATCHER_SZ // 16 - len(words)))
        self._write_executable(
            self.arena + self.lay.dispatcher, _pack(words))

    def _write_executable(self, va: int, data: bytes) -> None:
        """Fail closed if a runtime executable write escapes the heap arena.

        In particular, module text is never a legal destination.  The real
        cubin's entry trampoline is changed in a host bytearray before module
        load and therefore never appears in this runtime write journal.
        """
        if not (self.arena <= va and va + len(data) <= self.arena + self.lay.total):
            raise BootstrapError(
                f"executable write {va:#x}+{len(data):#x} outside arena")
        self.owner.device_write(va, data)
        self.exec_write_log.append((va, len(data)))

    def _patch_word_for_slot(self, slot: int) -> tuple[int, int]:
        va = self.lay.stub_va(self.arena, slot)
        words = assemble_flat(
            f"JMP 0x{va:x};[7:7:{{0,1,2,3,4,5}}:6:0]")
        if len(words) != 1:
            raise BootstrapError("breakpoint patch is not one word")
        return words[0]

    def _write_stub(self, bp: WarpBreakpoint) -> None:
        if not self.warps_per_cta:
            return
        src = _m11d_stub_src(
            self.lay, self.arena, bp.orig_index, bp.stub_slot,
            self.warps_per_cta)
        words = _checked_words(src, f"__m11d_stub_{bp.stub_slot}")
        if not 0 < len(words) * 16 <= self.lay.STUB_SZ:
            raise BootstrapError("M11d stub exceeds slot")
        self._write_executable(
            self.lay.stub_va(self.arena, bp.stub_slot), _pack(words))

    def _write_handlers(self, warps) -> None:
        for w in warps:
            img, cmdret = _m11d_handler_image(self.lay, self.arena, w)
            self._write_executable(self.lay.handler_va(self.arena, w), img)
            self._handler_cmdret[w] = cmdret

    def _replay_words(self, warp: int, idx: int,
                      replay_va: int) -> list[tuple[int, int]]:
        plan = self.template.replay_plans[idx]
        fallthrough = self.codes.amap.site_va(warp, idx) + 16
        if plan.kind == "verbatim":
            words = [self.template.materialize(self.code_base(warp))[idx]]
            words += assemble_flat(
                f"JMP 0x{fallthrough:x};[7:7:{{}}:6:0]")
        elif plan.kind == "bra_abs":
            src = "\n".join(list(plan.expand(self.code_base(warp)))
                              + [f"JMP 0x{fallthrough:x};[7:7:{{}}:6:0]"])
            words = assemble_flat(src)
        elif plan.kind == "bssy_rel":
            if plan.target_index is None:
                raise BootstrapError(f"BSSY replay at {idx} has no target")
            target = self.code_base(warp) + plan.target_index * 16
            delta = target - (replay_va + 16)
            if delta & 3:
                raise BootstrapError("BSSY replay target is not 4B aligned")
            scaled = delta // 4
            if not -(1 << 29) <= scaled < (1 << 29):
                raise BootstrapError("BSSY replay target is out of range")
            enc = _OPCODE_INDEX.encoding("BSSY")
            lo, hi = self.template.materialize(self.code_base(warp))[idx]
            word = _set_field_value(enc, "Sa", lo, hi,
                                     scaled & ((1 << 30) - 1))
            words = [word]
            words += assemble_flat(
                f"JMP 0x{fallthrough:x};[7:7:{{}}:6:0]")
        else:
            raise BootstrapError(
                f"unsupported replay plan {plan.kind!r} at {idx}")
        if not 0 < len(words) <= THUNK_MAX_INSTS:
            raise BootstrapError(f"replay thunk has {len(words)} words")
        return words

    def _write_bp_thunks(self, bp: WarpBreakpoint, warps) -> None:
        """Build immutable per-(warp,index) replay and restore epilogues.

        Stub slots may be recycled while their old stopped group still owns a
        frame.  Thunk addresses therefore remain unique for the launch and the
        slot-indexed table only points new entrants at the current epilogue.
        """
        for w in warps:
            key = (w, bp.orig_index)
            ep_va = self._thunk_cache.get(key)
            if ep_va is None:
                slot = self._thunk_next[w]
                if ((slot + 1) * BP_THUNK_STRIDE
                        > self.lay.thunk_arena):
                    raise BootstrapError(f"warp {w} thunk arena exhausted")
                base = (self.lay.thunk_va(self.arena, w)
                        + slot * BP_THUNK_STRIDE)
                self._thunk_next[w] += 1
                replay = self._replay_words(w, bp.orig_index, base)
                ep_va = base + THUNK_STRIDE
                ep = _checked_words(_restore_epilogue_src(base),
                                    f"__m11e_ep_{w}_{bp.orig_index}")
                if len(ep) > THUNK_MAX_INSTS:
                    raise BootstrapError(
                        "restore epilogue exceeds 0x100 bytes")
                self._write_executable(base, _pack(replay))
                self._write_executable(ep_va, _pack(ep))
                self._thunk_cache[key] = ep_va
            table = (self.arena + self.lay.bp_thunks
                     + (w * self.lay.max_bps + bp.stub_slot) * 8)
            self.owner.device_write(table, struct.pack("<Q", ep_va))

    def _seed_frames(self, warps) -> None:
        for w in warps:
            code_base = self.code_base(w)
            for lane in range(32):
                va = (self.arena + self.lay.frames
                      + (w * 32 + lane) * self.lay.FRAME + F_CODEBASE)
                self.owner.device_write(va, struct.pack("<Q", code_base))

    def _write_masks(self, warps) -> None:
        if not self.lay.max_bps:
            return
        for w in warps:
            vals = [0] * self.lay.max_bps
            for bp in self.codes.breakpoints:
                b = bp.bindings.get(w)
                if b is not None and b.armed:
                    vals[bp.stub_slot] = b.stop_mask
            self.owner.device_write(
                self.arena + self.lay.bp_masks
                + w * self.lay.max_bps * 4,
                struct.pack(f"<{self.lay.max_bps}I", *vals))

    def _wait_commit_ack(self, warp: int, want: int,
                         timeout: float = 5.0) -> None:
        va = (self.arena + self.lay.freeze_ctl
              + warp * self.lay.FREEZE_STRIDE + FC_ACK)
        t0 = time.time()
        while self._rd(va, "<I")[0] != want:
            if CudaModule.stream_query(self.stream):
                CudaModule.stream_sync(self.stream)
                raise BootstrapError("target exited before commit ack")
            if time.time() - t0 > timeout:
                raise TimeoutError(f"warp {warp} commit {want} not acked")
            time.sleep(0.0005)

    def _commit_frozen(self, warp: int) -> None:
        if self.codes.instances[warp].state is not WarpState.FROZEN:
            raise ScopeError(f"warp {warp} is not FROZEN")
        self._commit_gen[warp] += 1
        va = (self.arena + self.lay.freeze_ctl
              + warp * self.lay.FREEZE_STRIDE + FC_COMMIT)
        self.owner.device_write(va, struct.pack("<I", self._commit_gen[warp]))
        self._wait_commit_ack(warp, self._commit_gen[warp])
        self.codes.instances[warp].dirty = False

    def _apply_overlay(self, warps, *, commit_frozen: bool = True) \
            -> OverlayBatch:
        ws = list(warps)
        batch = self.codes.compute_overlay(ws)
        for w, idx, word in batch.writes:
            self._write_executable(
                self.codes.amap.site_va(w, idx), _pack([word]))
        for w, epoch in batch.epochs:
            self.owner.device_write(
                self.arena + self.lay.code_epoch + w * 4,
                struct.pack("<I", epoch))
        self.codes.commit(batch)
        self._write_masks(ws)
        if commit_frozen:
            for w in ws:
                if self.codes.instances[w].state is WarpState.FROZEN:
                    self._commit_frozen(w)
        return batch

    @staticmethod
    def _one_dim(x) -> tuple[int, int, int]:
        t = tuple(x)
        if not t or len(t) > 3:
            raise ValueError(f"bad launch dimension {x!r}")
        t = t + (1,) * (3 - len(t))
        if t[1:] != (1, 1):
            raise ValueError("M11c supports only 1-D grid/block")
        return t

    def launch(self, args: list, grid=(1,), block=(32,)) -> None:
        grid3 = self._one_dim(grid)
        block3 = self._one_dim(block)
        wpc = (block3[0] + 31) // 32
        total = grid3[0] * wpc
        if total > self.max_warps:
            raise ValueError(
                f"launch needs {total} warps, max_warps={self.max_warps}")
        if self.n_warps and any(
                i.state not in (WarpState.UNLAUNCHED, WarpState.DONE)
                for i in self.codes.instances[:self.n_warps]):
            raise BootstrapError("previous launch is still active")

        # Canonical reconstruction on every launch.  Reset the APPLIED cache
        # before deriving the persistent overlay; otherwise a relaunch could
        # incorrectly assume that a just-overwritten patch is still present.
        self._write_code_images(range(total))
        for inst in self.codes.instances:
            inst.applied.clear()
            inst.applied_words.clear()
            inst.dirty = False
        self.owner.devmem_set(self.arena + self.lay.ctrl, 0,
                              self.lay.CTRL_SZ // 4)
        self.owner.devmem_set(self.arena + self.lay.freeze_ctl, 0,
                              self.max_warps * self.lay.FREEZE_STRIDE // 4)
        self.owner.devmem_set(self.arena + self.lay.park_mode, 0,
                              self.max_warps * self.lay.PARK_MODE_SZ // 4)
        self.owner.devmem_set(self.arena + self.lay.hslots, 0,
                              self.max_warps * 32 * 16 // 4)
        self.owner.device_write(
            self.arena + CTRL_WARPS_PER_CTA,
            struct.pack("<II", wpc, total))
        self.n_warps = total
        self.warps_per_cta = wpc
        self._module_base = None
        self._commit_gen = [0] * self.max_warps
        self._release_gen = [0] * self.max_warps
        self._mode_gen = [0] * self.max_warps
        self._cmd_gen = [0] * self.max_warps
        self._hits.clear()
        self._hslot_seq = [[0] * 32 for _ in range(self.max_warps)]
        self._thunk_next = [0] * self.max_warps
        self._thunk_cache.clear()
        for w, inst in enumerate(self.codes.instances):
            inst.state = WarpState.GATED if w < total else WarpState.UNLAUNCHED
        if self.lay.max_bps:
            self._write_handlers(range(total))
            self._seed_frames(range(total))
            for bp in self.codes.breakpoints:
                self._write_stub(bp)
                self._write_bp_thunks(bp, range(total))
            # Fresh, never-fetched addresses: publish the persistent overlay
            # before launch without an IVALL/ack transaction.
            self._apply_overlay(range(total), commit_frozen=False)
        launch_args = list(args)
        if self._append_dbgctrl:
            launch_args.append(self.arena)
        self.mod.launch(self.func, grid=grid3, block=block3, args=launch_args,
                        stream=self.stream)

    def _rd(self, va: int, fmt: str):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.owner.device_read(va, size))

    def dispatch_report(self, warp: int) -> tuple[int, int]:
        if not 0 <= warp < self.n_warps:
            raise IndexError(warp)
        va = (self.arena + self.lay.freeze_ctl
              + warp * self.lay.FREEZE_STRIDE)
        selected, seen = self._rd(va, "<QI")
        return selected, seen

    def wait_ready(self, timeout: float = 5.0) -> list[int]:
        if not self.n_warps:
            raise BootstrapError("kernel not launched")
        t0 = time.time()
        while True:
            reports = [self.dispatch_report(w) for w in range(self.n_warps)]
            bad = [w for w, (selected, seen) in enumerate(reports)
                   if seen != 1 or selected != self.codes.instances[w].base]
            if not bad:
                break
            if CudaModule.stream_query(self.stream):
                CudaModule.stream_sync(self.stream)
                raise BootstrapError(
                    f"target exited before dispatcher gate; bad warps {bad}")
            if time.time() - t0 > timeout:
                raise TimeoutError(
                    f"dispatcher ready timeout; bad warps {bad}")
            time.sleep(0.001)
        lo, hi = self._rd(self.arena + CTRL_MODULE_BASE, "<II")
        self._module_base = lo | (hi << 32)
        if not self._module_base:
            raise BootstrapError("dispatcher did not report module entry")
        return [x[0] for x in reports]

    @property
    def module_base(self) -> int:
        if self._module_base is None:
            self.wait_ready()
        assert self._module_base is not None
        return self._module_base

    def code_base(self, warp: int) -> int:
        return self.codes.instances[warp].base

    def release(self) -> None:
        self.wait_ready()
        self.owner.device_write(
            self.arena + CTRL_GATE, struct.pack("<I", 1))
        for inst in self.codes.instances[:self.n_warps]:
            inst.state = WarpState.RUNNING

    def arm(self, orig_index: int, *, warps=None,
            lane_masks=None) -> WarpBreakpoint:
        """Arm one logical site on explicit private warp copies.

        Mid-run writes are accepted only for FROZEN target warps; another
        warp may remain RUNNING because its executable words are disjoint.
        """
        ws = self.codes._resolve_warps(warps)
        bp = self.codes.by_index.get(orig_index)
        if bp is None:
            bp = self.codes.arm(orig_index, warps=ws, lane_masks=lane_masks)
        else:
            self.codes._check_write_legal(ws)
            if any(bp.bindings.get(w) is not None
                   and bp.bindings[w].armed for w in ws):
                raise ScopeError(
                    f"breakpoint at {orig_index} already armed on a "
                    "requested warp")
            if isinstance(lane_masks, int) or lane_masks is None:
                masks = {w: (0xFFFFFFFF if lane_masks is None
                             else lane_masks) for w in ws}
            else:
                masks = {w: lane_masks.get(w, 0xFFFFFFFF) for w in ws}
            for w in ws:
                self.codes.set_break_mask(bp, w, masks[w])
        self._write_stub(bp)
        self._write_bp_thunks(bp, ws)
        self._apply_overlay(ws)
        return bp

    def disarm(self, bp: WarpBreakpoint, *, warps=None) -> None:
        """Restore each selected private word from the immutable template."""
        ws = self.codes._resolve_warps(warps)
        self.codes.disarm(bp, warps=ws)
        self._apply_overlay(ws)

    def configure_breakpoints(self, warp: int,
                              masks: dict[int, int]) -> None:
        """Atomically replace one frozen warp's logical stop-mask map.

        All replay/epilogue and site writes are published before the single
        code-generation commit/IVALL.  Other warps' bindings are untouched.
        """
        self.codes._check_write_legal([warp])
        wanted = {idx: mask & 0xFFFFFFFF for idx, mask in masks.items()
                  if mask & 0xFFFFFFFF}
        for bp in list(self.codes.breakpoints):
            b = bp.bindings.get(warp)
            if b is not None and b.armed and bp.orig_index not in wanted:
                self.codes.disarm(bp, warps=[warp])
        for idx, mask in sorted(wanted.items()):
            bp = self.codes.by_index.get(idx)
            if bp is None:
                bp = self.codes.arm(idx, warps=[warp], lane_masks=mask)
            else:
                self.codes.set_break_mask(bp, warp, mask)
            self._write_stub(bp)
            self._write_bp_thunks(bp, [warp])
        self._apply_overlay([warp])

    def wait_hit(self, timeout: float = 30.0) -> PrivateHit:
        """Wait for one newly reported execution-group hit.

        Hit slots are indexed by the group's leader lane, so disjoint sibling
        groups can report different sites while the warp is in cooperative
        mode without overwriting one another.
        """
        t0 = time.time()
        while True:
            for w in range(self.n_warps):
                for slot in range(32):
                    va = (self.arena + self.lay.hslots
                          + (w * 32 + slot) * 16)
                    mask, lo, hi, seq = self._rd(va, "<IIII")
                    if seq == self._hslot_seq[w][slot]:
                        continue
                    self._hslot_seq[w][slot] = seq
                    site = lo | (hi << 32)
                    idx = self.codes.amap.orig_index(w, site)
                    bp = self.codes.by_index.get(idx)
                    binding = bp.bindings.get(w) if bp is not None else None
                    if bp is None or binding is None or not binding.armed:
                        raise BootstrapError(
                            f"warp {w} hit unarmed private site {site:#x}")
                    rec = PrivateHit(w, bp, site, mask, slot, seq)
                    self._hits[(w, slot)] = rec
                    inst = self.codes.instances[w]
                    if inst.state is WarpState.RUNNING:
                        inst.state = WarpState.FROZEN
                    inst.parked_groups.append((mask, idx))
                    return rec
            if CudaModule.stream_query(self.stream):
                CudaModule.stream_sync(self.stream)
                raise BootstrapError("target completed before breakpoint hit")
            if time.time() - t0 > timeout:
                raise TimeoutError("no M11e group breakpoint hit")
            time.sleep(0.001)

    def wait_group_hit(self, timeout: float = 30.0):
        hit = self.wait_hit(timeout)
        return hit.warp, hit

    def _set_mode(self, warp: int, mode: int,
                  timeout: float = 5.0) -> None:
        if not any(w == warp for w, _ in self._hits):
            raise ScopeError(f"warp {warp} has no parked group")
        self._mode_gen[warp] += 1
        gen = self._mode_gen[warp]
        va = self.arena + self.lay.park_mode + warp * self.lay.PARK_MODE_SZ
        self.owner.device_write(va + PM_MODE, struct.pack("<II", mode, gen))
        t0 = time.time()
        while self._rd(va + PM_ACK, "<I")[0] != gen:
            if CudaModule.stream_query(self.stream):
                CudaModule.stream_sync(self.stream)
                raise BootstrapError("target exited during park-mode handshake")
            if time.time() - t0 > timeout:
                raise TimeoutError(
                    f"warp {warp} mode {mode} generation {gen} not acked")
            time.sleep(0.0005)
        self.codes.instances[warp].state = (
            WarpState.FROZEN if mode == MODE_FROZEN
            else WarpState.PARKED_COOPERATIVE)

    def cooperate(self, warp: int, timeout: float = 5.0) -> None:
        """Let sibling execution groups run and publish their own hit slots."""
        self._set_mode(warp, MODE_COOPERATIVE, timeout)

    def freeze(self, warp: int, timeout: float = 5.0) -> None:
        """Reacquire a tight no-yield boundary before executable mutation."""
        if self.codes.instances[warp].state is WarpState.FROZEN:
            return
        self.codes.instances[warp].state = WarpState.FREEZING
        self._set_mode(warp, MODE_FROZEN, timeout)

    def resume_hit(self, hit: PrivateHit) -> None:
        """Release every currently parked group of `hit.warp`.

        Each frame already names its site-specific immutable restore/replay
        epilogue, so release is data-only and is legal in either park mode.
        """
        if self._hits.get((hit.warp, hit.slot)) is not hit:
            raise BootstrapError("hit is not a current parked group")
        ctl = (self.arena + self.lay.freeze_ctl
               + hit.warp * self.lay.FREEZE_STRIDE)
        self._release_gen[hit.warp] += 1
        self.owner.device_write(
            ctl + FC_RELEASE,
            struct.pack("<I", self._release_gen[hit.warp]))
        for key in [k for k in self._hits if k[0] == hit.warp]:
            del self._hits[key]
        inst = self.codes.instances[hit.warp]
        inst.parked_groups.clear()
        inst.state = WarpState.RUNNING

    # -- M11f command injection --------------------------------------------
    _FRAME_SLOT = {
        "PR": F_PR, "R0": F_R01, "R1": F_R01 + 4,
        **{f"R{k}": F_R2 + 4 * (k - 2) for k in range(2, 8)},
    }

    def _parked_mask(self, warp: int) -> int:
        mask = 0
        for (w, _slot), hit in self._hits.items():
            if w == warp:
                mask |= hit.mask
        return mask & 0xFFFFFFFF

    def exec_cmd(self, warp: int, insts: list[str], *,
                 lane_mask: int | None = None, timeout: float = 5.0,
                 _trusted: bool = False) -> None:
        """Execute straight-line SASS on selected parked lanes.

        The command image is committed while tightly frozen.  A per-lane
        generation in each spill frame is then used for completion, so a lane
        entering the handler later cannot replay a stale command.
        """
        parked = self._parked_mask(warp)
        if not parked:
            raise ScopeError(f"warp {warp} has no parked execution group")
        selected = parked if lane_mask is None else lane_mask & 0xFFFFFFFF
        if not selected or selected & ~parked:
            raise ScopeError(
                f"command mask {selected:#x} is not a nonempty subset of "
                f"parked mask {parked:#x}")
        if not _trusted:
            for line in insts:
                body = re.sub(r"^\s*@!?P[T0-6]\s*", "", line).strip()
                parts = body.split(None, 1)
                dest = (parts[1].split(",", 1)[0].strip()
                        if len(parts) > 1 else "")
                if re.fullmatch(r"\{?R[01]\}?", dest):
                    raise ValueError(
                        f"command may not write R0/R1 (frame ptr): {line}")
                if re.match(
                        r"(BRA|CALL|RET|JMX|JMP|BRX|EXIT|KILL|BSSY|BSYNC)\b",
                        body):
                    raise ValueError(f"no control flow in commands: {line}")
        if len(insts) > self.lay.CMDBUF_SZ // 16 - 3:
            raise ValueError("command too long for per-warp command buffer")

        self.freeze(warp)
        handler = self.lay.handler_va(self.arena, warp)
        cmdret = self._handler_cmdret[warp]
        body = list(insts)
        if lane_mask is not None and not _trusted:
            body = [line if re.match(r"\s*@", line)
                    else "@P6 " + line.lstrip() for line in body]
        src = "\n".join(body + [
            f"MOV32I R2, 0x{handler & 0xFFFFFFFF:08x};"
            "[7:7:{0,1,2,3,4,5}:5:1]",
            f"MOV32I R3, 0x{handler >> 32:08x};[7:7:{{}}:13:1]",
            f"RET.ABS.NODEC PT, {{R2,R3}}, 0x{cmdret:x};"
            "[7:7:{}:5:1]",
        ])
        enc = assemble_flat(src)
        if not enc:
            raise BootstrapError("command assembled to no instructions")
        image = _pack(enc)
        if len(image) > self.lay.CMDBUF_SZ:
            raise BootstrapError("command image exceeds command buffer")
        self._write_executable(
            self.arena + self.lay.cmdbuf + warp * self.lay.CMDBUF_SZ,
            image)
        self._commit_frozen(warp)

        # Multiple sibling handlers must all get issue opportunities.  Code is
        # already committed; only data generations change in cooperative mode.
        self.cooperate(warp)
        self._cmd_gen[warp] += 1
        seq = self._cmd_gen[warp]
        cmdseq = self.arena + self.lay.cmdseq + warp * 16
        self.owner.device_write(cmdseq, struct.pack("<II", seq, selected))
        t0 = time.time()
        lanes = [lane for lane in range(32) if selected & (1 << lane)]
        while True:
            pending = []
            for lane in lanes:
                va = (self.arena + self.lay.frames
                      + (warp * 32 + lane) * self.lay.FRAME + F_CMD_ACK)
                if self._rd(va, "<I")[0] != seq:
                    pending.append(lane)
            if not pending:
                break
            if CudaModule.stream_query(self.stream):
                CudaModule.stream_sync(self.stream)
                raise BootstrapError("target exited during command")
            if time.time() - t0 > timeout:
                raise TimeoutError(
                    f"command {seq} ack timeout on warp {warp}, "
                    f"lanes {pending}")
            time.sleep(0.0005)
        self.freeze(warp)

    def cmd_read(self, warp: int, off: int, size: int) -> bytes:
        if off < 0 or size < 0 or off + size > self.lay.RESULTS_SZ:
            raise ValueError("command result read outside results window")
        return bytes(self.owner.device_read(
            self.arena + self.lay.results + warp * self.lay.RESULTS_SZ + off,
            size))

    def dump_regs(self, warp: int, regs: list[str], *,
                  lane: int = 0) -> dict[str, int]:
        if not 0 <= lane < 32:
            raise ValueError("lane out of range")
        if not (self._parked_mask(warp) & (1 << lane)):
            raise ScopeError(f"warp {warp} lane {lane} is not parked")
        results = self.arena + self.lay.results + warp * self.lay.RESULTS_SZ
        insts = []
        for i, reg in enumerate(regs):
            ru = reg.upper()
            dst = results + 4 * (i * 32 + lane)
            insts += [
                f"MOV32I R2, 0x{dst & 0xFFFFFFFF:08x};"
                "[7:7:{1}:5:1]",
                f"MOV32I R3, 0x{dst >> 32:08x};[7:7:{{}}:5:1]",
            ]
            if ru in self._FRAME_SLOT:
                insts += [
                    f"LDG.E.STRONG.GPU R4, [{{R0,R1}}+0x"
                    f"{self._FRAME_SLOT[ru]:x}];[4:7:{{}}:8:0]",
                    f"@P6 STG.E.STRONG.GPU [{{R2,R3}}], R4;"
                    f"[7:1:{{4}}:8:0]",
                ]
            elif re.fullmatch(r"R\d+", ru):
                insts.append(
                    f"@P6 STG.E.STRONG.GPU [{{R2,R3}}], {ru};"
                    "[7:1:{}:8:0]")
            else:
                raise ValueError(f"cannot dump {reg!r}")
        self.exec_cmd(warp, insts, lane_mask=1 << lane, _trusted=True)
        data = self.cmd_read(warp, 0, 4 * 32 * len(regs))
        return {reg.upper(): struct.unpack_from(
                    "<I", data, 4 * (i * 32 + lane))[0]
                for i, reg in enumerate(regs)}

    def set_reg(self, warp: int, reg: str, val: int, *, lane: int = 0) -> None:
        if not 0 <= lane < 32:
            raise ValueError("lane out of range")
        ru = reg.upper()
        if ru in self._FRAME_SLOT:
            insts = [
                f"MOV32I R2, 0x{val & 0xFFFFFFFF:x};[7:7:{{}}:5:1]",
                f"@P6 STG.E.STRONG.GPU [{{R0,R1}}+0x"
                f"{self._FRAME_SLOT[ru]:x}], R2;[7:1:{{}}:8:0]",
            ]
        elif re.fullmatch(r"R\d+", ru):
            insts = [
                f"@P6 MOV32I {ru}, 0x{val & 0xFFFFFFFF:x};[7:7:{{}}:5:1]"]
        else:
            raise ValueError(f"cannot set {reg!r}")
        self.exec_cmd(warp, insts, lane_mask=1 << lane, _trusted=True)

    def wait_done(self, timeout: float = 120.0) -> None:
        t0 = time.time()
        while not CudaModule.stream_query(self.stream):
            if time.time() - t0 > timeout:
                raise TimeoutError("private target still running")
            time.sleep(0.005)
        CudaModule.stream_sync(self.stream)
        for inst in self.codes.instances[:self.n_warps]:
            inst.state = WarpState.DONE


__all__ = [
    "BootstrapError", "PrivateHit", "PrivateKernel",
    "CTRL_MODULE_BASE", "CTRL_GATE", "CTRL_WARPS_PER_CTA",
    "CTRL_ACTIVE_WARPS", "DISPATCH_SELECTED", "DISPATCH_SEEN",
]
