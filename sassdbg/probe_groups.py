"""probe groups: M8a — resume-thunk primitives for divergence-aware
breakpoints.

Design under test (user proposal, M8 plan):

  * resume NO LONGER restores the site word.  Instead the host builds a
    per-warp RESUME THUNK in the blob's thunk arena ([THUNK_OFF, BLOB_SZ),
    128B-strided slots):  `INST1 ; JMP imm fallthrough`.  The handler's
    exit RETs into the thunk (comms COMMS_RTGT override; 0 = legacy
    site-RET).  The site stays patched for the bp's whole lifetime ->
    no icache restore race against still-running groups/warps, and bps
    become persistent (gdb-style; disarm only at a parked boundary).
  * JMP IMM (0x94a, UImm(57) SCALE 4) is the absolute-jump primitive:
    probe_rpc_writers proved it transfers to a devmem VA and preserves
    the RPC sentinel.  Conditional BRA emulation = `@P0 JMP T; JMP ft`.
  * BSSY's Sa target is INERT (notes/sm90/instr/bssy.md "Resolved") ->
    a BSSY thunk is the verbatim instruction; the participant mask is
    collected from the executing group, which is the same mask the site
    execution would have seen.
  * BSYNC: groups parked at the same BSYNC bp of one warp share the
    warp's blob, hence the SAME thunk VA -> same-PC rendezvous by
    construction.

Experiments (each runs as its own process — a faulting kernel poisons
its context and a hung kernel deadlocks cuCtxDestroy):

  E1  thunk-resume basics: bp inside a 3-iteration tight loop, 3 hits
      from ONE arming (persistence + tight-loop re-hit reliability,
      which site-restore never had), correct final value.
  E2  divergent conditional BRA thunk: `@P0 JMP else; JMP ft`, one hit,
      both lane halves produce their path's values.
  E3  BSSY thunk: verbatim BSSY + JMP back; divergent if/else with
      BSSY/BSYNC completes correctly.
  E4  BSYNC shared thunk: bps at BSSY and BSYNC; both groups park at
      the BSYNC bp; ONE thunk-resume releases both into the same thunk
      VA; rendezvous at the thunk's BSYNC; correct results.
      KEY FINDING: while one group spins in the handler, its divergent
      sibling makes NO progress (lanes 0-15 never parked within 5 s
      while 16-31 spun; they arrive only after the parked group is
      released and BLOCKS at the thunk's BSYNC — a convergence wait is
      what schedules the sibling).  "Wait for both groups to park, then
      resume" DEADLOCKS; resume must be PROMPT, and the stepper must be
      an event loop (release -> hit -> immediately re-release).  This
      makes M8b's barrier-assisted resume mandatory, not optional.
      Also: late-arriving groups read the CURRENT gen as their spin
      baseline, so one per-warp gen word cannot release a group that
      parked after the bump — M8b needs per-lane/per-group release
      words and per-group hit slots.
  E5  THE M8b PAYOFF: bps at DIFFERENT sites in the two branch bodies.
      Both divergent groups park simultaneously (NANOSLEEP in the spin),
      each reports via its own leader-lane hit slot (FLO(mask) is
      unique across disjoint masks — no atomics, no URs), and each is
      released with its OWN thunk via per-lane RTGTV/RLGEN words.
      Correct per-lane results.
"""
import faulthandler
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sassdbg.patch import Debugger  # noqa: E402

faulthandler.dump_traceback_later(120, exit=True)

K_LOOP = """\
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    MOV32I R2, 0x0;[7:7:{0,1}:5:1]
    MOV32I R3, 0x0;[7:7:{}:5:1]
#def_label(loop)
    IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]
    IADD3 R3, R3, 0x1, RZ;[7:7:{}:5:1]
    ISETP.LT.AND P0, PT, R3, 0x3, PT;[7:7:{}:13:1]
    @P0 BRA #label(loop);[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R4,R5}], R2;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""
# orig indices: 0 LDCU / 1 LDC / 2 MOV / 3 MOV / 4 IADD3(bp) / 5 IADD3 /
#               6 ISETP / 7 BRA / 8 STG / 9 EXIT

K_DIV = """\
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{0,1}:5:1]
    LOP3.LUT R2, R2, 0x1F, RZ, 0xC0;[7:7:{5}:5:1]
    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{}:13:1]
    BSSY B0, #label(join);[7:7:{}:5:1]
    @P0 BRA #label(else);[7:7:{}:5:1]
    MOV32I R3, 0xA0;[7:7:{}:5:1]
    BRA #label(sync);[7:7:{}:5:1]
#def_label(else)
    MOV32I R3, 0xB0;[7:7:{}:5:1]
