import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UFLO — uniform find-leading-one (udp_pipe; verified SM120, RTX 5090)
#
#   UFLO[.SH] URd, UPu, [~]URb|imm32     (0x12bd UUU / 0x18bd imm)
#
# SILICON SEMANTICS (the note's "0-based position of the leading one" is
# incomplete): UFLO returns the position of the FIRST BIT (scanning from
# bit 31 down) that DIFFERS from bit 31:
#   * bit31 = 0  -> position of the highest set bit (classic leading one)
#   * bit31 = 1  -> position of the highest CLEARED bit below the leading
#                   run of ones (e.g. 0xC0000000 -> 29, 0xFFFF0000 -> 15)
#   * all bits equal (0 or 0xFFFFFFFF) -> 0xFFFFFFFF (no boundary)
#   .SH = 31 - plain = the leading run length (bits matching bit 31).
#   [~] inverts the input first (find the boundary of ~URb).
#
# Verified across single-bit inputs (1<<0..1<<30 -> p; 1<<31 -> 30), leading
# one/zero runs, all-ones/zero sentinel, .SH, [~], and the imm form.
# ---------------------------------------------------------------------------

REF = [
    (0x00000006000472bd, 0x000fca00080e0200),  # UFLO UR4, UPT, UR6
    (0x00000006000472bd, 0x000fca0008000200),  # UFLO UR4, UP0, UR6
    (0x80000006000472bd, 0x000fca00080e0200),  # UFLO UR4, UPT, ~UR6
    (0x00000006000472bd, 0x000fca00080e0600),  # UFLO.SH UR4, UPT, UR6
    (0x12345678000478bd, 0x000fca00080e0200),  # UFLO UR4, UPT, imm
]
flat = assemble_flat("""UFLO UR4, UPT, UR6;[7:7:{}:5:1]
UFLO UR4, UP0, UR6;[7:7:{}:5:1]
UFLO UR4, UPT, ~UR6;[7:7:{}:5:1]
UFLO.SH UR4, UPT, UR6;[7:7:{}:5:1]
UFLO UR4, UPT, 0x12345678;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"
DUMS = "".join(f"    UMOV UR9, UR16;[7:7:{{}}:5:1]\n" for _ in range(4))


def kernel(inst):
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    {inst}[7:7:{{2}}:5:1]
{DUMS}    UMOV UR14, UR16;[7:7:{{}}:5:1]
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


def flo(x):
    """Position of first bit (from 31 down) differing from bit 31."""
    b31 = (x >> 31) & 1
    for p in range(30, -1, -1):
        if ((x >> p) & 1) != b31:
            return p
    return 0xFFFFFFFF


try:
    run("UFLO UR16, UPT, UR6;", 0x80000000)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# Plain: single bits and boundary patterns.
cases = [(1 << p) for p in range(32)] + [
    0xC0000000, 0xE0000000, 0xFFFF0000, 0x7FFFFFFF, 0x7FFFFFFE,
    0x60000000, 0x90000000, 0x80000001, 0x0F000000, 0x12345678,
    0x00000000, 0xFFFFFFFF,
]
for a in cases:
    v = run("UFLO UR16, UPT, UR6;", a)
    exp = flo(a)
    good = v == exp
    ok &= good
    if not good:
        print(f"FAIL plain 0x{a:08X}: {v} (exp {exp})")
print("ok  plain UFLO: single bits + boundary patterns")

# [~] invert.
for a in (0x00000000, 0x7FFFFFFF, 0x00000001, 0x00000010, 0x00000008):
    v = run("UFLO UR16, UPT, ~UR6;", a)
    exp = flo((~a) & 0xFFFFFFFF)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} ~0x{a:08X} -> {v} (exp {exp})")

# .SH = 31 - plain (leading run length).
for a in (0x80000000, 0xC0000000, 0xFFFF0000, 0x00000001, 0x0F000000, 0x7FFFFFFF):
    v = run("UFLO.SH UR16, UPT, UR6;", a)
    exp = 0xFFFFFFFF if flo(a) == 0xFFFFFFFF else 31 - flo(a)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} SH 0x{a:08X} -> {v} (exp {exp})")

# imm form.
v = run("UFLO UR16, UPT, 0x12345678;", 0)
good = v == flo(0x12345678)
ok &= good
print(f"{'ok ' if good else 'FAIL'} imm 0x12345678 -> {v} (exp {flo(0x12345678)})")

print("\n=== UFLO semantic verification: ALL OK ===" if ok else "\n=== UFLO FAILURES ===")
sys.exit(0 if ok else 1)
