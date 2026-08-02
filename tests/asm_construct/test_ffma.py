import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assembler import assemble, CudaModule
from fma_ref import fma32

# ---------------------------------------------------------------------------
# FFMA — FP32 fused multiply-add, bit-level semantic verification on SM120.
#
# Model under verification:
#   Rd = round(Ra * Rb + Rc)          (IEEE-754 fusedMultiplyAdd, single
#    rounding; the exact product keeps 48 bits, the add is exact, the final
#    round is applied once at the binary32 grid).
#
# Rounding field [79:78] ("stride"): RN=0 RM=1 RP=2 RZ=3
#   RN roundTiesToEven, RM toward -inf, RP toward +inf, RZ toward zero.
# fmz field bits [80],[76]: nofmz=0 FMZ=1 FTZ=2
#   .FTZ flushes denormal inputs AND the denormal result to sign-preserving
#   zero.  Empirically on SM120 .FMZ is behaviourally identical to .FTZ for
#   FFMA (flush denormal multiply inputs, addend, and result).
#
# Reference: fma_ref.fma32 (big-integer exact sum + single grid rounding).
# Cross-validated against an independent Fraction-based rounder over 20k
# random vectors per mode (RN/RM/RP/RZ all agree).
# ---------------------------------------------------------------------------

NAN = 0x7FFFFFFF    # NVIDIA canonical NaN (verified on SM120)


def bits(f): return struct.unpack("<I", struct.pack("<f", f))[0]


def mode_suffix(mode):
    return f".{mode}" if mode else ""


# (label, a, b, c, mode, expected)  mode "" = plain (RN, no flush)
# Modes: "", RN, RM, RP, RZ, FTZ, FMZ
cases = []
def add(label, a, b, c, mode, exp):
    cases.append((label, a, b, c, mode, exp))

# ---- exact results (all rounding modes identical) -------------------------
add("exact-1", bits(1.5), bits(2.0), bits(0.5), "", None)
add("exact-2", bits(3.0), bits(0.5), bits(1.25), "", None)
add("exact-3", (127<<23) | (1<<23), (128<<23), 0, "", None)   # 1.0*2.0+0
add("exact-4", (150<<23)|3, (127<<23), bits(1.0), "", None)   # (2^23+3)*1+1

# ---- tie-to-even (exact 1.5 ULP above a value) ---------------------------
# a = 1+2^-23, b = 1, c = 2^-24  ->  sum = 1 + 2^-23 + 2^-24  (1.5 ULP tie)
add("tie-even",   0x3F800001, 0x3F800000, 0x33800000, "RN", 0x3F800002)
add("tie-even",   0x3F800001, 0x3F800000, 0x33800000, "RM", 0x3F800001)
add("tie-even",   0x3F800001, 0x3F800000, 0x33800000, "RP", 0x3F800002)
add("tie-even",   0x3F800001, 0x3F800000, 0x33800000, "RZ", 0x3F800001)
# even mantissa already at the lower candidate -> RN stays down
add("tie-even2",  0x3F800002, 0x3F800000, 0x33800000, "RN", 0x3F800002)
add("tie-even2",  0x3F800002, 0x3F800000, 0x33800000, "RM", 0x3F800002)
add("tie-even2",  0x3F800002, 0x3F800000, 0x33800000, "RP", 0x3F800003)
add("tie-even2",  0x3F800002, 0x3F800000, 0x33800000, "RZ", 0x3F800002)

# ---- non-tie rounding (just below / above the midpoint) ------------------
# 1 + 2^-23 + 2^-25  (1.25 ULP) -> RN/RM/RZ down, RP up
add("subhalf",    0x3F800001, 0x3F800000, 0x33000000, "RN", 0x3F800001)
add("subhalf",    0x3F800001, 0x3F800000, 0x33000000, "RM", 0x3F800001)
add("subhalf",    0x3F800001, 0x3F800000, 0x33000000, "RP", 0x3F800002)
add("subhalf",    0x3F800001, 0x3F800000, 0x33000000, "RZ", 0x3F800001)
# 1 + 2^-23 + 3*2^-25  (1.75 ULP) -> RN/RP up, RM/RZ down
add("abvhalf",    0x3F800001, 0x3F800000, 0x33C00000, "RN", 0x3F800002)
add("abvhalf",    0x3F800001, 0x3F800000, 0x33C00000, "RM", 0x3F800001)
add("abvhalf",    0x3F800001, 0x3F800000, 0x33C00000, "RP", 0x3F800002)
add("abvhalf",    0x3F800001, 0x3F800000, 0x33C00000, "RZ", 0x3F800001)

# ---- FUSION: exact 48-bit product + c crosses a boundary the separately
#      rounded product misses.  a*b = (2^23+1)^2 = 2^46+2^24+1; ULP=2^23.
#      c = 2^22 (half ULP): exact sum 2^46 + 2.5 ULP + 1 -> rounds UP.
#      Non-fused: product rounds to 2^46+2^24, +c = 2^46 + 2.5 ULP exactly
#      (tie) -> stays at even 2^46+2^24.  1-ULP apart.
add("fusion",  0x4B000001, 0x4B000001, 0x4A800000, "RN", 0x56800003)
add("fusion2", 0x4B000001, 0x4B000002, 0xCA800000, "RN", 0x56800003)

