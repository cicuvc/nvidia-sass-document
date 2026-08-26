import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from archutil import adapt_source  # noqa: E402
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# udp_pipe -> int_pipe fixed-latency forwarding calibration (SM120, RTX 5090)
#
# Question: a udp_pipe producer writes a uniform register and an int_pipe
# consumer reads it (MOV R,UR / IADD3 R,..,UR).  The sm120 UGPR TABLE_TRUE
# says L_table = 12 cycles (UDP_subset -> MOV_OP / MATH_OPS).  How much stall
# is actually required on silicon?
#
# Method: stale/fresh boundary sweep (the usched_latency poison technique).
# Per instance: LDCU poisons UR10 (wr=SB0) -> producer UIADD3/UMOV UR10,..
# with req={0} (poison writeback settled; no WAW race) and stall=1 -> S-1 NOP
# fillers (stall=1 each) -> consumer reads UR10 -> generous pad -> STG.
#   S = total stall value between producer and consumer.
# The consumer is protected only by the gap: at small S it reads the poison
# (stale); at sufficient S it reads the producer's TRUE value (fresh).
#
# Measured (3-5 deterministic reps, sm_120 / GB202):
#   UIADD3 -> MOV        : minG stall = 3  (~3.4 cyc)   spec L = 12
#   UIADD3 -> IADD3.RUR  : minG stall = 3  (~3.4 cyc)   spec L = 12
#   UIADD3 -> UIADD3     : minG stall = 2  (~2.4 cyc)   spec L = 4   (same-pipe)
#   UMOV   -> MOV        : minG stall = 1  (~1.4 cyc)   spec L = 5
#
# Conclusions:
#   * udp->int forwarding is REAL but NOT free: reading within ~2 cycles of
#     the producer's issue reads stale (poison).  The hazard L_table warns
#     about genuinely exists at tiny gaps (the user's premise).
#   * The required stall (~3 cycles) is ~4x SMALLER than L_table (12): the
#     uniform datapath forwards to the int pipe's UR operand collector, so
#     the tabulated 12 is a conservative upper bound (overlap L-minG = 9).
#   * Producer-dependent: UIADD3 (uniform ALU) minG=3, UMOV (copy) minG=1;
#     the slow producers (R2UR cross-lane ~40cyc settle, LDCU const-load,
#     variable) need far more - see notes/sm90/arch/pipe_forwarding.md.
#
# Method gotchas baked in below:
#   * stall=0 is DRAIN, not "zero gap": it forces a ~34-cycle pipeline drain,
#     so the producer carries stall=1 and all extra gap comes from NOPs.
#   * The single-warp issue floor is ~2.5-3 cyc, so minG is only resolvable
#     down to ~2.4 cyc (stall=2).
#   * The poison LDCU must be settled by the producer's req={0} (wr=SB0),
#     else the poison writeback can land AFTER the producer (WAW) and fake a
#     stale result at every gap.
#
# Yield-bit probe (bottom half): sweeps the same boundary with the bracket
# yield bit set both ways.  yield=1 (usched bit4=0, WnEG) -> minG=3; yield=0
# (usched bit4=1, transN) -> minG=6 on all-transN fill.  The issue gap is
# identical (CS2R-timed), only the hazard window widens.  See
# notes/sm90/arch/pipe_forwarding.md "Yield bit".
# ---------------------------------------------------------------------------

POISON = 0xAAAAAAAA
TRUE   = 0x12345678
# index 0 = poison-only control (stall 0), 1..16 = sweep, last = huge-gap control
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)          # indices of the actual stall sweep

# spec sm120 UGPR TABLE_TRUE cells (sm120_latencies.txt)
SPEC_L = {("UIADD3", "MOV"): 12, ("UIADD3", "IADD3"): 12,
          ("UIADD3", "UIADD3"): 4, ("UMOV", "MOV"): 5}

PROD = {
    "UIADD3": "UIADD3 UR10, UPT, UPT, UR11, UR12, URZ",
    "UMOV":   "UMOV UR10, UR11",
}
CONS = {
    "MOV":    ("MOV R20, UR10", False),
    "IADD3":  ("IADD3 R20, PT, PT, RZ, UR10, RZ", False),
    "UIADD3": ("UIADD3 UR20, UPT, UPT, UR10, URZ, URZ", True),  # needs UR->R tail
}


