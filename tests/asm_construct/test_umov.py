import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UMOV — uniform move (udp_pipe; verified SM120, RTX 5090)
#
#   UMOV URd, URb|imm32        (0x1c82 UR / 0x882 imm)
#   UMOV.64 {URd,URd+1}, {URb,URb+1}|imm64   (0x1c82 .64 / imm64)
#   URd = URb|imm — pure uniform data movement (also serves as the udp
#   "settling" filler used throughout the uniform instruction tests).
# ---------------------------------------------------------------------------

REF = [
    (0x0000000600047c82, 0x000fca0008000000),  # UMOV UR4, UR6
    (0x1234567800047882, 0x000fca0000000000),  # UMOV UR4, imm
    (0x0000000600047c82, 0x000fca0008010000),  # UMOV.64 {UR4,5}, {UR6,7}
    (0x7812345678047482, 0x000fca0008123456),  # UMOV.64 {UR4,5}, imm64
]
from archutil import same_as_capture, is_sm90
_pins = same_as_capture("sm120")
if is_sm90():
    # sm_90 spec has no UMOV.64 variant (only URd←imm32 / URd←URb);
    # 64-bit uniform moves go through ULDC.64 instead.
    _src = """UMOV UR4, UR6;[7:7:{}:5:1]
UMOV UR4, 0x12345678;[7:7:{}:5:1]
"""
else:
    _src = """UMOV UR4, UR6;[7:7:{}:5:1]
UMOV UR4, 0x12345678;[7:7:{}:5:1]
UMOV.64 {UR4,UR5}, {UR6,UR7};[7:7:{}:5:1]
UMOV.64 {UR4,UR5}, 0x1234567812345678;[7:7:{}:5:1]
"""
flat = assemble_flat(_src)
ok = True
if not _pins:
    print("info byte-exact REF vectors captured on sm120 — skipped under", __import__('assembler.arch', fromlist=['x']).current().name)
for i, enc in enumerate(flat):
    good = (enc == REF[i]) if _pins else True
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(adapt_source(src), check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(inst):
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU.64 {{UR6, UR7}}, #param(a);[2:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR7;[7:7:{{2}}:5:1]
    {inst}[7:7:{{2}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR17;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR17;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    UMOV UR14, UR17;[7:7:{{}}:5:1]
    IADD3 R3, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x4], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a):
    mod = build(kernel(inst))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[a, 0, d])
    mod.synchronize()
    lo, hi = struct.unpack("<2I", mod.device_read(d, 8))
    mod.devmem_free(d)
    return lo, hi


try:
    run("UMOV UR16, UR6;", 0x12345678)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# Register move: URd = URb.
lo, hi = run("UMOV UR16, UR6;", 0xDEADBEEF)
good = lo == 0xDEADBEEF
ok &= good
print(f"{'ok ' if good else 'FAIL'} UMOV UR16 <- UR6: 0x{lo:08X} (exp 0xDEADBEEF)")

# Immediate move.
lo, hi = run("UMOV UR16, 0xCAFEBABE;", 0)
good = lo == 0xCAFEBABE
ok &= good
print(f"{'ok ' if good else 'FAIL'} UMOV imm: 0x{lo:08X} (exp 0xCAFEBABE)")

# 64-bit register pair move.
lo, hi = run("UMOV.64 {UR16,UR17}, {UR6,UR7};", 0xAAAAAAAA11111111)
good = (lo, hi) == (0x11111111, 0xAAAAAAAA)
ok &= good
print(f"{'ok ' if good else 'FAIL'} UMOV.64 pair: 0x{hi:08X}{lo:08X} (exp 0xAAAAAAAA11111111)")

# 64-bit immediate move.
lo, hi = run("UMOV.64 {UR16,UR17}, 0x123456789ABCDEF0;", 0)
good = (lo, hi) == (0x9ABCDEF0, 0x12345678)
ok &= good
print(f"{'ok ' if good else 'FAIL'} UMOV.64 imm64: 0x{hi:08X}{lo:08X} (exp 0x123456789ABCDEF0)")

print("\n=== UMOV semantic verification: ALL OK ===" if ok else "\n=== UMOV FAILURES ===")
sys.exit(0 if ok else 1)
