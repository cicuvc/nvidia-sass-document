# H100 (GH100) fixed-latency scalar pipeline: rates, forwarding, result visibility

Silicon: NVIDIA H100 80GB HBM3 (sm_90), driver 580.95.05, via Modal
(`tools/modal_h100_probe.py`).  No NCU — all numbers are `CS2R SR_CLOCKLO`
window timing or poison/fresh result-visibility boundaries from the sm_120
latency probe suite (`tests/asm_construct/probe_{alulite,aluheavy,fmalite,
fmaheavy,fmaheavy_wide,fp16,fp64}_latency.py`) run with
`ASSEMBLER_ARCH=sm90` + `archutil.adapt_source`.

This note supersedes the family-level H20 numbers where they conflict (see
"Corrections" below).

## Solo pipe rates (clean brackets)

`tests/asm_construct/probe_sm90_rates.py`, 1024-inst streams, one warp,
min-over-reps CS2R window.  `reuse` = `[7:7:{}:1:0:7]`, `yield` =
`[7:7:{}:1:1]`.

| stream | reuse | yield | implied lanes/SMSP |
|---|---:|---:|---|
| NOP | 1.01 | 2.01 | (fe_pipe, no datapath) |
| MOV/IADD/IADD3/LOP3/SHF/PRMT/IMNMX/SEL/FMNMX/FSEL/ISETP (int_pipe) | 2.01 | 2.01 | 16 INT |
| IMAD / IMUL / IDP.4A | 2.01 | 2.01 | 16 (mul array) |
| IMAD.WIDE / IMAD.HI | 4.01 | 4.01 | 64-bit product path = 2 passes |
| **FFMA / FADD / FMUL** (fmalighter) | **1.01** | 2.01 | **32 FP32** |
| HFMA2 / HADD2 (fp16_pipe) | 2.01 | 2.01 | 16 packed |
| DADD | 2.01 | 2.01 | 16 FP64 **per SMSP, private** (= 64/SM, the 1:2 ratio) |
| DFMA | 2.01 | **3.01** | 16 FP64, yield NOT hidden (see below) |
| MUFU.RCP | 8.00 | 8.00 | 4 XU |

Reuse matters for 3-source FP32: FFMA with `[1:0]` (no reuse bits) runs 2.01,
not 1.01 — GH100's RF does not collect 3 warp operands/clk without the reuse
cache (same constraint as GB202, unlike GA100).  INT-pipe 3-source ops are
immune (their 2.0 datapath floor already covers the collection).

### yield = 1-cycle warp-switch cost, confirmed on GH100

NOP 1.01 → 2.01 and FFMA 1.01 → 2.01 under yield=1: the same switch-cost
model as GB202/sm_89/GA100 (see `notes/sm120/yield_dispatch_cost.md`).
Two Hopper-specific details:

- int_pipe streams at the 2.0 datapath floor show NO yield adder (2.01 →
  2.01): the dead switch cycle hides under the second occupancy cycle.
- **DFMA is the exception**: 2.01 → 3.01.  Its fma64lite admission does not
  overlap the switch dead cycle with datapath occupancy the way int_pipe
  does.  DADD (same pipe) DOES hide it — so this is specific to DFMA's
  admission, not the FP64 datapath.

## Admission depth: corrected counted-barrier measurement

The earlier `CS2R; burst; CS2R` same-warp measurement is invalid for INT
depth because `CS2R` itself occupies `int_pipe`; it observes service drain,
not merely warp progress past admission.  The corrected construction uses two
same-subcore producers and a different-subcore observer.  Producers mark
post-burst progress with counted `BAR.SYNC` on `mio_pipe`; only the observer
timestamps barrier release.

The final dense-prefix rerun gives:

| family | credits/subcore | post-knee service |
|---|---:|---:|
| ALU: IADD3/LOP3/SHF | **about 12** | 0.5 instruction/cycle |
| FMA: IMAD.LO + ordinary HFMA2 | **about 12 shared** | 0.5 combined |
| FP64: DADD + HFMA2.MMA | **about 12 shared** | 0.5 combined |
| FP32 FFMA/FADD/FMUL | **not fillable by this frontend** | 1 instruction/cycle |

For the three slow domains, N=12 per producer is the last filling-region
point and N=13 begins the exact +4-clock/N slope for two new instructions.
FP32 instead reaches the +2-clock/N one-instruction/cycle service slope when
the producer path overtakes the fixed observer path; there is no FP32 knee.
The earlier five-credit result came from four stall-8 NOPs before the burst:
new instructions initially occupied those holes.  It is withdrawn, as is the
claim that the H100 SMSP can issue two warp instructions per cycle. Full
curves and ordered saturated-prefix sharing tests are in
[`h100_fixed_admission_depth.md`](h100_fixed_admission_depth.md).

