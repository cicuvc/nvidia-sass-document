import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from archutil import adapt_source, same_as_capture  # noqa: E402
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# R2UR — register to uniform register (udp_pipe; verified SM120, RTX 5090)
#
#   R2UR [Pu,] URd, Ra | R2UR.OR Pu, URd, Ra | R2UR.FILL/BROADCAST ... (0x2ca)
#
# Verified semantics on silicon:
#   * URd = the value of Ra in the FIRST ACTIVE lane (lowest active laneid
#     under the guard predicate).  Full warp  -> lane 0's value; @P0 with
#     lanes 8..31 active -> lane 8's value; @!P0 (lanes 0..7) -> lane 0's.
#   * The .OR variant does NOT perform a cross-lane OR-reduce (REDUX.OR is
#     the real reduction: OR(1..32) == 0x3F verified).  .FILL/.BROADCAST
#     (Blackwell nonconformity encodings) behave identically to the plain
#     form in every configuration probed.
#   * Pu (destination predicate) read back 0 via P2R in all probed cases
#     (uniform/divergent source, full/partial mask) — role unresolved.
#   * 64-bit register->uniform moves are two R2URs (low then high word).
#   * Pu (destination predicate) is a per-lane NON-UNIFORM predicate:
#     every ACTIVE lane whose Ra differs from the captured uniform value
#     (first active lane's Ra) gets Pu=1; ALL other lanes (the elected lane,
#     equal-valued lanes, inactive lanes) are PRESERVED -- Pu never writes 0.
#     Read it per-lane via P2R (a single uniform readback returns only the
#     elected lane's bit, which is why earlier probes saw "always 0").
#     Verified with preset experiments: pre-set P0=1 -> elected lane KEEPS 1.
# ---------------------------------------------------------------------------

# Reference encodings (schedule [2:7:{}:5:1] = wr_sb 2, WAIT5_END_GROUP).
# Note: the noOR nonconformity variants show Pu when it is explicit; the
# hidden-PT default encodes 0b111 at [83:81] (hi bits 0xe0000).
REF = [
    (0x00000000021072ca, 0x000fca00000e0000, "R2UR UR16, R2"),
    (0x00000000021072ca, 0x000fca0000100000, "R2UR.OR P0, UR16, R2"),
    (0x00000000021072ca, 0x000fca0000400000, "R2UR.FILL P0, UR16, R2"),
    (0x00000000021072ca, 0x000fca0000800000, "R2UR.BROADCAST P0, UR16, R2"),
    (0x00000000021072ca, 0x000fca00004e0000, "R2UR.FILL UR16, R2 (Pu=PT default)"),
    (0x00000000021072ca, 0x000fca00008e0000, "R2UR.BROADCAST UR16, R2 (Pu=PT default)"),
]
_SRC_ALL = """R2UR UR16, R2;[2:7:{}:5:1]
R2UR.OR P0, UR16, R2;[2:7:{}:5:1]
R2UR.FILL P0, UR16, R2;[2:7:{}:5:1]
R2UR.BROADCAST P0, UR16, R2;[2:7:{}:5:1]
R2UR.FILL UR16, R2;[2:7:{}:5:1]
R2UR.BROADCAST UR16, R2;[2:7:{}:5:1]
"""
_SRC_SM90 = "R2UR UR16, R2;[2:7:{}:5:1]\nR2UR.OR P0, UR16, R2;[2:7:{}:5:1]\n"
flat = assemble_flat(_SRC_ALL if same_as_capture("sm120") else _SRC_SM90)
ok = True
if not _pins:
    print("info .FILL/.BROADCAST forms absent from the sm_90 spec — running base/OR cases only")
for i, (lo, hi, name) in enumerate(REF if _pins else REF[:2]):
    good = flat[i] == (lo, hi)
    if i >= len(flat): break
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes {name:24s} lo={flat[i][0]:016x} hi={flat[i][1]:016x}")


