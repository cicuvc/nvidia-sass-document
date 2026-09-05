"""ACQSHMINIT encoding and safe sm_120 execution checks."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402
from assembler.sass_matcher import MatchError  # noqa: E402


REF = [
    (0x0000000000007877, 0x000fe20000000000),
    (0x0000000000000877, 0x000fca0000000000),
    (0x0000000000009877, 0x021fd00000000000),
    (0x000000000000f877, 0x000fe20000000000),
]

SOURCE = """ACQSHMINIT;[7:7:{}:1:0]
@P0 ACQSHMINIT;[7:7:{}:5:1]
@!P1 ACQSHMINIT;[7:7:{0,5}:8:1]
@!PT ACQSHMINIT;[7:7:{}:1:0]"""

ok = True


def check(name, condition, detail=""):
    global ok
    ok &= condition
    print(f"{'ok ' if condition else 'FAIL'} {name:<42} {detail}")


got = assemble_flat(SOURCE, arch="sm120")
check("sm120 encoding", got == REF, repr(got))

try:
    assemble_flat("ACQSHMINIT;[7:7:{}:1:0]", arch="sm90")
    rejected = False
except MatchError:
    rejected = True
check("sm90 rejects absent opcode", rejected)

KERNEL = """#fn k(out<8>) {
 #pragma SHARED(1024)
 LDCU.64 {UR10,UR11}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
 LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
 S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]
 UMOV UR4, 0x400;[7:7:{}:2:0]
 ULEA UR4, UR5, UR4, 0x18;[7:7:{2}:5:1]
 MOV32I R0, 0xdeadbeef;[7:7:{}:5:1]
 STS [UR4], R0;[7:7:{}:4:0]
 BAR.SYNC 0;[7:7:{}:5:1]
 UMOV UR6, 1;[7:7:{}:5:1]
 UMEMSETS.64 [UR4], URZ, UR6;[7:7:{}:1:0]
 ACQSHMINIT;[7:7:{}:1:0]
 LDS R5, [UR4];[3:7:{}:1:0]
 STG.E desc[{UR10,UR11}][{R2,R3}], R5;[7:7:{0,1,3}:1:0]
 EXIT;[7:7:{}:5:0]
}"""

IDLE = """#fn idle() {
 ACQSHMINIT;[7:7:{}:1:0]
 @!PT ACQSHMINIT;[7:7:{}:1:0]
 EXIT;[7:7:{}:5:0]
}"""

try:
    idle = CudaModule(assemble(IDLE))
except RuntimeError as exc:
    print(f"skip GPU checks (no CUDA driver/GPU): {exc}")
    sys.exit(0 if ok else 1)

idle.launch("idle", grid=(1,), block=(32,), args=[])
idle.synchronize()
check("idle release state returns", True)

mod = CudaModule(assemble(KERNEL))
dev = mod.devmem_alloc(4)
mod.device_write(dev, b"\xff" * 4)
mod.launch("k", grid=(1,), block=(32,), args=[dev])
mod.synchronize()
value = struct.unpack("<I", mod.device_read(dev, 4))[0]
check("UMEMSETS -> ACQSHMINIT smoke", value == 0, hex(value))
mod.devmem_free(dev)

print(f"\n=== ACQSHMINIT: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
