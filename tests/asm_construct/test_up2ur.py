import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UP2UR — uniform predicate to uniform register (udp_pipe; verified SM120)
#
#   UP2UR[.B0|.B1|.B2|.B3] URd, UPR[, URa, imm32|URb]
#     0x1883 imm/simple (ALT) / 0x1c83 URb form
#
# Silicon semantics (RTX 5090):
#   * UPR is NOT a fixed single predicate — it reads the WHOLE uniform
#     predicate register file as a bitmask: bit N = uniform predicate UPN
#     (UP0..UP6).  Written by UISETP/VOTEU (any uniform-predicate write).
#   * simple:  URd = UPR bitmask (e.g. UP0 -> 1, UP1 -> 2, UP3 -> 8).
#   * .Bx:     the mask is inserted into byte lane x of URd
#              (B1 -> <<8, B2 -> <<16, B3 -> <<24).
#   * imm/URb: URd = URa + (UPR_mask & imm/URb)  — the third operand is
#              AND-ed with the predicate bitmask and added directly.
#
# Caveat: uniform predicates PERSIST across launches (like the uniform
# register file), so tests clear UP0..UP3 first and read UPR right after
# setting the target predicate.
# ---------------------------------------------------------------------------

REF = [
    (0x000000ffff047883, 0x000fca0008000000),  # UP2UR UR4, UPR (B0)
    (0x000000ffff047883, 0x000fca0008001000),  # UP2UR.B1 UR4, UPR
    (0x0000012306047883, 0x000fca0008000000),  # UP2UR UR4, UPR, UR6, 0x123
    (0x0000000806047c83, 0x000fca0008000000),  # UP2UR UR4, UPR, UR6, UR8
]
flat = assemble_flat("""UP2UR UR4, UPR;[7:7:{}:5:1]
UP2UR.B1 UR4, UPR;[7:7:{}:5:1]
UP2UR UR4, UPR, UR6, 0x123;[7:7:{}:5:1]
UP2UR UR4, UPR, UR6, UR8;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(inst, up2ur="    UP2UR UR16, UPR;[7:7:{}:5:1]\n"):
    """Clear UP0..UP3, set one predicate per `inst`, read UPR via UP2UR."""
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
    LDCU UR8, #param(b);[3:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR8;[7:7:{{3}}:5:1]
    UISETP.F UP0, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.F UP1, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.F UP2, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.F UP3, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP3;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP2;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP1;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP0;[7:7:{{2,3}}:5:1]
{inst}{up2ur}
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a=0x1000, b=0x22222222, up2ur="    UP2UR UR16, UPR;[7:7:{}:5:1]\n"):
    mod = build(kernel(inst, up2ur=up2ur))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[a, b, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


try:
    run("")
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# Simple form: UPR = uniform-predicate bitmask.
mask_cases = [
    ("", 0x0, "clear-all -> 0"),
    ("    UISETP.T UP0, UR6, UR8;[7:7:{2,3}:5:1]\n", 0x1, "UP0 -> 1"),
    ("    UISETP.T UP1, UR6, UR8;[7:7:{2,3}:5:1]\n", 0x2, "UP1 -> 2"),
    ("    UISETP.T UP3, UR6, UR8;[7:7:{2,3}:5:1]\n", 0x8, "UP3 -> 8"),
    ("    UISETP.T UP0, UR6, UR8;[7:7:{2,3}:5:1]\n    UISETP.T UP1, UR6, UR8;[7:7:{2,3}:5:1]\n",
     0x3, "UP0+UP1 -> 3"),
    ("    VOTEU.ANY UP2, PT;[7:7:{}:5:1]\n", 0x4, "VOTEU.ANY UP2 -> 4"),
    ("    VOTEU.ALL UP0, !PT;[7:7:{}:5:1]\n", 0x0, "VOTEU.ALL !PT -> 0"),
]
for inst, exp, lab in mask_cases:
    v = run(inst)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lab:22s} -> 0x{v:08X} (exp 0x{exp:08X})")

# .Bx byte-lane insert (UPR=1 -> mask 1).
for bm, exp, lab in [("", 0x1, "B0"), (".B1", 0x100, "B1"), (".B2", 0x10000, "B2"), (".B3", 0x1000000, "B3")]:
    src = kernel("    UISETP.T UP0, UR6, UR8;[7:7:{2,3}:5:1]\n",
                 up2ur=f"    UP2UR{bm} UR16, UPR;[7:7:{{}}:5:1]\n")
    mod = build(src)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[0x1000, 0, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} .{lab:2s} insert UPR=1   -> 0x{v:08X} (exp 0x{exp:08X})")

# imm/URb: URd = URa + (UPR_mask & operand).
for inst, a, b, exp, lab in [
    ("    UISETP.T UP0, UR6, UR8;[7:7:{2,3}:5:1]\n",
     0x1000, 0, 0x1001, "imm: UPR=1 & 0x123 = 1 -> +1"),
    ("",
     0x1000, 0, 0x1000, "imm: UPR=0 -> +0"),
    ("    UISETP.T UP0, UR6, UR8;[7:7:{2,3}:5:1]\n",
     0x1000, 0, 0x1000, "imm: UPR=1 & 0x0 = 0 -> +0"),
    ("    UISETP.T UP1, UR6, UR8;[7:7:{2,3}:5:1]\n",
     0x1000, 0, 0x1002, "imm: UPR=2 & 0x123 = 2 -> +2"),
    ("    UISETP.T UP1, UR6, UR8;[7:7:{2,3}:5:1]\n",
     0x1000, 0, 0x1000, "imm: UPR=2 & 0x1 = 0 -> +0"),
    ("    UISETP.T UP0, UR6, UR8;[7:7:{2,3}:5:1]\n",
     0x1000, 0x1, 0x1001, "URb: UPR=1 & 1 = 1 -> +1"),
    ("    UISETP.T UP0, UR6, UR8;[7:7:{2,3}:5:1]\n",
     0x1000, 0x22222222, 0x1000, "URb: UPR=1 & 0x22222222 = 0 -> +0"),
    ("    UISETP.T UP1, UR6, UR8;[7:7:{2,3}:5:1]\n",
     0x1000, 0x3, 0x1002, "URb: UPR=2 & 3 = 2 -> +2"),
]:
    up2ur = {
        "imm: UPR=1 & 0x123 = 1 -> +1": "    UP2UR UR16, UPR, UR6, 0x123;[7:7:{}:5:1]\n",
        "imm: UPR=0 -> +0": "    UP2UR UR16, UPR, UR6, 0x123;[7:7:{}:5:1]\n",
        "imm: UPR=1 & 0x0 = 0 -> +0": "    UP2UR UR16, UPR, UR6, 0x0;[7:7:{}:5:1]\n",
        "imm: UPR=2 & 0x123 = 2 -> +2": "    UP2UR UR16, UPR, UR6, 0x123;[7:7:{}:5:1]\n",
        "imm: UPR=2 & 0x1 = 0 -> +0": "    UP2UR UR16, UPR, UR6, 0x1;[7:7:{}:5:1]\n",
        "URb: UPR=1 & 1 = 1 -> +1": "    UP2UR UR16, UPR, UR6, UR8;[7:7:{}:5:1]\n",
        "URb: UPR=1 & 0x22222222 = 0 -> +0": "    UP2UR UR16, UPR, UR6, UR8;[7:7:{}:5:1]\n",
        "URb: UPR=2 & 3 = 2 -> +2": "    UP2UR UR16, UPR, UR6, UR8;[7:7:{}:5:1]\n",
    }[lab]
    v = run(inst, a=a, b=b, up2ur=up2ur)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lab:30s} -> 0x{v:08X} (exp 0x{exp:08X})")

print("\n=== UP2UR semantic verification: ALL OK ===" if ok else "\n=== UP2UR FAILURES ===")
sys.exit(0 if ok else 1)
