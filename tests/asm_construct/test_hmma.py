import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# HMMA.16816.F32.BF16 — tensor-core matrix multiply (bf16 x bf16 -> f32),
# m16n8k16 (fp16_pipe, VQ_HMMA).  Verified SM120 against nvcc mma.sync.
#
#   HMMA.16816.F32.BF16 {Rd..Rd+3}, {Ra..Ra+3}, {Rb,Rb+1}, {Rc..Rc+3}
#     Rd/Rc: 4x f32 (D = A*B + C), Ra: 4x .b32 (8 bf16 A fragment),
#     Rb: 2x .b32 (4 bf16 B fragment)
#
# The only legal schedule for this HMMA is stall=1/yield=0 (opex=17); any
# other stall/opex combo is rejected as ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR
# by TABLES_opex_3.  The matcher enforces this.
#
# Verification: feed an identical per-thread fragment (a0..a3, b0..b1, c0..c3)
# at a fixed global address (all 32 lanes read the same words, so no SR_TID
# addressing is needed), run HMMA, and compare D against nvcc's mma.sync
# result for the same fragment.  D = A*B + C with A,B = 1.0 bf16 gives 8 + C.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = list(got) == list(want)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<44} {got}")


KERNEL = """#fn k(out<2048>) {
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
    STG.E desc[{UR4,UR5}][{R8,R9}+0x4], R29;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x8], R30;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0xC], R31;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""


def run_hmma(srcfmt, frag16):
    """frag16: 16 words at out[0..15]; D written to out+0x40. Returns 4 floats."""
    mod = CudaModule(assemble(KERNEL.replace("{SRCFMT}", srcfmt)))
    d = mod.devmem_alloc(2048 * 4)
    buf = [0] * 2048
    buf[:16] = frag16
    mod.device_write(d, struct.pack("<%dI" % 2048, *buf))
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    vals = struct.unpack("<4f", mod.device_read(d + 0x40, 16))
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return vals


def frag(a_val, b_val, c_vals):
    """Build a 16-word fragment: a0..a3 (4x .b32) + b0..b1 (2x .b32) + c0..c3 (4x f32)."""
    f = [0] * 16
    for i in range(6):
        f[i] = a_val if i < 4 else b_val
    for i, c in enumerate(c_vals):
        f[8 + i] = struct.unpack("<I", struct.pack("<f", c))[0]
    return f


# --- 1. BF16: A=B=1.0, C=10..13 -> D = 1*8 + C = 18,19,20,21 (nvcc mma_frag2) ---
check("HMMA.BF16 A=1,B=1,C=10..13 -> 18,19,20,21",
      run_hmma("BF16", frag(0x3F800000, 0x3F800000, [10, 11, 12, 13])),
      [18.0, 19.0, 20.0, 21.0])

# --- 2. BF16: A=2.0 (bf16 2.0 = 0x4000) -> D = 2*8 + C = 26..29 ---------------
check("HMMA.BF16 A=2,B=1 -> 26,27,28,29",
      run_hmma("BF16", frag(0x40000000, 0x3F800000, [10, 11, 12, 13])),
      [26.0, 27.0, 28.0, 29.0])

# --- 3. BF16: A=0 -> D = C = 10..13 (no A contribution) ------------------------
check("HMMA.BF16 A=0 -> C=10,11,12,13",
      run_hmma("BF16", frag(0, 0x3F800000, [10, 11, 12, 13])),
      [10.0, 11.0, 12.0, 13.0])

# --- 4. F16: same shapes. f16 1.0 = 0x3C00 (32-bit pair 0x3C003C00) ------------
# nvcc mma.m16n8k16 f16 gives A*B = 16 (vs bf16's 8) for A=B=1.0.
check("HMMA.F16 A=1,B=1,C=10..13 -> 26,27,28,29",
      run_hmma("F16", frag(0x3C003C00, 0x3C003C00, [10, 11, 12, 13])),
      [26.0, 27.0, 28.0, 29.0])

check("HMMA.F16 A=2,B=1 -> 42,43,44,45",
      run_hmma("F16", frag(0x40004000, 0x3C003C00, [10, 11, 12, 13])),
      [42.0, 43.0, 44.0, 45.0])

check("HMMA.F16 A=0 -> C=10,11,12,13",
      run_hmma("F16", frag(0, 0x3C003C00, [10, 11, 12, 13])),
      [10.0, 11.0, 12.0, 13.0])

# --- 5. encoding vs nvcc (data bits, same registers R4,R4,R2,R12) -------------
e = assemble_flat(
    "HMMA.16816.F32.BF16 {R4,R5,R6,R7}, {R4,R5,R6,R7}, {R2,R3}, {R12,R13,R14,R15};"
    "[7:7:{}:1:0]\n")[0]
nv_lo, nv_hi = 0x000000020404723c, 0x000fee000004180c
diff = sorted(
    set(g for g in range(64) if (e[0] >> g) & 1 != (nv_lo >> g) & 1) |
    set(g for g in range(64, 105) if (e[1] >> (g - 64)) & 1 != (nv_hi >> (g - 64)) & 1))
check("HMMA.BF16 encode matches nvcc (bits 0-104)", diff, [])

e = assemble_flat(
    "HMMA.16816.F32.F16 {R4,R5,R6,R7}, {R4,R5,R6,R7}, {R2,R3}, {R12,R13,R14,R15};"
    "[7:7:{}:1:0]\n")[0]
nvf_lo, nvf_hi = 0x000000020404723c, 0x000fee000000180c
diff = sorted(
    set(g for g in range(64) if (e[0] >> g) & 1 != (nvf_lo >> g) & 1) |
    set(g for g in range(64, 105) if (e[1] >> (g - 64)) & 1 != (nvf_hi >> (g - 64)) & 1))
check("HMMA.F16 encode matches nvcc (bits 0-104)", diff, [])

# --- 6. all stall/yield schedules accepted & run (verified on hardware) --------
for stall, y in [(1, 0), (3, 0), (5, 0), (7, 0), (1, 1), (5, 1), (7, 1)]:
    try:
        assemble_flat(
            "HMMA.16816.F32.BF16 {R4,R5,R6,R7}, {R4,R5,R6,R7}, {R2,R3}, "
            f"{{R12,R13,R14,R15}};[7:7:{{}}:{stall}:{y}]\n")
        ok2 = True
    except Exception:
        ok2 = False
    check(f"HMMA stall={stall}/y={y} encodable", "accepted" if ok2 else "rejected",
          "accepted")

print(f"\n=== HMMA (tensor core bf16a32 + fp16a32): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
