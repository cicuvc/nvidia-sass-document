"""sassdbg M8d / E6 — BAR.SYNC / WARPSYNC cross-PC rendezvous probes.

The thunk model replays a parked group's barrier instruction from the
blob (a DIFFERENT PC than the kernel's).  Question: do the hardware
barrier mechanisms rendezvous across PCs?

  E0  controls: both kernels run clean with no breakpoints.
  E1  BAR.SYNC baseline: bp on a PRE-barrier instruction of warp 0;
      warp 1 blocks in its in-place BAR while warp 0 is parked;
      thunk-resume -> warp 0 reaches its own in-place BAR -> rendezvous.
  E2  BAR.SYNC cross-PC: bp ON warp 1's BAR instruction; warp 0 blocks
      in its in-place BAR; the thunk replays BAR.SYNC from the blob VA
      -> does the CTA barrier count arrivals regardless of PC?
  E3  WARPSYNC cross-PC: two WARPSYNC.ALL sites (then/else paths);
      bp on the then site; the else half blocks in-place; the thunk
      replays WARPSYNC.ALL from the blob VA -> mask-matched rendezvous
      across PCs, or deadlock (warpsync.md says "reach the same PC")?

Potentially-deadlocking experiments run in subprocesses (a wedged
context is reset by process exit).
"""

import os
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import CudaModule                       # noqa: E402
from sassdbg.patch import Debugger                      # noqa: E402

K_BAR = """\
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{0,1}:5:1]
    ISETP.LT.AND P0, PT, R2, 0x20, PT;[7:7:{5}:13:1]
    @P0 BRA #label(w0);[7:7:{}:5:1]
    BAR.SYNC 0;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
#def_label(w0)
    MOV32I R3, 0x11;[7:7:{}:5:1]
    BAR.SYNC 0;[7:7:{}:5:1]
#def_label(done)
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}], R2;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""

K_WS = """\
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{0,1}:5:1]
    LOP3.LUT R2, R2, 0x1F, RZ, 0xC0;[7:7:{5}:5:1]
    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{}:13:1]
    @P0 BRA #label(els);[7:7:{}:5:1]
    MOV32I R3, 0xA0;[7:7:{}:5:1]
    BRA #label(sync);[7:7:{}:5:1]
#def_label(els)
    MOV32I R3, 0xB0;[7:7:{}:5:1]
#def_label(sync)
    WARPSYNC.ALL;[7:7:{}:5:1]
    IMAD R3, R3, R2, RZ;[7:7:{}:5:1]
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}], R3;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""

# two WARPSYNC.ALL sites, one per divergent half — the NATIVE cross-PC
# question (no debugger involved): does hardware rendezvous them?
K_WS_2SITE = K_WS.replace("""    BRA #label(sync);[7:7:{}:5:1]
#def_label(els)
    MOV32I R3, 0xB0;[7:7:{}:5:1]
#def_label(sync)
    WARPSYNC.ALL;[7:7:{}:5:1]""", """    WARPSYNC.ALL;[7:7:{}:5:1]
    BRA #label(join);[7:7:{}:5:1]
#def_label(els)
    MOV32I R3, 0xB0;[7:7:{}:5:1]
    WARPSYNC.ALL;[7:7:{}:5:1]
#def_label(join)""")


