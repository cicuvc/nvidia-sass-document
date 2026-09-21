# B200 fixed-pipeline admission and service

Silicon: B200 (sm_100), Modal, 2026-09-20--21.  Primary probes:

- `tests/asm_construct/probe_scalar_admission_depth.py`
- `tests/asm_construct/probe_sm100_scalar_admission_modal.py`
- `tests/asm_construct/probe_sm100_rf_banks_modal.py`
- `tests/asm_construct/probe_sm100_scalar_queue_topology_modal.py`

This note is the authoritative interpretation after correcting the original
sparse-prefix timing method.  Git history preserves the withdrawn
`common-5 + downstream-7` model and the raw exploratory interpretations; they
are intentionally not repeated here.

“Credit”, “window”, and “queue” below normally mean scheduler-visible
outstanding/reservation state.  Timing does not require a literal FIFO row.
Likewise, Heavy/Lite names group opcodes and describe observed resource
interactions; they do not by themselves prove physical execution leaves.

## Current model

| domain | service per subcore | effective outstanding window | status |
|---|---:|---:|---|
| unified ALU | about 0.5 warp inst/cycle | about 12 | established by timing |
| FMA Heavy | about 0.5 | about 12 | established by timing |
| packed FMA (`FFMA2`/`HFMA2` families) | about 0.5 | about 12 | effective shared/coupled domain |
| scalar FMA Lite (`FFMA/FADD/FMUL`) | about 1.0 | no independently visible deep window | queue depth unproven |

The scheduler has an aggregate ceiling of one warp instruction/cycle per
subcore.  ALU and FMA Heavy can progress concurrently at 0.5 each.  Scalar FMA
Lite keeps pace with the scheduler and therefore cannot normally be
overdriven.  Packed FMA requires both FMA sides operationally and serializes
with scalar Lite.

The preferred working model for the FMA side is:

```text
                       approximately 12 packed/Heavy reservations
                                      |
scalar LITE state                     |       PACKED_LOCK state
FFMA/FADD/FMUL, II=1   <---- handoff ---->   FFMA2/HFMA2, II=2
near-direct dispatch                           Heavy + Lite synchronized
no visible deep Lite queue
```

More precisely:

- `LITE`: scalar FMA has a one-cycle initiation interval.
- `PACKED_LOCK`: packed FP32x2 and packed FP16 have a two-cycle service
  interval and are timing-equivalent.
- `LITE -> PACKED_LOCK`: any setup cost is hidden by the packed operation's
  normal two-cycle service; no extra boundary clock is visible.
- `PACKED_LOCK -> LITE`: the first scalar instruction exposes one additional
  handoff/unlock clock, after which scalar issue returns to one/cycle.
- The scalar request does not disappear into a measurable independent Lite
  waiting queue during that handoff.  Backpressure reaches warp eligibility
  and the scheduler may choose another eligible warp despite `yield=0`.

This state machine is the **main inference**, not a transistor-level result.
Timing cannot yet distinguish zero Lite queue entries from a one- or two-entry
skid/collector which cannot accept across the packed handoff.  It also cannot
distinguish one physical packed queue from linked Heavy/Lite reservations or
separate queues serialized by a common backend interlock.  NCU pipe counters
on a usable GB100 system are the next discriminator.

## The dense-issue correction

`SR_CLOCKLO` is an SM-domain elapsed-cycle counter, not a per-warp issue
counter.  Warps 0 and 4 map to the same subcore, whose scheduler can issue at
most one instruction/cycle in aggregate.

The original probe placed four stall-8 NOPs before each producer burst.  New
instructions initially occupied those holes, producing a misleading
`+1 clock/N` curve when N added two instructions.  It did **not** mean that two
instructions entered in one physical cycle.  The corrected probe uses a dense
stall-1 producer prefix:

| N per same-subcore producer | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 11 | 12 | 13+ |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALU + FMA-Heavy, alternating | 80 | 82 | 84 | 86 | 88 | 90 | 91 | 101 | 103 | +2/N |
| scalar FMA Lite | 80 | 82 | 84 | 86 | 88 | 90 | 91 | 101 | 103 | +2/N |
| homogeneous ALU | 80 | 82 | 84 | 86 | 89 | 90 | 91 | 101 | 105 | +4/N |

