# GB202 subcore compute-path structural-conflict probe

**Status:** extended, directly measured on RTX 5090 / sm_120 on 2026-09-14--15.
The reusable probe is
`tests/asm_construct/probe_subcore_compute_conflict.py`.

For the corresponding H20/sm_90 experiment, including source/destination RF
bank controls and FP64, see `notes/sm90/arch/h20_compute_conflicts.md`.  The
H20 controls show that much of the active cross-family slowdown is banked
source collection rather than one unified ALU execution array.

## Question and placement control

Which scalar compute instructions contend for structures inside one GB202
subcore, and at which predicate/dispatch stage does the contention appear?

The probe uses one 256-thread CTA and the independently verified in-CTA
placement `warp_id % 4`:

- victim: warp 0;
- same-subcore contender: warp 4;
- different-subcore contender: warp 1.

Every body is an unrolled stream with 40 rotating destinations, stall 1 and
yield 1.  The contender is four times longer than the victim; its own clock
samples verify that it covers the victim's complete timed interval.  Multiple
victim lengths are fit as `cycles = slope*N + intercept`, so setup, branch and
clock-read costs fall into the intercept.

## Why NOP alone is not an adequate control

The first experiment used an active NOP stream as the contender control.  On
this GPU, a same-subcore NOP contender barely slows an arithmetic victim,
whereas an active arithmetic contender usually does.  NOP therefore does not
model the frontend/dispatch behavior of a compute instruction closely enough.

The final experiment retains NOP but adds a stronger control: the **same B
instruction with the same scheduling word, guarded by the never-written P6**.
P6 is false at kernel entry.  This preserves the instruction encoding and its
predicate-insensitive fetch/issue/dispatch reservations while disabling its
architectural operand/execution/writeback effects.

Three difference-in-differences scores are reported, in victim cycles per
instruction:

```text
E_dispatch = (same_ctrl - same_nop) - (diff_ctrl - diff_nop)
E_execute  = (same_ab - same_ctrl) - (diff_ab - diff_ctrl)
E_total    = (same_ab - same_nop) - (diff_ab - diff_nop)
```

`E_dispatch` is predicate-insensitive pressure; `E_execute` is the additional
pressure when B is predicated on.  This naming describes the observable
boundary, not a claim that the underlying physical stages have been uniquely
identified.

## Preliminary naked-run matrix

Run parameters: lengths 128/256/512, two repetitions, best-of per point,
linear slope fit.  No profiler was attached.  Sources use the parity-balanced
set `R24/R27/R28` (2 even + 1 odd); an earlier exploratory run accidentally
used three even sources and is superseded by this table.

| victim <- contender | E_dispatch | E_execute | E_total |
|---|---:|---:|---:|
| IADD3 <- IADD3 | +1.646 | +0.309 | +1.955 |
| FFMA <- FFMA | +0.107 | +1.791 | +1.898 |
| HFMA2 <- HFMA2 | +1.588 | +0.044 | +1.632 |
| MUFU.RCP <- MUFU.RCP | +9.138 | -0.136 | +9.002 |
| IADD3 <- FFMA | +0.171 | +1.518 | +1.690 |
| IADD3 <- HFMA2 | +0.061 | +1.458 | +1.519 |
| FFMA <- HFMA2 | +2.399 | -0.321 | +2.078 |
| FFMA <- MUFU.RCP | +0.055 | +0.633 | +0.688 |

The robust first observations are:

1. Same-subcore active compute streams interact strongly; different-subcore
   versions are close to the solo slope.  The established placement control is
   therefore working.
2. FFMA's self-pressure is mostly predicate-sensitive.  Its predicated-off
   stream is close to the NOP control, while active FFMA adds ~1.79 victim
   cycles/instruction.
3. IADD3 and HFMA2 self-pressure is mainly predicate-insensitive.  In
   particular, active HFMA2 adds almost nothing beyond its predicated-off
   dispatch path.
4. MUFU.RCP is almost entirely predicate-insensitive in this test: a
   predicated-off MUFU stream is already as disruptive as the active stream.
   This is consistent with an early MIO/MUFU dispatch bottleneck, but does not
   by itself locate the exact queue or execution unit.
5. Cross-family conflicts are directional.  For example HFMA2 produces a
   large predicate-insensitive effect on an FFMA victim, while FFMA's effect on
   IADD3 is mostly predicate-sensitive.  A complete **ordered** matrix is
   required; `(A,B)` must not be assumed equal to `(B,A)`.

## Source-bank controls: separate RF collection from execution

The expanded run controls source parity independently of destination parity.
The normal three-source pattern is `R24/R27/R28` = 2 even + 1 odd; the
complement is `R25/R26/R29` = 1 even + 2 odd; `_e` variants use three even
sources.  The most useful same-subcore active results are:

| victim / contender | fitted victim clocks/instruction |
|---|---:|
| FFMA / FFMA, same 2E+1O pattern | ~3.59--4.17 |
| FFMA / complementary FFMA | ~2.85 |
| FFMA / all-even FFMA | ~4.56 |
| FADD / FADD, each 1E+1O | ~2.00 |
| FADD / all-even FADD | ~2.81 |
| IADD3 / FFMA, original sources | ~3.69 |
| IADD3 / complementary FFMA | ~2.61 |
| FFMA / IADD3, original sources | ~3.33 |
| FFMA / complementary IADD3 | ~2.62 |

The curves follow the maximum same-parity source demand, not a unified ALU
occupancy.  The two parity banks each accept two physical reads, which form
one warp-wide 32-bit operand per clock; banks operate in parallel.  Thus a
single instruction with 2E+1O needs two collection clocks, while 3E needs
three.  Multiple same-subcore warps and different instruction families feed
the same collectors.

Flipping only the contender destination (`_o`) does not produce a stable
sustained change for IADD3, FFMA, FADD, HFMA2, or IMAD.  This distinguishes
the source-collection limit from the separately proven transient 1W-per-bank
commit collision.  Dead-result independent streams can phase their writes
around that commit arbiter even though an intentionally aligned completion
can still collide.

### Single-warp reuse discriminator

Yield-zero streams expose the narrowest per-instruction limits without the
two-warp scheduler's yield policy.  Reuse masks remove reads while keeping the
opcode and destination stream unchanged:

| stream | remaining steady-state RF demand | clocks/instruction |
|---|---:|---:|
| FADD, 1E+1O | 1E+1O | ~1.08 |
| FFMA, 2E+1O | 2E+1O | 2.00 |
| FFMA, 3E | 3E | 3.00 |
| all-even FFMA, reuse any one source | 2E | 2.00 |
| all-even FFMA, reuse two or three sources | <=1E | ~1.09 |
| IADD3, 2E+1O | 2E+1O | 2.00 |
| IADD3, reuse one even source | 1E+1O | **2.00** |
| HFMA2, reuse one even source | 1E+1O | **2.00** |
| IMAD, reuse one even source | 1E+1O | **2.00** |
| HADD2, 1E+1O | 1E+1O | **2.00** |

The FP32 lighter backend therefore accepts approximately one instruction per
clock when operands permit it.  FFMA's usual two-clock rate is collection of
its 2E+1O sources, not FMA execution occupancy.  In contrast, simple INT,
packed FP16, and IMAD remain at two clocks after reuse reduces their RF demand
to one operand per bank: each has a genuine approximately 0.5-inst/clock
admission limit independent of the collector.

A direct low-RF, two-warp saturation check removes the remaining ambiguity.
`IADD3 Rd, R24, RZ, RZ` uses only one GPR source; two same-subcore streams
raise the victim from a fitted 2.02 clocks/instruction to approximately
3.54--4.0, while a different-subcore stream leaves it near 2.  In contrast,
`FFMA Rd, R24, R27, RZ` has one source in each bank; a same-subcore second
stream leaves the victim at approximately 2.04, identical to its 1.98 solo
slope.  With the normal yield-after-each-instruction schedule, the two FP32
warps fill alternate slots for about one aggregate instruction/clock, whereas
the simple-INT admission domain remains about 0.5 aggregate
instruction/clock.  Thus ordinary three-register FFMA and IADD3 may both
*look* like 0.5 instruction/clock in a single stream, but only FFMA is reduced
to that rate by source collection; their low-RF backend/admission peaks differ
by approximately twofold.

Reuse-bearing schedules require `yield=0` in the legal opex table.  Such a
warp can be favored over a same-subcore sibling, so the reuse result above is
deliberately a single-warp discriminator; reuse/no-reuse two-warp timings are
not used as fair aggregate-throughput evidence.

### Active-lane predicate does not reduce collection cost

`tests/asm_construct/probe_rf_predicate_width.py` repeats the yield-zero test
with the instruction enabled for the whole warp, lane 0 only, the low or high
16 lanes, the even lanes, alternating low/high half warps, or no lanes.  The
fitted GB202 slopes are:

| source layout | full | lane 0 | low 16 | high 16 | even lanes | alternating halves | all off |
|---|---:|---:|---:|---:|---:|---:|---:|
| FADD 2E | 2.000 | 2.000 | 2.000 | 2.000 | 2.000 | 2.000 | 1.090 |
| FADD 1E+1O | 1.090 | 1.090 | 1.090 | 1.090 | 1.090 | 1.090 | 1.090 |
| FFMA 3E | 3.000 | 3.000 | 3.000 | 3.000 | 3.000 | 3.000 | 1.090 |
| FFMA 2E+1O | 2.000 | 2.000 | 2.000 | 2.000 | 2.000 | 2.000 | 1.090 |

Thus any nonempty execution mask incurs the same per-bank operand-collection
cost as a full warp.  Predicate masking does not expose independently usable
half-warp bandwidth, and complementary half-warp instructions do not merge.
This rules out a collector that dynamically turns two nominal 64-byte pieces
into two independently addressed half-warp operands.  It remains consistent
with two fixed lane slices ganged behind one register-row selection, or with
predicate lane gating occurring after a full-width RF read.  The all-off case
shows that the collector can suppress the reads when the execution mask is
empty; its approximately 1.09-clock slope is the instruction front-end floor.

