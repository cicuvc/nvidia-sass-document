import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# JMP — absolute jump (verified encoding + semantics on SM120)
#
# JMP imm (0x94a) is the ABSOLUTE counterpart of BRA: `target = Sa*4`, a 55-bit
# unsigned immediate, with NO PC added (unlike BRA's next_pc + sImm*4).  Used
# for jump tables / far jumps where the compiler emits an absolute address.
#
# Consequence for the hand assembler: **labels cannot be used as JMP targets** —
# the label mechanism resolves (target - next_pc)/4 (PC-relative, correct for
# BRA), but JMP interprets that as an absolute Sa*4, landing on a tiny invalid
# address -> ILLEGAL_ADDRESS (700) / INVALID_PC.  The same field bits that a
# BRA renders as `0x580` (absolute) render as `0x490` (= Sa*4) under JMP
# (see notes/sm90/instr/jmp.md).
#
# Variants (all verified to encode via tools/decode_jmp.py):
#   JMP 0x490                       imm, absolute target Sa*4
#   JMP c[0x2][0x200]               const-bank target (jump tables)
#   JMP.DIV UR4, 0x490              uniform-register form (cond .DIV/.CONV)
#   JMP.U   UP0, 0x490              uniform-predicate form (cond .U)
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

# A label-relative JMP points at a tiny absolute address -> faults (700).
# Run in a subprocess so the fault is isolated.
import subprocess
CHILD = r'''
import sys, struct
sys.path.insert(0, "__BASE__")
from assembler import assemble, CudaModule
lines = ["#fn k(buf<1024>) {",
         "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]",
         "    JMP #label(x);[7:7:{}:5:1]",        # relative-resolved, but JMP is absolute
         "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
         "    #def_label(x)",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0,1}:1:0]",
         "    EXIT;[7:7:{}:5:0]",
         "}"]
cubin = assemble("\n".join(lines))
mod = CudaModule(cubin)
d = mod.devmem_alloc(1024)
mod.device_write(d, struct.pack("<256I", *[0]*256))
try:
    mod.launch("k", grid=(1,), block=(32,), args=[d]); mod.synchronize()
    print("NO-FAULT")
except RuntimeError as e:
    print("FAULT", str(e)[:25])
'''
BASE = str(Path(__file__).resolve().parents[2])
r = subprocess.run([sys.executable, "-c", CHILD.replace("__BASE__", BASE)],
                   capture_output=True, text=True, timeout=15)
good = r.stdout.strip().startswith("FAULT")
check("JMP #label(x) (PC-relative) faults — JMP is absolute, not relative",
      "FAULT" if good else "NO-FAULT", "FAULT")

# The imm encoding matches the decoder's rendering: JMP.DIV UR4, 0x490
from assembler import assemble_flat
lo, _ = assemble_flat("JMP.DIV UR4, 0x490;[7:7:{}:5:1]")[0]
check("JMP.DIV UR4, 0x490 encodes (cond=.DIV, UR=4)", lo, 0x000000060424794a)

lo, _ = assemble_flat("JMP.CONV UR4, 0x490;[7:7:{}:5:1]")[0]
check("JMP.CONV UR4, 0x490 encodes (cond=.CONV)", lo, 0x000000070424794a)

print(f"\n=== JMP (absolute target) semantics: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
