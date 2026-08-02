import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
import struct
import ctypes

# LEA — Load Effective Address (shift-add).
# Semantics verified on SM120 (RTX 5090):
#   LO:  Rd = low32((Ra << N) + Rb)          ; N in 0..31
#        Pu = carry-out of the low-32 add    (fires when (Ra<<N)[31:0]+Rb >= 2^32;
#             NOT for the bits shifted out of Ra — see test [8] vs [9])
#   HI:  Rd = ((Ra << N) >> 32) + Rb + (Rc << N)   (32-bit wrapping add)
#        <-- SM120 empirical formula, verified on 27 value sets. This does NOT
#            match the sm_90 note's "high32((Ra<<N)+Rb+Rc)". Rc is shifted by N.
#   Negates: -Ra (bit [72]), -Rb (bit [63]); both together is illegal.
#
# X forms (LEA.HI.X / LEA.HI.X.SX32): supported on SM120. No-invert and
# single-invert execute; the X form adds the carry-in predicate Pp to the HI
# formula. Both `~Ra` AND `~Rb` together is an illegal encoding (spec
# CONDITIONS: Ra@invert->!Rb@invert), same as the negate-exclusivity rule.
#
# Reading predicates: P2R with stall>=4 (see notes/sm90/instr/p2r.md); we use
# SEL R, RZ, 0x1, !Px == R = (Px ? 1 : 0) for the Pu checks.

cubin = assemble('''
#fn lea_test(out<64>) {
    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]
    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]

    // === LO: Rd = low32((Ra << N) + Rb) ===
    MOV32I R0, 0x00000003;[7:7:{}:5:1]
    MOV32I R1, 0x00000005;[7:7:{}:5:1]

    // [1] (3<<4)+5 = 53
    LEA R2, R0, R1, 0x4;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}], R2;[7:1:{0}:1:0]
    // [2] (3<<0)+5 = 8
    LEA R2, R0, R1, 0x0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R2;[7:1:{0}:1:0]
    // [3] (1<<31)+2 = 0x80000002
    MOV32I R0, 0x00000001;[7:7:{}:5:1]
    MOV32I R1, 0x00000002;[7:7:{}:5:1]
    LEA R2, R0, R1, 0x1F;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R2;[7:1:{0}:1:0]
    // [4] (3<<4)+(-5) = 43
    MOV32I R0, 0x00000003;[7:7:{}:5:1]
    MOV32I R1, 0x00000005;[7:7:{}:5:1]
    LEA R2, R0, -R1, 0x4;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R2;[7:1:{0}:1:0]
    // [5] ((-3)<<4)+5 = -43 = 0xFFFFFFD5
    LEA R2, -R0, R1, 0x4;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R2;[7:1:{0}:1:0]
    // [6] LO overflow low32: (0x80000000<<1)+0 = 0x100000000 -> low32 = 0
    MOV32I R0, 0x80000000;[7:7:{}:5:1]
    MOV32I R1, 0x00000000;[7:7:{}:5:1]
    LEA R2, R0, R1, 0x1;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R2;[7:1:{0}:1:0]
    // [7] LO imm form (RuIR): (3<<4)+0x10 = 64
    MOV32I R0, 0x00000003;[7:7:{}:5:1]
    LEA R2, R0, 0x10, 0x4;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R2;[7:1:{0}:1:0]

    // === LO Pu carry: (0xFFFFFFFF + 1) -> carry 1 ===
    MOV32I R0, 0xFFFFFFFF;[7:7:{}:5:1]
    MOV32I R1, 0x00000001;[7:7:{}:5:1]
    // [8] 0xFFFFFFFF+1: Rd=0, Pu=1 (low-32 add carry)
    LEA R2, P0, R0, R1, 0x0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x1C], R2;[7:1:{0}:1:0]
    SEL R4, RZ, 0x1, !P0;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R4;[7:1:{0}:1:0]
    // [9] (0x80000000<<1)+0: Rd=0, Pu=0 (shift-out is NOT a carry)
    MOV32I R0, 0x80000000;[7:7:{}:5:1]
    MOV32I R1, 0x00000000;[7:7:{}:5:1]
    LEA R2, P0, R0, R1, 0x1;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x24], R2;[7:1:{0}:1:0]
    SEL R4, RZ, 0x1, !P0;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x28], R4;[7:1:{0}:1:0]

    // === HI: Rd = ((Ra<<N)>>32) + Rb + (Rc<<N) (SM120 empirical) ===
    // [10] (0x10000000<<4)>>32 = 1, +0 + (0<<4) = 1
    MOV32I R0, 0x10000000;[7:7:{}:5:1]
    MOV32I R1, 0x00000000;[7:7:{}:5:1]
    MOV32I R3, 0x00000000;[7:7:{}:5:1]
    LEA.HI R2, P0, R0, R1, R3, 0x4;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x2C], R2;[7:1:{0}:1:0]
    // [11] 1 + 5 + (7<<4)=112 = 118 = 0x76
    MOV32I R1, 0x00000005;[7:7:{}:5:1]
    MOV32I R3, 0x00000007;[7:7:{}:5:1]
    LEA.HI R2, P0, R0, R1, R3, 0x4;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x30], R2;[7:1:{0}:1:0]
    // [12] 0xFFFFFFFF + 1: (FF<<0)>>32=0, +1 + (0<<0) = 1
    MOV32I R0, 0xFFFFFFFF;[7:7:{}:5:1]
    MOV32I R1, 0x00000001;[7:7:{}:5:1]
    MOV32I R3, 0x00000000;[7:7:{}:5:1]
    LEA.HI R2, P0, R0, R1, R3, 0x0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x34], R2;[7:1:{0}:1:0]
    // [13] (0x80000000<<1)>>32=1, +1 + (1<<1)=2 -> 4
    MOV32I R0, 0x80000000;[7:7:{}:5:1]
    MOV32I R1, 0x00000001;[7:7:{}:5:1]
    MOV32I R3, 0x00000001;[7:7:{}:5:1]
    LEA.HI R2, P0, R0, R1, R3, 0x1;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x38], R2;[7:1:{0}:1:0]
    // [14] 0 + 0x0A + (0x0B<<2)=44 -> 54 = 0x36
    MOV32I R0, 0x20000000;[7:7:{}:5:1]
    MOV32I R1, 0x0000000A;[7:7:{}:5:1]
    MOV32I R3, 0x0000000B;[7:7:{}:5:1]
    LEA.HI R2, P0, R0, R1, R3, 0x2;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x3C], R2;[7:1:{0}:1:0]

    // === HI.X: adds carry-in Pp to the HI formula ===
    // [15] X no-invert, Pp=PT(1): (0x10000000<<4)>>32=1 + (1<<4)=16 + 1 = 18
    MOV32I R0, 0x10000000;[7:7:{}:5:1]
    MOV32I R1, 0x00000000;[7:7:{}:5:1]
    MOV32I R3, 0x00000001;[7:7:{}:5:1]
    LEA.HI.X R2, P0, R0, R1, R3, 0x4, PT;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x40], R2;[7:1:{0}:1:0]
    // [16] X no-invert, Pp=P1=0: (1<<1)>>32=0 + 0 + 0 + 0 = 0
    MOV32I R0, 0x00000001;[7:7:{}:5:1]
    MOV32I R1, 0x00000000;[7:7:{}:5:1]
    MOV32I R3, 0x00000000;[7:7:{}:5:1]
    LEA.HI.X R2, P0, R0, R1, R3, 0x1, P1;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x44], R2;[7:1:{0}:1:0]
    // [17] X single-invert ~Rb (one's complement of Rb), Pp=0:
    //     (1<<1)>>32=0 + ~0(0xFFFFFFFF) + 0 + 0 = 0xFFFFFFFF
    LEA.HI.X R2, P0, R0, ~R1, R3, 0x1, P1;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x48], R2;[7:1:{0}:1:0]
    // [18] X.SX32 no-invert, Pp=PT: same arithmetic as [15]
    MOV32I R0, 0x10000000;[7:7:{}:5:1]
    MOV32I R1, 0x00000000;[7:7:{}:5:1]
    LEA.HI.X.SX32 R2, P0, R0, R1, 0x4, PT;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4C], R2;[7:1:{0}:1:0]

    EXIT;[7:7:{}:5:0]
}
''')

