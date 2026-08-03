import sys, struct, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from assembler import assemble, CudaModule, assemble_flat
import hmma_model as M

# ---------------------------------------------------------------------------
# QMMA m16n8k32 e4m3 -> f32 (tensor-core fp8 matrix multiply), verified SM120.
#
#   QMMA.16832.F32.E4M3.E4M3 Rd, Ra, Rb, Rc
#     Rd/Rc: 4x f32, Ra: 4x .b32 (16 fp8 A fragment), Rb: 2x .b32 (8 fp8 B)
#
# Fragment layout reuses the HMMA m16n8k16 register packing: each 16-bit slot
# is split into two 8-bit fp8 values.  fp8 byte i pairs only with byte i
# (probed); each pair folds 4 k, so D0/D1 carry 8 pairs x 4k = 32k, D2/D3 the
# other 8.  QMMA uses the same FDA(F=25) model as HMMA (Blackwell), except:
#   * fp8 inputs have NO special values -- exp-15 is an ordinary exponent
#     (0x7C = 384), only the all-ones 0x7F/0xFF is NaN.
#   * only the FP32 accumulator C carries NaN/inf.
# Verified: D matches nvcc mma.sync m16n8k32 e4m3, and the FDA model is
# bit-exact against the simulator on random fragments.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = list(got) == list(want)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} {got}")


NOP = "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
KERNEL = """#fn k(out<2048>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]
    LDG.E.128 {R16,R17,R18,R19}, desc[{UR4,UR5}][{R6,R7}+0x0];[5:7:{0,1}:8:1]
    LDG.E.64 {R20,R21}, desc[{UR4,UR5}][{R6,R7}+0x10];[5:7:{0,1}:8:1]
    LDG.E.128 {R24,R25,R26,R27}, desc[{UR4,UR5}][{R6,R7}+0x20];[5:7:{0,1}:8:1]
""" + NOP + NOP + """    QMMA.16832.F32.E4M3.E4M3 {R28,R29,R30,R31}, {R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27};[7:7:{5}:1:0]
""" + NOP + NOP + """    IADD3 R8, R6, 0x40, RZ;[7:7:{1}:5:1]
    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R28;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x4], R29;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x8], R30;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0xC], R31;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""


def run_qmma(frag16):
    mod = CudaModule(assemble(KERNEL))
    d = mod.devmem_alloc(2048 * 4)
    buf = [0] * 2048
    buf[:16] = frag16
    mod.device_write(d, struct.pack("<%dI" % 2048, *buf))
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    out = struct.unpack("<4I", mod.device_read(d + 0x40, 16))
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return out


def fi(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def fv(x):
    return struct.unpack("<f", struct.pack("<I", x))[0]


def frag(av, bv, c):
    f = [0] * 16
    for i in range(4):
        f[i] = av
    for i in range(2):
        f[4 + i] = bv
    for i in range(4):
        f[8 + i] = fi(c[i])
    return f


# --- semantics vs nvcc mma.sync m16n8k32 e4m3 -------------------------------
ONE = 0x38383838                 # fp8 e4m3 1.0 x4
TWO = 0x40404040                 # fp8 e4m3 2.0 x4
check("QMMA A=B=1 -> 42,43,44,45",
      [round(fv(x), 2) for x in run_qmma(frag(ONE, ONE, [10, 11, 12, 13]))],
      [42.0, 43.0, 44.0, 45.0])
check("QMMA A=2,B=1 -> 74,75,76,77",
      [round(fv(x), 2) for x in run_qmma(frag(TWO, ONE, [10, 11, 12, 13]))],
      [74.0, 75.0, 76.0, 77.0])
check("QMMA A=0 -> C=10,11,12,13",
      [round(fv(x), 2) for x in run_qmma(frag(0, ONE, [10, 11, 12, 13]))],
      [10.0, 11.0, 12.0, 13.0])

# --- FDA model bit-exact on random fragments --------------------------------
random.seed(0x5EED)
def rnd8():
    """Layered random fp8 e4m3: ordinary exp range, exp-15 patterns, NaN."""
    if random.random() < 0.15:
        return random.choice([0x7F, 0xFF, 0x7C, 0xFC, 0x00, 0x80])
    return random.randint(0, 255)


def rndc():
    r = random.random()
    if r < 0.8:
        return struct.unpack("<I", struct.pack("<f", random.uniform(-1e4, 1e4)))[0]
    if r < 0.9:
        return struct.unpack("<I", struct.pack("<f", random.uniform(-1e35, 1e35)))[0]
    if r < 0.95:
        return random.choice([0, 0x80000000, 0x7F800000, 0xFF800000])
    return random.choice([0x7FC00000, 0x7F800001, 0xFFC00000])


for trial in range(16):
    frag16 = [0] * 16
    for i in range(6):
        frag16[i] = rnd8() | (rnd8() << 8) | (rnd8() << 16) | (rnd8() << 24)
    for i in range(4):
        frag16[8 + i] = rndc()
    hw = run_qmma(frag16)
    md = M.qmma_frag(frag16)
    check(f"QMMA random frag {trial}", hw, md)

# --- encoding vs nvcc (data bits, same registers R4,R4,R2,R12) --------------
e = assemble_flat(
    "QMMA.16832.F32.E4M3.E4M3 {R4,R5,R6,R7}, {R4,R5,R6,R7}, {R2,R3}, {R12,R13,R14,R15};"
    "[7:7:{}:1:0]\n")[0]
nv_lo, nv_hi = 0x000000020404727a, 0x000fd00000002c0c
diff = sorted(
    set(g for g in range(64) if (e[0] >> g) & 1 != (nv_lo >> g) & 1) |
    set(g for g in range(64, 105) if (e[1] >> (g - 64)) & 1 != (nv_hi >> (g - 64)) & 1))
check("QMMA encode matches nvcc (bits 0-104)", diff, [])

print(f"\n=== QMMA m16n8k32 e4m3: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