One N adds two instructions.  Cross-domain ALU/FMA and scalar Lite therefore
run at the scheduler's one-instruction/cycle aggregate ceiling.  Homogeneous
ALU eventually drains at 0.5/cycle and exposes its approximately twelve-entry
window.

Consequences:

- The old “five common credits” result was a sparse-prefix occupancy artifact.
- The old “FMA Lite has five credits/four waiting entries” result is withdrawn.
- The old `12 = common 5 + downstream 7` physical decomposition is withdrawn.
- Mixed-ratio knees derived from that decomposition do not measure queue sizes.
- Approximately twelve effective reservations for genuinely overdriven
  0.5/cycle domains remain supported.

## Front-end controls and the packed two-cycle floor

A solo-warp scan uses 256-instruction CS2R windows.  The RF-clean packed form

```text
FFMA2.F32.F32 RZ, R24, R25, 0f3f800000
```

has two opposite-parity GPR sources plus an immediate, so it needs one RF
collection cycle without reuse.  Measured rates, excluding about 0.08
cycle/instruction of fixed timing overhead, are:

| stream | `stall=1,yield=0` | `stall=2,yield=0` | `stall=1,yield=1` |
|---|---:|---:|---:|
| NOP | 1.00 | 2.00 | 2.00 |
| scalar FFMA | 1.00 | 2.00 | 2.00 |
| FFMA2 | **2.00** | 2.00 | 2.00 |

For larger encoded stalls, all three follow the requested interval.  `DRAIN`
costs roughly 33--35 cycles/instruction.  Reuse masks 0 through 7 do not alter
these rates.

Thus the single-warp 0.5/cycle FFMA2 result is not a generic front-end limit
and not a `yield=1` artifact.  Hardware clamps same-warp packed-FMA issue to a
two-cycle minimum even when the control word requests one.  `yield=1` wastes
the otherwise usable second cycle for NOP/scalar FFMA but adds nothing beyond
FFMA2's existing floor.

The unused slot is domain-specific:

| one-warp repeating stream, `stall=1,yield=0` | aggregate rate |
|---|---:|
| `FFMA2, NOP` | 1.0 inst/cycle |
| `FFMA2, IADD3` | 1.0 inst/cycle |
| `FFMA2, FFMA` | **0.5 inst/cycle** |

The warp can issue an independent instruction after FFMA2, but scalar FMA is
blocked by the packed FMA state.  Two same-subcore warps can alternate packed
requests at one/cycle during the filling region, overdrive the 0.5/cycle
service, and expose the packed outstanding window.  One warp cannot.

`yield=0` is only a keep-current-warp preference while that warp is eligible.
In a two-warp test, a 96-NOP transN background delays another transN warp's
first NOP to about clock 106.  Replacing the background with 96 alternating
`FFMA2,FFMA` instructions lets the target NOP reach the observer at about
clock 28; scalar FFMA targets also make early progress.  The blocked successor
makes the current warp ineligible, so the scheduler selects another eligible
warp instead of wasting the slot.  A packed target remains blocked when the
packed reservation/service resource is already occupied.

## Approximately twelve credits in slow domains

With two same-subcore producer warps, the scheduler initially supplies packed,
ALU, or FMA-Heavy requests at approximately one/cycle while each homogeneous
domain drains at approximately 0.5/cycle.  The corrected dense curves change
to the final four-clock increment per N at about N=12.  Since N adds one
instruction to each producer, this corresponds to roughly twelve effective
outstanding/reservation entries per subcore, including work in service.

This result applies to:

- unified ALU (`IADD3/LOP3/SHF` and `IADD/MOV/ISETP` groups);
- FMA Heavy (`IMAD/IMUL/FSWZADD` representatives);
- packed FP32x2 (`FFMA2/FADD2/FMUL2`);
- packed FP16 (`HFMA2/HADD2/HMUL2`).

Predicated-off packed instructions retain the same knee and final slope.
Admission/reservation therefore occurs before predicate cancellation; the
result is not caused by arithmetic result writeback.

