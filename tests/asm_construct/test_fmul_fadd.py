import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assembler import assemble, CudaModule
from fma_ref import fma32, is_denorm_bits

# ---------------------------------------------------------------------------
# FMUL / FADD — FP32 multiply / add, bit-level semantic verification on SM120.
#
# Models (single rounding, from fma_ref):
#   FMUL  Rd = round(Ra * Rb)        = fma32(a, b, +0) with the exact-zero
#                                      sign forced to (sa ^ sb) (the +0 addend
#                                      would otherwise apply the zero-SUM rule)
#   FADD  Rd = round(Ra + Rc)        = fma32(a, 1.0, c)
#
# Modifiers: rounding [79:78] RN/RM/RP/RZ; FMUL fmz bits [80],[76]
# (nofmz/FMZ/FTZ, FMZ==FTZ empirically like FFMA); FADD ftz bit (FTZ only);
# FMUL scale [86:84] M2/M4/M8 (x2/x4/x8) and D2/D4/D8 (/2//4//8) — exact
# power-of-2 scaling applied to the result.
# ---------------------------------------------------------------------------

NAN = 0x7FFFFFFF
SCALE = {"": 0, ".M2": 1, ".M4": 2, ".M8": 3, ".D2": -1, ".D4": -2, ".D8": -3}


def fmul32(a, b, rnd="RN", ftz=False):
    """FMUL model: round(a*b); exact-zero product keeps the multiply sign."""
    if ftz:
        a = a & 0x80000000 if is_denorm_bits(a) else a
        b = b & 0x80000000 if is_denorm_bits(b) else b
    if a == 0 or b == 0:
        return ((a >> 31) ^ (b >> 31)) << 31
    return fma32(a, b, 0, rnd=rnd, ftz=ftz)


def scale_bits(v, k):
    """Apply FMUL scale: multiply/divide by 2^k via exact exponent shift."""
    if k == 0:
        return v
    s = v & 0x80000000
    e = (v >> 23) & 0xFF
    m = v & 0x7FFFFF
    if e == 0xFF:                       # inf / nan unchanged
        return v
    e2 = e + k
    if e2 >= 0xFF:                      # overflow to inf
        return s | 0x7F800000
    if e2 <= 0:
        # underflow: exact power-of-2 may still be a denormal
        shift = 1 - e2
        mant = (1 << 23) | m
        mant >>= shift
        if mant == 0:
            return s
        return s | mant                 # denormal
    return s | (e2 << 23) | m


def fadd32(a, c, rnd="RN", ftz=False):
    return fma32(a, 0x3F800000, c, rnd=rnd, ftz=ftz)


# (kind, label, a, b/c, modifier, expected)  kind in {MUL, ADD, MULSCALE}
cases = []
def addM(label, a, b, mod, exp): cases.append(("MUL", label, a, b, mod, exp))
def addA(label, a, c, mod, exp): cases.append(("ADD", label, a, c, mod, exp))
def addS(label, a, b, mod, exp): cases.append(("MULS", label, a, b, mod, exp))

# ---- FMUL exact + rounding ------------------------------------------------
addM("exact",  0x3FC00000, 0x40000000, "", 0x40400000)       # 1.5*2 = 3
addM("exact2", 0x40400000, 0x3F800000, "", 0x40400000)       # 3*1 = 3
addM("tie-even", 0x3F800001, 0x3F800001, "RN", 0x3F800002)   # (1+2^-23)^2
addM("tie-even", 0x3F800001, 0x3F800001, "RM", 0x3F800002)
addM("tie-even", 0x3F800001, 0x3F800001, "RP", 0x3F800003)
addM("tie-even", 0x3F800001, 0x3F800001, "RZ", 0x3F800002)
addM("subhalf", 0x3F800001, 0x3F7FFFFF, "RN", 0x3F800000)    # (1+2^-23)(1-2^-23)
addM("subhalf", 0x3F800001, 0x3F7FFFFF, "RM", 0x3F800000)
addM("subhalf", 0x3F800001, 0x3F7FFFFF, "RP", 0x3F800001)
addM("subhalf", 0x3F800001, 0x3F7FFFFF, "RZ", 0x3F800000)