def _mk(source, block):
    dbg = Debugger(source, max_warps=(block + 31) // 32)
    out = dbg.mod.devmem_alloc(0x100)
    dbg.mod.device_write(out, bytes(0x100))
    dbg.launch(args=[out], block=(block,))
    dbg.wait_base()
    return dbg, out


def _check_bar_out(dbg, out, tag):
    v = struct.unpack("<64I", dbg.mod.device_read(out, 0x100))
    assert list(v) == list(range(64)), (tag, v[:8])
    print(f"  {tag}: out[tid]==tid for all 64 threads  OK")


def _check_ws_out(dbg, out, tag):
    v = struct.unpack("<32I", dbg.mod.device_read(out, 0x80))
    want = [(0xB0 if lane < 16 else 0xA0) * lane for lane in range(32)]
    assert list(v) == want, (tag, v[:8])
    print(f"  {tag}: out[lane]==path*lane for all 32 lanes  OK")


def e0() -> None:
    dbg, out = _mk(K_BAR, 64)
    dbg.release()
    dbg.wait_done()
    _check_bar_out(dbg, out, "E0 BAR control")
    dbg, out = _mk(K_WS, 32)
    dbg.release()
    dbg.wait_done()
    _check_ws_out(dbg, out, "E0 WARPSYNC single-site control")


def e0b() -> None:
    """NATIVE cross-PC WARPSYNC: two WARPSYNC.ALL sites, one per
    divergent half, NO debugger.  Deadlock = WARPSYNC needs same PC."""
    dbg, out = _mk(K_WS_2SITE, 32)
    dbg.release()
    try:
        dbg.wait_done(timeout=8.0)
    except TimeoutError:
        print("  FINDING: two divergent halves at DIFFERENT WARPSYNC.ALL"
              " sites deadlock natively — WARPSYNC rendezvous requires"
              " the SAME PC (as warpsync.md states)", flush=True)
        os._exit(0)                      # wedged context; exit clean
    _check_ws_out(dbg, out, "E0b")
    print("  FINDING: WARPSYNC is PC-AGNOSTIC?!  (two-site kernel"
          " completed)")


def e1() -> None:
    """bp on warp0's PRE-barrier MOV; warp1 blocks in-place BAR."""
    dbg, out = _mk(K_BAR, 64)
    bp = dbg.arm(7)                      # MOV32I (warp0 pre-barrier)
    dbg.release()
    w, g = dbg.wait_group_hit()
    assert w == 0 and g.bp is bp and g.mask == 0xFFFFFFFF, (w, g.mask)
    time.sleep(0.5)
    assert not CudaModule.stream_query(dbg.stream), "kernel finished while w1 in BAR?!"
    print("  w0 parked pre-barrier, w1 blocked in in-place BAR"
          " (kernel alive)  OK")
    dbg.release_group(w, g, ["MOV32I R3, 0x11;[7:7:{}:5:1]"])
    dbg.wait_done()
    _check_bar_out(dbg, out, "E1")


def e2() -> None:
    """bp ON warp1's BAR; the thunk replays BAR.SYNC from the blob VA
    while warp0 is blocked in the in-place BAR (cross-PC arrival)."""
    dbg, out = _mk(K_BAR, 64)
    bp = dbg.arm(5)                      # BAR.SYNC (warp1 path)
    dbg.release()
    w, g = dbg.wait_group_hit()
    assert w == 1 and g.bp is bp, (w, g.mask)
    time.sleep(0.5)
    assert not CudaModule.stream_query(dbg.stream)
    print("  w1 parked ON its BAR site, w0 blocked in in-place BAR  OK")
    dbg.release_group(w, g, ["BAR.SYNC 0;[7:7:{}:5:1]"])
    try:
        dbg.wait_done(timeout=8.0)
    except TimeoutError:
        print("  FINDING: cross-PC BAR.SYNC does NOT rendezvous"
              " (kernel still blocked after 8s)", flush=True)
        os._exit(2)                      # context wedged; exit clean
    _check_bar_out(dbg, out, "E2")
    print("  FINDING: BAR.SYNC arrival is PC-AGNOSTIC — thunk-replayed"
          " BAR rendezvous with the in-place BAR  OK")


def e3() -> None:
    """bp ON the single WARPSYNC site; both divergent halves park there
    (merged group); one release drops them into ONE thunk holding
    WARPSYNC.ALL -> same-PC rendezvous in the blob."""
    dbg, out = _mk(K_WS, 32)
    bp = dbg.arm(9)                      # WARPSYNC.ALL (join site)
    dbg.release()
    w, g = dbg.wait_group_hit()
    assert g.bp is bp
    if g.mask != 0xFFFFFFFF:
        w2, g2 = dbg.wait_group_hit()
        assert g2 is g and g2.mask == 0xFFFFFFFF, hex(g2.mask)
    print("  both halves piled at the WARPSYNC site (merged)  OK")
    dbg.release_group(0, g, ["WARPSYNC.ALL;[7:7:{}:5:1]"])
    dbg.wait_done()
    _check_ws_out(dbg, out, "E3")
    print("  thunk WARPSYNC rendezvous (all lanes, one VA)  OK")


def e4() -> None:
    """SEQUENTIAL release (deterministic): a second bp on the else
    body's MOV pins the else half away from the barrier.  Release the
    then half into its thunk WARPSYNC — it must BLOCK (sibling not at
    any WARPSYNC); then let the sibling reach the site and release it
    into the SAME cached thunk VA -> rendezvous.  This is the stepper
    barrier-assist pattern for WARPSYNC."""
    dbg, out = _mk(K_WS, 32)
    bp_sync = dbg.arm(9)                 # WARPSYNC.ALL (join site)
    bp_else = dbg.arm(8)                 # else-body MOV32I
    dbg.release()
    g_sync = g_else = None
    while g_sync is None or g_else is None:
        w, g = dbg.wait_group_hit()
        if g.bp is bp_sync:
            g_sync = g
        elif g.bp is bp_else:
            g_else = g
    assert g_sync.mask == 0xFFFF0000 and g_else.mask == 0x0000FFFF, \
        (hex(g_sync.mask), hex(g_else.mask))
    dbg.release_group(0, g_sync, ["WARPSYNC.ALL;[7:7:{}:5:1]"])
    time.sleep(0.5)
    assert not CudaModule.stream_query(dbg.stream)
    print("  then half blocked in thunk WARPSYNC while else half"
          " parked away from the barrier  OK")
    dbg.resume(bp_else)                  # else runs MOV, hits bp@9
    w2, g2 = dbg.wait_group_hit()
    assert g2.bp is bp_sync and g2.mask == 0x0000FFFF, hex(g2.mask)
    dbg.release_group(0, g2, ["WARPSYNC.ALL;[7:7:{}:5:1]"])
    try:
        dbg.wait_done(timeout=8.0)
    except TimeoutError:
        print("  FINDING: sequential-release WARPSYNC does NOT"
              " rendezvous despite the shared thunk VA", flush=True)
        os._exit(2)
    _check_ws_out(dbg, out, "E4")
    print("  FINDING: sequential releases into the SAME thunk VA"
          " rendezvous (WARPSYNC same-PC via cache)  OK")


EXPERIMENTS = {"E0": e0, "E0b": e0b, "E1": e1, "E2": e2, "E3": e3,
               "E4": e4}

if __name__ == "__main__":
    if len(sys.argv) > 1:                # child: run one experiment
        EXPERIMENTS[sys.argv[1]]()
        sys.exit(0)
    for name in EXPERIMENTS:
        r = subprocess.run([sys.executable, __file__, name],
                           timeout=180)
        print(f"== {name}: {'OK' if r.returncode == 0 else 'FAIL'}")
        if r.returncode != 0:
            sys.exit(1)
    print("== probe_bar: ALL OK ==")
