"""Probe per-warp mutable heap SASS under divergent execution groups.

M11a freeze-protocol + minimum-IVALL production probe
(SASSDBG_WARP_PRIVATE_PLAN.md sections 8.3 and 14/M11a).

Model: each warp runs two divergent execution groups.  Group B (lane 0)
heats a tight loop, publishes BEFORE/B_YIELDED, then hands the warp to
group A (lanes 1-31) with a one-shot NANOSLEEP (or YIELD).  Because a
non-blocked group monopolizes the warp's issue slots, A's first
instruction executes only when B blocks at the handoff -- that moment is
the freeze request.  A then runs a bounded no-yield settling loop
(--settle iterations), publishes the freeze acknowledgement (A_READY)
and enters a tight release/command poll that starves B forever: the
warp is FROZEN.  The host may mutate the (shared, M9-style) heap text
in that window; A's CCTL.I.IVALL sequence is the only thing between the
host patch and B's refetch of the hot SITE line.

Cases:
  F0  NANOSLEEP handler: B must keep progressing (positive control)
  F1  tight handler: B must stop; no patch, resume gives delta +1
  P1  site patched before launch: resumed delta +0x100
  P2  frozen in-place patch, no IVALL (diagnostic: expects stale)
  P3  frozen in-place patch, IVALL (decisive tight-loop case)
  P4  resume at a never-fetched fresh VA containing +0x100 (control)
  P5  P3 with a ~2 KiB fat loop (refetch control)
  C1  command buffer + device-self-written retline: A dispatches three
      host-provided commands through one per-warp heap buffer (JMX into
      it).  The command word and the retline word are DEVICE-side STG
      copies of host data into previously-fetched VAs, each dispatch
      followed by the configured IVALL sequence.  Expected cumulative
      R30 = 0x110100; without IVALL the cached round-1 command word
      re-executes (plateau at 0x200...) and the cached retline wedges
      the dispatch loop (teardown reclaims the context).

M11a additions over the first version of this probe:
  - immediate-after-ack patching: --patch-delay-ms (default 0; the old
    100 ms + 250 ms host dwell is gone),
  - configurable no-yield settling iterations before the ack (--settle),
  - multiple warps per CTA and multiple CTAs (--warps/--ctas): per-warp
    control slots (0x100-stride, cache-line separated), per-warp
    freeze/ack/release, per-warp deltas,
  - staggered release (--staggered): warp 0 is released and runs while
    every other warp must stay frozen with a constant progress counter
    (cross-warp and cross-CTA freeze isolation),
  - the C1 command-buffer/self-modified-retline visibility case,
  - outcome classification separating scheduling from visibility:
      SETUP       handoff/ack/patch-write failures and launch problems
                  (reported, excluded from visibility denominators)
      FREEZE      sibling progress after the ack (invalid boundary)
      VISIBILITY  frozen boundary held but the stale word/command
                  executed (the failure class the gate counts)
      TIMEOUT     release or completion never observed (context wedged)
      PASS        frozen + expected word/command.

Run:
    python3 -m sassdbg.probe_warp_mutable [--repeat N] [--iters N]
    python3 -m sassdbg.probe_warp_mutable --cases P3 --ivall-count 1 \
        --ivall-nops 0 --settle 0 --repeat 10 --iters 1000 \
        --gate-min 10000
    python3 -m sassdbg.probe_warp_mutable --cases P3 F1 --warps 2 \
        --staggered --repeat 10

Results (2026-08-30, first version):
RTX 5090, sm_120, driver 590.48.01:
F1 30/30 frozen; P2 30/30 old (+1); P3 30/30 new (+0x100);
P4 30/30 new (+0x100).  The full F0-F1/P1-P5 matrix passed 10/10.
IVALL-length sweep in the frozen-warp path: no IVALL gave the old word
30/30; one or two IVALLs with 0/1/2/4/8/16/32 stall-8 NOPs all gave the
new word 30/30.  The shortest candidate, one IVALL and zero NOPs, then
gave the new word 300/300.  This does not supersede the longer sequence
for paths that may still have an in-flight fill; here the tight handler
had kept the sibling group frozen for 350 ms before invalidation.

H20, sm_90, driver 580.65.06, using ``--handoff nanosleep``:
F1 30/30 frozen; P2 30/30 old (+1); P3 30/30 new (+0x100);
P4 30/30 new (+0x100).  A plain YIELD did not hand execution from B
back to A on this Hopper: B kept running while A_READY stayed zero.  A
one-shot NANOSLEEP can also occasionally fail to hand off during setup;
that is a scheduling/setup observation, not a patch-visibility sample.
The IVALL-length matrix had 405/405 valid patched runs execute the new
word (one/two IVALLs, 0/1/2/4/8/16/32 NOPs); 15 of 420 attempts timed
out before A_READY and were excluded.  The no-IVALL control executed the
old word 30/30.  A separate shortest-sequence stress run collected 300/300
new-word results from 305 attempts (5 pre-patch A_READY setup skips), with
zero stale fetches and zero other failures.

Results (multi-warp/multi-CTA completion of M11a, RTX 5090, sm_120):
The full matrix passes at warps=3 and warps=4 (deltas=[256]*N verdict=new),
C1 passes at warps=4 (cmd=0x110100, deltas=[1]*N), ctas=2/warps=2,
ctas=4/warps=1 and ctas=2/warps=4 (8 total warps) all PASS, staggered
warps=3 PASSes (P3+P4 x3), and the yield handoff works at warps=2.
The 10k shortest-sequence gate (1x IVALL, 0 NOPs) PASSED at warps=1
and at warps=3: 10,000/10,000 valid iterations, zero freeze failures,
zero stale fetches (GATE PASS, min=10000).

Hopper gate (2026-08-31, H20 sm_90, driver 580.65.06,
ASSEMBLER_ARCH=sm90, --handoff nanosleep): the full matrix passes x3
at warps=1; multi-warp P3+C1 pass at warps=2/3/4; ctas=2x2 and
ctas=4x1 pass; staggered warps=3 (P3+P4 x2) passes — the first
multi-warp sm_90 runs, also validating the REGCOUNT fix on Hopper.
The 10k shortest-sequence gate PASSED at warps=1 (10,541 valid /
159 SETUP / 0 visibility / 0 freeze) and at warps=3 (10,306 valid /
394 SETUP / 0 visibility / 0 freeze).  SETUP skips are the known
one-shot-NANOSLEEP handoff flakiness (scheduling, not a visibility
sample); their rate grows with warp count (~1.5% at warps=1, ~3.7%
total at warps=3), consistent with a per-warp failure probability.
Note: a first 10k attempt at warps=1 stopped at 9,841 valid because
the SETUP exclusions ate the budget -- run ~10.7k iters to clear
--gate-min 10000 on Hopper.

M11a root-cause found on the way (multi-warp >= 3 faulted 715):
the wrapper cubin's declared REGCOUNT covers only the wrapper's own
registers (auto-computed = 16 from R4/R5); the heap program executes
R14-R30 out of that declared window.  Out-of-window register access
is undefined, not always a fault: at <= 2 warps the overrun landed in
unallocated register-file space (harmless), at >= 3 warps the CTA's
RF allocation geometry changed and the access faulted
CUDA_ERROR_ILLEGAL_INSTRUCTION (715) before ANY heap store landed
(kernel died in the head; w3min/x1-style minimal kernels with R0-R13
worked at every warp count, and a one-word diff of the w=2 vs w=3
programs showed only the WPC immediate).  Fix: the wrapper now declares
#pragma MAXREG_COUNT computed over every word the GPU can execute from
the heap (program + fresh copy + C1 command/ret words + static STG)
via CubinBuilder._compute_regcount.  Same rule applies to ANY
wrapper-JMP-to-heap scheme (the M9 stub/JMP path only borrowed
R0-R7, which is why it never tripped this).
"""
from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402
from assembler.sass_elf import CubinBuilder  # noqa: E402

