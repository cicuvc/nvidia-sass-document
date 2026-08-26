import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from archutil import adapt_source, same_as_capture, is_sm90  # noqa: E402

# ---------------------------------------------------------------------------
# UISETP — uniform integer set-predicate (udp_pipe; verified SM120, RTX 5090)
#
#   simple: UISETP.icmp[.fmt] UPu, URa, URb|imm
#   full:   UISETP.icmp[.bop][.fmt] UPu, UPv, URa, URb|imm, [!]UPp
#   icmp: F/LT/EQ/LE/GT/NE/GE/T (ICmpAll, [78:76]); bop: AND/OR/XOR ([75:74]);
#   fmt: U32/S32 ([80],[73]); U64/S64 in the *_64_* variants.
#   UPu -> [83:81], UPv -> [86:84], UPp -> [89:87] + not [90],
#   URa -> [31:24], URb -> [39:32].
#
# Semantics (silicon-verified, 32-bit): comp = (URa icmp URb);
#   UPu = comp bop UPp,  UPv = !comp bop UPp   (full form; bop=AND with
#   UPT for the simple form).
#
# Uniform-datapath notes:
#   * A UISETP-written uniform predicate is not reliably readable by the
#     first udp consumer — one dummy udp read (UISETP with UPp=UP0,
#     result discarded) settles it (same pattern as LDCU-loaded URs).
#   * Only udp instructions with a UniformPredicate guard (e.g. UMOV) can
#     consume uniform predicates; a regular `@UP0 MOV32I` would encode a
#     GPR predicate instead.
#   * The 64-bit (U64/S64) forms pass the basic direction tests (sign
#     cases, high-word differences) but some equal/low-word cases return
#     unexpected results (e.g. EQ(5,5)=0) — flagged as an open question.
# ---------------------------------------------------------------------------

REF = [
    (0x000000080600728c, 0x000fca000bf01270),  # UISETP.LT UP0, UR6, UR8
    (0x000000080600728c, 0x000fca000bf07270),  # UISETP.T UP0, UR6, UR8
    (0x000000080600728c, 0x000fca000b902270),  # UISETP.EQ.AND UP0, UP1, UR6, UR8, UPT
    (0x000000080600728c, 0x000fca0009106670),  # UISETP.GE.OR UP0, UP1, UR6, UR8, UP2
    (0x000001230600788c, 0x000fca0009105a70),  # UISETP.NE.XOR UP0, UP1, UR6, 0x123, UP2
    (0x000000080600728c, 0x000fca000b911070),  # UISETP.LT.AND.U64 UP0, UP1, {UR6,7}, {UR8,9}, UPT
]
_SRC = """UISETP.LT UP0, UR6, UR8;[7:7:{}:5:1]
UISETP.T UP0, UR6, UR8;[7:7:{}:5:1]
UISETP.EQ.AND UP0, UP1, UR6, UR8, UPT;[7:7:{}:5:1]
UISETP.GE.OR UP0, UP1, UR6, UR8, UP2;[7:7:{}:5:1]
UISETP.NE.XOR UP0, UP1, UR6, 0x123, UP2;[7:7:{}:5:1]"""
if not is_sm90():
    # sm_90 spec has no UISETP *_64_* variants — Blackwell extension.
    _SRC += "\nUISETP.LT.AND.U64 UP0, UP1, {UR6,UR7}, {UR8,UR9}, UPT;[7:7:{}:5:1]"
flat = assemble_flat(_SRC + "\n")
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


