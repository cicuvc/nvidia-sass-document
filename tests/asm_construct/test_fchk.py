import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat, assemble, CudaModule

# ---------------------------------------------------------------------------
# FCHK — FP check, verified semantics on SM120 with a clean hand-built ELF.
#
# Encoding (verified): opcode 0x302 (RRR), Pu [83:81], Ra [31:24], Rb [39:32],
# Ra abs [73], Ra neg [72], Rb neg [63], Rb abs [62].  ChkMode is fixed to
# DIVIDE (0) on sm_90.  mio_pipe / DECOUPLED_RD_WR_SCBD (write scoreboard).
#
# Empirical semantics (DIVIDE mode): FCHK P0, Ra, Rb sets P0=1 ("slow path
# needed") iff a fast Newton-Raphson reciprocal-based division cannot produce
# a correctly-rounded result.  Fires when ANY of:
#   * Ra or Rb is NaN / +-Inf / +-0 / denormal
#   * |Ra| < 2^-102                (biased exp field < 25)
#   * |Rb| < 2^-125                (biased exp field < 2)
#   * |Rb| >= 2^125                (biased exp field >= 252)
#   * quotient Ra/Rb < 2^-125      (biased exp diff < -125)
#   * quotient Ra/Rb >= 2^127      (biased exp diff >= 127)
# Magnitude-based: sign of either operand is irrelevant (verified -1/2 etc).
# Negate/absolute modifiers fold into |Ra| so don't change the decision.
# ---------------------------------------------------------------------------

# --- encoding round-trip ---------------------------------------------------
lo, hi = assemble_flat('FCHK P0, R6, R7;[1:7:{}:5:1]')[0]
assert (lo >> 16) & 0xFF == 0        # no Rd
assert (lo >> 24) & 0xFF == 6        # Ra
assert (lo >> 32) & 0xFF == 7        # Rb
assert (hi >> 1) & 0x7 == 0          # Pu at [83:81]
assert lo & 0xFFF == 0x302           # opcode
print("encoding round-trip OK (opcode 0x302, Pu [83:81], Ra [31:24], Rb [39:32])")

# --- semantic probe --------------------------------------------------------
def fb(e, mant=0):     # FP32 bits for 2^e * (1 + mant/2^23)
    return ((e + 127) & 0xff) << 23 | (mant & 0x7fffff)

F = lambda b: struct.unpack("<f", struct.pack("<I", b))[0]
INF = 0x7f800000
NAN = 0x7fc00000
DEN = 1                 # smallest denormal

