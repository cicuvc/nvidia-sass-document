import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# VIMNMX — Vector Integer Min/Max on int_pipe (verified SM120, RTX 5090)
#
# sm_120 form:  VIMNMX[.U32|.S32|.U16x2|.S16x2|.U8x4|.S8x4][.RELU] Rd, Ra, Rb|imm|URb, [!]Pp
#   PT / !PT   -> min / max   (the ONLY form ptxas emits: `min` -> PT, `max` -> !PT)
#   .RELU      -> clamp result to >= 0 (signed fmt only; guarded by CONDITIONS)
#
# Silicon finding (probed on RTX 5090): with a real destination predicate
# P0..P6 the min/max SENSE FLIPS — P0..P6 compute MAX, !P0..!P6 compute MIN —
# and the predicate is NOT written (a pre-set P0 stays unchanged).  The
# predicate-output capability lives in the 6-operand vimnmx_pred_* form
# (sm_90 spec; sm_120 VIMNMX exposes only the 4-operand form).  Real code
# therefore always uses PT/!PT, exactly as ptxas does.
#
# Encodings (opcode 0x248 RRR / 0x848 RIR / 0x1c48 RUR):
#   Pp -> bits [89:87], Pp@not -> bit [90]; relu -> bit [76]; fmt -> bits [74:72].
# ---------------------------------------------------------------------------

# ptxas reference (sm_120, CUDA 12.8): VIMNMX.S32 R9, R2, R5, PT/!PT with
# &req={2} ?WAIT5_END_GROUP  ->  bracket [7:7:{2}:5:1].
REF_PT  = (0x0000000502097248, 0x004fca0003fe0100)  # S32 min
REF_NPT = (0x0000000502097248, 0x004fca0007fe0100)  # S32 max

got_pt = assemble_flat("VIMNMX.S32 R9, R2, R5, PT;[7:7:{2}:5:1]")[0]
got_npt = assemble_flat("VIMNMX.S32 R9, R2, R5, !PT;[7:7:{2}:5:1]")[0]
ok = True
for name, got, ref in (("PT (min) ", got_pt, REF_PT), ("!PT (max)", got_npt, REF_NPT)):
    good = got == ref
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes {name} lo={got[0]:016x} hi={got[1]:016x} (ptxas match)")