### Cross-warp half-slice discriminator

`tests/asm_construct/probe_rf_slice_overlap.py` removes the possibility that
the single-warp collector simply forbids overlap between its own consecutive
instructions.  Warp 0 and same-subcore warp 4 repeatedly execute
`FADD RZ, R24, R26`, which requires two even-bank source rows but no
architectural write.  Each warp is independently guarded by a full, low-16,
high-16, even-lane, odd-lane, or empty predicate mask.  The contender is long
enough to cover the complete victim interval.

| victim/contender masks | victim clocks/instruction |
|---|---:|
| full / full | 4.30--4.42 |
| low16 / low16 | 4.30--4.42 |
| low16 / high16 | 4.30--4.42 |
| high16 / low16 | 4.30--4.42 |
| even lanes / even lanes | 4.30 |
| even lanes / odd lanes | 4.30 |
| low16 / all off | 2.16--2.20 |
| different-subcore low16 / low16 or high16 | 2.14--2.15 |

Neither contiguous-half nor lane-parity complements recover any bandwidth;
two active same-subcore streams exactly double the one-stream collection
time.  This rejects two 64-byte ports that can accept independent warp/row
addresses according to lane predicates.  At the architectural collector
interface the correct capacity is therefore one independently addressed
warp-wide operand per bank per clock.

Timing cannot distinguish one physical 128-byte port from two physical
64-byte slices that share a row decoder, are always driven in lockstep, or
sit behind a collector that permits only one row address.  Those
implementations are observationally equivalent for ordinary SASS.  Calling
the latter `2R` describes circuit layout, not two architectural read services;
the performance model should call both cases effective `1R`.

## Refined family sharing

The predicated-off matrix locates early family resources independently of RF
reads:

- IADD3, LOP3, and SHF mutually expose the same approximately two-clock simple
  INT admission domain.
- IMAD has its own approximately two-clock admission behavior.  IMAD and FFMA
  do not show a predicate-insensitive cross-conflict even though both are
  called `fmalighter` by the conservative latency grouping.
- HFMA2/HADD2 expose an approximately two-clock packed-FP admission domain.
- A packed-FP16 stream and every tested fmalighter stream (FADD, FFMA, IMAD)
  mutually serialize near four clocks even when the contender is predicated
  off.  This is an additional shared steering/mode/admission boundary, not RF
  collection.
- Simple INT versus FP32, FP16, or IMAD has no such predication-insensitive
  cross-family conflict.  Its active slowdown follows source-bank demand.

The peculiar FP16/fmalighter interaction is better described as a common
ingress or mode-selection constraint than as one arithmetic body: FFMA and
FADD can run at one per clock when their operands are cheap, while HFMA2 and
IMAD retain independent two-clock floors.

`probe_scalar_mode_switch.py` removes RF traffic completely by guarding both
same-subcore streams with false P6.  With the normal yield-after-each-
instruction policy, the victim clocks/instruction are:

| predicated-off victim / contender | victim clocks/instruction |
|---|---:|
| HFMA2 / HFMA2 | ~4.3 |
| HFMA2 / FFMA or FADD | ~4.3 |
| HFMA2 / IMAD | ~4.3 |
| IMAD / IMAD | ~4.3 |
| IMAD / FFMA | ~2.0 |
| IADD3 / FFMA or HFMA2 | ~2.0 |
| FFMA / FFMA | ~2.0 |

This rejects one uniform two-clock `fmalighter` server: IMAD self-serializes
but overlaps a predicated-off FFMA stream, while both IMAD and FFMA collide
with packed FP16.  It instead requires per-family admission plus a cross-link
or common credit specifically on the packed-FP boundary.

Increasing the yield quantum is not a clean mode-switch experiment.  HFMA2 /
FFMA falls from about 4.3 at quantum 1 toward 3.1 at quantum 16, but even the
known-independent IADD3 / FFMA pair rises toward 5.7 because a long yield-zero
FFMA run monopolizes the scheduler.  The change is warp-selection fairness,
not evidence for a datapath mode-switch penalty.  Only the quantum-1 matrix is
used for topology.

## FP64 is one SM-wide 16-cycle pipe

GB202 differs sharply from the measured H20.  DADD and DFMA each asymptote to
roughly 16--19 clocks/instruction in the naked timing harness.  A predicated-
off DADD/DFMA contender on **any** other subcore nearly doubles the victim to
about 35--38 clocks/instruction; subcores 1, 2, and 3 give the same result.
Putting the contender on the victim's own subcore adds only another roughly
2--4 clocks/instruction of local frontend/RF pressure.

The aggregate comparison is suggestive: H20 exposed four subcore-local
roughly 1/64-instruction/clock FP64-lite paths, whereas GB202 exposes one
SM-wide roughly 1/16 path.  Both give about 1/16 FP64 instruction/clock per SM
in aggregate, but GB202 consolidates that throughput behind a common SM-level
arbiter instead of partitioning it four ways.  This is an inference from the
two silicon measurements, not an ISA guarantee.

