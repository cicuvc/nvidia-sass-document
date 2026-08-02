import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# HADD2 / HMUL2 — Packed FP16x2 add / multiply, semantics verification (SM120).
#
# HADD2: opcode 0x230, Rd = Ra + Rc (two source operands).  ofmt can widen to
#        F32 (HADD2.F32 → two FP32 outputs, HADD2_32I class).  ftz [80],
#        sat [77] single bits.  ISWZA on Ra, ISWZB-as-C on Rc.
# HMUL2: opcode 0x232, Rd = Ra * Rb (two source operands).  OFMT_F16_V2_BF16_V2,
#        FMZ_hfma2 (nofmz/FMZ/FTZ), sat [77].  ISWZA on Ra, ISWZB on Rb.
#
# Same harness as test_hfma2.py (MOV32I-built packed fp16 operands).
# ---------------------------------------------------------------------------

def build_kernel(movs, inst):
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]"]
    for reg, val in movs.items():
        lines.append(f"    MOV32I R{reg}, 0x{val:08x};[7:7:{{}}:5:1]")
    lines += [f"    {inst};[7:7:{{}}:5:1]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R22;[0:1:{0}:1:0]",
              "    EXIT;[7:7:{}:5:0]",
              "}"]
    return assemble("\n".join(lines))


def run(movs, inst):
    cubin = build_kernel(movs, inst)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.launch("k", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack("<I", mod.device_read(d + 0x0, 4))
    mod.devmem_free(d)
    return res[0]


def f16f(h):
    s = (h >> 15) & 1; e = (h >> 10) & 0x1f; m = h & 0x3ff
    if e == 0:
        return (1.0 if not s else -1.0) * m / 1024.0 * 2 ** -14
    if e == 31:
        return float('inf') if not s else float('-inf')
    return (1.0 if not s else -1.0) * (1.0 + m / 1024.0) * 2 ** (e - 15)


ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: got {got} want {want}")

H1 = 0x3c00; H2 = 0x4000; H3 = 0x4200; H4 = 0x4400; H5 = 0x4500; H7 = 0x4700
HN2 = 0xc000; HDEN = 0x0001

# ============================= HADD2 ========================================
# a=(2,5) + c=(3,7) = (5,12)
movs = {"10": H2 | (H5 << 16), "11": H3 | (H7 << 16)}
o = run(movs, "HADD2 R22, R10, R11")
check("2+3, 5+7 = (5,12)", (f16f(o & 0xffff), f16f(o >> 16)), (5.0, 12.0))
# negate Ra: -2+3=1, -5+7=2
o = run(movs, "HADD2 R22, -R10, R11")
check("-2+3, -5+7 = (1,2)", (f16f(o & 0xffff), f16f(o >> 16)), (1.0, 2.0))
# |Ra| with negative inputs
movs2 = {"10": HN2 | (H5 << 16), "11": H3 | (H7 << 16)}
o = run(movs2, "HADD2 R22, |R10|, R11")
check("|-2|+3, 5+7 = (5,12)", (f16f(o & 0xffff), f16f(o >> 16)), (5.0, 12.0))
# ISWZ: Ra.H0_H0 -> both lanes use Ra.H0=2: 2+3=5, 2+7=9
o = run(movs, "HADD2 R22, R10.H0_H0, R11")
check("A=H0_H0: (2+3, 2+7) = (5,9)", (f16f(o & 0xffff), f16f(o >> 16)), (5.0, 9.0))
# Rc.H0_H0 -> both use Rc.H0=3: 2+3=5, 5+3=8
o = run(movs, "HADD2 R22, R10, R11.H0_H0")
check("C=H0_H0: (2+3, 5+3) = (5,8)", (f16f(o & 0xffff), f16f(o >> 16)), (5.0, 8.0))
# FTZ denorm flush: denorm + 1 -> 1 (input flushed)
o = run({"10": HDEN | (HDEN << 16), "11": H1 | (H1 << 16)}, "HADD2 R22, R10, R11")
check("nofmz denorm+1", (f16f(o & 0xffff), f16f(o >> 16)), (1.0, 1.0))
# SAT: 65500+100 = 65600 overflows -> ? (check if same quirk as HFMA2)
import numpy as np
H65500 = int(np.float16(65500.0).view(np.uint16))
H100 = int(np.float16(100.0).view(np.uint16))
o = run({"10": H65500 | (H65500 << 16), "11": H100 | (H100 << 16)}, "HADD2 R22, R10, R11")
print(f"  HADD2 65500+100 (nosat): 0x{o:08x} -> ({f16f(o&0xffff):.4g}, {f16f(o>>16):.4g})")
o = run({"10": H65500 | (H65500 << 16), "11": H100 | (H100 << 16)}, "HADD2.SAT R22, R10, R11")
print(f"  HADD2.SAT 65500+100: 0x{o:08x} -> ({f16f(o&0xffff):.4g}, {f16f(o>>16):.4g})")

# ============================= HMUL2 ========================================
# a=(2,5) * b=(3,7) = (6,35)
movs = {"10": H2 | (H5 << 16), "11": H3 | (H7 << 16)}
o = run(movs, "HMUL2 R22, R10, R11")
check("2*3, 5*7 = (6,35)", (f16f(o & 0xffff), f16f(o >> 16)), (6.0, 35.0))
# negate Rb: 2*-3=-6, 5*-7=-35
o = run(movs, "HMUL2 R22, R10, -R11")
check("2*(-3), 5*(-7) = (-6,-35)", (f16f(o & 0xffff), f16f(o >> 16)), (-6.0, -35.0))
# ISWZ Ra.H1_H1 -> both use Ra.H1=5: 5*3=15, 5*7=35
o = run(movs, "HMUL2 R22, R10.H1_H1, R11")
check("A=H1_H1: (5*3, 5*7) = (15,35)", (f16f(o & 0xffff), f16f(o >> 16)), (15.0, 35.0))
# ISWZ Rb.H0_H0 -> both use Rb.H0=3: 2*3=6, 5*3=15
o = run(movs, "HMUL2 R22, R10, R11.H0_H0")
check("B=H0_H0: (2*3, 5*3) = (6,15)", (f16f(o & 0xffff), f16f(o >> 16)), (6.0, 15.0))
# FTZ denorm flush: nofmz preserves (denorm 0x1 * 2 = 0x2, still denormal), FTZ flushes to 0
o = run({"10": HDEN | (HDEN << 16), "11": H2 | (H2 << 16)}, "HMUL2 R22, R10, R11")
check("nofmz denorm*2 (preserved)", (o & 0xffff, o >> 16), (0x0002, 0x0002))
o = run({"10": HDEN | (HDEN << 16), "11": H2 | (H2 << 16)}, "HMUL2.FTZ R22, R10, R11")
check("FTZ denorm*2 (flushed)", (f16f(o & 0xffff), f16f(o >> 16)), (0.0, 0.0))
# SAT overflow quirk check
o = run({"10": H65500 | (H65500 << 16), "11": H100 | (H100 << 16)}, "HMUL2 R22, R10, R11")
print(f"  HMUL2 65500*100 (nosat): 0x{o:08x} -> ({f16f(o&0xffff):.4g}, {f16f(o>>16):.4g})")
o = run({"10": H65500 | (H65500 << 16), "11": H100 | (H100 << 16)}, "HMUL2.SAT R22, R10, R11")
print(f"  HMUL2.SAT 65500*100: 0x{o:08x} -> ({f16f(o&0xffff):.4g}, {f16f(o>>16):.4g})")

print(f"\n=== HADD2/HMUL2 semantic probe: {'ALL OK' if ok else 'FAILED'} ===")