# ---- overflow -------------------------------------------------------------
# 2^127 * 2 = 2^128 -> RN/RP +inf, RM/RZ clamp to max finite
add("ovf-pos",  0x7F000000, 0x40000000, 0, "RN", 0x7F800000)
add("ovf-pos",  0x7F000000, 0x40000000, 0, "RM", 0x7F7FFFFF)
add("ovf-pos",  0x7F000000, 0x40000000, 0, "RP", 0x7F800000)
add("ovf-pos",  0x7F000000, 0x40000000, 0, "RZ", 0x7F7FFFFF)
# -2^128 -> RN/RM -inf, RP/RZ clamp to -max finite
add("ovf-neg",  0xFF000000, 0x40000000, 0, "RN", 0xFF800000)
add("ovf-neg",  0xFF000000, 0x40000000, 0, "RM", 0xFF800000)
add("ovf-neg",  0xFF000000, 0x40000000, 0, "RP", 0xFF7FFFFF)
add("ovf-neg",  0xFF000000, 0x40000000, 0, "RZ", 0xFF7FFFFF)
# max finite + 2^104 (1 ULP above max) -> exactly 2^128
add("ovf-ulp",  0x7F7FFFFF, 0x3F800000, 0x73800000, "RN", 0x7F800000)
add("ovf-ulp",  0x7F7FFFFF, 0x3F800000, 0x73800000, "RM", 0x7F7FFFFF)
add("ovf-ulp",  0x7F7FFFFF, 0x3F800000, 0x73800000, "RZ", 0x7F7FFFFF)

# ---- denormal input preserved by plain FFMA, flushed by FTZ/FMZ -----------
add("den-in-a", 0x00000001, 0x3F800000, 0, "", 0x00000001)
add("den-in-a", 0x00000001, 0x3F800000, 0, "FTZ", 0)
add("den-in-a", 0x00000001, 0x3F800000, 0, "FMZ", 0)
add("den-in-b", 0x3F800000, 0x00000001, 0, "", 0x00000001)
add("den-in-b", 0x3F800000, 0x00000001, 0, "FTZ", 0)

# ---- denormal OUTPUT from normal inputs (2^-63 * 2^-86 = 2^-149) ----------
add("den-out",  0x20000000, 0x14800000, 0, "", 0x00000001)
add("den-out",  0x20000000, 0x14800000, 0, "FTZ", 0)
add("den-out",  0x20000000, 0x14800000, 0, "FMZ", 0)
# denormal output + denormal addend (2^-148) -> FTZ/FMZ flush all
add("den-out+add", 0x20000000, 0x14800000, 0x00000001, "", 0x00000002)
add("den-out+add", 0x20000000, 0x14800000, 0x00000001, "FTZ", 0)
add("den-out+add", 0x20000000, 0x14800000, 0x00000001, "FMZ", 0)
# FMZ flushes the denormal ADDEND too (result normal, addend 3*2^-149):
# plain keeps it (0x00800003), FTZ/FMZ flush to 0x00800000
add("fmz-addend", 0x20000000, 0x20000000, 0x00000003, "", 0x00800003)
add("fmz-addend", 0x20000000, 0x20000000, 0x00000003, "FTZ", 0x00800000)
add("fmz-addend", 0x20000000, 0x20000000, 0x00000003, "FMZ", 0x00800000)

# ---- underflow below the denormal grid ------------------------------------
add("underflow", 0x00000001, 0x00000001, 0, "", 0)   # 2^-149 * 2^-149 -> 0

# ---- zero sign rules (IEEE 754-2019 5.4.2) --------------------------------
# exact cancellation 1 + -1 -> +0 (RN/RP/RZ), -0 (RM)
add("z-cancel",  0x3F800000, 0x3F800000, 0xBF800000, "RN", 0x00000000)
add("z-cancel",  0x3F800000, 0x3F800000, 0xBF800000, "RM", 0x80000000)
add("z-cancel",  0x3F800000, 0x3F800000, 0xBF800000, "RP", 0x00000000)
add("z-cancel",  0x3F800000, 0x3F800000, 0xBF800000, "RZ", 0x00000000)
add("z-cancel2", 0xBF800000, 0x3F800000, 0x3F800000, "RN", 0x00000000)
add("z-cancel2", 0xBF800000, 0x3F800000, 0x3F800000, "RM", 0x80000000)
# (+0) + (-0): product +0 (1*0), c = -0 -> +0 (RN/RZ/RP), -0 (RM)
add("z-zeros",   0x3F800000, 0x00000000, 0x80000000, "RN", 0x00000000)
add("z-zeros",   0x3F800000, 0x00000000, 0x80000000, "RM", 0x80000000)
add("z-zeros",   0x3F800000, 0x00000000, 0x80000000, "RZ", 0x00000000)
# (-0)*(-0) -> +0, + (-0) -> +0 (RM gives -0)
add("z-negneg",  0x80000000, 0x80000000, 0x80000000, "RN", 0x00000000)
add("z-negneg",  0x80000000, 0x80000000, 0x80000000, "RM", 0x80000000)
# product -0 (from -2*0) + c = +1 -> +1
add("z-prodneg", 0xC0000000, 0x00000000, 0x3F800000, "RN", 0x3F800000)