#def_label(sync)
    BSYNC B0;[7:7:{}:4:0]
#def_label(join)
    IMAD R3, R3, R2, RZ;[7:7:{}:5:1]
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}], R3;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""
# orig indices: 0 LDCU / 1 LDC / 2 S2R / 3 LOP3 / 4 ISETP / 5 BSSY /
#               6 @P0 BRA / 7 MOV A0 / 8 BRA / 9 MOV B0 / 10 BSYNC /
#               11 IMAD / 12 IMAD.WIDE / 13 STG / 14 EXIT
# lanes 0-15 take else (0xB0), lanes 16-31 fall through (0xA0).

K_NODIV = """\
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{0,1}:5:1]
    LOP3.LUT R2, R2, 0x1F, RZ, 0xC0;[7:7:{5}:5:1]
    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{}:13:1]
    @P0 BRA #label(else);[7:7:{}:5:1]
    MOV32I R3, 0xA0;[7:7:{}:5:1]
    BRA #label(join);[7:7:{}:5:1]
#def_label(else)
    MOV32I R3, 0xB0;[7:7:{}:5:1]
#def_label(join)
    IMAD R3, R3, R2, RZ;[7:7:{}:5:1]
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}], R3;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""
# orig indices: 0 LDCU / 1 LDC / 2 S2R / 3 LOP3 / 4 ISETP / 5 @P0 BRA(bp)
#               6 MOV A0 / 7 BRA / 8 MOV B0 / 9 IMAD / 10 IMAD.WIDE /
#               11 STG / 12 EXIT


def _mk(src: str) -> tuple[Debugger, int]:
    dbg = Debugger(src)
    out = dbg.mod.devmem_alloc(0x100)
    dbg.mod.device_write(out, bytes(0x100))
    dbg.launch(args=[out])
    dbg.wait_base()
    return dbg, out


def _check_div_out(dbg: Debugger, out: int, tag: str) -> None:
    v = struct.unpack("<32I", dbg.mod.device_read(out, 0x80))
    want = [(0xB0 if lane < 16 else 0xA0) * lane for lane in range(32)]
    assert list(v) == want, f"{tag}: {v[:4]}...{v[16:20]} != {want[:4]}..."
    print(f"  {tag}: out[lane] == path*lane for all 32 lanes  OK")


def e1() -> None:
    dbg, out = _mk(K_LOOP)
    bp = dbg.arm(4)                      # IADD3 inside the loop
    dbg.release()
    for i in range(3):
        h = dbg.wait_hit()
        assert h is bp, (h, bp)
        dbg.resume_thunk(bp, ["IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]"])
        print(f"  hit {i + 1}: thunk-resumed (site still armed)")
    dbg.wait_done()
    v = struct.unpack("<I", dbg.mod.device_read(out, 4))[0]
    assert v == 21, hex(v)
    print("  out == 21 (3 x 7)  OK — persistent bp, tight-loop re-hits,"
          " JMP-back into the loop body")


def e2() -> None:
    dbg, out = _mk(K_NODIV)
    bp = dbg.arm(5)                      # @P0 BRA else
    dbg.release()
    h = dbg.wait_hit()
    assert h is bp
    else_va = dbg._site_va(8)
    dbg.resume_thunk(bp, [f"@P0 JMP 0x{else_va:x};[7:7:{{}}:6:0]"])
    dbg.wait_done()
    _check_div_out(dbg, out, "E2")
    print("  conditional-BRA thunk: @P0 JMP else / JMP fallthrough  OK")


def e3() -> None:
    dbg, out = _mk(K_DIV)
    bp = dbg.arm(5)                      # BSSY
    dbg.release()
    h = dbg.wait_hit()
    assert h is bp
    # BSSY's Sa is inert -> verbatim instruction; the label makes the
    # thunk self-consistent (target = thunk-local, never consumed).
    dbg.resume_thunk(bp, ["BSSY B0, #label(tk);[7:7:{}:5:1]",
                          "#def_label(tk)"])
    dbg.wait_done()
    _check_div_out(dbg, out, "E3")
    print("  BSSY thunk: participant mask collected in thunk,"
          " kernel BSYNC rendezvous  OK")


def _parked_lane_mask(dbg: Debugger, warp: int) -> int:
    """Per-lane presence probe: every lane still polling in the handler
    spin writes lane+1 to its own results slot.  Returns the mask of
    parked lanes (union over all parked groups of the warp)."""
    dbg.exec_cmd(warp, [
        "S2R R246, SR_TID.X;[5:7:{}:5:1]",
        "LOP3.LUT R246, R246, 0x1F, RZ, 0xC0;[7:7:{5}:5:1]",
        "IMAD R248, R246, 0x4, R252;[7:7:{}:5:1]",
        "MOV R249, R253;[7:7:{}:5:1]",
        "IADD3 R247, R246, 0x1, RZ;[7:7:{}:5:1]",
        "STG.E.STRONG.GPU [{R248,R249}+0x40100], R247;[7:7:{}:8:0]",
    ])
    pres = struct.unpack("<32I", dbg.cmd_read(warp, 0, 128))
    m = 0
    for i, x in enumerate(pres):
        if x == i + 1:
            m |= 1 << i
    return m


def _wait_all_parked(dbg: Debugger, warp: int,
                     timeout: float = 5.0) -> int:
    """Wait until every lane of the warp sits in the handler spin
    (all divergent groups arrived at their patched sites)."""
    t0 = time.time()
    while True:
        m = _parked_lane_mask(dbg, warp)
        if m == 0xFFFFFFFF:
            return m
        if time.time() - t0 > timeout:
            raise TimeoutError(f"parked lanes {m:#010x} != all-32")
        time.sleep(0.01)


def e4() -> None:
    dbg, out = _mk(K_DIV)
    bp_bssy = dbg.arm(5)
    bp_bsync = dbg.arm(10)
    dbg.release()
    h = dbg.wait_hit()
    assert h is bp_bssy
    dbg.resume_thunk(bp_bssy, ["BSSY B0, #label(tk);[7:7:{}:5:1]",
                               "#def_label(tk)"])
    h = dbg.wait_hit()
    assert h is bp_bsync, h.orig_index
    # with NANOSLEEP in the handler spin the parked group no longer starves
    # its divergent sibling: the sibling reaches the patched site and
    # parks promptly — BOTH groups are parked before one resume.
    m = _wait_all_parked(dbg, 0, timeout=5.0)
    print(f"  all 32 lanes parked (mask {m:#010x}) — NANOSLEEP cured the"
          " sibling starvation")
    dbg.resume_thunk(bp_bsync, ["BSYNC B0;[7:7:{}:4:0]"])
    dbg.wait_done()
    _check_div_out(dbg, out, "E4")
    print("  BSYNC shared thunk: one resume releases both parked groups,"
          " rendezvous at the thunk's BSYNC  OK")


def e5() -> None:
    """bps at BOTH branch bodies (different sites) — the M8b payoff:
    both divergent groups park simultaneously (NANOSLEEP in the spin),
    each
    is reported via its own leader-lane hit slot, and each is released
    with its OWN thunk (per-lane RTGTV/RLGEN).  Correct results."""
    dbg, out = _mk(K_DIV)
    bp_then = dbg.arm(7)                 # MOV32I 0xA0 (fall-through body)
    bp_else = dbg.arm(9)                 # MOV32I 0xB0 (else body)
    dbg.release()
    w1, g1 = dbg.wait_group_hit()
    w2, g2 = dbg.wait_group_hit()
    print(f"  group1: warp {w1} site {g1.bp.orig_index}"
          f" mask {g1.mask:#010x}")
    print(f"  group2: warp {w2} site {g2.bp.orig_index}"
          f" mask {g2.mask:#010x}")
    assert w1 == w2 == 0
    assert g1.mask & g2.mask == 0 and (g1.mask | g2.mask) == 0xFFFFFFFF
    assert {g1.bp, g2.bp} == {bp_then, bp_else}
    for g in (g1, g2):
        if g.bp is bp_then:
            dbg.release_group(0, g, ["MOV32I R3, 0xA0;[7:7:{}:5:1]"])
        else:
            dbg.release_group(0, g, ["MOV32I R3, 0xB0;[7:7:{}:5:1]"])
    dbg.wait_done()
    _check_div_out(dbg, out, "E5")
    print("  two groups at different sites released with their own"
          " thunks, results correct  OK")


EXPERIMENTS = {"E1": e1, "E2": e2, "E3": e3, "E4": e4, "E5": e5}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        EXPERIMENTS[sys.argv[1]]()
        print(f"probe_groups {sys.argv[1]}: OK")
    else:
        ok = True
        for name in EXPERIMENTS:
            r = subprocess.run(
                [sys.executable, __file__, name],
                capture_output=True, text=True, timeout=180)
            status = "OK" if r.returncode == 0 else "FAIL"
            if r.returncode != 0:
                ok = False
            print(f"== {name}: {status}")
            print(r.stdout, end="")
            if r.returncode != 0:
                print(r.stderr[-1500:])
        print("== probe_groups: ALL OK ==" if ok else "== FAILURES ==")
        sys.exit(0 if ok else 1)
