import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
import struct
import ctypes

cubin = assemble('''
#fn imad_test(out<48>) {
    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]

    // === 1: LO RRR — 5*10+100 = 150 ===
    MOV32I R0, 0x00000005;[7:7:{}:5:1]
    MOV32I R1, 0x0000000A;[7:7:{}:5:1]
    MOV32I R2, 0x00000064;[7:7:{}:5:1]
    IMAD R3, R0, R1, R2;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}], R3;[7:1:{0}:1:0]

    // === 2: LO negate Rc — 5*10 + (-100) = -50 (0xFFFFFFCE) ===
    IMAD R3, R0, R1, -R2;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R3;[7:1:{0}:1:0]

    // === 3: LO overflow — 0x80000000*2+1 = 1 (low32) ===
    MOV32I R2, 0x80000000;[7:7:{}:5:1]
    MOV32I R4, 0x00000002;[7:7:{}:5:1]
    MOV32I R5, 0x00000001;[7:7:{}:5:1]
    IMAD R3, R2, R4, R5;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R3;[7:1:{0}:1:0]

    // === 4: LO S32 — (-5)*10+100 = 50 ===
    MOV32I R2, 0xFFFFFFFB;[7:7:{}:5:1]
    MOV32I R5, 0x00000064;[7:7:{}:5:1]
    IMAD.S32 R3, R2, R1, R5;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R3;[7:1:{0}:1:0]

    // === 5: LO immediate Sb (RsIR) — 5*0xA+100 = 150 ===
    MOV32I R0, 0x00000005;[7:7:{}:5:1]
    MOV32I R2, 0x00000064;[7:7:{}:5:1]
    IMAD R3, R0, 0xA, R2;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R3;[7:1:{0}:1:0]

    // === 6: LO immediate Rc (RRsI) — 5*10+200 = 250 ===
    MOV32I R0, 0x00000005;[7:7:{}:5:1]
    MOV32I R1, 0x0000000A;[7:7:{}:5:1]
    IMAD R3, R0, R1, 200;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R3;[7:1:{0}:1:0]

    // === 7: WIDE.U32 — 0x12345678 * 0x9ABCDEF0 ===
    MOV32I R0, 0x12345678;[7:7:{}:5:1]
    MOV32I R1, 0x9ABCDEF0;[7:7:{}:5:1]
    IMAD.WIDE.U32 {R4,R5}, R0, R1, {RZ,RZ};[7:7:{2}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R4;[7:1:{0}:1:0]

    // === 8: WIDE signed (S32) — 0x80000000 * 2 ===
    MOV32I R0, 0x80000000;[7:7:{}:5:1]
    MOV32I R1, 0x00000002;[7:7:{}:5:1]
    IMAD.WIDE {R4,R5}, R0, R1, {RZ,RZ};[7:7:{2}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x1C], R4;[7:1:{0}:1:0]

    // === 9: WIDE.U32 with Rc=1 — product + 1 ===
    MOV32I R0, 0x12345678;[7:7:{}:5:1]
    MOV32I R1, 0x9ABCDEF0;[7:7:{}:5:1]
    MOV32I R2, 0x00000001;[7:7:{}:5:1]
    MOV32I R3, 0x00000000;[7:7:{}:5:1]
    IMAD.WIDE.U32 {R4,R5}, R0, R1, {R2,R3};[7:7:{2}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R4;[7:1:{0}:1:0]

    // === 10: HI signed — high32 of s32(0x80000000)*2 ===
    MOV32I R0, 0x80000000;[7:7:{}:5:1]
    MOV32I R1, 0x00000002;[7:7:{}:5:1]
    MOV32I R2, 0x00000000;[7:7:{}:5:1]
    MOV32I R3, 0x00000000;[7:7:{}:5:1]
    IMAD.HI R4, P0, R0, R1, {R2,R3};[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x24], R4;[7:1:{0}:1:0]

    // === 11: LO Rc=RZ — 5*10+0 = 50 ===
    MOV32I R0, 0x00000005;[7:7:{}:5:1]
    MOV32I R1, 0x0000000A;[7:7:{}:5:1]
    IMAD R3, R0, R1, RZ;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x28], R3;[7:1:{0}:1:0]

    EXIT;[7:7:{}:5:0]
}
''')

Path('x.cubin').write_bytes(cubin)

mod = CudaModule(cubin)
d = mod.devmem_alloc(48)
mod.launch("imad_test", grid=1, block=1, args=[d])
mod.synchronize()
vals = struct.unpack("<12I", mod.device_read(d, 48))

print("=== IMAD Semantic Verification (SM120) ===")
print()

ok = True

