# H100 fixed INT/FP admission windows

Silicon: Modal H100 (sm_90), 2026-09-20.  The cubins are assembled directly
with the repository assembler; ptxas is not used.  Probe:
`tests/asm_construct/probe_scalar_admission_depth.py`, launched through
`tools/modal_h100_probe.py` with `ASSEMBLER_ARCH=sm90`.

The construction and interpretation are identical to the B200 experiment in
`../../sm100/arch/b200_fixed_admission_depth.md`.  Targets use `RZ` sources and
destinations, `yield=0`, and source reuse.  Representative direct bursts are
active; the downstream-blocker targets use architecturally-false P6 so result
writeback cannot create the observed backpressure.

## Corrected INT admission marker

`CS2R` is itself assigned to `int_pipe` on sm_90.  Therefore
`CS2R; INT*N; CS2R` measures service completion rather than admission: the
ending timestamp cannot pass the INT stream.

The corrected `--barrier-method` places the producer on warp 0 and a timing
observer on a different subcore.  The producer's post-burst marker is a
counted `BAR.SYNC` on `mio_pipe`; only the observer executes the ending
`CS2R`.  Four stall-8 NOPs make the producer path critical even for N=0.
Thus the barrier release bounds when the producer has advanced past its final
admitted operation without requiring that operation to retire from int_pipe.

## One producer underfills the queues

Nine-repeat medians are exact and match B200:

| family / representatives | T(0) | T(1) | T(2) | later increment |
|---|---:|---:|---:|---:|
| `int_pipe`: IADD3, LOP3, SHF | 41 | 42 | 44 | +2/instruction |
| integer on `fmalighter_pipe`: IMAD.LO | 41 | 42 | 44 | +2/instruction |
| `fp16_pipe`: HFMA2 | 41 | 42 | 44 | +2/instruction |
| FP32 `fmalighter_pipe`: FFMA, FADD, FMUL | 41 | 42 | 43 | +1/instruction |

These curves measure service, not capacity.  A single warp supplies INT,
IMAD, and HFMA2 at only 0.5 instruction/cycle, equal to service; it supplies
FP32 at one instruction/cycle, also equal to service.  No one-producer stream
can accumulate backlog.  A second same-subcore producer is required.

## Same-subcore two-producer depth

Warps 0 and 4 issue identical N-instruction bursts while warp 1 on another
subcore timestamps their counted-barrier release.  IADD3, IMAD.LO, and HFMA2
produce the same nine-repeat median curve:

| N per producer | 0 | 1 | 2 | 3 | 4 | 8 | 12 | 13 | 14 | 15 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| common clocks | 47 | 48 | 50 | 52 | 56 | 64 | 72 | 76 | 80 | 84 |

From N=13 onward the span increases by exactly four clocks for the two added
instructions, the 0.5-instruction/cycle service slope.  Before that boundary,
the two warp schedulers admit near one instruction/cycle in aggregate.  At
N=12, 24 operations have entered in about 25 incremental clocks while about
12 have drained.  This gives approximately **12 outstanding credits/subcore**
including the operation in service, or roughly eleven waiting entries.

FP32 gives a shallower exact boundary:

| N per producer | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 and later |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| common clocks | 47 | 48 | 49 | 50 | 51 | 52 | 54 | +2/N |

Through N=5, each extra N admits two operations in one clock while one drains,
leaving five outstanding operations.  N=6 is the first service-limited point.
FFMA/FADD/FMUL therefore have **5 effective outstanding credits/subcore**,
including the operation in service, or about four waiting entries.

Different-subcore controls remain at +2/N for the heavy families and +1/N
for FP32 through the tested range, confirming independent per-subcore pools.

## FP32 blocking controls

Four active `IMAD.HI` operations hold the scalar FMA entrance.  Prefix-only
is 18 clocks, and appending FP32 targets gives:

| appended target count | 0 | 1 | 2 | 3 | 4 |
|---:|---:|---:|---:|---:|---:|
| FFMA | 18 | 21 | 22 | 23 | 24 |
| FADD | 18 | 21 | 22 | 23 | 24 |
| FMUL | 18 | 21 | 22 | 23 | 24 |

The first target costs three clocks; later targets resume the +1 cadence.  An
active HFMA2 blocker gives prefix-only 6 clocks, then `8,9,10,11` for one
through four FFMA targets.

