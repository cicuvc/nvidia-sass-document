"""M11d E2E — isolated per-warp mutation with tight-freeze + one IVALL.

T0 freezes warp 0 while warp 1 demonstrably keeps making progress, adds a
   second breakpoint only to the frozen private copy, checks persistent re-hit,
   then disarms back to the canonical word.
T1 uses two CTAs (one warp each) with independent breakpoint sets/sites.
T2 keeps a persistent binding across relaunch and verifies it is reconstructed.
T3 attaches the same private-mutation engine to a real cubin and replays FFMA.
All hit PCs must lie in the reporting warp's heap copy, never module text.
"""
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.private import PrivateKernel  # noqa: E402


SRC = """#fn k(progress<8>, stop<8>) {
    LDC.64 {R4,R5}, #param(progress);[1:7:{}:8:0]
    LDC.64 {R6,R7}, #param(stop);[2:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{}:5:1]
    S2R R3, SR_CTAID.X;[4:7:{}:5:1]
    IMAD R2, R3, 0x20, R2;[7:7:{4,5}:5:1]
    MOV32I R10, 0x0;[7:7:{}:5:1]
#def_label(loop)
    IADD3 R10, R10, 0x1, RZ;[7:7:{1}:5:1]
    IMAD.WIDE.U32 {R8,R9}, R2, 0x4, {R4,R5};[7:7:{1}:5:1]
    STG.E.STRONG.GPU [{R8,R9}], R10;[7:1:{}:8:0]
    LDG.E.STRONG.GPU R11, [{R6,R7}];[3:1:{2}:8:0]
    ISETP.EQ.AND P0, PT, R11, RZ, PT;[7:7:{3}:13:1]
    @P0 BRA #label(loop);[7:7:{}:6:0]
    EXIT;[7:7:{1}:5:0]
}
"""

I_ENTRY = 5
I_LOOP = 6
I_STORE = 8
FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'FAIL'} {name}" +
          ("" if ok else f": {got!r} want {want!r}"))
    if not ok:
        FAILS.append(name)


def u32(mod, va):
    return struct.unpack("<I", mod.device_read(va, 4))[0]


def assert_private(k, hit, tag):
    lo = k.code_base(hit.warp)
    check(f"{tag}: hit PC is warp-private",
          (hit.site, lo <= hit.site < lo + k.template.size,
           hit.site != k.module_base),
          (lo + hit.bp.orig_index * 16, True, True))


try:
    k = PrivateKernel.from_source(SRC, max_warps=2, max_bps=4)
except RuntimeError as e:
    if "CUDA_ERROR_NO_DEVICE" in str(e):
        print("SKIP M11d GPU E2E: no CUDA device visible")
        sys.exit(0)
    raise

# T0: mutate only frozen warp 0 while warp 1 remains live.
progress = k.mod.devmem_alloc(64 * 4)
stop = k.mod.devmem_alloc(4)
k.mod.device_write(progress, bytes(64 * 4))
k.mod.device_write(stop, bytes(4))
entry = k.arm(I_ENTRY, warps=[0])
k.launch([progress, stop], block=(64,))
k.wait_ready()
k.release()
h0 = k.wait_hit()
check("T0: entry stop belongs only to warp 0",
      (h0.warp, h0.bp.orig_index, h0.mask),
      (0, I_ENTRY, 0xFFFFFFFF))
assert_private(k, h0, "T0")

# Lane 32 belongs to warp 1.  It must advance while warp 0 owns a tight spin.
p0 = u32(k.mod, progress + 32 * 4)
time.sleep(0.01)
p1 = u32(k.mod, progress + 32 * 4)
check("T0: warp 1 progresses while warp 0 is frozen", p1 > p0, True)

# This is the key isolation operation: write a new executable word only in the
# already-frozen warp-0 copy while warp 1 is issuing the original image.
loop = k.arm(I_LOOP, warps=[0])
check("T0: isolated arm advances only warp-0 code epoch",
      (k.codes.instances[0].code_epoch > 0,
       k.codes.instances[1].code_epoch), (True, 0))
k.disarm(entry, warps=[0])
k.resume_hit(h0)
h1 = k.wait_hit()
check("T0: newly armed private loop site hits", (h1.warp, h1.bp.orig_index),
      (0, I_LOOP))
k.resume_hit(h1)
h2 = k.wait_hit()
check("T0: persistent tight-loop breakpoint re-hits",
      (h2.warp, h2.bp.orig_index), (0, I_LOOP))

# Restore from immutable materialized canonical image, then let both warps exit.
k.disarm(loop, warps=[0])
canonical = k.template.materialize(k.code_base(0))[I_LOOP]
restored = struct.unpack(
    "<QQ", k.owner.device_read(k.code_base(0) + I_LOOP * 16, 16))
