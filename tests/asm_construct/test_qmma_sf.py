import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# QMMA.SF — block-scaled (MXFP) fp8 matrix multiply, m16n8k32, verified SM120.
#
#   QMMA.SF.16832.F32.{srcFmtA}.{srcFmtB}.E8 Rd, Ra, Rb, Rc, Re, Rh, URi
#     Re / Rh: 32-bit scale-A / scale-B data (4x E8M0 bytes, one per warp
#              thread); URi: uniform selector register.
#
# Block scaling (PTX `kind::mxf8f6f4.block_scale` / OCP MX): A and B carry a
# per-32-column E8M0 scale factor (A^SF is M x K/32, B^SF is K/32 x N).  Each
# product scales by E8M0: d = sum_k (a*2^(eA-127))*(b*2^(eB-127)) + c.  The
# selector (URi value, low 2 bits = byte-id, high = thread-id) picks which
# E8M0 byte of Re/Rh feeds the block.  E8M0: 0x7F = 2^0, 0x80 = 2^1,
# 0x7E = 2^-1, 0x01 ~ 2^-126.
#
# Verified: scale semantics (1x/2x/0.5x, Re*Rh composite) and the URi
# byte-selector match the model; the SASS encoding matches nvcc's lowering of
# mma.sync...kind::mxf8f6f4.block_scale...ue8m0 (sm_120a).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = list(got) == list(want)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} {got}")

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
""" + NOP + NOP + """    QMMA.SF.16832.F32.E4M3.E5M2.E8 {R28,R29,R30,R31}, {R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27}, R22, R23, UR6;[7:7:{5}:1:0]
""" + NOP + NOP + """    IADD3 R8, R6, 0x40, RZ;[7:7:{1}:5:1]
    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R28;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x4], R29;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x8], R30;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0xC], R31;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""


def run_sf(re, rh, sel=0):
    mod = CudaModule(assemble(KERNEL.replace("RE", re).replace("RH", rh)))
    d = mod.devmem_alloc(2048 * 4)
    frag = [0] * 2048
    for i in range(4):
        frag[i] = 0x38383838                    # fp8 e4m3 1.0 x4
    for i in range(2):
        frag[4 + i] = 0x3C3C3C3C                # fp8 e5m2 1.0 x4
    for i in range(4):
        frag[8 + i] = struct.unpack("<I", struct.pack("<f", float([10, 11, 12, 13][i])))[0]
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

# --- scale semantics (E4M3 x E5M2, A*B = 32) --------------------------------
check("SF scale 1 x 1 -> 42,43,44,45", run_sf(ONE, ONE), [42.0, 43.0, 44.0, 45.0])
check("SF scale 2 x 1 -> 74,75,76,77", run_sf(TWO, ONE), [74.0, 75.0, 76.0, 77.0])
check("SF scale 0.5 x 1 -> 26,27,28,29", run_sf(HALF, ONE), [26.0, 27.0, 28.0, 29.0])
check("SF scale 2 x 2 -> 138..141", run_sf(TWO, TWO), [138.0, 139.0, 140.0, 141.0])
check("SF scale 0.5 x 0.5 -> 18,19,20,21", run_sf(HALF, HALF), [18.0, 19.0, 20.0, 21.0])
check("SF scale 2 x 0.5 -> 42,43,44,45", run_sf(TWO, HALF), [42.0, 43.0, 44.0, 45.0])

# --- URi selector: low 2 bits pick the Re byte ------------------------------
# Re bytes LE = 80(2) 7F(1) 7F(1) 01(~0): sel%4 -> byte0..3
check("URi sel=0 -> byte0 (2x)", run_sf("017F7F80", ONE, 0), [74.0, 75.0, 76.0, 77.0])
check("URi sel=1 -> byte1 (1x)", run_sf("017F7F80", ONE, 1), [42.0, 43.0, 44.0, 45.0])
check("URi sel=2 -> byte2 (1x)", run_sf("017F7F80", ONE, 2), [42.0, 43.0, 44.0, 45.0])
check("URi sel=3 -> byte3 (~0x)", run_sf("017F7F80", ONE, 3), [10.0, 11.0, 12.0, 13.0])
check("URi sel=7 -> byte3 (7%%4)", run_sf("017F7F80", ONE, 7), [10.0, 11.0, 12.0, 13.0])

# --- encoding vs nvcc (data bits, same registers R4,R4,R2,RZ,RZ,RZ,URZ) -----
e = assemble_flat(
    "QMMA.SF.16832.F32.E4M3.E5M2.E8 {R4,R5,R6,R7}, {R4,R5,R6,R7}, {R2,R3}, "
    "{R12,R13,R14,R15}, R16, R17, URZ;[7:7:{}:1:0]\n")[0]
nv_lo, nv_hi = 0x7ff0ff020404747a, 0x000fe2000000beff
# compare with Re/Rh (lo 40-47,52-59) and Rc (hi 0-7) normalized (nvcc uses RZ)
mask_lo = ~(0xFF << 40) & ~(0xFF << 52) & 0xFFFFFFFFFFFFFFFF
mask_hi = ~0xFF & 0xFFFFFFFFFFFFFFFF
diff = sorted(
    set(g for g in range(64) if ((e[0] & mask_lo) >> g) & 1 != ((nv_lo & mask_lo) >> g) & 1) |
    set(g for g in range(64, 105) if ((e[1] & mask_hi) >> (g - 64)) & 1
        != ((nv_hi & mask_hi) >> (g - 64)) & 1))
check("QMMA.SF encode matches nvcc (bits 0-104)", diff, [])

print(f"\n=== QMMA.SF block scaling: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
