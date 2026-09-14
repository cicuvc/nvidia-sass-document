#!/usr/bin/env python3
"""Probe: per-SM warp-slot accounting across subcores (RTX 5090 / sm_120).

Hypothesis under test
---------------------
The user's model: a CTA's warps are handed out round-robin to the 4 subcores
(warp i -> subcore i%4).  A 5-warp CTA therefore puts **2** warps on subcore 0
and 1 warp on each of the others.  If MAXREG_COUNT=255 makes 2 warps exactly
exhaust a subcore's register file, then a later-launched **1-warp** kernel
cannot become resident until the 5-warp CTA retires.

Result (this probe): FALSIFIED.  At rc=255 a 5-warp CTA leaves 3 free
warp-slots per SM (one on each of subcores 1-3); a 1-warp kernel co-resides
3 CTAs/SM while the 5-warp CTA is still parked.  Only when the occupying CTA
is 8 warps (2 per subcore, all slots full) is the 1-warp kernel blocked.

The probe also gives the full slot accounting: at rc=255 the SM has exactly
8 warp-slots (2 per subcore x 4); parking an A CTA of W warps leaves 8-W
1-warp B CTAs per SM, for W = 1..8.  A 9-warp CTA at rc=255 cannot launch at
all (CUDA_ERROR_LAUNCH_OUT_OF_RESOURCES 701).

Method
------
* A kernel ("spinA") parks one CTA per SM: it writes arrivedA[ctaid]=1 then
  spins on a global GO flag.  blockDim = a_warps*32, MAXREG_COUNT = a_rc.
* A second kernel ("spinB") is 1 warp/CTA by default: writes arrivedB[ctaid]=1
  then also spins on GO.
* Both are launched on separate non-blocking streams.  After all A CTAs have
  arrived, B is launched with a grid far larger than any possible capacity.
  After a settle delay the host reads (async DtoH -- a synchronous
  cuMemcpyDtoH deadlocks behind a parked kernel) how many B CTAs started while
  A was still parked (`arrivedB` nonzero and `doneA` still zero).  Then GO is
  set and everything drains.
* Warm-up note: every module must be launched once and synced BEFORE a
  spinning target exists -- cuModuleLoadData / first cuLaunchKernel of a module
  blocks while another kernel spins (lazy-load path, see AGENTS.md M3).

Run:  python3 tests/asm_construct/probe_subcore_slots.py
"""

import ctypes
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble                      # noqa: E402
from assembler.runner import CudaModule, _cuda, _check   # noqa: E402

# ---------------------------------------------------------------------------
# Control-buffer layout (0x4000 bytes of device memory)
ARR_A, DONE_A, ARR_B, DONE_B, GO = 0x0000, 0x0400, 0x0800, 0x2400, 0x3000
BUF_SIZE = 0x4000

# Spin-park kernel: arrived[ctaid]=1 ; loop { nansleep; if GO {done=1; exit} }.
# The `arrived`/`done` offsets differ between spinA and spinB so both can park
# at once and be counted independently.
SRC = """#fn {name}(buf<8>) {{
 #pragma MAXREG_COUNT({rc})
 LDC.64 {{R2,R3}}, #param(buf);[1:7:{{}}:8:0]
 S2R R4, SR_CTAID.X;[2:7:{{}}:5:1]
 IMAD.WIDE.U32 {{R6,R7}}, R4, 0x4, {{R2,R3}};[7:7:{{1,2}}:5:1]
 MOV32I R8, 1;[7:7:{{}}:5:1]
 STG.E.STRONG.GPU [{{R6,R7}}+0x{arr_off:x}], R8;[7:1:{{}}:8:0]
#def_label(spin)
 NANOSLEEP 0x100;[7:7:{{}}:5:1]
 LDG.E.STRONG.GPU R9, [{{R2,R3}}+0x{GO:x}];[3:1:{{}}:8:0]
 ISETP.NE.AND P0, PT, R9, RZ, PT;[7:7:{{3}}:13:1]
 @!P0 BRA #label(spin);[7:7:{{}}:6:0]
 STG.E.STRONG.GPU [{{R6,R7}}+0x{done_off:x}], R8;[7:1:{{}}:8:0]
 EXIT;[7:7:{{}}:5:0]
}}"""


def build(rc: int, arr_off: int, done_off: int, name: str) -> bytes:
    return assemble(SRC.format(rc=rc, arr_off=arr_off, done_off=done_off,
                               name=name, GO=GO), name)


