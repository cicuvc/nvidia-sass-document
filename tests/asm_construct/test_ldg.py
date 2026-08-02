import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# LDG global load — hand-built ELF (scoreboard-corrected).
#
# LDG is variable-latency AND depends on the `desc[{UR4,UR5}]` cache-policy
# descriptor, which the kernel loads itself via LDCU.64 UR4.  That LDCU is
# also variable-latency; the LDG must wait on its scoreboard before using
# the descriptor, or the policy is garbage and the access faults with
# CUDA_ERROR_ILLEGAL_ADDRESS (700).
#
# Working pattern (mirrors ptxas `LDG.E ... &req={0} &wr=0x2`):
#   LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]   # wr=0 -> sets SB0
#   LDG.E  R20, desc[{UR4,UR5}][{R6,R7}+0x20];[1:7:{0}:5:1]  # req={0} waits SB0
#                                                     # (descriptor), wr=1 result
#   IADD3  R22, R20, RZ, RZ;[7:7:{1}:5:1]    # first use of R20 waits SB1
#   STG.E  desc[{UR4,UR5}][{R6,R7}], R22;[0:1:{0}:1:0]
# ---------------------------------------------------------------------------

FIVE = 0x40A00000   # 5.0


def build():
    lines = ["#fn ldg_test(out<1024>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",   # desc policy, wr=SB0
             "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]",
             "    LDG.E R20, desc[{UR4,UR5}][{R6,R7}+0x20];[1:7:{0}:5:1]",  # wait SB0, wr=SB1
             "    IADD3 R22, R20, RZ, RZ;[7:7:{1}:5:1]",       # first use waits SB1
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R22;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))


print("=== hand-built ELF LDG, scoreboard-corrected ===")
cubin = build()
open("x.cubin", "wb").write(cubin)
mod = CudaModule(cubin)
d = mod.devmem_alloc(64)
mod.device_write(d, struct.pack("<16I", *([0] * 8 + [FIVE] + [0] * 7)))  # out[8] = 5.0
mod.launch("ldg_test", grid=(1,), block=(1,), args=[d])
mod.synchronize()
v = struct.unpack("<I", mod.device_read(d, 4))[0]
mod.devmem_free(d)
f = struct.unpack("<f", struct.pack("<I", v))[0]
print(f"loaded {f} (expect 5.0)")
assert f == 5.0, "LDG round-trip mismatch"
print("=== ALL OK: LDG reads out[8] = 5.0 ===")
print("Key: LDG must wait (req) on the LDCU.64 UR4 descriptor scoreboard")
print("before using desc[{UR4,UR5}]; plus a result scoreboard (wr) consumed by the")
print("first user of the loaded register.")