# ---- FMUL overflow / underflow --------------------------------------------
addM("ovf-pos", 0x7F000000, 0x40000000, "RN", 0x7F800000)    # 2^127 * 2
addM("ovf-pos", 0x7F000000, 0x40000000, "RM", 0x7F7FFFFF)
addM("ovf-pos", 0x7F000000, 0x40000000, "RZ", 0x7F7FFFFF)
addM("den-in",  0x00000001, 0x3F800000, "", 0x00000001)      # 2^-149 * 1
addM("den-in",  0x00000001, 0x3F800000, "FTZ", 0)
addM("den-in",  0x00000001, 0x3F800000, "FMZ", 0)
addM("den-out", 0x20000000, 0x14800000, "", 0x00000001)      # 2^-63 * 2^-86
addM("den-out", 0x20000000, 0x14800000, "FTZ", 0)
addM("underflow", 0x00000001, 0x00000001, "", 0)             # 2^-298

# ---- FMUL zero signs (product sign, NOT the +0-sum rule) ------------------
addM("z-neg0",  0xC0000000, 0x00000000, "", 0x80000000)      # -2 * +0 = -0
addM("z-pos0",  0x00000000, 0x80000000, "", 0x80000000)      # +0 * -0 = -0
addM("z-pos0",  0x00000000, 0x80000000, "RM", 0x80000000)    # product sign, not RM rule
addM("z-negneg", 0x80000000, 0x80000000, "", 0x00000000)     # -0 * -0 = +0

# ---- FMUL inf / nan -------------------------------------------------------
addM("inf-pos", 0x7F800000, 0x3F800000, "", 0x7F800000)
addM("inf-0",   0x7F800000, 0x00000000, "", NAN)
addM("nan",     0x7FAAAAAA, 0x3F800000, "", NAN)

# ---- FMUL scale (exact power-of-2) ---------------------------------------
addS("M2", 0x3F800000, 0x40000000, ".M2", 0x40800000)        # 1*2=2 *2 = 4
addS("M4", 0x3F800000, 0x40000000, ".M4", 0x41000000)        # 8
addS("D2", 0x3F800000, 0x40000000, ".D2", 0x3F800000)        # 1
addS("D4", 0x3F800000, 0x40000000, ".D4", 0x3F000000)        # 0.5
addS("ovf-M8", 0x7F000000, 0x40000000, ".M8", 0x7F800000)    # 2^127*2*8 -> inf

# ---- FADD rounding --------------------------------------------------------
addA("exact",  0x3FC00000, 0x3F000000, "", 0x40000000)       # 1.5+0.5 = 2
addA("tie-even", 0x3F800001, 0x33800000, "RN", 0x3F800002)   # 1+2^-23 + 2^-24
addA("tie-even", 0x3F800001, 0x33800000, "RM", 0x3F800001)
addA("tie-even", 0x3F800001, 0x33800000, "RP", 0x3F800002)
addA("tie-even", 0x3F800001, 0x33800000, "RZ", 0x3F800001)
addA("subhalf", 0x3F800001, 0x33000000, "RN", 0x3F800001)    # 1+2^-23 + 2^-25
addA("subhalf", 0x3F800001, 0x33000000, "RP", 0x3F800002)

# ---- FADD specials --------------------------------------------------------
addA("ovf-pos", 0x7F000000, 0x7F000000, "RN", 0x7F800000)    # 2^127 + 2^127
addA("ovf-pos", 0x7F000000, 0x7F000000, "RM", 0x7F7FFFFF)
addA("z-cancel", 0x3F800000, 0xBF800000, "RN", 0)            # 1 + -1 = +0
addA("z-cancel", 0x3F800000, 0xBF800000, "RM", 0x80000000)
addA("den-in", 0x00000001, 0x3F800000, "", 0x3F800000)       # denormal + 1 = 1
addA("den-in", 0x00000001, 0x3F800000, "FTZ", 0x3F800000)
addA("den-add", 0x20000000, 0x14800000, "", 0x20000001)      # 2^-63 + 2^-86 = 2^-63+1ulp
addA("den-out", 0x00000001, 0x00000001, "", 0x00000002)      # 2^-149+2^-149
addA("den-out", 0x00000001, 0x00000001, "FTZ", 0)
addA("nan", 0x7F800000, 0xFF800000, "", NAN)                 # inf + -inf

