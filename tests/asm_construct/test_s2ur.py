import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# S2UR — special register to uniform register (udp_pipe; verified SM120)
#
#   S2UR URd, SR_<NAME>[.<SUB>]    (0x9c3)
#   URd = the special register's value on the uniform datapath (per-warp).
#   Verified to track SR_CTAID.X per block (same value as S2R in every
#   configuration probed).
# ---------------------------------------------------------------------------

REF = [
    (0x00000000000479c3, 0x000e220000002500),  # S2UR UR4, SR_CTAID.X
    (0x00000000000479c3, 0x000e220000000000),  # S2UR UR4, SR_LANEID
    (0x00000000000479c3, 0x000e220000002100),  # S2UR UR4, SR_TID.X
]
flat = assemble_flat("""S2UR UR4, SR_CTAID.X;[0:7:{}:1:0]
S2UR UR4, SR_LANEID;[0:7:{}:1:0]
S2UR UR4, SR_TID.X;[0:7:{}:1:0]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(inst):
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    {inst}[2:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{2}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, grid):
    mod = build(kernel(inst))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(grid,), block=(32,), args=[0, 0, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


try:
    run("S2UR UR16, SR_CTAID.X;", 1)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

v = run("S2UR UR16, SR_CTAID.X;", 1)
good = v == 0
ok &= good
print(f"{'ok ' if good else 'FAIL'} SR_CTAID.X grid=1: {v} (exp 0)")

# grid=3: all blocks write d[0]; the last writer's CTAID.X lands (2).
v = run("S2UR UR16, SR_CTAID.X;", 3)
good = v == 2
ok &= good
print(f"{'ok ' if good else 'FAIL'} SR_CTAID.X grid=3 (last writer): {v} (exp 2)")

v = run("S2UR UR16, SR_CTAID.Y;", 3)
good = v == 0
ok &= good
print(f"{'ok ' if good else 'FAIL'} SR_CTAID.Y: {v} (exp 0)")

v = run("S2UR UR16, SR_LANEID;", 1)
print(f"info SR_LANEID -> 0x{v:08X} (uniform datapath value)")

v = run("S2UR UR16, SR_CLOCKLO;", 1)
good = v != 0
ok &= good
print(f"{'ok ' if good else 'FAIL'} SR_CLOCKLO -> 0x{v:08X} (nonzero)")

print("\n=== S2UR semantic verification: ALL OK ===" if ok else "\n=== S2UR FAILURES ===")
sys.exit(0 if ok else 1)