def build_kernel(prod, cons, stalls, prod_y=1, filler_y=1):
    """prod_y / filler_y = bracket yield bit on the producer / NOP fillers
    (yield=1 -> usched=stall, WnEG;  yield=0 -> usched=16+stall, transN;
    eff_stall identical either way)."""
    cons_text, needs_tail = CONS[cons]
    lines = ["#fn fwd(out<8>, poison<4>, a<4>, b<4>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    LDCU UR11, #param(a);[0:7:{}:2:0]",
             "    LDCU UR12, #param(b);[0:7:{}:2:0]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        if S == 0:                      # poison-only control
            lines.append("    LDCU UR10, #param(poison);[0:7:{}:2:0]")
            lines += ["    NOP;[7:7:{}:7:1]"] * 6
            # first read of a freshly-LDCU-loaded UR is stale (old value) and
            # the LDCU writeback only commits once a consumer req's it; the
            # dummy read (req={0}) settles both, then the real read captures it.
            lines.append("    MOV RZ, UR10;[7:7:{0}:5:1]")
            lines.append("    MOV R20, UR10;[7:7:{}:5:1]")
        else:
            lines.append("    LDCU UR10, #param(poison);[0:7:{}:2:0]")
            lines.append(f"    {PROD[prod]};[7:7:{{0}}:1:{prod_y}]")
            for _ in range(S - 1):
                lines.append(f"    NOP;[7:7:{{}}:1:{filler_y}]")
            lines.append(f"    {cons_text};[7:7:{{}}:5:1]")
            if needs_tail:
                lines += ["    NOP;[7:7:{}:5:1]"] * 8
                lines.append("    MOV R20, UR20;[7:7:{}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 8
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(prod, cons, stalls, prod_y=1, filler_y=1):
    reset_context()
    cubin = assemble(adapt_source(build_kernel(prod, cons, stalls, prod_y, filler_y)),
                     check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("fwd", grid=(1,), block=(1,),
               args=[d, POISON, 0x12345678, 0])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == TRUE else ("S" if v == POISON else "?")


try:
    run("UIADD3", "MOV", [8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("udp->int forwarding calibration (SM120);  poison=0x%08X true=0x%08X"
      % (POISON, TRUE))
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

ok = True
for prod, cons in [("UIADD3", "MOV"), ("UIADD3", "IADD3"),
                   ("UIADD3", "UIADD3"), ("UMOV", "MOV")]:
    reps = [run(prod, cons, STALLS) for _ in range(3)]
    maj = "".join("F" if sum(1 for r in reps if r[i] == TRUE) >= 2
                  else ("S" if sum(1 for r in reps if r[i] == POISON) >= 2
                        else "?")
                  for i in range(len(STALLS)))
    det = all(r == reps[0] for r in reps)
    lspec = SPEC_L[(prod, cons)]
    sweep = maj[SWEEP]
    minG = None
    for j in range(len(sweep)):
        if all(c == "F" for c in sweep[j:]):
            minG = STALLS[SWEEP][j]
            break
    print(f"{prod:6s}->{cons:7s} Lspec={lspec:2d} "
          f"[{'det' if det else 'var'}]: {sweep}")
    if minG is not None:
        print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
              f"overlap Lspec-minG={lspec - minG}")

    good = True
    # poison-only control (index 0) must read poison; huge-gap (last) must be fresh
    if maj[0] != "S":
        good = False
        print("        FAIL: poison-only control should read poison")
    if maj[-1] != "F":
        good = False
        print("        FAIL: huge-gap control (stall 30) should be fresh")
    # hazard is real for the ALU producers: reads at stall 1 are stale
    if minG is None or minG < 1 or minG > 16:
        good = False
        print("        FAIL: could not resolve minG in the sweep range")
    if prod == "UIADD3" and (minG is None or minG < 2):
        good = False
        print("        FAIL: UIADD3 producers must show stale reads at stall 1")
    # spec L_table must be conservative (hardware needs less)
    if minG is None or minG >= lspec:
        good = False
        print(f"        FAIL: expected minG < L_table ({lspec})")
    if not det:
        print("        WARN: boundary not deterministic across reps (alignment zone)")
    ok &= good

# --- yield-bit (usched bit4) probe: does transN vs WnEG shift the boundary? ---
# bracket yield=1 -> usched=stall (bit4=0, WnEG); yield=0 -> usched=16+stall
# (bit4=1, transN).  eff_stall is identical, and CS2R-timed chains confirm the
# issue gap is identical too -- but the *stale/fresh hazard pattern* can differ:
# on this silicon the all-transN form (producer + every filler yield=0) shows a
# deterministic stale read at stall 5, pushing the reliable boundary 3 -> 6.
print("\nyield-bit probe (UIADD3->MOV):  yield=1 -> WnEG, yield=0 -> transN")


def boundary(prod_y, filler_y):
    reps = [run("UIADD3", "MOV", STALLS, prod_y, filler_y) for _ in range(3)]
    sweep = "".join("F" if sum(1 for r in reps if r[i] == TRUE) >= 2
                    else ("S" if sum(1 for r in reps if r[i] == POISON) >= 2
                          else "?")
                    for i in range(len(STALLS)))[SWEEP]
    m = None
    for j in range(len(sweep)):
        if all(c == "F" for c in sweep[j:]):
            m = STALLS[SWEEP][j]
            break
    return sweep, m


for py, fy, tag in [(1, 1, "WnEG / WnEG  "), (0, 0, "transN / transN"),
                    (1, 0, "WnEG prod, transN fillers"),
                    (0, 1, "transN prod, WnEG fillers")]:
    sweep, m = boundary(py, fy)
    print(f"  P=yield={py} F=yield={fy} [{tag}]: {sweep}  minG={m}")

gW, mW = boundary(1, 1)
gT, mT = boundary(0, 0)
if mW is not None and mT is not None:
    delta = mT - mW
    print(f"  all-transN minG ({mT}) vs all-WnEG minG ({mW}): "
          f"delta = {delta:+d}")
    if delta > 0:
        print("  -> transN carries a wider hazard window; use WnEG (yield=1)")
    elif delta < 0:
        print("  WARN: transN boundary is TIGHTER than WnEG here (unexpected)")
    if not (mW and mT and 1 <= mW <= 16 and 1 <= mT <= 16):
        ok = False
        print("  FAIL: yield-probe could not resolve both boundaries")
else:
    ok = False
    print("  FAIL: yield-probe could not resolve a boundary")
print()

print("=== udp->int forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
