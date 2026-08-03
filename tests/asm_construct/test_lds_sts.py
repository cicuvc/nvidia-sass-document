import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# LDS / STS — shared-memory load/store (mio_pipe, VQ_AGU).  Verified SM120.
#
#   LDS[.U8|.S8|.U16|.S16|.64|.128] Rd, [Ra+off]    load from shared
#   STS[.U8|.S8|.U16|.S16|.64|.128] [Ra+off], Rb     store to shared
#   addressing: byte offset (Ra+off), immediate-only [RZ+off], uniform
#               [RZ+URb+off] with /STRIDE .X1/.X4/.X8/.X16.
#
# Shared memory window: the SM120 driver maps ~1KB by default for a kernel
# with no declared shared.  Larger windows are obtained by passing
# `shared_mem` (dynamic) at launch — the static .nv.shared.<kernel> section
# is not yet recognized by the driver in hand-built cubins.  All tests here
# launch with shared_mem=0x4000 (16KB).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<44} {got}")

def run_kernel(body, nparams=0, block=1, smem=0x4000):
    """Build a kernel with the given instruction body (params p0..) that
    declares `smem` bytes of STATIC shared (#pragma SHARED), run, return the
    out buffer words.  The .nv.shared.<kernel> section (0x400-padded, sh_info
    -> .text) now makes the driver allocate the window."""
    sig = "out<128>" + "".join(f", p{i}<4>" for i in range(nparams))
    src = ("#fn k(%s) {\n    #pragma SHARED(0x%X)\n" % (sig, smem) + body
           + "    EXIT;[7:7:{}:5:0]\n}")
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(128)
    args = [d] + list(range(nparams))
    mod.launch("k", grid=(1,), block=(block,), args=args)
    mod.synchronize()
    v = struct.unpack("<32I", mod.device_read(d, 128))
    try: mod.devmem_free(d)
    except: pass
    return v

# --- 1. 32-bit roundtrip at various offsets (dynamic 16KB) ------------------
for off, want in [(0x0, 0xDEADBEEF), (0x3FC, 0x12345678), (0x1000, 0xCAFEBABE),
                  (0x3FFC, 0x13579BDF)]:
    body = ("    MOV32I R0, 0x%08X;[7:7:{}:5:1]\n"
            f"    STS [RZ+0x{off:X}], R0;[7:7:{{}}:5:1]\n"
            f"    LDS R1, [RZ+0x{off:X}];[1:7:{{0}}:8:1]\n"
            "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
            "    IADD3 R2, R1, RZ, RZ;[7:7:{1}:5:1]\n"
            "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[0:1:{1}:1:0]\n" % want)
    body = ("    LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]\n"
            "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n" + body)
    r = run_kernel(body)[0]
    check(f"roundtrip @0x{off:X}", hex(r), hex(want))

# --- 2. register-offset addressing + multi-lane ----------------------------
body = ("    LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    S2R R0, SR_TID.X;[0:7:{}:5:1]\n"
        "    IADD3 R3, R0, R0, RZ;[7:7:{0}:5:1]\n"
        "    IADD3 R3, R3, R3, RZ;[7:7:{0}:5:1]\n"
        "    STS [R3], R0;[7:7:{0}:5:1]\n"
        "    LDS R1, [R3];[1:7:{0}:8:1]\n"
        "    IADD3 R2, R1, RZ, RZ;[7:7:{1}:5:1]\n"
        "    IADD3 R8, R6, R3, RZ;[7:7:{0,1}:5:1]\n"
        "    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]\n"
        "    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R2;[0:1:{1}:1:0]\n")
v = run_kernel(body, block=8)
check("multi-lane shared[tid]=tid", v[:8], tuple(range(8)))