# Per-warp control slots (ctrl + warp*WCTRL + off).  The stride is
# cache-line separated so host writes for adjacent warps never share a
# line (plan section 5).
A_READY = 0x00
A_CMD = 0x04
B_YIELDED = 0x08
FINISH = 0x0C
BEFORE = 0x10
AFTER = 0x14
PROGRESS = 0x18
CMD_WORD = 0x20              # 128-bit executable word, host -> device
RET_WORD = 0x30              # 128-bit retline word, host -> device
CMD_RESULT = 0x40            # u32 accumulated command counter
RESUME_T = 0x48              # u64 fresh-code target (P4)
WCTRL = 0x100

OLD_OFF = 0x0000
FRESH_OFF = 0x8000
CMDBUF_OFF = 0x9000          # per-warp command buffers
CMBUF_STRIDE = 0x100
HEAP_SIZE = 0x10000
WARM_ITERS = 0x40

SITE_OLD = "IADD3 R20, R20, 0x1, RZ;[7:7:{}:5:1]"
SITE_NEW = "IADD3 R20, R20, 0x100, RZ;[7:7:{}:5:1]"

# C1 command rounds: (IADD3 delta, retline target).  The first two
# rounds return to the tight spin; the final round's retline jumps to
# the after-block which observes FINISH=1 and exits.  The host sets
# FINISH before bumping A_CMD for the final round, so B (parked since
# its handoff) later resumes into exactly one unpatched SITE (+1).
ROUNDS = ((0x100, "spin"), (0x10000, "spin"), (0x100000, "after"))


@dataclass(frozen=True)
class Case:
    cooperative: bool = False
    fat: bool = False
    patch: str = "none"             # none / before / frozen / fresh
    ivall: str = "hard"             # none / hard
    cmd: bool = False               # C1 command dispatch path


CASES = {
    "F0": Case(cooperative=True),
    "F1": Case(),
    "P1": Case(patch="before"),
    "P2": Case(patch="frozen", ivall="none"),
    "P3": Case(patch="frozen", ivall="hard"),
    "P4": Case(patch="fresh", ivall="hard"),
    "P5": Case(fat=True, patch="frozen", ivall="hard"),
    "C1": Case(cmd=True),
}


def _inst_count(src: str) -> int:
    return sum(1 for ln in src.splitlines() if ";[" in ln)


