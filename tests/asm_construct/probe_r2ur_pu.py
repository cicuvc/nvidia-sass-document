import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# Probe the MEANING of the R2UR destination predicate Pu (sm_120, RTX 5090).
#
# Prior work (test_r2ur.py) read Pu back as 0 via P2R in every configuration,
# and left it unresolved.  Two hypotheses were addressed poorly there:
#   1. Pu is a NON-UNIFORM predicate -- it may differ per lane -- but it was
#      collapsed to a single uniform value when read.  We now read each lane's
#      own bit via P2R (thread-local predicate->GPR) and store per-lane.
#   2. The old probe may have read Pu BEFORE R2UR's coupled pd write landed
#      (no scoreboard on R2UR: dst_wr_sb is pinned *7).  We sweep a wide
#      dependent-IADD3 stall chain between the R2UR and the P2R read.
#
# Battery 1 -- stall sweep + scenario x variant matrix:
#   A. uniform source, converged full mask
#   B. divergent source (laneid+1), converged full mask
#   C. predicated partial mask (lanes 8..31)
#   D. TRUE divergence -- R2UR executed on a branch path (mask 16..31) while
#      lanes 0..15 run a different PC (nonconformant convergence mask)
#   E. guard-off (all lanes masked) -- does a skipped R2UR still write Pu?
#
# Battery 2 -- disambiguation:
#   G. value = (laneid&8) ? 0xAA : 0x55, full mask: lanes 0..7 all carry the
#      captured value 0x55 -> tests "elect-flag" vs "differs-from-captured"
#   C0/C1. scenario C with P0 pre-set 0/1 -> are inactive lanes untouched?
#   Dd. scenario D read per-lane (elected lane 16 must read 0)
#   L0. only lane 0 active, uniform/divergent source
# ---------------------------------------------------------------------------

REF_SCHED = "[2:7:{}:5:1]"


def chain(n, reg=22):
    """n dependent IADD3s on the same reg: serializes at ~ALU latency each."""
    return "".join(f"    IADD3 R{reg}, R{reg}, RZ, RZ;[7:7:{{}}:5:1]\n" for _ in range(n))


PRESET0 = "    ISETP.LT.AND P0, PT, RZ, 0x0, PT;[7:7:{}:13:1]\n"
PRESET1 = "    ISETP.GE.AND P0, PT, RZ, 0x0, PT;[7:7:{}:13:1]\n"