# --- 3. LDS narrow loads: sign/zero extension ------------------------------
# store a 4-byte pattern at shared[0]: bytes 0x81, 0x02, 0x03, 0x84
pattern = 0x84030281
def narrow(lds_sfx, want):
    body = ("    LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]\n"
            "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
            f"    MOV32I R0, 0x{pattern:08X};[7:7:{{}}:5:1]\n"
            "    STS [RZ+0x0], R0;[7:7:{}:5:1]\n"
            f"    LDS.{lds_sfx} R1, [RZ+0x0];[1:7:{{0}}:8:1]\n"
            "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
            "    IADD3 R2, R1, RZ, RZ;[7:7:{1}:5:1]\n"
            "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[0:1:{1}:1:0]\n")
    r = run_kernel(body)[0]
    check(f"LDS.{lds_sfx} of 0x{pattern:08x}", hex(r), hex(want))
narrow("U8", 0x81)              # zero-extend low byte
narrow("S8", 0xFFFFFF81)        # sign-extend byte0 (0x81)
narrow("U16", 0x0281)           # zero-extend low 2 bytes
narrow("S16", 0x00000281)       # 0x0281 sign bit clear -> no extend
# byte-offset loads: store full pattern at 0, read byte 1 (0x02) and byte 3
# (0x84 sign-extended)
for lds, off, want in [("U8", 0x1, 0x02), ("S8", 0x3, 0xFFFFFF84)]:
    body = ("    LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]\n"
            "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
            "    MOV32I R0, 0x84030281;[7:7:{}:5:1]\n"
            "    STS [RZ+0x0], R0;[7:7:{}:5:1]\n"
            f"    LDS.{lds} R1, [RZ+0x{off:X}];[1:7:{{0}}:8:1]\n"
            "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
            "    IADD3 R2, R1, RZ, RZ;[7:7:{1}:5:1]\n"
            "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[0:1:{1}:1:0]\n")
    r = run_kernel(body)[0]
    check(f"LDS.{lds} @byte0x{off:X}", hex(r), hex(want))

# --- 4. 64-bit / 128-bit loads and stores ----------------------------------
body = ("    LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    MOV32I R0, 0x11111111;[7:7:{}:5:1]\n"
        "    MOV32I R1, 0x22222222;[7:7:{}:5:1]\n"
        "    STS.64 [RZ+0x0], {R0,R1};[7:7:{}:5:1]\n"
        "    LDS.64 {R2,R3}, [RZ+0x0];[1:7:{0}:8:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    IADD3 R4, R2, RZ, RZ;[7:7:{1}:5:1]\n"
        "    IADD3 R5, R3, RZ, RZ;[7:7:{1}:5:1]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R4;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R5;[0:1:{1}:1:0]\n")
v = run_kernel(body)
check("STS.64/LDS.64 roundtrip", (hex(v[0]), hex(v[1])), (hex(0x11111111), hex(0x22222222)))

# --- 5. offline encoding self-check -----------------------------------------
enc = assemble_flat(
    "LDS R1, [R0+0x100];[7:7:{}:5:1]\n"
    "LDS.U8 R1, [R0];[7:7:{}:5:1]\n"
    "LDS.64 {R0,R1}, [R2];[7:7:{}:5:1]\n"
    "LDS.128 {R0,R1,R2,R3}, [R4];[7:7:{}:5:1]\n"
    "STS [R0+0x8], R1;[7:7:{}:5:1]\n"
    "STS.64 [R0], {R2,R3};[7:7:{}:5:1]\n"
    "LDS R1, [RZ+UR3];[7:7:{}:5:1]\n"
    "STS [RZ+UR3], R1;[7:7:{}:5:1]\n")
for i, e in enumerate(enc):
    assert e[0] & 0xFFF in (0x984, 0x388, 0x1984, 0x1988), (i, hex(e[0]))
# offset field [63:40] for the immediate offset cases
assert (enc[0][0] >> 40) == 0x100, hex(enc[0][0])
print("encoding self-check: LDS/STS widths + offsets + uniform OK")

print(f"\n=== LDS / STS (shared memory): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
