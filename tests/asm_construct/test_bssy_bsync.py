import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# BSSY / BSYNC — branch-to-symbol & sync-stack reconvergence (verified SM120).
#
# BSSY (0x4A5, cbu_pipe): pushes {return_pc, reconvergence_target} on the warp
#   sync stack and continues linearly.  BSYNC (0x4A1, cbu_pipe): pops the
#   entry and branches to the matching BSSY's target (the reconvergence point).
#
# Encoding: `BSSY Bn, #label(target)` — barReg Bn at [19:16], target Sa at
#   [63:34] SCALE 4, PC-relative from the NEXT instruction:
#   Sa = (target - next_pc) / 4.  Guard predicate Pg at [14:12]+[15].
#   `BSYNC Bn` — barReg only; BSSY Bn must match BSYNC Bn.
#
# Key empirical findings (this session):
#   1. The BSSY guard predicate does NOT skip lanes to the target.  The skip
#      must be an explicit predicated branch (ptxas: `@P0 BRA join` inside a
#      BSSY/BSYNC-wrapped region).
#   2. A predicated BRA that consumes a predicate produced by ISETP needs a
#      long scheduler stall on the ISETP (>=13) — the CBU predicate-consume
#      latency; below 13 the branch reads a stale predicate and takes the
#      wrong path.  (int_pipe consumers like MOV read it in-order with no
#      such requirement.)
#   3. `BSSY.RECONVERGENT` / `BSYNC.RECONVERGENT` printed by cuobjdump is only
#      a scheduling annotation (opex/usched bits 73/107/109); the plain
#      BSSY/BSYNC encoding is functionally identical.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

STALL = 13   # ISETP->predicated-BRA latency floor

