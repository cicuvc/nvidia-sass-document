import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# CBU_STATE slots via BMOV — per-warp convergence/barrier-unit state capture
# (verified SM120, single warp)
#
# `BMOV Rd, cbu_state` reads one CBU_STATE slot into a GPR.  Empirically:
#   * MACTIVE  = current execution mask (which lanes are active NOW).
#       baseline 32-lane: 0xFFFFFFFF
#       after @P0 EXIT (tid<16): 0xFFFF0000 (survivors)
#       inside divergence (tid>=16 skipped body): 0xFFFF (body lanes)
#   * MEXITED  = mask of lanes that executed EXIT (0xFFFF after tid<16 exit).
#   * MATEXIT  = 0xFFFFFFFF in all states probed (no at-exit handler armed).
#   * THREAD_STATE_ENUM.0 = the "converged / region-participation" mask
#       (0xFFFFFFFF baseline AND during divergence; 0xFFFF0000 after exit).
#   * TRAP_RETURN_PC.LO  = the CURRENT PC (kernel base + offset of the reading
#       instruction) — verified across 4 kernel layouts (base 0x071675B0).
#       It's the trap-handler return PC slot, but reads back as the live PC.
#   * TRAP_RETURN_MASK  = 0xFFFF0000 during divergence (the parked/other-path
#       lanes); 0x0 baseline.
#   * MCOLLECTIVE, MKILL, TRAP_RETURN_PC.HI, OPT_STACK, API_CALL_DEPTH,
#     ATEXIT_PC.LO/HI all read 0x0 in these probes.  ATEXIT_PC is NOT set by
#     BSSY (it's a separate at-exit-handler mechanism).
#
# B0 (B-register) is the participating-lane mask of the BSSY divergence point
# (see test_breg.py).  The reconvergence PC itself is not exposed as a constant
# in the B/CBU slots — only the live PC is (via TRAP_RETURN_PC.LO).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    # warp-state slot materializes on some lanes; others read 0
    wants = want if isinstance(want, (list, tuple, set)) else [want]
    good = all(w in got for w in wants)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

def capture(slot, mode, block=32):
    """Read one CBU slot per kernel (avoids back-to-back BMOV race)."""
    pre = ["    S2R R2, SR_TID.X;[0:7:{}:5:1]",
           "    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{0}:13:1]"]
    tail = []
    if mode == "after-exit":
        pre += ["    @P0 EXIT;[7:7:{}:5:0]"]
    elif mode == "divergence":
        pre += ["    BSSY B0, #label(join);[7:7:{}:5:1]",
                "    @!P0 BRA #label(join);[7:7:{}:5:1]"]
        tail = ["    BSYNC B0;[7:7:{}:5:1]", "    #def_label(join)"]
    lines = ["#fn k(buf<1024>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]"] + pre + [
             f"    BMOV R4, {slot};[0:7:{{}}:5:1]"] + ["    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]"] * 8 + [
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R4;[0:1:{0}:1:0]",
             ] + tail + ["    EXIT;[7:7:{}:5:0]", "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    v = struct.unpack(f"<{block}I", mod.device_read(d, block * 4))
    mod.devmem_free(d)
    return sorted({x for x in v})

# baseline
check("MACTIVE baseline = all-active", capture("MACTIVE", "baseline"), [0xFFFFFFFF])
check("MEXITED baseline = 0", capture("MEXITED", "baseline"), [0])
check("MKILL baseline = 0", capture("MKILL", "baseline"), [0])
check("MCOLLECTIVE baseline = 0", capture("MCOLLECTIVE", "baseline"), [0])
check("TS_ENUM.1..4 baseline = 0", capture("THREAD_STATE_ENUM.1", "baseline"), [0])
check("ATEXIT_PC.LO baseline = 0", capture("ATEXIT_PC.LO", "baseline"), [0])
check("OPT_STACK baseline = 0", capture("OPT_STACK", "baseline"), [0])
check("API_CALL_DEPTH baseline = 0", capture("API_CALL_DEPTH", "baseline"), [0])

# after partial EXIT
check("MEXITED after tid<16 EXIT = 0xFFFF",
      capture("MEXITED", "after-exit"), [0xFFFF])
check("MACTIVE after tid<16 EXIT = 0xFFFF0000",
      capture("MACTIVE", "after-exit"), [0xFFFF0000])

# inside divergence
check("MACTIVE in divergence = 0xFFFF (body lanes)",
      capture("MACTIVE", "divergence"), [0xFFFF])
check("MEXITED in divergence = 0",
      capture("MEXITED", "divergence"), [0])

print(f"\n=== CBU_STATE capture: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
