# sm_89 (Ada / RTX 4090) scalar math pipeline structure

Probed on RTX 4090 (AD102, 128 SMs, CUDA 12.8 driver) with the repo
assembler (new `sm89` arch config, see below).  **No NCU** on this host —
all numbers are CS2R/SR_CLOCKLO timing.  CS2R verified to tick at the real
SM clock: a 2×10^8-FFMA loop measured 17 800 143 CS2R cycles in 7.2 ms wall
= 2.477 GHz ≈ the observed 2.5 GHz boost clock, so "cycle" below is a real
SM cycle.

## Assembler support (new)

- `sm_89_instructions.txt` → `tools/parse_sm75_80.py` now also builds
  `sm89.json` (1340 variants, 203 mnemonics, 0 structural errors).
- `assembler/arch.py`: `sm89` ArchConfig — captured from an nvcc CUDA 12.8
  `sm_89` cubin: params at `c[0x0][0x160]`, default cdesc `c[0x0][0x118]`
  (same ABI as sm_80), `e_flags = 0x00590559` (arch nibble 0x59 = 89),
  ELF OSABI 0x33 / ABIVER 0x07, ET_EXEC.
- **Const-bank offsets are DWORD indices** (like sm_70/sm_80, unlike sm_90+):
  our encoder wrote byte offset 0x160 and nvdisasm rendered `c[0x0][0x580]`;
  fixed by adding `sm_89_instructions.txt` to the dword-division set in
  `sass_encoder.py` (`ConstBankAddress0/2`).  Smoke test: full 160-lane
  store kernel passes on hardware.
- Probes take `PROBE_ARCH=sm89` (env) instead of a hardcoded `sm80`.

## Solo per-warp rates (1 warp per SM, batch_t=7 reuse bracket)

| Instruction | cyc/inst | lanes/clk/SMSP |
|---|---|---|
| FFMA / FADD / FMUL | **1.00** | 32 FP32 |
| IADD / IADD3 / LOP3 / SHF / MOV | 2.00 | 16 INT |
| IMAD | 2.00 | 16 |
| IMAD.WIDE.U32 | 4.00 | 8 |
| IDP.4A.S8.S8 | 2.00 | 16 (×4 dot) |
| HFMA2 / HFMA2.MMA | 2.00 | 16 packed (32 half/clk) |
| DFMA | 16.0 | 2 FP64 per SM (shared!) |
| DADD / DMUL | 19.0 | 2 FP64 per SM |
| MUFU.RCP / POPC / F2I / I2F | 8.00¹ | 4 |
| NOP | ~0.5 (issue-bound) | — |

¹ measured with the `[7:7:{}:1:0]` bracket — the reuse/batch_t=7
combination is an *illegal encoding* for these classes on sm_89
(`ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR`); the assembler rejects it.

The Ada SM picture (per SMSP: 32 FP32 + 16 INT32 lanes, 2× the FP32 of
GA100) matches: FFMA runs at full 32-lane rate from a SINGLE warp (GA100
halved it), INT stays at 16 lanes.

**yield=1 costs a full issue slot on sm_89**: the same FFMA stream with
`[7:7:{}:1:1]` runs at 2.00 cyc/inst instead of 1.00.  The yield releases
the scheduler and the solo warp is not re-picked the next cycle.  Any
bracket-based probe must use `[7:7:{}:1:0:7]` (or `:1:0`) to expose pipe
rates; the older conflict probe's `[7:7:{}:1:1]` masked exactly the
FFMA 1.0-vs-2.0 generational difference until this was found.

Two-warp follow-up (both warps yield=1, same subcore, windowed):

- The int_pipe serialization lock **disappears** — all pairs (iadd<-iadd,
  iadd<-ffma, ...) overlap on every rep.  The lock is therefore specifically
  "a no-yield int stream never generates a switch event", and an explicit
  yield forces one.
- Both-yield FFMA×2 combine for only ~0.50/clk during overlap (half the 1.0
  FP32 capacity).  On GB202 the same setup gives the identical halving, and
  the mechanism was pinned down there (see
  `notes/sm120/yield_dispatch_cost.md`): **yield = warp-switch hint, and the
  switch itself costs one dead issue cycle** — a NOP stream (no operands, no
  reuse cache at stake) pays it too; the dead cycle follows the switch
  event, and a non-yielding sibling can issue right through the yielding
  warp's pauses (mixed yield/no-yield: 0.33/0.87).  sm_89 assumes the same
  mechanism (not re-run with the mixed brackets).

