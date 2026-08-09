import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# SM subcore mapping (warp i -> subcore i%4) and yield-hint scheduler switch
# (SM120, RTX 5090 / GB202)
#
# Claims under test:
#   (a) each SM has 4 subcores (SMSPs); CTA warp i runs on subcore i%4.
#   (b) the "yield" hint (bracket yield=1 -> usched bit4=0, WnEG) tells the
#       subcore's scheduler to switch to another warp next cycle; yield=0
#       (transN, bit4=1) means "keep issuing this warp".
#
# Method: two active warps (block=256 -> warps 0..7, others EXIT), each on its
# OWN branch with a DIFFERENT yield bit on N independent NOPs:
#   warp A: yield=1 (WnEG)   warp B: yield=0 (transN)
# Each records CS2R start/end and stores its delta to out[warp*16].
#
# If A,B share a subcore (i%4) AND yield steers the scheduler, the transN warp
# hogs the issue slot while the WnEG warp yields -> A.delta >> B.delta
# (asymmetry ~2x).  If they are on different subcores there is no interaction.
#
# Measured (5 reps, best-of, sm_120):
#   warps   subcores      A(WnEG) B(transN)  asym A/B
#   {0,1}   0,1 diff        1100    1042      1.06   (no interaction)
#   {0,4}   0,0 SAME        1415     732      1.93   (yield switch!)
#   {1,5}   1,1 SAME        1374     685      2.01
#   {2,6}   2,2 SAME        1415     732      1.93
#   {0,5}   0,1 diff        1100    1042      1.06
#   {0,7}   0,3 diff        1100    1042      1.06
# Flipping the yields on {0,4} reverses the asymmetry (0.61); both-yield-same
# is symmetric (~0.99).  Only i%4 pairs interact -> BOTH claims verified.
#
# Notes on the SASS recipes used:
#   * the ISETP feeding a guarded BRA needs stall=13 so the predicate writeback
#     settles before the BRA reads it (see tests/asm_construct/test_break.py).
#   * warp selection via S2R SR_TID.X -> SHR (tid>>5) -> ISETP.EQ -> @P0 BRA;
#     non-target warps fall through to EXIT.
#   * host-side warp stride is 16 BYTES = 4 words (the classic stride bug).
# See notes/sm90/arch/subcore_scheduler.md.
# ---------------------------------------------------------------------------

WARP_STRIDE_WORDS = 4        # out[warp*16 bytes] = words[warp*4]

def build_kernel(targets, yieldA, yieldB, N):
    lines = ["#fn sc(out<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[1:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    SHR R3, R2, 0x5;[7:7:{0}:5:1]",
             "    MOV R9, R3;[7:7:{}:5:1]"]
    for w, lbl in [(targets[0], "workA"), (targets[1], "workB")]:
        lines.append(f"    ISETP.EQ.AND P0, PT, R3, 0x{w}, PT;[7:7:{{}}:13:1]")
        lines.append(f"    @P0 BRA #label({lbl});[7:7:{{}}:5:1]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    for lbl, y in [("workA", yieldA), ("workB", yieldB)]:
        lines.append(f"    #def_label({lbl})")
        lines.append("    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]")
        lines.append("    NOP;[7:7:{}:5:0]")
        for _ in range(N):
            lines.append(f"    NOP;[7:7:{{}}:1:{y}]")
        lines.append("    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]")
        lines.append("    NOP;[7:7:{}:5:0]")
        lines.append("    SHL R9, R9, 0x4;[7:7:{}:5:1]")
        lines.append("    IADD3 R4, R6, R9, RZ;[7:7:{1}:5:1]")
        lines.append("    IADD3 R5, R7, RZ, RZ;[7:7:{1}:5:1]")
        for off, src in ((0x0, "R30"), (0x4, "R31"), (0x8, "R26"), (0xC, "R27")):
            lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R4,R5}}+0x{off:x}], {src};[0:1:{{0}}:1:0]")
        lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(targets, yA, yB, N=400):
    reset_context()
    cubin = assemble(build_kernel(targets, yA, yB, N), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(4096)
    mod.device_write(d, bytes(4096))
    mod.launch("sc", grid=(1,), block=(256,), args=[d])
    mod.synchronize()
    words = struct.unpack("<256I", mod.device_read(d, 1024))
    mod.devmem_free(d)
    out = {}
    for w in targets:
        a = words[w * WARP_STRIDE_WORDS: w * WARP_STRIDE_WORDS + 4]
        s = (a[1] << 32) | a[0]
        e = (a[3] << 32) | a[2]
        out[w] = (e - s) & ((1 << 64) - 1)
    return out


def measure(targets, yA, yB, N=400, reps=5):
    best = None
    for _ in range(reps):
        r = run(targets, yA, yB, N)
        if best is None:
            best = dict(r)
            continue
        for w in targets:
            best[w] = min(best[w], r[w])
    assert best is not None
    return best


try:
    measure([0, 4], 1, 0)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

N = 400
print("subcore mapping + yield-hint scheduler switch (SM120)")
print("  A=warp0 yield=1(WnEG)  B=warp1 yield=0(transN), N=%d NOPs" % N)
print(f"  {'warps':<8} {'A(delta)':>8} {'B(delta)':>8} {'asym':>6}  interaction")
rows = []
ok = True
pairs = [([0, 1], False), ([0, 4], True), ([1, 5], True), ([2, 6], True),
         ([3, 7], True), ([0, 5], False), ([0, 7], False), ([0, 3], False)]
for targets, expect_share in pairs:
    r = measure(targets, 1, 0, N)
    dA, dB = r[targets[0]], r[targets[1]]
    asym = dA / dB
    rows.append((targets, dA, dB, asym, expect_share))
    tag = "SHARE" if asym > 1.4 else "none "
    print(f"  {{{targets[0]},{targets[1]}}}    {dA:8d} {dB:8d} {asym:6.2f}  {tag}")

share = [r for r in rows if r[4]]
none = [r for r in rows if not r[4]]
min_share = min(r[3] for r in share)
max_none = max(r[3] for r in none)
print(f"\n  min asym on i%4 pairs = {min_share:.2f}; max asym on diff pairs = {max_none:.2f}")

# flip control: {0,4} with yields swapped must reverse the asymmetry
r = measure([0, 4], 0, 1, N)
flip_asym = r[0] / r[4]
print(f"  flip {0,4} A=transN B=WnEG: asym A/B = {flip_asym:.2f} (expect < 1)")

# same-yield controls: {0,4} both WnEG / both transN -> symmetric
r = measure([0, 4], 1, 1, N)
same_wn = r[0] / r[4]
r = measure([0, 4], 0, 0, N)
same_tn = r[0] / r[4]
print(f"  {0,4} both WnEG: asym = {same_wn:.2f}; both transN: asym = {same_tn:.2f}")

# --- assertions (methodology-robust) ----------------------------------------
if not (min_share > 1.4 and max_none < 1.35):
    ok = False
    print("FAIL: i%4 pairs must show >1.4x asymmetry; non-i%4 pairs <1.35x")
if not (flip_asym < 0.75 and flip_asym > 0.0):
    ok = False
    print("FAIL: flipping the yield bits must reverse the asymmetry (<0.75)")
if not (0.8 < same_wn < 1.25 and 0.8 < same_tn < 1.25):
    ok = False
    print("FAIL: same-yield pairs on a shared subcore must be symmetric")
if not all(d > 0 for _, dA, dB, _, _ in rows for d in (dA, dB)):
    ok = False
    print("FAIL: per-warp CS2R deltas must be non-zero")

print("\n=== subcore i%4 mapping + yield-switch: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
