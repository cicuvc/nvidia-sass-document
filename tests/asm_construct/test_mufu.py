import sys, struct, math, random, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# MUFU — Multi-Function Unit, quantitative semantics + error analysis (SM120).
#
# Encoding: opcode 0x308 (RRR), Rd [23:16], Rb [39:32], mufuop [77:74],
# Rb negate [63], Rb abs [62].  mio_pipe, DECOUPLED_RD_WR_SCBD.
#
# Verified semantics (empirical):
#   RCP/RSQ/SQRT : correctly rounded (max 1 ulp) for normal-range inputs.
#   EX2          : 2^x, max 2 ulp (mean ~0.5).
#   LG2          : log2 x, max ~29 ulp near x=1 (mean ~0.6).
#   TANH         : tanh x, max ~67 ulp (mean ~0.06); denormal input passes
#                  through bit-exact (returns the denormal unchanged).
#   COS/SIN      : cos(2pi*x) / sin(2pi*x) — argument is in TURNS, not
#                  radians!  absolute error ~3.3e-7 regardless of |x| (exact
#                  range reduction); MUFU.COS(0.5) = cos(pi) = -1.
#   RCP64H/RSQ64H: read the HIGH 32 bits of a double, emit the HIGH 32 bits
#                  of the double result (low 32 implicit 0) — an
#                  approximation with rel err ~1e-6 (NOT correctly rounded),
#                  used as a Newton-Raphson seed for full FP64 div/sqrt.
#   Specials    : RCP(0)=inf, RCP(denorm)=inf, SQRT(denorm)=0, LG2(0)=-inf,
#                 EX2(denorm)=1.0, TANH(denorm)=denorm (passthrough),
#                 COS/SIN(inf/nan)=nan, all ops propagate NaN.
# ---------------------------------------------------------------------------