check("T0: disarm restores canonical private word", restored, canonical)
k.mod.device_write(stop, struct.pack("<I", 1))
k.resume_hit(h2)
k.wait_done()
check("T0: both warps complete after isolated restore",
      (u32(k.mod, progress) > 0, u32(k.mod, progress + 32 * 4) > 0),
      (True, True))
check("T0: every runtime executable write stayed in heap arena",
      (bool(k.exec_write_log),
       all(k.arena <= va and va + size <= k.arena + k.lay.total
           for va, size in k.exec_write_log)),
      (True, True))

# T1: two CTAs, independent sites/bindings.
k1 = PrivateKernel.from_source(SRC, max_warps=2, max_bps=4)
progress1 = k1.mod.devmem_alloc(64 * 4)
stop1 = k1.mod.devmem_alloc(4)
k1.mod.device_write(progress1, bytes(64 * 4))
k1.mod.device_write(stop1, bytes(4))
b0 = k1.arm(I_ENTRY, warps=[0])
b1 = k1.arm(I_LOOP, warps=[1])
k1.launch([progress1, stop1], grid=(2,), block=(32,))
k1.wait_ready()
k1.release()
hits = [k1.wait_hit(), k1.wait_hit()]
check("T1: two CTAs stop at independent private sites",
      sorted((h.warp, h.bp.orig_index) for h in hits),
      [(0, I_ENTRY), (1, I_LOOP)])
for h in hits:
    assert_private(k1, h, "T1")
k1.mod.device_write(stop1, struct.pack("<I", 1))
for h in hits:
    k1.disarm(h.bp, warps=[h.warp])
    k1.resume_hit(h)
k1.wait_done()
check("T1: per-CTA independent restores complete",
      (u32(k1.mod, progress1), u32(k1.mod, progress1 + 32 * 4)),
      (1, 1))

# T2: a persistent final-store bp is reconstructed on relaunch.
k2 = PrivateKernel.from_source(SRC, max_warps=2, max_bps=2)
progress2 = k2.mod.devmem_alloc(64 * 4)
stop2 = k2.mod.devmem_alloc(4)
store = k2.arm(I_STORE, warps=[0])
for rep, (grid, block) in enumerate([
        ((1,), (64,)), ((1,), (64,)), ((2,), (32,))]):
    k2.mod.device_write(progress2, bytes(64 * 4))
    k2.mod.device_write(stop2, struct.pack("<I", 1))
    k2.launch([progress2, stop2], grid=grid, block=block)
    k2.wait_ready()
    k2.release()
    hit = k2.wait_hit()
    check(f"T2.{rep}: persistent binding survives relaunch",
          (hit.warp, hit.bp is store, hit.bp.orig_index),
          (0, True, I_STORE))
    assert_private(k2, hit, f"T2.{rep}")
    k2.resume_hit(hit)
    k2.wait_done()
    check(f"T2.{rep}: replayed store and peer warp complete",
          (u32(k2.mod, progress2), u32(k2.mod, progress2 + 32 * 4)),
          (1, 1))

# T3: real-cubin ABI + private FFMA replay (ordinary verbatim ReplayPlan).
cubin = Path(__file__).resolve().parents[1] / "m2_smoke.cubin"
kr = PrivateKernel.from_cubin(cubin, max_warps=2, max_bps=2)
n = 64
a = kr.mod.devmem_alloc(n * 4)
b = kr.mod.devmem_alloc(n * 4)
kr.mod.device_write(
    a, b"".join(struct.pack("<f", float(i + 1)) for i in range(n)))
kr.mod.device_write(b, bytes(n * 4))
ffma = kr.arm(12, warps=[0])
kr.launch([a, b, n], block=(64,))
kr.wait_ready()
kr.release()
rh = kr.wait_hit()
check("T3: real cubin hits warp-private FFMA",
      (rh.warp, rh.bp is ffma, rh.bp.orig_index), (0, True, 12))
assert_private(kr, rh, "T3")
kr.resume_hit(rh)
kr.wait_done()
got = struct.unpack(f"<{n}f", kr.mod.device_read(b, n * 4))
want = tuple((i + 1) * 2.0 + 1.0 for i in range(n))
check("T3: real cubin FFMA replay output", got, want)
check("T3: real module text was never a runtime write destination",
      (all(kr.arena <= va and va + size <= kr.arena + kr.lay.total
           for va, size in kr.exec_write_log),
       all(not (va <= kr.module_base < va + size)
           for va, size in kr.exec_write_log)),
      (True, True))

if FAILS:
    print(f"=== M11d FAILURES: {FAILS} ===")
    sys.exit(1)
print("=== sassdbg M11d per-warp mutation: ALL PASS ===")