## Multi-warp same-subcore (windowed CS2R timestamps, warp→SMSP = w%4)

Methodology warning: the A100-style conflict probe (contender 4× longer,
min-over-reps victim slope) is **unreliable on sm_89** — same-subcore warp
pairs are *bistable*: in some launches the contender's window starts exactly
when the victim's ends (zero overlap, verified with per-warp CS2R
start/end timestamps), in others they fully overlap.  Min-over-reps then
silently picks whichever mode appeared.  The fix is to record both warps'
start/end and select the max-overlap rep (`/tmp` probes `aggregate.py`,
`asym.py`; repo copy `tests/asm_construct/probe_sm89_scalar_windows.py`).
Warp→SMSP mapping confirmed w%4 by sweeping contender warps
1–7: only w4 ever contends with w0.  (The serialization turns out to be
deterministic for int_pipe victims — see the next section.)

Aggregate capacity per SMSP (max-overlap reps, inst/clk summed over warps):

| mix (per-warp streams) | aggregate inst/clk | notes |
|---|---|---|
| FFMA ×2 / ×4 warps | 0.98–0.99 | 32 FP32 lanes shared; solo warp can saturate |
| IADD ×2 / ×4 | 0.50 | 16 INT lanes shared |
| IMAD ×2 / ×4 | 0.50 | INT-mul on its own 16-lane resource |
| HFMA2 ×2 | 0.50 | packed FP16 = 16 lanes |
| FADD ×2, FFMA+FADD | 0.98 | FADD shares the FP32 32-lane pool |
| FFMA + IADD | 0.66 | FFMA keeps ~0.98, IADD squeezed to ~0.34 |
| FFMA + IMAD | 0.66 | FFMA 0.98, IMAD 0.34 |
| FFMA + HFMA2 | 0.66 | FFMA 0.98, HFMA2 0.34 |
| HFMA2 + IMAD | ~0.75 | HFMA2 full 0.50 AND IMAD 0.25 — partially disjoint resources |

Model that fits: per SMSP two 16-lane FP32 blocks (F = FP32-only,
C = FP32/INT shared).  FFMA uses F+C (32 lanes, 1.0/inst solo); a second
FFMA warp splits the same blocks (aggregate 1.0).  INT ops need C (16 lanes,
0.5/inst solo; two INT warps share C → aggregate 0.5).  When FFMA competes
with INT, arbitration strongly favors FFMA: it keeps ~0.98 while INT gets
the C leftovers (~0.34 ≈ 1/3 of the block).  HFMA2 (packed FP16) behaves
like a 16-lane op of its own that partially overlaps the IMAD resource.

## FP64 is SM-shared (opposite of GA100)

`probe_sm80_admission_depth --mode fp64 --actors diff4` (one warp per
subcore, 4 subcores): per-warp cost goes from +18 cyc/op (solo) to +72
(4×) → the FP64 unit(s) are shared SM-wide.  DFMA at 16 cyc/inst/warp =
32 lanes × 4 subcores / 128 lanes-clk ⇒ **2 FP64 lanes per SM** (1:64 of
FP32, the consumer ratio).  GA100 instead has 8 private FP64 lanes per SMSP
(diff4 showed no slowdown, 4 cyc/op each).  This mirrors GB202's shared
FP64 (there with a 7-credit admission window).

## Admission depth (predicated-off bursts, single warp)

`probe_sm80_admission_depth` on sm_89: every scalar class (IADD3/IADD/IMAD/
FFMA/HFMA2) is linear from N=1 at +2 cyc/op with predicated-off `@P6`
streams — **no burst/credit window** (like GA100, unlike GB202's 7-credit
FMALite window).  Predicated-off FP64 holds +18 cyc/op (same as active).

Note: predicated-off FFMA costs 2.0, not the active 1.0 — the off-mask
stream doesn't reach the 32-lane rate (either the predicated-off dispatch
takes the INT-style 2-clk slot, or the bracket interacts; not resolved).

## Warp co-scheduling: the int_pipe stream monopolizes the subcore

