# B200 fixed-pipeline admission windows

Silicon: B200 (sm_100), Modal, 2026-09-20--21.  Probes:

- `tests/asm_construct/probe_scalar_admission_depth.py`
- `tests/asm_construct/probe_sm100_scalar_admission_modal.py`

The target burst uses an architecturally-false predicate, `RZ` destination,
`yield=0`, and operand reuse.  Active representative controls produce the
same curves.  No target result is consumed.  As elsewhere, “credit” below is
an effective scheduler-visible admission credit and does not require a literal
FIFO cell.

The Heavy/Lite labels below were initially borrowed from the GB202 Blackwell
counter hierarchy to group opcodes.  They must not be assumed to name B200
physical leaves: the GB100 NCU catalog and the B200 timing results below show
one unified ALU pipe.  Representatives used here are:

| leaf | measured representatives |
|---|---|
| ALU Heavy | IADD3, LOP3, SHF |
| ALU Lite | IADD, MOV, ISETP |
| FMA Heavy | IMAD.LO, IMUL, FSWZADD.NDV |
| FMA Lite | FFMA, FADD, FMUL |
| packed FP16 using FMA Heavy + FMA Lite | HFMA2, HADD2, HMUL2 |

## 2026-09-21 dense-issue correction (authoritative)

`SR_CLOCKLO` is an SM-domain elapsed-cycle counter, not a per-warp issue
counter.  Warps 0/4 use the established same-subcore/scheduler mapping, whose
aggregate issue ceiling is one warp instruction/cycle.  The original
producer-critical-path control used four `NOP` instructions with stall 8.
Those NOPs leave scheduler holes: increasing `N` adds one target instruction
to each producer, and the pair can initially occupy pre-existing holes while
extending the final barrier span by only one clock.  That `+1 clock/N` is not
two instructions enqueued in one physical cycle.

A corrected control uses 32 producer NOPs at stall 1, keeping the scheduler
issue slots dense and making the producer path critical.  The medians are:

| N per producer | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 11 | 12 | 13+ |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALU-Heavy + FMA-Heavy 1:1 | 80 | 82 | 84 | 86 | 88 | 90 | 91 | 101 | 103 | +2/N |
| FMA Lite | 80 | 82 | 84 | 86 | 88 | 90 | 91 | 101 | 103 | +2/N |
| ALU Heavy homogeneous | 80 | 82 | 84 | 86 | 89 | 90 | 91 | 101 | 105 | +4/N |

Thus the scheduler supplies at most one aggregate instruction/cycle:

- Cross-domain ALU/FMA and FMA-Lite service keep pace with issue, so this
  experiment cannot fill or size an upstream/common queue.  The former
  “common-5” and “FMA-Lite depth 5” interpretations are withdrawn.
- A homogeneous 0.5/cycle domain still changes from the +2-clock scheduler
  slope to the +4-clock service slope at about `N=12`, retaining evidence for
  about twelve effective outstanding/reservation credits per slow domain.
- The decomposition `12 = common 5 + downstream 7` is not established.

The RF placement control was repeated with the dense prefix.  `2E+1O`
no-reuse streams retain the N≈12 change to +4 clocks/count.  `3E` no-reuse
streams enter their final +6 clocks/count at N≈11 after an intermediate RF-
limited region.  This still requires reservation state before/during operand
collection and rules out a purely post-RF queue, but no longer assigns exactly
seven of the approximately twelve credits to that location.

The remaining sections preserve the raw historical experiments.  Any
interpretation in them that depends on a literal five-credit common queue, a
five-credit FMA-Lite queue, or `5+7` physical decomposition is superseded by
this correction.  Long-run service-rate and same-domain/cross-domain
compatibility results remain useful.

### Attempt to expose FMA Lite by making it RF-bound

FFMA was repeated with explicit no-reuse scheduling and either three
same-parity sources (`R24,R26,R28`) or a 2-even+1-odd split
(`R24,R25,R26`).  The same two-producer dense control gives:

| FFMA operands | steady increment per N | first sustained RF-limited region |
|---|---:|---:|
| ordinary/RZ | about +2 clocks | none through N=32 |
| 2-even + 1-odd, no reuse | about +4 clocks | approximately N=2 |
| 3-even, no reuse | about +6 clocks | approximately N=2 |

