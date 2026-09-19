# GA100 scalar-math pipes and ALU/FMA sharing

Hardware: NVIDIA A100-SXM4-40GB, compute capability 8.0.  Measurements were
made in September 2026 with native sm_80 cubins from this repository and
Nsight Compute 2023.1 running with performance-counter permission.

## 2026-09-19 update: occupancy counters, admission bursts, status

**NCU version is NOT the limiter.**  The `*_subpipe_*` leaf counters used for
the GB202 split (`fmaheavy_subpipe_alulite` etc.) are GB202 hardware counters;
a metric-namespace diff between NCU 2023.1 (remote, CUDA 12.1) and NCU
2025.4.1 (local, CUDA 13.x) over `--chip ga100` shows zero new scalar-pipe
metrics (only tensor-op paths, LSU latency and icache counters were added).
Copying a newer NCU to the A100 machine would not help.

**Official framing (NCU documentation, "Pipeline Statistics").**  NVIDIA
describes the GA10x FMA pipe as: *"The FMA pipeline processes most FP32
arithmetic (FADD, FMUL, FMAD). It also performs integer multiplication
operations (IMUL, IMAD), as well as integer dot products. On GA10x, FMA is a
logical pipeline ... an aggregated pipe composed of the FMA Heavy and FMA
Lite sub-pipelines."*  So the Heavy/Lite structure officially exists on GA10x
too; GA100 simply reports only the aggregate counter.  Our measurements pin
down what the aggregation means physically on GA100: the two sub-pipes
**time-share one 16-lane FP32 datapath per SMSP** — a 4x IMAD (heavy)
contender and an FFMA (lite) victim split the service proportionally (victim
slope ~10.9, i.e. the aggregate pipe stays at exactly 2 clk/inst), and a
single-warp FFMA+IMAD alternating stream shows zero overlap (4.00 clk/pair).
This is unlike GB202, where the same counter hierarchy hides two
independently accepting leaves (FFMA can fill IMAD's issue gaps at 2.167
clk/pair).  On GA100 the aggregate is not hiding parallel capacity; the 2-clk
service is one shared resource.

### New probes

- `tests/asm_construct/probe_sm80_pipe_occupancy.py` — 62 ops x
  active/predicated-off, 2048 all-reuse instances, grid=108x1 warp, run under
  ncu with `inst_executed_pipe_*` + `pipe_{alu,fma,fp64}_cycles_active` +
  `issue_active` + `math_pipe_throttle`.
- `tests/asm_construct/probe_sm80_admission_depth.py` — sm_80 port of the
  GB202 short-burst credit probe (`@P6` targets between two CS2R reads).

### Confirmed new facts (clean measurements)

1. **Uniform 2-clock pipe service.**  Every ALU-counter op occupies
   `pipe_alu` for exactly 2.0 cycles/instruction; every FMA-counter op
   (FFMA/FADD/FMUL/IMAD/IMUL/IDP.2A/IDP.4A, *including* IMAD.HI/WIDE) occupies
   `pipe_fma` for exactly 2.0 cycles/instruction.  FP64 ops occupy
   `pipe_fp64` exactly 4.0 cycles/instruction.  `issue_active` is ~1 cycle
   per instruction regardless: the warp issues in one cycle, then waits on
   `math_pipe_throttle` (~36% of active cycles at full rate).
2. **IMAD.HI/WIDE: 2-cycle pipe occupancy but 4-cycle admission.**  The
   elapsed wall rate is 4.0 inst/clk with 71% math throttle while
   `pipe_fma_cycles_active` stays 2.0/inst — the extra hold is admission-side
   and is *predicate-sensitive*: `@P6`-off IMAD.HI relaxes to 2.0/inst.  An
   IMAD.HI/DADD victim is immune to a 4x same-pipe contender (slope stays
   4.0) because its admission-limited stream leaves the pipe half idle.
3. **Predicated-off instructions retain full admission AND occupancy** on all
   pipes (identical inst_executed, cycles_active, elapsed, throttle vs the
   active stream).  Source slots were all-reuse, so this does not contradict
   the GB202 RF-read suppression.
4. **No burst/admission window for scalar pipes.**  Short-burst T(N) curves
   are linear from N=1: ALU ops admit the first op in +2 clocks, FMA/FP16/FP64
   in +1, then drain at the pipe rate.  One active credit per family, no
   hidden FIFO (unlike GB202 FP64's 7-credit redirectable window — GA100 FP64
   has NO burst window: T(N)=7+4N from N=1).