def run(body, block=32):
    """body: list of SASS lines inside the kernel; stores R20/R21/R22 per lane
    at buf[4*tid], buf[4*tid+128], buf[4*tid+256]."""
    lines = ["#fn k(buf<2048>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    MOV32I R20, 0xAAAAAAAA;[7:7:{0}:5:1]",
             "    MOV32I R21, 0xBBBBBBBB;[7:7:{0}:5:1]",
             "    MOV32I R22, 0xCCCCCCCC;[7:7:{0}:5:1]",
             f"    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{{0}}:{STALL}:1]",
             ] + body + [
             "    IADD3 R3, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R3, R3, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R4, R6, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R5, R7, RZ, RZ;[7:7:{0}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R4,R5}+0x0], R20;[0:1:{0}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R4,R5}+0x80], R21;[0:1:{0}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R4,R5}+0x100], R22;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(2048)
    mod.device_write(d, struct.pack("<512I", *[0] * 512))
    mod.launch("k", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    v = struct.unpack("<96I", mod.device_read(d, 384))
    mod.devmem_free(d)
    return v[0:32], v[32:64], v[64:96]


# ---- 1. linear warp-wide BSSY/BSYNC (no divergence) -----------------------
a20, a21, a22 = run([
    "    BSSY B0, #label(join);[7:7:{}:5:1]",
    "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
    "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",
    "    MOV32I R22, 0x33333333;[7:7:{}:5:1]",
    "    BSYNC B0;[7:7:{}:5:1]",
    "    #def_label(join)",
])
r1 = all(a20[t] == 0x11111111 and a21[t] == 0x22222222 and a22[t] == 0x33333333
         for t in range(32))
check("1. linear warp-wide BSSY/BSYNC (all 32 run body+join)", r1, True)

# ---- 2. ptxas-style if-skip ----------------------------------------------
# BSSY B0, join ; @!P0 BRA join ; body(tid<16) ; BSYNC B0 ; join
a20, a21, a22 = run([
    "    BSSY B0, #label(join);[7:7:{}:5:1]",
    "    @!P0 BRA #label(join);[7:7:{}:5:1]",
    "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
    "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",
    "    MOV32I R22, 0x33333333;[7:7:{}:5:1]",
    "    BSYNC B0;[7:7:{}:5:1]",
    "    #def_label(join)",
])
r2 = all((a20[t] == (0x11111111 if t < 16 else 0xAAAAAAAA)) and
         (a21[t] == (0x22222222 if t < 16 else 0xBBBBBBBB)) and
         (a22[t] == (0x33333333 if t < 16 else 0xCCCCCCCC)) for t in range(32))
check("2. if-skip: @!P0 BRA skips body for tid>=16, BSYNC reconverges", r2, True)

# ---- 3. if/else two divergent paths ---------------------------------------
# BSSY B0, join ; @P0 BRA taken ; else path ; BRA join ; taken: if path ; BSYNC
a20, a21, a22 = run([
    "    BSSY B0, #label(join);[7:7:{}:5:1]",
    "    @P0 BRA #label(taken);[7:7:{}:5:1]",
    "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",   # else path (tid>=16)
    "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",
    "    BRA #label(join);[7:7:{}:5:1]",          # else lanes skip BSYNC
    "    #def_label(taken)",
    "    MOV32I R21, 0x55555555;[7:7:{}:5:1]",   # if path (tid<16)
    "    MOV32I R22, 0x66666666;[7:7:{}:5:1]",
    "    BSYNC B0;[7:7:{}:5:1]",
    "    #def_label(join)",
    "    MOV32I R22, 0x77777777;[7:7:{}:5:1]",   # join: all lanes
])
r3 = all((a20[t] == (0xAAAAAAAA if t < 16 else 0x11111111)) and
         (a21[t] == (0x55555555 if t < 16 else 0x22222222)) and
         (a22[t] == 0x77777777) for t in range(32))
check("3. if/else: taken path BSYNCs, else path BRA-skips, both reconverge", r3, True)

# ---- 4. loop with back-branch + BSSY/BSYNC exit ---------------------------
# P1 = P0 (tid<16): P1-true lanes loop back N times, then BSYNC to exit.
a20, a21, a22 = run([
    "    MOV32I R24, 0x0;[7:7:{}:5:1]",           # counter
    "    BSSY B0, #label(exit);[7:7:{}:5:1]",
    "    #def_label(loop)",
    "    IADD3 R24, R24, 0x1, RZ;[7:7:{}:5:1]",   # ++counter
    "    ISETP.LT.AND P1, PT, R24, 0x3, PT;[7:7:{0}:13:1]",  # P1 = counter<3
    "    IADD3 R20, R24, 0x1000, RZ;[7:7:{}:5:1]",
    "    @P1 BRA #label(loop);[7:7:{}:5:1]",
    "    BSYNC B0;[7:7:{}:5:1]",
    "    #def_label(exit)",
])
# tid<16 (P0 true) lanes loop 3x -> R20 = 3+0x1000; tid>=16 loop 0x -> 0x1000
r4 = all((a20[t] == 0x1003 if t < 16 else 0x1000) for t in range(32))
check("4. loop: @P1 BRA back-branch, BSYNC exits to join", r4, True)

# ---- 5. mismatched bar register -------------------------------------------
# BSSY B0 ... BSYNC B1 — does the sync id have to match?
a20, a21, a22 = run([
    "    BSSY B0, #label(join);[7:7:{}:5:1]",
    "    @!P0 BRA #label(join);[7:7:{}:5:1]",
    "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
    "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",
    "    BSYNC B1;[7:7:{}:5:1]",
    "    #def_label(join)",
    "    MOV32I R22, 0x33333333;[7:7:{}:5:1]",
], block=32)
r5 = all(a22[t] == 0x33333333 for t in range(32))
check("5. BSSY B0 / BSYNC B1 mismatch: join still reached (bar id ignored?)", r5, True)

# ---- 6. predicated BSSY alone (no skip) -----------------------------------
# @P0 BSSY: does gating change who reaches the join?  (Earlier: predicate does
# NOT skip lanes; all fall through and run the body.)
a20, a21, a22 = run([
    "    @P0 BSSY B0, #label(join);[7:7:{}:5:1]",
    "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
    "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",
    "    BSYNC B0;[7:7:{}:5:1]",
    "    #def_label(join)",
])
r6 = all(a20[t] == 0x11111111 and a21[t] == 0x22222222 for t in range(32))
check("6. @P0 BSSY (guarded): body still runs for ALL lanes (no lane skip)", r6, True)

print(f"\n=== BSSY/BSYNC: {'ALL PASS' if ok else 'FAILURES PRESENT'} ===")
sys.exit(0 if ok else 1)