Here one N adds one instruction to each of the two same-scheduler producer
warps.  The +4/+6 slopes are therefore the expected 2-/3-cycle RF collection
floors.  Unlike ALU-Heavy and FMA-Heavy, RF-bound FFMA does **not** retain a
scheduler-rate prefix out to N≈12.  RF pressure consequently cannot fill and
measure a deep FMA-Lite queue: it throttles FFMA before such storage becomes
occupied.  The data are consistent with only a very shallow FFMA RF-collection
front end, or with FMA-Lite admission occurring after operand collection; they
do not distinguish those implementations.

A second attempt used packed FP16 as a downstream resource competitor without
making FFMA's own RF reads slow.  An alternating `FFMA/HFMA2` stream changes
from the scheduler slope to about +4 clocks/N at N≈12.  However, ordered
phases show that this boundary follows the slow packed requests: a packed
prefix of 12 or 16 delays the first following FFMA, after which additional
FFMAs again cost about +2 clocks/N.  Conversely an FFMA prefix does not move
the packed suffix's eventual +4-clock slope.  This experiment alone exposes
approximately 12 effective reservations in the multi-leaf FMA path, but
cannot assign a standalone capacity to FMA Lite.  The packed-FP32x2 experiment
below supplies that missing discriminator.

### Packed FP32x2 supplies the missing issue pressure

`FFMA2`, `FADD2`, and `FMUL2` each encode two FP32 lanes in one scheduler
instruction and run on `fmalighter_pipe`.  Their `INST_TYPE_COUPLED_MATH`
classification means fixed-latency math as opposed to decoupled, variable-
latency MIO; the name by itself does **not** imply use of multiple math leaves.
Repeating the dense two-producer experiment while enabling operand reuse gives:

| instruction | low-N increment | sustained high-N increment | knee |
|---|---:|---:|---:|
| scalar FFMA | about +2 clocks/N | about +2 | none through N=32 |
| FADD2 | about +2 | +4 | N=12 |
| FMUL2 | about +2 | +4 | N=12 |
| FFMA2 | about +3 | +4 | N≈11 |

One N again adds two instructions, one to each same-scheduler warp.  The x2
forms can therefore enter at the scheduler's aggregate 1 inst/cycle but drain
at approximately 0.5 inst/cycle.  During the issue of 2N instructions the
backlog grows by approximately N entries, so the N≈12 knee directly exposes
an effective **approximately 12-entry packed-FP32x2 outstanding window per
subcore**.  Static classification places these instructions on
`fmalighter_pipe`, but timing alone cannot decide whether this window is the
ordinary Lite queue or additional masked reservation state.  FADD2/FMUL2 are
the cleanest representatives; FFMA2's three packed sources add a visible
operand-collection cost before the final pipe-limited region.

With only one producer warp, all three x2 forms remain at approximately +2
clocks/instruction through N=40 and never fill the queue.  A single warp's
back-to-back issue cadence is already about 0.5 instruction/cycle; two eligible
same-scheduler warps are required to reach the 1/cycle aggregate input and
create backlog.

Predicated-off x2 instructions show the same N≈12 knee and +4 final slope,
whereas predicated-off scalar FFMA remains at +2.  The immediate cause is thus
fixed-pipeline admission/dispatch applied before predicate cancellation, not
the execution of twice as many floating-point arithmetic operations.

Ordered marker tests locate the coupling but do not identify a single physical
FIFO.  After a saturated FADD2 prefix, the first scalar FFMA marker costs four
clocks rather than two, then further FFMAs return to +2 each.  FMA-Heavy IMAD
markers remain at +4 each, while ALU-Heavy IADD3 markers remain at +2 and are
unaffected.

An asymmetric test establishes that x2 admission reserves or gates the Lite
side, but not that its twelve-entry boundary belongs to Lite alone.  Warp 0
continuously issues 256 or 512 all-reuse FFMA2/FADD2 instructions while same-
scheduler warps 4 and 8 issue scalar FFMA; a clean-subcore observer waits only
for the FFMA warps.  Even one target FFMA waits approximately the complete
background duration (about 470 clocks for 256 and 990 clocks for 512).  Active
and predicated-off x2 backgrounds behave identically.  An FMA-Heavy background,
in contrast, does not delay the first FFMA at all.