5. **FP64 is per-SMSP, not SM-shared.**  Four warps on four different
   subcores each sustain 4 clk/DADD in parallel (diff4); GB202's FP64 is a
   single 1-op/16clk SM-wide server.  Matches A100's 8 FP64 lanes/SMSP.
6. **Common scalar-math entrance credit.**  One *active* IMAD.HI prefix
   delays the next admission of ANY scalar family (ALU-heavy, ALU-lite,
   FMA, packed-FP16) by +4 clocks; one active HFMA2 prefix costs only +1..2.
7. **Single-warp pipe alternation has a penalty, no gap-filling.**
   One-warp alternating pairs: same-pipe (IADD+IADD, FFMA+IMAD) = 4.00
   clocks/pair; ALU×FMA pairs (IADD+IMAD, MOV+IMAD, IADD+FFMA, LOP3+IMAD) =
   4.50 clocks/pair — *worse* than same-pipe serialization, i.e. a ~0.25
   clock/instruction cross-pipe steering bubble and zero overlap.  (GB202
   fills FMA-Heavy gaps with ALU-Lite at 2.167 clocks/pair; GA100 does not.)
8. **HFMA2.MMA quirk:** counts on NO pipe counter at all (not even fp16).
9. **Mixed-stream occupancy (2048 IADD+IMAD pairs, one warp).**  Both pipes
   show their full 2.0 cyc/inst occupancy (alu 442368, fma 442368 cycles),
   elapsed is ~5.2 clk/pair, and `math_pipe_throttle` drops to **0** — the
   ALU×FMA alternation is limited by neither pipe's credit.  The ~0.25
   clk/inst penalty over the same-pipe FFMA+IMAD stream (5.28 clk/pair, 37%
   throttle on one pipe) sits in the shared dispatch/steering front-end.
   One-source IADD3 (`iadd3_1r`) still measures exactly 2.0 cyc/inst on
   pipe_alu: the 2-clock ALU floor is admission, not RF collection.

### Cross-pipe conflict matrix (consistent subset; see contamination caveat)

Victim = warp 0, contender = warp 4 (same subcore) with 4x instruction count;
slope in clocks per victim instruction; solo = 2.0:

| victim <- contender | slope | interpretation |
|---|---:|---|
| ALU x ALU (iadd/iadd3/mov/shf/lop3/prmt/isetp/fsetp any order) | 10.93 | ONE ALU server, proportional share |
| FMA x FMA (fadd/fmul/ffma/imad/idp4) | 10.93 | ONE FMA server |
| FP16 x FP16 (hadd2/hfma2/hmnmx2/hsetp2) | 10.93 | ONE FP16 server |
| iadd,mov <- imad/ffma | 2.59-2.63 | light cross-pipe interference |
| iadd3 <- imad | 4.00 | heavy cross-pipe interference |
| hfma2 <- ffma / imad / iadd3 | 4.00 | packed-FP couples to everything (cf. GB202 coupled credit) |
| hmnmx2 <- iadd3 | 2.63 | packed compare behaves light |
| imad_hi / imad_wide / dadd <- anything same-pipe | = solo (4.00) | admission-limited, immune |

So the earlier "hidden ALU admission classes" (heavy vs light) are **not two
ALU servers**: within-ALU pairs now show full proportional sharing (10.93).
The heavy/light split only appears in *cross-pipe* interference depth against
an FMA contender — consistent with heavy ops needing a 2-issue-slot
admission window that a cross-pipe contender can disrupt, while light ops
squeeze into single slots.  The GB202 layout (ALU-Lite physically inside the
FMA-Heavy envelope) does NOT carry over: on GA100, ALU and FMA are separate
physical pipe domains, and FP32-FMA/integer-multiply share one FMA server.

### Yield/switch-cost correction (2026-09-19, clean A100-PCIE rerun)

The original conflict matrix was measured with `SCHED = [7:7:{}:1:1]`
(yield=1 on every instruction).  Later work on sm_89/GB202 established that
yield is a warp-switch hint and **the switch itself costs one dead issue
cycle** (see `notes/sm120/yield_dispatch_cost.md`).  A clean-machine rerun
(A100-PCIE-40GB, windowed CS2R timestamps, max-overlap rep) pins the GA100
side of this:

- **GA100 has the same 1-cycle yield switch cost**: a solo NOP stream runs
  1.016 cyc/inst with `[1:0]` and 2.016 with `[1:1]`.  The cost was
  invisible in the original A100 measurements because every scalar-math op
  already sits at the 2.0 cyc/inst datapath floor, which absorbs the extra
  cycle.  Only NOP (fe_pipe, no datapath floor) reveals it.
- **The ~10.9 same-pipe conflict slope is NOT yield overhead.**  With
  yield-free reuse brackets, `iadd3<-iadd3` still starves the victim to
  10.71 cyc/inst while the contender runs at full speed (2.0) — a strong
  scheduler priority asymmetry, not a datapath share.  With yield brackets
  the same pair becomes 4.3/2.47 (forced alternation makes the split
  fairer).  The old 10.93 therefore mixes three effects: dependent-chain
  latency (old probe used chains, solo 4.0), the yield switch cost, and
  this priority asymmetry.
- **Priority direction is fickle**: with reuse brackets the winner flips by
  op and by stream shape — FFMA pair: victim wins (2.17, contender frozen);
  independent-dest IADD3 pair: contender wins (victim 10.71); chained IADD3
  pair: victim wins again (2.19).  Treat all same-pipe conflict magnitudes
  as qualitative; the robust fact is that the aggregate pipe rate stays at
  0.5 warp-inst/clk (16-lane capacity) in every configuration.
- The conflict-matrix **pairing** conclusions (which op pairs share a
  server, cross-pipe interference depth 2.59 vs 4.00, proportional share)
  are unaffected — they depend on relative ordering, not on the absolute
  10.93 magnitude.

### Contamination caveat (2026-09-19)

The two-warp conflict probe currently gives **bistable** results on this
machine: for some (pair, N=512) launches the contender's interference
vanishes entirely (victim runs at solo speed), flipping between process runs.
Two contributing defects found:

- Another tenant's inference job (all 8 GPUs, ~25% util, GPU7 at 100%) makes
  the machine unsuitable for uncontended timing right now.
- The conflict probe's prologue has a *marginal* S2R hazard: `SHR R5, R0, 0x5`
  sits 3 instructions after `S2R R0, SR_TID.X`; a dedicated sweep shows
  S2R->consumer needs a >=4-instruction gap on GA100 (gap<=3 reads stale 0,
  which silently disables the contender branch).  The admission-depth probe
  was fixed (4 NOPs); the conflict probe still has the borderline gap.

**TODO when the machine frees up:** lock clocks
(`sudo nvidia-smi -lgc 1410,1410 -i <gpu>`), pad the conflict-probe prologue,
have the contender store its own CS2R span (verify it actually ran), and
rerun the full matrix; also parse `occ_pairs.log` (mixed-pair occupancy).

## NCU-visible pipe partition

GA100 exposes only the older top-level instruction counters
`smsp__inst_executed_pipe_{alu,fma,fp16,fp64}`.  It does not expose the
`fmaheavy_subpipe_{alulite,fmaheavy}` leaf counters available on GB202.  A
minimal kernel containing 128 copies of each target instruction gives the
following exact partition.  The six initializer MOVs account for the ALU
counter floor of six in non-ALU kernels.

| NCU pipe | Mnemonics measured (+128 target instructions) |
|---|---|
| ALU | `BMSK F2FP FMNMX FSEL FSET FSETP I2I I2IP IABS IADD IADD3 IADD32I IMNMX ISCADD ISCADD32I ISETP LEA LOP LOP3 LOP32I MOV MOV32I P2R PLOP3 PRMT PSETP R2P SEL SGXT SHF SHL SHR` |
| FMA | `FADD FADD32I FFMA FFMA32I FMUL FMUL32I FSWZADD IDP.2A IDP.4A IMAD IMUL IMUL32I` |
| FP16 | `HADD2 HADD2_32I HFMA2 HFMA2_32I HMNMX2 HMUL2 HMUL2_32I HSET2 HSETP2` |
| FP64 | `CLMAD DADD DFMA DMUL DSETP` |

Seven scalar mnemonics present in the sm_120 catalog do not have encodable
mnemonics in the current sm_80 database: `F2IP`, `I2FP`, `MOV64IUR`,
`VIMNMX`, `FHADD`, `FHFMA`, and `VIADD`.

