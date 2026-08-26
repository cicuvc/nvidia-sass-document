import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from archutil import adapt_source  # noqa: E402

# ---------------------------------------------------------------------------
# Bit-level precision of the tensor-core HMMA, verified against the FDA model
# of "MMA-Sim" (arXiv:2511.10909, "Bit-Accurate Reference Model of Tensor
# Cores"): Hopper HMMA.16816 uses the Fused-Dot-Add algorithm with F=25
# fractional bits in the align step (Step 3) and round-to-zero (RZ) at the
# FP32 23rd fractional bit on output (Step 5).
#
#   Step 1: special values — NaN in -> canonical NaN 0x7FFFFFFF; 0*inf -> NaN;
#           only one inf kind -> that inf; both +inf and -inf -> NaN.
#   Step 2: products exact (significand x exponent, no normalization).
#   Step 3: align products and c to e_max, truncate (RZ) to F=25 bits.
#   Step 4: fixed-point sum (order-independent, exact).
#   Step 5: normalize to FP32; |result| >= 2^128 -> inf, else RZ at bit 23.
#
# All cases use a fixed-address fragment (all 32 lanes read the same words),
# so no SR_TID addressing is involved.  a0..a3 = 4x .b32 (8 bf16/f16 A frag),
# b0..b1 = 2x .b32, c0..c3 = 4x f32.  Only D0 is observed (c0 + P, P from the
# nonzero a/b entries).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<42} {got:#x} (exp {want:#x})")


