import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat
import struct

# IABS — Integer absolute value (32-bit, int_pipe).
#
# Semantics under verification on SM120 (RTX 5090):
#   Rd = |Rb|      (two's-complement; INT_MIN = 0x80000000 wraps to itself)
# No modifiers. Three source forms:
#   RRR  : IABS Rd, Rb          opcode 0x213
#   RsIR : IABS Rd, imm32       opcode 0x813
#   RUR  : IABS Rd, URb         opcode 0x1c13
# ptxas emits only RRR (see notes/sm90/instr/iabs.md); the imm and uniform
# forms are exercised here directly.

cubin = assemble('''
#fn iabs_test(out<64>, n<4>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]
    LDCU UR3, #param(n);[2:7:{}:1:0]     // n = -3; NOT UR5 — UR4:UR5 is the
                                         // 64-bit cache descriptor high half

    // === RRR: register source ===
    MOV32I R0, 0x00000000;[7:7:{}:5:1]   // 0
    IABS R3, R0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R3;[0:1:{0}:1:0]
    MOV32I R0, 0x00000001;[7:7:{}:5:1]   // 1
    IABS R3, R0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R3;[0:1:{0}:1:0]
    MOV32I R0, 0xFFFFFFFF;[7:7:{}:5:1]   // -1
    IABS R3, R0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R3;[0:1:{0}:1:0]
    MOV32I R0, 0x7FFFFFFF;[7:7:{}:5:1]   // INT_MAX
    IABS R3, R0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R3;[0:1:{0}:1:0]
    MOV32I R0, 0x80000000;[7:7:{}:5:1]   // INT_MIN -> wraps to itself
    IABS R3, R0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R3;[0:1:{0}:1:0]
    MOV32I R0, 0x80000001;[7:7:{}:5:1]   // INT_MIN+1
    IABS R3, R0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R3;[0:1:{0}:1:0]
    MOV32I R0, 0xDEADBEEF;[7:7:{}:5:1]   // negative
    IABS R3, R0;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R3;[0:1:{0}:1:0]

    // === RsIR: signed immediate source ===
    IABS R3, 0xFFFFFF00;[7:7:{}:8:1]     // -0x100
    STG.E desc[{UR4,UR5}][{R6,R7}+0x1C], R3;[0:1:{0}:1:0]
    IABS R3, 0x80000000;[7:7:{}:8:1]     // INT_MIN imm -> wraps
    STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R3;[0:1:{0}:1:0]
    IABS R3, 0x00000005;[7:7:{}:8:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x24], R3;[0:1:{0}:1:0]

    // === RUR: uniform register source (n = -3) ===
    IABS R3, UR3;[7:7:{2}:8:1]           // req={2} = wait LDCU UR3 (var-latency)
    STG.E desc[{UR4,UR5}][{R6,R7}+0x28], R3;[0:1:{0}:1:0]

    EXIT;[7:7:{}:5:0]
}
''')

Path('x.cubin').write_bytes(cubin)

# --- offline encoding self-check -------------------------------------------
enc = assemble_flat(
    "IABS R3, R0;[7:7:{}:5:1]\n"
    "IABS R3, 0xFFFFFF00;[7:7:{}:5:1]\n"
    "IABS R3, UR3;[7:7:{}:5:1]\n")
for (name, exp_op), (lo, hi) in zip(
        (("RRR", 0x213), ("RsIR", 0x813), ("RUR", 0x1c13)), enc):
    op = ((hi >> 27) & 1) << 12 | (lo & 0xFFF)
    assert op == exp_op, f"{name}: opcode 0x{op:x} != 0x{exp_op:x}"
print("encoding self-check: RRR/RsIR/RUR opcodes OK")

# --- run on GPU -------------------------------------------------------------
mod = CudaModule(cubin)
d = mod.devmem_alloc(4 * 11)
mod.launch("iabs_test", grid=(1,), block=(1,), args=[d, 0xFFFFFFFD])  # n = -3
mod.synchronize()
vals = struct.unpack("<11I", mod.device_read(d, 4 * 11))


def abs32(v):
    v &= 0xFFFFFFFF
    return (0 - v) & 0xFFFFFFFF if v >> 31 else v


rrr_cases = [
    ("0x00000000", 0x00000000),
    ("0x00000001", 0x00000001),
    ("0xFFFFFFFF (-1)", 0x00000001),
    ("0x7FFFFFFF (INT_MAX)", 0x7FFFFFFF),
    ("0x80000000 (INT_MIN)", 0x80000000),
    ("0x80000001 (INT_MIN+1)", 0x7FFFFFFF),
    ("0xDEADBEEF", 0x21524111),
]
rsir_cases = [
    ("imm 0xFFFFFF00", abs32(0xFFFFFF00)),
    ("imm 0x80000000", abs32(0x80000000)),
    ("imm 0x00000005", abs32(0x00000005)),
]
rur_expected = 3  # |n| with n = -3

print("=== IABS Semantic Verification (SM120) ===")
print()
ok = True
for i, (name, exp) in enumerate(rrr_cases):
    got = vals[i]
    status = "OK" if got == exp else "FAIL"
    ok &= got == exp
    print(f"[{i+1:2d}] RRR  |{name:<22}| got 0x{got:08x} expected 0x{exp:08x}  {status}")
for j, (name, exp) in enumerate(rsir_cases):
    got = vals[7 + j]
    status = "OK" if got == exp else "FAIL"
    ok &= got == exp
    print(f"[{8+j:2d}] RsIR |{name:<22}| got 0x{got:08x} expected 0x{exp:08x}  {status}")
got = vals[10]
status = "OK" if got == rur_expected else "FAIL"
ok &= got == rur_expected
print(f"[11] RUR  |UR3=-3         | got 0x{got:08x} expected 0x{rur_expected:08x}  {status}")

print()
print(f"=== {'ALL OK' if ok else 'SOME FAILED'} ===")
print("Key findings: Rd = |Rb|; INT_MIN (0x80000000) wraps to itself;")
print("              all three source forms (RRR/RsIR/RUR) agree.")

mod.devmem_free(d)