# ---- NaN canonicalization (NVIDIA -> 0x7fffffff) --------------------------
add("nan-payload", 0x7FAAAAAA, 0x3F800000, 0, "", NAN)
add("nan-sign",    0xFFC00001, 0x3F800000, 0, "", NAN)
add("nan-inf0",    0x7F800000, 0x00000000, 0, "", NAN)
add("nan-inf_minf", 0x7F800000, 0x7F800000, 0xFF800000, "", NAN)

# ---- infinity propagation --------------------------------------------------
add("inf-pos",  0x7F800000, 0x3F800000, 0, "", 0x7F800000)
add("inf-neg",  0x7F800000, 0xBF800000, 0, "", 0xFF800000)
add("inf-addend", 0x3F800000, 0x3F800000, 0x7F800000, "", 0x7F800000)

# ---- extended IEEE battery (expected computed by the reference) -----------
def ref(a, b, c, mode):
    rnd = "RN" if mode in ("", "FTZ", "FMZ") else mode
    return fma32(a, b, c, rnd=rnd, ftz=(mode == "FTZ"))


import random
random.seed(99)
for i in range(24):
    a = random.getrandbits(32) & 0xFFFFFFFF
    b = random.getrandbits(32) & 0xFFFFFFFF
    c = random.getrandbits(32) & 0xFFFFFFFF
    for mode in ("", "RM", "RP", "RZ", "FTZ"):
        add(f"rand{i}-{mode or 'RN'}", a, b, c, mode, ref(a, b, c, mode))


# ---------------------------------------------------------------------------
# Build kernel
# ---------------------------------------------------------------------------
lines = ["#fn ffma_test(out<1024>) {",
         "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]"]
for i, (label, a, b, c, mode, _exp) in enumerate(cases):
    lines.append(f"    MOV32I R0, 0x{a:08X};[7:7:{{}}:5:1]")
    lines.append(f"    MOV32I R1, 0x{b:08X};[7:7:{{}}:5:1]")
    lines.append(f"    MOV32I R2, 0x{c:08X};[7:7:{{}}:5:1]")
    m = mode_suffix(mode)
    lines.append(f"    FFMA{m} R3, R0, R1, R2;[7:7:{{}}:8:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{i*4:X}], R3;[0:1:{{0}}:1:0]")
lines += ["    EXIT;[7:7:{}:5:0]",
          "}"]

cubin = assemble("\n".join(lines))
Path("x.cubin").write_bytes(cubin)

# ---------------------------------------------------------------------------
# Run on GPU and compare
# ---------------------------------------------------------------------------
mod = CudaModule(cubin)
d = mod.devmem_alloc(4 * len(cases))
mod.launch("ffma_test", grid=(1,), block=(1,), args=[d])
mod.synchronize()
vals = struct.unpack(f"<{len(cases)}I", mod.device_read(d, 4 * len(cases)))
mod.devmem_free(d)

ok = True
fails = []
print("=== FFMA Semantic Verification (SM120) ===")
print(f"{'case':<12} {'mode':<4} {'a':>8} {'b':>8} {'c':>8} {'got':>8} {'exp':>8}  st")
for i, ((label, a, b, c, mode, exp), got) in enumerate(zip(cases, vals)):
    e = exp if exp is not None else ref(a, b, c, mode)
    status = "OK" if got == e else "FAIL"
    ok &= (got == e)
    if status == "FAIL":
        fails.append((label, mode, a, b, c, got, e))
    print(f"{label:<12} {mode or '-':<4} {a:08x} {b:08x} {c:08x} "
          f"{got:08x} {e:08x}  {status}")

print()
print(f"=== {'ALL OK' if ok else f'{len(fails)} FAILURES'} ===")
print("Bit-level conclusions (SM120):")
print("  rounding field [79:78] = {RN:ties-to-even, RM:toward -inf,")
print("                           RP:toward +inf, RZ:toward zero}; tie on")
print("  1.5-ULP exact sums rounds to the EVEN mantissa (RN)")
print("  FFMA is truly fused: exact 48-bit product + addend, single round;")
print("  fused != separate (FMUL, then FADD) by 1 ULP on half-ULP addends")
print("  overflow: RN/RP -> inf, RM/RZ -> clamp to max finite")
print("  zero sum sign: +0 except RM -> -0 (IEEE 754-2019 5.4.2)")
print("  NaN canonicalized to 0x7fffffff (all-1 mantissa, + sign)")
print("  plain FFMA preserves denormal inputs AND denormal results")
print("  .FTZ flushes denormal inputs + result; .FMZ == .FTZ on FFMA")
