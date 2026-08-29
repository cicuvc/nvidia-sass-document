"""sassdbg M8 E2E — divergence-aware breakpoints via resume thunks.

  T1  persistent bp inside a tight loop: arm ONCE, re-hit every
      iteration (the site stays patched; loop-buffer replay is a
      non-issue because nothing is ever restored), disarm at a parked
      boundary, correct result.
  T2  divergent if/else with a bp in EACH body: both divergent groups
      park SIMULTANEOUSLY at different sites (per-group hit slots
      keyed by leader lane = FLO(MACTIVE)), each released with its own
      thunk (per-lane RTGTV/RLGEN), correct per-lane results.
  T3  bp at a BSYNC: both groups pile up at the site (merged lane
      mask), ONE release drops them into the SAME cached thunk VA ->
      same-PC rendezvous, correct results.
  T4  group-aware stepping (Stepper.step_groups): a divergent if/else
      kernel stepped from entry to exit — the warp visibly SPLITS into
      two parked groups (one per body) and MERGES at the BSYNC via the
      stepper's barrier assist; exact path prefix + correct results.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.patch import Debugger                      # noqa: E402
from sassdbg.stepper import Stepper                     # noqa: E402

FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'FAIL'}  {name}" +
          ("" if ok else f": {got}  (want {want})"))
    if not ok:
        FAILS.append(name)


def mk(source, buf_sz=0x100):
    dbg = Debugger(source)
    out = dbg.mod.devmem_alloc(buf_sz)
    dbg.mod.device_write(out, bytes(buf_sz))
    dbg.launch(args=[out])
    dbg.wait_base()
    return dbg, out


K_LOOP = """\
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    MOV32I R2, 0x0;[7:7:{0,1}:5:1]
    MOV32I R3, 0x0;[7:7:{}:5:1]
#def_label(loop)
    IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]
    IADD3 R3, R3, 0x1, RZ;[7:7:{}:5:1]
    ISETP.LT.AND P0, PT, R3, 0xA, PT;[7:7:{}:13:1]
    @P0 BRA #label(loop);[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R4,R5}], R2;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""

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


def check_div_out(dbg, out, tag):
    v = struct.unpack("<32I", dbg.mod.device_read(out, 0x80))
    want = [(0xB0 if lane < 16 else 0xA0) * lane for lane in range(32)]
    check(f"{tag}: out[lane] == path*lane for all 32 lanes",
          list(v), want)


def t1():
    dbg, out = mk(K_LOOP)
    bp = dbg.arm(4)                     # loop-body IADD3 R2
    dbg.release()
    for _ in range(5):                  # bp armed ONCE, re-hit per iter
        w, g = dbg.wait_group_hit()
        assert g.bp is bp and w == 0
        dbg.release_group(w, g, ["IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]"])
    w, g = dbg.wait_group_hit()         # 6th hit: parked again
    check("T1: 6 hits from a single arming inside a tight loop",
          g.bp is bp, True)
    dbg.disarm(bp)                      # safe: the warp is parked
    dbg.release_group(0, g, ["IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]"])
    dbg.wait_done()
    v = struct.unpack("<I", dbg.mod.device_read(out, 4))[0]
    check("T1: result 10*7", v, 70)


def t2_divergent_two_sites():
    dbg, out = mk(K_DIV)
    bp_then = dbg.arm(7)                # MOV32I 0xA0 (fall-through body)
    bp_else = dbg.arm(9)                # MOV32I 0xB0 (else body)
    dbg.release()
    w1, g1 = dbg.wait_group_hit()
    w2, g2 = dbg.wait_group_hit()
    check("T2: two groups parked at different sites",
          (w1, w2, {g1.bp, g2.bp}), (0, 0, {bp_then, bp_else}))
    check("T2: disjoint lane masks covering the warp",
          (g1.mask & g2.mask, g1.mask | g2.mask), (0, 0xFFFFFFFF))
    for g in (g1, g2):
        insts = (["MOV32I R3, 0xB0;[7:7:{}:5:1]"] if g.bp is bp_else
                 else ["MOV32I R3, 0xA0;[7:7:{}:5:1]"])
        dbg.release_group(0, g, insts)
    dbg.wait_done()
    check_div_out(dbg, out, "T2")


def t3_bsync_shared_thunk():
    dbg, out = mk(K_DIV)
    bp = dbg.arm(10)                    # BSYNC
    dbg.release()
    w, g = dbg.wait_group_hit()
    assert g.bp is bp
    if g.mask != 0xFFFFFFFF:
        # the second group was still in flight at the first poll; its
        # arrival merges into the same parked group (seq bump)
        w2, g2 = dbg.wait_group_hit()
        check("T3: pile-up merges into one parked group at BSYNC",
              (w2, g2 is g, g2.mask), (0, True, 0xFFFFFFFF))
    else:
        check("T3: pile-up merged before the first poll",
              g.mask, 0xFFFFFFFF)
    dbg.release_group(0, g, ["BSYNC B0;[7:7:{}:4:0]"])
    dbg.wait_done()
    check_div_out(dbg, out, "T3")


def t4_group_stepping():
    st = Stepper(K_DIV)
    out = st.dbg.mod.devmem_alloc(0x100)
    st.dbg.mod.device_write(out, bytes(0x100))
    st.launch(args=[out])
    bp = st.run_to_entry()
    check("T4: parked at entry", bp.orig_index, 0)
    groups = st._parked
    saw_split = False
    steps = 0
    while groups:
        groups = st.step_groups(groups)
        if sum(1 for w, _ in groups if w == 0) > 1:
            saw_split = True
        steps += 1
        assert steps < 100, "step budget"
    st.dbg.wait_done()
    check("T4: warp visibly split into two parked groups",
          saw_split, True)
    p = st.paths[0]
    check("T4: path prefix 0..6", p[:7], [0, 1, 2, 3, 4, 5, 6])
    check("T4: both branch bodies executed",
          (7 in p, 9 in p), (True, True))
    # after the split the two groups run one step apart (a lone group
    # passes its thunk BSYNC before the sibling arrives — a legal
    # schedule), so assert coverage + termination rather than an exact
    # tail order
    check("T4: every instruction 0..14 stepped",
          set(p) == set(range(15)), True)
    check("T4: path ends at EXIT", p[-1], 14)
    check_div_out(st.dbg, out, "T4")


t1()
t2_divergent_two_sites()
t3_bsync_shared_thunk()
t4_group_stepping()

if FAILS:
    print(f"=== FAILURES: {FAILS} ===")
    sys.exit(1)
print("=== sassdbg M8 divergence-aware breakpoints: ALL PASS ===")
