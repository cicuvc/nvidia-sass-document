import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# S2R special-register read — hand-built ELF (scoreboard-corrected).
#
# S2R is variable-latency; completion is signalled through a write
# scoreboard.  ptxas emits `S2R R7, SR_TID.X &wr=0x0` (sets SB0) and the
# consumer waits with `&req={0}`.  Without the wait, reading the S2R result
# (or an address derived from it) returns garbage and a computed store
# address faults (CUDA_ERROR_ILLEGAL_ADDRESS).
#
# Here each thread reads TID.X, computes out + 4*tid, and stores the tid
# back; the STG waits on the S2R's SB0 so the address and data are valid.
# ---------------------------------------------------------------------------

def build():
    lines = ["#fn s2r_test(out<1024>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]",
             # S2R writes SB0 (wr=0); result is ready only after SB0 set.
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             # derive per-thread address out + 4*tid
             "    IADD3 R5, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R5, R5, R5, RZ;[7:7:{}:5:1]",
             "    IADD3 R20, R6, R5, RZ;[7:7:{}:5:1]",
             "    IADD3 R21, R7, RZ, RZ;[7:7:{}:5:1]",
             # STG waits on SB0 (the S2R) before reading R20/R2
             "    STG.E desc[{UR4,UR5}][{R20,R21}], R2;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))

print("=== hand-built ELF S2R, scoreboard-corrected ===")
cubin = build()
open("x.cubin", "wb").write(cubin)
try:
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(256)
    mod.launch("s2r_test", grid=(1,), block=(8,), args=[d])
    mod.synchronize()
    vals = struct.unpack("<64I", mod.device_read(d, 256))
    mod.devmem_free(d)
    print("per-thread SR_TID.X stored to out[tid]:", vals[0:8])
    print("(expect 0,1,2,3,4,5,6,7)")
except RuntimeError as e:
    print(f"ERR {str(e)[:45]}")
