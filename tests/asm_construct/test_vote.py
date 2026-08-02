import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# VOTE — warp-wide predicate reduction / ballot (int_pipe, fixed latency)
# Verified on SM120.
#
#   VOTE.ALL/ANY/EQ Rd, Pu, [!]Pp
#     Rd = 32-bit ballot mask (bit i = lane i's Pp), for ALL modes
#     Pu = reduction over the ACTIVE lanes: ALL=AND, ANY=OR, EQ=all-equal
#   Membermask is dropped (PTX vote.sync) — votes over the hardware active
#   lane mask.  Rd may be RZ (dropped in text), Pu may be PT (sink).
#
# VoteOp [73:72]: ALL=0, ANY=1, EQ=2 (3 = INVALID, illegal).
# Pp [89:87] with negate bit [90]; Pu [83:81].
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} {got}")

def run_vote(pred_setup, vote_instr, block=32, divergent=False):
    """pred_setup sets P0 (and P2 if divergent); vote_instr is the VOTE.
    Returns (ballot_per_lane, pu_per_lane) each 32-entry (0 for inactive)."""
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4,UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(buf);[1:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]",
             "    MOV32I R10, 0xAAAAAAAA;[7:7:{}:5:1]"] + pred_setup
    if divergent:
        lines.append("    @P2 BRA #label(done);[7:7:{}:5:1]")
    lines += [
             "    " + vote_instr,
             "    IADD3 R3, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R3, R3, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R8, R6, R3, RZ;[7:7:{0,1}:5:1]",
             "    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R10;[0:1:{0,1}:1:0]",
             "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]",
             "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]",
             "    @P1 MOV32I R20, 0xDEADBEEF;[7:7:{}:5:1]",
             "    @!P1 MOV32I R20, 0x00000000;[7:7:{}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R8,R9}+0x80], R20;[7:1:{}:1:0]",
             "    #def_label(done)",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    v = struct.unpack(f"<{2 * block}I", mod.device_read(d, 2 * block * 4))
    mod.devmem_free(d)
    ballot = tuple(v[t] for t in range(block))
    pu = tuple(0xDEADBEEF if v[block + t] == 0xDEADBEEF else 0 for t in range(block))
    return ballot, pu

ISETP_LT16 = ["    MOV32I R3, 0x10;[7:7:{}:5:1]",
              "    ISETP.LT P0, R2, R3;[7:7:{0}:13:1]"]
ISETP_ALL = ["    MOV32I R3, 0x20;[7:7:{}:5:1]",
             "    ISETP.LT P0, R2, R3;[7:7:{0}:13:1]"]
ISETP_ODD = ["    LOP3 R3, R2, 0x1, RZ, 0xc0;[7:7:{0}:5:1]",
             "    MOV32I R4, 0x1;[7:7:{}:5:1]",
             "    ISETP.EQ.AND P0, PT, R3, R4, PT;[7:7:{0}:13:1]"]
ISETP_DIV = ["    MOV32I R3, 0x10;[7:7:{}:5:1]",
             "    ISETP.GE P2, R2, R3;[7:7:{0}:13:1]",   # active lanes 0-15
             "    MOV32I R3, 0x8;[7:7:{}:5:1]",
             "    ISETP.LT P0, R2, R3;[7:7:{0}:13:1]"]    # P0 = tid<8

# --- 1. ballot mask, all lanes active -------------------------------------
b, p = run_vote(ISETP_LT16, "VOTE.ANY R10, PT, P0;[7:7:{}:5:1]")
check("ballot tid<16 (all active) = 0x0000FFFF", b[0], 0x0000FFFF)
check("ballot is warp-wide (lane31 same)", b[31], 0x0000FFFF)

b, p = run_vote(ISETP_LT16, "VOTE.ANY R10, PT, !P0;[7:7:{}:5:1]")
check("ballot !P0 = 0xFFFF0000", b[0], 0xFFFF0000)

b, p = run_vote(ISETP_ALL, "VOTE.ANY R10, PT, P0;[7:7:{}:5:1]")
check("ballot all-true = 0xFFFFFFFF", b[0], 0xFFFFFFFF)

b, p = run_vote(ISETP_ODD, "VOTE.ANY R10, PT, P0;[7:7:{}:5:1]")
check("ballot tid%2 (odd lanes) = 0xAAAAAAAA", b[0], 0xAAAAAAAA)

# --- 2. vote predicates (ALL / ANY / EQ) ----------------------------------
b, p = run_vote(ISETP_LT16, "VOTE.ALL P1, P0;[7:7:{}:5:1]")
check("VOTE.ALL tid<16: Pu=0 (not all true)", p[0], 0)
b, p = run_vote(ISETP_ALL, "VOTE.ALL P1, P0;[7:7:{}:5:1]")
check("VOTE.ALL all-true: Pu=1", p[0], 0xDEADBEEF)
b, p = run_vote(ISETP_LT16, "VOTE.ANY P1, P0;[7:7:{}:5:1]")
check("VOTE.ANY tid<16: Pu=1 (some true)", p[0], 0xDEADBEEF)
b, p = run_vote(ISETP_LT16, "VOTE.EQ P1, P0;[7:7:{}:5:1]")
check("VOTE.EQ tid<16: Pu=0 (not all equal)", p[0], 0)
b, p = run_vote(ISETP_ALL, "VOTE.EQ P1, P0;[7:7:{}:5:1]")
check("VOTE.EQ all-true: Pu=1", p[0], 0xDEADBEEF)
b, p = run_vote(ISETP_ODD, "VOTE.EQ P1, P0;[7:7:{}:5:1]")
check("VOTE.EQ tid%2: Pu=0", p[0], 0)

# --- 3. divergent active mask (membermask dropped) -------------------------
b, p = run_vote(ISETP_DIV, "VOTE.ANY R10, PT, P0;[7:7:{}:5:1]", divergent=True)
check("diverged @P2(tid<16): ballot only over active lanes (0-7 true)", b[0], 0x000000FF)
check("diverged: inactive lane 31 never stores (out stays 0)", b[31], 0)
b, p = run_vote(ISETP_DIV, "VOTE.ANY P1, P0;[7:7:{}:5:1]", divergent=True)
check("diverged VOTE.ANY over active lanes: Pu=1", p[0], 0xDEADBEEF)
check("diverged VOTE.ANY: inactive lane 31 Pu=0", p[31], 0)

# --- 4. offline encoding self-check vs note/decoder -------------------------
enc = assemble_flat(
    "VOTE.ANY R7, PT, !P0;[7:7:{}:5:1]\n"
    "VOTE.ANY P0, P0;[7:7:{}:5:1]\n"
    "VOTE.ALL P0, P0;[7:7:{}:5:1]\n"
    "VOTE.EQ P0, P0;[7:7:{}:5:1]\n")
def fields(lo, hi):
    return (lo >> 16) & 0xFF, (hi >> 8) & 3, (hi >> 17) & 7, (hi >> 23) & 7, (hi >> 26) & 1
# Rd[23:16], voteop[73:72]=hi[9:8], Pu[83:81]=hi[19:17], Pp[89:87]=hi[25:23], Pp_not[90]=hi[26]
assert fields(*enc[0]) == (7, 1, 7, 0, 1), fields(*enc[0])
assert fields(*enc[1]) == (255, 1, 0, 0, 0), fields(*enc[1])
assert fields(*enc[2]) == (255, 0, 0, 0, 0), fields(*enc[2])
assert fields(*enc[3]) == (255, 2, 0, 0, 0), fields(*enc[3])
try:
    assemble_flat("VOTE.XYZ P0, P0;[7:7:{}:5:1]")
    check("invalid VoteOp rejected", False, True)
except Exception:
    check("invalid VoteOp rejected", True, True)
print("encoding self-check: VOTE modes + !Pp + invalid-op guard OK")

print(f"\n=== VOTE (warp vote/ballot): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