Reciprocal dense phases locate the other half.  `FADD2 -> HFMA2`,
`FMA-Heavy -> HFMA2`, `HFMA2 -> FADD2`, and `HFMA2 -> FMA-Heavy` are point-for-
point identical; once a prefix reaches N=11, every suffix starts immediately
at `0,4,8,12,...`.  Packed FP32x2 and packed FP16 therefore cannot dispatch
independently of either FMA backend.  This proves a Heavy+Lite execution/
dispatch interlock, but does **not** prove that the instruction is inserted
into both admission queues.  Plausible implementations include one
`fmalighter_pipe` request with a `Heavy|Lite` backend mask, one separate packed
request with that mask, or two linked physical queue tokens.  Pipe counters on
real GB100 hardware are needed to distinguish the first-level attribution.

### Packed FP16 interlocks Heavy and Lite service

Dense-issue retesting places `HFMA2`/`HADD2`/`HMUL2` more precisely.  A pure
HFMA2 stream has the same N≈12 knee and +4-clock final increment as the other
0.5-inst/cycle domains.  Alternating FMA-Heavy/HFMA2 is point-for-point
identical to pure HFMA2.  Ordered phases are symmetric: after either a
saturated HFMA2 or FMA-Heavy prefix, every suffix instruction of the other
class immediately costs +4 clocks/N.  Thus packed FP16 and FMA Heavy share the
same effective reservation/service domain rather than owning independent
queues of coincidentally equal depth.

The other pairings separate admission from execution:

- Alternating ALU-Heavy/HFMA2 remains at the scheduler-limited +2 clocks/N
  through N=32, and a saturated HFMA2 prefix does not delay ALU-Heavy markers.
  The ALU reservation/execution domain is independent.
- Alternating scalar FFMA/HFMA2 eventually has the same +4-clock drain slope
  and N≈12 boundary as packed FP16.  After a saturated HFMA2 prefix, however,
  only the first following FFMA costs +4; subsequent FFMAs return to +2 each.
  Packed FP16 therefore consumes the Lite execution side, while scalar FFMA
  can accumulate in distinct ready/reservation state once it crosses the
  initial shared boundary.

An asymmetric HFMA2 background also prevents even one same-scheduler scalar
FFMA from passing until the background ends.  The smallest current model is
therefore a packed-FP16 instruction whose dispatch/service locks both FMA
backends.  Whether it consumes entries in both scalar admission queues, lives
in the static `fp16_pipe` queue with a two-backend mask, or is represented by
linked tokens is not determined by timing.

### Scalar FMA Lite admission is independent of FMA Heavy

A dense ordered test fills FMA Heavy and then appends scalar FFMA.  Once the
Heavy prefix reaches its N≈11--12 boundary, another Heavy suffix is
service-limited immediately (`0,4,8,...` clocks for suffix counts 0,1,2,...).
The FFMA suffix instead remains exactly `0,2,4,...` from its first instruction,
identical to the independent ALU-Heavy control.  Reversing the order also
preserves FMA Heavy's complete filling window: an FFMA prefix does not consume
Heavy credits.

Thus scalar FMA Lite has an operationally independent admission/ready-credit
domain; it does not share one exhaustible FIFO with scalar FMA Heavy.  A physical
implementation may still use one tagged or statically partitioned entry array,
but it must have independent availability accounting and selection.  Packed
FP16/FP32x2 operations can interlock both execution sides without implying
shared scalar Heavy/Lite admission credits.  Scalar FFMA
alone cannot expose the Lite depth because its 1-inst/cycle service matches
the scheduler ceiling.  Packed FP32x2 supplies a 0.5-inst/cycle drain, but its
Heavy interlock means the N≈12 boundary is not a unique measurement of scalar-
Lite capacity.

### B200 has one unified ALU backend, not observable Heavy/Lite leaves

The dense ordered test is symmetric and exact.  Once either an ALU-Heavy or
ALU-Lite prefix reaches N=11--12, a suffix from the other leaf is immediately
service-limited:

```text
ALU Heavy -> ALU Lite:  0,4,8,12,... clocks
ALU Lite  -> ALU Heavy: 0,4,8,12,... clocks
```

These curves are identical to a same-leaf suffix.  In contrast, either ALU
prefix followed by FMA Heavy retains the fresh scheduler-rate window
`0,2,4,6,...`.  Independent twelve-entry Heavy and Lite queues would allow the
opposite ALU leaf to admit at the scheduler rate while the prefix drains; the
observed immediate +4 slope rules that organization out.

