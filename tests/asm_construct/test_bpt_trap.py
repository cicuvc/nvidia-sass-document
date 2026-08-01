import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# PTX `trap;` -> BPT.TRAP — verification (SM90 + SM120).
#
# ptxas lowers PTX `trap;` / `__trap()` to:
#     BPT.TRAP 0x1        (lo=0x000000040000795c, opcode 0x95c, cbu_pipe)
#
# BPT (BreakPoinT): opcode 0x95c, 2 variants (noDRAIN / onlyDRAIN scheduling),
# /BPT_TRAP_INT:bpt selector (TRAP=3, INT=4) + UImm(3):Sb trap selector.
#
# Verified on GPU (each case in a clean subprocess — a real trap poisons the
# CUDA context with CUDA_ERROR_LAUNCH_FAILED (719) that persists):
#   BPT.TRAP 0x1 -> launch FAILS with 719 (the trap fires)
#   BPT.TRAP 0x3, 0x7 -> 719 too
#   BPT.TRAP 0x2, 0x4, 0x5, 0x6 -> kernel runs (no trap)
#   BPT.INT 0x1..4 -> kernel runs (interrupt, not trap, masked in compute)
#   BPT.TRAP 0x0 -> assembler rejects (CONDITION: TRAP illegal for Sb=0)
#
# Contrast with NANOTRAP (see nanotrap.md): NANOTRAP injects a hardware trap
# that the runtime swallows (no fault, just ~10k-cycle cost); BPT.TRAP is the
# real user-visible trap — PTX `trap` semantics (kernel launch failure).
# ---------------------------------------------------------------------------

import subprocess, os, sys as _sys

ASSEMBLER = os.path.join(os.path.dirname(__file__), "..", "assembler")

def run_in_subprocess(bpt, sb):
    """Run one BPT variant in a clean CUDA context (subprocess) so a 719
    context poisoning doesn't affect the rest.  Result is written to a temp
    file (stdout capture was unreliable for the OK path)."""
    import tempfile
    outfile = tempfile.mktemp(suffix=".out")
    code = f'''
import sys, struct
sys.path.insert(0, {ASSEMBLER!r})
from assembler import assemble, CudaModule
lines = ["#fn k(buf<1024>) {{",
         "    LDCU.64 UR4, c[0x0][0x358];[0:7:{{}}:1:0]",
         "    LDC.64 R6, #param(buf);[0:7:{{}}:1:0]",
         "    BPT.{bpt} 0x{sb:x};[7:7:{{}}:5:1]",
         "    MOV32I R22, 0xdeadbeef;[7:7:{{}}:5:1]",
         "    STG.E desc[UR4][R6.64+0x0], R22;[0:1:{{0}}:1:0]",
         "    EXIT;[7:7:{{}}:5:0]",
         "}}"]
cubin = assemble("\\n".join(lines))
mod = CudaModule(cubin)
d = mod.devmem_alloc(1024)
try:
    mod.launch("k", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack("<I", mod.device_read(d+0x0, 4))[0]
    open({outfile!r}, "w").write("OK 0x%08x" % res)
except RuntimeError as e:
    open({outfile!r}, "w").write("ERR " + str(e)[:40])
'''
    r = subprocess.run([_sys.executable, "-c", code], capture_output=True, text=True)
    try:
        with open(outfile) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "NOOUTPUT: " + (r.stderr or "")[-80:]


print("=== PTX trap; -> BPT.TRAP (SM120, clean subprocess per case) ===")
print(f"{'variant':<16} result")
results = {}
for bpt in ("TRAP", "INT"):
    for sb in (1, 2, 3, 4, 5, 6, 7):
        res = run_in_subprocess(bpt, sb)
        results[(bpt, sb)] = res
        print(f"  BPT.{bpt:<4} 0x{sb:x}   {res}")

# assertions
ok = True
for sb in (1, 3, 7):
    ok &= results[("TRAP", sb)].startswith("ERR")
for sb in (2, 4, 5, 6):
    ok &= results[("TRAP", sb)].startswith("OK 0xdeadbeef")
for sb in (1, 2, 3, 4):
    ok &= results[("INT", sb)].startswith("OK")

print(f"\n=== BPT.TRAP: Sb=1/3/7 trap (719), others continue; INT never faults: "
      f"{'ALL OK' if ok else 'FAILED'} ===")
print("ptxas emits BPT.TRAP 0x1 (a trap-firing selector) for PTX trap;/__trap()")
sys.exit(0 if ok else 1)