Windowed two-warp experiments (victim w0 = 512-inst stream, contender w4 =
2048-inst stream, same subcore, overlap measured from CS2R start/end):

| victim stream | contender | overlap? |
|---|---|---|
| IADD / IADD3 / LOP3 / SHF / MOV (all int_pipe) | iadd / iadd3 / ffma / nop | **NEVER — strict serialization** (contender's first instruction lands the cycle after the victim's last) |
| FFMA (1.0/inst, pipe-saturating) | iadd / ffma / nop | yes (occasionally sequential — bistable) |
| IMAD (2.0/inst) | iadd / imad / ffma | yes |
| NOP (fe_pipe, no math unit) | iadd | yes |
| MUFU (8.0/inst, MIO) | iadd | yes |
| DADD (19/inst, FP64) | iadd | yes |

This refutes the naive "greedy until math-pipe backpressure" scheduler
model: NOP/MUFU/DADD streams (no math pipe, or far heavier backpressure)
cede the scheduler, while the exactly-at-capacity IADD stream (0.5/clk offer
= 16-lane INT service rate) starves its sibling completely — the sibling
cannot even issue fe_pipe NOPs.  The working model is that on sm_89 an
int_pipe dispatch stream **holds the SMSP arbitration stage** (or never
generates a warp-switch event), so a sibling warp is only scheduled once
the int stream drains.  32-lane-piped FFMA at 1.0/inst does not block
arbitration; MIO/FP64 ops release it immediately after dispatch into their
queues.

Complication: with FOUR int_pipe warps on the subcore (w0/w4/w8/w12) the
streams DO interleave (per-warp 0.49/0.13/0.17/0.25, aggregate 0.50/clk) —
so the exclusion is specific to the two-warp situation; the multi-warp
arbiter mode differs.  Open: what exactly generates a switch event, and why
int×4 interleaves while int×2 and int+nop serialize.

Consequence for measurement methodology: any two-warp sm_89 conflict probe
whose victim is an int_pipe stream measures scheduling policy, not pipe
contention.  Cross-pipe INT×FP32 contention must be measured with the INT
op as the *contender* (ffma<-iadd: FFMA stays 0.98, IADD is squeezed to
~0.34 — that overlap does happen).

## Refined datapath model (16 dual-mode + 16 FP-only, sticky mode)

Working model, cross-checked against all of the above: per SMSP there is a
16-lane FP32-only block (F) and a 16-lane dual-mode block (C) whose
FP32-mul/FADD and INT-mul paths are shared, plus a separate 16-lane INT
adder/logic array (A):

- FFMA/FADD/FMUL need F+C (32 lanes) → 1.0/inst solo, shared 1.0/clk.
- HFMA2 needs C in FP mode (16 packed lanes) → 2.0/inst.
- IMAD uses C's multiplier path (16 lanes) → 2.0/inst; conflicts with FFMA
  cross-warp (FFMA 0.98 / IMAD 0.34) but **fully overlaps IADD**
  (0.50+0.50 both full rate, verified with windowed timestamps) and
  single-warp IADD/IMAD alternation sustains 1.0/inst aggregate.
- IADD/IADD3/LOP3/SHF/MOV use A (16 lanes) → 2.0/inst, shared 0.5/clk.

The scheduler treats the C block's INT↔FP mode as *sticky at warp
granularity*: an active int_pipe stream pins the subcore and the sibling
warp is not scheduled at all (even its fe_pipe NOPs never issue — the
exclusion is at warp selection, not dispatch).  Once the sibling is a
non-int stream (or four int warps make the mode uniform), normal
interleaving resumes.