def _label_indices(src: str) -> dict[str, int]:
    out: dict[str, int] = {}
    count = 0
    for ln in src.splitlines():
        s = ln.strip()
        if s.startswith("#def_label(") and s.endswith(")"):
            out[s[len("#def_label("):-1]] = count
        elif ";[" in ln:
            count += 1
    return out


def _settle_block(iters: int) -> str:
    """Bounded no-yield settling loop: R14 counts down, no NANOSLEEP."""
    if iters <= 0:
        return ""
    return (("    MOV32I R14, 0x%x;[7:7:{}:5:1]\n" % iters)
            + "#def_label(settle)\n"
            "    IADD3 R14, R14, -0x1, RZ;[7:7:{}:5:1]\n"
            "    ISETP.NE.AND P5, PT, R14, RZ, PT;[7:7:{}:13:1]\n"
            "    @P5 BRA #label(settle);[7:7:{}:6:0]\n")


def _invalidate(count: int, nops: int, req: str = "{}") -> str:
    if not count:
        return ""
    s = f"    CCTL.I.IVALL;[7:7:{req}:4:0]\n"
    s += "    NOP;[7:7:{}:8:0]\n" * nops
    if count == 2:
        s += "    CCTL.I.IVALL;[7:7:{}:4:0]\n"
    return s


def _head(wpc: int, settle: int) -> str:
    """Common prefix: per-warp control base + role predicates.

    R4/R5 hold the ctrl base (from the wrapper LDC.64).  R6/R7 become
    the per-warp base ctrl + w*0x100 where w = CTAID.X*wpc + TID.X>>5.
    The 32-bit half-add assumes no carry out of the low half; the host
    asserts that before launch.  P0 = lane 0 (group B), P1 = lane 1
    (the lane that publishes A_READY).
    """
    return f"""\
    MOV R5, R5;[7:7:{{1}}:5:1]
    S2R R2, SR_TID.X;[5:7:{{}}:5:1]
    S2R R9, SR_CTAID.X;[3:7:{{}}:5:1]
    MOV32I R10, 0x1;[7:7:{{}}:5:1]
    SHF.R.U32 R8, R2, 0x5, RZ;[7:7:{{5}}:5:1]
    IMAD R9, R9, 0x{wpc:x}, R8;[7:7:{{3}}:5:1]
    SHF.L.U32 R9, R9, 0x8, RZ;[7:7:{{}}:5:1]
    SHF.L.U32 R3, R8, 0x5, RZ;[7:7:{{}}:5:1]
    IADD3 R6, R4, R9, RZ;[7:7:{{}}:5:1]
    MOV R7, R5;[7:7:{{}}:5:1]
    IADD3 R11, R3, R10, RZ;[7:7:{{}}:5:1]
    ISETP.EQ.AND P0, PT, R2, R3, PT;[7:7:{{5}}:13:1]
    ISETP.EQ.AND P1, PT, R2, R11, PT;[7:7:{{5}}:13:1]
    @P0 BRA #label(group_b);[7:7:{{}}:6:0]

    YIELD;[7:7:{{}}:5:1]
""" + _settle_block(settle) + f"""\
    @P1 STG.E.STRONG.GPU [{{R6,R7}}+0x{A_READY:x}], R10;[7:1:{{}}:8:0]
"""


def _a_spin(invalidate: str, cooperative: bool = False) -> str:
    sleep = "    NANOSLEEP 0x100;[7:7:{}:5:1]\n" if cooperative else ""
    return f"""\
#def_label(handler_spin)
{sleep}    LDG.E.STRONG.GPU R12, [{{R6,R7}}+0x{A_CMD:x}];[2:7:{{}}:8:0]
    ISETP.EQ.AND P2, PT, R12, RZ, PT;[7:7:{{2}}:13:1]
    @P2 BRA #label(handler_spin);[7:7:{{}}:6:0]
{invalidate}    EXIT;[7:7:{{}}:5:0]
"""