The homogeneous ALU-Heavy, homogeneous ALU-Lite, and alternating Heavy/Lite
dense curves are moreover point-for-point identical through N=32.  All change
at N≈12 to the same aggregate 0.5-inst/cycle service slope.  Either ALU group
alternated with FMA Heavy instead sustains the scheduler's aggregate
1-inst/cycle ceiling.  There is no measured concurrent Heavy+Lite service.

The metric catalogs independently support the simpler interpretation.  With
Nsight Compute 2026.3 queried by chip, GB100 exposes only:

```text
smsp__inst_executed_pipe_alu
smsp__pipe_alu_cycles_active
```

GB202 additionally exposes `pipe_aluheavy` and
`fmaheavy_subpipe_alulite` instruction and active-cycle counters.  The static
sm100 latency description likewise places both opcode groups in one
`int_pipe` set.

B200 should therefore be modeled as one approximately twelve-credit ALU
admission/reservation domain feeding one effective 0.5-inst/cycle ALU backend.
“ALU Heavy” and “ALU Lite” remain useful opcode-set labels for comparison with
GB202, but there is no evidence that they correspond to distinct B200 physical
backends.  Timing alone could not rule out redundant internal units hidden
behind a single shared half-rate dispatcher, but such units would have no
observable independent throughput or availability.

## Measurement correction for INT

On sm_100, `CS2R` itself is statically assigned to `int_pipe`.  A naive
`CS2R; IADD3*N; CS2R` sequence therefore times retirement/service of the
entire INT burst: the ending timestamp cannot pass the same pipe.  Its
`5+2N` curve is valid INT throughput evidence but not queue-depth evidence.

The corrected construction puts the producer on warp 0 and the observer on
a different subcore.  After a common start barrier, the producer issues its
burst and reaches a counted `BAR.SYNC`; the observer timestamps the barrier
release.  `BAR` is on `mio_pipe`, and the observer's ending `CS2R` uses a clean
subcore, so producer progress after the last admitted INT no longer waits for
the producer's INT service queue to drain.  Four stall-8 producer NOPs make
the producer, rather than observer control flow, the critical path.  The same
method is also an independent control for FP.

## Why one producer underfills the queues

The one-producer barrier spans are exact at their medians:

| family / representatives | T(0) | T(1) | T(2) | later increment |
|---|---:|---:|---:|---:|
| ALU Heavy: IADD3, LOP3, SHF | 41 | 42 | 44 | +2/instruction |
| ALU Lite: IADD, MOV, ISETP | 41 | 42 | 44 | +2/instruction |
| FMA Heavy: IMAD.LO, IMUL, FSWZADD | 41 | 42 | 44 | +2/instruction |
| packed FP16: HFMA2, HADD2, HMUL2 | 41 | 42 | 44 | +2/instruction |
| FMA Lite: FFMA, FADD, FMUL | 41 | 42 | 43 | +1/instruction |

These are service rates, not queue depths.  One warp supplies the first four
rows at only about one instruction per two clocks, equal to their service
rate.  It supplies FMA Lite at one per clock, again equal to service.  A
single producer can therefore never accumulate backlog.  The earlier
interpretation of these curves as one active credit and zero waiting entries
was wrong.

## Same-subcore two-producer depth

Warps 0 and 4 share a subcore and issue identical N-instruction bursts.  Warp
1, on another subcore, timestamps their counted-barrier release.  The two
producers can initially admit about one instruction/cycle in aggregate, twice
the 0.5-instruction/cycle service rate.  Every tested ALU Heavy, ALU Lite, FMA
Heavy, and packed-FP16 representative gives the same median curve:

| N per producer | 0 | 1 | 2 | 3 | 4 | 8 | 12 | 13 | 14 | 15 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| common clocks | 47 | 48 | 50 | 52 | 56 | 64 | 72 | 76 | 80 | 84 |

There are scheduler-phase steps of 1--4 clocks in the filling region, but
from N=13 onward every added N costs exactly four clocks: two new operations
drain at 0.5 instruction/cycle.  At N=12, 24 operations have been admitted in
about 25 incremental clocks while about 12 have drained.  The knee therefore
corresponds to approximately **12 outstanding credits/subcore**, including
the operation in service, or roughly eleven waiting operations.

FMA Lite has a distinct and exact shallower curve:

| N per producer | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 and later |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| common clocks | 47 | 48 | 49 | 50 | 51 | 52 | 54 | +2/N |

Each increment through N=5 admits two FMA-Lite operations in one clock while
one operation drains, accumulating five outstanding operations.  At N=6 the
curve becomes service-limited.  Thus FFMA/FADD/FMUL expose **5 effective
outstanding credits/subcore**, including service, or about four waiting
operations.

Different-subcore producer pairs preserve the one-producer slopes (+2/N for
the four 0.5/cycle families and +1/N for FMA Lite), confirming that these
capacities and service limits are subcore-local rather than SM-wide.

## Blocking controls for the one-cycle FMA-Lite leaf

An active four-beat `IMAD.HI` prefix makes the common scalar-math entrance
temporarily unavailable.  Four prefixes alone take 18 clocks.  Appending a
predicated-off target gives:

| appended target count | 0 | 1 | 2 | 3 | 4 |
|---:|---:|---:|---:|---:|---:|
| FFMA | 18 | 21 | 22 | 23 | 24 |
| FADD | 18 | 21 | 22 | 23 | 24 |
| FMUL | 18 | 21 | 22 | 23 | 24 |

The first FMA-Lite target pays three clocks before the entrance becomes
available; once admitted, the FMA-Lite leaf resumes its +1-clock cadence.  One
active HFMA2 prefix gives prefix-only 6 clocks, then 8 for one FFMA and +1
thereafter.

The two-producer result shows why this must not be read as “no FMA-Lite queue.”
The cross-family blocker holds a shared upstream scalar-math entrance, so the
following FMA-Lite operation cannot reach its five-credit leaf queue early.
Two synchronized FMA-Lite producers bypass that ambiguity and fill the
leaf-local credits directly.

## Mixed-leaf substitution

Homogeneous depths do not distinguish one shared queue from several queues
with coincidentally equal capacities.  To make that distinction, both
same-subcore producers were changed to issue an alternating pair of leaf
representatives.  `N` remains the number of instructions per producer, so an
even-length burst contains equal numbers from the two leaves.

All ten unordered leaf pairs give the following effective-depth matrix.  The
diagonal is the homogeneous result for reference:

| | ALU Heavy | ALU Lite | FMA Heavy | FMA Lite | packed FP16 |
|---|---:|---:|---:|---:|---:|
| **ALU Heavy** | ~12 | **~12** | **5** | **5** | **5** |
| **ALU Lite** | | ~12 | **5** | **5** | **5** |
| **FMA Heavy** | | | ~12 | **5** | **~12** |
| **FMA Lite** | | | | 5 | **~12*** |
| **packed FP16** | | | | | ~12 |

`*` FMA Lite + FP16 has a clear deep boundary but extra phase structure near
it.  The three deep off-diagonal pairs have approximately +4 clocks/N after
the boundary; every other pair has the exact five-credit curve and +2
clocks/N.

The exact five-credit curve is `47,48,49,50,51,52,54,56,...` for
`N=0,1,...`: through N=5 the two producers admit two operations while one
drains in one clock, then the pair becomes service-limited.  It occurs for
all ALU/FMA cross-pairs, and also for FMA Heavy + FMA Lite.  ALU Heavy + ALU
Lite and FMA Heavy + FP16 instead reproduce the homogeneous deep curve
`47,48,50,52,56,...,72,76,80,...`, including its N=12 boundary.  FMA Lite +
FP16 also retains the deep boundary, though N=14--17 has extra
scheduler/execution-phase structure (`76,82,86,90,91` from N=13).

Architecturally-false targets reproduce these boundaries exactly, excluding
result data and register writeback as their cause.  With the two producers
placed on different subcores, all four representative mixes are linear
through N=16 and show no boundary: ALU-Heavy + ALU-Lite, FMA-Heavy + FP16,
and FMA-Lite + FP16 are +2 clocks/N, while ALU-Heavy + FMA-Heavy is +1.
The five- and twelve-credit resources are consequently subcore-local.

### Ratio sweep: shallow mixed behavior is occupancy, not a fixed mode throttle

A fixed “both ALU and FMA are present” throttle could imitate the 1:1
five-credit curve without a literal full queue.  To distinguish it, the same
two producers issue periodic ALU-Heavy:FMA-Heavy patterns at ratios 1:1, 2:1,
3:1, and 7:1, plus all reversed ratios.  With active RZ operands:

| ratio | approximate onset of final majority-domain-limited pattern |
|---|---:|
| 1:1 | `N=6` |
| 2:1 / 1:2 | `N≈18--20` |
| 3:1 / 1:3 | `N≈18--19` |
| 7:1 / 1:7 | `N≈14--15` |
| homogeneous | `N=13` |

These are not all measurements of one queue's depth.  The 1:1 `N=6` boundary
is the shallow common window becoming the limiter; at exactly 1:1 no
downstream domain accumulates.  The later boundaries in imbalanced streams are
a second transition: after the common window is active, the majority domain's
additional state slowly accumulates until it too becomes full.  Thus the
horizontal burst length at that second transition is a fill *time*, not a slot
count.

The long-run increment pattern follows the majority domain: 1:1 is a
constant +2 clocks/count, 2:1 repeats approximately `+4,+2,+2`, and increasingly
biased streams contain increasingly many +4 increments.  This is the expected
occupancy behavior.  At 1:1, the one-instruction/cycle downstream switch feeds
each 0.5/cycle backend at exactly its drain rate, so only the shallow common
window accumulates.  With a slight imbalance, the majority-domain state fills
only at the small excess of arrival rate over 0.5/cycle, moving the knee much
farther out.  At extreme imbalance it approaches the homogeneous deep curve.

More explicitly, if the majority fraction is `p`, its state grows after the
common switch at approximately `p - 0.5` entries/cycle.  Filling `K≈7` extra
credits therefore takes roughly `K/(p-0.5)` dispatch cycles.  This diverges as
`p→0.5`, while at exactly `p=0.5` that second knee does not exist at all and the
only visible knee is common-5.  This change of limiting resource explains the
apparently non-monotonic `5 → 20 → 18 → 14 → 13` sequence.

Thus a fixed five-token throttle triggered merely by mixed instruction classes
is ruled out.  A completion-refilled, per-domain token mechanism could still
reproduce the curves, but such tokens are operationally the same admission
credits/reservation occupancy modeled here; timing alone cannot require the
credits to be literal FIFO rows.

### The extra credits are allocated before RF collection completes

The RF-bank result supplies a placement test.  For the same active IADD3 and
IMAD opcodes, destination RZ, and explicitly no reuse, only source parity is
changed:

| source rows | RF collection floor | final two-producer increment | knee |
|---|---:|---:|---:|
| 2 even + 1 odd | 2 cycles/instruction | +4 clocks/count | about `N=12--13` |
| 3 even | 3 cycles/instruction | +6 clocks/count | about `N=12--13` |

ALU-Heavy and FMA-Heavy curves match point-for-point in each row.  In the
three-even case the RF collector supplies at most about 1/3 instruction/cycle,
slower than the leaf executor's approximately 1/2 instruction/cycle.  A queue
allocated only *after* RF read completion therefore could not accumulate: its
input would be slower than its drain, and only the shallow common window would
remain visible.  Instead the same deep boundary survives while only the final
slope changes from +4 to +6.

Consequently the extra approximately seven credits are acquired before all
source rows have been read and remain occupied during operand collection.  The
data do not distinguish a dedicated pre-RF instruction/reservation FIFO from
seven operand-collector slots holding register IDs and progressively latched
operands.  They rule out interpreting all seven as a pure post-RF operand-data
queue; some later pipeline/result staging may still be covered by the lifetime
of the same credits.

The minimum *effective-domain* model consistent with the pair matrix is:

```text
common cross-domain fixed-math window: ~5 total outstanding

same-domain modes which expose a deeper ~12-total window:
    ALU mode           = ALU Heavy + ALU Lite
    FMA-Heavy mode     = FMA Heavy + packed FP16
    multi-leaf FMA mode = packed FP16 + FMA Lite

FMA-Lite-only mode: 5 total
```

Thus the five leaf subpipes do share admission state, but **not one flat
12-entry queue**.  Cross-domain Heavy pairs directly prove a common
approximately five-credit admission/backpressure window: if their
homogeneous 12-credit queues were independent, putting only half of the mixed
stream in each would postpone rather than advance the knee.  ALU Heavy and
ALU Lite share the same deeper ALU domain.  FMA Heavy and FMA Lite cannot use
a common deeper window: their alternating stream stops at five.  Packed FP16
is genuinely coupled and makes ownership non-transitive: it exposes a deep
window with either FMA Heavy or FMA Lite even though those two together do
not.  This is incompatible with assigning each mnemonic to one fixed leaf
FIFO.

