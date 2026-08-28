"""M4 — warp-level trace decode + forward/backward state replay.

Builds a divergent if/else kernel (tid<16 -> +100, else +200) with a
BSSY/BSYNC region, traces it with sassdbg.wtrace, then:

  1. replays the trace forward and checks the reconstructed final state
     against the device memory ground truth (per-lane GPRs, sparse mem,
     predicates, URs)
  2. walks the state BACKWARD one step at a time (undo from REG/PRED
     history + MEMOLD old-bytes) and verifies the register/memory values
     at earlier points — including that the two divergent IADD3 paths
     undo into the LDG-loaded values and that the reverse PC chain is
     the STEP stream walked backwards
  3. checks partial forward replay (replay(n_frames=k)) agrees with
     full-replay-then-step-back at the same point

Divergence handling: each STEP record carries its group's MACTIVE mask
(BMOV), so divergent groups appear as separate steps in issue order —
the predecessor of a branch target is simply the previous STEP.
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule              # noqa: E402
from sassdbg.wtrace import instrument_warp, REGION_BYTES  # noqa: E402
from sassdbg.reverse import WarpReplay, KIND_STEP        # noqa: E402

ok = True


def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got!r}")


# tid<16: b[t] = a[t] + 0x64 ; else: b[t] = a[t] + 0xC8
KERNEL = """\
#fn div4(a<8>, b<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(a);[1:7:{}:1:0]
    LDC.64 {R6,R7}, #param(b);[2:7:{}:1:0]
    S2R R2, SR_TID.X;[0:7:{}:5:1]
    IMAD.WIDE.U32 {R8,R9}, R2, 0x4, {R4,R5};[7:7:{0,1}:5:1]
    IMAD.WIDE.U32 {R10,R11}, R2, 0x4, {R6,R7};[7:7:{0,2}:5:1]
    LDG.E R12, desc[{UR4,UR5}][{R8,R9}];[3:7:{}:1:0]
    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{0,3}:13:1]
    BSSY B0, #label(join);[7:7:{}:5:1]
    @P0 BRA #label(tpath);[7:7:{}:5:1]
    IADD3 R12, R12, 0xC8, RZ;[7:7:{}:5:1]
    BRA #label(join);[7:7:{}:5:1]
    #def_label(tpath)
    IADD3 R12, R12, 0x64, RZ;[7:7:{}:5:1]
    BSYNC B0;[7:7:{}:5:1]
    #def_label(join)
    STG.E desc[{UR4,UR5}][{R10,R11}], R12;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""

A = [0x1000 + 7 * t for t in range(32)]
SENT = 0xDEADBEEF


def expected(t):
    return (A[t] + (0x64 if t < 16 else 0xC8)) & 0xFFFFFFFF


ik = instrument_warp(KERNEL)
mod = CudaModule(assemble(ik.source, check_deps=False))
a_dev = mod.devmem_alloc(256)
b_dev = mod.devmem_alloc(256)
trace = mod.devmem_alloc(REGION_BYTES)
mod.device_write(a_dev, struct.pack("<32I", *A))
mod.device_write(b_dev, struct.pack("<32I", *([SENT] * 32)))
mod.device_write(trace, bytes(REGION_BYTES))
mod.launch("div4", grid=(1,), block=(32,), args=[a_dev, b_dev, trace])
mod.synchronize()

# ---- 0. ground truth -------------------------------------------------------
bvals = struct.unpack("<32I", mod.device_read(b_dev, 128))
check("kernel result b[tid]", bvals, tuple(expected(t) for t in range(32)))

raw_trace = mod.device_read(trace, REGION_BYTES)
sidecar = ik.sidecar()
steps = json.loads(sidecar)["steps"]


def find_step(mnem_part, nth=0):
    hits = [i for i, s in enumerate(steps) if mnem_part in s["text"]]
    return hits[nth] if hits else -1


idx_ldg = find_step("LDG")
idx_else = find_step("IADD3 R12, R12, 0xC8")
idx_then = find_step("IADD3 R12, R12, 0x64")
idx_stg = find_step("STG.E desc")
idx_isetp = find_step("ISETP")
assert -1 not in (idx_ldg, idx_else, idx_then, idx_stg, idx_isetp), \
    (idx_ldg, idx_else, idx_then, idx_stg, idx_isetp)

# ---- 1. forward replay -----------------------------------------------------
rp = WarpReplay(sidecar, bytes(raw_trace), warp=0)
st = rp.replay()

check("final R12 per lane", tuple(st.reg(t, 12) for t in range(32)),
      tuple(expected(t) for t in range(32)))