def _a_cmd(cmdbuf_lo: int, cmdbuf_hi: int, ivall_count: int,
           ivall_nops: int) -> str:
    """C1 dispatch loop: copy host-provided executable words into the
    per-warp command buffer (device-written cmd word + retline), then
    IVALL and JMX into it.  The static STG at cmdbuf+0x10 is written by
    the host at setup.  The command word carries req={4} so the next
    round's overwrite of R30 waits the previous round's static STG
    read-claim (M9 late-read rule)."""
    invalidate = _invalidate(ivall_count, ivall_nops, req="{1,2}")
    return f"""\
    MOV32I R18, 0x{cmdbuf_lo:x};[7:7:{{}}:5:1]
    MOV32I R19, 0x{cmdbuf_hi:x};[7:7:{{}}:5:1]
    IADD3 R18, R18, R9, RZ;[7:7:{{}}:5:1]
    MOV32I R13, 0x0;[7:7:{{}}:5:1]
    MOV32I R30, 0x0;[7:7:{{}}:5:1]
#def_label(handler_spin)
    LDG.E.STRONG.GPU R12, [{{R6,R7}}+0x{A_CMD:x}];[2:7:{{}}:8:0]
    ISETP.EQ.AND P2, PT, R12, R13, PT;[7:7:{{2}}:13:1]
    @P2 BRA #label(handler_spin);[7:7:{{}}:6:0]
    MOV R13, R12;[7:7:{{2}}:5:1]
    LDG.E.128.STRONG.GPU {{R20,R21,R22,R23}}, [{{R6,R7}}+0x{CMD_WORD:x}];[2:7:{{}}:8:0]
    STG.E.128.STRONG.GPU [{{R18,R19}}+0x00], {{R20,R21,R22,R23}};[7:1:{{2}}:8:0]
    LDG.E.128.STRONG.GPU {{R20,R21,R22,R23}}, [{{R6,R7}}+0x{RET_WORD:x}];[2:7:{{1}}:8:0]
    STG.E.128.STRONG.GPU [{{R18,R19}}+0x20], {{R20,R21,R22,R23}};[7:1:{{2}}:8:0]
{invalidate}    JMX {{R18,R19}}, 0x0;[7:7:{{}}:6:0]

#def_label(after_cmd)
    LDG.E.STRONG.GPU R12, [{{R6,R7}}+0x{FINISH:x}];[2:7:{{}}:8:0]
    ISETP.NE.AND P4, PT, R12, RZ, PT;[7:7:{{2}}:13:1]
    @P4 EXIT;[7:7:{{}}:5:0]
    BRA #label(handler_spin);[7:7:{{}}:6:0]
"""


def _b_body(handoff: str, fat: bool, fresh: bool) -> str:
    pad = "    NOP;[7:7:{}:8:0]\n" * (120 if fat else 0)
    # P4 deliberately redirects the resumed group to a never-fetched VA.
    # Every other case falls straight through from the handoff to SITE,
    # retaining the strongest possible old-loop/fetch-buffer state.
    fresh_jump = ""
    if fresh:
        fresh_jump = (f"    @P3 LDG.E.64.STRONG.GPU {{R24,R25}}, "
                      f"[{{R6,R7}}+0x{RESUME_T:x}];[2:7:{{}}:8:0]\n"
                      f"    @P3 JMX {{R24,R25}}, 0x0;[7:7:{{2}}:13:1]\n")
    return f"""\
#def_label(group_b)
    MOV32I R20, 0x0;[7:7:{{}}:5:1]
    MOV32I R21, 0x0;[7:7:{{}}:5:1]
    MOV32I R22, 0x0;[7:7:{{}}:5:1]
#def_label(loop)
    IADD3 R21, R21, 0x1, RZ;[7:7:{{}}:5:1]
    STG.E.STRONG.GPU [{{R6,R7}}+0x{PROGRESS:x}], R21;[7:1:{{}}:8:0]
    ISETP.GE.U32.AND P2, PT, R21, 0x{WARM_ITERS:x}, PT;[7:7:{{}}:13:1]
    ISETP.EQ.AND P3, PT, R22, RZ, P2;[7:7:{{}}:13:1]
    @P3 MOV32I R22, 0x1;[7:7:{{}}:5:1]
    @P3 STG.E.STRONG.GPU [{{R6,R7}}+0x{BEFORE:x}], R20;[7:1:{{}}:8:0]
    @P3 STG.E.STRONG.GPU [{{R6,R7}}+0x{B_YIELDED:x}], R10;[7:1:{{}}:8:0]
    @P3 {handoff};[7:7:{{}}:5:1]
{fresh_jump}"""


def _old_program(case: Case, wpc: int, handoff: str, settle: int,
                 ivall_count: int, ivall_nops: int,
                 cmdbuf_lo: int | None = None,
                 cmdbuf_hi: int | None = None) -> tuple[str, int, dict]:
    """Return (plain SASS, SITE instruction index, label index map)."""
    head = _head(wpc, settle)
    if case.cmd:
        assert cmdbuf_lo is not None and cmdbuf_hi is not None
        a_path = _a_cmd(cmdbuf_lo, cmdbuf_hi, ivall_count, ivall_nops)
    else:
        a_path = _a_spin(_invalidate(ivall_count, ivall_nops),
                         cooperative=case.cooperative)
    b_body = _b_body(handoff, case.fat, case.patch == "fresh")
    pre = head + a_path + b_body
    site_idx = _inst_count(pre)
    tail = f"    {SITE_OLD}\n"
    if case.fat:
        tail += "    NOP;[7:7:{}:8:0]\n" * 120
    tail += f"""\
    LDG.E.STRONG.GPU R12, [{{R6,R7}}+0x{FINISH:x}];[2:7:{{}}:8:0]
    ISETP.NE.AND P4, PT, R12, RZ, PT;[7:7:{{2}}:13:1]
    @P4 BRA #label(done);[7:7:{{}}:6:0]
    BRA #label(loop);[7:7:{{}}:6:0]

#def_label(done)
    STG.E.STRONG.GPU [{{R6,R7}}+0x{AFTER:x}], R20;[7:1:{{}}:8:0]
    EXIT;[7:7:{{1}}:5:0]
"""
    src = pre + tail
    return src, site_idx, _label_indices(src)


def _fresh_program() -> str:
    return f"""\
    {SITE_NEW}
    STG.E.STRONG.GPU [{{R6,R7}}+0x{AFTER:x}], R20;[7:1:{{}}:8:0]
    EXIT;[7:7:{{1}}:5:0]
"""