NCU confirms the physical scope.  One 128-instruction DADD victim plus 128
predicated-off DADDs on subcore 1 reports:

| counter | value |
|---|---:|
| `smsp__inst_executed_pipe_fp64.sum` | 256 |
| `smsp__inst_executed_pipe_fp64_pred_off_all.sum` | 128 |
| `smsp__pipe_fp64_cycles_active.sum` | 4096 |
| `sm__pipe_fp64_cycles_active.sum` | 4096 |

`4096 = 256 * 16`: every instruction, including all-predicated-off ones,
occupies the FP64 pipe for 16 clocks, and the two subcores do not overlap.  If
each subcore had an independent backend, the SM-active interval would be near
`128*16 = 2048` instead.  DADD and DFMA combinations give the same sharing
signature.

Long active IADD3/FFMA/HFMA2 streams do not affect a DADD victim and add only
about 0.7--1.3 clocks/instruction to DFMA, attributable to its larger RF input.
Conversely an active FP64 stream adds only about 0.2--0.45 clocks/instruction
to fast scalar victims on the same subcore and nothing remotely like the
FP64/FP64 serialization.  The narrow FP64 backend is therefore independent
of the scalar execution bodies but fed through the local RF frontend.

## Revised scalar-ALU datapath

The conflict and forwarding results are more consistent with **shared ingress
and egress around several specialized execution lanes** than with either one
unified INT/FP ALU or completely independent INT and FP datapaths:

```text
four subcore schedulers / predicate-insensitive family admission
       |                 |                  |
 INT (~0.5)         IMAD (~0.5)       packed FP16 (~0.5)
       |                 |                  |
       +---------- FP16/fmalighter steering constraint --------+
       |                 |                  |                   |
       +---------- shared local even/odd RF collectors --------+
                       (one warp operand/bank/clock)
                              |
        +---------------------+--------------------+
        |                     |                    |
   simple INT body       FP32 FMA/lighter      packed-FP body
                         (>=1 inst/clock)
        |                     |                    |
        +---------- bypass/result queues ----------+
                              |
                    parity-steered commit merge
                     /                       \
            even RF bank 2R1W          odd RF bank 2R1W

All four subcores also feed one SM-wide FP64 pipe (~16 clocks/instruction),
with operands sourced through their respective local collectors.
```

Confidence and evidence:

- **High:** the RF banks and their write arbiters are subcore-local.  The
  cross-warp experiment in `rf_writeback_conflict.md` delays an even LDG
  completion only with same-subcore even FFMA writes; odd writes and a
  different-subcore contender do not.
- **High:** fixed-pipe bypass delivery precedes architectural RF commit.
  Same-pipe GPR forwarding is usable at roughly two cycles, cross-pipe
  int/fmal forwarding at roughly three, while a scoreboard wait observes a
  later roughly 5.4--5.8-cycle commit.  This accounts for fixed-pipe RF
  collisions being invisible to ordinary RAW consumers.
- **High:** INT and FP have separate execution bodies but share operand
  delivery.  The stable extra cycle for cross-pipe forwarding argues for a
  forwarding mux/crossbar hop.  Conversely, active FFMA/HFMA2 affects IADD3
  much more than its predicated-off control, consistent with active operand
  reads competing for a shared collector/read crossbar rather than the FP op
  occupying the INT arithmetic unit.
- **Medium-high:** packed FP16 and fmalighter encodings share an early
  dispatch/operand-packet
  ingress.  A predicated-off HFMA2 stream strongly affects an FFMA victim,
  before additional active execution matters.  This does not uniquely prove
  whether their arithmetic arrays are physically shared.

The ISA pipe names should be read as hardware-shape classes, not source-level
types: `IMAD`, `IMUL` and integer dot products are assigned to
`fmalighter_pipe`, while simple integer add/logic/shift/compare operations use
`int_pipe`/FXU.

## Nsight Compute cross-check

An initial single Nsight Compute 2025.4.1 pass, retained here as historical raw
data, used kernel replay on `IADD3 <- FFMA`, length 512, same subcore:

| contender | FMA instructions | FMA pipe active | math-pipe throttle |
|---|---:|---:|---:|
| `@P6 FFMA` | 2056 | 7.74% | 12.5 |
| active `FFMA` | 2056 | 12.47% | 325.0 |

The identical FMA instruction count confirms that the predicated-off control
still traverses the counter-visible pipe path.  The active/control difference
looked like backend pressure in this pass, but the throttle magnitude and even
the FMA-active difference did not reproduce reliably in the recheck below;
they are not used as topology evidence.

The throttle metric's reported `.pct` is an aggregation over mostly idle SMSP
instances for this one-CTA kernel and exceeds 100.  Profiler replay also
changes the absolute clock timing, so naked-run slopes and profiler-run clock
values must not be mixed.

### 2026-09-14 recheck: what `math_pipe_throttle` actually covers

NCU 2025.4.1 describes the two relevant metrics as follows:

- `math_pipe_throttle`: warp cycles spent **waiting for an execution pipe to
  be available**;
- `lg_throttle`: warp cycles spent **waiting for a free entry in the LSU
  instruction queue**.

There is also a distinct `mio_throttle`, described as waiting for a free entry
in the MIO instruction queue.  Thus "throttle" is the exposed backpressure
reason; the metric definition does not claim a proactive policy that reserves
capacity for another instruction class.

The derived `average_warp_latency...pct/ratio` proved unstable for this sparse
one-CTA replay.  In particular, the earlier FFMA active `.pct=325` result above
did not reproduce: later runs ranged down to the idle floor and could even
reverse active/control ordering.  Use the raw cumulative
`smsp__warps_issue_stalled_*_throttle.sum` below instead.  Three independent
N=512 runs give:

| stream | active math-stalled warps | predicated-off control |
|---|---:|---:|
| IADD3 | 121 / 63 / 68 | 57 / 60 / 51 |
| FFMA | 1 / 1 / 1 | 1 / 1 / 1 |
| HFMA2 | 66 / 69 / 59 | 58 / 55 / 56 |

Additional single paired runs give FADD active/control = 1/1 and HADD2 =
106/56.  The matching pipe-active counters identify the boundary:

| instruction family | GB202 active counter | math throttle observed? |
|---|---|---|
| IADD3 | `aluheavy` | yes |
| FFMA, FADD | `fmalite` | no in this saturation test |
| HFMA2, HADD2 | both `fmalite` and `fmaheavy` | yes |
| HMMA.16816, QMMA.16832 | `tensor` / `tensor_subpipe_hmma` | **yes, strongly** |
| IMMA.16816 | `tensor` / `tensor_subpipe_imma` | **yes, strongly** |
| MUFU.RCP | MIO, not scalar-math counters | no; `mio_throttle` instead |

For MUFU at N=512, math-stalled warps remain at 1 while MIO-stalled warps are
21539 active and 20884 predicated-off.  Predicated-off IADD3/HFMA2/HADD2 also
retain substantial math throttle and pipe-active counts.  Pipe admission or a
dispatch credit is therefore reserved before (or independently of) the stage
where predication suppresses architectural execution.

### Tensor extension: HMMA, IMMA, and QMMA are math-throttle sources

`tests/asm_construct/probe_tensor_math_throttle.py` runs 512 independent
MMA instructions in warp 0 and selects warp 4 (same subcore) or warp 1
(different subcore) as an active or `@P6` contender.  The opcode is selectable
among `HMMA.16816.F32.BF16`, `IMMA.16816.U8.U8`, and
`QMMA.16832.F32.E4M3.E4M3`; victim and contender may differ.  Forty-seven
four-register destination groups are rotated and never consumed, avoiding the
non-scoreboarded MMA RAW hazard.  (A 48th HMMA group `{R220..R223}` assembles
but faults 715 on this GB202, so the probe deliberately excludes it for every
opcode.)

| placement | HMMA tensor-active sum | math-stalled-warps sum |
|---|---:|---:|
| warp 0 only | 16384 | 15848 |
| warp 0 + warp 1 active | 32768 | 31689 |
| warp 0 + warp 1 `@P6` | 32768 | 31689 |
| warp 0 + warp 4 active | 32768 | 47457 |
| warp 0 + warp 4 `@P6` | 32768 | 46547 |

Two repeat profiles of the same-subcore pair give active 47383/47385 and
control 46989/47035; `tensor_subpipe_hmma_cycles_active.sum` remains exactly
32768 in every case.  The different-subcore result is essentially two solo
values added.  Placing both streams on one subcore adds roughly 14900--15700
stalled-warp events, directly showing that the tensor execution pipe/credit is
subcore-local and is included in `math_pipe_throttle`.

The predicated-off HMMA contender retains its complete tensor-active count and
almost all of the same-subcore throttle.  HMMA therefore reserves the tensor
pipe very early, before the predicate suppresses architectural results; the
small active-minus-control remainder may come from operand/result traffic.
Notably, GB202 reports zero `fmalite` cycles for this HMMA workload even though
the sm90 latency description maps `HMMA_OP` to `FMALITE_Occupancy[2]`.  That
latency resource is a scheduling abstraction, not the physical GB202 pipe
identity.

The same-shape IMMA and QMMA results are:

| opcode / placement | executed subpipe | tensor-active sum | math-stalled-warps sum |
|---|---|---:|---:|
| IMMA, warp 0 only | IMMA | 8192 | 7665 |
| IMMA, warp 0 + warp 1 active/control | IMMA | 16384 | 15330 / 15330 |
| IMMA, warp 0 + warp 4 active/control | IMMA | 16384 | 22903 / 22484 |
| QMMA, warp 0 only | HMMA | 16384 | 15848 |
| QMMA, warp 0 + warp 1 active/control | HMMA | 32768 | 31689 / 31689 |
| QMMA, warp 0 + warp 4 active/control | HMMA | 32768 | 47457 / 46965 |

