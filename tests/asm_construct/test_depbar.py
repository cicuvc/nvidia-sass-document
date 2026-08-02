import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# DEPBAR — counted scoreboard barrier (fe_pipe).  Verified on SM120.
#
#   DEPBAR.LE SBn, cnt {, S}     wait until SBn's outstanding count <= cnt,
#                                AND every SB in S is drained to 0
#   DEPBAR {S}                   drain S to 0
#   DEPBAR.ALL                   drain all
#   DEPBAR.LE SBn, URb {, S}     dynamic count from a uniform register
#
# The distinguishing semantic vs the per-instruction `req` mask:
#   req={k}  forces SBk's counter to 0 before issue (binary).
#   DEPBAR.LE SBn, cnt  proceeds as soon as the counter is <= cnt — a
#   PARTIAL drain.  cnt=0 is the same as a req-wait (force 0); cnt>=1 lets
#   dependent code run while `cnt` ops are still in flight.
#
# Bookkeeping here uses ordinary `wr=SBn` ops (MUFU ~18 cyc + a cold LDG
# ~500-1000 cyc) instead of LDGSTS/LDGDEPBAR.  Verified:
#   counter=3 (2 MUFU + 1 LDG): LE 3/2/1 proceed at ~10 cyc with the LDG
#   still in flight (its register is stale); LE 0 waits the full load and the
#   LDG result is valid.  S-list {1} forces SB1 to drain even when the LE
#   part is already satisfied.  DEPBAR {S} = force-0 on S.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<40} {got!r}")

def run_probe(depbar, extra_wr1_load=False, ur_cnt=None):
    """2 MUFU + 1 cold LDG on SB0 (counter=3); optional SB1 load; DEPBAR.
    Returns (wait_delta_cycles, ldg_value_after)."""
    lines = ["    LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
             "    LDC.64 {R2,R3}, #param(src);[1:7:{}:1:0]",
             "    MOV32I R1, 0x3f800000;[7:7:{}:5:1]",
             "    MUFU.RCP R20, R1;[0:7:{}:5:1]",
             "    MUFU.RCP R21, R1;[0:7:{}:5:1]",
             "    LDG.E R0, desc[{UR4,UR5}][{R2,R3}+0x0];[0:7:{1}:5:1]"]
    if extra_wr1_load:
        lines.append("    LDG.E R22, desc[{UR4,UR5}][{R2,R3}+0x4];[1:7:{1}:5:1]")
    if ur_cnt is not None:
        # LDCU needs a sufficient stall (stall=2, yield=0) + consumer req on
        # its scoreboard even though it is scoreboard-tracked (wr=3).
        lines.append("    LDCU UR3, #param(cnt);[3:7:{}:2:0]")
    lines += ["    CS2R {R10,R11}, SR_CLOCKLO;[1:7:{}:5:1]",
              "    " + depbar,
              "    CS2R {R12,R13}, SR_CLOCKLO;[1:7:{}:5:1]",
              "    IADD3 R14, R0, RZ, RZ;[7:7:{}:5:1]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R10;[0:1:{1}:1:0]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R12;[0:1:{1}:1:0]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R14;[0:1:{1}:1:0]",
              "    EXIT;[7:7:{}:5:0]"]
    params = "out<8>, src<8>" + (", cnt<4>" if ur_cnt is not None else "")
    src = "#fn k(%s) {\n%s\n}" % (params, "\n".join(lines))
    args = {"out": 0}
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(12)
    srcbuf = mod.devmem_alloc(16 * 1024 * 1024)
    mod.device_write(srcbuf, b"\x00" * 16 * 1024 * 1024)
    mod.device_write(srcbuf + 8 * 1024 * 1024, struct.pack("<4I", 0xDEADBEEF, 0, 0, 0))
    launch_args = [d, srcbuf + 8 * 1024 * 1024]
    if ur_cnt is not None:
        launch_args.append(ur_cnt)
    try:
        mod.launch("k", grid=(1,), block=(1,), args=launch_args)
        mod.synchronize()
        v = struct.unpack("<3I", mod.device_read(d, 12))
        return v[1] - v[0], v[2]
    finally:
        try: mod.devmem_free(d)
        except: pass
        try: mod.devmem_free(srcbuf)
        except: pass

