#!/usr/bin/env python3
"""Probe: cross-CTA warp->subcore placement via the per-SMSP PM counter.

Question
--------
Within a CTA the mapping is `warp i -> subcore i%4` (see
`tests/asm_construct/test_subcore_yield.py` + `notes/sm90/arch/subcore_scheduler.md`).
But the per-CTA base `c` (which subcore warp 0 lands on) is invisible inside a
single CTA.  Is the placement `(i + c_CTA) % 4` with a *per-CTA* `c` that
varies (spreads consecutive CTAs across the 4 subcores), or does every CTA
start at the same subcore (which would make 1-warp CTAs stack)?

Method
------
`SR_PM0` is a 32-bit per-SMSP instruction counter.  It reads 0 normally; when
profiled by `ncu` with `smsp__inst_executed.sum` requested it mirrors the
*reading warp's own SMSP* cumulative instruction count (see
`notes/sm90/instr/pmtrig.md`, and the in-CTA validation below).  So:

  * **Uniform-work test** — give every CTA the same NOP work D and read
    SR_PM0.  If k 1-warp CTAs co-reside on one subcore they contribute k*D and
    every warp on that subcore reads ~k*D; if they spread, each reads ~D.
    Sweep grid = 1/2/4/8 CTAs per SM.
  * **Distinct-work test** — grid = 2 CTAs/SM, wave0 does a small D0 and wave1
    a large D1, no rendezvous.  If the two CTAs share an SMSP, the small-work
    warp's read is contaminated by the large one (~D0+D1); if they are on
    different subcores each reads only its own work (~D0 / ~D1).

Observed on RTX 5090 / sm_120 (this probe, `ncu` + root, one profiling pass):

  uniform work, D = 4064 inst:
    grid=170  (1 CTA/SM) : every read == 4064          -> 1 subcore used
    grid=340  (2 CTA/SM) : every read == 4064          -> spread to 2 subcores
    grid=680  (4 CTA/SM) : every read == 4064          -> spread to 4 subcores
    grid=1360 (8 CTA/SM) : every read in [8100,8157]   -> 2 warps per subcore
  distinct work (D0=412, D1=4067):
    wave0 read == 412 for all 170 SMs, wave1 read == 4067
    -> the small-work warp is NOT contaminated by its SM's large-work warp,
       i.e. the two 1-warp CTAs are on DIFFERENT subcores.

=> the per-CTA base `c` is NOT fixed: consecutive CTAs are spread across the
   four subcores (a rotating / load-balancing placement), giving the alias
   `warp i of CTA -> subcore (i + c_CTA) % 4` with c_CTA chosen per CTA.
   (For capacity, only the total matters: `slots_used = sum(warps)`, 2 slots
   per subcore at MAXREG_COUNT=255.)

Run (SR_PM0 needs the profiler to arm it):
    sudo ncu --metrics smsp__inst_executed.sum python3 \\
        tests/asm_construct/probe_subcore_crosscta.py uniform 170 340 680 1360
    sudo ncu --metrics smsp__inst_executed.sum python3 \\
        tests/asm_construct/probe_subcore_crosscta.py distinct
Without ncu every SR_PM0 read is 0.
"""

import ctypes
import struct
import sys
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble                      # noqa: E402
from assembler.runner import CudaModule             # noqa: E402

NLOOP = 200                 # NOPs per loop iteration


def build(uniform_iters=None, w0=None, w1=None, cut=170, name="pmx"):
    """uniform_iters: all CTAs do this many iterations.
    w0/w1: wave0 (ctaid<cut) / wave1 iteration counts (distinct-work mode)."""
    L = [f"#fn {name}(out<8>) {{", " #pragma MAXREG_COUNT(255)",
         " LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
         " S2R R2, SR_CTAID.X;[2:7:{}:5:1]",
         " S2R R3, SR_VIRTUALSMID;[3:7:{}:5:1]"]
    if uniform_iters is not None:
        L.append(f" MOV32I R5, {uniform_iters};[7:7:{{}}:5:1]")
    else:
        L += [f" MOV32I R5, {w0};[7:7:{{}}:5:1]",
              f" ISETP.LT.AND P1, PT, R2, {cut}, PT;[7:7:{{2}}:13:1]",
              " @P1 BRA #label(got);[7:7:{}:5:1]",
              f" MOV32I R5, {w1};[7:7:{{}}:5:1]"]
    L += ["#def_label(got)", "#def_label(loop)"]
    for _ in range(NLOOP):
        L.append(" NOP;[7:7:{}:5:1]")
    L += [" IADD3 R5, R5, -0x1, RZ;[7:7:{}:5:1]",
          " ISETP.NE.AND P2, PT, R5, RZ, PT;[7:7:{}:13:1]",
          " @P2 BRA #label(loop);[7:7:{}:6:0]",
          " CS2R {R8,R9}, SR_PM0;[7:7:{}:5:0]"]
    for _ in range(24):                     # let the coupled CS2R write back
        L.append(" NOP;[7:7:{}:5:1]")
    L += [" SHL R14, R2, 0x3;[7:7:{}:5:1]",
          " IADD3 R12, R6, R14, RZ;[7:7:{1}:5:1]",
          " IADD3 R13, R7, RZ, RZ;[7:7:{1}:5:1]",
          " STG.E.STRONG.GPU [{R12,R13}], R8;[7:1:{}:8:0]",
          " STG.E.STRONG.GPU [{R12,R13}+0x4], R3;[7:1:{}:8:0]",
          " EXIT;[7:7:{}:5:0]", "}"]
    return assemble("\n".join(L), name, check_deps=False)


def launch(cubin, ncta, fname):
    mod = CudaModule(cubin)
    buf = mod.devmem_alloc(ncta * 8)
    mod.devmem_set(buf, 0, ncta * 2)
    mod.launch(fname, grid=(ncta,), block=(32,), args=[buf])
    mod.synchronize()
    raw = mod.device_read(buf, ncta * 8)
    mod.devmem_free(buf)
    by_sm = {}
    for c in range(ncta):
        pm, smid = struct.unpack_from("<2I", raw, c * 8)
        by_sm.setdefault(smid, []).append((c, pm))
    return by_sm


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "uniform"
    if mode == "uniform":
        grids = [int(x) for x in sys.argv[2:]] or [170, 340, 680, 1360]
        for g in grids:
            by_sm = launch(build(uniform_iters=20), g, "pmx")
            vals = sorted(pm for l in by_sm.values() for _, pm in l)
            print(f"grid={g:5d}  cta/sm={g/len(by_sm):5.2f}  "
                  f"SR_PM0 min={vals[0]} med={statistics.median(vals)} "
                  f"max={vals[-1]}")
    else:
        by_sm = launch(build(w0=2, w1=20), 340, "pmx")
        shared = sep = 0
        ex = []
        for smid, l in sorted(by_sm.items()):
            if len(l) != 2:
                continue
            (c0, p0), (c1, p1) = l
            a0, a1 = (p0, p1) if c0 < 170 else (p1, p0)
            if a0 > 2000:        # small-work warp sees the large-work warp
                shared += 1
            else:
                sep += 1
            if len(ex) < 8:
                ex.append((smid, a0, a1))
        print(f"distinct work (wave0=412 inst, wave1=4067 inst): "
              f"same-SMSP={shared}  separate={sep}")
        print("  samples (smid, wave0_pm, wave1_pm):", ex)


if __name__ == "__main__":
    main()