Each row executes exactly 512 instructions per participating warp.  IMMA is a
distinct, half-duration tensor subpipe in these forms: 16 active cycles per
instruction versus 32 for HMMA/QMMA.  QMMA is counted in the HMMA subpipe and
has the same occupancy and same-subcore contention signature as HMMA.  A mixed
HMMA+QMMA same-subcore pair also gives 32768 HMMA-subpipe cycles and 47434
math-stalled-warp events, directly confirming that the two opcodes share this
reported resource.

The mixed-subpipe experiment exposes a second level of sharing:

| victim + contender | placement | overall tensor-active | HMMA subpipe | IMMA subpipe | math stalled |
|---|---|---:|---:|---:|---:|
| HMMA + IMMA active | different subcores | 24576 | 16384 | 8192 | 23513 |
| HMMA + IMMA `@P6` | different subcores | 24576 | 16384 | 8192 | 23513 |
| HMMA + IMMA active | same subcore | 19528 | 16384 | 8192 | 32813 |
| HMMA + IMMA `@P6` | same subcore | 19563 | 16384 | 8192 | 32794 |
| QMMA + IMMA active | same subcore | 19528 | 16384 | 8192 | 32802 |

On one subcore, the HMMA/QMMA and IMMA subpipes overlap for about 5K cycles
(the overall tensor-active count is smaller than the two subpipe counts
added), so they are not merely aliases for one non-overlappable arithmetic
array.  Nevertheless their same-subcore math throttle is about 9.3K above the
different-subcore baseline.  The most likely boundary is therefore a shared
tensor admission/dispatch queue or credit pool feeding two concurrently active
backend subpipes.  Since the predicated-off contender reproduces both the
subpipe counters and throttle almost exactly, that common resource is acquired
before effective predication.

### Tensor operand and result connection to the RF

`tests/asm_construct/probe_tensor_rf_paths.py` separates the tensor backend
from its register traffic.  Its collection mode holds tensor execution and
four-register result writes constant, while replacing selected A/B/C sources
with RZ.  Against a same-subcore two-even-row `FADD RZ` victim, full GPR
sources add 1.97 clocks/HMMA, 1.85 clocks/QMMA and 1.77 clocks/IMMA relative
to the all-RZ form after subtracting the different-subcore control.  All
different-subcore GPR/RZ pairs are identical.  HMMA A-only, B-only and C-only
sources add approximately 0.71, 0.51 and 0.96 clocks/instruction.  Therefore
all explicit tensor operand groups contend with scalar RF delivery, including
the non-aliased C accumulator source.  On RTX 5090 the visible cost is smaller
than one collection clock per parity-paired register row, but the full-rate
control below shows that backend idle slots, rather than a separate wide RF
port, hide the remaining transactions.

The table above is a reuse=0 characterization.  The dense sm_120 HMMA/QMMA/
IMMA classes have one reuse flag on Rb (schedule mask 2), while Ra and Rc are
not reusable in these classes.  A back-to-back HMMA RMW test proves that the
flag is functional: without reuse the second instruction observes the first
instruction's new Rb value (`0x42a80000` result), while Rb reuse supplies the
cached pre-write value (`0x41800000`).  The reuse/no-reuse cross-warp collector
timings are identical; scalar instructions issue between consecutive HMMAs,
so this is consistent with displacement of the short-lived reuse entry (as
already established for scalar reuse), rather than evidence that the bit is
ineffective.  Thus optimized consecutive tensor code can remove some
B-fragment reads even though the cold-source probe correctly locates the
underlying shared RF path.

An explicit in-place discriminator further constrains Rc.  Two HMMA streams
use A=B=RZ and identical 20-group rotations; one keeps Rc in a disjoint group
at a fixed +96-register displacement, while the other sets `Rc==Rd`.  Across
512 HMMAs their same-subcore scalar-victim minimum/median timings are exactly
the same (8884/8950 clocks), as are the different-subcore controls
(8325/8355.5).  Therefore destination aliasing does not move Rc onto an
observably independent RMW read service.  A physically separate port that
still shares the same row decoder/admission credit remains indistinguishable,
but it provides no additional architectural collection bandwidth.

### Full-rate RTX PRO 6000 control

RTX 5090 limits the tested FP32-accumulating HMMA/QMMA forms to exactly 32
clocks/instruction.  A naked `cycles = slope*N + intercept` run on an RTX PRO
6000 Server Edition gives exactly 16 clocks/instruction for HMMA, QMMA and
IMMA; the corresponding RTX 5090 slopes are 32/32/16.  Nsight Compute was
present remotely but performance-counter access was disabled, so these are
unprofiled `SR_CLOCKLO` slopes rather than NCU estimates.

This changes the operand-contention result in precisely the expected way:

| cold GPR sources versus all RZ | RTX 5090 | RTX PRO 6000 |
|---|---:|---:|
| HMMA ABC | about 1.88--1.97 clocks/inst | 4.43 |
| QMMA ABC | 1.85 | 4.43 |
| IMMA ABC | 1.77 | 1.77 |

