import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# ULOP3 — uniform three-input logic (udp_pipe; verified SM120, RTX 5090)
#
#   ULOP3.LUT URd, URa, URb, URc, imm8      (0x1292 noimm / 0x1892 imm32)
#   ULOP3.AND|OR|XOR|PASS_B URd, [~]URa, [~]URb, [~]URc
#
# SILICON QUIRK (verified): the LUT truth-table index uses the inputs in
# the order (c, b, a) — i.e. bit i of the result is
#     LUT[ (c_i) | (b_i)<<1 | (a_i)<<2 ]
# NOT the standard LOP3 order (a | b<<1 | c<<2).  The a and c inputs are
# swapped in the index.  Verified against 15 LUT values; the classic LOP3
# LUTs (XOR=0x96, AND=0x80, OR=0xFE, PASS_B=0xCC) are invariant under this
# swap, which is why they "just work" as named ops.
#
# imm8 -> bits [79:72]; URa [31:24], URb [39:32], URc (Ra_URc) [71:64];
# UPu -> [83:81].  The assembler's LUT form matches the optional-UPp ALT
# (UPp pinned !UPT), same as ptxas.
# ---------------------------------------------------------------------------

REF = [
    (0x0000000706047292, 0x000fca000f8e9608),  # ULOP3.LUT UR4, UR6, UR7, UR8, 0x96
    (0x1234567806047892, 0x000fca000f8e9608),  # ULOP3.LUT UR4, UR6, 0x12345678, UR8, 0x96
    (0x0000000706047292, 0x000fca000f8e8008),  # ULOP3.AND (LUT 0x80)
    (0x0000000706047292, 0x000fca000f8e2008),  # ULOP3.AND with ~URb (LUT 0x20)
]
flat = assemble_flat("""ULOP3.LUT UR4, UR6, UR7, UR8, 0x96;[7:7:{}:5:1]
ULOP3.LUT UR4, UR6, 0x12345678, UR8, 0x96;[7:7:{}:5:1]
ULOP3.AND UR4, UR6, UR7, UR8;[7:7:{}:5:1]
ULOP3.AND UR4, UR6, ~UR7, UR8;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(inst, imm=False):
    if imm:
        loads = ("    LDCU UR6, #param(a);[2:7:{}:1:0]\n"
                 "    LDCU UR8, #param(c);[4:7:{}:1:0]\n"
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"
                 "    UMOV UR9, UR8;[7:7:{4}:5:1]\n")
        reqs = "{2,4}"
    else:
        loads = ("    LDCU UR6, #param(a);[2:7:{}:1:0]\n"
                 "    LDCU UR7, #param(b);[3:7:{}:1:0]\n"
                 "    LDCU UR8, #param(c);[4:7:{}:1:0]\n"
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"
                 "    UMOV UR9, UR7;[7:7:{3}:5:1]\n"
                 "    UMOV UR9, UR8;[7:7:{4}:5:1]\n")
        reqs = "{2,3,4}"
    return f"""#fn t(a<8>, b<8>, c<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
{loads}    {inst}[7:7:{reqs}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a, b, c, imm=False):
    mod = build(kernel(inst, imm=imm))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[a, b, c, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


def model_swap(a, b, c, lut):
    r = 0
    for i in range(32):
        idx = ((c >> i) & 1) | (((b >> i) & 1) << 1) | (((a >> i) & 1) << 2)
        r |= ((lut >> idx) & 1) << i
    return r


try:
    run("ULOP3.LUT UR16, UR6, UR7, UR8, 0x96;", 1, 2, 4)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

A, B, C = 0xFF00FF00, 0xF0F0F0F0, 0xCCCCCCCC

# LUT mode: bit-sliced truth table with the (c,b,a) index order.
for lut in (0x00, 0x96, 0x80, 0xFE, 0xCC, 0x3C, 0xAA, 0xFF, 0x01, 0x0F,
            0x69, 0x0E, 0x5A, 0xA5, 0x55):
    v = run(f"ULOP3.LUT UR16, UR6, UR7, UR8, 0x{lut:X};", A, B, C)
    exp = model_swap(A, B, C, lut)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} LUT=0x{lut:02X} -> 0x{v:08X} (swap-model 0x{exp:08X})")

# imm32 form (URb replaced by immediate).
v = run("ULOP3.LUT UR16, UR6, 0x12345678, UR8, 0x96;", A, B, C, imm=True)
exp = model_swap(A, 0x12345678, C, 0x96)
good = v == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} imm32 LUT=0x96 -> 0x{v:08X} (exp 0x{exp:08X})")

# Named LOP ops (consistent with the swap-indexed LUTs).
for op, lut in [("AND", 0x80), ("OR", 0xFE), ("XOR", 0x96), ("PASS_B", 0xCC)]:
    v = run(f"ULOP3.{op} UR16, UR6, UR7, UR8;", A, B, C)
    exp = model_swap(A, B, C, lut)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {op:6s} -> 0x{v:08X} (exp 0x{exp:08X})")

# ~ inversion on URb.
v = run("ULOP3.AND UR16, UR6, ~UR7, UR8;", A, B, C)
exp = model_swap(A, (~B) & 0xFFFFFFFF, C, 0x80)
good = v == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} AND ~URb -> 0x{v:08X} (exp 0x{exp:08X})")

print("\n=== ULOP3 semantic verification: ALL OK ===" if ok else "\n=== ULOP3 FAILURES ===")
sys.exit(0 if ok else 1)
