import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
import struct
import ctypes

# IMAD.X — extended-precision multiply-add with carry chain.
# Semantics (from notes/sm90/instr/imad.md):
#   IMAD.X  Rd, Ra, Rb, [~]Rc, [!]Pp
#   Rd = low32(Ra × Rb + Rc) + carry_in;  Pp = carry_out
#
# Status (SM120 / RTX 5090):
#   - IMAD.X / IMAD.WIDE.X / IMAD.HI.X *do* execute on the GPU.
#   - FIXED: `~Rc` (one's-complement invert of Rc) was not encoded by the
#     assembler — bit [75] (Rc@invert) was always 0. The lexer silently dropped
#     the `~` token and the encoder had no `@invert` branch. Both fixed.
#   - FIXED: R14+ as any operand faulted with CUDA_ERROR_ILLEGAL_INSTRUCTION.
#     Root cause was in sass_elf.py: EIATTR func_sym was hardcoded to 6 (a
#     ptxas symbol ordering) but our kernel function is symbol 5, so the device
#     REGCOUNT EIATTR pointed at .nv.constant0 and the driver defaulted to a
#     tiny register file. Also fixed _compute_regcount reading MOV32I immediate
#     bits as registers. R13-R200 now work (R254 is spec-illegal).
#   - Semantics verified: IMAD.X Rd, Ra, Rb, ~Rc, Pp computes
#     Rd = low32(Ra*Rb + ~Rc);  Pp = carry-out.
#   - ptxas never emits the X form on sm_120; it uses IMAD.WIDE.U32 +
#     IADD3.X carry chains instead.

# IMAD.X without carry-in: Rd = low32(Ra*Rb + Rc), same as IMAD LO but with
# output predicate P0 capturing the carry-out bit.
src = '''
#fn imad_x_test(out<16>) {
    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]

    // [1] IMAD.X no invert: 0xFFFFFFFF*0xFFFFFFFF + 1
    //     lo32 = 0xFFFFFFFE00000001 + 1 = 0xFFFFFFFE00000002 -> lo = 2
    MOV32I R0, 0xFFFFFFFF;[7:7:{}:5:1]
    MOV32I R1, 0xFFFFFFFF;[7:7:{}:5:1]
    MOV32I R2, 0x00000001;[7:7:{}:5:1]
    IMAD.X R3, R0, R1, R2, P0;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}], R3;[7:1:{0}:1:0]

    // [2] IMAD.X with ~Rc (one's complement): + ~1 = + 0xFFFFFFFE
    //     0xFFFFFFFE00000001 + 0xFFFFFFFE = 0xFFFFFFFEFFFFFFFF -> lo = 0xFFFFFFFF
    IMAD.X R3, R0, R1, ~R2, P1;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R3;[7:1:{0}:1:0]

    // [3] IMAD.WIDE.X
    MOV32I R2, 0x00000000;[7:7:{}:5:1]
    MOV32I R3, 0x00000000;[7:7:{}:5:1]
    IMAD.WIDE.X {R4,R5}, P2, R0, R1, {RZ,RZ}, P3;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R4;[7:1:{0}:1:0]

    // [4] IMAD.HI.X
    IMAD.HI.X R4, P4, R0, R1, {RZ,RZ}, P5;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R4;[7:1:{0}:1:0]

    EXIT;[7:7:{}:5:0]
}
'''

cubin = assemble(src)

Path('x.cubin').write_bytes(cubin)

# Show what cuobjdump thinks of the encodings (decode-only, no GPU)
import subprocess, tempfile, os
tmp = '/tmp/test_imad_x_dbg.cubin'
Path(tmp).write_bytes(cubin)
r = subprocess.run(['/usr/local/cuda/bin/cuobjdump', '-arch', 'sm_120', '-sass', tmp],
                   capture_output=True, text=True)
print(r.stdout)
print(r.stderr if r.stderr else "")

mod = CudaModule(cubin)
d = mod.devmem_alloc(16)
try:
    mod.launch("imad_x_test", grid=1, block=1, args=[d])
    mod.synchronize()
    vals = struct.unpack("<4I", mod.device_read(d, 16))

    print("=== IMAD.X Verification ===")
    # [1] 0xFFFFFFFF*0xFFFFFFFF + 1
    r1 = vals[0]; e1 = (0xFFFFFFFF * 0xFFFFFFFF + 1) & 0xFFFFFFFF
    print(f"[1] IMAD.X no carry:   got 0x{r1:08x} expected 0x{e1:08x}")
    # [2] with ~Rc (one's complement)
    r2 = vals[1]
    e2 = ((0xFFFFFFFF * 0xFFFFFFFF) + ((~1) & 0xFFFFFFFF)) & 0xFFFFFFFF
    print(f"[2] IMAD.X ~Rc:     got 0x{r2:08x} expected 0x{e2:08x}  {'OK' if r2==e2 else 'FAIL'}")
    # [3] WIDE.X
    r3 = vals[2]
    print(f"[3] IMAD.WIDE.X lo:    got 0x{r3:08x}")
    # [4] HI.X
    r4 = vals[3]
    print(f"[4] IMAD.HI.X:         got 0x{r4:08x}")
except Exception as e:
    print(f"LAUNCH FAILED: {e}")
finally:
    mod.devmem_free(d)