# ---- random battery (expected from the model) -----------------------------
import random
random.seed(1234)
for i in range(20):
    a = random.getrandbits(32) & 0xFFFFFFFF
    b = random.getrandbits(32) & 0xFFFFFFFF
    for mode in ("", "RM", "RP", "RZ", "FTZ", "FMZ"):
        m = f".{mode}" if mode else ""
        exp = fmul32(a, b, rnd=("RN" if mode in ("", "FTZ", "FMZ") else mode),
                     ftz=(mode in ("FTZ", "FMZ")))
        addM(f"r{i}-{mode or 'RN'}", a, b, m, exp)
for i in range(20):
    a = random.getrandbits(32) & 0xFFFFFFFF
    c = random.getrandbits(32) & 0xFFFFFFFF
    for mode in ("", "RM", "RP", "RZ", "FTZ"):
        m = f".{mode}" if mode else ""
        exp = fadd32(a, c, rnd=("RN" if mode in ("", "FTZ") else mode),
                     ftz=(mode == "FTZ"))
        addA(f"r{i}-{mode or 'RN'}", a, c, m, exp)

# ---------------------------------------------------------------------------
# Build kernel (stable multi-case structure)
# ---------------------------------------------------------------------------
lines = ["#fn fm_test(out<1024>) {",
         "    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]",
         "    LDC.64 R6, #param(out);[0:7:{}:1:0]"]
def rrr(kind, a, b, mod):
    m = mod if not mod or mod.startswith(".") else "." + mod
    if kind == "MUL":
        return f"FMUL{m} R4, R10, R11;[7:7:{{}}:8:1]"
    if kind == "ADD":
        return f"FADD{m} R4, R10, R11;[7:7:{{}}:8:1]"
    return f"FMUL{m} R4, R10, R11;[7:7:{{}}:8:1]"
for i, (kind, label, a, b, mod, exp) in enumerate(cases):
    lines += ["    MOV32I R10, 0x%08X;[7:7:{}:5:1]" % a]
    lines += ["    MOV32I R11, 0x%08X;[7:7:{}:5:1]" % b]
    lines.append("    " + rrr(kind, a, b, mod))
    lines.append("    MOV R20, RZ;[7:7:{}:15:1]")
    lines.append(f"    STG.E desc[UR4][R6.64+0x{i*4:X}], R4;[0:1:{{0}}:1:0]")
lines += ["    EXIT;[7:7:{}:5:0]",
          "}"]

cubin = assemble("\n".join(lines))
Path("x.cubin").write_bytes(cubin)

# ---------------------------------------------------------------------------
# Run and compare
# ---------------------------------------------------------------------------
mod = CudaModule(cubin)
d = mod.devmem_alloc(4 * len(cases))
mod.launch("fm_test", grid=(1,), block=(1,), args=[d])
mod.synchronize()
vals = struct.unpack(f"<{len(cases)}I", mod.device_read(d, 4 * len(cases)))
mod.devmem_free(d)

def expected(kind, a, b, mod, exp):
    if exp is not None:
        return exp
    mode = mod.lstrip(".")
    if kind == "MUL":
        return fmul32(a, b, rnd=("RN" if mode in ("", "FTZ", "FMZ") else mode),
                      ftz=(mode in ("FTZ", "FMZ")))
    if kind == "ADD":
        return fadd32(a, b, rnd=("RN" if mode in ("", "FTZ") else mode),
                      ftz=(mode == "FTZ"))
    # MULS: FMUL + scale
    k = SCALE[mod]
    return scale_bits(fmul32(a, b, "RN"), k)

ok = True
fails = 0
for (kind, label, a, b, mod, exp), got in zip(cases, vals):
    e = expected(kind, a, b, mod, exp)
    if got != e:
        ok = False
        fails += 1
        if fails <= 12:
            print(f"FAIL {kind} {label:<10} {mod:<5} a={a:08x} b={b:08x} "
                  f"got={got:08x} exp={e:08x}")
print(f"=== {len(cases)} cases, {'ALL OK' if ok else f'{fails} FAILURES'} ===")
print("FMUL: round(Ra*Rb) single rounding, product-sign zeros (not +0-sum rule)")
print("FMUL scale M2/M4/M8 x2/4/8, D2/D4/D8 /2/4/8 (exact power-of-2)")
print("FMUL FMZ == FTZ (flush denormal inputs+result); NaN -> 0x7fffffff")
print("FADD: round(Ra+Rc) single rounding; FTZ flushes; z-cancel +0/-0 per mode")
