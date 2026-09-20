# B200 fixed leaf-pipeline admission windows

Silicon: B200 (sm_100), Modal, 2026-09-20--21.  Probes:

- `tests/asm_construct/probe_scalar_admission_depth.py`
- `tests/asm_construct/probe_sm100_scalar_admission_modal.py`

The target burst uses an architecturally-false predicate, `RZ` destination,
`yield=0`, and operand reuse.  Active representative controls produce the
same curves.  No target result is consumed.  As elsewhere, “credit” below is
an effective scheduler-visible admission credit and does not require a literal
FIFO cell.

Results are grouped by the counter-derived Blackwell leaf hierarchy, not by
the older static ISA pipe names.  Representatives used here are:

| leaf | measured representatives |
|---|---|
| ALU Heavy | IADD3, LOP3, SHF |
| ALU Lite | IADD, MOV, ISETP |
| FMA Heavy | IMAD.LO, IMUL, FSWZADD.NDV |
| FMA Lite | FFMA, FADD, FMUL |
| coupled FMA Heavy + FMA Lite / FP16 | HFMA2, HADD2, HMUL2 |

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
| coupled FP16: HFMA2, HADD2, HMUL2 | 41 | 42 | 44 | +2/instruction |
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
Heavy, and coupled-FP16 representative gives the same median curve:

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

| | ALU Heavy | ALU Lite | FMA Heavy | FMA Lite | coupled FP16 |
|---|---:|---:|---:|---:|---:|
| **ALU Heavy** | ~12 | **~12** | **5** | **5** | **5** |
| **ALU Lite** | | ~12 | **5** | **5** | **5** |
| **FMA Heavy** | | | ~12 | **5** | **~12** |
| **FMA Lite** | | | | 5 | **~12*** |
| **coupled FP16** | | | | | ~12 |

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

The minimum *effective-domain* model consistent with the pair matrix is:

```text
common cross-domain fixed-math window: ~5 total outstanding

same-domain modes which expose a deeper ~12-total window:
    ALU mode           = ALU Heavy + ALU Lite
    FMA-Heavy mode     = FMA Heavy + coupled FP16
    coupled-FMA mode   = coupled FP16 + FMA Lite

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

## Resulting model

| path | effective outstanding capacity | qualification |
|---|---:|---|
| ALU Heavy | **about 12/subcore** | IADD3/LOP3/SHF agree |
| ALU Lite | **about 12/subcore** | IADD/MOV/ISETP agree |
| FMA Heavy | **about 12/subcore** | IMAD/IMUL/FSWZADD agree |
| FMA Lite | **5/subcore** | FFMA/FADD/FMUL agree |
| coupled FP16 | **about 12/subcore** | HFMA2/HADD2/HMUL2 agree |

The mixed-family test refines these homogeneous capacities: the first five
credits are shared across fixed math, while the remaining depth belongs to
the ALU and FMA-Heavy/coupled domains.  Packed FP16 reserves both FMA leaves
for execution but exposes the deeper Heavy-side admission capacity.  Every
fixed path is substantially deeper than a single active operation once two
same-subcore warp schedulers feed it fast enough.
