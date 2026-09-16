import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from archutil import same_as_capture  # noqa: E402
from assembler import CudaModule, assemble, assemble_flat  # noqa: E402
from assembler.runner import reset_context  # noqa: E402

# REDUX -- warp-wide integer reduction to a uniform register.
# Direct SASS verification on sm_120 / RTX 5090.  This is the instruction
# emitted for PTX redux.sync and the __reduce_*_sync CUDA intrinsics.

REF_SM120 = [
    (0x00000000021073C4, 0x000E8A0000000000),  # AND (default), U32
    (0x00000000021073C4, 0x000E8A0000004000),  # OR
    (0x00000000021073C4, 0x000E8A0000008000),  # XOR
    (0x00000000021073C4, 0x000E8A000000C000),  # SUM
    (0x00000000021073C4, 0x000E8A0000010000),  # MIN.U32
    (0x00000000021073C4, 0x000E8A0000014000),  # MAX.U32
    (0x00000000021073C4, 0x000E8A0000010200),  # MIN.S32
    (0x00000000021073C4, 0x000E8A0000014200),  # MAX.S32
]

FORMS = [
    "REDUX UR16, R2",
    "REDUX.OR UR16, R2",
    "REDUX.XOR UR16, R2",
    "REDUX.SUM UR16, R2",
    "REDUX.MIN UR16, R2",
    "REDUX.MAX UR16, R2",
    "REDUX.MIN.S32 UR16, R2",
    "REDUX.MAX.S32 UR16, R2",
]


ok = True
flat = assemble_flat("\n".join(f"{x};[2:7:{{}}:5:1]" for x in FORMS))
pin_bytes = same_as_capture("sm120")
if not pin_bytes:
    print("info byte-exact REDUX vectors are pinned only for sm120")
for i, (name, enc) in enumerate(zip(FORMS, flat)):
    good = enc == REF_SM120[i] if pin_bytes else True
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes {name:<28} "
          f"lo={enc[0]:016x} hi={enc[1]:016x}")


def kernel(inst, value_setup, guard="", writer_lane=0):
    # REDUX is a decoupled producer.  It claims SB2 and the first consumer of
    # UR16 waits through req={2}; stall cycles alone are not used as a proxy.
    return f"""#fn redux_probe(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
    S2R R3, SR_TID.X;[0:7:{{}}:5:1]
    ISETP.EQ.AND P0, PT, R3, {writer_lane}, PT;[7:7:{{0}}:13:1]
    ISETP.GE.AND P1, PT, R3, 8, PT;[7:7:{{}}:13:1]
    {value_setup}
    {guard}{inst};[2:7:{{}}:5:1]
    MOV R20, UR16;[7:7:{{2}}:5:1]
    @P0 STG.E desc[{{UR4,UR5}}][{{R6,R7}}], R20;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, value_setup, block=32, guard="", writer_lane=0):
    reset_context()
    mod = CudaModule(assemble(kernel(inst, value_setup, guard, writer_lane)))
    out = mod.devmem_alloc(4)
    try:
        mod.device_write(out, bytes(4))
        mod.launch("redux_probe", grid=(1,), block=(block,), args=[out])
        mod.synchronize()
        return struct.unpack("<I", mod.device_read(out, 4))[0]
    finally:
        mod.devmem_free(out)


LANE_PLUS_ONE = "IADD3 R2, R3, 1, RZ;[7:7:{}:5:1]"
SIGNED_SPLIT = """IADD3 R2, R3, RZ, RZ;[7:7:{}:5:1]
    @P0 MOV32I R2, 0x80000000;[7:7:{}:5:1]"""

try:
    run("REDUX.SUM UR16, R2", LANE_PLUS_ONE)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)


def check(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name:<30} "
          f"got=0x{got:08x} want=0x{want:08x}")


# Full-warp lane values are 1..32.
checks = [
    ("AND 1..32", "REDUX UR16, R2", 0),
    ("OR 1..32", "REDUX.OR UR16, R2", 0x3F),
    ("XOR 1..32", "REDUX.XOR UR16, R2", 32),
    ("SUM 1..32", "REDUX.SUM UR16, R2", 528),
    ("MIN.U32 1..32", "REDUX.MIN UR16, R2", 1),
    ("MAX.U32 1..32", "REDUX.MAX UR16, R2", 32),
]
for label, inst, want in checks:
    check(label, run(inst, LANE_PLUS_ONE), want)

# Lane 0 contributes 0x80000000 and lanes 1..31 contribute their lane IDs.
# This makes signed and unsigned ordering produce opposite extrema.
check("MIN.U32 signed split", run("REDUX.MIN UR16, R2", SIGNED_SPLIT), 1)
check("MAX.U32 signed split", run("REDUX.MAX UR16, R2", SIGNED_SPLIT), 0x80000000)
check("MIN.S32 signed split", run("REDUX.MIN.S32 UR16, R2", SIGNED_SPLIT), 0x80000000)
check("MAX.S32 signed split", run("REDUX.MAX.S32 UR16, R2", SIGNED_SPLIT), 31)

# A short warp reduces only its live lanes.  A predicated REDUX reduces over
# the instruction's active lanes; lanes 8..31 contribute 9..32 here.
check("SUM 16 live lanes", run("REDUX.SUM UR16, R2", LANE_PLUS_ONE, block=16), 136)
check("SUM @P1 lanes 8..31",
      run("REDUX.SUM UR16, R2", LANE_PLUS_ONE, guard="@P1 ", writer_lane=8),
      492)

print("\n=== REDUX sm120 verification: ALL OK ===" if ok
      else "\n=== REDUX sm120 verification: FAILURES ===")
sys.exit(0 if ok else 1)
