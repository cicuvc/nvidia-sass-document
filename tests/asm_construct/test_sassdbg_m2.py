import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from sassdbg.lift import lift, roundtrip, normalize_source
from sassdbg.instrument import instrument
from sassdbg.tracer import decode_thread

# ---------------------------------------------------------------------------
# sassdbg M2 — cubin round-trip + lift->instrument->run pipeline.
#
# tests/m2_smoke.cubin is an unmodified nvcc build of tests/m2_smoke.cu
# (float b[i] = 2*a[i]+1).  The test checks:
#   1. lift + re-encode is byte-exact vs the original cubin text section
#   2. the lifted kernel's #fn carries the real param signature (from the
#      .nv.info KPARAM records), incl. the 4-byte scalar between two pointers
#   3. instrument(lift(kernel)) assembles, launches and computes correctly
#   4. the trace records the FFMA result and the STG (with MEMOLD undo)
# ---------------------------------------------------------------------------

ok = True
def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")

CUBIN = str(Path(__file__).resolve().parents[1] / "m2_smoke.cubin")

# --- 1. byte-exact round-trip ---------------------------------------------
check("cubin round-trip byte-exact", roundtrip(CUBIN))

fns = lift(CUBIN)
src = fns["k"]

# --- 2. param signature ----------------------------------------------------
check("param signature lifted", src.splitlines()[0] == "#fn k(p0<8>, p1<8>, p2<4>) {",
      src.splitlines()[0])

# --- 3. instrument + run ---------------------------------------------------
ik = instrument(normalize_source(src))
mod = CudaModule(assemble(ik.source, check_deps=False))
n = 8
a = mod.devmem_alloc(n * 4)
b = mod.devmem_alloc(n * 4)
trace = mod.devmem_alloc(n * ik.per_thread_bytes)
mod.device_write(a, struct.pack(f"<{n}f", *range(n)))
mod.launch(ik.kernel_name, grid=(1,), block=(n,), args=[a, b, n, trace])
mod.synchronize()
got = struct.unpack(f"<{n}f", mod.device_read(b, n * 4))
want = tuple(2.0 * i + 1.0 for i in range(n))
check("instrumented lifted kernel computes b=2a+1", got == want, str(got))

# --- 4. trace content (thread 3) -------------------------------------------
sidecar = json.loads(ik.sidecar())
raw = mod.device_read(trace + 3 * ik.per_thread_bytes, ik.per_thread_bytes)
steps = decode_thread(raw, sidecar)
texts = [s["text"] for s in steps]
ffma = next((s for s in steps if s["text"].startswith("FFMA")), None)
stg = next((s for s in steps if s["text"].startswith("STG")), None)
check("trace covers all executed steps (no early EXIT for tid 3)",
      any(t.startswith("STG") for t in texts) and
      not any(t.startswith("@P0 EXIT") and not s["changes"] == []  # noqa
              for t, s in zip(texts, steps)))
ffma_val = None
if ffma:
    for ch in ffma["changes"]:
        if ch[0] == "REG" and ch[1] == 7:
            ffma_val = struct.unpack("<f", struct.pack("<I", ch[2][0]))[0]
check("FFMA step records R7 = 2*3+1 = 7.0", ffma_val == 7.0, str(ffma_val))
mem = None
memold = None
if stg:
    for ch in stg["changes"]:
        if ch[0] == "MEM":
            mem = ch
        elif ch[0] == "MEMOLD":
            memold = ch
check("STG step records MEM write of 7.0",
      mem is not None and mem[2] == struct.unpack("<I", struct.pack("<f", 7.0))[0],
      str(mem))
check("STG step records MEMOLD undo (old value 0)",
      memold is not None and memold[2] == 0, str(memold))

print("\n=== sassdbg M2 pipeline:", "ALL PASS ===" if ok else "FAILURES ===")
sys.exit(0 if ok else 1)