On RTX PRO 6000 the HMMA A/B/C components are 1.77/1.32/2.21 clocks per
instruction, close to their 2/1/2 logical register rows per parity bank.  The
full-rate SKU therefore reveals the normal shared RF collector demand that
fits into otherwise idle tensor-backend slots on RTX 5090.  It strengthens,
rather than weakens, the shared scalar/tensor operand-frontend conclusion.

The full-rate control also reproduces the exact equality between separate C
and in-place `Rc==Rd` (4664 minimum, 4667 median in both cases).  Hence the
absence of extra RMW read bandwidth is not caused by the RTX 5090 throttle.
Single-result LDG collision phases are also identical across SKUs; admission
throughput changes, but the latency/phase of one tensor return does not.

### Ampere-style fixed-Ra scheduling does not carry over

Ampere's dense HMMA class exposes both `Ra.reuse` and `Rb.reuse`, matching the
common compiler schedule that holds one A fragment while rotating B and the
C/D accumulator groups.  The dense sm_120 class exposes only `Rb.reuse`.

Two independent tests find no hidden replacement for the removed Ra flag:

- In a back-to-back `Rd==Ra` hazard, RTX 5090 exactly matches the newly written
  Ra reference (`42b00000,42b00000,42c00000,42c00000`), not the old-Ra
  reference (`41800000` repeated).  Full-rate RTX PRO 6000 exposes the latency
  hidden by the 5090 admission floor: gaps 0--5 return the same stable mixed
  fragment (`41800000,41800000,42500000,42500000`), and gap 6 onward returns
  the complete new reference.  It never returns the complete old reference,
  so the early result is streaming non-scoreboarded RAW overlap rather than
  default Ra reuse.
- Holding Ra fixed versus rotating it every HMMA, while B and in-place C/D
  follow identical rotations, gives bit-identical timing distributions.  On
  RTX 5090 the same-subcore minimum/median is 9266/9313 clocks for both; on RTX
  PRO 6000 it is 10466/10471 for both.  Different-subcore controls are also
  identical.  A PRO 6000 single-warp sweep with 3--8 bank-stressing FADDs
  between HMMAs crosses several 16-cycle admission/collection thresholds and
  still reports exactly 0.0000 clocks/block fixed-minus-rotating.

Therefore repeated Ra addresses neither hit a visible coherent tensor
fragment cache nor reduce shared RF collection demand.  The Ampere ordering
may remain harmless for register lifetime or source-code tiling reasons, but
on the tested Blackwell SASS it has no measured execution advantage.

The PRO 6000 gap sweep also adds a scheduling warning independent of reuse:
at full 16-clock HMMA throughput, a tensor result used as the next HMMA's Ra
needs about six additional issue slots in this construction to avoid a
partially updated four-register fragment.  RTX 5090's 32-clock backend limit
hides this RAW window automatically.

### Fixed Rb and the surviving reuse bit

The complementary Blackwell-style schedule rotates Ra and C/D while holding
Rb fixed.  Merely repeating the Rb register address has no automatic effect:
with the reuse mask clear, fixed-Rb and rotating-Rb streams are cycle-for-cycle
identical on both RTX 5090 and full-rate RTX PRO 6000.  This is consistent
with the functional hazard test: reuse is controlled by the explicit Rb bit,
not by an address-tagged implicit cache.

Setting `Rb.reuse` (schedule mask 2) is functionally real but does not improve
the measured issue time of the valid fixed-Rb stream relative to the same
stream with reuse disabled.  On PRO 6000, both curves remain identical
through 3--8 interleaved two-even-row FADDs.  A stricter version
replaces Ra, Rc and Rd with RZ so Rb is the only tensor RF operand and sweeps
0--10 FADDs; reuse-on and reuse-off curves are still identical on both GPUs.
The same-subcore scalar victim also sees the same 10466/10471-clock minimum /
median on PRO 6000 (9266/9313 on RTX 5090), with or without the reuse bit.
(Rotating Rb while setting reuse is only a timing control: it intentionally
consumes the retained previous value and is not numerically equivalent.)

Therefore the bit demonstrably supplies a retained old Rb value, but saving
that read does not move a visible admission or shared-collector bottleneck in
these HMMA streams.  It can still save RF activity/energy, and it is the only
dense-sm_120 source-reuse mechanism software can intentionally exploit.  This
supports mapping the fragment intended for repeated use into physical Rb,
even though the benefit is not a higher naked HMMA issue rate.

Its retirement mode instead holds sources and tensor execution constant and
changes only the destination between four GPRs and RZ.  A phase sweep against
a warmed scoreboarded LDG finds a repeatable +1-clock GPR-result penalty for
both load parities: phases 2/6/10 for HMMA and QMMA, and 3/7/11 for IMMA.  The
four-register result covers both RF parities, so this is evidence that tensor
completion joins the normal parity-bank commit service.  Because tensor RAW
is not covered by the general scoreboards and no test exposes the fixed-pipe
2--3-clock forwarding behavior, the data do not place tensor completion in
the INT/FP bypass/result queue; the conservative model keeps an independent
tensor accumulator-return path until the final commit merge.

