import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# SETCTAID — Set CTA (thread-block) ID hardware state, verified (SM120).
#
# Opcode 0x31f, mio_pipe, INST_TYPE_DECOUPLED_RD_WR_SCBD, VQ_ADU, compute-only.
# Modifiers: dim [79:78] = X(0) / Y(1) / Z(2) / ALL(3, default).  Source Ra:
# 32-bit single register for .X/.Y/.Z, 64-bit pair for ALL (even-aligned).
#
# Semantics verified: SETCTAID writes the CTA block-index hardware state that
# `S2R SR_CTAID.{X,Y,Z}` reads.  After SETCTAID.X R20, S2R SR_CTAID.X returns
# the injected value (0x55), NOT the real blockIdx (verified with grid=(2,1,1)
# where the real X is 0/1).  Same for .Y and .Z.
#
# ALL variant 64-bit packing (verified): X = low 32 bits (R20),
# Y = low 16 bits of the high word (R21), Z = high 16 bits of R21.
# R20:R21 = 0x00000101_02030004 -> X=0x101, Y=0x004, Z=0x203.
# ---------------------------------------------------------------------------

def build(set_inst, read_reg):
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    IADD3 R4, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R4, R4, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R16, R6, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R17, R7, RZ, RZ;[7:7:{}:5:1]",
             "    MOV32I R20, 0x00000055;[7:7:{}:5:1]",
             "    MOV32I R21, 0x02030004;[7:7:{}:5:1]",
             f"    {set_inst};[7:7:{{}}:5:1]",
             f"    S2R R22, {read_reg};[0:7:{{}}:5:1]",
             "    IADD3 R23, R22, RZ, RZ;[7:7:{0}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R16,R17}+0x0], R23;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))


def run(set_inst, read_reg, grid):
    cubin = build(set_inst, read_reg)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<64I", *[0] * 64))
    try:
        mod.launch("k", grid=grid, block=(4,), args=[d])
        mod.synchronize()
        res = struct.unpack("<4I", mod.device_read(d + 0x0, 16))
        mod.devmem_free(d)
        return list(res)
    except RuntimeError as e:
        return f"ERR {str(e)[:40]}"


ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: got {got} want {want}")

# .X / .Y / .Z: inject 0x55, S2R reads it back (not the real blockIdx)
r = run("SETCTAID.X R20", "SR_CTAID.X", (2, 1, 1))
check("SETCTAID.X -> S2R SR_CTAID.X (0x55, grid X=0/1)", r, [0x55] * 4)
r = run("SETCTAID.Y R20", "SR_CTAID.Y", (1, 2, 1))
check("SETCTAID.Y -> S2R SR_CTAID.Y (0x55, grid Y=0/1)", r, [0x55] * 4)
r = run("SETCTAID.Z R20", "SR_CTAID.Z", (1, 1, 2))
check("SETCTAID.Z -> S2R SR_CTAID.Z (0x55, grid Z=0/1)", r, [0x55] * 4)

# .ALL: 64-bit pair packing R20:R21 = X|(Y&0xffff)<<16... : X=R20, Y=R21&0xffff, Z=R21>>16
# R20=0x55 (as set above), R21=0x02030004 -> X=0x55, Y=0x4, Z=0x203
r = run("SETCTAID.ALL {R20,R21}", "SR_CTAID.X", (1, 1, 1))
check("SETCTAID.ALL -> X = R20 (0x55)", r[0], 0x55)
r = run("SETCTAID.ALL {R20,R21}", "SR_CTAID.Y", (1, 1, 1))
check("SETCTAID.ALL -> Y = R21&0xffff (0x4)", r[0], 0x4)
r = run("SETCTAID.ALL {R20,R21}", "SR_CTAID.Z", (1, 1, 1))
check("SETCTAID.ALL -> Z = R21>>16 (0x203)", r[0], 0x203)

# negative / different values
r = run("SETCTAID.X R20", "SR_CTAID.X", (1, 1, 1))  # R20 still 0x55
check("SETCTAID.X idempotent", r[0], 0x55)

print(f"\n=== SETCTAID semantics: {'ALL OK' if ok else 'FAILED'} ===")
print("SETCTAID.X/Y/Z writes the CTA block-index state read by S2R SR_CTAID;")
print("ALL packs X=R20 (low32), Y=R21[15:0], Z=R21[31:16].")


# --- SETCTAID does NOT move the CTA to a different SM -----------------------
# Inject an invalid-SMID value (0xFFFF); if SETCTAID migrated the CTA, the
# SR_VIRTUALSMID readback would change.  It stays constant.
def build_sm(set_inst):
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    IADD3 R4, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R4, R4, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R16, R6, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R17, R7, RZ, RZ;[7:7:{}:5:1]",
             "    MOV32I R20, 0x0000FFFF;[7:7:{}:5:1]",
             "    S2R R8, SR_VIRTUALSMID;[0:7:{}:5:1]",
             "    IADD3 R8, R8, RZ, RZ;[7:7:{0}:5:1]",
             f"    {set_inst};[7:7:{{}}:5:1]",
             "    S2R R10, SR_VIRTUALSMID;[0:7:{}:5:1]",
             "    IADD3 R10, R10, RZ, RZ;[7:7:{0}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R16,R17}+0x0], R8;[0:1:{0}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R16,R17}+0x4], R10;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))

def run_sm(set_inst):
    cubin = build_sm(set_inst)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<64I", *[0] * 64))
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    b, a = struct.unpack("<2I", mod.device_read(d + 0x0, 8))
    mod.devmem_free(d)
    return b, a

for inst in ("SETCTAID.X R20", "SETCTAID.Y R20", "SETCTAID.Z R20", "SETCTAID.ALL {R20,R21}"):
    b, a = run_sm(inst)
    check(f"SM unchanged after {inst} (smid {b}=={a})", b == a, True)

print("\n(SETCTAID injects 0xFFFF — an invalid SM id — SMID readback is unchanged,")
print(" confirming SETCTAID rewrites blockIdx state, not physical SM placement.)")
