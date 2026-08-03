import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# ULEPC — uniform load effective PC (udp_pipe; verified SM120, RTX 5090)
#
#   ULEPC {URd,URd+1}                  (0x13ce) — PC of the ULEPC itself
#   ULEPC {URd,URd+1}, sImm58          (0x19ce) — (instr_addr + 16) + sImm58
#                                          (next-instruction-relative; #label
#                                          operands resolve to target - next)
#
# Verified identical to LEPC on silicon: same target computed by both for the
# same label; pc-only form returns the instruction's own address; 64-bit pair
# hi word is 0 for kernel-text addresses.
# ---------------------------------------------------------------------------

# Reference encodings (schedule [7:7:{}:5:1], fixed-latency COUPLED_MATH).
REF = [
    (0x00000000000473ce, 0x000fca0008000000, "ULEPC {UR4,UR5}"),
    (0x00000000000479ce, 0x000fca0008000000, "ULEPC {UR4,UR5}, 0x0"),
    (0x00000000400479ce, 0x000fca0008000000, "ULEPC {UR4,UR5}, 0x40"),
    (0xfffffffff00479ce, 0x000fca000803ffff, "ULEPC {UR4,UR5}, -0x10"),
]
flat = assemble_flat("""ULEPC {UR4,UR5};[7:7:{}:5:1]
ULEPC {UR4,UR5}, 0x0;[7:7:{}:5:1]
ULEPC {UR4,UR5}, 0x40;[7:7:{}:5:1]
ULEPC {UR4,UR5}, -0x10;[7:7:{}:5:1]
""")
ok = True
for i, (lo, hi, name) in enumerate(REF):
    good = flat[i] == (lo, hi)
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes {name:24s} lo={flat[i][0]:016x} hi={flat[i][1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def read_ur_pair(ur_lo, ur_hi, rd_lo, rd_hi, off):
    return f"""    UMOV UR9, {ur_lo};[7:7:{{}}:5:1]
    UMOV UR9, {ur_hi};[7:7:{{}}:5:1]
    UMOV UR9, {ur_lo};[7:7:{{}}:5:1]
    UMOV UR9, {ur_hi};[7:7:{{}}:5:1]
    UMOV UR14, {ur_lo};[7:7:{{}}:5:1]
    IADD3 {rd_lo}, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    UMOV UR15, {ur_hi};[7:7:{{}}:5:1]
    IADD3 {rd_hi}, PT, PT, RZ, UR15, RZ;[7:7:{{}}:8:1]
{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], {rd_lo};[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off+4:x}], {rd_hi};[7:7:{{0,1}}:1:0]
"""


SRC = f"""#fn t(out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    ULEPC {{UR16, UR17}};[7:7:{{}}:5:1]           # 0x20 — pc-only
    LEPC {{R20, R21}};[7:7:{{}}:5:1]              # 0x30 — pc-only (GPR twin)
    ULEPC {{UR18, UR19}}, #label(tgt);[7:7:{{}}:5:1]  # 0x40
    LEPC {{R22, R23}}, #label(tgt);[7:7:{{}}:5:1]     # 0x50
    ULEPC {{UR24, UR25}}, 0x40;[7:7:{{}}:5:1]     # 0x60 — raw imm
    ULEPC {{UR26, UR27}}, #label(tgt);[7:7:{{}}:5:1]  # 0x70
    ULEPC {{UR28, UR29}}, -0x10;[7:7:{{}}:5:1]    # 0x80 — negative imm
    #def_label(tgt)                               # 0x90
{read_ur_pair("UR16","UR17","R2","R3",0x0)}
{read_ur_pair("UR18","UR19","R8","R9",0x10)}
{read_ur_pair("UR24","UR25","R12","R13",0x20)}
{read_ur_pair("UR26","UR27","R14","R15",0x30)}
{read_ur_pair("UR28","UR29","R16","R17",0x40)}
{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x8], R20;[7:7:{{0,1}}:1:0]
{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0xc], R22;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""

try:
    build(SRC)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()
reset_context()
mod = build(SRC)
d = mod.devmem_alloc(1024)
mod.device_write(d, bytes(1024))
mod.launch("t", grid=(1,), block=(1,), args=[d])
mod.synchronize()
data = mod.device_read(d, 0x50)
vals = struct.unpack("<20I", data)
mod.devmem_free(d)

def at(off):
    return vals[off // 4]

base = at(0x00) - 0x20          # ULEPC@0x20 pc-only = its own address
print(f"ULEPC pc-only = 0x{at(0x00):08x} (base 0x{base:x} + 0x20)")

checks = {
    "pc-only returns own address (base+0x20)": at(0x00) == base + 0x20,
    "LEPC pc-only own address = +0x10":        at(0x08) == base + 0x30,
    "hi word of 64-bit PC pair == 0":          at(0x04) == 0,
    "ULEPC #tgt == LEPC #tgt":                 at(0x10) == at(0x0c),
    "label target == base+0x90":               at(0x10) == base + 0x90,
    "raw imm 0x40: next(0x70)+0x40 == base+0xb0": at(0x20) == base + 0xb0,
    "label tgt again == base+0x90":            at(0x30) == base + 0x90,
    "neg imm -0x10: next(0x90)-0x10 == base+0x80": at(0x40) == base + 0x80,
}
for name, good in checks.items():
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name}")

print("\n=== ULEPC semantic verification: ALL OK ===" if ok else "\n=== ULEPC FAILURES ===")
sys.exit(0 if ok else 1)
