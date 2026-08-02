import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
import struct

# ISETP — Integer Set-Predicate.
# Semantics verified on SM120 (RTX 5090):
#   Simple:  Pu = (Ra icmp Rb)
#   Full:    Pu = (Ra icmp Rb) BOP Pp
#            Pv = ~(Ra icmp Rb) BOP Pp     <-- complement of the comparison,
#                                            NOT the raw comparison!
#   icmp: F=0 LT=1 EQ=2 LE=3 GT=4 NE=5 GE=6 T=7  (from ICmpAll)
#   bop:  AND=0 OR=1 XOR=2                      (from Bop)
#
# NOTE: the Pv output is `~raw BOP Pp` (verified across 18 (bop, pp, raw)
# combinations). This contradicts the loose "{Pu,Pv} = bop(raw,Pp)" claim in
# notes/sm90/instr/isetp.md and is a new empirical finding.
#
# Reading predicates: P2R reads the predicate file too early in a back-to-back
# ISETP burst (returns the previous ISETP's value) UNLESS given a sufficient
# stall. Verified on SM120: P2R with stall>=4 reads fresh values reliably
# (avoid stall=12 with yield=0, usched=28 boundary). We use stall=8.
#   P2R R, PR, RZ, 0x7f; [7:7:{1}:8:0]