def kernel_simple(icmp, a_or_imm):
    """Simple form: UISETP.icmp UP0, UR6, URb; settle UP0; @UP0 UMOV marker."""
    if isinstance(a_or_imm, int) and a_or_imm < 0x10000:
        rhs = f"0x{a_or_imm:X}"
        load_b = ""
    else:
        rhs = "UR8"
        load_b = "    LDCU UR8, #param(b);[3:7:{}:1:0]\n"
    return f"""#fn uisetp_test(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
{load_b}    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR8;[7:7:{{3}}:5:1]
    UISETP.{icmp} UP0, UR6, {rhs};[7:7:{{2,3}}:5:1]
    UISETP.T.AND UP1, UP2, UR6, {rhs}, UP0;[7:7:{{2,3}}:5:1]
    @UP0 UMOV UR14, 0x11111111;[7:7:{{}}:5:1]
    @!UP0 UMOV UR14, 0x22222222;[7:7:{{}}:5:1]
    UMOV UR15, UR14;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR15, RZ;[7:7:{{}}:8:1]
    UMOV UR9, UR4;[7:7:{{0}}:5:1]
    UMOV UR9, UR5;[7:7:{{0}}:5:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def kernel_full(icmp, bop, pp, a, b):
    return f"""#fn uisetp_test(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
    LDCU UR8, #param(b);[3:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR8;[7:7:{{3}}:5:1]
    UISETP.T UP2, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.F UP3, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP2;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP3;[7:7:{{2,3}}:5:1]
    UISETP.{icmp}.{bop} UP0, UP1, UR6, UR8, {pp};[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP0;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP1;[7:7:{{2,3}}:5:1]
    @UP0 UMOV UR14, 0x11111111;[7:7:{{}}:5:1]
    @!UP0 UMOV UR14, 0x22222222;[7:7:{{}}:5:1]
    @UP1 UMOV UR15, 0xAAAAAAAA;[7:7:{{}}:5:1]
    @!UP1 UMOV UR15, 0xBBBBBBBB;[7:7:{{}}:5:1]
    UMOV UR16, UR14;[7:7:{{}}:5:1]
    UMOV UR17, UR15;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR16, RZ;[7:7:{{}}:8:1]
    IADD3 R3, PT, PT, RZ, UR17, RZ;[7:7:{{}}:8:1]
    UMOV UR9, UR4;[7:7:{{0}}:5:1]
    UMOV UR9, UR5;[7:7:{{0}}:5:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x4], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(kernel_src, args):
    mod = build(kernel_src)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("uisetp_test", grid=(1,), block=(1,), args=list(args) + [d])
    mod.synchronize()
    n = 2 if "@UP1 UMOV" in kernel_src else 1
    v = struct.unpack(f"<{n}I", mod.device_read(d, 4 * n))
    mod.devmem_free(d)
    if n == 1:
        return 1 if v[0] == 0x11111111 else 0
    return (1 if v[0] == 0x11111111 else 0), (1 if v[1] == 0xAAAAAAAA else 0)


try:
    build(kernel_simple("T", "UR8"))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# ---- simple form: all 8 icmp modes x 3 input sets (a=5 b=3 etc.) ----
for a, b in [(5, 3), (3, 5), (5, 5)]:
    exp = {"F": 0, "LT": int(a < b), "EQ": int(a == b), "LE": int(a <= b),
           "GT": int(a > b), "NE": int(a != b), "GE": int(a >= b), "T": 1}
    for icmp in ("F", "LT", "EQ", "LE", "GT", "NE", "GE", "T"):
        got = run(kernel_simple(icmp, "UR8"), [a, b])
        good = got == exp[icmp]
        ok &= good
        if not good:
            print(f"FAIL simple {icmp} a={a} b={b}: {got} (exp {exp[icmp]})")
print("ok  simple form: 8 icmp modes x (5,3)/(3,5)/(5,5)")

# ---- full form: UPu = comp bop UPp, UPv = !comp bop UPp ----
full_cases = [
    ("LT", "AND", "UP2", 0, 0, 1), ("LT", "OR", "UP2", 0, 1, 1), ("LT", "XOR", "UP2", 0, 1, 0),
    ("GT", "AND", "UP2", 1, 1, 0), ("GT", "OR", "UP2", 1, 1, 1), ("GT", "XOR", "UP2", 1, 0, 1),
    ("GT", "AND", "UP3", 1, 0, 0), ("GT", "OR", "UP3", 1, 1, 0), ("GT", "XOR", "UP3", 1, 1, 0),
    ("LT", "AND", "!UP3", 0, 0, 1), ("LT", "OR", "!UP3", 0, 1, 1),
]
for icmp, bop, pp, comp, exp_u, exp_v in full_cases:
    u, v = run(kernel_full(icmp, bop, pp, 5, 3), [5, 3])
    good = u == exp_u and v == exp_v
    ok &= good
    if not good:
        print(f"FAIL full {icmp}.{bop} Pp={pp}: UP0={u} (exp {exp_u}) UP1={v} (exp {exp_v})")
print("ok  full form: UPu = comp bop UPp, UPv = !comp bop UPp (11 cases)")

# ---- imm form ----
for icmp, imm, exp in [("GT", 4, 1), ("LT", 4, 0), ("EQ", 5, 1)]:
    got = run(kernel_simple(icmp, imm), [5, 0])
    good = got == exp
    ok &= good
    if not good:
        print(f"FAIL imm {icmp} 5,0x{imm:X}: {got} (exp {exp})")
print("ok  imm form: 3 cases")

print("\n=== UISETP semantic verification: ALL OK ===" if ok else "\n=== UISETP FAILURES ===")
sys.exit(0 if ok else 1)
