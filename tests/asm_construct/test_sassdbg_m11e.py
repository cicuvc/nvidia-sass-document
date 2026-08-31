"""M11e GPU E2E: group masks, dual park modes, and private stepping."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.private import PrivateKernel                     # noqa: E402
from sassdbg.stepper import Stepper                            # noqa: E402


SRC = """#fn k(out<8>) {
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{1}:5:1]
    LOP3.LUT R2, R2, 0x1F, RZ, 0xC0;[7:7:{5}:5:1]
    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{}:13:1]
    @P0 BRA #label(lower);[7:7:{}:6:0]
    MOV32I R3, 0xA0;[7:7:{}:5:1]
    BRA #label(join);[7:7:{}:6:0]
#def_label(lower)
    MOV32I R3, 0xB0;[7:7:{}:5:1]
#def_label(join)
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{}:5:1]
    STG.E.STRONG.GPU [{R6,R7}], R3;[7:7:{}:8:0]
    EXIT;[7:7:{}:5:0]
}
"""

FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'FAIL'} {name}" +
          ("" if ok else f": {got!r} want {want!r}"))
    if not ok:
        FAILS.append(name)


def output(k, out):
    return struct.unpack("<32I", k.mod.device_read(out, 128))


def want_output():
    return tuple([0xB0] * 16 + [0xA0] * 16)


try:
    probe = PrivateKernel.from_source(SRC, max_warps=1, max_bps=8)
except RuntimeError as e:
    if "CUDA_ERROR_NO_DEVICE" in str(e):
        print("SKIP M11e GPU E2E: no CUDA device visible")
        sys.exit(0)
    raise

# T0: the upper-half body reaches instruction 5, but its MACTIVE has no
# intersection with this lower-half stop mask.  It must replay transparently.
out = probe.mod.devmem_alloc(128)
probe.mod.device_write(out, bytes(128))
probe.arm(5, warps=[0], lane_masks=0x0000FFFF)
probe.launch([out])
probe.wait_ready()
probe.release()
probe.wait_done()
check("T0 transparent replay ignores a nonmatching execution group",
      output(probe, out), want_output())

# T1: different divergent groups report different sites only after the host
# explicitly enters cooperative collection; freeze is reacquired before code
# restoration, then one data-only release resumes both groups.
k = PrivateKernel.from_source(SRC, max_warps=1, max_bps=8)
out = k.mod.devmem_alloc(128)
k.mod.device_write(out, bytes(128))
bpa = k.arm(5, warps=[0], lane_masks=0xFFFF0000)
bpb = k.arm(7, warps=[0], lane_masks=0x0000FFFF)
k.launch([out])
k.wait_ready()
k.release()
h0 = k.wait_hit()
k.cooperate(0)
h1 = k.wait_hit()
check("T1 cooperative mode collects two disjoint sibling groups",
      ({h0.bp.orig_index, h1.bp.orig_index}, h0.mask & h1.mask,
       h0.mask | h1.mask), ({5, 7}, 0, 0xFFFFFFFF))
k.freeze(0)
k.disarm(bpa, warps=[0])
k.disarm(bpb, warps=[0])
k.resume_hit(h0)
k.wait_done()
check("T1 both site-specific replay epilogues resume correctly",
      output(k, out), want_output())

# T2: Stepper uses per-warp successor masks.  At the predicated branch, the
# two possible successors are armed only for the source group's mask; sibling
# groups cannot be captured merely because a site belongs to a global union.
pk = PrivateKernel.from_source(SRC, max_warps=1, max_bps=8)
st = Stepper(SRC, dbg=pk)
out = pk.mod.devmem_alloc(128)
pk.mod.device_write(out, bytes(128))
st.launch([out])
st.run_to_entry()
groups = st._parked
saw_split = False
steps = 0
while groups:
    groups = st.step_groups(groups)
    saw_split |= len(groups) == 2
    steps += 1
    assert steps < 40
pk.wait_done()
check("T2 private stepper observes the divergent split", saw_split, True)
check("T2 private stepper covers both bodies", (5 in st.paths[0],
                                                  7 in st.paths[0]),
      (True, True))
check("T2 stepped output", output(pk, out), want_output())

# T3: the same private stepping protocol carries both halves to a common
# BSYNC site before releasing either one.  Their immutable replay thunk is
# shared by (warp,index), preserving the same-PC rendezvous property.
SYNC = SRC.replace(
    "    @P0 BRA #label(lower);[7:7:{}:6:0]\n",
    "    BSSY B0, #label(after);[7:7:{}:5:1]\n"
    "    @P0 BRA #label(lower);[7:7:{}:6:0]\n").replace(
    "BRA #label(join)", "BRA #label(sync)").replace(
    "#def_label(join)\n    IMAD.WIDE",
    "#def_label(sync)\n    BSYNC B0;[7:7:{}:4:0]\n"
    "#def_label(after)\n    IMAD.WIDE")
# Direct control: a pre-gate private patch at BSYNC must be reached before
# diagnosing the stepper's boundary migration.
direct = PrivateKernel.from_source(SYNC, max_warps=1, max_bps=16)
dout = direct.mod.devmem_alloc(128)
direct.mod.device_write(dout, bytes(128))
direct.arm(9, warps=[0])
direct.launch([dout])
direct.wait_ready()
direct.release()
dh = direct.wait_hit()
check("T3 direct BSYNC breakpoint is reachable", dh.bp.orig_index, 9)
direct.disarm(dh.bp, warps=[0])
direct.resume_hit(dh)
direct.wait_done()
pk = PrivateKernel.from_source(SYNC, max_warps=1, max_bps=16)
st = Stepper(SYNC, dbg=pk)
out = pk.mod.devmem_alloc(128)
pk.mod.device_write(out, bytes(128))
st.launch([out])
st.run_to_entry()
groups = st._parked
steps = 0
while groups:
    groups = st.step_groups(groups)
    steps += 1
    assert steps < 50
pk.wait_done()
check("T3 BSYNC private replay reconverges", output(pk, out), want_output())

# T4: WARPSYNC has the same same-PC requirement, but no BSSY token.  Both
# divergent groups are collected at the one logical site and replay its one
# per-warp immutable thunk together.
WSYNC = SRC.replace(
    "#def_label(join)\n    IMAD.WIDE",
    "#def_label(join)\n    WARPSYNC.ALL;[7:7:{}:5:1]\n    IMAD.WIDE")
pk = PrivateKernel.from_source(WSYNC, max_warps=1, max_bps=16)
st = Stepper(WSYNC, dbg=pk)
out = pk.mod.devmem_alloc(128)
pk.mod.device_write(out, bytes(128))
st.launch([out])
st.run_to_entry()
groups = st._parked
steps = 0
while groups:
    groups = st.step_groups(groups)
    steps += 1
    assert steps < 50
pk.wait_done()
check("T4 WARPSYNC private replay reconverges", output(pk, out),
      want_output())

# T5: BAR.SYNC rendezvous is CTA-wide and PC-agnostic.  The two private warps
# reach distinct logical BAR sites; barrier assist releases the second arrival
# while the first is blocked in its immutable replay thunk.
BAR = """#fn k(out<8>) {
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{1}:5:1]
    ISETP.LT.AND P0, PT, R2, 0x20, PT;[7:7:{5}:13:1]
    @P0 BRA #label(w0);[7:7:{}:6:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:6:0]
#def_label(w0)
    MOV32I R3, 0x11;[7:7:{}:5:1]
    BAR.SYNC 0;[7:7:{}:5:1]
#def_label(done)
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{}:5:1]
    STG.E.STRONG.GPU [{R6,R7}], R2;[7:7:{}:8:0]
    EXIT;[7:7:{}:5:0]
}
"""
pk = PrivateKernel.from_source(BAR, max_warps=2, max_bps=16)
st = Stepper(BAR, dbg=pk)
out = pk.mod.devmem_alloc(256)
pk.mod.device_write(out, bytes(256))
st.launch([out], block=(64,))
st.run_to_entry_all()
groups = st._parked
steps = 0
while groups:
    groups = st.step_groups(groups)
    steps += 1
    assert steps < 50
pk.wait_done()
check("T5 CTA BAR replay rendezvous",
      struct.unpack("<64I", pk.mod.device_read(out, 256)), tuple(range(64)))

if FAILS:
    print("=== M11e FAILURES:", ", ".join(FAILS), "===")
    sys.exit(1)
print("=== sassdbg M11e group-aware stepping: ALL PASS ===")
