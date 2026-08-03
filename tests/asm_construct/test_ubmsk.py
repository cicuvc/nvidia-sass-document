import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UBMSK — uniform bitmask (udp_pipe; verified SM120, RTX 5090)
#
#   UBMSK[.C|.W] URd, URa, URb | imm32     (0x129b RUR / 0x189b RIR)
#   URd = ((1 << width) - 1) << pos, truncated to 32 bits.
#   URa = POSITION, URb = WIDTH (same semantics as BMSK, silicon-confirmed):
#     .C (clamp, default): operands as-is; the "clamp" is just the 32-bit
#        truncation (pos=2, w=32 -> 0xFFFFFFFC, NOT width-clamped).
#     .W (wrap): pos & 31 and width & 31 (pos=33 -> 1, width=33 -> 1).
#   Fields: cw -> [75], URb -> [39:32], URa -> [31:24], URd -> [23:16],
#   guard UPg -> [14:12]/[15].
#
# Uniform-datapath recipe (see test_ubrev.py): LDCU-loaded URs need a dummy
# first udp read, GPR consumers need an intervening udp instruction, and
# LDCU param reads need a fresh module per launch (module reuse lags).
# ---------------------------------------------------------------------------

REF = [
    (0x000000070604729b, 0x000fca0008000000),  # UBMSK UR4, UR6, UR7 (C)
    (0x000000070604729b, 0x000fca0008000800),  # UBMSK.W UR4, UR6, UR7
    (0x000000210604789b, 0x000fca0008000000),  # UBMSK UR4, UR6, 0x21
    (0x000000210604789b, 0x000fca0008000800),  # UBMSK.W UR4, UR6, 0x21
]
flat = assemble_flat("""UBMSK UR4, UR6, UR7;[7:7:{}:5:1]
UBMSK.W UR4, UR6, UR7;[7:7:{}:5:1]
UBMSK UR4, UR6, 0x21;[7:7:{}:5:1]
UBMSK.W UR4, UR6, 0x21;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"

# Kernel 1 (RIR): width is an immediate, position from the `pos` param.
def kernel_rir(width, cw):
    modif = ".W" if cw else ""
    return f"""#fn ubmsk_test(pos<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(pos);[2:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UBMSK{modif} UR8, UR6, 0x{width:X};[7:7:{{2}}:5:1]
    UMOV UR10, UR8;[7:7:{{}}:5:1]
    IADD3 R3, PT, PT, RZ, UR8, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""

# Kernel 2 (RUR): both position and width from params.
def kernel_rur(cw):
    modif = ".W" if cw else ""
    return f"""#fn ubmsk_test(pos<8>, wid<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(pos);[2:7:{{}}:1:0]
    LDCU UR7, #param(wid);[3:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR7;[7:7:{{3}}:5:1]
    UBMSK{modif} UR8, UR6, UR7;[7:7:{{2,3}}:5:1]
    UMOV UR10, UR8;[7:7:{{}}:5:1]
    IADD3 R3, PT, PT, RZ, UR8, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""

try:
    build(kernel_rir(3, 0))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# RIR battery: (pos, width_imm, cw, expected)
rir_cases = [
    (4, 3, 0, 0x00000070, "C pos=4 w=3"),
    (3, 4, 0, 0x00000078, "C pos=3 w=4"),
    (30, 4, 0, 0xC0000000, "C pos=30 w=4 (trunc)"),
    (30, 4, 1, 0xC0000000, "W pos=30 w=4"),
    (31, 2, 1, 0x80000000, "W pos=31 w=2"),
    (2, 32, 0, 0xFFFFFFFC, "C pos=2 w=32 (trunc, not clamp)"),
    (0, 33, 0, 0xFFFFFFFF, "C pos=0 w=33"),
    (0, 33, 1, 0x00000001, "W pos=0 w=33 (width&31=1)"),
    (33, 1, 1, 0x00000002, "W pos=33 w=1 (pos&31=1)"),
    (33, 1, 0, 0x00000000, "C pos=33 w=1 (shifted out)"),
    (8, 24, 0, 0xFFFFFF00, "C pos=8 w=24"),
    (0, 31, 0, 0x7FFFFFFF, "C pos=0 w=31"),
]
for pos, width, cw, exp, lab in rir_cases:
    mod = build(kernel_rir(width, cw))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("ubmsk_test", grid=(1,), block=(1,), args=[pos, d])
    mod.synchronize()
    got = struct.unpack("<I", mod.device_read(d, 4))[0]
    good = got == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} RIR {lab:28s} -> 0x{got:08X} (exp 0x{exp:08X})")
    mod.devmem_free(d)

# RUR battery: (pos, width, cw, expected)
rur_cases = [
    (4, 3, 0, 0x00000070, "C pos=4 w=3"),
    (30, 4, 1, 0xC0000000, "W pos=30 w=4"),
    (33, 1, 1, 0x00000002, "W pos=33 w=1"),
    (0, 32, 1, 0x00000000, "W pos=0 w=32"),
    (2, 32, 0, 0xFFFFFFFC, "C pos=2 w=32"),
]
for pos, width, cw, exp, lab in rur_cases:
    mod = build(kernel_rur(cw))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("ubmsk_test", grid=(1,), block=(1,), args=[pos, width, d])
    mod.synchronize()
    got = struct.unpack("<I", mod.device_read(d, 4))[0]
    good = got == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} RUR {lab:28s} -> 0x{got:08X} (exp 0x{exp:08X})")
    mod.devmem_free(d)

print("\n=== UBMSK semantic verification: ALL OK ===" if ok else "\n=== UBMSK FAILURES ===")
sys.exit(0 if ok else 1)
