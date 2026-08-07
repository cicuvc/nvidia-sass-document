import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# PMTRIG — performance-monitor trigger (fe_pipe).  Verified on SM120.
#
#   PMTRIG [!]Pp, <16-bit mask>
#
# lo64 encoding: opcode 0x801, imm mask at [47:32]; PTX pmevent N (no .mask)
# lowers to 1 << N, pmevent.mask M passes M through.  Pp gates the trigger
# (default PT = always); ptxas never emits a non-PT Pp for `@p pmevent`
# (it branches instead).  The hi64 control word is written by the assembler's
# scheduler and intentionally differs from ptxas's; lo64 must match.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<44} {got!r}")

# --- 1. encoding self-check vs real nvcc pmevent dumps (sm_90 == sm_120) ---
# lo64 only: the assembler scheduler writes its own hi64 control word.
REFS = {
    "PMTRIG 0x1":          0x0000000100007801,   # pmevent 0
    "PMTRIG 0x2":          0x0000000200007801,   # pmevent 1
    "PMTRIG 0x4":          0x0000000400007801,   # pmevent 2
    "PMTRIG 0x8":          0x0000000800007801,   # pmevent 3
    "PMTRIG 0x10":         0x0000001000007801,   # pmevent 4
    "PMTRIG 0x8000":       0x0000800000007801,   # pmevent 15
    "PMTRIG 0x5":          0x0000000500007801,   # pmevent.mask 0x5
    "PMTRIG 0xffff":       0x0000ffff00007801,   # pmevent.mask 0xffff
    "PMTRIG P1, 0x8":      0x0000000800007801,   # Pp slot (gated trigger)
    "PMTRIG !P1, 0x8":     0x0000000800007801,   # !Pp
    "@!P0 PMTRIG 0x10":    0x0000001000008801,   # guard predicate
}
for src, want in REFS.items():
    lo, hi = assemble_flat(src + ";[7:7:0:5:1]")[0]
    check(f"assemble {src}", lo, want)

# --- 2. GPU run: PMTRIGs execute without fault; marker store survives -------
src = """#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:0:1:0]
    LDC.64 {R6,R7}, #param(out);[1:7:0:1:0]
    MOV32I R0, 0x55aa;[7:7:0:5:1]
    PMTRIG 0x1;[7:7:0:5:1]
    PMTRIG 0x10;[7:7:0:5:1]
    PMTRIG 0xffff;[7:7:0:5:1]
    PMTRIG P1, 0x8;[7:7:0:5:1]
    PMTRIG !P1, 0x8;[7:7:0:5:1]
    @!P0 PMTRIG 0x4;[7:7:0:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R0;[0:1:{1}:1:0]
    EXIT;[7:7:0:5:0]
}"""
mod = CudaModule(assemble(src))
d = mod.devmem_alloc(4)
try:
    mod.launch("k", grid=(4,), block=(32,), args=[d])
    mod.synchronize()
    val = int.from_bytes(mod.device_read(d, 4), "little")
    check("kernel with 6x PMTRIG ran, marker stored", val, 0x55aa)
finally:
    try: mod.devmem_free(d)
    except: pass

print(f"\n=== PMTRIG (performance-monitor trigger): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
