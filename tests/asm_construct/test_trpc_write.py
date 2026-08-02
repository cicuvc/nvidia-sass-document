import subprocess, sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# TRAP_RETURN_PC is WRITE-PROTECTED; NANOTRAP + TRPC experiment impossible
# (SM120)
#
# The user hypothesis: set TRAP_RETURN_PC to a valid PC, then NANOTRAP, and the
# injected trap should "return" to TRAP_RETURN_PC.  Verified: the WRITE cannot
# be done from user SASS —
#   BMOV TRAP_RETURN_PC.LO/HI, src  -> ILLEGAL_INSTRUCTION (715) at runtime,
#     even though the encoding is legal per the spec (cuobjdump decodes
#     `BMOV.32 TRAP_RETURN_PC.LO, R4` correctly) and the spec conditions pass.
#   Same for ATEXIT_PC.LO/HI.
#   BMOV writes to MEXITED / OPT_STACK work fine (write form is functional).
# TRAP_RETURN_PC is therefore READ-only from user code (it reads the live PC
# during divergence as a side effect) and WRITE-protected — the driver / trap
# machinery owns it.  NANOTRAP without a settable TRPC is swallowed: execution
# continues fall-through.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

CHILD = r'''
import sys, struct
sys.path.insert(0, "__BASE__")
from assembler import assemble, CudaModule
slot = sys.argv[1]
lines = ["#fn k(buf<1024>) {",
         "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    MOV32I R4, 0xDEADBEEF;[7:7:{}:5:1]",
         f"    BMOV {slot}, R4;[7:7:{{}}:5:1]",
         "    NOP;[7:7:{}:5:1]","    NOP;[7:7:{}:5:1]","    NOP;[7:7:{}:5:1]","    NOP;[7:7:{}:5:1]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R4;[0:1:{0,1}:1:0]",
         "    EXIT;[7:7:{}:5:0]",
         "}"]
cubin = assemble("\n".join(lines))
mod = CudaModule(cubin)
d = mod.devmem_alloc(1024)
mod.device_write(d, struct.pack("<256I", *[0]*256))
try:
    mod.launch("k", grid=(1,), block=(32,), args=[d]); mod.synchronize()
    print("OK")
except RuntimeError as e:
    print("FAULT", str(e)[:25])
'''
BASE = str(Path(__file__).resolve().parents[2])
py = CHILD.replace("__BASE__", BASE)

def bmov_write_ok(slot):
    r = subprocess.run([sys.executable, "-c", py, slot],
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip().startswith("OK")

check("BMOV write MEXITED (write form functional)", bmov_write_ok("MEXITED"), True)
check("BMOV write TRAP_RETURN_PC.LO -> write-protected",
      bmov_write_ok("TRAP_RETURN_PC.LO"), False)
check("BMOV write TRAP_RETURN_PC.HI -> write-protected",
      bmov_write_ok("TRAP_RETURN_PC.HI"), False)
check("BMOV write ATEXIT_PC.LO -> write-protected",
      bmov_write_ok("ATEXIT_PC.LO"), False)

# NANOTRAP is swallowed: falls through (no way to set TRPC from user code)
CHILD2 = r'''
import sys, struct
sys.path.insert(0, "__BASE__")
from assembler import assemble, CudaModule
lines = ["#fn k(buf<1024>) {",
         "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]",
         "    NANOTRAP;[7:7:{}:5:1]",
         "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0,1}:1:0]",
         "    EXIT;[7:7:{}:5:0]",
         "}"]
cubin = assemble("\n".join(lines))
mod = CudaModule(cubin)
d = mod.devmem_alloc(1024)
mod.device_write(d, struct.pack("<256I", *[0]*256))
mod.launch("k", grid=(1,), block=(32,), args=[d])
mod.synchronize()
v = struct.unpack("<32I", mod.device_read(d, 128))
print("FALLTHROUGH" if v[0] == 0x11111111 else "JUMPED")
'''
r = subprocess.run([sys.executable, "-c", CHILD2.replace("__BASE__", BASE)],
                   capture_output=True, text=True, timeout=15)
check("NANOTRAP (no settable TRPC) is swallowed -> fall-through",
      r.stdout.strip(), "FALLTHROUGH")

print(f"\n=== TRAP_RETURN_PC write-protection: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
