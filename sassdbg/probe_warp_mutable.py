"""Probe per-warp mutable heap SASS under divergent execution groups.

One warp splits into A={lanes 1..31} and B={lane 0}.  A yields once,
B heats a tight loop and yields back, then A enters either a tight polling
handler or a NANOSLEEP polling handler.  The host checks whether B advances
and, for the tight-handler cases, patches B's hot loop while it is frozen.

Cases (each runs in a disposable subprocess):
  F0  NANOSLEEP handler: B must make progress (positive control)
  F1  tight handler: B must stop; no patch, resume gives delta +1
  P1  site patched before launch: resumed delta +0x100
  P2  frozen in-place patch, no IVALL (diagnostic)
  P3  frozen in-place patch, hardened IVALL (decisive tight-loop case)
  P4  resume at a never-fetched fresh VA containing +0x100 (positive control)
  P5  P3 with a ~2 KiB fat loop (refetch control)

Run:
    python3 -m sassdbg.probe_warp_mutable [--repeat N]
    python3 -m sassdbg.probe_warp_mutable --cases F1 P2 P3 P4 --repeat 30
    python3 -m sassdbg.probe_warp_mutable --child P3

Results (2026-08-30):
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
"""
from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402


A_READY = 0x00
A_CMD = 0x04
B_YIELDED = 0x08
FINISH = 0x0C
RESUME_TARGET = 0x10              # u64
BEFORE = 0x18
AFTER = 0x1C
PROGRESS = 0x20

OLD_OFF = 0x0000
FRESH_OFF = 0x8000
HEAP_SIZE = 0x10000
WARM_ITERS = 0x40

SITE_OLD = "IADD3 R20, R20, 0x1, RZ;[7:7:{}:5:1]"
SITE_NEW = "IADD3 R20, R20, 0x100, RZ;[7:7:{}:5:1]"


@dataclass(frozen=True)
class Case:
    cooperative: bool = False
    fat: bool = False
    patch: str = "none"             # none / before / frozen / fresh
    ivall: str = "hard"             # none / hard


CASES = {
    "F0": Case(cooperative=True),
    "F1": Case(),
    "P1": Case(patch="before"),
    "P2": Case(patch="frozen", ivall="none"),
    "P3": Case(patch="frozen", ivall="hard"),
    "P4": Case(patch="fresh", ivall="hard"),
    "P5": Case(fat=True, patch="frozen", ivall="hard"),
}


def _inst_count(src: str) -> int:
    return sum(1 for ln in src.splitlines() if ";[" in ln)