Quantitative wrinkle, now largely resolved: when FFMA (victim) shares with a
16-lane C-user (IADD contender 0.34, IMAD 0.34, HFMA2 0.34), FFMA stays at
0.98.  Strict input time-slicing of C (1:1 alternation) would predict FFMA =
F(0.5) + C(0.25) = 0.75, so the observed 0.98 requires that **switching C's
input mux to INT mode does not stall its FP32 backend** — already-admitted
FFMA lanes keep draining while C's front-end serves INT work.  Doubling the
INT-mul pressure (ffma + imad×2) leaves FFMA at 0.94 and the IMADs split
their fixed ~0.5/clk datapath capacity (0.20+0.34), i.e. the limit is the
C-mul datapath, not a scheduler slot ratio.  Conversely imad×2+iadd shows
IMADs sharing ~0.53 while IADD runs at 0.43 on its independent adder A —
so A (INT add/logic) and C-mul are separate physical resources.  (Caveat:
with ≥3 warps the per-warp windows are staggered, so individual rates are
window averages; the robust invariants are the aggregate capacities and
FFMA's pressure immunity.)

## Official pipe taxonomy vs measured reality

`sm_89_latencies.txt` (nvdisasm dump) defines: `int_pipe` (IADD3/IADD/LOP3/
SHF/MOV/PRMT/I2I/...), `fmalighter_pipe` (FFMA/FADD/FMUL + **IMAD/IMUL/
IDP4A**), `fp16_pipe` (HFMA2/HADD2/HMUL2/HMNMX2/HMMA/QMMA), `fma64lite_pipe`
(DFMA/DADD/DMUL + **HFMA2.MMA**), `mio_pipe` (MUFU/POPC/F2I/I2F/...).

Measured reality diverges from the logical pipes in two places:

- **fmalighter is internally heterogeneous**: FFMA runs 32 lanes/clk
  (1.0/inst) but IMAD — officially the same pipe — runs 16 lanes/clk
  (2.0/inst), and an IMAD warp + FFMA warp aggregate 0.66/clk (not the 1.0
  of a true shared 32-lane unit, nor full overlap).  The dump's own latency
  tables already split them: `TABLE_TRUE` has separate `FMAI_WITHOUT_IMAD`
  and `IMAD_OP` rows (with different numbers: 5/4/4 vs 5/4/6 in the first
  columns).
- **HFMA2.MMA is officially in fma64lite_pipe** (with DFMA/DADD) but
  measures 2.0 cyc/inst like plain HFMA2, not 16–19 like FP64.

## Generational comparison (per SMSP per clock)

| resource | sm_80 (GA100) | sm_89 (AD102) | sm_120 (GB202) |
|---|---|---|---|
| FP32 (FFMA) | 16 lanes (2.0 cyc/inst) | **32 lanes (1.0)** | 32 lanes via FMAHeavy+FMALite |
| INT (IADD3/LOP3/SHF) | 16 (2.0) | 16 (2.0) | 16 heavy + 16 lite (ALUHeavy/ALULite) |
| IMAD | on FP32 pipe (2.0) | own 16-lane (2.0) | FMAHeavy |
| packed FP16 (HFMA2) | 16 (2.0) | 16 (2.0) | folded into FMA |
| FP64 | 8/SMSP private (4.0) | **2/SM shared** (16–19) | SM-shared, 7-credit window |
| burst admission | none | none | 7-credit window |
| yield=1 bracket | +1 cyc/inst switch cost (NOP-verified; hidden under the 2.0 datapath floor for math ops — see sm_80 note "Yield/switch-cost correction") | halves stream (switch dead cycle) | halves stream (switch dead cycle) — see notes/sm120/yield_dispatch_cost.md |
| no-yield int stream locks subcore | (not observed; pairs always overlapped) | YES (int×2 strict serialize) | no (int×2 overlaps) |

## Open questions

- What exactly generates a warp-switch event on sm_89; why int×4
  interleaves while int×2 and int+nop serialize (the C-block mode
  stickiness is warp-granular, but the 4-warp escape hatch is unexplained).
- MUFU/POPC/F2I at 8.0 measured without the reuse bracket — re-measure with
  a legal reuse-bracket variant if one exists, to separate bracket cost
  from unit cost.
- Predicated-off FFMA costing 2.0 while active costs 1.0.

## Reproduction

```
rsync assembler/ sm89.json tests/asm_construct/ to the 4090 host
PROBE_ARCH=sm89 python3 tests/asm_construct/probe_sm80_scalar_overlap.py
PROBE_ARCH=sm89 python3 tests/asm_construct/probe_sm80_scalar_conflict.py ...
PROBE_ARCH=sm89 python3 tests/asm_construct/probe_sm80_admission_depth.py --mode fp64 --actors diff4
```

plus the windowed-timestamp probes (`aggregate.py`, `asym.py`, `multiw2.py`,
`rates2/3.py`, `clockcheck2.py` — copies in /tmp on the 4090 host at
`/tmp/nvsass_4090` and `/tmp/*.py`).
