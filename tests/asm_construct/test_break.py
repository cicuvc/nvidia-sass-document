import subprocess, sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# BREAK — peel lanes out of a convergence barrier (verified SM120)#
# `@P BREAK Bi` removes the guarded lanes from Bi's participating-lane mask,
# so the matching `BSYNC Bi` no longer waits for them.
#
# Verified two ways:
#   1. Mask observation: BSSY B0 (all 32 push), then `@P0 BREAK B0` with
#      P0=(tid<16) → `BMOV R4, B0` reads 0xFFFF0000 (bits 0-15 cleared).
#   2. Deadlock: lanes peeled out go spin-wait on a memory flag that the
#      surviving lanes set only AFTER passing `BSYNC B0`.  Without BREAK the
#      BSYNC waits for the spinning lanes → the warp deadlocks (kernel never
#      completes).  With BREAK the peeled lanes no longer block BSYNC → the
#      flag is set → the spin loop exits.  Run in a subprocess so a genuine
#      deadlock is killed by a hard timeout.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

# ---- 1. mask observation --------------------------------------------------
def build_mask():
    lines = ["#fn k(buf<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{0}:13:1]",
             "    BSSY B0, #label(join);[7:7:{}:5:1]",
             "    @P0 BREAK B0;[7:7:{}:5:1]",
             "    BMOV R4, B0;[0:7:{}:5:1]",
             "    BSYNC B0;[7:7:{}:5:1]",
             "    #def_label(join)",
             "    IADD3 R3, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R3, R3, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R8, R6, R3, RZ;[7:7:{0}:5:1]",
             "    IADD3 R9, R7, RZ, RZ;[7:7:{0}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R4;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))

cubin = build_mask()
mod = CudaModule(cubin)
d = mod.devmem_alloc(1024)
mod.device_write(d, struct.pack("<256I", *[0] * 256))
mod.launch("k", grid=(1,), block=(32,), args=[d])
mod.synchronize()
v = struct.unpack("<32I", mod.device_read(d, 128))
mod.devmem_free(d)
vals = {x for x in v}
check("BREAK clears peeled lanes from B0 mask (0xFFFF0000)", 0xFFFF0000 in vals, True)

# ---- 2. deadlock experiment (subprocess + hard timeout) --------------------
CHILD = r'''
import sys, struct
sys.path.insert(0, "__BASE__")
from assembler import assemble, CudaModule
use_break = sys.argv[1] == "yes"
brk = "    @P0 BREAK B0;[7:7:{}:5:1]" if use_break else "    NOP;[7:7:{}:5:1]"
lines = ["#fn k(buf<8>) {",
         "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
         "    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{0}:13:1]",
         "    BSSY B0, #label(join);[7:7:{}:5:1]",
         brk,
         "    @P0 BRA #label(elsewhere);[7:7:{}:5:1]",
         "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
         "    BSYNC B0;[7:7:{}:5:1]",
         "    #def_label(join)",
         "    MOV32I R30, 0x1;[7:7:{}:5:1]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x400], R30;[0:1:{0}:1:0]",
         "    EXIT;[7:7:{}:5:0]",
         "    #def_label(elsewhere)",
         "    #def_label(spin)",
         "    LDG.E R31, desc[{UR4,UR5}][{R6,R7}+0x400];[2:7:{0,1}:5:1]",
         "    IADD3 R30, R31, RZ, RZ;[7:7:{2}:5:1]",
         "    ISETP.EQ.AND P1, PT, R31, 0x0, PT;[7:7:{2}:13:1]",
         "    @P1 BRA #label(spin);[7:7:{}:5:1]",
         "    EXIT;[7:7:{}:5:0]",
         "}"]
cubin = assemble("\n".join(lines))
mod = CudaModule(cubin)
d = mod.devmem_alloc(2048)
mod.device_write(d, struct.pack("<512I", *[0]*512))
mod.launch("k", grid=(1,), block=(32,), args=[d])
mod.synchronize()
flag = struct.unpack("<I", mod.device_read(d + 0x400, 4))[0]
print("COMPLETED flag=%#x" % flag)
'''
BASE = str(Path(__file__).resolve().parents[2])
py = CHILD.replace("__BASE__", BASE)
for use_break, expect in ((False, "DEADLOCK"), (True, "COMPLETED")):
    try:
        r = subprocess.run([sys.executable, "-c", py, "yes" if use_break else "no"],
                           capture_output=True, text=True, timeout=12)
        out = r.stdout.strip()
        verdict = "DEADLOCK" if out.startswith("DEADLOCK") else out
        good = verdict.split()[0] == expect.split()[0]
        print(f"{'ok ' if good else 'FAIL'} BREAK={'yes' if use_break else 'no '}: "
              f"{verdict or 'no-output'} (expect {expect})")
        if not good:
            ok = False
    except subprocess.TimeoutExpired:
        verdict = "DEADLOCK"
        good = expect == "DEADLOCK"
        print(f"{'ok ' if good else 'FAIL'} BREAK={'yes' if use_break else 'no '}: "
              f"DEADLOCK (expect {expect})")
        if not good:
            ok = False

print(f"\n=== BREAK semantics: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
