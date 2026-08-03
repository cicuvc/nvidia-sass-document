import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# B-register (B0..B15) content via BMOV — what does a branch register store?
# (verified SM120, single warp)
#
# BMOV (cbu_pipe) reads per-warp CBU state: `BMOV Rd, cbu_state` (0x355) moves a
# CBU_STATE slot into a GPR.  The B registers (B0..B15) are CBU_STATE values
# 0..15.  Empirically (single B-register read, no back-to-back BMOV):
#   * after an UNPREDICATED BSSY (all 32 lanes push), B0 reads 0xFFFFFFFF —
#     the participating-lane mask (warp-uniform, all 32 lanes).
#   * a predicated BSSY (subset pushes) makes the pushed lanes read the subset
#     mask (e.g. 0xFFFF for tid<16).
#   * before any BSSY, B0 = 0x0; after BSYNC (entry popped), B0 = 0x0.
#   * an unused B1 = 0x0.
#
# So B0's readable 32-bit content is the ACTIVE/participating thread mask of
# the BSSY-established divergence point — NOT an address.  The reconvergence
# target lives in the BSSY instruction's own Sa field; the return PC is carried
# implicitly by the hardware sync stack and is not exposed by the 32-bit B-read.
#
# Caveat: two BMOV state reads back-to-back race in a hand-built cubin (the
# second read clobbers the first's GPR result), so each probe reads one slot.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

def run(inner, block=32, stall=13):
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             f"    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{{0}}:{stall}:1]",
             ] + inner + [
             "    IADD3 R3, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R3, R3, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R8, R6, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R9, R7, RZ, RZ;[7:7:{0}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R4;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    v = struct.unpack("<32I", mod.device_read(d, 128))
    mod.devmem_free(d)
    return v[0:32]

# 1. B0 after unpredicated full-warp BSSY = 0xFFFFFFFF (all lanes active)
b0 = run(["    BSSY B0, #label(join);[7:7:{}:5:1]",
          "    BMOV R4, B0;[0:7:{}:5:1]",
          "    BSYNC B0;[7:7:{}:5:1]",
          "    #def_label(join)"])
check("1. B0 after full-warp BSSY = 0xFFFFFFFF", sorted(set(b0)), [0xFFFFFFFF])

# 2. B0 before any BSSY = 0x0
b0 = run(["    BMOV R4, B0;[0:7:{}:5:1]",
          "    #def_label(join)"])
check("2. B0 (no BSSY ever) = 0x0", sorted(set(b0)), [0])

# 3. B0 after BSYNC (entry popped) = 0x0
b0 = run(["    BSSY B0, #label(join);[7:7:{}:5:1]",
          "    BSYNC B0;[7:7:{}:5:1]",
          "    #def_label(join)",
          "    BMOV R4, B0;[0:7:{}:5:1]"])
check("3. B0 after BSYNC = 0x0", sorted(set(b0)), [0])

# 4. unused B1 = 0x0
b0 = run(["    BSSY B0, #label(join);[7:7:{}:5:1]",
          "    BMOV R4, B1;[0:7:{}:5:1]",
          "    BSYNC B0;[7:7:{}:5:1]",
          "    #def_label(join)"])
check("4. unused B1 = 0x0", sorted(set(b0)), [0])

# 5. predicated BSSY (tid<16 push): pushed lanes read the subset mask 0xFFFF
b0 = run(["    @P0 BSSY B0, #label(join);[7:7:{}:5:1]",
          "    BMOV R4, B0;[0:7:{}:5:1]",
          "    BSYNC B0;[7:7:{}:5:1]",
          "    #def_label(join)"])
mask = b0[0]  # lane 0 pushed
check("5. predicated BSSY: lane0 B0 = subset mask 0xFFFF", mask, 0xFFFF)

print(f"\n=== B-register content via BMOV: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
