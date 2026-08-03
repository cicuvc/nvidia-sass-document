import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UBREV — uniform bit reverse (udp_pipe; verified SM120, RTX 5090)
#
#   UBREV URd, URb | imm32          (opcode 0x12be RUR / 0x18be RIR)
#   URd = bit_reverse(URb): bit 0 <-> bit 31 (uniform twin of BREV).
#   Guard: @[!]UPg (UniformPredicate, default UPT); UPg -> bits [14:12],
#   UPg@not -> [15]; URb -> [37:32]; URd -> [23:16]; imm -> [63:32].
#
# Uniform-datapath (udp) notes discovered while verifying on silicon:
#   * A uniform register freshly written by LDCU (const-bank load) is not
#     reliably readable by the FIRST udp consumer in a kernel — the first
#     read returns the stale value from the previous launch.  A dummy udp
#     read (e.g. `UMOV UR9, UR6` discarding the result) before the real
#     consumer settles the path.
#   * A GPR-pipe consumer (IADD3 RUR) reading a udp-written UR needs an
#     intervening udp instruction (UMOV filler) before the value is stable.
#   * LDCU param reads lag ~4 launches when the CUBIN module is REUSED
#     across launches in this assembler/driver setup (fresh module per
#     launch reads the param correctly).  Regular LDC is not affected.
# ---------------------------------------------------------------------------

# Reference encodings from the sm_120 spec (also cuobjdump-verified):
REF = {
    "RUR":        (0x00000006000472be, 0x000fca0008000000),  # UBREV UR4, UR6
    "RIR":        (0x12345678000478be, 0x000fca0008000000),  # UBREV UR4, 0x12345678
    "RUR@!UP1":   (0x00000006000492be, 0x000fca0008000000),  # @!UP1 guard
}
flat = assemble_flat("""UBREV UR4, UR6;[7:7:{}:5:1]
UBREV UR4, 0x12345678;[7:7:{}:5:1]
@!UP1 UBREV UR4, UR6;[7:7:{}:5:1]
""")
ok = True
for name, enc in zip(REF, flat):
    good = enc == REF[name]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes {name:8s} lo={enc[0]:016x} hi={enc[1]:016x}")


def bitrev(x):
    r = 0
    for i in range(32):
        r |= ((x >> i) & 1) << (31 - i)
    return r


def build(src):
    cubin = assemble(src, check_deps=False)
    return CudaModule(cubin)


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"

# Kernel 1: UBREV of the `in` kernel parameter (0x12be RUR form).
SRC1 = f"""#fn ubrev_test(in<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(in);[2:7:{{}}:1:0]
    // dummy first udp read of UR6 (settles the uniform datapath)
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    // real read + bit-reverse
    UBREV UR8, UR6;[7:7:{{2}}:5:1]
    UMOV UR10, UR8;[7:7:{{}}:5:1]
    IADD3 R3, PT, PT, RZ, UR8, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""

# Kernel 2: UBREV of a baked-in immediate (0x18be RIR form).
SRC2 = f"""#fn ubrev_imm(out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    UBREV UR8, 0x0F0F0F0F;[7:7:{{}}:5:1]
    UMOV UR10, UR8;[7:7:{{}}:5:1]
    IADD3 R3, PT, PT, RZ, UR8, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""

try:
    build(SRC1)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()
print("GPU: RTX 5090 (or whatever CUDA device 0 is)")

# RUR form: bit-reverse of the kernel parameter.  Fresh module per launch —
# see the LDCU module-reuse caveat in the header comment.
vals = [0x12345678, 0x00000001, 0x80000000, 0x00000000,
        0xFFFFFFFF, 0x0000FFFF, 0xDEADBEEF, 0x0000FF00]
for v in vals:
    mod = build(SRC1)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("ubrev_test", grid=(1,), block=(1,), args=[v, d])
    mod.synchronize()
    got = struct.unpack("<I", mod.device_read(d, 4))[0]
    exp = bitrev(v & 0xFFFFFFFF)
    good = got == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} UBREV 0x{v:08X} -> 0x{got:08X} (exp 0x{exp:08X})")
    mod.devmem_free(d)

# RIR form: baked immediate.
mod = build(SRC2)
d = mod.devmem_alloc(1024)
mod.device_write(d, bytes(1024))
mod.launch("ubrev_imm", grid=(1,), block=(1,), args=[d])
mod.synchronize()
got = struct.unpack("<I", mod.device_read(d, 4))[0]
exp = bitrev(0x0F0F0F0F)
good = got == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} UBREV imm 0x0F0F0F0F -> 0x{got:08X} (exp 0x{exp:08X})")
mod.devmem_free(d)

print("\n=== UBREV semantic verification: ALL OK ===" if ok else "\n=== UBREV FAILURES ===")
sys.exit(0 if ok else 1)
