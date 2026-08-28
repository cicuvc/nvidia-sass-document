import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.lift import lift, normalize_source
from sassdbg.patch import Debugger

# ---------------------------------------------------------------------------
# sassdbg M3 — runtime breakpoints via device-side code patching.
#
# tests/m2_smoke.cubin is an unmodified nvcc build (float b[i] = 2*a[i]+1).
# The test lifts it, injects the debugger prologue/slots (patch.py), then:
#   1. the kernel parks at the entry gate and reports its code base (LEPC)
#   2. host arms breakpoints at the FFMA and the STG (patched while parked)
#   3. release -> bp1 parks the warp BEFORE the FFMA (b still zero)
#   4. resume -> bp2 parks BEFORE the STG (b still zero)
#   5. resume -> kernel completes with correct results
# ---------------------------------------------------------------------------

ok = True
def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")

CUBIN = str(Path(__file__).resolve().parents[1] / "m2_smoke.cubin")
src = normalize_source(lift(CUBIN)["k"])

# original-source instruction indices (skip label lines)
insts = [ln.strip() for ln in src.splitlines()[1:]
         if ln.strip() and not ln.strip().startswith("#")]
i_ffma = next(i for i, t in enumerate(insts) if t.startswith("FFMA"))
i_stg = next(i for i, t in enumerate(insts) if t.startswith("STG"))

dbg = Debugger(src, max_bps=4)
n = 8
a = dbg.mod.devmem_alloc(n * 4)
b = dbg.mod.devmem_alloc(n * 4)
dbg.mod.device_write(a, struct.pack(f"<{n}f", *range(n)))
dbg.mod.device_write(b, bytes(n * 4))

dbg.launch([a, b, n], block=(n,))           # dbgctrl appended internally
base = dbg.base()
check("target reports code base", base != 0 and base % 16 == 0,
      hex(base))

bp1 = dbg.arm(i_ffma)
bp2 = dbg.arm(i_stg)
check("two breakpoints armed", bp1.id != bp2.id)

dbg.release()

h1 = dbg.wait_hit()
check("first hit is the FFMA bp", h1.id == bp1.id, f"hit id {h1.id}")
got = struct.unpack(f"<{n}f", dbg.mod.device_read(b, n * 4))
check("at bp1 the STG has not run (b all zero)",
      all(v == 0.0 for v in got), str(got[:4]))
dbg.resume(h1)

h2 = dbg.wait_hit()
check("second hit is the STG bp", h2.id == bp2.id, f"hit id {h2.id}")
got = struct.unpack(f"<{n}f", dbg.mod.device_read(b, n * 4))
check("at bp2 the STG has not run (b all zero)",
      all(v == 0.0 for v in got), str(got[:4]))
dbg.resume(h2)

dbg.wait_done()
got = struct.unpack(f"<{n}f", dbg.mod.device_read(b, n * 4))
want = tuple(2.0 * i + 1.0 for i in range(n))
check("after resume the kernel completes b=2a+1", got == want, str(got))

print("\n=== sassdbg M3 breakpoints:", "ALL PASS ===" if ok else "FAILURES ===")
sys.exit(0 if ok else 1)
