import subprocess, sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# WARPSYNC.COLLECTIVE + ENDCOLLECTIVE — warp collective-sync region (SM120)
#
# WARPSYNC.COLLECTIVE Rmask, TGT opens a collective region; ENDCOLLECTIVE
# closes it.  The whole thing is wrapped in a BSSY/BSYNC bracket (BSSY target
# = the loop-back/join after the BSYNC; WARPSYNC target = the instruction right
# after ENDCOLLECTIVE, i.e. the BSYNC).  Real idiom (libcusparse, sm_90):
#
#     BSSY B1, LOOP
#     WARPSYNC.COLLECTIVE Rmask, TGT
#     NOP                       ; region body
#     ENDCOLLECTIVE
#   TGT: BSYNC B1
#   LOOP: ...
#
# Verified empirically (SM120, hand-built cubin):
#   1. Rmask must be a SUPERSET of the lanes executing WARPSYNC.COLLECTIVE;
#      an executing lane outside the mask raises ILLEGAL_INSTRUCTION (715).
#      (all-32 active: mask 0xFFFFFFFF ok, 0xFFFF fails; survivors tid>=16:
#      mask 0xFFFF0000 and 0xFFFFFFFF both ok, 0xFFFF fails.)
#   2. MCOLLECTIVE (CBU_STATE 32) = Rmask & active-lanes DURING the region;
#      it reads 0x0 after ENDCOLLECTIVE (region closed).  With Rmask=0xFFFFFFFF
#      and only tid>=16 active it reads 0xFFFF0000 — the mask is clamped to the
#      active set, not the declared value.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

# ---- MCOLLECTIVE inside the region = Rmask & active ------------------------
def mcollective_inside(mask, exit_lanes, block=32):
    pre = ["    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]",
           "    LDC.64 R6, #param(buf);[1:7:{}:1:0]",
           "    S2R R2, SR_TID.X;[0:7:{}:5:1]"]
    if exit_lanes:
        pre += ["    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{0}:13:1]",
                "    @P0 EXIT;[7:7:{}:5:0]"]
    lines = ["#fn k(buf<1024>) {"] + pre + [
             f"    MOV32I R5, 0x{mask};[7:7:{{}}:5:1]",
             "    BSSY B1, #label(loop);[7:7:{}:5:1]",
             "    WARPSYNC.COLLECTIVE R5, #label(sync);[7:7:{}:5:1]",
             "    BMOV R4, MCOLLECTIVE;[0:7:{}:5:1]",
             "    NOP;[7:7:{}:5:1]", "    NOP;[7:7:{}:5:1]",
             "    STG.E desc[UR4][R6.64+0x0], R4;[0:1:{0,1}:1:0]",
             "    ENDCOLLECTIVE;[7:7:{}:5:1]",
             "    #def_label(sync)",
             "    BSYNC B1;[7:7:{}:5:1]",
             "    #def_label(loop)",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    v = struct.unpack(f"<{block}I", mod.device_read(d, block * 4))
    mod.devmem_free(d)
    return sorted({x for x in v})

# all 32 lanes active, declared full mask
v = mcollective_inside("FFFFFFFF", exit_lanes=False)
check("MCOLLECTIVE inside (all-active, mask=0xFFFFFFFF) = 0xFFFFFFFF",
      0xFFFFFFFF in v, True)
# survivors tid>=16, declared full mask -> clamped to active (0xFFFF0000)
v = mcollective_inside("FFFFFFFF", exit_lanes=True)
check("MCOLLECTIVE inside (tid>=16 active, mask=0xFFFFFFFF) = 0xFFFF0000",
      0xFFFF0000 in v and 0xFFFFFFFF not in v, True)
# survivors tid>=16, declared exact mask
v = mcollective_inside("FFFF0000", exit_lanes=True)
check("MCOLLECTIVE inside (mask=0xFFFF0000 exact) = 0xFFFF0000",
      0xFFFF0000 in v, True)

# ---- MCOLLECTIVE after ENDCOLLECTIVE = 0 ----------------------------------
def mcollective_after():
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 R6, #param(buf);[1:7:{}:1:0]",
             "    MOV32I R5, 0xFFFFFFFF;[7:7:{}:5:1]",
             "    BSSY B1, #label(loop);[7:7:{}:5:1]",
             "    WARPSYNC.COLLECTIVE R5, #label(sync);[7:7:{}:5:1]",
             "    ENDCOLLECTIVE;[7:7:{}:5:1]",
             "    #def_label(sync)",
             "    BSYNC B1;[7:7:{}:5:1]",
             "    #def_label(loop)",
             "    BMOV R4, MCOLLECTIVE;[0:7:{}:5:1]",
             "    NOP;[7:7:{}:5:1]", "    NOP;[7:7:{}:5:1]",
             "    STG.E desc[UR4][R6.64+0x0], R4;[0:1:{0,1}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    v = struct.unpack("<32I", mod.device_read(d, 128))
    mod.devmem_free(d)
    return sorted({x for x in v})

v = mcollective_after()
check("MCOLLECTIVE after ENDCOLLECTIVE = 0", v == [0], True)

# ---- illegal: mask not covering an executing lane -> 715 ------------------
CHILD = r'''
import sys, struct
sys.path.insert(0, "__BASE__")
from assembler import assemble, CudaModule
lines = ["#fn k(buf<1024>) {",
         "    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]",
         "    LDC.64 R6, #param(buf);[1:7:{}:1:0]",
         "    MOV32I R5, 0x0000FFFF;[7:7:{}:5:1]",
         "    BSSY B1, #label(loop);[7:7:{}:5:1]",
         "    WARPSYNC.COLLECTIVE R5, #label(sync);[7:7:{}:5:1]",
         "    ENDCOLLECTIVE;[7:7:{}:5:1]",
         "    #def_label(sync)",
         "    BSYNC B1;[7:7:{}:5:1]",
         "    #def_label(loop)",
         "    EXIT;[7:7:{}:5:0]",
         "}"]
cubin = assemble("\n".join(lines))
mod = CudaModule(cubin)
d = mod.devmem_alloc(1024)
mod.device_write(d, struct.pack("<256I", *[0]*256))
try:
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    print("NO-FAULT")
except RuntimeError as e:
    print("FAULT", str(e)[:30])
'''
BASE = str(Path(__file__).resolve().parents[2])
try:
    r = subprocess.run([sys.executable, "-c", CHILD.replace("__BASE__", BASE)],
                       capture_output=True, text=True, timeout=15)
    out = r.stdout.strip()
    good = out.startswith("FAULT")
    check("mask not covering executing lane -> ILLEGAL_INSTRUCTION",
          "FAULT" if good else "NO-FAULT", "FAULT")
except subprocess.TimeoutExpired:
    check("mask not covering executing lane -> ILLEGAL_INSTRUCTION", "timeout", "FAULT")

print(f"\n=== WARPSYNC.COLLECTIVE / ENDCOLLECTIVE: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