def kernel(body):
    return f"""#fn t(out<8>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    S2R R8, SR_LANEID;[0:7:{{}}:5:1]
    IADD3 R10, R8, R8, RZ;[7:7:{{0}}:5:1]
    IADD3 R10, R10, R10, RZ;[7:7:{{0}}:5:1]
{body}    IADD3 R16, R6, R10, RZ;[7:7:{{0,1}}:5:1]
    IADD3 R17, R7, RZ, RZ;[7:7:{{1}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R16,R17}}], R3;[7:1:{{}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def body(scenario, inst, stall, preset=None):
    src_uniform = "    MOV32I R2, 0x12345678;[2:7:{}:5:1]\n"
    src_diverg = "    S2R R2, SR_LANEID;[0:7:{}:5:1]\n    IADD3 R2, R2, 1, RZ;[7:7:{0}:5:1]\n"
    pre = src_uniform if scenario == "A" else src_diverg
    p = "" if preset is None else preset

    if scenario in ("A", "B"):
        lines = [pre, p, f"    {inst};{REF_SCHED}\n"]
    elif scenario == "C":  # predicated mask: lanes >= 8 (first active = 8)
        lines = [pre, "    ISETP.GE.AND P1, PT, R2, 0x9, PT;[7:7:{0}:13:1]\n",
                 p, f"    @P1 {inst};{REF_SCHED}\n"]
    elif scenario == "D":  # true divergence: lanes 16..31 fall through,
        # lanes 0..15 branch straight to join (verified BSSY/BSYNC pattern)
        lines = [pre, "    ISETP.LT.AND P1, PT, R2, 0x11, PT;[7:7:{0}:13:1]\n",
                 p, "    MOV32I R3, 0xDEADBEEF;[7:7:{}:5:1]\n",
                 "    BSSY B0, #label(join);[7:7:{}:5:1]\n",
                 "    @!P1 BRA #label(join);[7:7:{}:5:1]\n",
                 f"    {inst};{REF_SCHED}\n"]
    elif scenario == "E":  # guard never true: P1 = 0 for all lanes
        lines = [pre, p, "    ISETP.NE.AND P1, PT, RZ, RZ, PT;[7:7:{0}:13:1]\n",
                 f"    @P1 {inst};{REF_SCHED}\n"]
    else:
        raise ValueError(scenario)

    tail = "".join(lines) + chain(stall)
    if scenario == "D":
        tail += ("    P2R R3, PR, RZ, 0x1;[7:7:{}:5:1]\n"
                 + chain(4)
                 + "    BSYNC B0;[7:7:{}:5:1]\n"
                 + "    #def_label(join)\n")
    else:
        tail += ("    P2R R3, PR, RZ, 0x1;[7:7:{}:5:1]\n" + chain(4))
    return tail + "\n"


def body_groups(inst, preset=None, stall=256):
    """value = (laneid & 8) ? 0xAA : 0x55, full mask."""
    p = "" if preset is None else preset
    return ("    MOV32I R2, 0x55;[2:7:{}:5:1]\n"
            + "    LOP3 R9, R8, 0x8, RZ, 0xc0;[7:7:{0}:5:1]\n"
            + "    ISETP.NE.AND P2, PT, R9, 0x0, PT;[7:7:{0}:13:1]\n"
            + "    @P2 MOV32I R2, 0xAA;[7:7:{}:5:1]\n"
            + p + f"    {inst};{REF_SCHED}\n"
            + chain(stall)
            + "    P2R R3, PR, RZ, 0x1;[7:7:{}:5:1]\n" + chain(4) + "\n")


def body_lane0(inst, uniform, preset=None, stall=256):
    """only lane 0 active (@P1), source uniform or divergent."""
    src = ("    MOV32I R2, 0x12345678;[2:7:{}:5:1]\n" if uniform else
           "    S2R R2, SR_LANEID;[0:7:{}:5:1]\n    IADD3 R2, R2, 1, RZ;[7:7:{0}:5:1]\n")
    p = "" if preset is None else preset
    return (src
            + "    ISETP.EQ.AND P1, PT, R8, 0x0, PT;[7:7:{0}:13:1]\n"
            + p + f"    @P1 {inst};{REF_SCHED}\n"
            + chain(stall)
            + "    P2R R3, PR, RZ, 0x1;[7:7:{}:5:1]\n" + chain(4) + "\n")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


def run(body):
    reset_context()
    mod = build(kernel(body))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    data = mod.device_read(d, 0x80)
    mod.devmem_free(d)
    return struct.unpack("<32I", data)


try:
    build(kernel(body("A", "R2UR.OR P0, UR16, R2", 0)))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

VARIANTS = {
    "OR":        "R2UR.OR P0, UR16, R2",
    "FILL":      "R2UR.FILL P0, UR16, R2",
    "BROADCAST": "R2UR.BROADCAST P0, UR16, R2",
    "OR.FILL":   "R2UR.OR.FILL P0, UR16, R2",
}

print("== stall sweep (uniform source, converged full mask, .OR) ==")
for stall in (0, 2, 4, 8, 16, 32, 64, 128, 256):
    v = run(body("A", VARIANTS["OR"], stall))
    print(f"  stall={stall:4d}  per-lane Pu[0..31] = {v}")

print("\n== scenario x variant matrix (stall=256) ==")
for scen in ("A", "B", "C", "D", "E"):
    for label, inst in VARIANTS.items():
        v = run(body(scen, inst, 256))
        nonz = {i for i, x in enumerate(v) if x != 0}
        print(f"  {scen} {label:10s} non-zero lanes={sorted(nonz) if nonz else 'NONE'}")

print("\n== stall sweep on B (divergent source) — Pu RAW settle ==")
for stall in (0, 1, 2, 4, 8, 16, 32, 64, 128):
    v = run(body("B", VARIANTS["OR"], stall))
    print(f"  stall={stall:4d}  per-lane Pu[0..31] = {v}")

print("\n== disambiguation battery (stall=256) ==")
v = run(body_groups(VARIANTS["OR"]))
print(f"  G  groups full-mask : Pu = {v}   (exp 0..7:0, 8..31:1 if 'differs-from-captured')")
v = run(body("C", VARIANTS["OR"], 256, preset=PRESET0))
print(f"  C0 preset0 lanes0-7 : Pu = {v}   (untouched->0, written->1)")
v = run(body("C", VARIANTS["OR"], 256, preset=PRESET1))
print(f"  C1 preset1 lanes0-7 : Pu = {v}   (untouched->1, cleared->0)")
v = run(body("D", VARIANTS["OR"], 256))
print(f"  Dd per-lane detail  : Pu = {v}   (exp 0..15=DEADBEEF, lane16=0, 17..31=1)")
v = run(body("D", VARIANTS["OR"], 256, preset=PRESET1))
print(f"  D1 preset1 detail   : Pu = {v}   (lanes 0..15 keep preset 1 if untouched)")
v = run(body_lane0(VARIANTS["OR"], uniform=True))
print(f"  L0u lane0-only uni  : Pu = {v}   (exp all 0)")
v = run(body_lane0(VARIANTS["OR"], uniform=False))
print(f"  L0d lane0-only div  : Pu = {v}   (exp all 0: lane0 == captured)")
for label in ("FILL", "BROADCAST"):
    v = run(body_groups(VARIANTS[label]))
    print(f"  G  groups {label:10s}: Pu = {v}")

print("\n=== done ===")