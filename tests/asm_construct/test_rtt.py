import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat

# ---------------------------------------------------------------------------
# RTT — Return from Trap (verified encoding + privilege on SM120)
#
# RTT (0x94f, cbu_pipe, BRANCH_TYPE=BRT_RETURN) is the trap-handler RETURN
# instruction: it returns to TRAP_RETURN_PC (the address the trap machinery
# saved when dispatching the handler).  It is PRIVILEGED — executing it from
# ordinary user code (outside a trap-handler context) raises
# ILLEGAL_INSTRUCTION (715), even when TRAP_RETURN_PC is legitimately set (via
# BSSY's divergence side effect).
#
# Encoding: RTT uses TABLES_opex_2 (not opex_0) — only stall=0 is a legal
# scheduling value; `[7:7:{}:5:1]` is rejected as an illegal batch/usched
# combination.  `RTT;[7:7:{}:0:1]` encodes to lo=0x000000000000794f.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

# Encoding: RTT with the legal opex_2 sched (stall=0)
lo, _ = assemble_flat("RTT;[7:7:{}:0:1]")[0]
check("RTT encodes (0x94f, TABLES_opex_2, stall=0)", lo, 0x000000000000794f)

# RTT is privileged: 715 from user code even with TRPC set via BSSY
CHILD = r'''
import sys, struct
sys.path.insert(0, "__BASE__")
from assembler import assemble, CudaModule
lines = ["#fn k(buf<8>) {",
         "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
         "    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{0}:13:1]",
         "    BSSY B0, #label(join);[7:7:{}:5:1]",   # TRPC = BSSY addr
         "    @P0 BRA #label(pathA);[7:7:{}:5:1]",
         "    RTT;[7:7:{}:0:1]",
         "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
         "    BRA #label(join);[7:7:{}:5:1]",
         "    #def_label(pathA)",
         "    MOV32I R21, 0x55555555;[7:7:{}:5:1]",
         "    BSYNC B0;[7:7:{}:5:1]",
         "    #def_label(join)",
         "    EXIT;[7:7:{}:5:0]",
         "}"]
cubin = assemble("\n".join(lines))
mod = CudaModule(cubin)
d = mod.devmem_alloc(2048)
mod.device_write(d, struct.pack("<512I", *[0]*512))
try:
    mod.launch("k", grid=(1,), block=(32,), args=[d]); mod.synchronize()
    print("OK")
except RuntimeError as e:
    print("FAULT", str(e)[:25])
'''
BASE = str(Path(__file__).resolve().parents[2])
r = subprocess.run([sys.executable, "-c", CHILD.replace("__BASE__", BASE)],
                   capture_output=True, text=True, timeout=15)
check("RTT from user code (TRPC set via BSSY) -> ILLEGAL_INSTRUCTION (privileged)",
      "FAULT" if r.stdout.strip().startswith("FAULT") else "OK", "FAULT")

print(f"\n=== RTT (trap return, privileged): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