The important generational difference is that GA100 counts FP32 FADD/FFMA
and integer IMAD/IMUL/dot product on the same FMA pipe.  In a same-subcore
two-warp test, a four-times-long FFMA contender serializes an IMAD victim (and
vice versa): the victim slope grows from 2 to 10 clocks/instruction.  Thus the
GA100 counter is not merely a logical aggregate of the independently
accepting GB202 FMA-Heavy and FMA-Lite leaves; these tested operations expose
one common execution service on A100.

4x contender) expose one common execution service.  NVIDIA's NCU
documentation officially frames GA10x FMA as "an aggregated pipe composed of
the FMA Heavy and FMA Lite sub-pipelines" (see the 2026-09-19 update above):
the sub-pipes exist architecturally, but on GA100 they time-share a single
16-lane/SMSP FP32-capable datapath, so the aggregate counter is not hiding
independently accepting leaves the way it does on GB202.

### Doc-guided reinterpretation (NCU pipe glossary)

The NCU documentation's pipe glossary (ALU/ALUHeavy/ALULite/CBU/FMA/
FMAHeavy/FMALite/FP16) is written for the *current* counter hierarchy and
matches GB202 exactly ("Shared FMA Heavy is an aggregated, physical pipe
composed of the subpipes FMA Heavy and ALU Lite").  Two sentences explicitly
scope Ampere:

- *"On GA10x, FMA is a logical pipeline ... an aggregated pipe composed of
  the FMA Heavy and FMA Lite sub-pipelines."*
- *"On Volta, Turing and NVIDIA GA100, the FP16 pipeline performs paired FP16
  instructions ... Starting with GA10x chips, this functionality is part of
  the FMA pipeline."*  (Note the wording: GA100 keeps a separate FP16 pipe;
  the consumer GA10x parts fold FP16 into FMA.  Our scan confirms a separate
  `pipe_fp16` counter on GA100 with HADD2/HFMA2/HMUL2/HMNMX2/HSET2/HSETP2.)

Re-reading our GA100 measurements against the glossary:

| Doc element | GA100 counter | Measured GA100 behavior |
|---|---|---|
| ALU = ALUHeavy + ALULite, "ALU Lite is a subpipe of physical pipe FMA Heavy" | `pipe_alu` (aggregate only) | **Placement does NOT carry over.**  ALU-Lite ops (MOV/IADD) share ONE server with ALU-Heavy ops (IADD3/SHF/LOP3): `mov<-iadd3` and `iadd<-iadd3` conflict at the full proportional-share slope 10.93, while `iadd<-imad` (alulite vs FMA) interferes only mildly (2.59) and `iadd3<-imad` at 4.00.  If ALU Lite really sat inside the FMA-Heavy pipe, IADD vs IMAD would share a server (slope ~10) and IADD3 vs IMAD would be milder.  We measure the exact opposite. |
| FMA = FMAHeavy + FMALite aggregate | `pipe_fma` (aggregate only) | The aggregate time-shares one 16-lane/SMSP FP32-capable datapath: FFMA (lite) and IMAD (heavy) fully serialize (conflict slope ~10, single-warp alternation 4.00 clk/pair).  No independent-acceptance leaves as on GB202.  GA100 is 64 FP32 lanes/SM; the consumer GA102 "both paths do FP32" (128/SM) arrangement is where a real FMALite datapath exists. |
| FMAHeavy also does FP16 (HADD2/HMUL2/HFMA2) | `pipe_fp16` separate | On GA100 packed FP16 arithmetic counts ONLY on `pipe_fp16`, never on `pipe_fma` — the doc's "FMAHeavy performs FP16" applies to chips where FP16 is folded into FMA (GA10x consumer), not GA100.  HFMA2.MMA counts on no pipe counter at all. |
| "ALU performs fast FP32-to-FP16 conversion on Ampere" | `pipe_alu` | Confirmed: F2FP counts on `pipe_alu` at 2.0 cyc/inst. |
| FP64 (not in glossary excerpt) | `pipe_fp64` | Per-SMSP server, 4.0 cyc/inst, no SM-level sharing (diff4 test), no redirectable burst window. |

Net GA100 structure (measured), per SMSP:

```text
scheduler (1 inst/clk)
  |-- shared scalar-math entrance credit (1 active op; an active IMAD.HI
  |    blocks ALL scalar families' next admission by +4 clk)
  |-- ALU pipe   : 2 clk/inst, ONE server for heavy+lite ALU ops + F2FP
  |-- FMA pipe   : 2 clk/inst, ONE server for FP32 FMA/add/mul + IMAD/IMUL/IDP
  |                 (IMAD.HI/WIDE: 4-clk admission hold, 2-clk occupancy)
  |-- FP16 pipe  : separate; packed FP16 arithmetic
  |-- FP64 pipe  : 4 clk/inst, per-SMSP (not SM-shared)
```

### Cross-check against the GA100 whitepaper SM diagram

The GA100 microarchitecture diagram draws, per subcore, **16 INT32 units +
16 FP32 units** (32 total; plus 8 FP64 lanes implied by the 1:2 FP64:FP32
ratio and 4 third-gen tensor-core units).  Weak evidence (unit counts, not
wiring), but it lines up exactly with the measured model:

| Diagram block | Measured signature |
|---|---|
| 16 INT32 lanes/SMSP | ALU pipe: exactly 2.0 cyc/warp-inst for every ALU op (32 lanes / 16 units) |
| 16 FP32 lanes/SMSP | FMA pipe: exactly 2.0 cyc/warp-inst for FFMA/FADD/FMUL — and for IMAD/IMUL/IDP, i.e. **integer multiplication runs on the FP32 multiplier array** (FFMA×IMAD timeshare one server at proportional-share slope ~10.9) |
| separate INT vs FP32 blocks | ALU and FMA are separate physical servers on GA100 (no ALU-Lite inside FMA as on GB202) |
| 8 FP64 lanes/SMSP | FP64 pipe: exactly 4.0 cyc/inst, per-SMSP, no SM sharing |
| (FP16 not drawn) | separate `pipe_fp16` counter + execution-separate (HFMA2 vs any contender = 4.0 cross-pipe interference, never the 10.9 same-server share) |

This also explains why the NCU glossary's "Shared FMA Heavy = FMA Heavy +
ALU Lite" topology fits GB202 (and consumer GA102, whose 16+16
"FP32 + FP32/INT32" per-SMSP blocks literally share one datapath between FP32
and INT work) but not GA100: GA100's INT32 block is a full private 16-lane
array, so ALU Lite has no reason to live inside the FMA pipe.

So the glossary's *names* are a cross-chip counter taxonomy; the GB202
physical topology (ALU Lite inside Shared FMA Heavy, FMALite as an
independently accepting leaf) must not be projected onto GA100.  On GA100
each NCU counter pipe behaves as one time-shared 2-clk server, and the
heavy/light vocabulary is visible only as cross-pipe interference depth
(2.59 vs 4.00) and admission-width differences, not as separate servers.

### Issue-rate and RF-bandwidth exclusions

All structural conclusions above hold against the two obvious confounders:

**Issue-rate limit (1 inst/clk/SMSP).**  The occupancy scan shows
`issue_active` = 1.02 cycles/instruction for every op while the pipe counter
shows 2.0 cycles/instruction: the scheduler issues each instruction in one
cycle and the warp then waits on `math_pipe_throttle`.  The issue port is 50%
idle at the measured floor, so the 2-clk service is pipe backpressure, not
issue bandwidth.  In the conflict probe the same-subcore totals are 0.59
inst/clk (victim 1/10.93 + contender 1/2) — far below the 1/clk issue limit,
so issue arbitration alone cannot produce the 5:1 starvation; a saturated
2-clk *execution* server (utilization ≈ 0.92) can.

**RF read bandwidth.**  All conflict/occupancy runs mark every source slot
reusable (`batch_t=7`), which eliminates RF reads, and the results are
identical to the non-reuse forms (September note + our reruns).  Moreover the
predicated-off streams (which perform no architectural reads/writes at all)
retain the full 2.0/4.0 pipe occupancy.  Even without reuse, a 3-source op
needs at most 2 even + 1 odd bank reads; at the known 2R1W-per-bank GA100 RF
organization that collects in one cycle, below the 2-clk pipe floor, so RF
reads cannot bind a scalar stream in the first place.  `iadd3_1r`
(one source) measuring the same 2.0/inst as 3-source IADD3 confirms this
directly.

