import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UPOPC — uniform population count (udp_pipe; verified SM120, RTX 5090)
#
#   UPOPC URd, [~]URb|imm32    (0x12bf UUU / 0x18bf imm)
#   URd = number of set bits in URb; [~] counts the bits of ~URb instead.
# ---------------------------------------------------------------------------

REF = [
    (0x00000006000472bf, 0x000fca0008000000),  # UPOPC UR4, UR6
    (0x12345678000478bf, 0x000fca0008000000),  # UPOPC UR4, imm
]
flat = assemble_flat("""UPOPC UR4, UR6;[7:7:{}:5:1]
UPOPC UR4, 0x12345678;[7:7:{}:5:1]
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
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    {inst}[7:7:{{2}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a):
    mod = build(kernel(inst))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[a & 0xFFFFFFFF, 0, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


def popc(x):
    return bin(x & 0xFFFFFFFF).count("1")


try:
    run("UPOPC UR16, UR6;", 0x12345678)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

for a in (0x00000000, 0x00000001, 0x80000000, 0xFFFFFFFF, 0x12345678,
          0x0F0F0F0F, 0xAAAAAAAA, 0x0000FFFF):
    v = run("UPOPC UR16, UR6;", a)
    exp = popc(a)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} popc(0x{a:08X}) = {v} (exp {exp})")

for a in (0x00000000, 0x00000001, 0xFFFFFFFF):
    v = run("UPOPC UR16, ~UR6;", a)
    exp = popc(~a)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} popc(~0x{a:08X}) = {v} (exp {exp})")

v = run("UPOPC UR16, 0x12345678;", 0)
good = v == popc(0x12345678)
ok &= good
print(f"{'ok ' if good else 'FAIL'} imm 0x12345678 = {v} (exp {popc(0x12345678)})")

print("\n=== UPOPC semantic verification: ALL OK ===" if ok else "\n=== UPOPC FAILURES ===")
sys.exit(0 if ok else 1)