This is an upstream entrance effect, not evidence against the five-credit
FP32 leaf queue.  A cross-family blocker prevents the following FP32 from
reaching that queue early, whereas two synchronized FP32 producers directly
fill it.

## H100 versus B200

| path | H100 | B200 |
|---|---:|---:|
| INT: IADD3/LOP3/SHF | about **12/subcore** | about **12/subcore** |
| integer IMAD.LO | about **12/subcore** | about **12/subcore** |
| packed FP16 HFMA2 | about **12/subcore** | about **12/subcore** |
| FP32 FFMA/FADD/FMUL | **5/subcore** | **5/subcore** |

No tested fixed-pipeline admission parameter distinguishes the Modal H100
from B200.  Capacity equality alone does not prove that the three heavy
families share one physical queue; only that each exposes the same effective
depth under homogeneous traffic.

## Mixed-family bursts: the heavy families share one queue; HFMA2.MMA executes on the FP64 path

The capacity equality above leaves open whether INT/FP16/FP64 share one
physical queue.  Interleaved two-family bursts answer it
(`probe_sm80_admission_depth.py --mode mix_* --actors same2`, the older
same-subcore CS2R construction, so absolute knee positions are on its
scale; the *sharing* inference is structural and method-independent):

| mixed burst (alternating) | knee at cumulative N | steady slope |
|---|---:|---:|
| IADD3 + HFMA2 | ~11 | +3 cyc/op |
| IADD3 + DADD | ~11 | +3 |
| HFMA2 + DADD | ~11 | +3 |
| HFMA2.MMA + HFMA2 | ~11 | +3 |
| HFMA2.MMA + DADD | ~11 | **+4** |

Separate per-family queues would postpone the knee to ~2x (each queue
fills at half the combined arrival rate); every mix knees at the same
cumulative ~11 as the homogeneous bursts, so **the heavy fixed-pipe
families share one admission queue per subcore**.  The +3 (0.67 inst/cyc)
steady slope of the cross-family mixes sits between one shared 0.5/cyc
service (+4) and two fully independent 0.5/cyc services (+2): the two
pipes overlap partially once past admission.

The exception proves the execution resource of HFMA2.MMA: mixed with DADD
it degrades to exactly +4 = a single 0.5/cyc service, while mixed with
HFMA2 it keeps the +3 cross-path overlap.  **HFMA2.MMA is serviced by the
FP64 pipe** (matching its DADD-like 4-cycle result bypass), so its
admission queue is the shared fixed-pipe queue, but its service resource
is FP64, not the FP16/C path used by plain HFMA2.

## B200 packed-state phenomenology reproduces on H100

`probe_sm90_packed_clamp.py` (single warp, CS2R window, `[7:7:{}:1:0]`,
RF-clean E+O+immediate operands) ports the sm_100 packed-FMA experiments
from `../../sm100/arch/b200_fixed_admission_depth.md` to HFMA2.  H100
matches B200 point for point:

| one-warp repeating stream | H100 | B200 |
|---|---:|---:|
| HFMA2 alone (stall=1, yield=0) | 2.0 | 2.0 (FFMA2) |
| HFMA2 + NOP alternating | **1.0** | 1.0 |
| HFMA2 + IADD3 alternating | **1.0** | 1.0 |
| HFMA2 + FFMA alternating | **2.0** | 0.5/cyc (blocked) |
| scalar FFMA alone | 1.0 | 1.0 |

The 2-cycle packed interval is therefore a **front-end issue clamp**, not
backend occupancy: the second slot accepts INT and NOP work but not scalar
FMA.  Combined with the same2 experiments (two warps fill the ~12-entry
packed window, one warp cannot), this is the same PACKED_LOCK/LITE picture
as B200.

Ordered handoff phases also match:

| direction (32-op prefix) | H100 suffix increments (B=1,2,3,4,...) | B200 |
|---|---|---|
| HFMA2 -> FFMA | +2,+3,+4,+5,... | 0,2,3,4,5 extra |
| FFMA -> HFMA2 | +2,+4,+6,+8,... | 0,2,4,6 extra |

The first scalar FFMA after packed work pays one extra handoff clock;
scalar->packed pays nothing beyond the normal 2-cycle service.

H100 differences to keep in mind: packed FP16 has no FFMA2 sibling format
(no format-switch test applies), and HFMA2.MMA — not plain HFMA2 — is the
variant serviced by the FP64 pipe (see the mixed-family section above).