This is an effective admission/backpressure model, not yet proof of literal
FIFO placement.  In particular, subtraction alone cannot locate the seven
credits between the 5- and 12-credit boundaries in a physical downstream
FIFO; they could be distributed among dispatch staging and leaf-local state.
Also, a pair containing FMA Lite would naturally knee at five even if its
standalone five-credit pool were independent, so the strongest evidence for
the common cross-domain window comes from pairs whose two homogeneous depths
are both twelve.  The full pair matrix nevertheless rules out both five
independent fixed-ownership queues and a single shared twelve-entry queue.

## Ordered two-phase bursts and their ambiguity

The alternating-pair test still admits a possible flat interpretation: a
single queue might change its effective depth according to the current mode.
The phased probe is stronger.  Each of the two same-subcore producer warps
issues `A^NA`, immediately followed by `B^NB`; the clean-subcore observer and
counted ending barrier are unchanged.  For each `NA`, the reported suffix
curve is `T(NA,NB)-T(NA,0)`, so the cost of the A prefix is removed.

With `NA=12` and no gap, representative suffix curves are:

| ordered pair | suffix increments for `NB=0..12` | interpretation |
|---|---|---|
| ALU Heavy → FMA Heavy | `0,2,4,...,24` | FMA Heavy retains its complete filling window |
| ALU Heavy → ALU Lite | `0,4,8,...,48` | ALU suffix is service-limited immediately |
| FMA Heavy → FP16 | `0,4,8,...,48` | FP16 sees the already occupied Heavy domain |
| FMA Lite → FMA Heavy | still has a filling region | Lite prefix does not occupy Heavy's deep state |

The first row proves that a cross-domain suffix behaves differently from a
same-domain suffix.  It does **not**, by itself, prove two simultaneously
occupied seven-entry queues: the ending `BAR.SYNC` may absorb the time needed
to drain and retag one shared downstream pool into the `T(NA,0)` baseline.
Reversing the order gives the same result.  Replacing the suffix with ALU Lite
removes the filling region completely, and the symmetric FMA-Heavy/FP16 case
behaves like the same-domain ALU pair.

Removing the false predicate from all three representative phased pairs
(ALU-Heavy→FMA-Heavy, ALU-Heavy→ALU-Lite, and FMA-Heavy→FP16) reproduces the
same curves clock for clock through `NB=14`.  The separation is therefore not
an artifact of nullified operations skipping execution or writeback.

Consequently these data establish domain-sensitive downstream state, but leave
two storage organizations open:

```text
shared fixed-math ingress/backpressure state:  ~5 effective credits
                         |
                  domain selection
                         |
       either one tagged/domain-sensitive ~7 pool
       or separate ALU and FMA-Heavy reservation state

FMA-Lite: no independently visible extra window
packed FP16: also reserves the Lite execution side
```

The “extra ~7” should still be read as distributed valid/reservation state,
not necessarily as a seven-word SRAM FIFO.  A cheap implementation is a small
common issue skid/metadata queue (four waiting entries plus the dispatch head
gives the observed five), followed by a tagged seven-slot reservation array.
Separate per-domain valid bits in operand, pipeline, or result staging remain
possible.  If the deeper structure is an eight-slot ring, one unavailable or
reserved slot plus the common five naturally appears as the approximately
twelve effective total.

### A drain-before-retag pool is ruled out

`probe_sm100_scalar_queue_topology_modal.py` first confirmed that ordered
cross-domain service overlaps: with twelve ALU-Heavy instructions per producer
ahead of the suffix, active and false-predicated versions give the same
polling-phase-envelope medians:

| suffix count per producer | 0 | 4 | 8 | 12 | 16 |
|---:|---:|---:|---:|---:|---:|
| ALU-Heavy → FMA-Heavy increment | 0 | 11 | 18 | 26 | 30 |
| ALU-Heavy → ALU-Lite increment | 0 | 18 | 35 | 50 | 66 |

