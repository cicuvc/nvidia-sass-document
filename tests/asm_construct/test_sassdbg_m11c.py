"""M11c E2E — execute canonical SASS from per-warp private heap copies.

T0 source bootstrap, one warp: private-base report and exact output.
T1 source bootstrap, four warps: distinct selected code bases and exact output
   through divergence + a tight loop.
T2 source multi-CTA (2 CTAs x 2 warps): global-warp mapping and output.
T3 source relaunch with a different block/grid shape reconstructs canonical
   images and uses the new active-warp count.
T4 real m2_smoke.cubin: static entry trampoline -> shared dispatcher -> two
   private copies, then relaunch; outputs remain identical to the baseline.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.private import PrivateKernel  # noqa: E402


SRC = """#fn k(out<8>, ctathreads<4>) {
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    LDC R12, #param(ctathreads);[3:7:{}:8:0]
    S2R R2, SR_CTAID.X;[5:7:{}:5:1]
    S2R R3, SR_TID.X;[4:7:{}:5:1]
    IMAD R2, R2, R12, R3;[7:7:{3,4,5}:5:1]
    LOP3.LUT R3, R3, 0x1, RZ, 0xC0;[7:7:{}:5:1]
    ISETP.NE.AND P0, PT, R3, RZ, PT;[7:7:{}:13:1]
    BSSY B0, #label(join);[7:7:{}:5:1]
    @P0 BRA #label(odd);[7:7:{}:6:0]
    MOV32I R10, 0x100;[7:7:{}:5:1]
    BRA #label(sync);[7:7:{}:6:0]
#def_label(odd)
    MOV32I R10, 0x200;[7:7:{}:5:1]
#def_label(sync)
    MOV32I R11, 0x0;[7:7:{}:5:1]
#def_label(loop)
    IADD3 R10, R10, 0x1, RZ;[7:7:{}:5:1]
    IADD3 R11, R11, 0x1, RZ;[7:7:{}:5:1]
    ISETP.LT.AND P1, PT, R11, 0x5, PT;[7:7:{}:13:1]
    @P1 BRA #label(loop);[7:7:{}:6:0]
    BSYNC B0;[7:7:{}:4:0]
#def_label(join)
    IADD3 R10, R10, R2, RZ;[7:7:{}:5:1]
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{1}:5:1]
    STG.E.STRONG.GPU [{R6,R7}], R10;[7:1:{}:8:0]
    EXIT;[7:7:{1}:5:0]
}
"""

FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'FAIL'} {name}" +
          ("" if ok else f": {got!r} want {want!r}"))
    if not ok:
        FAILS.append(name)


def expected(n):
    return tuple((0x200 if i & 1 else 0x100) + 5 + i
                 for i in range(n))


def run_source(k, out, *, grid, block, n, tag):
    k.mod.device_write(out, bytes(n * 4))
    k.launch([out, block[0]], grid=grid, block=block)
    selected = k.wait_ready()
    active = grid[0] * ((block[0] + 31) // 32)
    check(f"{tag}: selected private bases are distinct",
          (len(selected), len(set(selected))), (active, active))
    check(f"{tag}: reports equal CodeInstance bases",
          selected, [k.code_base(w) for w in range(active)])
    check(f"{tag}: 0x100-aligned private strides",
          all(selected[i + 1] - selected[i] == k.lay.code_stride
              for i in range(active - 1)), True)
    k.release()
    k.wait_done()
    got = struct.unpack(f"<{n}I", k.mod.device_read(out, n * 4))
    check(f"{tag}: divergent tight-loop output", got, expected(n))


try:
    src = PrivateKernel.from_source(SRC, max_warps=4)
except RuntimeError as e:
    if "CUDA_ERROR_NO_DEVICE" in str(e):
        print("SKIP M11c GPU E2E: no CUDA device visible")
        sys.exit(0)
    raise

out = src.mod.devmem_alloc(128 * 4)

# T0: the minimum one-warp bootstrap.
run_source(src, out, grid=(1,), block=(32,), n=32, tag="T0 1x1")

# T1: one CTA, four warp-private images.
run_source(src, out, grid=(1,), block=(128,), n=128, tag="T1 1x4")

# T2: same four global warp ids distributed across two CTAs.
run_source(src, out, grid=(2,), block=(64,), n=128, tag="T2 2x2")

# T3: relaunch with fewer active warps and a different shape.
run_source(src, out, grid=(2,), block=(32,), n=64, tag="T3 relaunch 2x1")

# T4: real cubin, two private copies, then relaunch.
CUBIN = Path(__file__).resolve().parents[1] / "m2_smoke.cubin"
real = PrivateKernel.from_cubin(CUBIN, max_warps=2)
n = 64
a = real.mod.devmem_alloc(n * 4)
b = real.mod.devmem_alloc(n * 4)
real.mod.device_write(
    a, b"".join(struct.pack("<f", float(i + 1)) for i in range(n)))

for rep in range(2):
    real.mod.device_write(b, bytes(n * 4))
    real.launch([a, b, n], block=(n,))
    selected = real.wait_ready()
    check(f"T4.{rep}: real cubin selected two distinct private bases",
          len(set(selected)), 2)
    check(f"T4.{rep}: module entry differs from heap code",
          all(real.module_base != va for va in selected), True)
    real.release()
    real.wait_done()
    got = struct.unpack(f"<{n}f", real.mod.device_read(b, n * 4))
    want = tuple((i + 1) * 2.0 + 1.0 for i in range(n))
    check(f"T4.{rep}: real cubin output", got, want)

if FAILS:
    print(f"=== M11c FAILURES: {FAILS} ===")
    sys.exit(1)
print("=== sassdbg M11c warp-private bootstrap: ALL PASS ===")