Saturated ordered phases establish separate ALU, FMA, and FP64 reservation
domains. IMAD and ordinary HFMA2 share the FMA window; DADD and HFMA2.MMA
share the FP64 window. Scalar Lite has no independently visible deep queue.

The predicate-off single-warp slopes still show that squashed instructions
reserve pipe service; only the depth inference has changed.

## Corrections to the H20-era numbers

`h20_compute_conflicts.md` measured everything with `SCHED=[7:7:{}:1:1]`
(yield=1 on every instruction):

- "Every ordinary stream runs near two clocks/instruction" — artifact of the
  yield switch cost for the 32-lane FP32 pipe.  H100 FFMA/FADD/FMUL solo =
  **1.0 cyc/inst**.  (The H20 die may genuinely differ — H20 FP64 is
  fuse-nerfed to 1:64 — but the FFMA "2.04 solo" number is the yield
  artifact and should be re-read as 1.0-class.)
- The conflict-matrix *pairing* conclusions (early INT/FP16/IMAD admission,
  RF bank collection law) used relative comparisons and survive, but their
  absolute slopes include per-instruction switch noise.

## Result-visibility (producer→consumer bypass) matrices

Method: settle poison, issue producer, wait a controlled issue gap, consume
the destination; the permanent stale→fresh boundary is the hardware-visible
latency.  `fine` = stall-1 NOP fillers, `coarse` = few big-stall NOPs; where
they disagree the boundary is phase-sensitive (same caveat as sm_120).

### int_pipe producers (MOV/IADD/IADD32I/IADD3/ISCADD/LEA/LOP*/PRMT/SHF/SHL/SHR/SGXT/IABS/BMSK/FMNMX/FSEL/FSET/IMNMX/SEL)

Uniform across every tested producer:

| consumer leaf | detector | fine | coarse |
|---|---|---:|---:|
| int (MOV) | bit-copy | **2** | 2 |
| int (IADD3) | add-zero | **2** | 2 |
| fmalighter (FADD) | fp add-zero | **3** | 4 |

### fmalighter producers (FADD/FFMA/FMUL/FSWZADD/IDP.2A/IDP.4A/IMAD/IMUL, +32I forms)

Uniform:

| consumer leaf | fine | coarse |
|---|---:|---:|
| int (MOV / IADD3) | **3** | 4 |
| fmalighter (FADD) | **2** | 2 |
| fmalighter (IMAD ×1) | **2** | 2 |

So GH100 has a **2-cycle same-domain bypass and a 3-cycle (fine) / 4-cycle
(coarse-safe) cross-domain hop** between the INT domain and the
FP32/integer-multiply domain.  There is no ALU-Lite/ALU-Heavy or
FMA-Lite/FMA-Heavy split in visibility: every int_pipe op forwards to every
int_pipe consumer at 2, and `IMAD ×1` as a consumer behaves identically to
`FADD` (both fmalighter on sm_90 — unlike GB202, where they are different
leaves of Shared FMA Heavy with different boundaries).

### fp16_pipe (HADD2/HMUL2/HFMA2 + 32I forms)

| producer | any consumer (int/fma) fine |
|---|---:|
| HADD2/HMUL2/HFMA2 (+32I) | **3** |
| HFMA2.MMA | **4** |
| HADD2.F32 (FP32 dest) → int | 3 |
| HADD2.F32 → fmalighter | **2** |

Packed-FP results broadcast at 3 cycles to all domains (one cycle slower
than the fmalighter same-domain path); `HFMA2.MMA` pays one extra cycle;
`HADD2.F32`'s FP32-formatted dest lands in the fmalighter domain at 2.

### fma64lite (DADD/DMUL/DFMA/CLMAD)

Uniform 64-bit results, lo and hi halves identical:

| consumer | fine | coarse |
|---|---:|---:|
| all (int/fma) | **4** | 7 |

No lo/hi split on the FP64 pipe (contrast IMAD.WIDE below).

### IMAD.WIDE / IMAD.HI split halves

| result | int consumer | fmalighter consumer |
|---|---:|---:|
| IMAD.WIDE lo | 2 | **1** (gap-1 fresh — zero extra latency) |
| IMAD.WIDE hi | 3 (coarse 4) | 2 |
| IMAD.HI dest | 3 (coarse 4) | 2 |

