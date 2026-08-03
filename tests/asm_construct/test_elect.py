import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# ELECT — elect a leader lane (verified SM120)
#
# `ELECT Pu, URd, <candidates>` picks the LOWEST-NUMBERED ACTIVE candidate lane
# and writes:
#   Pu  — leader predicate: true in exactly the elected lane (elsewhere false)
#   URd — uniform register = the elected lane's ID (warp-uniform)
# Candidates come from a uniform-register membermask `URa` (or its invert
# `~URa`) or a predicate `Pp` (with `.IGNOREKILL` controlling killed lanes).
# `MOV Rd, URx` (mov__RU, 0x1c02) reads a uniform register into a GPR.
#
# Empirical (SM120, per-lane stores):
#   candidates all (UR6=0xFFFFFFFF)            -> lane 0,  URd=0
#   candidates lanes 16-31 (UR6=0xFFFF0000)    -> lane 16, URd=16
#   ~UR6 = lanes 0-15                          -> lane 0
#   predicate Pp = (tid&1)                     -> lane 1,  URd=1
#
# Gotchas:
#   * ELECT's output predicate Pu needs a cross-pipe delay before an int-pipe
#     consumer (@P0 MOV) sees it — 8 NOPs suffices; 0 gives "no lane elected".
#   * `MOV Rd, URx` (UR->GPR) is 0x1c02; UMOV is UR->UR only.
#   * Scoreboard: the per-lane address chain that reads R6/R7 (from `LDC.64
#     R6` wr=1/SB1) must carry req={1} on those consumers, else the store
#     faults (700).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

def elect(cands, block=32):
    inner = []
    if cands == "full":
        inner = ["    UMOV UR6, 0xFFFFFFFF;[7:7:{}:5:1]",
                 "    ELECT P0, UR8, UR6;[7:7:{}:5:1]"]
    elif cands == "mask16":
        inner = ["    UMOV UR6, 0xFFFF0000;[7:7:{}:5:1]",
                 "    ELECT P0, UR8, UR6;[7:7:{}:5:1]"]
    elif cands == "invmask16":
        inner = ["    UMOV UR6, 0xFFFF0000;[7:7:{}:5:1]",
                 "    ELECT P0, UR8, ~UR6;[7:7:{}:5:1]"]
    elif cands == "pred":
        inner = ["    LOP3 R3, R2, 0x1, RZ, 0xc0;[7:7:{0}:5:1]",
                 "    ISETP.EQ.AND P1, PT, R3, 0x1, PT;[7:7:{0}:13:1]",
                 "    ELECT P0, UR8, P1;[7:7:{}:5:1]"]
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]"] + inner + [
             "    NOP;[7:7:{}:5:1]"] * 8 + [
             "    MOV R4, UR8;[7:7:{}:5:1]",
             "    @P0 MOV32I R20, 0xDEADBEEF;[7:7:{}:5:1]",
             "    IADD3 R3, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R3, R3, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R8, R6, R3, RZ;[7:7:{0,1}:5:1]",
             "    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R20;[0:1:{0,1}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R8,R9}+0x80], R4;[7:1:{}:1:0]",
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
    elected = [t for t in range(block) if v[t] == 0xDEADBEEF]
    urd = [x for x in sorted({v[block + t] for t in range(block)}) if x != 0xAAAAAAAA]
    return elected, urd

e, u = elect("full")
check("full candidates -> lane 0, URd=0", (e, u), ([0], [0]))
e, u = elect("mask16")
check("candidates lanes 16-31 -> lane 16, URd=16", (e, u), ([16], [16]))
e, u = elect("invmask16")
check("~UR6 (lanes 0-15) -> lane 0", (e, u), ([0], [0]))
e, u = elect("pred")
check("predicate Pp=(tid&1) -> lane 1, URd=1", (e, u), ([1], [1]))

print(f"\n=== ELECT (leader election): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