Because a tail marker can still hide drain-before-retag time in the prefix,
the decisive version separates the warps.  Warps 0/4 issue the ALU-Heavy
filling burst.  Warps 8/12, on the same subcore but with no program-order
dependency on that burst, issue one real-result ALU-Lite or FMA-Heavy marker
after a swept delay; a dependent STS makes marker completion visible to the
clean-subcore observer.  Across all thirteen marker delays, the FMA marker is
independent of ALU prefix length apart from the periodic ±3-clock polling
phase.  The otherwise identical ALU marker is strongly delayed.  At marker
delay 2, for example:

| ALU prefix count per filler | 0 | 4 | 6 | 12 | 13 | 17 | 20 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| FMA-Heavy marker delta | 0 | -3 | 0 | -3 | 0 | 0 | -3 |
| ALU-Lite marker delta | 0 | -3 | 24 | 42 | 48 | 72 | 87 |

Thus an FMA operation completes while the same ALU occupancy blocks an ALU
operation for tens of clocks.  A single untagged seven-slot pool whose global
ALU/FMA mode cannot change until drain is directly ruled out; this result does
not rely on subtracting a prefix-only draining barrier.

It does not distinguish a single **per-entry-tagged** seven-slot pool from two
physical seven-slot queues behind a one-entry/cycle switch.  In the ordinary
cross-domain stream, the switch supplies each 0.5/cycle backend at exactly its
service rate, so neither organization can accumulate more downstream backlog.
There is also no measurable throughput cost from switching every instruction:
the alternating ALU/FMA stream reaches the full 1/cycle aggregate rate.  Any
remaining “sticky” behavior must therefore concern reservation ownership or
selection policy, not a mandatory bubble on each switch.

An attempted discriminator made both streams RF-bound using three same-parity,
no-reuse sources.  Homogeneous ALU and FMA streams settle at +6 clocks/count;
the alternating stream also settles at +6 and exposes only the shallow knee.
This control is inconclusive for queue storage because both instruction types
then serialize on the same two-bank RF collector before domain-local execution;
it does not create two independent slow drains.

### Recovery controls

Plain NOP gaps are not a clean clock delay: changing the gap changes warp
scheduler phase.  Nevertheless, same-gap controls preserve the ordered-pair
distinction.  A producer-local `LDS` followed by an explicit scoreboard wait
was therefore added as a second delay mechanism.  For a twelve-operation
prefix:

- ALU→ALU and FMA-Heavy→FP16 remain suffix-service-limited after one to three
  load/wait gaps, while shorter five- and eight-operation prefixes recover
  earlier.
- Cross-domain ALU↔FMA-Heavy and FMA-Lite→FMA-Heavy are already close to their
  empty-prefix controls after two load/wait gaps.
- At four load/wait gaps all tested pairs approach the corresponding empty-
  prefix suffix curve.

This is evidence that the effect is finite downstream state which releases
with progress, not a permanent mode bit.  The exact recovery time is not yet
a pipeline latency: LDS traffic and the two-warp scheduling phase alter the
elapsed baseline, and the ending barrier observes admission rather than an
individual entry's retirement.

Two attempted controls are deliberately not used quantitatively.  An
all-participant intermediate `BAR.SYNC` orders/drains the prefix and makes all
suffix pairs alike; it is useful evidence that the barrier does not pass the
outstanding fixed work, but destroys the state being measured.  `NANOSLEEP`
causes large, duration-dependent `CS2R` jitter (including negative median
suffix differences), so it is not a valid in-kernel timing gap here.

## Resulting model

| path | effective outstanding capacity | qualification |
|---|---:|---|
| unified ALU | **about 12/subcore** | both former Heavy/Lite opcode groups |
| FMA Heavy | **about 12/subcore** | IMAD/IMUL/FSWZADD agree |
| scalar FMA Lite | **unknown** | 1/cycle service matches scheduler ceiling |
| packed FMA window | **about 12/subcore effective** | queue attribution pending NCU |
| packed FP16 | **about 12/subcore** | HFMA2/HADD2/HMUL2 agree |

The dense-issue correction removes the claimed common-5/downstream-7
decomposition.  What remains is approximately twelve effective credits when a
single 0.5/cycle service domain is driven by the one-instruction/cycle
scheduler.  Cross-domain ALU/FMA reaches the scheduler ceiling and therefore
does not reveal its storage capacity.  RF-conflict controls place at least part
of the slow-domain reservation lifetime before/during operand collection.
Packed FP16 interlocks both FMA execution sides; timing does not establish
whether it occupies either or both scalar admission queues.
