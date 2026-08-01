import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# HSET2 / HSETP2 / HMNMX2 — packed FP16 compare/set, compare/set-predicate,
# min/max.  Semantics verification (SM120), MOV32I harness.
#
# HSET2  (0x233): Rd = bval(cmp_bool) per lane, then Bop reduces the two lane
#        bools to ONE result replicated to both 16-bit halves.
#        BM (default): true = 0xffffffff, false = 0.  BF: true = 0x3c003c00.
#        Bop: AND=both-true, OR=either-true, XOR=lanes-differ.
# HSETP2 (0x234): P0 = lane0 cmp, P1 = lane1 cmp.  .H_AND reduces both into P0.
# HMNMX2 (0x240): Rd = min/max(Ra,Rb) per lane; PT = min, !PT = max.
#        .NAN propagates NaN (else NaN treated as the "other" operand).
#        .XORSIGN = select min/max by signed value, result = |sel| with
#        sign(a)^sign(b).  All take ISWZ swizzles like HFMA2/HADD2.
# ---------------------------------------------------------------------------

def build_kernel(movs, inst, extra_stores=None):
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 R6, #param(buf);[0:7:{}:1:0]"]
    for reg, val in movs.items():
        lines.append(f"    MOV32I R{reg}, 0x{val:08x};[7:7:{{}}:5:1]")
    lines += [f"    {inst};[7:7:{{}}:5:1]"]
    if extra_stores:
        for off, reg in extra_stores:
            lines.append(f"    STG.E desc[UR4][R6.64+0x{off:x}], R{reg};[0:1:{{0}}:1:0]")
    else:
        lines.append("    STG.E desc[UR4][R6.64+0x0], R22;[0:1:{0}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return assemble("\n".join(lines))


def run(movs, inst, nout=1):
    cubin = build_kernel(movs, inst)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.launch("k", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack(f"<{nout}I", mod.device_read(d + 0x0, 4 * nout))
    mod.devmem_free(d)
    return res[0] if nout == 1 else res


def f16f(h):
    s = (h >> 15) & 1; e = (h >> 10) & 0x1f; m = h & 0x3ff
    if e == 0:
        return (1.0 if not s else -1.0) * m / 1024.0 * 2 ** -14
    if e == 31:
        return float('nan') if m else (float('-inf') if s else float('inf'))
    return (1.0 if not s else -1.0) * (1.0 + m / 1024.0) * 2 ** (e - 15)


ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: got {got} want {want}")

H2 = 0x4000; H5 = 0x4500; H3 = 0x4200; H7 = 0x4700
HN3 = 0xc200

# ============================= HSET2 ========================================
# Bop semantics (default H1_H0 swizzle, per-lane bools b0=lane0, b1=lane1):
#   AND: per-lane passthrough (h0=b0, h1=b1)
#   OR:  always true (all-ones) — quirk on sm_120
#   XOR: per-lane NOT (h0=¬b0, h1=¬b1) — quirk on sm_120
# With H0_H0 (both lanes compute the same bool b): AND(b,b)=b, OR(b,b)=T, XOR(b,b)=¬b
movs = {"10": H2 | (H5 << 16), "11": H3 | (H7 << 16)}
o = run(movs, "HSET2.LT.AND R22, R10.H0_H0, R11.H0_H0, PT")
check("AND(b,b)=b both-true -> ones", o, 0xffffffff)
o = run(movs, "HSET2.LT.XOR R22, R10.H0_H0, R11.H0_H0, PT")
check("XOR(b,b)=NOT b (T->0)", o, 0x00000000)
movs = {"10": H5 | (H7 << 16), "11": H3 | (H2 << 16)}   # both-F under H0_H0? no, H0_H0 uses H0
movs = {"10": H5 | (H5 << 16), "11": H2 | (H2 << 16)}   # both F under H0_H0 (5 vs 2)
o = run(movs, "HSET2.LT.AND R22, R10.H0_H0, R11.H0_H0, PT")
check("AND(b,b)=b both-false -> 0", o, 0x00000000)
o = run(movs, "HSET2.LT.OR R22, R10.H0_H0, R11.H0_H0, PT")
check("OR(b,b)=T always (quirk)", o, 0xffffffff)
o = run(movs, "HSET2.LT.XOR R22, R10.H0_H0, R11.H0_H0, PT")
check("XOR(b,b)=NOT b (F->ones)", o, 0xffffffff)
# default swizzle per-lane (b0=lane0, b1=lane1): (2,5)<(3,2) = (T,F)
movs = {"10": H2 | (H5 << 16), "11": H3 | (H2 << 16)}
o = run(movs, "HSET2.LT.AND R22, R10, R11, PT")
check("AND per-lane (T,F) = 0x0000ffff", o, 0x0000ffff)
o = run(movs, "HSET2.LT.OR R22, R10, R11, PT")
check("OR always true", o, 0xffffffff)
o = run(movs, "HSET2.LT.XOR R22, R10, R11, PT")
check("XOR per-lane NOT (T,F) = 0xffff0000", o, 0xffff0000)
# BM vs BF true value
movs = {"10": H2 | (H5 << 16), "11": H3 | (H7 << 16)}
o = run(movs, "HSET2.LT.AND R22, R10.H0_H0, R11.H0_H0, PT")
check("BM true = 0xffffffff", o, 0xffffffff)
o = run(movs, "HSET2.LT.AND.BF R22, R10.H0_H0, R11.H0_H0, PT")
check("BF true = 0x3c003c00 (1.0)", o, 0x3c003c00)
# cmp variants: EQ, GE
movs = {"10": H2 | (H5 << 16), "11": H2 | (H5 << 16)}
o = run(movs, "HSET2.EQ.AND R22, R10.H0_H0, R11.H0_H0, PT")
check("EQ.AND (2=2,5=5) -> ones", o, 0xffffffff)
o = run(movs, "HSET2.GE.AND R22, R10.H0_H0, R11.H0_H0, PT")
check("GE.AND (2>=2,5>=5) -> ones", o, 0xffffffff)
o = run(movs, "HSET2.GT.AND R22, R10.H0_H0, R11.H0_H0, PT")
check("GT.AND (2>2 F,5>5 F) -> 0", o, 0x00000000)

# ============================= HSETP2 =======================================
def run_pred(movs, inst):
    # P0/P1 -> conditional MOV -> store two regs
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 R6, #param(buf);[0:7:{}:1:0]"]
    for reg, val in movs.items():
        lines.append(f"    MOV32I R{reg}, 0x{val:08x};[7:7:{{}}:5:1]")
    lines += [f"    {inst};[7:7:{{}}:5:1]",
              "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
              "    MOV32I R22, 0x22222222;[7:7:{}:5:1]",
              "    @P0 MOV32I R20, 0xdeadbeef;[7:7:{}:5:1]",
              "    @P1 MOV32I R22, 0xcafebabe;[7:7:{}:5:1]",
              "    STG.E desc[UR4][R6.64+0x0], R20;[0:1:{0}:1:0]",
              "    STG.E desc[UR4][R6.64+0x4], R22;[0:1:{0}:1:0]",
              "    EXIT;[7:7:{}:5:0]",
              "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.launch("k", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack("<2I", mod.device_read(d + 0x0, 8))
    mod.devmem_free(d)
    return res

movs = {"10": H2 | (H5 << 16), "11": H3 | (H7 << 16)}
p0, p1 = run_pred(movs, "HSETP2.LT.AND P0, P1, R10, R11, PT")
check("HSETP2 LT (T,T): P0=dead P1=cafe", (p0, p1), (0xdeadbeef, 0xcafebabe))
movs = {"10": H2 | (H5 << 16), "11": H3 | (H2 << 16)}
p0, p1 = run_pred(movs, "HSETP2.LT.AND P0, P1, R10, R11, PT")
check("HSETP2 LT (T,F): P0=dead P1=skip", (p0, p1), (0xdeadbeef, 0x22222222))
# H_AND: P0 = AND of both lane bools; P1 = the OTHER lane's bool (per swizzle)
p0, p1 = run_pred(movs, "HSETP2.LT.AND.H_AND P0, P1, R10, R11, PT")
check("HSETP2 H_AND (T,F): P0=skip(AND=false), P1=lane1(true)", (p0, p1), (0x11111111, 0xcafebabe))

# ============================= HMNMX2 =======================================
movs = {"10": H2 | (H5 << 16), "11": H3 | (H7 << 16)}
o = run(movs, "HMNMX2 R22, R10, R11, PT")
check("min (2,5),(3,7) = (2,5)", (f16f(o & 0xffff), f16f(o >> 16)), (2.0, 5.0))
o = run(movs, "HMNMX2 R22, R10, R11, !PT")
check("max (2,5),(3,7) = (3,7)", (f16f(o & 0xffff), f16f(o >> 16)), (3.0, 7.0))
# XORSIGN: value-min/max, |sel| with sign(a)^sign(b)
movs = {"10": H5 | (H5 << 16), "11": HN3 | (HN3 << 16)}
o = run(movs, "HMNMX2.XORSIGN R22, R10, R11, PT")
check("XORSIGN min(5,-3) = -3", (f16f(o & 0xffff), f16f(o >> 16)), (-3.0, -3.0))
movs = {"10": 0xc500 | (0xc500 << 16), "11": 0xc200 | (0xc200 << 16)}
o = run(movs, "HMNMX2.XORSIGN R22, R10, R11, PT")
check("XORSIGN min(-5,-3) = +5 (|sel|=5, xor=+)", (f16f(o & 0xffff), f16f(o >> 16)), (5.0, 5.0))
# NaN
HNaN = 0x7e00
movs = {"10": HNaN | (H2 << 16), "11": H2 | (H2 << 16)}
o = run(movs, "HMNMX2 R22, R10, R11, PT")
check("min(NaN,2) nonan -> other (2)", (o & 0xffff), 0x4000)
o = run(movs, "HMNMX2.NAN R22, R10, R11, PT")
check("min(NaN,2) .NAN -> NaN propagated", ((o & 0xffff) >> 10) & 0x1f, 31)

print(f"\n=== HSET2/HSETP2/HMNMX2 semantic probe: {'ALL OK' if ok else 'FAILED'} ===")