def _pack(words) -> bytes:
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in words)


def _u32(mod: CudaModule, va: int) -> int:
    return struct.unpack("<I", mod.device_read(va, 4))[0]


def _wait_stream(stream: int, timeout: float) -> bool:
    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > timeout:
            return False
        time.sleep(0.001)
    CudaModule.stream_sync(stream)
    return True


def _poll(fn, want, timeout: float) -> bool:
    t0 = time.time()
    while True:
        try:
            if fn() == want:
                return True
        except Exception:
            pass
        if time.time() - t0 > timeout:
            return False
        time.sleep(0.001)


def _delta_kinds(case: Case, deltas: list[int], staggered: bool) -> list[str]:
    """Classify each warp's AFTER-BEFORE delta as new/old/weird.

    Plain release: B executes SITE exactly once (FINISH pre-set), so
    new == 0x100 and old == 0x1 exactly.  Staggered warp 0 loops until
    the host sets FINISH, so K executions give K*0x100 (new, low byte
    0) or 1 + (K-1)*0x100 (first execution stale, low byte 1).  F1 and
    C1 never patch: any delta is the old word.
    """
    kinds = []
    for w, d in enumerate(deltas):
        lead = staggered and w == 0 and len(deltas) > 1
        if case.cmd or case.patch == "none":
            kinds.append("old" if d >= 1 else "weird")
        elif lead:
            if d != 0 and d % 0x100 == 0:
                kinds.append("new")
            elif d % 0x100 == 1:
                kinds.append("stale")
            else:
                kinds.append(f"weird:{d:#x}")
        else:
            if d == 0x100:
                kinds.append("new")
            elif d == 0x1:
                kinds.append("stale")
            else:
                kinds.append(f"weird:{d:#x}")
    return kinds