def _old_program(case: Case, handoff: str, ivall_count: int = 2,
                 ivall_nops: int = 32) -> tuple[str, int]:
    """Return (plain SASS, SITE instruction index)."""
    pad = "    NOP;[7:7:{}:8:0]\n" * (120 if case.fat else 0)
    sleep = "    NANOSLEEP 0x100;[7:7:{}:5:1]\n" \
        if case.cooperative else ""
    if case.ivall == "hard" and ivall_count:
        invalidate = "    CCTL.I.IVALL;[7:7:{}:4:0]\n"
        invalidate += "    NOP;[7:7:{}:8:0]\n" * ivall_nops
        if ivall_count == 2:
            invalidate += "    CCTL.I.IVALL;[7:7:{}:4:0]\n"
    else:
        invalidate = ""

    head = f"""\
    MOV R5, R5;[7:7:{{1}}:5:1]
    S2R R2, SR_TID.X;[5:7:{{}}:5:1]
    ISETP.EQ.AND P0, PT, R2, 0x0, PT;[7:7:{{5}}:13:1]
    ISETP.EQ.AND P1, PT, R2, 0x1, PT;[7:7:{{}}:13:1]
    MOV32I R10, 0x1;[7:7:{{}}:5:1]
    @P0 BRA #label(group_b);[7:7:{{}}:6:0]

    YIELD;[7:7:{{}}:5:1]
    @P1 STG.E.STRONG.GPU [{{R4,R5}}+0x{A_READY:x}], R10;[7:1:{{}}:8:0]
#def_label(handler_spin)
{sleep}    LDG.E.STRONG.GPU R12, [{{R4,R5}}+0x{A_CMD:x}];[2:7:{{}}:8:0]
    ISETP.EQ.AND P2, PT, R12, RZ, PT;[7:7:{{2}}:13:1]
    @P2 BRA #label(handler_spin);[7:7:{{}}:6:0]
{invalidate}    EXIT;[7:7:{{}}:5:0]

#def_label(group_b)
    MOV32I R20, 0x0;[7:7:{{}}:5:1]
    MOV32I R21, 0x0;[7:7:{{}}:5:1]
    MOV32I R22, 0x0;[7:7:{{}}:5:1]
#def_label(loop)
    IADD3 R21, R21, 0x1, RZ;[7:7:{{}}:5:1]
    STG.E.STRONG.GPU [{{R4,R5}}+0x{PROGRESS:x}], R21;[7:1:{{}}:8:0]
    ISETP.GE.U32.AND P2, PT, R21, 0x{WARM_ITERS:x}, PT;[7:7:{{}}:13:1]
    ISETP.EQ.AND P3, PT, R22, RZ, P2;[7:7:{{}}:13:1]
    @P3 MOV32I R22, 0x1;[7:7:{{}}:5:1]
    @P3 STG.E.STRONG.GPU [{{R4,R5}}+0x{BEFORE:x}], R20;[7:1:{{}}:8:0]
    @P3 STG.E.STRONG.GPU [{{R4,R5}}+0x{B_YIELDED:x}], R10;[7:1:{{}}:8:0]
    @P3 {handoff};[7:7:{{}}:5:1]
"""
    # P4 deliberately redirects the resumed group to a never-fetched VA.
    # Every other case falls straight through from YIELD to SITE, retaining
    # the strongest possible old-loop/fetch-buffer state.
    if case.patch == "fresh":
        head += f"""\
    @P3 LDG.E.64.STRONG.GPU {{R24,R25}}, [{{R4,R5}}+0x{RESUME_TARGET:x}];[2:7:{{}}:8:0]
    @P3 JMX {{R24,R25}}, 0x0;[7:7:{{2}}:13:1]
"""
    site_idx = _inst_count(head)
    tail = f"""\
    {SITE_OLD}
{pad}    LDG.E.STRONG.GPU R12, [{{R4,R5}}+0x{FINISH:x}];[2:7:{{}}:8:0]
    ISETP.NE.AND P4, PT, R12, RZ, PT;[7:7:{{2}}:13:1]
    @P4 BRA #label(done);[7:7:{{}}:6:0]
    BRA #label(loop);[7:7:{{}}:6:0]

#def_label(done)
    STG.E.STRONG.GPU [{{R4,R5}}+0x{AFTER:x}], R20;[7:1:{{}}:8:0]
    EXIT;[7:7:{{1}}:5:0]
"""
    return head + tail, site_idx


def _fresh_program() -> str:
    return f"""\
    {SITE_NEW}
    STG.E.STRONG.GPU [{{R4,R5}}+0x{AFTER:x}], R20;[7:1:{{}}:8:0]
    EXIT;[7:7:{{1}}:5:0]
"""


def _u32(mod: CudaModule, va: int) -> int:
    return struct.unpack("<I", mod.device_read(va, 4))[0]


def _wait_u32(mod: CudaModule, va: int, want: int = 1,
              timeout: float = 5.0) -> None:
    t0 = time.time()
    while _u32(mod, va) != want:
        if time.time() - t0 > timeout:
            raise TimeoutError(f"timeout waiting for {va:#x} == {want}")
        time.sleep(0.001)