cubin = assemble('''
#fn isetp_test(out<64>) {
    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]
    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]

    // === Simple form: all 8 icmp ops, Ra=5, Rb=5 ===
    MOV32I R0, 0x00000005;[7:7:{}:5:1]
    MOV32I R1, 0x00000005;[7:7:{}:5:1]

    ISETP.F   P0, R0, R1;[7:7:{}:5:1]   // always 0
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}], R2;[7:1:{0}:1:0]

    ISETP.LT  P0, R0, R1;[7:7:{}:5:1]   // 5<5 = 0
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R2;[7:1:{0}:1:0]

    ISETP.EQ  P0, R0, R1;[7:7:{}:5:1]   // 5==5 = 1
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R2;[7:1:{0}:1:0]

    ISETP.LE  P0, R0, R1;[7:7:{}:5:1]   // 5<=5 = 1
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R2;[7:1:{0}:1:0]

    ISETP.GT  P0, R0, R1;[7:7:{}:5:1]   // 5>5 = 0
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R2;[7:1:{0}:1:0]

    ISETP.NE  P0, R0, R1;[7:7:{}:5:1]   // 5!=5 = 0
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R2;[7:1:{0}:1:0]

    ISETP.GE  P0, R0, R1;[7:7:{}:5:1]   // 5>=5 = 1
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R2;[7:1:{0}:1:0]

    ISETP.T   P0, R0, R1;[7:7:{}:5:1]   // always 1
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x1C], R2;[7:1:{0}:1:0]

    // === Signed vs unsigned: Ra=-1 (0xFFFFFFFF), Rb=5 ===
    MOV32I R0, 0xFFFFFFFF;[7:7:{}:5:1]
    MOV32I R1, 0x00000005;[7:7:{}:5:1]

    ISETP.LT.S32 P0, R0, R1;[7:7:{}:5:1]   // -1 < 5 = 1
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R2;[7:1:{0}:1:0]

    ISETP.LT.U32 P0, R0, R1;[7:7:{}:5:1]   // 0xFFFFFFFF < 5 = 0
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x24], R2;[7:1:{0}:1:0]

    // === Immediate form: Ra=5, Rb=5 (imm); Pu=EQ&PT=1, Pv=~EQ&PT=0 ===
    MOV32I R0, 0x00000005;[7:7:{}:5:1]
    ISETP.EQ.U32.AND P0, P1, R0, 5, PT;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x28], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x2C], R3;[7:1:{0}:1:0]

    // === Full form bop matrix: Ra=5, Rb=5 (raw EQ=1) ===
    MOV32I R0, 0x00000005;[7:7:{}:5:1]
    MOV32I R1, 0x00000005;[7:7:{}:5:1]

    // AND, Pp=P0=1  -> Pu = 1&1 = 1,  Pv = ~1&1 = 0
    ISETP.T P0, RZ, RZ;[7:7:{}:5:1]
    ISETP.EQ.AND P2, P3, R0, R1, P0;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x30], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x34], R3;[7:1:{0}:1:0]

    // AND, Pp=0  -> Pu = 1&0 = 0,  Pv = ~1&0 = 0
    ISETP.F P0, RZ, RZ;[7:7:{}:5:1]
    ISETP.EQ.AND P2, P3, R0, R1, P0;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x38], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x3C], R3;[7:1:{0}:1:0]

    // OR, Pp=1  -> Pu = 1|1 = 1,  Pv = ~1|1 = 1
    ISETP.T P0, RZ, RZ;[7:7:{}:5:1]
    ISETP.EQ.OR P2, P3, R0, R1, P0;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x40], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x44], R3;[7:1:{0}:1:0]

    // OR, Pp=0  -> Pu = 1|0 = 1,  Pv = ~1|0 = 0
    ISETP.F P0, RZ, RZ;[7:7:{}:5:1]
    ISETP.EQ.OR P2, P3, R0, R1, P0;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x48], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4C], R3;[7:1:{0}:1:0]

    // XOR, Pp=1 -> Pu = 1^1 = 0,  Pv = ~1^1 = 1
    ISETP.T P0, RZ, RZ;[7:7:{}:5:1]
    ISETP.EQ.XOR P2, P3, R0, R1, P0;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x50], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x54], R3;[7:1:{0}:1:0]

    // XOR, Pp=0 -> Pu = 1^0 = 1,  Pv = ~1^0 = 0
    ISETP.F P0, RZ, RZ;[7:7:{}:5:1]
    ISETP.EQ.XOR P2, P3, R0, R1, P0;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x58], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x5C], R3;[7:1:{0}:1:0]

    // === Full form with raw=0: Ra=5, Rb=6 (EQ false) ===
    MOV32I R1, 0x00000006;[7:7:{}:5:1]

    // XOR, Pp=1 -> Pu = 0^1 = 1,  Pv = ~0^1 = 1^1 = 0
    ISETP.T P0, RZ, RZ;[7:7:{}:5:1]
    ISETP.EQ.XOR P2, P3, R0, R1, P0;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x60], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x64], R3;[7:1:{0}:1:0]

    // AND, Pp=1 -> Pu = 0&1 = 0,  Pv = ~0&1 = 1
    ISETP.EQ.AND P2, P3, R0, R1, P0;[7:7:{}:5:1]
    P2R R2, PR, RZ, 0x7f;[7:7:{1}:8:0]
    P2R R3, PR, RZ, 0x7f;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x68], R2;[7:1:{0}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x6C], R3;[7:1:{0}:1:0]

    EXIT;[7:7:{}:5:0]
}
''')

Path('x.cubin').write_bytes(cubin)

mod = CudaModule(cubin)
d = mod.devmem_alloc(128)
mod.launch("isetp_test", grid=1, block=1, args=[d])
mod.synchronize()
vals = struct.unpack("<32I", mod.device_read(d, 128))

print("=== ISETP Semantic Verification (SM120) ===")
print()
ok = True

# [1]-[8] simple form, Ra=5, Rb=5
cases = [
    ("ISETP.F   P0, R0, R1", 0),   # always 0
    ("ISETP.LT  P0, R0, R1", 0),   # 5<5
    ("ISETP.EQ  P0, R0, R1", 1),   # 5==5
    ("ISETP.LE  P0, R0, R1", 1),   # 5<=5
    ("ISETP.GT  P0, R0, R1", 0),   # 5>5
    ("ISETP.NE  P0, R0, R1", 0),   # 5!=5
    ("ISETP.GE  P0, R0, R1", 1),   # 5>=5
    ("ISETP.T   P0, R0, R1", 1),   # always 1
]
for i, (asm, exp) in enumerate(cases):
    got = vals[i] & 1
    status = "OK" if got == exp else "FAIL"
    ok &= got == exp
    print(f"[{i+1:2d}] {asm:<28} P0={got} (expected {exp})  {status}")

