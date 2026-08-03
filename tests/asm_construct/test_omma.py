import sys, struct, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from assembler import assemble, CudaModule, assemble_flat
import hmma_model as M

# ---------------------------------------------------------------------------
# OMMA.SF — block-scaled MXFP4 tensor-core MMA, m16n8k64 e2m1 -> f32.
#
#   OMMA.SF.16864.F32.E2M1.E2M1.E8 Rd, Ra, Rb, Rc, Re, Rh, URi
#     Re/Rh: scale-A/B data (4x E8M0 bytes); URi: uniform selector.
#
# PTX: mma.sync.aligned.m16n8k64.row.col.kind::mxf4.block_scale.f32.e2m1.e2m1
# .f32.ue8m0 (sm_120a).  e2m1 is packed 4 bits/element (no padding for mxf4):
# exp 2 bits (bias 1), 1 mantissa bit, sign top.  Scale factors are per-32
# columns (scale_A is M x K/32 = M x 2, "2X"): byte 0 of Re scales k 0..31,
# byte 1 scales k 32..63.
#
# Verified SM120:
#   e2m1 values: 0x1 = 0.5 (subnormal), 0x2 = 1.0, 0x6 = 4.0
#   A*B (all 1.0) = 64 k  (m16n8k64)
#   scale 2x/0x, half-2-half-1 per 32-column block (96 = 32*2 + 32*1)
#   URi accepts only sel=0 here (other values fault 0x715)
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = list(got) == list(want)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<44} {got}")

NOP = "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
KERNEL = """#fn k(out<8>, sel<4>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]
    LDG.E.128 {R16,R17,R18,R19}, desc[{UR4,UR5}][{R6,R7}+0x0];[5:7:{0,1}:8:1]
    LDG.E.64 {R20,R21}, desc[{UR4,UR5}][{R6,R7}+0x10];[5:7:{0,1}:8:1]
    LDG.E.128 {R24,R25,R26,R27}, desc[{UR4,UR5}][{R6,R7}+0x20];[5:7:{0,1}:8:1]
    MOV32I R22, 0xRE;[7:7:{}:5:1]
    MOV32I R23, 0xRH;[7:7:{}:5:1]
    LDCU.32 UR6, #param(sel);[7:7:{1}:5:1]
""" + NOP + NOP + """    OMMA.SF.16864.F32.E2M1.E2M1.E8 {R28,R29,R30,R31}, {R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27}, R22, R23, UR6;[7:7:{5}:1:0]
""" + NOP + NOP + """    IADD3 R8, R6, 0x40, RZ;[7:7:{1}:5:1]
    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R28;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x4], R29;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x8], R30;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0xC], R31;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""


def run_omma(av, bv, re, rh, sel=0):
    mod = CudaModule(assemble(KERNEL.replace("RE", re).replace("RH", rh)))
    d = mod.devmem_alloc(2048 * 4)
    frag = [0] * 2048
    for i in range(4):
        frag[i] = av
    for i in range(2):
        frag[4 + i] = bv
    mod.device_write(d, struct.pack("<%dI" % 2048, *frag))
    mod.launch("k", grid=(1,), block=(32,), args=[d, sel])
    mod.synchronize()
    out = [round(x, 2) for x in struct.unpack("<4f", mod.device_read(d + 0x40, 16))]
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return out


ONE, TWO, HALF = "7F7F7F7F", "80808080", "7E7E7E7E"   # E8M0 1.0 / 2.0 / 0.5

# --- e2m1 values and A*B (m16n8k64) -----------------------------------------
# 0x1 = 0.5 (subnormal): 64 k * 0.25 = 16
check("OMMA A=0x1(e2m1 0.5) A*B=16", run_omma(0x11111111, 0x11111111, ONE, ONE), [16.0] * 4)
check("OMMA A=0x2(e2m1 1.0) A*B=64", run_omma(0x22222222, 0x22222222, ONE, ONE), [64.0] * 4)
check("OMMA A=0x6(e2m1 4.0) A*B=1024", run_omma(0x66666666, 0x66666666, ONE, ONE), [1024.0] * 4)

# --- scale semantics --------------------------------------------------------
check("OMMA scale 2x -> 128", run_omma(0x22222222, 0x22222222, TWO, ONE), [128.0] * 4)
check("OMMA scale 0  -> 0", run_omma(0x22222222, 0x22222222, "00000000", ONE), [0.0] * 4)
# 2X: byte0 scales k0..31, byte1 scales k32..63: 32*2 + 32*1 = 96
check("OMMA scale [2,1,1,0x01] -> 96", run_omma(0x22222222, 0x22222222, "017F7F80", ONE), [96.0] * 4)

# --- encoding vs nvcc (data bits, same regs R4,R4,R2,RZ,RZ,RZ,URZ) ----------
e = assemble_flat(
    "OMMA.SF.16864.F32.E2M1.E2M1.E8 {R4,R5,R6,R7}, {R4,R5,R6,R7}, {R2,R3}, "
    "{R12,R13,R14,R15}, R16, R17, URZ;[7:7:{}:1:0]\n")[0]
nv_lo, nv_hi = 0x7ff0ff020404747f, 0x000fe20000083eff
mask_lo = ~(0xFF << 40) & ~(0xFF << 52) & 0xFFFFFFFFFFFFFFFF
mask_hi = ~0xFF & 0xFFFFFFFFFFFFFFFF
diff = sorted(
    set(g for g in range(64) if ((e[0] & mask_lo) >> g) & 1 != ((nv_lo & mask_lo) >> g) & 1) |
    set(g for g in range(64, 105) if ((e[1] & mask_hi) >> (g - 64)) & 1
        != ((nv_hi & mask_hi) >> (g - 64)) & 1))
check("OMMA encode matches nvcc (bits 0-104)", diff, [])

# --- bit-accurate GDFS model vs hardware on random fragments -----------------
random.seed(0x0FFA)
def rnd():
    return random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF])


def run_omma_bits(frag16):
    k = KERNEL.replace("RE", "7F7F7F7F").replace("RH", "7F7F7F7F")
    mod = CudaModule(assemble(k))
    d = mod.devmem_alloc(2048 * 4)
    buf = [0] * 2048
    buf[:16] = frag16
    mod.device_write(d, struct.pack("<%dI" % 2048, *buf))
    mod.launch("k", grid=(1,), block=(32,), args=[d, 0])
    mod.synchronize()
    return struct.unpack("<4I", mod.device_read(d + 0x40, 16))


for mode in ["c0", "crand"]:
    for trial in range(8):
        f = [0] * 16
        for i in range(6):
            f[i] = rnd() | (rnd() << 4) | (rnd() << 8) | (rnd() << 12) | \
                   (rnd() << 16) | (rnd() << 20) | (rnd() << 24) | (rnd() << 28)
        f[6] = 0x7F7F7F7F
        f[7] = 0x7F7F7F7F
        if mode == "crand":
            for i in range(4):
                f[8 + i] = struct.unpack("<I", struct.pack("<f", random.uniform(-100, 100)))[0]
        hw = run_omma_bits(f)
        md = M.omma_frag(f)
        check(f"OMMA random frag ({mode}) {trial}", hw, md)

print(f"\n=== OMMA m16n8k64 MXFP4: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