These equal effective depths do not prove four identical physical FIFOs.
The cross-family and ordered-phase results below determine which domains can
progress independently.

## B200 has one unified ALU backend

Dense pure ALU-Heavy, pure ALU-Lite, and alternating Heavy/Lite curves are
point-for-point identical.  Once either opcode group fills the approximately
twelve-entry state, a suffix from the other group is service-limited
immediately:

```text
ALU Heavy -> ALU Lite:  0,4,8,12,... clocks
ALU Lite  -> ALU Heavy: 0,4,8,12,... clocks
```

Either ALU group alternated with FMA Heavy instead reaches the scheduler's
aggregate one-instruction/cycle ceiling.  Thus “ALU Heavy” and “ALU Lite” are
only useful opcode-set names on B200; there is one observable 0.5/cycle ALU
backend/reservation domain.

The GB100 Nsight Compute metric catalog agrees with this interpretation.  It
exposes only:

```text
smsp__inst_executed_pipe_alu
smsp__pipe_alu_cycles_active
```

GB202 additionally exposes separate `pipe_aluheavy` and
`fmaheavy_subpipe_alulite` counters.  Timing cannot rule out redundant B200
units hidden behind one dispatcher, but they would have no independently
observable throughput.

## FMA Heavy, scalar Lite, and packed coupling

FMA Heavy has 0.5/cycle service and approximately twelve effective credits.
Scalar FFMA has 1/cycle service and bypasses occupied Heavy state:

```text
saturated FMA-Heavy prefix -> FMA-Heavy suffix: 0,4,8,... clocks
saturated FMA-Heavy prefix -> scalar FFMA suffix: 0,2,4,... clocks
```

Here each suffix count adds one instruction to each of two producers.  An FFMA
prefix likewise does not consume the Heavy filling window.  Scalar Lite and
ordinary Heavy therefore have independent execution progress in the absence
of packed instructions.

Packed instructions couple the two sides.  Reciprocal dense phases
(`FADD2 <-> HFMA2`, `FMA-Heavy <-> HFMA2`) are point-for-point identical after
saturation, and a packed prefix prevents scalar Lite from using a nominal
second FMA slot in the same warp.  Plausible physical encodings include one
packed token with a `Heavy|Lite` backend mask, linked Heavy/Lite tokens, or a
separate packed queue feeding a synchronized backend.

### FFMA2 and HFMA2 are one effective packed state

The RF-clean FFMA2 form above and RZ-source HFMA2 give point-for-point
identical pure and alternating curves for one producer and two same-subcore
producers.  Both sustain 0.5/cycle, expose the same N≈12 boundary, and have the
same final drain slope.

Ordered phases have no format-switch penalty:

| direction | one producer, B=0,1,2,... | two producers, B=0,1,2,... |
|---|---|---|
| FFMA2 -> HFMA2 | `0,2,4,...` | `0,4,8,...` |
| HFMA2 -> FFMA2 | `0,2,4,...` | `0,4,8,...` |

The static names differ (`fmalighter_pipe` versus `fp16_pipe`), but timing sees
one persistent `PACKED_LOCK` state.  This does not prove one physical FIFO.

### Packed/scalar transition direction

With a no-reuse packed operation and RZ-source scalar FFMA, a one-warp ordered
phase after a 32-instruction prefix gives:

| prefix -> suffix | extra clocks for B=0,1,2,3,4,... |
|---|---|
| scalar `FFMA -> FFMA2` | `0,2,4,6,8,...` |
| `FFMA2 ->` scalar FFMA | `0,2,3,4,5,...` |

The first packed instruction after scalar work pays only its normal two-cycle
service.  The first scalar instruction after packed work costs two cycles;
later scalar instructions return to one/cycle.  A repeating block with one
packed instruction and k scalar instructions costs approximately `k+3`
cycles, rather than the `k+2` non-transition service sum.

An equivalent externally visible schedule is:

```text
packed service                    2 cycles
PACKED_LOCK -> LITE handoff       1 cycle
scalar service                    1 cycle
```

The timing does not locate the handoff physically.  It could be backend-mode
state, dispatch eligibility, or an operand-collector ownership transition.
The important observation is that the handoff clock is not hidden inside the
packed instruction's two-cycle service when a scalar consumer follows.