def main() -> None:
    cu = _cuda()
    # async host<->device copies so polling never queues behind a parked kernel
    for fn, args in [
        ("cuMemcpyDtoHAsync", [ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_size_t, ctypes.c_void_p]),
        ("cuMemcpyHtoDAsync", [ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_size_t, ctypes.c_void_p]),
        ("cuStreamSynchronize", [ctypes.c_void_p]),
    ]:
        f = getattr(cu, fn)
        f.argtypes = args
        f.restype = ctypes.c_int

    _m0 = CudaModule(build(32, ARR_A, DONE_A, "spinA"))   # bring up context
    dev = ctypes.c_int()
    cu.cuDeviceGet(ctypes.byref(dev), 0)
    nsm = ctypes.c_int()
    cu.cuDeviceGetAttribute(ctypes.byref(nsm), 16, dev)   # MULTIPROCESSOR_COUNT
    NSM = nsm.value
    B_GRID = NSM * 10
    io = CudaModule.stream_create()
    print(f"SM count = {NSM}\n")

    def rd(ptr: int, size: int) -> bytearray:
        buf = (ctypes.c_char * size)()
        _check(cu.cuMemcpyDtoHAsync(buf, ctypes.c_void_p(ptr), size,
                                    ctypes.c_void_p(io)))
        _check(cu.cuStreamSynchronize(ctypes.c_void_p(io)))
        return bytearray(buf)

    def wr(ptr: int, data: bytes) -> None:
        _check(cu.cuMemcpyHtoDAsync(ctypes.c_void_p(ptr), ctypes.c_char_p(data),
                                    len(data), ctypes.c_void_p(io)))
        _check(cu.cuStreamSynchronize(ctypes.c_void_p(io)))

    def count_nonzero(buf: int, off: int, n: int) -> int:
        d = rd(buf + off, n * 4)
        return sum(1 for i in range(n) if struct.unpack_from("<I", d, i * 4)[0])

    def co_resident(a_warps: int, a_rc: int, b_warps: int) -> tuple:
        """Return (B_CTAs_per_SM, A_alive_at_B_launch, B_parked)."""
        b_grid = NSM * 10
        modA = CudaModule(build(a_rc, ARR_A, DONE_A, "spinA"))
        modB = CudaModule(build(a_rc, ARR_B, DONE_B, "spinB"))
        buf = modA.devmem_alloc(BUF_SIZE)
        sA = CudaModule.stream_create()
        sB = CudaModule.stream_create()
        try:
            # --- warm up BOTH modules while nothing is spinning ---
            modA.devmem_set(buf, 0, BUF_SIZE // 4)
            wr(buf + GO, struct.pack("<I", 1))
            modA.launch("spinA", grid=(1,), block=(a_warps * 32,),
                        args=[buf], stream=sA)
            modB.launch("spinB", grid=(1,), block=(b_warps * 32,),
                        args=[buf], stream=sB)
            CudaModule.stream_sync(sA)
            CudaModule.stream_sync(sB)
            modA.devmem_set(buf, 0, BUF_SIZE // 4)           # GO=0 again

            # --- park one A CTA on every SM ---
            try:
                modA.launch("spinA", grid=(NSM,), block=(a_warps * 32,),
                            args=[buf], stream=sA)
            except Exception as exc:                          # noqa: BLE001
                return (None, exc, None)
            t0 = time.time()
            arrived = 0
            while time.time() - t0 < 5:
                arrived = count_nonzero(buf, ARR_A, NSM)
                if arrived >= NSM:
                    break
                time.sleep(0.005)

            # --- launch B and see how much can co-reside ---
            modB.launch("spinB", grid=(b_grid,), block=(b_warps * 32,),
                        args=[buf], stream=sB)
            time.sleep(0.8)
            a_done = count_nonzero(buf, DONE_A, NSM)          # 0 => A parked
            b_start = count_nonzero(buf, ARR_B, b_grid)
            b_done = count_nonzero(buf, DONE_B, b_grid)       # 0 => B parked
            wr(buf + GO, struct.pack("<I", 1))
            CudaModule.stream_sync(sA)
            CudaModule.stream_sync(sB)
            return (arrived, a_done == 0 and b_done == 0,
                    b_start / NSM if NSM else 0)
        finally:
            wr(buf + GO, struct.pack("<I", 1))
            CudaModule.stream_sync(sA)
            CudaModule.stream_sync(sB)
            modA.devmem_free(buf)
            CudaModule.stream_destroy(sA)
            CudaModule.stream_destroy(sB)

    print("A = 1 parked CTA/SM @ rc=255, B = parked 1-warp CTAs @ rc=255")
    print(f"{'A warps':>8} | {'free slots (B CTAs/SM)':>24} | A parked & B parked")
    for w in range(1, 9):
        arrived, ok, per_sm = co_resident(w, 255, 1)
        print(f"{w:>8} | {per_sm:>24.2f} | {ok}")
    try:
        co_resident(9, 255, 1)
        print(f"{9:>8} | {'(unexpectedly launched)':>24} |")
    except Exception as exc:  # noqa: BLE001
        print(f"{9:>8} | {'A launch rejected':>24} | "
              f"{type(exc).__name__}: {exc}")

    print("\nMixed-CTA check (A = 5 warps, still parked):")
    for w in (1, 2, 3):
        _, ok, per_sm = co_resident(5, 255, w)
        print(f"  B = {w}-warp CTAs -> {per_sm:.2f} CTAs/SM "
              f"({per_sm * w:.2f} warps/SM), co-resident={ok}")


if __name__ == "__main__":
    main()