**RF write bandwidth.**  Every stream writes one 32-bit result per
instruction with rotating parity — 0.25 W/clk/bank average at the 2-clk
floor, against 1W/clk/bank available.  The `Rd=RZ` controls (no register
write at all) give identical slopes, and predicated-off streams keep full
pipe occupancy with zero writeback.  Writeback is excluded.

The one SM-level residue that is *not* pipe/RF/issue is the different-subcore
control running at 2.37 instead of 2.00 in the September-19 sessions: a
contender on another SMSP slows the victim ~19%.  Plausible causes are shared
L1i fetch or clock/power coupling; it needs an idle-machine rerun (with
locked clocks) before interpretation.

### Machine status caveat (2026-09-19)

The A100 machine currently runs another tenant's inference job on all GPUs,
which makes the two-warp conflict probe bistable (see "Contamination caveat"
above).  The conflict slopes quoted below are from the September idle-machine
session and remain consistent with the clean occupancy/admission data.

## Hidden ALU admission classes

Although NCU reports all 32 operations above as `pipe_alu`, an all-source-
reuse structural-conflict scan separates two admission behaviours.  Each
instruction alone takes exactly 2 clocks per warp instruction on one GA100
subcore.

With a four-times-long FMA contender on the same subcore:

| inferred ALU admission class | Mnemonics | victim slope |
|---|---|---:|
| heavy | `IADD3 LOP3 PRMT SHF` | 4.000000 clocks/instruction |
| light | all other measured ALU mnemonics in the table above | 2.585938 clocks/instruction |

The different-subcore control remains 2.000000.  All source slots were marked
reusable, so this split is not RF read bandwidth.  Repeating representative
tests with both results discarded to `RZ` gives the same values:

| pair (same subcore) | normal destination | `Rd=RZ` |
|---|---:|---:|
| `IADD + IMAD` | 2.585938 | 2.585938 |
| `MOV + IMAD` | 2.585938 | 2.585938 |
| `IADD3 + IMAD` | 4.000000 | 4.000000 |
| `IADD + FFMA` | 2.585938 | 2.585938 |
| `FFMA + IMAD` (same FMA pipe) | 10.000000 | 10.000000 |

It is therefore also not scalar-RF writeback arbitration.  Calling the two
sets *ALU Heavy* and *ALU Lite* is a microarchitectural inference from their
admission behaviour; GA100's public counters do not expose those leaf names.

## What ALU Lite and FMA share on GA100

The best-fit model is not a shared arithmetic body:

```text
                  one subcore warp scheduler
                           |
                 common issue/admission control
                     /             \
       inferred ALU-Lite body      FMA body
       (gap-using admission)       (2-cycle warp service)
                     \             /
                  common scalar RF domain
```

A same-pipe victim with a 4x contender has slope 10, whereas an ALU-Lite/FMA
pair has slope only 2.585938.  Most of their execution occupancy therefore
overlaps.  The residual penalty survives both operand reuse and `Rd=RZ`,
placing the shared resource before execution/writeback: most likely the
single warp scheduler's issue selection, dispatch wiring, or a common
admission-credit boundary.

The inferred heavy ALU class paired with FMA has slope four.  This still does
not imply a common arithmetic unit: separate exposed FP16 and FMA pipes also
produce slope four, while same-pipe FP16/FP16 produces slope ten.  Rather,
two heavy-class warp instructions cannot exploit the admission gaps that a
light ALU instruction can use.

Consequently, the GB202 phrase **Shared FMA Heavy = ALU Lite + FMA Heavy**
must not be projected literally onto GA100.  On A100, NCU exposes ALU and FMA
as separate physical pipe domains, and the directly visible sharing is a
subcore-front-end admission effect.  Any deeper common physical placement,
clocking, or wiring cannot be isolated by these counters.

## Reproduction

The NCU catalog uses
`tests/asm_construct/probe_scalar_pipe_catalog.py` with
`ASSEMBLER_ARCH=sm80`.  The single-warp floor can be checked with the first
probe below; structural sharing is measured by the second:

```bash
python3 tests/asm_construct/probe_sm80_scalar_overlap.py

python3 tests/asm_construct/probe_sm80_scalar_conflict.py \
  --pair iadd_rz,imad_rz --pair iadd3_rz,imad_rz \
  --pair ffma_rz,imad_rz --counts 128,256 \
  --placements solo,same,different --factor 4
```

The two-warp test uses warp 0 as victim, warp 4 as the same-subcore contender,
and warp 1 as the different-subcore control.