The same directionality holds for packed FP16: after HFMA2, the first scalar
FFMA costs two cycles and subsequent FFMAs cost one each.  Both operations use
RZ sources in that control, excluding RF/reuse effects.

### Why packed FMA does not expose a Lite queue

Two same-subcore producers each issue an A-instruction prefix of RF-clean
FFMA2 and then B scalar FFMAs.  Once `A >= 12`, all tested prefix lengths give:

| B per producer | 0 | 1 | 2 | 3 | 4 | ... | 32 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| extra clocks | 0 | 4 | 6 | 8 | 10 | ... | 66 |

There is no initial flat interval in which scalar requests disappear into an
independent Lite queue behind the packed backlog.  Packed work blocks at or
upstream of the point where such a queue would accept.  Therefore packed FMA
is not a downstream-only blocker suitable for measuring a hidden Lite queue.

This favors near-direct Lite dispatch, but does not prove zero physical slots:
a Lite queue behind the shared packed/scalar gate would be unreachable in this
experiment.

## Register collection and reservation placement

B200 GPR collection follows the parity-bank model:

```text
bank = register_id & 1
read_cycles = max(even_rows, odd_rows)
```

Each bank supplies one warp-wide 32-bit row per cycle.  RZ, immediate,
uniform, and valid reuse-hit operands do not request a row.  Changing a source
register ID invalidates that operand's reuse hit, and switching warps
unconditionally invalidates the reuse cache.

For scalar FFMA:

- E+O collection takes one cycle;
- 2E+1O takes two cycles;
- 3E takes three cycles;
- the execution floor is one cycle.

RF-bound scalar FFMA throttles almost immediately rather than exposing a deep
pre-RF Lite queue.  This is additional evidence for direct or very shallow
Lite dispatch.

For HFMA2, the backend floor is already two cycles.  Up to two RF rows per bank
are hidden by that floor; three same-parity uncached sources increase the rate
to three cycles/instruction.  Reusing any one of those sources restores the
two-cycle floor.

For ALU and FMA Heavy, dense two-producer parity sweeps retain the N≈12
boundary even when RF collection becomes the slower 2- or 3-cycle stage.  The
effective reservations are therefore allocated before all source rows have
been collected and remain occupied during collection.  They may be queue
entries, operand-collector slots, or distributed valid state; they are not a
pure post-RF operand-data FIFO.

## What is established and what awaits NCU

Established by timing:

- one aggregate scheduler issue slot/cycle/subcore;
- one observable B200 ALU domain at 0.5/cycle with about twelve credits;
- FMA Heavy at 0.5/cycle with about twelve credits;
- scalar FMA Lite at 1/cycle, independently progressing past ordinary Heavy;
- packed FFMA2/HFMA2 at 0.5/cycle with one effective approximately twelve-
  credit state and a Heavy+Lite execution/dispatch interlock;
- no FFMA2/HFMA2 format-switch penalty;
- a visible packed-to-scalar handoff clock and no measurable Lite waiting
  window which absorbs it;
- opportunistic warp switching overrides `yield=0` when the current
  instruction is structurally ineligible.

Still open:

- whether scalar Lite has zero queue entries or a tiny/inaccessible skid;
- whether the packed window is a literal FIFO, distributed reservation state,
  or linked tokens in multiple structures;
- whether FFMA2 increments GB100 Heavy, Lite, or both hardware counters;
- the exact physical location of `PACKED_LOCK -> LITE` handoff state.

The GB100 NCU catalog contains separate FMA metrics:

```text
smsp__inst_executed_pipe_fma
smsp__inst_executed_pipe_fma_type_fp16
smsp__inst_executed_pipe_fmaheavy
smsp__inst_executed_pipe_fmalite
smsp__pipe_fma_cycles_active
smsp__pipe_fmaheavy_cycles_active
smsp__pipe_fmalite_cycles_active
```

Modal does not permit usable NCU collection.  A B200 system with working NCU
is required to resolve first-level attribution; until then `PACKED_LOCK` is an
effective timing model rather than a claimed physical block diagram.