def run_child(name: str, handoff: str, ivall_count: int, ivall_nops: int,
              *, warps: int = 1, ctas: int = 1, settle: int = 0,
              patch_delay_ms: float = 0.0, freeze_ms: float = 2.0,
              staggered: bool = False, iters: int = 1) -> None:
    case = CASES[name]
    total = warps * ctas
    assert total * CMBUF_STRIDE <= HEAP_SIZE - CMDBUF_OFF, "cmdbuf overflow"
    assert total >= 1

    # A tiny already-loaded module establishes the shared context and owns
    # allocations whose VAs must be baked into the wrapper before it loads.
    owner = CudaModule(assemble(
        "#fn owner() {\n    EXIT;[7:7:{}:5:0]\n}\n"))
    ctrl = owner.devmem_alloc(total * WCTRL)
    heap = owner.devmem_alloc(HEAP_SIZE)
    # The kernels add 32-bit per-warp offsets to the low halves of these
    # VAs; fail closed on a would-be carry instead of assuming.
    assert (ctrl & 0xFFFFFFFF) + (total - 1) * WCTRL < (1 << 32), "ctrl carry"
    cmdbuf_base = heap + CMDBUF_OFF
    assert ((cmdbuf_base & 0xFFFFFFFF) + (total - 1) * CMBUF_STRIDE
            < (1 << 32)), "cmdbuf carry"
    owner.device_write(ctrl, bytes(total * WCTRL))
    owner.device_write(heap, bytes(HEAP_SIZE))

    handoff_inst = "YIELD" if handoff == "yield" else "NANOSLEEP 0x100"
    old_src, site_idx, labels = _old_program(
        case, warps, handoff_inst, settle, ivall_count, ivall_nops,
        cmdbuf_base & 0xFFFFFFFF if case.cmd else None,
        cmdbuf_base >> 32 if case.cmd else None)
    old_enc = assemble_flat(old_src)
    fresh_enc = assemble_flat(_fresh_program())
    assert old_enc and len(old_enc) * 16 < FRESH_OFF
    site_va = heap + OLD_OFF + site_idx * 16
    fresh_va = heap + FRESH_OFF
    owner.device_write(heap + OLD_OFF, _pack(old_enc))
    owner.device_write(fresh_va, _pack(fresh_enc))

    old_word = assemble_flat(SITE_OLD)[0]
    new_word = assemble_flat(SITE_NEW)[0]
    assert old_enc[site_idx] == old_word, (site_idx, old_enc[site_idx])
    old_pk = struct.pack("<QQ", *old_word)
    new_pk = struct.pack("<QQ", *new_word)

    # C1 host-side words.  The command word req-waits {4}: the previous
    # round's static STG claimed a read on R30 (M9 late-read rule).
    cmd_words = {d: assemble_flat(
        f"IADD3 R30, R30, 0x{d:x}, RZ;[7:7:{{4}}:5:1]")[0]
        for d, _ in ROUNDS}
    ret_words: dict[str, tuple[int, int]] = {}
    if case.cmd:
        spin_va = heap + OLD_OFF + labels["handler_spin"] * 16
        after_va = heap + OLD_OFF + labels["after_cmd"] * 16
        ret_words = {
            "spin": assemble_flat(f"JMP 0x{spin_va:x};[7:7:{{}}:6:0]")[0],
            "after": assemble_flat(f"JMP 0x{after_va:x};[7:7:{{}}:6:0]")[0],
        }
    static_stg = assemble_flat(
        f"STG.E.STRONG.GPU [{{R6,R7}}+0x{CMD_RESULT:x}], R30;[7:4:{{}}:8:0]")[0]
    for w in range(total):
        owner.device_write(cmdbuf_base + w * CMBUF_STRIDE + 0x10,
                           struct.pack("<QQ", *static_stg))

    # The wrapper's cubin declares the register budget the GPU allocates
    # per warp.  The heap program is assembled separately (assemble_flat)
    # and its register usage (R14-R30: the warm loop, C1 command words,
    # fresh-jump address pair) is invisible to the wrapper's auto-computed
    # REGCOUNT (16 from R4/R5 alone).  A register outside the declared
    # window faults 715 once the CTA's RF allocation geometry changes:
    # empirically <= 2 warps the overrun lands in unallocated (harmless)
    # RF space, at >= 3 warps it trips a guarded boundary.  Cover every
    # word the GPU can execute from the heap (program, fresh copy, C1
    # command/ret words) using the assembler's own window math.
    heap_words = list(old_enc) + list(fresh_enc)
    heap_words += [old_word, new_word] + list(cmd_words.values())
    heap_words += list(ret_words.values()) + [static_stg]
    regcount = max(32, CubinBuilder._compute_regcount(heap_words))

    wrapper = f"""#fn k(ctrl<8>) {{
    #pragma MAXREG_COUNT({regcount})
    LDC.64 {{R4,R5}}, #param(ctrl);[1:7:{{}}:8:0]
    JMP 0x{heap:x};[7:7:{{}}:6:0]
}}
"""
    mod = CudaModule(assemble(wrapper, check_deps=True))
    stream = CudaModule.stream_create()

    def wslot(w: int, off: int) -> int:
        return ctrl + w * WCTRL + off

    def wr32(w: int, off: int, val: int) -> None:
        owner.device_write(wslot(w, off), struct.pack("<I", val))

    def rd32(w: int, off: int) -> int:
        return _u32(mod, wslot(w, off))

    def progress(w: int) -> int:
        return rd32(w, PROGRESS)

    def wait_all(off: int, want: int, timeout: float = 5.0) -> None:
        t0 = time.time()
        while True:
            bad = [w for w in range(total) if rd32(w, off) != want]
            if not bad:
                return
            if time.time() - t0 > timeout:
                raise TimeoutError(f"slot {off:#x}!={want}: warps {bad}")
            time.sleep(0.001)

    def drain() -> bool:
        """Release every warp so a failed iteration cannot wedge the
        stream: A exits on A_CMD, B finishes on FINISH."""
        for w in range(total):
            wr32(w, FINISH, 1)
        for w in range(total):
            wr32(w, A_CMD, 1)
        return _wait_stream(stream, 5.0)

    def emit(it: int, outcome: str, detail: str) -> None:
        print(f"ITER {it} {name} outcome={outcome} {detail}".rstrip(),
              flush=True)

    for it in range(iters):
        # --- reset per-iteration device state
        owner.device_write(ctrl, bytes(total * WCTRL))
        if case.patch == "frozen":
            owner.device_write(site_va, old_pk)      # canonical between runs
        resume = fresh_va if case.patch == "fresh" else site_va
        for w in range(total):
            owner.device_write(wslot(w, RESUME_T), struct.pack("<Q", resume))
        if case.patch == "before":
            owner.device_write(site_va, new_pk)

        mod.launch("k", grid=(ctas,), block=(32 * warps,), args=[ctrl],
                   stream=stream)

        # --- handoff + freeze acknowledgement
        try:
            wait_all(B_YIELDED, 1)
            wait_all(A_READY, 1)
        except TimeoutError as e:
            if not drain():
                emit(it, "SETUP", f"setup {e} drain_failed")
                os._exit(6)
            emit(it, "SETUP", f"setup {e}")
            continue

        p0 = [progress(w) for w in range(total)]
        if patch_delay_ms:
            time.sleep(patch_delay_ms / 1000.0)
        if case.patch == "frozen":
            owner.device_write(site_va, new_pk)
        if case.patch in ("before", "frozen"):
            got = struct.unpack("<QQ", owner.device_read(site_va, 16))
            if got != new_word:
                if not drain():
                    emit(it, "SETUP", "patch_write_mismatch drain_failed")
                    os._exit(6)
                emit(it, "SETUP", "patch_write_mismatch")
                continue
        p1 = [progress(w) for w in range(total)]
        time.sleep(freeze_ms / 1000.0)
        p2 = [progress(w) for w in range(total)]
        frozen = all(p0[w] == p1[w] == p2[w] for w in range(total))

        if case.cooperative:
            advanced = any(p2[w] != p0[w] for w in range(total))
            emit(it, "PASS" if advanced else "FREEZE",
                 f"progress={p0[0]},{p2[0]}")
            break    # B intentionally never stops; teardown cleans up

        if case.cmd:
            # --- C1: command rounds through the per-warp buffer
            cmd_ok, frozen_mid, plateaus = True, True, []
            expected = 0
            for r, (delta, target) in enumerate(ROUNDS):
                expected += delta
                word = cmd_words[delta]
                retw = ret_words[target]
                for w in range(total):
                    owner.device_write(wslot(w, CMD_WORD),
                                       struct.pack("<QQ", *word))
                    owner.device_write(wslot(w, RET_WORD),
                                       struct.pack("<QQ", *retw))
                    if r == len(ROUNDS) - 1:
                        wr32(w, FINISH, 1)
                    wr32(w, A_CMD, r + 1)
                for w in range(total):
                    got = _poll(lambda w=w: rd32(w, CMD_RESULT), expected, 2.0)
                    if not got:
                        cmd_ok = False
                        plateaus.append(f"r{r + 1}w{w}="
                                        f"{rd32(w, CMD_RESULT):#x}")
                        break
                if not cmd_ok:
                    break
                if any(progress(w) != p0[w] for w in range(total)):
                    frozen_mid = False
                    break
            if cmd_ok and frozen_mid:
                if not _wait_stream(stream, 5.0):
                    emit(it, "TIMEOUT", "c1_completion")
                    os._exit(4)
            else:
                if not drain():
                    emit(it, "VISIBILITY" if not cmd_ok else "FREEZE",
                         f"{' '.join(plateaus)} drain_failed")
                    os._exit(6)
                emit(it, "VISIBILITY" if not cmd_ok else "FREEZE",
                     f"{' '.join(plateaus)} (expected {expected:#x})")
                continue
            deltas = [(rd32(w, AFTER) - rd32(w, BEFORE)) & 0xFFFFFFFF
                      for w in range(total)]
            kinds = _delta_kinds(case, deltas, staggered)
            b_ok = all(k == "old" for k in kinds)
            if frozen and frozen_mid and cmd_ok and b_ok:
                emit(it, "PASS", f"cmd={expected:#x} deltas={deltas}")
            elif not (frozen and frozen_mid):
                emit(it, "FREEZE", f"progress={p0},{p1},{p2}")
            else:
                emit(it, "VISIBILITY",
                     f"cmd={expected:#x} deltas={deltas} b={kinds}")
            continue

        # --- release
        if staggered and total > 1:
            wr32(0, A_CMD, 1)
            if case.patch != "fresh":
                if not _poll(lambda: progress(0) != p2[0], True, 2.0):
                    emit(it, "TIMEOUT", "stagger_warp0_no_progress")
                    os._exit(4)
            else:
                if not _poll(lambda: rd32(0, AFTER) != 0, True, 2.0):
                    emit(it, "TIMEOUT", "stagger_warp0_no_finish")
                    os._exit(4)
            time.sleep(freeze_ms / 1000.0)
            p3 = [progress(w) for w in range(1, total)]
            frozen_others = all(p3[i] == p2[w]
                                for i, w in enumerate(range(1, total)))
            for w in range(1, total):
                wr32(w, FINISH, 1)
            wr32(0, FINISH, 1)
            for w in range(1, total):
                wr32(w, A_CMD, 1)
            if not _wait_stream(stream, 5.0):
                emit(it, "TIMEOUT", "stagger_completion")
                os._exit(4)
            frozen = frozen and frozen_others
        else:
            for w in range(total):
                wr32(w, FINISH, 1)
            for w in range(total):
                wr32(w, A_CMD, 1)
            if not _wait_stream(stream, 5.0):
                emit(it, "TIMEOUT", "completion")
                os._exit(4)

        deltas = [(rd32(w, AFTER) - rd32(w, BEFORE)) & 0xFFFFFFFF
                  for w in range(total)]
        kinds = _delta_kinds(case, deltas, staggered)
        if not frozen:
            emit(it, "FREEZE", f"progress={p0},{p1},{p2} deltas={deltas}")
        elif case.patch == "none":
            good = all(k == "old" for k in kinds)
            emit(it, "PASS" if good else "VISIBILITY",
                 f"deltas={deltas} kinds={kinds}")
        else:
            stale = sum(1 for k in kinds if k != "new")
            verdict = "new" if stale == 0 else (
                "stale" if stale == len(kinds) else "mixed")
            emit(it, "PASS" if stale == 0 else "VISIBILITY",
                 f"deltas={deltas} verdict={verdict}")

    print("CHILD_DONE", flush=True)