The best current interpretation is that `math_pipe_throttle` is an OR/summary
of **per-target execution-pipe credit/backpressure conditions**, not evidence
for one global math FIFO.  On GB202 the tested heavy scalar paths (`aluheavy`
and `fmaheavy`) and both tensor subpipes reach that condition; the tensor
subpipes additionally expose a likely common admission/credit level.
`fmalite` accepts FFMA/FADD at the available scheduler rate and does not in the
present two-stream test.  A physical FIFO may use a high-water mark or reserved
credit, so the signal need not mean every storage bit is occupied, but no
current result shows that its purpose is to preserve issue capacity for
non-math operations.  Likewise, the official LG definition is simply LSU
instruction-queue fullness; shared-memory/MUFU-style traffic has a separately
reported MIO queue, even if those paths share structures farther downstream.

## Heavy/Lite leaf-pipe discrimination

The extended probe adds `MOV`, `PRMT`, `IMAD.HI`, `IMAD.WIDE.U32`,
`IDP.4A.U8.U8`, and `IDP.2A.LO.U16.U8`.  NCU was collected with the four
leaf counters rather than inferred from the latency-table family name.  The
NOP control and multiply cases below use N=256; values are executed
instructions summed over all SMSPs:

| stream | ALU Heavy | Shared-FMA-Heavy / ALU Lite | Shared-FMA-Heavy / FMA Heavy | FMA Lite |
|---|---:|---:|---:|---:|
| NOP/control framework | 73 | 330 | 8 | 0 |
| IMAD.LO | 73 | 330 | 264 | 0 |
| IMAD.HI | 74 | 329 | 264 | 0 |
| IMAD.WIDE.U32 | 74 | 329 | 264 | 0 |
| IDP.4A | 73 | 330 | 264 | 0 |
| IDP.2A | 73 | 330 | 264 | 0 |

Every multiply/dot form therefore contributes exactly N operations to FMA
Heavy irrespective of input element width or low/high/wide result selection.

The first expanded ALU scan made an invalid inference from this harness: each
case performs one warm-up plus one measured launch, while the NCU launch IDs
were initially paired one-to-one with cases.  Moreover, the harness itself
executes hundreds of ALU instructions.  That combination falsely suggested
that PRMT/BMSK dynamically switched between ALU Heavy and Lite.

The replacement
[`probe_scalar_pipe_catalog.py`](../../tests/asm_construct/probe_scalar_pipe_catalog.py)
uses a uniquely named one-warp kernel containing only six MOV32I initializers,
128 target instructions, and EXIT.  All 65 scalar-math mnemonics reproduce
exactly over four launches.  PRMT and BMSK each add 128 ALU-Heavy operations;
neither adds ALU-Lite operations.  The complete corrected partition is in
[`scalar_math_pipe_catalog.md`](scalar_math_pipe_catalog.md).  This is direct
evidence for the official cross-cut hierarchy in which ALU Lite is a subpipe
of the physical Shared FMA Heavy pipe rather than a synonym for ALU Heavy.

Long-stream issue time separates opcode modes inside the same FMA Heavy leaf:

| stream (N=1024) | no reuse | Ra+Rb+Rc reuse |
|---|---:|---:|
| IMAD.LO | 2.077 | 2.075 |
| IMAD.HI | 4.074 | 4.073 |
| IMAD.WIDE.U32 | 4.074 | 4.073 |

The unchanged reuse curves rule out the extra 64-bit addend read as the cause
of the HI/WIDE penalty.  They occupy a downstream portion of FMA Heavy for
two service beats where IMAD.LO needs one.  The counters do not reveal
whether this is multiplier reduction, high-half selection, result formatting,
or return bandwidth, so those alternatives remain intentionally unresolved.

An exploratory same-subcore cross-family pass also showed strong asymmetric
slowdown among MOV, PRMT, and IMAD, while a different-subcore contender did
not.  It is consistent with shared admission/physical-pipe resources, but the
single-warp timing is sensitive to scheduler priority and contender lifetime;
it is not used here to claim that ALU Lite and FMA Heavy cannot overlap.

## Remaining controls before a physical topology claim

- Lock clocks and repeat the few curves whose 128/256/512-point slope is
  visibly frequency-sensitive; all exact integer admission/reuse boundaries
  already reproduce without clock locking.
- Extend the ordered matrix to less common scalar classes (video/conversion,
  compare/minmax and integer dot products) and cluster their two-component
  conflict signatures.
- Vary contender duty cycle and the number of same-subcore warps
  (`{0,4,8,...}`) to identify saturation knees.
- Test whether the FP16/fmalighter mixed-mode penalty depends on opcode runs
  and switching frequency, which would distinguish a mode switch from a
  finite shared admission queue.
- Sweep mixed tensor duty cycles to separate shared admission bandwidth from
  finite shared queue-credit depth.  `UTCHMMA` is deliberately absent here:
  sm_120 has no such instruction, so it is not a valid GB202 extension target.
