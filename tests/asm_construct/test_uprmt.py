import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UPRMT — uniform byte permute (udp_pipe; verified SM120, RTX 5090)
#
#   UPRMT URd, URa, URb|imm32, URc    (0x1296 UR / 0x1896 imm)
#   Control = the 3rd operand; for each output byte i the control nibble i
#   (LSB-first) selects the byte:
#     bits 1:0  -> byte index within the chosen source
#     bit  2    -> source: 0 = URa, 1 = URc
#     bit  3    -> 0x00 (invalid), except 0xF -> 0xFF
#   (Verified: identity 0x76543210, interleave, splats, register + imm
#   control forms.)
# ---------------------------------------------------------------------------

REF = [
    (0x0000000706047296, 0x000fca0008000008),  # UPRMT UR4, UR6, UR7, UR8
    (0x1234567806047896, 0x000fca0008000008),  # UPRMT UR4, UR6, imm, UR8
]
flat = assemble_flat("""UPRMT UR4, UR6, UR7, UR8;[7:7:{}:5:1]
UPRMT UR4, UR6, 0x12345678, UR8;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(inst, imm=False):
    if imm:
        loads = ("    LDCU UR6, #param(a);[2:7:{}:1:0]\n"
                 "    LDCU UR8, #param(c);[4:7:{}:1:0]\n"
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"
                 "    UMOV UR9, UR8;[7:7:{4}:5:1]\n")
        reqs = "{2,4}"
    else:
        loads = ("    LDCU UR6, #param(a);[2:7:{}:1:0]\n"
                 "    LDCU UR7, #param(b);[3:7:{}:1:0]\n"
                 "    LDCU UR8, #param(c);[4:7:{}:1:0]\n"
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"
                 "    UMOV UR9, UR7;[7:7:{3}:5:1]\n"
                 "    UMOV UR9, UR8;[7:7:{4}:5:1]\n")
        reqs = "{2,3,4}"
    return f"""#fn t(a<8>, b<8>, c<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
{loads}    {inst}[7:7:{reqs}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a, b, c, imm=False):
    mod = build(kernel(inst, imm=imm))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,),
               args=[a & 0xFFFFFFFF, b & 0xFFFFFFFF, c & 0xFFFFFFFF, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


def prmt(a, c, ctrl):
    r = 0
    for i in range(4):
        sel = (ctrl >> (i * 4)) & 0xF
        if sel == 0xF:
            byte = 0xFF
        elif sel & 8:
            byte = 0
        else:
            src = c if (sel & 4) else a
            byte = (src >> ((sel & 3) * 8)) & 0xFF
        r |= byte << (i * 8)
    return r


try:
    run("UPRMT UR16, UR6, 0x76543210, UR8;", 0x44332211, 0, 0x88776655, imm=True)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

A, C = 0x44332211, 0x88776655
ctrls = [0x00000000, 0x00000001, 0x00000007, 0x0000001B, 0x00001234,
         0x000000E4, 0x00007777, 0x76543210, 0x0000FFFF, 0x54105410]
for ctrl in ctrls:
    v = run("UPRMT UR16, UR6, 0x{c:X}, UR8;".format(c=ctrl), A, 0, C, imm=True)
    exp = prmt(A, C, ctrl)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} imm ctrl=0x{ctrl:08X}: 0x{v:08X} (model 0x{exp:08X})")

for ctrl in (0x1B, 0x76543210, 0x7777, 0x1234):
    v = run("UPRMT UR16, UR6, UR7, UR8;", A, ctrl, C)
    exp = prmt(A, C, ctrl)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} reg ctrl=0x{ctrl:08X}: 0x{v:08X} (model 0x{exp:08X})")

print("\n=== UPRMT semantic verification: ALL OK ===" if ok else "\n=== UPRMT FAILURES ===")
sys.exit(0 if ok else 1)
