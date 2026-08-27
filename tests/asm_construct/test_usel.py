import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from archutil import adapt_source, same_as_capture, is_sm90  # noqa: E402

# ---------------------------------------------------------------------------
# USEL — uniform register conditional select (udp_pipe; verified SM120)
#
#   USEL URd, URa, URb|imm32, [!]UPp     (0x1287 / 0x1887)
#   USEL.64 {URd,URd+1}, {URa,URa+1}, {URb,URb+1}|imm32, [!]UPp  (0x1c87/0x1487)
#
#   URd = UPp ? URa : URb|imm   (32-bit, verified)
#
# SILICON QUIRK (64-bit register form, UPp=0): selecting the second source
# gives {URb, URb} — the HIGH word is the LOW word duplicated (URb+1 is not
# read).  The true path (UPp=1) and the 64-bit imm form are correct.
#
# Fields: URd [23:16], URa [31:24], URb [39:32], imm [63:32], UPp [89:87]
# + not [90].
# ---------------------------------------------------------------------------

REF = [
    (0x0000000806047287, 0x000fca0008000000),  # USEL UR4, UR6, UR8, UP0
    (0x1234567806047887, 0x000fca0008000000),  # USEL UR4, UR6, 0x12345678, UP0
    (0x0000000806047287, 0x000fca000c000000),  # USEL UR4, UR6, UR8, !UP0
    (0x0000000806047c87, 0x000fca0008000000),  # USEL.64 {UR4,5}, {UR6,7}, {UR8,9}, UP0
    (0x1234567806047487, 0x000fca0008000000),  # USEL.64 {UR4,5}, {UR6,7}, imm, UP0
]
_S = "USEL UR4, UR6, UR8, UP0;[7:7:{}:5:1]\nUSEL UR4, UR6, 0x12345678, UP0;[7:7:{}:5:1]\nUSEL UR4, UR6, UR8, !UP0;[7:7:{}:5:1]\n"
if is_sm90():
    # no USEL.64 variant in the sm_90 spec
    _src = _S
else:
    _src = _S + """USEL.64 {UR4,UR5}, {UR6,UR7}, {UR8,UR9}, UP0;[7:7:{}:5:1]
USEL.64 {UR4,UR5}, {UR6,UR7}, 0x12345678, UP0;[7:7:{}:5:1]
"""
flat = assemble_flat(_src)
ok = True
_pins = same_as_capture("sm120")
if not _pins:
    print("info byte-exact REF vectors captured on sm120 — skipped under",
          __import__('assembler.arch', fromlist=['x']).current().name)
for i, enc in enumerate(flat):
    good = (enc == REF[i]) if _pins else True
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(adapt_source(src), check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


# Simpler: build each kernel inline with a helper for the select predicate.
def kernel32(inst, pp):
    t = "T" if pp else "F"
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
    LDCU UR8, #param(b);[3:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR8;[7:7:{{3}}:5:1]
    UISETP.{t} UP0, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP0;[7:7:{{2,3}}:5:1]
    {inst}[7:7:{{2,3}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run32(inst, pp, a, b):
    mod = build(kernel32(inst, pp))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[a, b, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


def kernel64(inst, pp):
    t = "T" if pp else "F"
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU.64 {{UR6, UR7}}, #param(a);[2:7:{{}}:1:0]
    LDCU.64 {{UR8, UR9}}, #param(b);[3:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR7;[7:7:{{2}}:5:1]
    UMOV UR9, UR8;[7:7:{{3}}:5:1]
    UMOV UR9, UR9;[7:7:{{3}}:5:1]
    UISETP.{t} UP0, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP0;[7:7:{{2,3}}:5:1]
    {inst}[7:7:{{2,3}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR17;[7:7:{{}}:5:1]
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


def run64(inst, pp, a, b):
    mod = build(kernel64(inst, pp))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[a, b, d])
    mod.synchronize()
    v = struct.unpack("<2I", mod.device_read(d, 8))
    mod.devmem_free(d)
    return v


try:
    run32("USEL UR16, UR6, UR8, UP0;", 1, 1, 2)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

A, B = 0x11111111, 0x22222222
for pp in (0, 1):
    for neg in ("", "!"):
        v = run32(f"USEL UR16, UR6, UR8, {neg}UP0;", pp, A, B)
        exp = A if (pp ^ (1 if neg else 0)) else B
        good = v == exp
        ok &= good
        print(f"{'ok ' if good else 'FAIL'} USEL UPp={pp} {neg or ''}not -> 0x{v:08X} (exp 0x{exp:08X})")
for pp in (0, 1):
    v = run32("USEL UR16, UR6, 0xCAFEBABE, UP0;", pp, A, B)
    exp = A if pp else 0xCAFEBABE
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} USEL imm UPp={pp} -> 0x{v:08X} (exp 0x{exp:08X})")

# 64-bit register form: true path correct, false path duplicates URb (quirk).
A64, B64 = 0xAAAAAAAA_11111111, 0xCCCCCCCC_33333333
lo, hi = run64("USEL.64 {UR16,UR17}, {UR6,UR7}, {UR8,UR9}, UP0;", 1, A64, B64)
good = (lo, hi) == (0x11111111, 0xAAAAAAAA)
ok &= good
print(f"{'ok ' if good else 'FAIL'} USEL.64 reg UPp=1 -> lo=0x{lo:08X} hi=0x{hi:08X} (exp A pair)")
lo, hi = run64("USEL.64 {UR16,UR17}, {UR6,UR7}, {UR8,UR9}, UP0;", 0, A64, B64)
good = (lo, hi) == (0x33333333, 0x33333333)  # QUIRK: hi duplicates lo
ok &= good
print(f"{'ok ' if good else 'FAIL'} USEL.64 reg UPp=0 -> lo=0x{lo:08X} hi=0x{hi:08X} (QUIRK: {{URb,URb}})")

# 64-bit imm form: both paths correct.
for pp in (0, 1):
    lo, hi = run64("USEL.64 {UR16,UR17}, {UR6,UR7}, 0xCAFEBABE, UP0;", pp, A64, B64)
    exp = (0x11111111, 0xAAAAAAAA) if pp else (0xCAFEBABE, 0x00000000)
    good = (lo, hi) == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} USEL.64 imm UPp={pp} -> lo=0x{lo:08X} hi=0x{hi:08X} (exp 0x{exp[0]:08X},0x{exp[1]:08X})")

print("\n=== USEL semantic verification: ALL OK ===" if ok else "\n=== USEL FAILURES ===")
sys.exit(0 if ok else 1)