# [1] LO RRR — 5*10+100=150
r = vals[0]; e = 5*10+100; ok &= r==e
print(f"[1] LO RRR:       IMAD R3, R0(5), R1(10), R2(100)")
print(f"    got {r}, expected {e}  {'OK' if r==e else 'FAIL'}")

# [2] LO negate — 5*10+(-100) = -50
r = ctypes.c_int32(vals[1]).value; e = 5*10 + (-100); ok &= r==e
print(f"[2] LO negate:    IMAD R3, R0(5), R1(10), -R2(100)")
print(f"    got {r}, expected {e}  {'OK' if r==e else 'FAIL'}")

# [3] LO overflow
r = vals[2]; e = (0x80000000*2 + 1) & 0xFFFFFFFF; ok &= r==e
print(f"[3] LO overflow:  IMAD R3, R2(0x80000000), R4(2), R5(1)")
print(f"    got 0x{r:08x}, expected 0x{e:08x}  {'OK' if r==e else 'FAIL'}")

# [4] LO S32
r = vals[3]; e = ((-5)*10 + 100) & 0xFFFFFFFF; ok &= r==e
print(f"[4] LO S32:       IMAD.S32 R3, R2(-5), R1(10), R5(100)")
print(f"    got 0x{r:08x}, expected 0x{e:08x}  {'OK' if r==e else 'FAIL'}")

# [5] LO imm Sb
r = vals[4]; e = 5*0xA + 100; ok &= r==e
print(f"[5] LO imm Sb:    IMAD R3, R0(5), 0xA, R2(100)")
print(f"    got {r}, expected {e}  {'OK' if r==e else 'FAIL'}")

# [6] LO imm Rc
r = vals[5]; e = 5*10 + 200; ok &= r==e
print(f"[6] LO imm Rc:    IMAD R3, R0(5), R1(10), 200")
print(f"    got {r}, expected {e}  {'OK' if r==e else 'FAIL'}")

# [7] WIDE.U32
r = vals[6]; e = 0x242D2080; ok &= r==e
full7 = (0x12345678 * 0x9ABCDEF0) & 0xFFFFFFFFFFFFFFFF
print(f"[7] WIDE.U32:     IMAD.WIDE.U32 {{R4,R5}}, R0(0x12345678), R1(0x9ABCDEF0), RZ")
print(f"    lo=0x{r:08x}, expected full=0x{full7:016x}  {'OK' if full7 & 0xFFFFFFFF == r else 'FAIL'}")

# [8] WIDE signed
r_lo = vals[7]
a8 = ctypes.c_int32(0x80000000).value
full8 = (a8 * 2) & 0xFFFFFFFFFFFFFFFF
r8_full = ctypes.c_int32(vals[7]).value | (0 if True else 0)  # just check low
ok &= r_lo == (full8 & 0xFFFFFFFF)
print(f"[8] WIDE S32:     IMAD.WIDE {{R4,R5}}, R0(0x80000000), R1(2), RZ")
print(f"    lo=0x{r_lo:08x}, expected lo=0x{full8 & 0xFFFFFFFF:08x}")
print(f"    (signed: {a8}*2 = {a8*2} = 0x{full8:016x})  {'OK' if r_lo == (full8 & 0xFFFFFFFF) else 'FAIL'}")

# [9] WIDE.U32 + 1
r_lo = vals[8]
full9 = (0x12345678 * 0x9ABCDEF0 + 1) & 0xFFFFFFFFFFFFFFFF
ok &= r_lo == (full9 & 0xFFFFFFFF)
print(f"[9] WIDE.U32+1:   IMAD.WIDE.U32 {{R4,R5}}, R0, R1, R2(1)")
print(f"    lo=0x{r_lo:08x}, expected lo=0x{full9 & 0xFFFFFFFF:08x}  {'OK' if r_lo == (full9 & 0xFFFFFFFF) else 'FAIL'}")

# [10] HI signed
r = vals[9]
a10 = ctypes.c_int32(0x80000000).value
e10 = ((a10 * 2) >> 32) & 0xFFFFFFFF
ok &= r == e10
print(f"[10] HI S32:      IMAD.HI R4, P0, R0(0x80000000), R1(2), R2(0)")
print(f"    got 0x{r:08x}, expected hi32(s32*2) = 0x{e10:08x}  {'OK' if r==e10 else 'FAIL'}")

# [11] LO RZ
r = vals[10]; e = 5*10; ok &= r==e
print(f"[11] LO RZ:       IMAD R3, R0(5), R1(10), RZ")
print(f"    got {r}, expected {e}  {'OK' if r==e else 'FAIL'}")

print()
print(f"=== {'ALL OK' if ok else 'SOME FAILED'} ===")

mod.devmem_free(d)