def run(pairs):
    lines = ["#fn k(buf<4096>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    IADD3 R4, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R4, R4, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R16, R6, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R17, R7, RZ, RZ;[7:7:{}:5:1]",
             "    LDG.E R10, desc[{UR4,UR5}][{R16,R17}];[1:7:{0}:5:1]",        # Ra, wr=SB1
             "    IADD3 R18, R10, RZ, RZ;[7:7:{1}:5:1]",
             "    LDG.E R11, desc[{UR4,UR5}][{R16,R17}+0x100];[2:7:{0}:5:1]",  # Rb, wr=SB2
             "    IADD3 R19, R11, RZ, RZ;[7:7:{2}:5:1]",
             "    MOV R3, 1;[7:7:{}:5:1]",
             "    FCHK P0, R10, R11;[1:7:{0}:5:1]",                   # wr=SB1
             "    SEL R22, R3, RZ, P0;[7:7:{1}:5:1]",                 # wait SB1
             "    STG.E desc[{UR4,UR5}][{R16,R17}+0x200], R22;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    init = [0] * 256
    for i, (a, b) in enumerate(pairs):
        init[i] = a
        init[64 + i] = b
    d = mod.devmem_alloc(4096)
    mod.device_write(d, struct.pack("<256I", *init))
    mod.launch("k", grid=(1,), block=(len(pairs),), args=[d])
    mod.synchronize()
    res = struct.unpack("<8I", mod.device_read(d + 0x200, 32))
    mod.devmem_free(d)
    return list(res)

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: got {got} want {want}")

ONE = fb(0)
# 1. ordinary safe divides
check("safe 1/2", run([(ONE, fb(1))])[0], 0)
check("safe 2/1", run([(fb(1), ONE)])[0], 0)
check("safe -1/-2", run([(fb(0, 0) | 0x80000000, fb(1, 0) | 0x80000000)])[0], 0)
check("safe 1/2^100", run([(ONE, fb(100))])[0], 0)
check("safe 2^100/1", run([(fb(100), ONE)])[0], 0)
# 2. specials
check("a=NaN", run([(NAN, ONE)])[0], 1)
check("b=NaN", run([(ONE, NAN)])[0], 1)
check("a=+Inf", run([(INF, ONE)])[0], 1)
check("b=+Inf", run([(ONE, INF)])[0], 1)
check("a=b=Inf", run([(INF, INF)])[0], 1)
check("a=+0", run([(0, ONE)])[0], 1)
check("a=-0", run([(0x80000000, ONE)])[0], 1)
check("b=0", run([(ONE, 0)])[0], 1)
check("a=b=0", run([(0, 0)])[0], 1)
check("a=denormal", run([(DEN, ONE)])[0], 1)
check("b=denormal", run([(ONE, DEN)])[0], 1)
# 3. |Ra| < 2^-102
check("a=2^-103", run([(fb(-103), ONE)])[0], 1)
check("a=2^-102*0.5", run([(fb(-103, 0x7fffff), ONE)])[0], 1)
check("a=2^-102 (edge)", run([(fb(-102), ONE)])[0], 0)
# 4. |Rb| < 2^-125
check("b=2^-126", run([(ONE, fb(-126))])[0], 1)
check("b=2^-125.9", run([(ONE, fb(-126, 0x7fffff))])[0], 1)
check("b=2^-125 (edge)", run([(ONE, fb(-125))])[0], 0)
# 5. |Rb| >= 2^125
check("b=2^125", run([(ONE, fb(125))])[0], 1)
check("b=2^125.5", run([(ONE, fb(125, 0x400000))])[0], 1)
check("b=2^124.99 (edge)", run([(ONE, fb(124, 0x7fffff))])[0], 0)
# 6. quotient >= 2^127
check("q=2^127 (a=2^127/1)", run([(fb(127), ONE)])[0], 1)
check("q=2^127 (a=2^126/2^-1)", run([(fb(126), fb(-1))])[0], 1)
check("q=2^126 (edge)", run([(fb(126), ONE)])[0], 0)
check("q=2^125 (a=2^126/2)", run([(fb(126), fb(1))])[0], 0)
# 7. quotient < 2^-125
check("q=2^-125", run([(fb(-60), fb(65))])[0], 1)
check("q=2^-125 (b)", run([(fb(-100), fb(25))])[0], 1)
check("q=2^-124 (edge)", run([(fb(-60), fb(64))])[0], 0)
# 8. magnitude-based (sign irrelevant)
check("a=-2^127", run([(fb(127) | 0x80000000, ONE)])[0], 1)
check("-1/2 safe", run([(fb(0) | 0x80000000, fb(1))])[0], 0)

# 9. negate/absolute modifiers don't change the decision (magnitude-based)
def run_mods(pairs, ra_form="R10", rb_form="R11"):
    lines = ["#fn k(buf<4096>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    IADD3 R4, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R4, R4, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R16, R6, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R17, R7, RZ, RZ;[7:7:{}:5:1]",
             "    LDG.E R10, desc[{UR4,UR5}][{R16,R17}];[1:7:{0}:5:1]",
             "    IADD3 R18, R10, RZ, RZ;[7:7:{1}:5:1]",
             "    LDG.E R11, desc[{UR4,UR5}][{R16,R17}+0x100];[2:7:{0}:5:1]",
             "    IADD3 R19, R11, RZ, RZ;[7:7:{2}:5:1]",
             "    MOV R3, 1;[7:7:{}:5:1]",
            f"    FCHK P0, {ra_form}, {rb_form};[1:7:{{0}}:5:1]",
             "    SEL R22, R3, RZ, P0;[7:7:{1}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R16,R17}+0x200], R22;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    init = [0] * 256
    for i, (a, b) in enumerate(pairs):
        init[i] = a
        init[64 + i] = b
    d = mod.devmem_alloc(4096)
    mod.device_write(d, struct.pack("<256I", *init))
    mod.launch("k", grid=(1,), block=(len(pairs),), args=[d])
    mod.synchronize()
    res = struct.unpack("<8I", mod.device_read(d + 0x200, 32))
    mod.devmem_free(d)
    return list(res)

NEG127 = (254 << 23) | 0x80000000   # -2^127 -> fires
for form in ("R10", "|R10|", "-|R10|", "-R10"):
    check(f"a=-2^127 {form}", run_mods([(NEG127, ONE)], form)[0], 1)
for form in ("R11", "|R11|", "-|R11|", "-R11"):
    check(f"b=-1 {form}", run_mods([(ONE, fb(0) | 0x80000000)], rb_form=form)[0], 0)

print(f"=== FCHK semantic probe: {'ALL OK' if ok else 'FAILED'} ===")
print("FCHK.DIVIDE fires (P0=1) for: NaN/Inf/0/denorm, |Ra|<2^-102,")
print("|Rb|<2^-125 or >=2^125, or quotient outside [2^-125, 2^127)")