KERNEL = """#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]
    LDG.E.128 {R16,R17,R18,R19}, desc[{UR4,UR5}][{R6,R7}+0x0];[5:7:{0,1}:8:1]
    LDG.E.64 {R20,R21}, desc[{UR4,UR5}][{R6,R7}+0x10];[5:7:{0,1}:8:1]
    LDG.E.128 {R24,R25,R26,R27}, desc[{UR4,UR5}][{R6,R7}+0x20];[5:7:{0,1}:8:1]
    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]
    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]
    HMMA.16816.F32.{SRCFMT} {R28,R29,R30,R31}, {R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27};[7:7:{5}:1:0]
    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]
    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]
    IADD3 R8, R6, 0x40, RZ;[7:7:{1}:5:1]
    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R28;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""

ONE = 0x3F80          # bf16 1.0
ONE16 = 0x3C00        # f16 1.0
NAN = 0x7FC0          # bf16 NaN
NAN16 = 0x7E00        # f16 NaN
PINF = 0x7F80         # bf16 +inf
NINF = 0xFF80         # bf16 -inf
PINF16 = 0x7C00       # f16 +inf
NINF16 = 0xFC00       # f16 -inf
ZERO = 0x0000


def pair(lo, hi=ZERO):
    return (lo & 0xFFFF) | ((hi & 0xFFFF) << 16)


def fi(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def run(srcfmt, frag16):
    mod = CudaModule(assemble(adapt_source(KERNEL.replace("{SRCFMT}", srcfmt))))
    d = mod.devmem_alloc(2048 * 4)
    buf = [0] * 2048
    buf[:16] = frag16
    mod.device_write(d, struct.pack("<%dI" % 2048, *buf))
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    out = struct.unpack("<I", mod.device_read(d + 0x40, 4))[0]
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return out


def base(one):
    f = [0] * 16
    for i in range(4):
        f[i] = pair(one, one)          # a0..a3 = {1.0, 1.0}
    f[4] = pair(one, ZERO)             # b0 = {1.0, 0.0}  -> P = 4
    return f


def case(name, srcfmt, frag, want):
    check(name, run(srcfmt, frag), want)


# ============================ BF16 (HMMA.16816.F32.BF16) =====================
B = "BF16"
# RZ output (FDA Step 5): b0.lo = 3*2^-26 (bf16 0x3340) -> P = 4*3*2^-26 = 3*2^-24.
# D0 = 1.0 + 3*2^-24 = 1.0 + 1.5 ulp.  RZ -> truncate to 1 ulp = 0x3f800001.
f = base(ONE); f[4] = pair(0x3340, ZERO); f[8] = fi(1.0)
case("BF16 RZ +1.5ulp -> 1ulp", B, f, 0x3F800001)
# negative: D0 = -1.0 + 3*2^-24; RZ toward zero -> -1.0 + 1ulp(2^-23) = 0xBF7FFFFE
f = base(ONE); f[4] = pair(0x3340, ZERO); f[8] = fi(-1.0)
case("BF16 RZ -1.5ulp -> 1ulp", B, f, 0xBF7FFFFE)
# exact product sum: P = 3*2^-24 exactly representable with c0 = 0
f = base(ONE); f[4] = pair(0x3340, ZERO)
case("BF16 exact P = 3*2^-24", B, f, 0x34400000)
# c large exponent, small P survives (align + exact sum + FP32 23-bit): 2^20 + 8
f = base(ONE); f[4] = pair(0x4000, ZERO); f[8] = fi(2.0**20)   # P = 8
case("BF16 c=2^20 + P=8 -> 2^20+8", B, f, 0x49800040)
# NaN propagation -> canonical 0x7FFFFFFF
f = base(ONE); f[8] = 0x7FC00000
case("BF16 c=NaN", B, f, 0x7FFFFFFF)
f = base(ONE); f[0] = pair(NAN, ONE)
case("BF16 a0.lo=NaN", B, f, 0x7FFFFFFF)
f = base(ONE); f[4] = pair(NAN, ZERO)
case("BF16 b0.lo=NaN", B, f, 0x7FFFFFFF)
f = base(ONE); f[5] = pair(NAN, ZERO)
case("BF16 b1.lo=NaN", B, f, 0x7FFFFFFF)
# 0 * inf -> NaN
f = base(ONE); f[0] = pair(ZERO, ZERO); f[4] = pair(PINF, ZERO)
case("BF16 0*inf -> NaN", B, f, 0x7FFFFFFF)
# single product +inf * -inf -> -inf (sign of product, not NaN)
f = base(ONE); f[0] = pair(PINF, ONE); f[4] = pair(NINF, ZERO)
case("BF16 +inf*-inf -> -inf", B, f, 0xFF800000)
# both +inf and -inf products present -> NaN
f = base(ONE); f[0] = pair(PINF, PINF); f[4] = pair(PINF, NINF)
case("BF16 mixed +inf/-inf -> NaN", B, f, 0x7FFFFFFF)
# single inf kind propagates
f = base(ONE); f[8] = 0x7F800000
case("BF16 c=+inf -> +inf", B, f, 0x7F800000)
f = base(ONE); f[0] = pair(PINF, ONE)
case("BF16 a=+inf -> +inf", B, f, 0x7F800000)

# ============================ F16 (HMMA.16816.F32) ===========================
F = "F16"
# f16 subnormal support (MMA-Sim: NVIDIA Tensor Cores support the full FP32
# dynamic range incl. subnormals): b0.lo = f16 0x0001 = 2^-24 (min subnormal)
# -> P = 4 * 2^-24 = 2^-22 = 0x34800000.
f = base(ONE16); f[4] = pair(0x0001, ZERO)
case("F16 subnormal b=2^-24 -> P=2^-22", F, f, 0x34800000)
# exact product sum: b0.lo = 1.0 + 2^-10 (f16 0x3C01) -> P = 4.00390625
f = base(ONE16); f[4] = pair(0x3C01, ZERO)
case("F16 exact P = 4.00390625", F, f, 0x40802000)
# c large exponent, small P survives: c=2^20 + P=8 (b0.lo = f16 2.0)
f = base(ONE16); f[4] = pair(0x4000, ZERO); f[8] = fi(2.0**20)
case("F16 c=2^20 + P=8 -> 2^20+8", F, f, 0x49800040)
# NaN / inf
f = base(ONE16); f[8] = 0x7FC00000
case("F16 c=NaN", F, f, 0x7FFFFFFF)
f = base(ONE16); f[0] = pair(NAN16, ONE16)
case("F16 a0.lo=NaN", F, f, 0x7FFFFFFF)
f = base(ONE16); f[0] = pair(ZERO, ZERO); f[4] = pair(PINF16, ZERO)
case("F16 0*inf -> NaN", F, f, 0x7FFFFFFF)
f = base(ONE16); f[0] = pair(PINF16, PINF16); f[4] = pair(PINF16, NINF16)
case("F16 mixed +inf/-inf -> NaN", F, f, 0x7FFFFFFF)
f = base(ONE16); f[8] = 0x7F800000
case("F16 c=+inf -> +inf", F, f, 0x7F800000)

print(f"\n=== HMMA precision (FDA bit-level): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