def run_child(name: str, handoff: str, ivall_count: int,
              ivall_nops: int) -> None:
    case = CASES[name]

    # A tiny already-loaded module establishes the shared context and owns
    # allocations whose VAs must be baked into the wrapper before it loads.
    owner = CudaModule(assemble(
        "#fn owner() {\n    EXIT;[7:7:{}:5:0]\n}\n"))
    ctrl = owner.devmem_alloc(0x100)
    heap = owner.devmem_alloc(HEAP_SIZE)
    owner.device_write(ctrl, bytes(0x100))
    owner.device_write(heap, bytes(HEAP_SIZE))

    handoff_inst = "YIELD" if handoff == "yield" else "NANOSLEEP 0x100"
    old_src, site_idx = _old_program(case, handoff_inst, ivall_count,
                                     ivall_nops)
    old_enc = assemble_flat(old_src)
    fresh_enc = assemble_flat(_fresh_program())
    assert old_enc and len(old_enc) * 16 < FRESH_OFF
    site_va = heap + OLD_OFF + site_idx * 16
    fresh_va = heap + FRESH_OFF
    owner.device_write(heap + OLD_OFF, b"".join(
        struct.pack("<QQ", lo, hi) for lo, hi in old_enc))
    owner.device_write(fresh_va, b"".join(
        struct.pack("<QQ", lo, hi) for lo, hi in fresh_enc))

    old_word = assemble_flat(SITE_OLD)[0]
    new_word = assemble_flat(SITE_NEW)[0]
    assert old_enc[site_idx] == old_word, (site_idx, old_enc[site_idx], old_word)
    if case.patch == "before":
        owner.device_write(site_va, struct.pack("<QQ", *new_word))

    resume = fresh_va if case.patch == "fresh" else site_va
    owner.device_write(ctrl + RESUME_TARGET, struct.pack("<Q", resume))

    wrapper = f"""#fn k(ctrl<8>) {{
    LDC.64 {{R4,R5}}, #param(ctrl);[1:7:{{}}:8:0]
    JMP 0x{heap:x};[7:7:{{}}:6:0]
}}
"""
    mod = CudaModule(assemble(wrapper, check_deps=True))
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=(32,), args=[ctrl], stream=stream)

    _wait_u32(mod, ctrl + B_YIELDED)
    try:
        _wait_u32(mod, ctrl + A_READY)
    except TimeoutError:
        print(f"RESULT {name} handoff={handoff} "
              f"ivall={ivall_count}x/{ivall_nops}n A_READY_TIMEOUT "
              f"b_yielded={_u32(mod, ctrl + B_YIELDED)} "
              f"progress={_u32(mod, ctrl + PROGRESS)}", flush=True)
        os._exit(5)
    p0 = _u32(mod, ctrl + PROGRESS)
    time.sleep(0.10)
    p1 = _u32(mod, ctrl + PROGRESS)
    time.sleep(0.25)
    p2 = _u32(mod, ctrl + PROGRESS)
    frozen = p0 == p1 == p2

    if case.cooperative:
        print(f"RESULT {name} handoff={handoff} "
              f"ivall={ivall_count}x/{ivall_nops}n "
              f"progress={p0},{p1},{p2} "
              f"advanced={int(not frozen)}", flush=True)
        # B intentionally owns a no-yield loop now; context teardown is the
        # cleanup mechanism, exactly like test_yield's negative controls.
        os._exit(0 if not frozen else 2)

    if not frozen:
        print(f"RESULT {name} handoff={handoff} "
              f"ivall={ivall_count}x/{ivall_nops}n "
              f"progress={p0},{p1},{p2} frozen=0",
              flush=True)
        os._exit(3)

    if case.patch == "frozen":
        owner.device_write(site_va, struct.pack("<QQ", *new_word))
        got = struct.unpack("<QQ", owner.device_read(site_va, 16))
        assert got == new_word, (got, new_word)

    # Publish all data before waking A.  A optionally invalidates the target
    # SM's icache, exits, and B resumes at old SITE or the fresh code VA.
    owner.device_write(ctrl + FINISH, struct.pack("<I", 1))
    owner.device_write(ctrl + A_CMD, struct.pack("<I", 1))

    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > 5.0:
            print(f"RESULT {name} handoff={handoff} "
                  f"ivall={ivall_count}x/{ivall_nops}n TIMEOUT "
                  f"progress={_u32(mod, ctrl + PROGRESS)}",
                  flush=True)
            os._exit(4)
        time.sleep(0.001)
    CudaModule.stream_sync(stream)
    before = _u32(mod, ctrl + BEFORE)
    after = _u32(mod, ctrl + AFTER)
    delta = (after - before) & 0xFFFFFFFF
    print(f"RESULT {name} handoff={handoff} "
          f"ivall={ivall_count}x/{ivall_nops}n "
          f"progress={p0},{p1},{p2} frozen=1 "
          f"before={before:#x} after={after:#x} delta={delta:#x}",
          flush=True)


