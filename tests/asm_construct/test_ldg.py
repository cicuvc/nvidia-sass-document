import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from archutil import adapt_source  # noqa: E402
from archutil import adapt_source  # noqa: E402

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
#   LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]   # wr=0 -> sets SB0
#   LDG.E  R20, desc[{UR4,UR5}][{R6,R7}+0x20];[1:7:{0}:5:1]  # req={0} waits SB0
#                                                     # (descriptor), wr=1 result
#   IADD3  R22, R20, RZ, RZ;[7:7:{1}:5:1]    # first use of R20 waits SB1
#   STG.E  desc[{UR4,UR5}][{R6,R7}], R22;[0:1:{0}:1:0]
# ---------------------------------------------------------------------------

FIVE = 0x40A00000   # 5.0


# Canonical template (empirically the only shape that is stable on H20):
#   * every purpose gets its own pointer parameter (in != out),
#   * ALL const-bank loads happen up-front, before the first desc[] consumer,
#   * the load-base register pair is NOT reused as a later store target.
def build():
    # Brackets are byte-for-byte those of the green /tmp/decide.py "D" probe.
    lines = ["#fn ldg_test(out<8>, in<8>) {",
             "    LDC.64 {R6, R7}, #param(in);[1:7:{}:1:0]",
             "    LDC.64 {R2, R3}, #param(out);[1:7:{}:1:0]",
             "    ULDC.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[7:7:{}:3:1]",
             "    LDG.E R20, desc[{UR4,UR5}][{R6,R7}+0x20];[1:7:{1}:5:1]",
             "    IADD3 R21, R20, RZ, RZ;[7:7:{1}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R2,R3}+0x0], R21;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble(adapt_source("\n".join(lines)))


print("=== hand-built ELF LDG, H20-canonical template ===")
cubin = build()
open("x.cubin", "wb").write(cubin)
mod = CudaModule(cubin)
d_in = mod.devmem_alloc(64)
d_out = mod.devmem_alloc(64)
mod.device_write(d_in, struct.pack("<16I", *([0] * 8 + [FIVE] + [0] * 7)))   # in[8] = 5.0
mod.device_write(d_out, b"\x00" * 64)
mod.launch("ldg_test", grid=(1,), block=(1,), args=[d_out, d_in])
mod.synchronize()
v = struct.unpack("<I", mod.device_read(d_out, 4))[0]
f = struct.unpack("<f", struct.pack("<I", v))[0]
good = f == 5.0
print(f"{'ok ' if good else 'FAIL'} loaded {f} (expect 5.0)")
import sys as _s
_s.exit(0 if good else 1)

f = struct.unpack("<f", struct.pack("<I", v))[0]
print(f"loaded {f} (expect 5.0)")
assert f == 5.0, "LDG round-trip mismatch"
print("=== ALL OK: LDG reads out[8] = 5.0 ===")
print("Key: LDG must wait (req) on the LDCU.64 UR4 descriptor scoreboard")
print("before using desc[{UR4,UR5}]; plus a result scoreboard (wr) consumed by the")
print("first user of the loaded register.")