The wide-multiply **low half is available to the fmalighter pipe one cycle
before the producer's own next instruction could re-issue** — the multiply
array's low-word bypass is the fastest forwarding path measured on GH100.
The high half (and IMAD.HI's result) takes the normal same-domain 2-cycle
path to fmalighter and the 3-cycle cross-domain path to int.

### Predicate results

| producer → consumer | fine | coarse |
|---|---:|---:|
| ISETP/FSETP/IADD.PU → SEL selector | 2 | 2 |
| ISETP/FSETP/IADD.PU → P2R | 2 | 2 |
| IMAD.WIDE/HI Pu → selector / P2R | 3 | 4 |
| any predicate → @P guard | **7** | 12 |
| any predicate → @P BRA | **7** | 12 |

The guard/branch floor of 7 (fine) matches the CBU predicate-forwarding
floor found in the sassdbg work (ISETP→BRA needs stall ≥13 yield=1 when
bracketed the conservative way).  Local predicate forwarding (selector,
P2R) is fast at 2–3.

## sm_90 const-load hazard found during bring-up

`probe_sm90_ldc_req.py`: an `LDC.64` with stall=1 faults a *req-waiting*
consumer (700, address 0) — **the scoreboard claim is not yet visible to an
instruction issuing 1 cycle later**.  LDC stall≥2 + consumer req-wait works;
either alone faults or reads stale.  `archutil.adapt_source` now bumps
`LDC.64/128` stalls to ≥2 on sm90.  (Same class as the H20 "LDC.64 wants
stall ≥ 2" hint, now root-caused to claim visibility.)

## GH100 fixed-pipeline model

```text
warp scheduler (1 inst/clk/SMSP; warp switch costs 1 dead cycle)
    |
    +-- int_pipe        16 lanes   2.0 cyc/inst   (IADD3/LOP3/SHF/MOV/SEL/
    |                                              FMNMX/ISETP/PRMT/...)
    +-- fmalighter      32 lanes   1.0 cyc/inst   FP32 FFMA/FADD/FMUL
    |                    16-lane mul path          IMAD/IMUL/IDP  2.0
    |                                IMAD.WIDE/HI  4.0 (two passes)
    +-- fp16_pipe       16 packed  2.0 cyc/inst
    +-- fma64lite       16 lanes   2.0 cyc/inst   DADD/DFMA/DMUL
    +-- XU (mio)         4 lanes   8.0 cyc/inst   MUFU

bypass:  same-domain 2 cyc,  INT<->fmalighter cross-domain 3 (fine)/4 (safe),
         fp16 -> all 3 (MMA 4),  fp64 -> all 4 (safe 7),
         IMAD.WIDE lo -> fmalighter 1 (fastest path on the chip)
```

### Execution-service domains on GH100 — final corrected map

The clean discriminator is a one-warp alternating stream. Two independent
0.5/cycle leaves fill each other's unused issue slots and approach one
instruction/cycle aggregate; two opcodes on one shared 0.5/cycle backend stay
at two clocks/instruction. The 2048-instruction unrolled independent streams
measure about 1.10 clocks/instruction because of fetch overhead, versus 2.004
for the shared pairs.

| alternating pair | clocks/instruction | domains |
|---|---:|---|
| IADD3 + IMAD | ~1.10 | ALU independent of FMA |
| IADD3 + DADD | ~1.10 | ALU independent of FP64 |
| IMAD + DADD | ~1.10 | FMA independent of FP64 |
| HFMA2 + DADD | ~1.10 | packed FP16 independent of FP64 |
| HFMA2.MMA + HFMA2 | ~1.10 | FP64-path MMA independent of packed FP16 |
| **IMAD + HFMA2** | **2.004** | **shared 0.5/cycle FMA backend** |
| **HFMA2.MMA + DADD** | **2.004** | **shared 0.5/cycle FP64 backend** |

The dense counted-barrier mixed streams and saturated ordered phases give the
same map and additionally show that the corresponding admission windows are
separate for ALU/FMA/FP64, but shared within each bold pair.

Same-subcore, yield=0 structure per SMSP:

```text
ALU domain      IADD3/LOP3/SHF/...        0.5 inst/cyc
FMA domain      IMAD (Heavy) + HFMA2       0.5 inst/cyc shared
FP64 domain     DADD/DFMA + HFMA2.MMA      0.5 inst/cyc shared (per-SMSP private)
FMA Lite        FFMA/FADD/FMUL             1.0 inst/cyc, bypasses ALU/Heavy
                                           (blocked only by packed state)
XU (MUFU)       8 cyc, fully disjoint
```

This is close to the B200 domain map (unified ALU ‖ FMA ‖ Lite) plus a
private FP64 domain; the Hopper-specific twist is that packed FP16 shares
the FMA-Heavy service and HFMA2.MMA shares the FP64 service.  The GH100
NCU catalog agrees: it exposes one `smsp__pipe_alu` (no heavy/lite split —
the split exists only on GB202: `pipe_aluheavy` +
`fmaheavy_subpipe_alulite`), plus `pipe_fmaheavy`/`pipe_fmalite`; there is
no separate fp64 pipe counter, so FP64 presumably accounts under
`pipe_fma`.

The earlier `probe_sm90_alu_fmaheavy_isolation.py` conclusion that H100 can
issue two instructions/cycle is invalid. Its two yield-0 streams reside at
different PCs and their timed windows are largely sequential: each per-warp
span can be near 2N while the global `max(end)-min(start)` wall span is near
4N. Summing reciprocal per-warp spans therefore double-counted time. NOP and
scalar FFMA establish a one-instruction/cycle frontend ceiling.

Scalar Lite fills the unused slot beside IADD3 or IMAD (~1.10 clocks/op in
the long alternating stream), but ordinary HFMA2 + FFMA stays at about two
clocks/op. This is the packed-state/Lite interlock described in the admission
note, not evidence for a deep Lite queue.

## Cross-arch comparison (per SMSP, clean solo rates)

| resource | GA100 sm_80 | AD102 sm_89 | GH100 sm_90 | GB202 sm_120 |
|---|---|---|---|---|
| FP32 FFMA | 2.0 (16 lanes) | 1.0 (32) | **1.0 (32, needs reuse bits)** | 1.0 (32, needs reuse bits) |
| INT IADD3 | 2.0 | 2.0 | 2.0 | 2.0 heavy / 1.0-ish lite split |
| IMAD | 2.0 (on FP32 pipe) | 2.0 (own 16-lane) | 2.0 (fmalighter mul path) | FMAHeavy |
| IMAD.WIDE | 4.0 | 4.0 | 4.0 | 4.0 |
| packed FP16 | 2.0 | 2.0 | 2.0 | 2.0 |
| FP64 DADD/DFMA | 4.0 (8/SMSP private) | 16/19 (2 lanes/SM shared) | **2.0 (16/SMSP private)** | SM-shared |
| MUFU | 8.0 | 8.0 | 8.0 | 8.0 |
| yield switch cost | +1 (NOP-verified) | +1 | **+1** (DFMA anomaly +1 on top of 2.0) | +1 |
| INT × IMAD same-subcore | disjoint (0.5+0.5) | disjoint (A + C-mul) | **disjoint (same2 mix +2)** | — |
| scalar structure | separate INT + FP32-with-mul | F + C(dual) + A | **ALU ‖ FMA(Heavy+HFMA2) ‖ Lite ‖ FP64(private)** | ALUH/ALUL-in-FMAH + FMAL |
| same-domain bypass | — | — | 2 | 2 |
| INT↔FP cross-domain | — | — | 3/4 | none (unified 2; some 3/4 paths) |

GH100 is architecturally much closer to AD102 than to GB202 for the scalar
side: 32 FP32 + 16 INT lanes, no ALU-Lite fast path.  Like GB202 (and unlike
GA100), **the RF needs reuse bits for full 3-source FP32 rate**: FFMA runs
1.0 with `[1:0:7]` but 2.0 with `[1:0]` — consistent with the H20-measured
bank law (≈1 warp operand per even/odd bank per clock: a 2E+1O FFMA needs
two even-bank reads).  INT ops stay at their 2.0 datapath floor regardless.

## Reproduction

```bash
# remote (Modal H100):
modal run tools/modal_h100_probe.py --script probe_sm90_rates.py
modal run tools/modal_h100_probe.py --script probe_alulite_latency.py
# ... aluheavy / fmalite / fmaheavy / fmaheavy_wide / fp16 / fp64
modal run tools/modal_h100_probe.py --script probe_sm90_ldc_req.py
```

Raw logs from the 2026-09-20 runs: alulite 80 rows, aluheavy 188,
fmalite 48, fmaheavy 48, fmaheavy_wide 64, fp16 64, fp64 64 — zero faults,
all permanent boundaries clean.

## Open questions

- Why does DFMA (but not DADD) expose the yield switch cycle on top of its
  2.0 floor?  fma64lite admission granularity vs int_pipe's.
- H20 re-run with clean brackets: does the nerfed die still show FFMA 1.0,
  and what are its FP64 rates (the fuse-nerf target)?
- HFMA2.MMA's +1 vs plain HFMA2: tensor-core-adjacent path or encoding
  variant of the same fp16 pipe?
- The coarse/fine 3-vs-4 phase sensitivity on cross-domain hops — same
  unresolved filler-shape effect as sm_120.