# ---------------------------------------------------------------------------
# GPU semantic battery
# ---------------------------------------------------------------------------
src = """#fn k(out<128>) {
    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]

    // [0x00/0x04] U32 min/max: 10 vs 20
    MOV32I R0, 0x0000000A;[7:7:{}:5:1]
    MOV32I R1, 0x00000014;[7:7:{}:5:1]
    VIMNMX.U32 R2, R0, R1, PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[7:1:{0}:1:0]
    VIMNMX.U32 R2, R0, R1, !PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R2;[7:1:{0}:1:0]

    // [0x08/0x0C] S32 with negatives: -5 vs 3
    MOV32I R0, 0xFFFFFFFB;[7:7:{}:5:1]
    MOV32I R1, 0x00000003;[7:7:{}:5:1]
    VIMNMX.S32 R2, R0, R1, PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R2;[7:1:{0}:1:0]
    VIMNMX.S32 R2, R0, R1, !PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R2;[7:1:{0}:1:0]

    // [0x10/0x14] RELU: min(-5,3) clamps to 0; min(3,4) stays 3
    VIMNMX.S32.RELU R2, R0, R1, PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R2;[7:1:{0}:1:0]
    MOV32I R0, 0x00000003;[7:7:{}:5:1]
    MOV32I R1, 0x00000004;[7:7:{}:5:1]
    VIMNMX.S32.RELU R2, R0, R1, PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R2;[7:1:{0}:1:0]

    // [0x18/0x1C] direction flip for real predicates: P0=max, !P0=min (3 vs 4)
    MOV32I R0, 0x00000003;[7:7:{}:5:1]
    MOV32I R1, 0x00000004;[7:7:{}:5:1]
    VIMNMX.U32 R2, R0, R1, P0;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R2;[7:1:{0}:1:0]
    VIMNMX.U32 R2, R0, R1, !P0;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x1C], R2;[7:1:{0}:1:0]
    VIMNMX.U32 R2, R0, R1, P6;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R2;[7:1:{0}:1:0]
    VIMNMX.U32 R2, R0, R1, !P6;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x24], R2;[7:1:{0}:1:0]

    // [0x28/0x2C] RIR immediate: 3 vs 5
    MOV32I R0, 0x00000003;[7:7:{}:5:1]
    VIMNMX.U32 R2, R0, 0x5, PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x28], R2;[7:1:{0}:1:0]
    VIMNMX.U32 R2, R0, 0x5, !PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x2C], R2;[7:1:{0}:1:0]

    // [0x30/0x34] U16x2 packed min/max: {5,3} vs {4,6}
    MOV32I R0, 0x00050003;[7:7:{}:5:1]
    MOV32I R1, 0x00040006;[7:7:{}:5:1]
    VIMNMX.U16x2 R2, R0, R1, PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x30], R2;[7:1:{0}:1:0]
    VIMNMX.U16x2 R2, R0, R1, !PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x34], R2;[7:1:{0}:1:0]

    // [0x38] P0 NOT written by 4-op form: pre-set P0=1, VIMNMX ...,P0, store marker
    ISETP.T P0, RZ, RZ;[7:7:{}:5:1]
    VIMNMX.U32 R2, R0, R1, P0;[7:7:{}:13:1]
    IADD3 R9, R9, RZ, RZ;[7:7:{}:5:1]
    IADD3 R9, R9, RZ, RZ;[7:7:{}:5:1]
    IADD3 R9, R9, RZ, RZ;[7:7:{}:5:1]
    IADD3 R9, R9, RZ, RZ;[7:7:{}:5:1]
    @P0 MOV32I R3, 0x11111111;[7:7:{}:5:1]
    @!P0 MOV32I R3, 0x22222222;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x38], R3;[7:1:{0}:1:0]

    EXIT;[7:7:{}:5:0]
}"""

try:
    mod = CudaModule(assemble(src))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

d = mod.devmem_alloc(256)
mod.device_write(d, bytes(256))
mod.launch("k", grid=(1,), block=(1,), args=[d])
mod.synchronize()
v = struct.unpack("<15I", mod.device_read(d, 15 * 4))
mod.devmem_free(d)

EXPECT = [
    0x0000000A,   # U32 min (10)
    0x00000014,   # U32 max (20)
    0xFFFFFFFB,   # S32 min (-5)
    0x00000003,   # S32 max (3)
    0x00000000,   # RELU min(-5,3) -> 0
    0x00000003,   # RELU min(3,4) -> 3
    0x00000004,   # P0  (real pred, not=0) -> MAX
    0x00000003,   # !P0 (real pred, not=1) -> MIN
    0x00000004,   # P6  -> MAX
    0x00000003,   # !P6 -> MIN
    0x00000003,   # RIR min(3,5)
    0x00000005,   # RIR max(3,5)
    0x00040003,   # U16x2 min {4,3}
    0x00050006,   # U16x2 max {5,6}
    0x11111111,   # P0 still 1 after VIMNMX ..., P0 (not written)
]
labels = ["U32 min", "U32 max", "S32 min", "S32 max", "RELU neg->0", "RELU pos",
          "P0 -> max", "!P0 -> min", "P6 -> max", "!P6 -> min",
          "RIR min", "RIR max", "U16x2 min", "U16x2 max", "P0 unwritten"]
for i, (got, want, lab) in enumerate(zip(v, EXPECT, labels)):
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} [{i:2d}] {lab:14s} = 0x{got:08X} (exp 0x{want:08X})")

print("\n=== VIMNMX semantic verification: ALL OK ===" if ok else "\n=== VIMNMX FAILURES ===")
sys.exit(0 if ok else 1)
