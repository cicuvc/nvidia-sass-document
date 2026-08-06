import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UCLEA — uniform "clear effective address" (udp_pipe; verified SM120, RTX 5090)
#
#   UCLEA {URd,URd+1}, UPu, {URa,URa+1}, URb|imm16, constSize
#         (0x1cbc URb-form / 0x18bc imm-form)
#
# SILICON BEHAVIOR (contradicts the note's "align down by constSize" guess):
#   URd.64 = (URa.64 << 6) + URb      -- a HARDWIRED 6-bit left shift (x64)
#   + the 32-bit URb/imm offset, truncated to 64 bits.
#   * constSize (0..16, validated by CONDITIONS) has NO observable effect:
#     K=0, 5, 16 all produce the same result.
#   * UPu output: NOT probed here.  Reading it requires UISETP->PLOP3
#     materialization, and the uniform-predicate write->read path is not
#     scoreboard-synchronized in hand-assembled SASS (observed
#     nondeterministic); the earlier "@UP0 MOV32I" probe read the guard field
#     as regular P0 (stale), so "UPu never asserted" was an artifact.
# The 64-bit URa pair is fully shifted (hi word participates).
#
# Fields: URb -> [39:32], URa -> [31:24], URd -> [23:16], UPu -> [83:81],
# constSize -> [77:73], guard UPg -> [14:12]/[15].
# ---------------------------------------------------------------------------

REF = [
    (0x0000000806047cbc, 0x000fca00080e0a00),  # UCLEA {UR4,5}, UPT, {UR6,7}, UR8, 5
    (0x0000000806047cbc, 0x000fca0008000a00),  # UP0 instead of UPT
    (0x00000123060478bc, 0x000fca00080e0a00),  # imm16 0x123
    (0x00000123060478bc, 0x000fca00080e2000),  # constSize=16
]
flat = assemble_flat("""UCLEA {UR4,UR5}, UPT, {UR6,UR7}, UR8, 0x5;[7:7:{}:5:1]
UCLEA {UR4,UR5}, UP0, {UR6,UR7}, UR8, 0x5;[7:7:{}:5:1]
UCLEA {UR4,UR5}, UPT, {UR6,UR7}, 0x123, 0x5;[7:7:{}:5:1]
UCLEA {UR4,UR5}, UPT, {UR6,UR7}, 0x123, 16;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"

def kernel(imm=None, K=5):
    if imm is not None:
        uclea = f"UCLEA {{UR12,UR13}}, UP0, {{UR6,UR7}}, 0x{imm:X}, {K};[7:7:{{2,3}}:5:1]"
        off_load = ""
    else:
        uclea = f"UCLEA {{UR12,UR13}}, UP0, {{UR6,UR7}}, UR8, {K};[7:7:{{2,3}}:5:1]"
        off_load = "    LDCU UR8, #param(off);[3:7:{}:1:0]\n"
    return f"""#fn uclea_test(base<8>, off<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU.64 {{UR6, UR7}}, #param(base);[2:7:{{}}:1:0]
{off_load}    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR7;[7:7:{{2}}:5:1]
    UMOV UR9, UR8;[7:7:{{3}}:5:1]
{uclea}    UMOV UR9, UR12;[7:7:{{}}:5:1]
    UMOV UR14, UR12;[7:7:{{}}:5:1]
    UMOV UR9, UR13;[7:7:{{}}:5:1]
    UMOV UR15, UR13;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    IADD3 R3, PT, PT, RZ, UR15, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E.64 desc[{{UR4,UR5}}][{{R6,R7}}+0x0], {{R2,R3}};[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""

try:
    build(kernel())
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

def run_kernel(src, base, off):
    mod = build(src)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("uclea_test", grid=(1,), block=(1,),
               args=[base & 0xFFFFFFFFFFFFFFFF, off & 0xFFFFFFFFFFFFFFFF, d])
    mod.synchronize()
    res = struct.unpack("<Q", mod.device_read(d, 8))[0]
    mod.devmem_free(d)
    return res

# URb-form: (URa << 6) + URb, constSize irrelevant.
cases = [
    (0x12345678, 0x123, 5, "base+off, K=5"),
    (0x100000001, 0x0, 5, "hi word participates"),
    (0xFFFFFFFFFFFFFFFF, 0x1, 5, "64-bit truncation"),
    (0xFFFFFFFF, 0x2, 4, "32-bit carry"),
    (0x00000000, 0x0, 5, "zero"),
    (0x41, 0x0, 5, "0x41<<6"),
    (0x12345678, 0x123, 0, "K=0 same as K=5"),
    (0x12345678, 0x123, 16, "K=16 same as K=5"),
]
for base, off, K, lab in cases:
    res = run_kernel(kernel(K=K), base, off)
    exp = ((base << 6) + off) & 0xFFFFFFFFFFFFFFFF
    good = res == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lab:24s} -> 0x{res:016X} (exp 0x{exp:016X})")

# imm16-form.
res = run_kernel(kernel(imm=0x123), 0x12345678, 0)
exp = ((0x12345678 << 6) + 0x123) & 0xFFFFFFFFFFFFFFFF
good = res == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} imm16 0x123            -> 0x{res:016X} (exp 0x{exp:016X})")

print("\n=== UCLEA semantic verification: ALL OK ===" if ok else "\n=== UCLEA FAILURES ===")
sys.exit(0 if ok else 1)