def build(src):
    return CudaModule(assemble(adapt_source(src), check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def settle_store(ur, rd, off):
    """Settle a udp-written URx then store it via IADD3 RUR to out+off."""
    return f"""    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR14, {ur};[7:7:{{2}}:5:1]
    IADD3 {rd}, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], {rd};[7:7:{{0,1}}:1:0]
"""


def kernel(body):
    return f"""#fn t(out<8>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
{body}    EXIT;[7:7:{{}}:5:0]
}}"""


def run(body, block=32):
    reset_context()
    mod = build(kernel(body))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    data = mod.device_read(d, 0x40)
    mod.devmem_free(d)
    return struct.unpack("<16I", data)


try:
    build(kernel(""))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

UNI = "    MOV32I R2, 0x12345678;[2:7:{}:5:1]\n"
DIV = """    S2R R2, SR_LANEID;[0:7:{}:5:1]
    IADD3 R2, R2, 1, RZ;[7:7:{0}:5:1]
"""
MASK = """    S2R R8, SR_LANEID;[0:7:{}:5:1]
    IADD3 R8, R8, 1, RZ;[7:7:{0}:5:1]
    ISETP.GE.AND P0, PT, R8, 0x9, PT;[7:7:{}:13:1]
"""

# uniform source -> exact value through every encoding variant
for label, inst in [("noOR", "R2UR UR16, R2"),
                    ("OR", "R2UR.OR P0, UR16, R2"),
                    ("FILL", "R2UR.FILL UR16, R2"),
                    ("BROADCAST", "R2UR.BROADCAST UR16, R2")]:
    v = run(UNI + f"    {inst};[2:7:{{}}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
    good = v == 0x12345678
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} uniform {label:10s} -> 0x{v:08x} (exp 0x12345678)")

# divergent source: full warp elects lane 0 (value 1)
v = run(DIV + "    R2UR UR16, R2;[2:7:{}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
good = v == 1
ok &= good
print(f"{'ok ' if good else 'FAIL'} divergent full-warp noOR -> {v} (exp 1 = lane0's lane+1)")

# .OR is NOT a cross-lane OR-reduce (REDUX.OR control = 0x3f)
v = run(DIV + "    R2UR.OR P0, UR16, R2;[2:7:{}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
good = v == 1
ok &= good
print(f"{'ok ' if good else 'FAIL'} divergent .OR -> {v} (exp 1; NOT 0x3f — REDUX.OR is the real reduce)")

v = run(DIV + "    REDUX.OR UR16, R2;[2:7:{}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
good = v == 0x3F
ok &= good
print(f"{'ok ' if good else 'FAIL'} REDUX.OR control -> 0x{v:02x} (exp 0x3f = OR of 1..32)")

# partial active mask: first active lane is lane 8 -> its value is 9
for label, inst in [("noOR", "R2UR UR16, R2"),
                    ("OR", "R2UR.OR P1, UR16, R2"),
                    ("FILL", "R2UR.FILL UR16, R2"),
                    ("BROADCAST", "R2UR.BROADCAST UR16, R2")]:
    v = run(DIV + MASK + f"    @P0 {inst};[2:7:{{}}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
    good = v == 9
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} partial-mask @P0 {label:10s} -> {v} (exp 9 = first active lane 8)")

# negated guard: active lanes 0..7, first active lane 0 -> 1
v = run(DIV + MASK + "    @!P0 R2UR UR16, R2;[2:7:{}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
good = v == 1
ok &= good
print(f"{'ok ' if good else 'FAIL'} partial-mask @!P0 noOR -> {v} (exp 1 = first active lane 0)")

# 64-bit register pair -> two R2URs (low then high word)
vals = run("""    MOV32I R2, 0xDEADBEEF;[2:7:{}:5:1]
    MOV32I R3, 0x12345678;[3:7:{}:5:1]
    R2UR UR16, R2;[4:7:{}:5:1]
    R2UR UR17, R3;[5:7:{}:5:1]
""" + settle_store("UR16", "R20", 0x0) + settle_store("UR17", "R21", 0x4))
good = vals[0] == 0xDEADBEEF and vals[1] == 0x12345678
ok &= good
print(f"{'ok ' if good else 'FAIL'} 64-bit pair -> lo=0x{vals[0]:08x} hi=0x{vals[1]:08x} (exp DEADBEEF/12345678)")

# ---------------------------------------------------------------------------
# Pu semantics: per-lane non-uniform predicate, write-1-only (never clears).
# R2UR has NO write scoreboard (dst_wr_sb pinned *7) and is coupled; pad a
# dependent-IADD3 chain before the P2R readback of Pu.
#
# Pu RAW latency (probed with static stalls): WAIT1..3_END_GROUP read a STALE
# predicate (old 0s); WAIT4/WAIT5 suffice with zero filler; usched=0 is
# OFF_DECK_DRAIN (warp waits for full pipeline drain -> also correct).  The
# URd result still needs the ~13-15 cycle coupled latency, so pad generously.
# ---------------------------------------------------------------------------
PU_CHAIN = "    IADD3 R22, R22, RZ, RZ;[7:7:{}:5:1]\n" * 16


def kernel_lanes(body):
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


def run_lanes(body):
    reset_context()
    mod = CudaModule(assemble(kernel_lanes(body), check_deps=False))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    v = struct.unpack("<32I", mod.device_read(d, 0x80))
    mod.devmem_free(d)
    return v


DIV = "    S2R R2, SR_LANEID;[0:7:{}:5:1]\n    IADD3 R2, R2, 1, RZ;[7:7:{0}:5:1]\n"
P0_PRESET_0 = "    ISETP.LT.AND P0, PT, RZ, 0x0, PT;[7:7:{}:13:1]\n"
P0_PRESET_1 = "    ISETP.GE.AND P0, PT, RZ, 0x0, PT;[7:7:{}:13:1]\n"
R2UR_OR = "    R2UR.OR P0, UR16, R2;[2:7:{}:5:1]\n"
P2R_P0 = "    P2R R3, PR, RZ, 0x1;[7:7:{}:5:1]\n" + "    IADD3 R22, R22, RZ, RZ;[7:7:{}:5:1]\n" * 4 + "\n"

# divergent source, P0 preset 0: elected lane 0 preserved (0), rest written (1)
v = run_lanes(DIV + P0_PRESET_0 + R2UR_OR + PU_CHAIN + P2R_P0)
good = v[0] == 0 and all(x == 1 for x in v[1:])
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu preset0 div: lane0={v[0]} lanes1-31 all-1: {all(x==1 for x in v[1:])}")

# divergent source, P0 preset 1: elected lane KEEPS 1 (never cleared)
v = run_lanes(DIV + P0_PRESET_1 + R2UR_OR + PU_CHAIN + P2R_P0)
good = all(x == 1 for x in v)
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu preset1 div: elected lane preserved={v[0]} (all lanes must be 1)")

# groups: value = (laneid&8) ? 0xAA : 0x55, P0 preset 0.
# equal-valued lanes (0..7, 16..23) preserved -> 0; differing (8..15, 24..31) -> 1
GROUPS = ("    MOV32I R2, 0x55;[2:7:{}:5:1]\n"
          + "    LOP3 R9, R8, 0x8, RZ, 0xc0;[7:7:{0}:5:1]\n"
          + "    ISETP.NE.AND P2, PT, R9, 0x0, PT;[7:7:{0}:13:1]\n"
          + "    @P2 MOV32I R2, 0xAA;[7:7:{}:5:1]\n")
v = run_lanes(GROUPS + P0_PRESET_0 + R2UR_OR + PU_CHAIN + P2R_P0)
good = (v[0:8] == (0,) * 8 and v[8:16] == (1,) * 8 and
        v[16:24] == (0,) * 8 and v[24:32] == (1,) * 8)
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu groups 0x55/0xAA: equal-valued lanes preserved 0, differing written 1 -> {tuple(v)}")

# predicated partial mask (lanes >= 8), divergent, P0 preset 1:
# inactive lanes 0..7 preserved (1), elected lane 8 preserved (1), 9..31 written (1)
MASK_GE8 = "    ISETP.GE.AND P1, PT, R2, 0x9, PT;[7:7:{0}:13:1]\n"
v = run_lanes(DIV + P0_PRESET_1 + MASK_GE8 + f"    @P1 {R2UR_OR}" + PU_CHAIN + P2R_P0)
good = all(x == 1 for x in v)
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu partial mask preset1: inactive+elected preserved (all lanes must be 1)")

# guard-off entirely (@P1 with P1=0), P0 preset 1: nothing written, all keep 1
v = run_lanes(DIV + P0_PRESET_1 + "    ISETP.NE.AND P1, PT, RZ, RZ, PT;[7:7:{0}:13:1]\n"
              + f"    @P1 {R2UR_OR}" + PU_CHAIN + P2R_P0)
good = all(x == 1 for x in v)
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu guard-off: skipped R2UR writes nothing (all lanes keep preset 1)")

# divergent + FILL/BROADCAST variants write Pu identically
for label, inst in [("FILL", "R2UR.FILL P0, UR16, R2"),
                    ("BROADCAST", "R2UR.BROADCAST P0, UR16, R2")]:
    v = run_lanes(DIV + P0_PRESET_0 + f"    {inst};[2:7:{{}}:5:1]\n" + PU_CHAIN + P2R_P0)
    good = v[0] == 0 and all(x == 1 for x in v[1:])
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} Pu {label:10s} preset0 div: lane0={v[0]} lanes1-31 all-1: {all(x==1 for x in v[1:])}")

# Pu RAW latency floor: WAIT1_END_GROUP reads STALE (old P0=0), WAIT5 reads settled.
v = run_lanes(DIV + P0_PRESET_0 + "    R2UR.OR P0, UR16, R2;[2:7:{}:1:1]\n" + P2R_P0)
good = all(x == 0 for x in v)
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu WAIT1 stale readback: all-0 (write not landed yet) -> {tuple(v[:8])}...")
v = run_lanes(DIV + P0_PRESET_0 + "    R2UR.OR P0, UR16, R2;[2:7:{}:5:1]\n" + P2R_P0)
good = v[0] == 0 and all(x == 1 for x in v[1:])
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu WAIT5 settled readback: lane0={v[0]} lanes1-31 all-1: {all(x==1 for x in v[1:])}")

# the trans flavor (yield=0 -> usched=stall+16) has the SAME timing:
# trans1 stale, trans4 settled.  (usched=16 from yield=0/stall=0 is a gap
# and is rejected by TABLES_opex_* with ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR.)
v = run_lanes(DIV + P0_PRESET_0 + "    R2UR.OR P0, UR16, R2;[2:7:{}:1:0]\n" + P2R_P0)
good = all(x == 0 for x in v)
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu trans1 stale readback: all-0 (yield=0 same as WAIT1) -> {tuple(v[:8])}...")
v = run_lanes(DIV + P0_PRESET_0 + "    R2UR.OR P0, UR16, R2;[2:7:{}:4:0]\n" + P2R_P0)
good = v[0] == 0 and all(x == 1 for x in v[1:])
ok &= good
print(f"{'ok ' if good else 'FAIL'} Pu trans4 settled readback: lane0={v[0]} lanes1-31 all-1: {all(x==1 for x in v[1:])}")

print("\n=== R2UR semantic verification: ALL OK ===" if ok else "\n=== R2UR FAILURES ===")
sys.exit(0 if ok else 1)
