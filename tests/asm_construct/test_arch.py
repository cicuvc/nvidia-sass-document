import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_kernel, assemble_flat, arch

# ---------------------------------------------------------------------------
# Cross-arch assembler: db selection + const-bank layout per arch.
#
#   sm90 (Hopper/H800):  SLOT_DEFAULT_CDESC = c[0x0][0x208], param base 0x210,
#                        LDCU is spelled ULDC (opcode 0xab9).
#   sm120 (Blackwell):   SLOT_DEFAULT_CDESC = c[0x0][0x358], param base 0x380,
#                        LDCU (opcode 0x77ac).
# Default process arch is sm120 (historical behaviour); arch= switches just
# the call, and the previous arch is restored afterwards.
# ---------------------------------------------------------------------------

ok = True


def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<48} {got}{'' if good else f'  want {want}'}")


SRC = """#fn k(p<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(p);[1:7:{}:1:0]
    MOV32I R0, 0x1;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R0;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""

# --- sm90: ULDC encoding + const-bank layout -------------------------------
saved = arch.current().name
try:
    arch.set_arch("sm90")
    r = assemble_kernel(SRC)
    check("sm90 param base (0x210)", r.params[0][1], 0x210)
    check("sm90 LDCU->ULDC enc (UR4 + c[0x0][0x208])",
          r.encoded[0][0], 0x0000820000047ab9)
    # arch restored after the call?  set_arch is sticky here; restore manually
finally:
    arch.set_arch(saved)

# --- sm120 (default): LDCU opcode + const-bank layout ----------------------
check("default arch is sm120", arch.current().name, "sm120")
r = assemble_kernel(SRC)
check("sm120 param base (0x380)", r.params[0][1], 0x380)
check("sm120 LDCU enc (UR4 + c[0x0][0x358])",
      r.encoded[0][0], 0x00006b00ff0477ac)

# --- arch= kwarg switches per-call and restores ----------------------------
before = arch.current().name
r90 = assemble_kernel(SRC, arch="sm90")
check("arch=sm90 param base", r90.params[0][1], 0x210)
check("arch restored after kwarg", arch.current().name, before)

# --- unknown arch rejected -------------------------------------------------
try:
    assemble_kernel(SRC, arch="sm100")
    check("unknown arch rejected", "no-error", "ValueError")
except ValueError:
    check("unknown arch rejected", "ValueError", "ValueError")

print(f"\n=== arch management: {'ALL OK' if ok else 'FAILED'} ===")
sys.exit(0 if ok else 1)
