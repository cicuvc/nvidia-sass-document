import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# VOTEU — uniform warp vote / ballot (udp_pipe; verified SM120, RTX 5090)
#
#   VOTEU[.ALL|.ANY|.EQ] URd, UPu, [!]Pp    (0x886)
#
#   URd = ballot mask: bit L = 1 if lane L's effective Pp is true
#        (NOT the VOTE-style 0xFFFFFFFF/0 reduction mirror!)
#   UPu = the vote reduction result over the 32 lanes:
#        ALL: all lanes true; ANY: any true; EQ: all lanes equal.
# ---------------------------------------------------------------------------

REF = [
    (0x0000000000ff7886, 0x000fca0003800100),  # VOTEU.ANY UP0, PT (URd=URZ)
    (0x0000000000047886, 0x000fca0000000000),  # VOTEU.ALL UR4, UP0, P0
    (0x0000000000047886, 0x000fca0004000200),  # VOTEU.EQ UR4, UP0, !P0
]
flat = assemble_flat("""VOTEU.ANY UP0, PT;[7:7:{}:5:1]
VOTEU.ALL UR4, UP0, P0;[7:7:{}:5:1]
VOTEU.EQ UR4, UP0, !P0;[7:7:{}:5:1]
""")
from archutil import same_as_capture
_pins = same_as_capture("sm120")
ok = True
if not _pins:
    print("info byte-exact REF vectors captured on sm120 — skipped under", __import__('assembler.arch', fromlist=['x']).current().name)
for i, enc in enumerate(flat):
    good = (enc == REF[i]) if _pins else True
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(voteu, predline):
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    S2R R2, SR_TID.X;[0:7:{{}}:5:1]
    {predline}
    UISETP.F UP0, UR6, UR8;[7:7:{{}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP0;[7:7:{{}}:5:1]
    {voteu}[7:7:{{0}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UP2UR UR18, UPR;[7:7:{{}}:5:1]
    UP2UR UR17, UPR;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    UMOV UR14, UR17;[7:7:{{}}:5:1]
    IADD3 R3, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x4], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(voteu, predline):
    mod = build(kernel(voteu, predline))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(32,), args=[0, 0, d])
    mod.synchronize()
    urd, upr = struct.unpack("<2I", mod.device_read(d, 8))
    mod.devmem_free(d)
    return urd, upr & 1


try:
    run("VOTEU.ANY UR16, UP0, P0;", "ISETP.LT P0, R2, 0x8;[7:7:{0}:13:1]")
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# tid<8 -> 8 lanes true (ballot 0xFF).
for op, exp_u in [("ANY", 1), ("ALL", 0), ("EQ", 0)]:
    for neg in ("", "!"):
        urd, up0 = run(f"VOTEU.{op} UR16, UP0, {neg}P0;",
                       "ISETP.LT P0, R2, 0x8;[7:7:{0}:13:1]")
        ballot = 0xFF if not neg else 0xFFFFFF00
        good = urd == ballot and up0 == exp_u
        ok &= good
        print(f"{'ok ' if good else 'FAIL'} {op} {neg or ''}P0: ballot=0x{urd:08X} UP0={up0} (exp 0x{ballot:08X},{exp_u})")

# all-true / all-false / half.
cases = [
    ("VOTEU.ALL UR16, UP0, P0;", "ISETP.T P0, RZ, RZ;[7:7:{0}:13:1]", 0xFFFFFFFF, 1, "ALL all-true"),
    ("VOTEU.ALL UR16, UP0, P0;", "ISETP.F P0, RZ, RZ;[7:7:{0}:13:1]", 0x00000000, 0, "ALL all-false"),
    ("VOTEU.EQ UR16, UP0, P0;", "ISETP.T P0, RZ, RZ;[7:7:{0}:13:1]", 0xFFFFFFFF, 1, "EQ all-true"),
    ("VOTEU.ANY UR16, UP0, P0;", "ISETP.F P0, RZ, RZ;[7:7:{0}:13:1]", 0x00000000, 0, "ANY all-false"),
    ("VOTEU.EQ UR16, UP0, P0;", "ISETP.LT P0, R2, 0x10;[7:7:{0}:13:1]", 0x0000FFFF, 0, "EQ half"),
]
for voteu, pred, exp_ballot, exp_u, lab in cases:
    urd, up0 = run(voteu, pred)
    good = urd == exp_ballot and up0 == exp_u
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lab:12s}: ballot=0x{urd:08X} UP0={up0} (exp 0x{exp_ballot:08X},{exp_u})")

print("\n=== VOTEU semantic verification: ALL OK ===" if ok else "\n=== VOTEU FAILURES ===")
sys.exit(0 if ok else 1)