# --- 1. LE partial-drain vs force-zero -------------------------------------
res = {}
for nm, dep in [("LE 3 (<=3, no wait)", "DEPBAR.LE SB0, 3;[7:7:{}:5:1]"),
                ("LE 1 (LDG in flight)", "DEPBAR.LE SB0, 1;[7:7:{}:5:1]"),
                ("LE 0 (force-0)", "DEPBAR.LE SB0, 0;[7:7:{}:5:1]"),
                ("req={0} consumer", "IADD3 R14, R0, RZ, RZ;[7:7:{0}:5:1]")]:
    w, ldg = run_probe(dep)
    res[nm] = (w, ldg)

# LE 1 must proceed while the LDG is still in flight (LDG stale)...
check("LE 1 proceeds early (LDG stale, small wait)",
      res["LE 1 (LDG in flight)"][1] != 0xDEADBEEF and res["LE 1 (LDG in flight)"][0] < 50,
      True)
# LE 0 / req force-0: LDG valid after a long wait
for nm in ("LE 0 (force-0)", "req={0} consumer"):
    w, ldg = res[nm]
    check(f"{nm}: LDG valid + long wait", (ldg == 0xDEADBEEF and w > 100), True)
    print(f"        ({nm}: wait={w} cyc, LDG=0x{ldg:08x})")

# --- 2. S-list drains other scoreboards to 0 -------------------------------
w, ldg = run_probe("DEPBAR.LE SB0, 63, {1};[7:7:{}:5:1]", extra_wr1_load=True)
check("LE SB0,63 {1} waits for SB1 load (S-list force-0)", w > 100, True)
w, ldg = run_probe("DEPBAR {1};[7:7:{}:5:1]", extra_wr1_load=True)
check("DEPBAR {1} drains SB1 (force-0)", w > 100, True)

# --- 3. uniform-register dynamic count -------------------------------------
w, ldg = run_probe("DEPBAR.LE SB0, UR3;[7:7:{3}:5:1]", ur_cnt=0)
check("DEPBAR.LE SB0, UR3 (cnt=0) drains LDG", ldg == 0xDEADBEEF, True)
w, ldg = run_probe("DEPBAR.LE SB0, UR3;[7:7:{3}:5:1]", ur_cnt=1)
check("DEPBAR.LE SB0, UR3 (cnt=1) proceeds early", ldg != 0xDEADBEEF, True)

# --- 4. offline encoding self-check vs ptxas -------------------------------
enc = assemble_flat(
    "DEPBAR.LE SB0, 0x1;[7:7:{}:5:1]\n"
    "DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]\n"
    "DEPBAR.LE SB2, 0, {0,3,5};[7:7:{}:5:1]\n"
    "DEPBAR {1};[7:7:{}:5:1]\n"
    "DEPBAR.ALL;[7:7:{}:5:1]\n")
refs = [0x000080400000791a, 0x000080000000791a]
assert enc[0][0] == refs[0] and enc[1][0] == refs[1], \
    f"LE encodings {[hex(e[0]) for e in enc[:2]]} != ptxas refs"
def dep_fields(lo):
    return (lo >> 47) & 1, (lo >> 44) & 7, (lo >> 38) & 0x3f, (lo >> 32) & 0x3f
assert dep_fields(enc[2][0]) == (1, 2, 0, 0x29), dep_fields(enc[2][0])
assert dep_fields(enc[3][0]) == (0, 0, 0, 0x2), dep_fields(enc[3][0])
assert enc[4][0] == 0x0000003f0000791a, hex(enc[4][0])
# illegal: sbidx inside S must be rejected at assemble time
try:
    assemble_flat("DEPBAR.LE SB0, 1, {0};[7:7:{}:5:1]")
    check("sbidx-in-S rejected", False, True)
except Exception:
    check("sbidx-in-S rejected", True, True)
print("encoding self-check: DEPBAR LE/noLE/ALL/UR + sbidx-in-S guard OK")

print(f"\n=== DEPBAR (counted scoreboard barrier): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