b_base = b_dev  # device VA recorded in MEM records is the same VA
check("final sparse mem b[tid]",
      tuple(st.mem32(b_base + 4 * t) for t in range(32)),
      tuple(expected(t) for t in range(32)))
check("final mask (last group of the reconverged tail)",
      st.mask in (0x0000FFFF, 0xFFFF0000, 0xFFFFFFFF), True)
check("final pc == EXIT step", st.pc, len(steps) - 1)

# predicates after ISETP: P0 (bit0) set exactly for tid<16
st_i = rp.replay()
while st_i.pc != idx_isetp and rp.step_back(st_i):
    pass
pr_at_isetp = tuple(st_i.pr[t] & 1 for t in range(32))
check("P0 after ISETP (tid<16)", pr_at_isetp,
      tuple(1 if t < 16 else 0 for t in range(32)))

# ---- 2. divergence visible in the STEP stream ------------------------------
chain = [(fr[0].idx, fr[0].mask) for fr in rp.frames
         if fr and fr[0].kind == KIND_STEP]
masks = [m for _i, m in chain]
check("pc chain has both branch bodies",
      (idx_then in [i for i, _ in chain], idx_else in [i for i, _ in chain]),
      (True, True))
check("distinct group masks (divergence)", len(set(masks)) > 1, True)
# the taken-path group must carry exactly the low-16 mask on its add
then_masks = [m for i, m in chain if i == idx_then]
else_masks = [m for i, m in chain if i == idx_else]
check("then-path mask", then_masks, [0x0000FFFF])
check("else-path mask", else_masks, [0xFFFF0000])
# issue order: else group issued before the taken group (fall-through first)
pos_else = next(k for k, (i, _m) in enumerate(chain) if i == idx_else)
pos_then = next(k for k, (i, _m) in enumerate(chain) if i == idx_then)
check("issue order else<then", pos_else < pos_then, True)

# URs: default cdesc is genuinely 0/0 on sm_120 (verified by readback kernel)
check("UR4/UR5 recorded", (st.urs.get(4), st.urs.get(5)), (0, 0))

# ---- 3. backward stepping ----------------------------------------------------
st = rp.replay()
total_frames = len(rp.frames)

# undo back to the LDG step: both IADD3 paths and both groups' join
# STG/EXIT steps undo (each divergent group owns disjoint lanes)
n_back = 0
while st.pc != idx_ldg:
    assert rp.step_back(st), "ran out of frames before LDG"
    n_back += 1
check("steps back to LDG (3 shared + 2x4 divergent frames)", n_back, 11)
check("R12 at LDG == a[tid]", tuple(st.reg(t, 12) for t in range(32)),
      tuple(A))
check("mem restored to sentinel at LDG",
      tuple(st.mem32(b_base + 4 * t) for t in range(32)),
      tuple([SENT] * 32))

# undo to the very start: register/predicate state is gone; memory holds
# the host-written sentinel again (undoing a store restores its OLD value,
# which for the first traced write is exactly the pre-kernel content)
while rp.step_back(st):
    pass
check("start: pc", st.pc, -1)
check("start: no regs", all(not st.regs[t] for t in range(32)), True)
sent_bytes = struct.pack("<32I", *([SENT] * 32))
check("start: mem == pre-kernel sentinel image",
      bytes(st.mem.get(b_base + i, 0) for i in range(128)), sent_bytes)
check("start: no other mem", len(st.mem), 128)
check("start: no urs", st.urs, {})
check("frames fully consumed", len(st._undo), 0)

# ---- 4. partial forward replay == full replay + step back ------------------
# find the frame index of the LDG step
ldg_frame = next(k for k, fr in enumerate(rp.frames)
                 if fr and fr[0].kind == KIND_STEP and fr[0].idx == idx_ldg)
st_fwd = rp.replay(n_frames=ldg_frame + 1)
check("partial replay R12", tuple(st_fwd.reg(t, 12) for t in range(32)),
      tuple(A))
check("partial replay pc", st_fwd.pc, idx_ldg)
st2 = rp.replay()
for _ in range(total_frames - (ldg_frame + 1)):
    rp.step_back(st2)
check("step-back == partial replay (R12)",
      tuple(st2.reg(t, 12) for t in range(32)),
      tuple(st_fwd.reg(t, 12) for t in range(32)))
check("step-back == partial replay (pc)", st2.pc, st_fwd.pc)
check("step-back == partial replay (mask)", st2.mask, st_fwd.mask)

mod.devmem_free(a_dev)
mod.devmem_free(b_dev)
mod.devmem_free(trace)

print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