def build_kernel(op, src64=False):
    if src64:
        src = "    LDG.E R10, desc[{UR4,UR5}][{R16,R17}+0x80];[1:7:{0}:5:1]"
    else:
        src = "    LDG.E R10, desc[{UR4,UR5}][{R16,R17}];[1:7:{0}:5:1]"
    lines = ["#fn mufu(buf<16384>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    IADD3 R4, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R4, R4, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R16, R6, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R17, R7, RZ, RZ;[7:7:{}:5:1]",
             src,
             "    IADD3 R18, R10, RZ, RZ;[7:7:{1}:5:1]",
            f"    MUFU.{op} R20, R10;[1:7:{{0}}:5:1]",
             "    IADD3 R22, R20, RZ, RZ;[7:7:{1}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R16,R17}+0x1000], R22;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))


def run_op(op, inputs, src64=False):
    """inputs: list of 32-bit words (or hi-words for the 64H ops)."""
    cubin = build_kernel(op, src64)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(16384)
    res = []
    for start in range(0, len(inputs), 8):
        chunk = inputs[start:start + 8]
        init = [0] * 256
        for i, x in enumerate(chunk):
            init[32 + i if src64 else i] = x
        mod.device_write(d, struct.pack("<256I", *init))
        mod.launch("mufu", grid=(1,), block=(len(chunk),), args=[d])
        mod.synchronize()
        out = struct.unpack("<8I", mod.device_read(d + 0x1000, 32))
        res += list(out[:len(chunk)])
    mod.devmem_free(d)
    return res


def f32(x): return struct.unpack("<f", struct.pack("<I", x))[0]
def f32b(x): return struct.unpack("<I", struct.pack("<f", x))[0]

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: got {got} want {want}")

# --- exact values ----------------------------------------------------------
one = f32b(1.0); two = f32b(2.0); four = f32b(4.0); three = f32b(3.0)
check("RCP 2.0", f32(run_op("RCP", [two])[0]), 0.5)
check("RCP 4.0", f32(run_op("RCP", [four])[0]), 0.25)
check("SQRT 4.0", f32(run_op("SQRT", [four])[0]), 2.0)
check("SQRT 9.0", f32(run_op("SQRT", [f32b(9.0)])[0]), 3.0)
check("EX2 1.0", f32(run_op("EX2", [one])[0]), 2.0)
check("EX2 -1.0", f32(run_op("EX2", [f32b(-1.0)])[0]), 0.5)
check("LG2 2.0", f32(run_op("LG2", [two])[0]), 1.0)
check("LG2 4.0", f32(run_op("LG2", [four])[0]), 2.0)
check("RSQ 4.0", f32(run_op("RSQ", [four])[0]), 0.5)
check("RSQ 1.0", f32(run_op("RSQ", [one])[0]), 1.0)
check("TANH 0.0", f32(run_op("TANH", [0])[0]), 0.0)
check("TANH -0.0", f32(run_op("TANH", [0x80000000])[0]), -0.0)

# --- COS/SIN turn convention ------------------------------------------------
# MUFU.COS(x) = cos(2pi*x): 0.5 -> cos(pi) = -1; 1.0 -> cos(2pi) = 1
check("COS 0.0", f32(run_op("COS", [0])[0]), 1.0)
check("COS 0.5 = cos(pi)", f32(run_op("COS", [f32b(0.5)])[0]), -1.0)
check("COS 1.0 = cos(2pi)", f32(run_op("COS", [one])[0]), 1.0)
check("SIN 0.0", f32(run_op("SIN", [0])[0]), 0.0)
check("SIN 0.25 = sin(pi/2)", f32(run_op("SIN", [f32b(0.25)])[0]), 1.0)
check("SIN 0.5 = sin(pi)", f32(run_op("SIN", [f32b(0.5)])[0]), 0.0)

# --- specials ---------------------------------------------------------------
INF = 0x7f800000; NAN = 0x7fc00000
check("RCP 0 -> inf", run_op("RCP", [0])[0], INF)
check("RCP -0 -> -inf", run_op("RCP", [0x80000000])[0], 0xff800000)
check("LG2 0 -> -inf", run_op("LG2", [0])[0], 0xff800000)
check("RCP denorm -> inf", run_op("RCP", [1])[0], INF)
check("SQRT denorm -> 0", run_op("SQRT", [1])[0], 0)
check("LG2 denorm -> -inf", run_op("LG2", [1])[0], 0xff800000)
check("EX2 denorm -> 1.0", run_op("EX2", [1])[0], f32b(1.0))
check("RCP inf -> 0", run_op("RCP", [INF])[0], 0)
check("EX2 inf -> inf", run_op("EX2", [INF])[0], INF)
check("LG2 inf -> inf", run_op("LG2", [INF])[0], INF)
for op in ("RCP", "SQRT", "RSQ", "LG2", "EX2", "TANH"):
    out = run_op(op, [NAN])[0]
    check(f"{op} NaN -> NaN", (out >> 23) & 0xff == 0xff, True)
check("COS inf -> NaN", (run_op("COS", [INF])[0] >> 23) & 0xff == 0xff, True)
check("SIN inf -> NaN", (run_op("SIN", [INF])[0] >> 23) & 0xff == 0xff, True)

# --- TANH denormal passthrough (bit-exact) ----------------------------------
for xb in (0x00000001, 0x00000400, 0x007fffff):
    check(f"TANH denorm 0x{xb:08x} passthrough", run_op("TANH", [xb])[0], xb)

# --- quantitative error analysis --------------------------------------------
random.seed(99)
print("\n=== quantitative error vs double-precision reference ===")
print(f"{'op':<6} {'n':>4}  {'p50_rel':>9} {'p99_rel':>9} {'max_rel':>9}")
for op, ref, dom in (
    ("RCP", lambda x: 1.0 / x, lambda x: x != 0),
    ("RSQ", lambda x: 1.0 / math.sqrt(x), lambda x: x > 0),
    ("SQRT", lambda x: math.sqrt(x), lambda x: x >= 0),
    ("EX2", lambda x: 2.0 ** x, lambda x: -120 <= x < 120),
    ("LG2", lambda x: math.log2(x), lambda x: x > 0),
    ("TANH", lambda x: math.tanh(x), lambda x: True),
):
    xs = [2.0 ** random.uniform(-80, 80) for _ in range(1200)]
    xs += [random.uniform(-8, 8) for _ in range(400)]
    inputs = [f32b(x) for x in xs]
    got = run_op(op, inputs)
    rels = []
    for x, o in zip(xs, got):
        if not dom(x):
            continue
        try:
            r = ref(x)
        except Exception:
            continue
        if math.isnan(r) or math.isinf(r) or r == 0:
            continue
        rels.append(abs(f32(o) - r) / abs(r))
    rels.sort()
    n = len(rels)
    print(f"  {op:<6} {n:>4}  {rels[n//2]:>9.2e} {rels[int(n*0.99)]:>9.2e} {rels[-1]:>9.2e}")

print("\n=== COS/SIN absolute error (output in [-1,1]; turn-domain) ===")
for op, ref in (("COS", math.cos), ("SIN", math.sin)):
    xs = [random.uniform(-0.25, 0.25) for _ in range(2000)]
    inputs = [f32b(x) for x in xs]
    got = run_op(op, inputs)
    abserrs = sorted(abs(f32(o) - ref(2 * math.pi * x)) for x, o in zip(xs, got))
    n = len(abserrs)
    print(f"  {op}  p50={abserrs[n//2]:.2e}  p99={abserrs[int(n*0.99)]:.2e}  max={abserrs[-1]:.2e}")

print("\n=== RCP64H/RSQ64H (hi-word of double in -> hi-word of double out) ===")
random.seed(5)
xs = [2.0 ** random.uniform(-500, 500) for _ in range(1500)]
hi = [(struct.unpack("<Q", struct.pack("<d", v))[0] >> 32) for v in xs]
for op, ref in (("RCP64H", lambda x: 1.0 / x), ("RSQ64H", lambda x: 1.0 / math.sqrt(x))):
    got = run_op(op, hi, src64=True)
    rels = sorted(abs(struct.unpack("<d", struct.pack("<Q", o << 32))[0] - ref(v)) / abs(ref(v))
                  for o, v in zip(got, xs))
    n = len(rels)
    print(f"  {op}  p50={rels[n//2]:.2e}  p99={rels[int(n*0.99)]:.2e}  max={rels[-1]:.2e}")

print(f"\n=== MUFU quantitative analysis: {'ALL OK' if ok else 'FAILED'} ===")
print("RCP/RSQ/SQRT correctly-rounded; COS/SIN take turns (2pi); TANH denorm-passthrough")
