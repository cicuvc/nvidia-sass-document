import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
import struct

# LOP3 — Three-Input Arbitrary Logic (LUT).
# Semantics verified on SM120 (RTX 5090):
#   Rd = LUT(Ra, Rb, Rc)                     bitwise, per-bit truth table
#   Pu = (Rd != 0) LOP_POP Pp                predicate output:
#                                             POR -> Pu = (Rd!=0) OR Pp
#                                             PAND -> Pu = (Rd!=0) AND Pp
#   Pu_old is NOT accumulated (contrary to the "accumulator" wording in
#   notes/sm90/instr/lop3.md — Pu is a pure output of (Rd!=0) and Pp).
#
# LUT truth-table bit index: idx = (A<<2)|(B<<1)|C, bit idx of imm8.
# Reading predicates: P2R reads the predicate file too early in a back-to-back
# burst (stale) UNLESS given a sufficient stall; stall>=4 works on SM120
# (avoid stall=12/yield=0, usched=28 boundary). We use stall=8.
#   P2R R, PR, RZ, 0x7f; [7:7:{1}:8:0]

def lut32(lut, a, b, c):
    res = 0
    for bit in range(32):
        idx = ((a >> bit) & 1) << 2 | ((b >> bit) & 1) << 1 | ((c >> bit) & 1)
        if (lut >> idx) & 1:
            res |= 1 << bit
    return res

cubin = assemble('''
#fn lop3_test(out<64>) {
    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]

    // === LUT truth-table: A=0x0F, B=0x33, C=0x55 ===
    MOV32I R0, 0x0000000F;[7:7:{}:5:1]
    MOV32I R1, 0x00000033;[7:7:{}:5:1]
    MOV32I R2, 0x00000055;[7:7:{}:5:1]

    LOP3.LUT R3, R0, R1, R2, 0x80, !PT;[7:7:{}:5:1]   // A&B&C
    STG.E desc[{UR4,UR5}][{R6,R7}], R3;[7:1:{0}:1:0]
    LOP3.LUT R3, R0, R1, R2, 0xFE, !PT;[7:7:{}:5:1]   // A|B|C
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R3;[7:1:{0}:1:0]
    LOP3.LUT R3, R0, R1, R2, 0x96, !PT;[7:7:{}:5:1]   // A^B^C
    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R3;[7:1:{0}:1:0]
    LOP3.LUT R3, R0, R1, R2, 0xE8, !PT;[7:7:{}:5:1]   // A | (B & ~C)
    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R3;[7:1:{0}:1:0]
    LOP3.LUT R3, R0, R1, R2, 0xCA, !PT;[7:7:{}:5:1]   // (A&B)|(C&~(A&B)) majority
    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R3;[7:1:{0}:1:0]

    // 2-input with C=RZ
    LOP3.LUT R3, R0, R1, RZ, 0xC0, !PT;[7:7:{}:5:1]   // A&B
    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R3;[7:1:{0}:1:0]
    LOP3.LUT R3, R0, R1, RZ, 0x0C, !PT;[7:7:{}:5:1]   // A & ~B
    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R3;[7:1:{0}:1:0]
    LOP3.LUT R3, RZ, R1, RZ, 0x33, !PT;[7:7:{}:5:1]   // ~B
    STG.E desc[{UR4,UR5}][{R6,R7}+0x1C], R3;[7:1:{0}:1:0]
    LOP3.LUT R3, R0, RZ, RZ, 0x55, !PT;[7:7:{}:5:1]   // ~A
    STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R3;[7:1:{0}:1:0]

    // mux: (A & m) | (B & ~m) with m=C
    LOP3.LUT R3, R0, R1, R2, 0xB8, !PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x24], R3;[7:1:{0}:1:0]

    // === Named ops ===
    LOP3.AND R3, R0, R1, R2, !PT;[7:7:{}:5:1]         // A&B&C
    STG.E desc[{UR4,UR5}][{R6,R7}+0x28], R3;[7:1:{0}:1:0]
    LOP3.OR  R3, R0, R1, R2, !PT;[7:7:{}:5:1]         // A|B|C
    STG.E desc[{UR4,UR5}][{R6,R7}+0x2C], R3;[7:1:{0}:1:0]
    LOP3.XOR R3, R0, R1, R2, !PT;[7:7:{}:5:1]         // A^B^C
    STG.E desc[{UR4,UR5}][{R6,R7}+0x30], R3;[7:1:{0}:1:0]
    LOP3.PASS_B R3, R0, R1, R2, !PT;[7:7:{}:5:1]      // B
    STG.E desc[{UR4,UR5}][{R6,R7}+0x34], R3;[7:1:{0}:1:0]

    // === Immediate operand (RuIR): A | 0xFF ===
    MOV32I R0, 0x0000000F;[7:7:{}:5:1]
    MOV32I R2, 0x00000000;[7:7:{}:5:1]
    LOP3.LUT R3, R0, 0xFF, R2, 0xFE, !PT;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x38], R3;[7:1:{0}:1:0]

    // === Uniform register operand (RUR) — covered in test_ulop3.py ===

    // === Pu output: POR/PAND with (Rd != 0) ===
    // A&B&C with A=0x0F,B=0x33,C=0x55 -> Rd = 0x01 (nonzero)
    MOV32I R0, 0x0000000F;[7:7:{}:5:1]
    MOV32I R1, 0x00000033;[7:7:{}:5:1]
    MOV32I R2, 0x00000055;[7:7:{}:5:1]

    // POR, Pp=!PT(0): Pu = 1 OR 0 = 1
    LOP3.LUT.POR P1, R3, R0, R1, R2, 0x80, !PT;[7:7:{}:5:1]
    P2R R4, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x40], R4;[7:1:{0}:1:0]

    // PAND, Pp=!PT(0): Pu = 1 AND 0 = 0
    LOP3.LUT.PAND P1, R3, R0, R1, R2, 0x80, !PT;[7:7:{}:5:1]
    P2R R4, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x44], R4;[7:1:{0}:1:0]

    // PAND, Pp=P0(1): Pu = 1 AND 1 = 1
    ISETP.T P0, RZ, RZ;[7:7:{}:5:1]
    LOP3.LUT.PAND P1, R3, R0, R1, R2, 0x80, P0;[7:7:{}:5:1]
    P2R R4, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x48], R4;[7:1:{0}:1:0]

    // PAND, Pp=P0(1) with zero result: A=0x0F,B=0x30,C=0x00 -> Rd = 0
    MOV32I R1, 0x00000030;[7:7:{}:5:1]
    MOV32I R2, 0x00000000;[7:7:{}:5:1]
    ISETP.T P0, RZ, RZ;[7:7:{}:5:1]
    LOP3.LUT.PAND P1, R3, R0, R1, R2, 0x80, P0;[7:7:{}:5:1]
    P2R R4, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4C], R4;[7:1:{0}:1:0]

    EXIT;[7:7:{}:5:0]
}
''')