def run_parent(repeat: int, names: list[str], handoff: str,
               ivall_count: int, ivall_nops: int) -> int:
    ok = True
    this = str(Path(__file__).resolve())
    results: dict[str, list[str]] = {name: [] for name in names}
    for name in names:
        for i in range(repeat):
            try:
                r = subprocess.run(
                    [sys.executable, this, "--child", name,
                     "--handoff", handoff,
                     "--ivall-count", str(ivall_count),
                     "--ivall-nops", str(ivall_nops)],
                    capture_output=True, text=True, timeout=12)
            except subprocess.TimeoutExpired:
                ok = False
                results[name].append("TIMEOUT")
                print(f"FAIL {name}[{i}]: subprocess timeout")
                continue
            line = next((ln for ln in r.stdout.splitlines()
                         if ln.startswith("RESULT ")), "NO_RESULT")
            results[name].append(line)
            good = r.returncode == 0
            if name == "F0":
                good = good and "advanced=1" in line
            elif name in ("F1",):
                good = good and "delta=0x1" in line
            elif name in ("P1", "P4", "P5"):
                good = good and "delta=0x100" in line
            elif name == "P3":
                # Decisive observation, not a pre-imposed expected result.
                good = good and ("delta=0x1" in line or
                                  "delta=0x100" in line)
            elif name == "P2":
                good = good and ("delta=0x1" in line or
                                  "delta=0x100" in line)
            print(f"{'ok ' if good else 'FAIL'} {name}[{i}]: {line}")
            if not good:
                ok = False
                if r.stderr:
                    print(r.stderr[-1200:])

    print("\n=== summary ===")
    for name, rows in results.items():
        deltas = []
        for row in rows:
            marker = "delta="
            if marker in row:
                deltas.append(row.split(marker, 1)[1].split()[0])
        print(f"{name}: runs={len(rows)} deltas={deltas or '-'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", choices=CASES)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--cases", nargs="+", choices=CASES,
                    default=list(CASES),
                    help="parent-mode case subset (default: all)")
    ap.add_argument("--handoff", choices=("yield", "nanosleep"),
                    default="nanosleep",
                    help="B-to-A execution-group handoff primitive")
    ap.add_argument("--ivall-count", type=int, choices=(0, 1, 2), default=2,
                    help="P3/P4/P5 IVALL count (default: hardened pair)")
    ap.add_argument("--ivall-nops", type=int, default=32,
                    help="stall-8 NOPs after the first IVALL")
    args = ap.parse_args()
    if args.ivall_nops < 0:
        ap.error("--ivall-nops must be non-negative")
    if args.child:
        run_child(args.child, args.handoff, args.ivall_count,
                  args.ivall_nops)
        return 0
    return run_parent(args.repeat, args.cases, args.handoff,
                      args.ivall_count, args.ivall_nops)


if __name__ == "__main__":
    sys.exit(main())
