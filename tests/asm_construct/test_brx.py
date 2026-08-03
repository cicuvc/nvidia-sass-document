import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# BRX — register-indirect branch (verified SM120)
#
# `BRX Ra, off` branches to:  next_pc + (sign-extended Ra:R(a+1)) + off*4
#   - Ra is an even-aligned 64-bit pair (MISALIGNED_REG_ERROR if odd); the
#     SHF.R.S32.HI sign-extension idiom (libcusparse) extends a 32-bit offset
#     into R(a+1).
#   - Ra holds a KERNEL-RELATIVE signed byte offset from the NEXT instruction
#     (NOT an absolute address).  off is the encoded sImm*4.
#   - `BRX Ra, #label(x)` with Ra=0 works: the assembler's label resolution
#     fills off = (x - next_pc)/4, so target = next_pc + 0 + (x-next_pc) = x.
#
# Empirical matrix (single warp, block 32, `BRX R4, #label(x)` with 2 MOVs
# between BRX and x):
#   R4=0x00 -> lands on x            (R20/R21 keep sentinels, MOVs skipped)
#   R4=0x10 -> lands x+0x10 (past)   (stores skipped -> buffer stays 0)
#   R4=0x20 -> lands x+0x20 (farther)
# A huge/absolute Ra (e.g. TRAP_RETURN_PC) makes target = next_pc + huge ->
# out of range -> ILLEGAL_ADDRESS / INVALID_PC, i.e. Ra is NOT an absolute
# target.  Used for switch jump tables: LDC table entry -> SHF sign-extend ->
# BRX.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

def run(r4, block=32):
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
             "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]",
             "    MOV32I R21, 0xBBBBBBBB;[7:7:{}:5:1]",
             f"    MOV32I R4, 0x{r4:x};[7:7:{{}}:5:1]",
             "    MOV32I R5, 0x0;[7:7:{}:5:1]",
             "    BRX {R4,R5}, #label(x);[7:7:{}:5:1]",   # target = next_pc + R4 + (x-next_pc)
             "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
             "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",
             "    #def_label(x)",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0,1}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R21;[0:1:{0,1}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    r20, r21 = struct.unpack("<2I", mod.device_read(d, 8))
    mod.devmem_free(d)
    return r20, r21

# R4=0 -> lands on x (skips the two MOVs; sentinels preserved)
r20, r21 = run(0x0)
check("R4=0: BRX lands on x (R20/R21 sentinels kept)", (r20, r21),
      (0xAAAAAAAA, 0xBBBBBBBB))

# R4=0x10 -> lands x+0x10: R20 store (at x) skipped, R21 store (at x+0x10) runs
r20, r21 = run(0x10)
check("R4=0x10: BRX lands at x+0x10 (R20 store skipped, R21 store runs)",
      (r20, r21), (0, 0xBBBBBBBB))

print(f"\n=== BRX semantics: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
