# B200 fixed INT/FP admission windows

Silicon: B200 (sm_100), Modal, 2026-09-20.  Probes:

- `tests/asm_construct/probe_scalar_admission_depth.py`
- `tests/asm_construct/probe_sm100_scalar_admission_modal.py`

The target burst uses an architecturally-false predicate, `RZ` destination,
`yield=0`, and operand reuse.  Active representative controls produce the
same curves.  No target result is consumed.  As elsewhere, “credit” below is
an effective scheduler-visible admission credit and does not require a literal
FIFO cell.

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

## Direct short bursts

The one-producer barrier spans are exact at their medians:

| family / representatives | T(0) | T(1) | T(2) | later increment |
|---|---:|---:|---:|---:|
| `int_pipe`: IADD3, LOP3, SHF | 41 | 42 | 44 | +2/instruction |
| integer on `fmalighter_pipe`: IMAD.LO | 41 | 42 | 44 | +2/instruction |
| `fp16_pipe`: HFMA2 | 41 | 42 | 44 | +2/instruction |
| FP32 `fmalighter_pipe`: FFMA, FADD, FMUL | 41 | 42 | 43 | +1/instruction |

The first three rows accept one operation at the fast +1-cycle frontend
step.  The second operation already falls on their +2-cycle service cadence.
They therefore expose **one active credit, including the instruction being
serviced, and zero additional waiting instructions**.  The result is
predicate-insensitive: active and `@P6`-off versions of IADD3, IMAD, and
HFMA2 give the same `41,42,44,46,...` curve.

FP32 accepts and services one instruction per cycle, so an FFMA/FADD/FMUL-only
stream cannot fill a possible queue.  Its `41+N` line alone does not identify
leaf-private storage depth.

Different-subcore two-producer controls preserve the one-producer slopes,
showing independent admission/service progress across subcores.  Same-subcore
FMA-Heavy and FP16 streams eventually cost +4 clocks per N (two instructions),
where different-subcore streams cost +2; their limiting service is local.
Same-subcore FP32 costs +2 per N versus +1 across different subcores, also
localizing the one-instruction/cycle FP32 service.  Initial two-warp alignment
contains scheduler phase artifacts and is not used to count entries.

## Blocking controls for the one-cycle FP32 leaf

An active four-beat `IMAD.HI` prefix makes the common scalar-math entrance
temporarily unavailable.  Four prefixes alone take 18 clocks.  Appending a
predicated-off target gives:

| appended target count | 0 | 1 | 2 | 3 | 4 |
|---:|---:|---:|---:|---:|---:|
| FFMA | 18 | 21 | 22 | 23 | 24 |
| FADD | 18 | 21 | 22 | 23 | 24 |
| FMUL | 18 | 21 | 22 | 23 | 24 |

The first FP32 target cannot enter a waiting slot behind the busy prefix; it
pays three clocks before the entrance becomes available.  Once admitted, the
FP32 leaf resumes its +1-clock cadence.  One active HFMA2 prefix supplies a
second blocker: prefix-only is 6 clocks, prefix plus one FFMA is 8, and each
further FFMA adds one clock.  The same control with one or four IMAD.HI
prefixes gives the same boundary.

Thus the scheduler-visible scalar-math entrance also exposes **one active
credit and no additional waiting operation** for FP32.  This is stronger than
the unblocked `41+N` curve, but the wording remains deliberately narrow: it
does not prove that no physically deeper FP32-only structure exists behind an
entrance that these streams cannot outrun.

## Resulting model

| path | effective admission capacity seen by a warp | qualification |
|---|---:|---|
| INT (`IADD3`, `LOP3`, `SHF`) | **1 active, 0 waiting** | corrected CBU-barrier observer |
| integer multiply (`IMAD.LO`) | **1 active, 0 waiting** | second request is already +2 |
| packed FP16 (`HFMA2`) | **1 active, 0 waiting** | second request is already +2 |
| FP32 (`FFMA`, `FADD`, `FMUL`) | **1 scheduler-visible active credit, 0 visible waiting** | own service equals arrival; blocker closes the entrance ambiguity |

This matches the effective one-credit behavior previously measured on GB202.
It is much shallower than the MIO-side LSU/XU and UTCHMMA credit pools, and is
better modeled as backpressure at a fixed-pipeline entrance than as a
multi-entry instruction FIFO.
