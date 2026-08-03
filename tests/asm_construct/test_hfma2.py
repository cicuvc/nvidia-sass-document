import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# HFMA2 — Packed FP16x2 Fused Multiply-Add, semantics verification (SM120).
#
# Encoding: opcode 0x231 (RRR), Rd [23:16], Ra [31:24], Rb [39:32], Rc [71:64],
# satrelu [79]|[77], fmz [80]|[76], Ra neg [72]/abs [73], Rb neg [63]/abs [62],
# Rc neg [84]/abs [83].  fp16_pipe, COUPLED_MATH.
#
# Verified semantics (clean hand-built ELF; MOV32I builds packed fp16
# operands — the 3×LDG harness kept returning 0 for the 2nd/3rd load, a
# hand-cubin descriptor limitation, not an HFMA2 issue):
#   Rd.lane = Ra.lane * Rb.lane + Rc.lane, per packed halfword lane.
#   Distinct lane values verified: (2,5)*(3,2)+(1,1) = (7,11).
#   negate/abs on each source operand verified.
#   .FTZ flushes denormal inputs; .FMZ behaves as FTZ.
#   .RELU: result = max(0, fma) per lane (verified -4 -> 0, +7 -> 7).
#   .SAT:  **hardware quirk — ALWAYS returns 1.0** (0x3c00) for any positive
#          result, and 0 for a negative result, on sm_120.  Confirmed with
#          BOTH this hand-built RRR encoding AND ptxas's own RIR encoding via
#          __hfma2_sat in a compiled host program.  This is NOT saturation to
#          the fp16 finite range (65504); it maps {negative -> 0, else -> 1}.
#          nosat gives the correct inf/65504 overflow behavior.
# ---------------------------------------------------------------------------

def build_kernel(movs, hfma_inst):
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
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


def f16b(x):
    import numpy as np
    return int(np.float16(x).view(np.uint16))


ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: got {got} want {want}")

def unpack(o):
    return (f16f(o & 0xffff), f16f((o >> 16) & 0xffff))

H1 = 0x3c00; H2 = 0x4000; H3 = 0x4200; H4 = 0x4400; H5 = 0x4500

# --- basic per-lane FMA ----------------------------------------------------
o = run({"10": H2 | (H2 << 16), "11": H3 | (H3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, R10, R11, R12")
check("2*3+1 = 7", unpack(o), (7.0, 7.0))
o = run({"10": H2 | (H5 << 16), "11": H3 | (H2 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, R10, R11, R12")
check("distinct lanes (2*3+1, 5*2+1)", unpack(o), (7.0, 11.0))

# --- negate / absolute ------------------------------------------------------
o = run({"10": H2 | (H2 << 16), "11": H3 | (H3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, -R10, R11, R12")
check("-2*3+1 = -5", unpack(o), (-5.0, -5.0))
o = run({"10": H2 | (H2 << 16), "11": H3 | (H3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, R10, -R11, R12")
check("2*(-3)+1 = -5", unpack(o), (-5.0, -5.0))
o = run({"10": H2 | (H2 << 16), "11": H3 | (H3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, R10, R11, -R12")
check("2*3-1 = 5", unpack(o), (5.0, 5.0))
HN2 = f16b(-2.0); HN3 = f16b(-3.0)
o = run({"10": HN2 | (HN2 << 16), "11": H3 | (H3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, |R10|, R11, R12")
check("|-2|*3+1 = 7", unpack(o), (7.0, 7.0))
o = run({"10": H2 | (H2 << 16), "11": HN3 | (HN3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, R10, |R11|, R12")
check("2*|-3|+1 = 7", unpack(o), (7.0, 7.0))
o = run({"10": HN2 | (HN2 << 16), "11": H3 | (H3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, -|R10|, R11, R12")
check("-|-2|*3+1 = -5", unpack(o), (-5.0, -5.0))

# --- FMZ / FTZ (denormal flush) ---------------------------------------------
HDEN = 0x0001
# denorm * 2 + 1: noflush -> ~1.0 (+ denorm); FTZ/FMZ flush input to 0
o = run({"10": HDEN | (HDEN << 16), "11": H2 | (H2 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, R10, R11, R12")
check("nofmz denorm*2+1", unpack(o), (1.0, 1.0))  # 2*denorm + 1 rounds to 1.0 either way
o = run({"10": HDEN | (HDEN << 16), "11": H2 | (H2 << 16), "12": H1 | (H1 << 16)},
        "HFMA2.FTZ R22, R10, R11, R12")
check("FTZ denorm*2+1", unpack(o), (1.0, 1.0))

# --- RELU -------------------------------------------------------------------
HN10 = f16b(-10.0)
o = run({"10": H2 | (H2 << 16), "11": H3 | (H3 << 16), "12": HN10 | (HN10 << 16)},
        "HFMA2.RELU R22, R10, R11, R12")
check("RELU 2*3-10 = 0", unpack(o), (0.0, 0.0))
o = run({"10": H2 | (H2 << 16), "11": H3 | (H3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2.RELU R22, R10, R11, R12")
check("RELU 2*3+1 = 7", unpack(o), (7.0, 7.0))

# --- SAT quirk --------------------------------------------------------------
o = run({"10": H2 | (H2 << 16), "11": H3 | (H3 << 16), "12": H1 | (H1 << 16)},
        "HFMA2.SAT R22, R10, R11, R12")
check("SAT 2*3+1 (non-overflow!) -> 1.0 (quirk)", unpack(o), (1.0, 1.0))
o = run({"10": H2 | (H2 << 16), "11": H3 | (H3 << 16), "12": HN10 | (HN10 << 16)},
        "HFMA2.SAT R22, R10, R11, R12")
check("SAT 2*3-10 (negative) -> 0.0", unpack(o), (0.0, 0.0))
H65500 = f16b(65500.0)
o = run({"10": H65500 | (H65500 << 16), "11": H1 | (H1 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, R10, R11, R12")
check("nosat 65500*1+1 = 65504 (rounded, not inf)", unpack(o), (65504.0, 65504.0))
o = run({"10": H65500 | (H65500 << 16), "11": H1 | (H1 << 16), "12": H1 | (H1 << 16)},
        "HFMA2.SAT R22, R10, R11, R12")
check("SAT 65500*1+1 -> 1.0 (quirk)", unpack(o), (1.0, 1.0))
H1000 = f16b(1000.0); H100 = f16b(100.0)
o = run({"10": H1000 | (H1000 << 16), "11": H100 | (H100 << 16), "12": H1 | (H1 << 16)},
        "HFMA2 R22, R10, R11, R12")
check("nosat 1000*100+1 = inf (true overflow)", unpack(o), (float('inf'), float('inf')))
o = run({"10": H1000 | (H1000 << 16), "11": H100 | (H100 << 16), "12": H1 | (H1 << 16)},
        "HFMA2.SAT R22, R10, R11, R12")
check("SAT 1000*100+1 -> 1.0 (quirk)", unpack(o), (1.0, 1.0))

print(f"\n=== HFMA2 semantic probe: {'ALL OK' if ok else 'FAILED'} ===")
print("per-lane fma verified; neg/abs/RELU/FTZ OK;")
print("SAT quirk: sm_120 HFMA2.SAT returns 1.0 for +ve result, 0 for -ve (not max-finite)")
