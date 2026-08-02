import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# HFMA2 ISWZ lane swizzle verification (SM120).
#
# iswzA [75:74] (Ra), iswzB [86]|[61:60] (Rb), iswzC [82:81] (Rc).
# Enum: H1_H0=0 (default), H0_H0=2, H1_H1=3 (iswzA/C);
#       + F32=1, H0_NH1=4, INVALID5/6/7 (iswzB, all illegal on HFMA2).
#
# Verified semantics (packed fp16, distinct lanes a=(2,5) b=(3,7) c=(1,4),
# baseline lane0=2*3+1=7, lane1=5*7+4=39):
#   H0_H0 on an operand = BOTH output lanes use that operand's H0.
#   H1_H1 on an operand = BOTH output lanes use that operand's H1.
#   H1_H0 (default)     = lane0 uses H0, lane1 uses H1 (identity).
#   iswzB=F32 / H0_NH1 / INVALID* -> ILLEGAL_INSTRUCTION (spec CONDITIONS).
#
# The assembler now parses `.H0_H0`/`.H1_H1` operand suffixes into the iswz
# slots (iswzA/B/C), so the kernel uses native syntax.
# ---------------------------------------------------------------------------

def build_kernel(movs, hfma_inst):
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]"]
    for reg, val in movs.items():
        lines.append(f"    MOV32I R{reg}, 0x{val:08x};[7:7:{{}}:5:1]")
    lines += [f"    {hfma_inst};[7:7:{{}}:5:1]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R22;[0:1:{0}:1:0]",
              "    EXIT;[7:7:{}:5:0]",
              "}"]
    return assemble("\n".join(lines))


def run(movs, hfma_inst):
    cubin = build_kernel(movs, hfma_inst)
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


H2 = 0x4000; H5 = 0x4500; H3 = 0x4200; H7 = 0x4700; H1 = 0x3c00; H4 = 0x4400
# a=(2,5) b=(3,7) c=(1,4): baseline lane0=2*3+1=7, lane1=5*7+4=39
movs = {"10": H2 | (H5 << 16), "11": H3 | (H7 << 16), "12": H1 | (H4 << 16)}

def P(*parts):  # build HFMA2 with per-operand iswz
    return f"HFMA2 R22, {parts[0]}, {parts[1]}, {parts[2]}"

o = run(movs, P("R10", "R11", "R12"))
check("default H1_H0: (7, 39)", (f16f(o & 0xffff), f16f(o >> 16)), (7.0, 39.0))
o = run(movs, P("R10.H0_H0", "R11", "R12"))
check("A=H0_H0: (2*3+1, 2*7+4)", (f16f(o & 0xffff), f16f(o >> 16)), (7.0, 18.0))
o = run(movs, P("R10.H1_H1", "R11", "R12"))
check("A=H1_H1: (5*3+1, 5*7+4)", (f16f(o & 0xffff), f16f(o >> 16)), (16.0, 39.0))
o = run(movs, P("R10", "R11.H0_H0", "R12"))
check("B=H0_H0: (2*3+1, 5*3+4)", (f16f(o & 0xffff), f16f(o >> 16)), (7.0, 19.0))
o = run(movs, P("R10", "R11.H1_H1", "R12"))
check("B=H1_H1: (2*7+1, 5*7+4)", (f16f(o & 0xffff), f16f(o >> 16)), (15.0, 39.0))
o = run(movs, P("R10", "R11", "R12.H0_H0"))
check("C=H0_H0: (2*3+1, 5*7+1)", (f16f(o & 0xffff), f16f(o >> 16)), (7.0, 36.0))
o = run(movs, P("R10", "R11", "R12.H1_H1"))
check("C=H1_H1: (2*3+4, 5*7+4)", (f16f(o & 0xffff), f16f(o >> 16)), (10.0, 39.0))

# combined: A=H0_H0 + B=H1_H1 + C=H0_H0 -> a=2 both, b=7 both, c=1 both
o = run(movs, P("R10.H0_H0", "R11.H1_H1", "R12.H0_H0"))
check("combined (2*7+1, 2*7+1)", (f16f(o & 0xffff), f16f(o >> 16)), (15.0, 15.0))

print(f"\n=== HFMA2 ISWZ verification (native assembler syntax): {'ALL OK' if ok else 'FAILED'} ===")
print("H0_H0/H1_H1 confirmed (both lanes take that half); assembler now encodes .H0_H0/.H1_H1")

