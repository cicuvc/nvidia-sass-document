import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# SHFL — warp shuffle (verified SM120)
#
# SHFL is the SASS of PTX shfl.sync (__shfl_*_sync).  Each lane puts its value
# in Ra; SHFL reads another lane's Ra selected by the mode + index, writes the
# result to Rd, and sets Pu = "source lane in range".
#
#   SHFL.IDX  Pu, Rd, Ra, source, bound   -> Rd = Ra[source]           (all)
#   SHFL.UP   Pu, Rd, Ra, delta, 0        -> Rd = Ra[t-delta]  t>=delta
#   SHFL.DOWN Pu, Rd, Ra, delta, 0x1f     -> Rd = Ra[t+delta]  t+delta<32
#   SHFL.BFLY Pu, Rd, Ra, mask, 0x1f      -> Rd = Ra[t^mask]
#   out-of-range source -> Rd = own Ra (unchanged), Pu = 0.
#   UP's bound must be 0 (RZ); DOWN/IDX/BFLY use 0x1f for a full warp.
#
# Empirically verified: IDX source=5 -> all lanes get 5; UP delta=4 ->
# (0,1,2,3, 0,1,2,...,27); DOWN delta=4 -> (4..31, 28,29,30,31 own); BFLY
# mask=4 -> t^4.  Pu=1 for lanes with a valid source (16-NOP cross-pipe delay
# needed before an int-pipe @P predicate consumer reads it).
#
# Gotchas: SHFL is DECOUPLED_RD_WR_SCBD — the result write needs `wr` and the
# consumer `req`; the Pu predicate needs ~16 NOPs before @P consumption.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

def shfl(mode):
    pre = ""
    if mode == "idx":
        pre = "    MOV32I R4, 0x5;[7:7:{}:5:1]"
        sh = "    SHFL.IDX P1, R5, R2, R4, R4;[2:7:{0}:5:1]"
    elif mode == "up":
        sh = "    SHFL.UP P1, R5, R2, 0x4, RZ;[2:7:{0}:5:1]"
    elif mode == "down":
        sh = "    SHFL.DOWN P1, R5, R2, 0x4, 0x1f;[2:7:{0}:5:1]"
    elif mode == "bfly":
        sh = "    SHFL.BFLY P1, R5, R2, 0x4, 0x1f;[2:7:{0}:5:1]"
    lines = ["#fn k(buf<8>) {",
             "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(buf);[1:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]", pre, sh]
    lines += ["    NOP;[7:7:{}:5:1]"] * 16
    lines += [
             "    @P1 MOV32I R10, 0x1;[7:7:{}:5:1]",
             "    @!P1 MOV32I R10, 0x0;[7:7:{}:5:1]",
             "    IADD3 R3, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R3, R3, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R8, R6, R3, RZ;[7:7:{0,1}:5:1]",
             "    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R5;[2:1:{2}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R8,R9}+0x80], R10;[7:1:{}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    v = struct.unpack("<64I", mod.device_read(d, 256))
    mod.devmem_free(d)
    return tuple(v[0:32]), tuple(v[32:64])

rd, pu = shfl("idx")
check("IDX source=5: all lanes get 5", rd, (5,) * 32)
check("IDX Pu all in-range", pu, (1,) * 32)

rd, pu = shfl("up")
check("UP delta=4: lane t <- t-4 (own for t<4)",
      rd, tuple(t - 4 if t >= 4 else t for t in range(32)))
check("UP Pu in-range for t>=4", pu, tuple(1 if t >= 4 else 0 for t in range(32)))

rd, pu = shfl("down")
check("DOWN delta=4: lane t <- t+4 (own for t>=28)",
      rd, tuple(t + 4 if t < 28 else t for t in range(32)))

rd, pu = shfl("bfly")
check("BFLY mask=4: lane t <- t^4", rd, tuple(t ^ 4 for t in range(32)))
check("BFLY Pu all in-range", pu, (1,) * 32)

print(f"\n=== SHFL (warp shuffle): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