def run_parent(repeat: int, names: list[str], handoff: str,
               ivall_count: int, ivall_nops: int, *, warps: int, ctas: int,
               settle: int, patch_delay_ms: float, freeze_ms: float,
               staggered: bool, iters: int, gate_min: int) -> int:
    this = str(Path(__file__).resolve())
    agg: dict[str, Counter] = {name: Counter() for name in names}
    for name in names:
        for i in range(repeat):
            try:
                r = subprocess.run(
                    [sys.executable, this, "--child", name,
                     "--handoff", handoff,
                     "--ivall-count", str(ivall_count),
                     "--ivall-nops", str(ivall_nops),
                     "--warps", str(warps), "--ctas", str(ctas),
                     "--settle", str(settle),
                     "--patch-delay-ms", str(patch_delay_ms),
                     "--freeze-ms", str(freeze_ms),
                     "--iters", str(iters)]
                    + (["--staggered"] if staggered else []),
                    capture_output=True, text=True, timeout=30 + iters * 0.5)
            except subprocess.TimeoutExpired:
                agg[name]["child_timeout"] += 1
                print(f"FAIL {name}[{i}]: subprocess timeout")
                continue
            rows = [ln for ln in r.stdout.splitlines()
                    if ln.startswith("ITER ")]
            for ln in rows:
                outcome = ln.split("outcome=", 1)[1].split()[0]
                agg[name][outcome] += 1
                print(f"{'ok ' if outcome == 'PASS' else '!!'} {name}[{i}] "
                      f"{ln.split(' ', 2)[2]}")
            if "CHILD_DONE" not in r.stdout:
                agg[name]["abort"] += 1
                print(f"FAIL {name}[{i}]: child aborted "
                      f"(rc={r.returncode})")
                if r.stderr:
                    print(r.stderr[-1200:])
            if r.returncode != 0 and "CHILD_DONE" in r.stdout:
                agg[name]["rc_nonzero"] += 1

    print("\n=== summary ===")
    totals = Counter()
    for name, c in agg.items():
        totals.update(c)
        print(f"{name}: " + " ".join(f"{k}={v}" for k, v in sorted(c.items())))
    valid = totals["PASS"] + totals["VISIBILITY"]
    print(f"total: valid={valid} (pass={totals['PASS']} "
          f"visibility={totals['VISIBILITY']}) setup={totals['SETUP']} "
          f"freeze={totals['FREEZE']} timeout={totals['TIMEOUT']} "
          f"abort={totals['abort']}")
    rc = 0
    if gate_min:
        gate = (totals["VISIBILITY"] == 0 and totals["FREEZE"] == 0
                and totals["TIMEOUT"] == 0 and totals["abort"] == 0
                and valid >= gate_min)
        print(f"GATE {'PASS' if gate else 'FAIL'} "
              f"valid={valid} stale={totals['VISIBILITY']} "
              f"freeze={totals['FREEZE']} setup={totals['SETUP']} "
              f"(min={gate_min})")
        rc = 0 if gate else 1
    elif totals["VISIBILITY"] or totals["FREEZE"] or totals["TIMEOUT"]:
        rc = 1
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", choices=CASES)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--iters", type=int, default=1,
                    help="iterations per child process (batched, warm ctx)")
    ap.add_argument("--cases", nargs="+", choices=CASES,
                    default=list(CASES),
                    help="parent-mode case subset (default: all)")
    ap.add_argument("--handoff", choices=("yield", "nanosleep"),
                    default="nanosleep",
                    help="B-to-A execution-group handoff primitive")
    ap.add_argument("--ivall-count", type=int, choices=(0, 1, 2), default=2,
                    help="IVALL count in the frozen-warp path "
                         "(default: hardened pair)")
    ap.add_argument("--ivall-nops", type=int, default=32,
                    help="stall-8 NOPs after the first IVALL")
    ap.add_argument("--warps", type=int, default=1,
                    help="warps per CTA (block = 32*warps)")
    ap.add_argument("--ctas", type=int, default=1)
    ap.add_argument("--settle", type=int, default=0,
                    help="no-yield settling iterations in the handler "
                         "before the freeze acknowledgement")
    ap.add_argument("--patch-delay-ms", type=float, default=0.0,
                    help="host dwell between ack and patch (0 = immediate)")
    ap.add_argument("--freeze-ms", type=float, default=2.0,
                    help="sibling-progress sampling window while frozen")
    ap.add_argument("--staggered", action="store_true",
                    help="release warp 0 first; other warps must stay "
                         "frozen with constant progress (isolation)")
    ap.add_argument("--gate-min", type=int, default=0,
                    help="if set, require >= this many valid iterations "
                         "with zero stale/freeze/timeout and print a "
                         "GATE line")
    args = ap.parse_args()
    if args.ivall_nops < 0:
        ap.error("--ivall-nops must be non-negative")
    if args.iters < 1 or args.repeat < 1:
        ap.error("--iters/--repeat must be >= 1")
    if args.warps < 1 or args.ctas < 1:
        ap.error("--warps/--ctas must be >= 1")
    if args.warps * args.ctas * CMBUF_STRIDE > HEAP_SIZE - CMDBUF_OFF:
        ap.error("warps*ctas too large for the command-buffer arena")
    if args.child:
        run_child(args.child, args.handoff, args.ivall_count,
                  args.ivall_nops, warps=args.warps, ctas=args.ctas,
                  settle=args.settle, patch_delay_ms=args.patch_delay_ms,
                  freeze_ms=args.freeze_ms, staggered=args.staggered,
                  iters=args.iters)
        return 0
    return run_parent(args.repeat, args.cases, args.handoff,
                      args.ivall_count, args.ivall_nops,
                      warps=args.warps, ctas=args.ctas, settle=args.settle,
                      patch_delay_ms=args.patch_delay_ms,
                      freeze_ms=args.freeze_ms, staggered=args.staggered,
                      iters=args.iters, gate_min=args.gate_min)


if __name__ == "__main__":
    sys.exit(main())