Path('x.cubin').write_bytes(cubin)

mod = CudaModule(cubin)
d = mod.devmem_alloc(96)
mod.launch("lop3_test", grid=1, block=1, args=[d])
mod.synchronize()
vals = struct.unpack("<24I", mod.device_read(d, 96))

A, B, C = 0x0F, 0x33, 0x55
Z = 0

print("=== LOP3 Semantic Verification (SM120) ===")
print()
ok = True

# [1]-[9] LUT truth table
lut_cases = [
    ("A&B&C        LUT 0x80", 0x80, A, B, C),
    ("A|B|C        LUT 0xFE", 0xFE, A, B, C),
    ("A^B^C        LUT 0x96", 0x96, A, B, C),
    ("A|(B&~C)     LUT 0xE8", 0xE8, A, B, C),
    ("majority     LUT 0xCA", 0xCA, A, B, C),
    ("A&B (C=RZ)   LUT 0xC0", 0xC0, A, B, Z),
    ("A&~B (C=RZ)  LUT 0x0C", 0x0C, A, B, Z),
    ("~B (A,C=RZ)  LUT 0x33", 0x33, Z, B, Z),
    ("~A (B,C=RZ)  LUT 0x55", 0x55, A, Z, Z),
]
for i, (name, lut, a, b, c) in enumerate(lut_cases):
    got = vals[i]
    exp = lut32(lut, a, b, c)
    status = "OK" if got == exp else "FAIL"
    ok &= got == exp
    print(f"[{i+1:2d}] {name:<20} got 0x{got:08x} expected 0x{exp:08x}  {status}")

# [10] mux
got = vals[9]
exp = lut32(0xB8, A, B, C)
status = "OK" if got == exp else "FAIL"; ok &= got == exp
print(f"[10] mux (A&C)|(B&~C) LUT 0xB8  got 0x{got:08x} expected 0x{exp:08x}  {status}")

# [11]-[14] named ops
named = [
    ("LOP3.AND", 0x80),
    ("LOP3.OR ", 0xFE),
    ("LOP3.XOR", 0x96),
    ("LOP3.PASS_B", 0xCC),   # B pass-through: LUT = B selector = 0b11001100
]
for i, (name, lut) in enumerate(named):
    got = vals[10 + i]
    exp = lut32(lut, A, B, C)
    status = "OK" if got == exp else "FAIL"; ok &= got == exp
    print(f"[{11+i:2d}] {name:<14} got 0x{got:08x} expected 0x{exp:08x}  {status}")

# [15] immediate form
got = vals[14]
exp = lut32(0xFE, 0x0F, 0xFF, 0)   # A | 0xFF
status = "OK" if got == exp else "FAIL"; ok &= got == exp
print(f"[15] imm form A|0xFF     got 0x{got:08x} expected 0x{exp:08x}  {status}")

# [16]-[19] Pu output
pu_cases = [
    ("POR Pp=!PT (Rd!=0)", 1),
    ("PAND Pp=!PT (Rd!=0)", 0),
    ("PAND Pp=P0=1 (Rd!=0)", 1),
    ("PAND Pp=P0=1 (Rd==0)", 0),
]
for i, (name, exp) in enumerate(pu_cases):
    got = (vals[16 + i] >> 1) & 1
    status = "OK" if got == exp else "FAIL"; ok &= got == exp
    print(f"[{16+i:2d}] Pu {name:<24} Pu={got} (expected {exp})  {status}")

print()
print(f"=== {'ALL OK' if ok else 'SOME FAILED'} ===")
print("Key finding: Pu = (Rd != 0) LOP_POP Pp; Pu_old is not accumulated.")

mod.devmem_free(d)