Path('x.cubin').write_bytes(cubin)

mod = CudaModule(cubin)
d = mod.devmem_alloc(80)
mod.launch("lea_test", grid=1, block=1, args=[d])
mod.synchronize()
vals = struct.unpack("<20I", mod.device_read(d, 80))

print("=== LEA Semantic Verification (SM120) ===")
print()
ok = True

def check(i, name, got, exp):
    global ok
    status = "OK" if got == exp else "FAIL"
    ok &= got == exp
    print(f"[{i:2d}] {name:<38} got 0x{got:08x} expected 0x{exp:08x}  {status}")

# LO
check(1, "LO (3<<4)+5", vals[0], 53)
check(2, "LO (3<<0)+5", vals[1], 8)
check(3, "LO (1<<31)+2", vals[2], 0x80000002)
check(4, "LO (3<<4)+(-5)", vals[3], 43)
check(5, "LO ((-3)<<4)+5", vals[4], 0xFFFFFFD5)
check(6, "LO low32((0x80000000<<1)+0)", vals[5], 0)
check(7, "LO imm (3<<4)+0x10", vals[6], 64)
check(8,  "LO carry 0xFFFFFFFF+1 Rd", vals[7], 0)
check(8,  "LO carry 0xFFFFFFFF+1 Pu", vals[8], 1)
check(9,  "LO shift-out 0x80000000<<1 Rd", vals[9], 0)
check(9,  "LO shift-out 0x80000000<<1 Pu", vals[10], 0)

# HI (empirical formula: ((Ra<<N)>>32) + Rb + (Rc<<N), 32-bit wrap)
def hi_model(ra, rb, rc, n):
    return (((ra << n) >> 32) + rb + ((rc << n) & 0xFFFFFFFF)) & 0xFFFFFFFF
check(10, "HI (0x10000000<<4)>>32", vals[11], hi_model(0x10000000, 0, 0, 4))
check(11, "HI 1+5+(7<<4)", vals[12], hi_model(0x10000000, 5, 7, 4))
check(12, "HI 0xFFFFFFFF+1", vals[13], hi_model(0xFFFFFFFF, 1, 0, 0))
check(13, "HI (0x80000000<<1)>>32+1+(1<<1)", vals[14], hi_model(0x80000000, 1, 1, 1))
check(14, "HI (0x20000000<<2)>>32+0xA+(0xB<<2)", vals[15], hi_model(0x20000000, 0xA, 0xB, 2))

# HI.X (adds Pp carry-in)
check(15, "HI.X Pp=PT (1+16+1)", vals[16], 18)
check(16, "HI.X Pp=P1=0 (0+0+0)", vals[17], 0)
check(17, "HI.X ~Rb Pp=0 (0+0xFFFFFFFF)", vals[18], 0xFFFFFFFF)

print()
print(f"=== {'ALL OK' if ok else 'SOME FAILED'} ===")
print("Note: LEA.HI on SM120 = ((Ra<<N)>>32)+Rb+(Rc<<N); X form adds Pp;")
print("      both ~Ra+~Rb together is illegal (spec CONDITIONS).")

mod.devmem_free(d)