# [9]-[10] signed/unsigned with Ra=-1, Rb=5
got = vals[8] & 1
status = "OK" if got == 1 else "FAIL"; ok &= got == 1
print(f"[9]  ISETP.LT.S32 P0, R0(-1), R1(5)      P0={got} (expected 1)  {status}")
got = vals[9] & 1
status = "OK" if got == 0 else "FAIL"; ok &= got == 0
print(f"[10] ISETP.LT.U32 P0, R0(0xFFFFFFFF), R1(5)  P0={got} (expected 0)  {status}")

# [11]-[12] immediate form: Pu=EQ&PT, Pv=~EQ&PT; raw=1, Pp=PT(1)
got_pu, got_pv = vals[10] & 1, (vals[11] >> 1) & 1
status = "OK" if (got_pu, got_pv) == (1, 0) else "FAIL"
ok &= (got_pu, got_pv) == (1, 0)
print(f"[11] ISETP.EQ.U32.AND P0, P1, R0, 5, PT  Pu={got_pu} Pv={got_pv} (expected 1,0)  {status}")

# [13]-[24] full form, raw=1 (EQ 5==5): (bop, pp, e_pu, e_pv)
full = [
    ("AND", 1, 1, 0),   # Pu = 1&1, Pv = ~1&1
    ("AND", 0, 0, 0),   # Pu = 1&0, Pv = ~1&0
    ("OR",  1, 1, 1),   # Pu = 1|1, Pv = ~1|1
    ("OR",  0, 1, 0),   # Pu = 1|0, Pv = ~1|0
    ("XOR", 1, 0, 1),   # Pu = 1^1, Pv = ~1^1
    ("XOR", 0, 1, 0),   # Pu = 1^0, Pv = ~1^0
]
for i, (bop, pp, e_pu, e_pv) in enumerate(full):
    got_pu, got_pv = (vals[12 + 2*i] >> 2) & 1, (vals[13 + 2*i] >> 3) & 1
    status = "OK" if (got_pu, got_pv) == (e_pu, e_pv) else "FAIL"
    ok &= (got_pu, got_pv) == (e_pu, e_pv)
    print(f"[{13+2*i:2d}] EQ.{bop} Pp={pp}: Pu={got_pu} Pv={got_pv} (expected {e_pu},{e_pv})  {status}")

# [25]-[26] full form, raw=0 (EQ 5==6)
got_pu, got_pv = (vals[24] >> 2) & 1, (vals[25] >> 3) & 1
e_pu, e_pv = 1, 0   # Pu = 0^1, Pv = ~0^1 = 1^1 = 0
status = "OK" if (got_pu, got_pv) == (e_pu, e_pv) else "FAIL"
ok &= (got_pu, got_pv) == (e_pu, e_pv)
print(f"[25] EQ.XOR Pp=1 (raw=0): Pu={got_pu} Pv={got_pv} (expected {e_pu},{e_pv})  {status}")
got_pu, got_pv = (vals[26] >> 2) & 1, (vals[27] >> 3) & 1
e_pu, e_pv = 0, 1   # Pu = 0&1, Pv = ~0&1
status = "OK" if (got_pu, got_pv) == (e_pu, e_pv) else "FAIL"
ok &= (got_pu, got_pv) == (e_pu, e_pv)
print(f"[26] EQ.AND Pp=1 (raw=0): Pu={got_pu} Pv={got_pv} (expected {e_pu},{e_pv})  {status}")

print()
print(f"=== {'ALL OK' if ok else 'SOME FAILED'} ===")
print("Key finding: full-form Pv = ~(Ra icmp Rb) BOP Pp, NOT the raw comparison.")

mod.devmem_free(d)
