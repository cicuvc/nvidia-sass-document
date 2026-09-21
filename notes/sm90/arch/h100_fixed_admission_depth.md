# H100 fixed-pipeline admission and service

Silicon: Modal H100 (sm_90), 2026-09-20--21. Cubins are assembled directly
with the repository assembler; ptxas and NCU are not used. Primary probes:

- `tests/asm_construct/probe_scalar_admission_depth.py`
- `tests/asm_construct/probe_sm90_rates.py`
- `tests/asm_construct/probe_sm90_packed_clamp.py`

This is the corrected interpretation after applying the dense counted-barrier
method developed for B200. Git history contains two withdrawn models: the
four-stall-8-NOP construction falsely made FP32 look like a five-credit pipe,
and summing two partially non-overlapping per-warp windows falsely implied a
two-instruction/cycle SMSP issue rate. Neither result is used below.

“Window” and “credits” mean scheduler-visible outstanding/reservation state.
Timing does not require a literal FIFO with that many SRAM rows.

## Current model

| effective domain | representatives | service/SMSP | visible window |
|---|---|---:|---:|
| ALU | IADD3/LOP3/SHF and other `int_pipe` ops | about 0.5 inst/cycle | about 12 |
| FMA | IMAD/IMUL/IDP + ordinary HFMA2/HADD2 | about 0.5 combined | about 12 shared |
| FP64 | DADD/DFMA + HFMA2.MMA | about 0.5 combined | about 12 shared |
| scalar FP32 Lite | FFMA/FADD/FMUL | 1.0 | no independently visible deep window |

The three slow domains have separate admission state. Equal depths do not
mean one common queue. Scalar FP32 keeps pace with the one-instruction/cycle
SMSP issue ceiling, so this timing method cannot overdrive it and does not
determine whether a tiny skid/collector exists.

```text
                 ~12                 ~12                  ~12
issue <= 1  -> [ ALU ]        || [ IMAD + HFMA2 ]  || [ FP64 + HFMA2.MMA ]
                  0.5/cyc              0.5/cyc               0.5/cyc

scalar FFMA/FADD/FMUL: 1/cyc, no deep window seen
ordinary HFMA2 blocks the scalar-Lite state
```

## Corrected counted-barrier construction

`CS2R` is assigned to `int_pipe`, so `CS2R; burst; CS2R` cannot measure ALU
admission. Two producer warps (0 and 4, same SMSP) execute dense stall-1,
yield-0 bursts. Warp 1, on another SMSP, timestamps a counted `BAR.SYNC`
reached by both producers. The final timestamp observes producer progress
past the burst without waiting on the target pipe itself.

The current source has **no stall-8 producer prefix**. Such a prefix leaves
issue holes which new instructions initially occupy and manufactured the old
five-credit FP32 knee. RZ-source operations also use no unnecessary reuse
`batch_t` field; on H100 that control field changes multi-warp scheduling and
must not be treated as neutral.

Predicated-off and active RZ-destination runs agree. Squashed operations
therefore consume the same admission/service reservation relevant here; the
knee is not result-writeback pressure.

Representative two-producer curves are identical for IADD3, IMAD, HFMA2,
DADD, and HFMA2.MMA (minor phase teeth at N=6--8 omitted):

| N per producer | 0 | 5 | 8 | 10 | 11 | 12 | 13 | 14 | 16 | 20 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| observer span | 28 | 28 | 30--31 | 34--35 | 37 | 40--41 | 44--45 | 48--49 | 56--57 | 72--73 |

From N=13 onward each increment adds two producer instructions and four
clocks: the domain drains at 0.5 instruction/cycle. During filling the two
warps supply close to one instruction/cycle while half that rate drains. The
transition corresponds to approximately **12 outstanding reservations per
SMSP**, including work in service.

Scalar FFMA instead stays hidden under the fixed observer path through about
N=10 and then advances by +2 clocks/N, exactly its one-instruction/cycle
service for the two newly added instructions. That is an observer crossover,
not a queue knee. The old “five FP32 credits” conclusion is withdrawn.

## Admission topology from saturated ordered phases

Homogeneous equal-depth curves alone cannot say whether families share a
queue. The stronger test first issues 24 operations per producer from domain
A (well beyond its window), then varies a B suffix. Each B increment adds two
instructions. A suffix in an independent domain advances at +2 clocks/B; a
suffix blocked by the saturated domain advances at +4 clocks/B.

| saturated prefix -> suffix | clocks per B | inference |
|---|---:|---|
| ALU -> ALU | +4 | same ALU reservation/service domain |
| ALU -> IMAD | **+2** | ALU and FMA admission are independent |
| IMAD -> ALU | **+2** | reciprocal control |
| IMAD -> IMAD | +4 | same FMA domain |
| IMAD -> HFMA2 | **+4** | IMAD and ordinary packed FP16 share FMA admission |
| IMAD -> DADD | **+2** | FMA and FP64 admission are independent |
| DADD -> HFMA2.MMA | **+4** | MMA form shares the FP64 domain |
| DADD -> ordinary HFMA2 | **+2** | ordinary packed FP16 is not on FP64 |

Thus H100 does **not** have one common 12-entry heavy queue. It exposes at
least three independently progressing approximately-12-credit domains: ALU,
FMA (including ordinary packed FP16), and FP64 (including HFMA2.MMA).

## Backend composition from one-warp alternating streams

One warp avoids the large and phase-dependent warp-switch effects seen when
two yield-0 streams live at different PCs. In a 2048-instruction alternating
stream, independent 0.5/cycle leaves fill each other's unused issue slots;
shared leaves remain at two clocks/instruction. Long unrolled independent
streams measure about 1.10 rather than exactly 1.00 clocks/instruction because
of front-end/fetch overhead, while shared pairs measure 2.004.

| alternating pair | clocks/instruction | relation |
|---|---:|---|
| IADD3 + IMAD | ~1.10 | independent |
| IADD3 + DADD | ~1.10 | independent |
| IMAD + DADD | ~1.10 | independent |
| ordinary HFMA2 + DADD | ~1.10 | independent |
| HFMA2.MMA + ordinary HFMA2 | ~1.10 | independent |
| **IMAD + ordinary HFMA2** | **2.004** | shared FMA backend |
| **HFMA2.MMA + DADD** | **2.004** | shared FP64 backend |
| IADD3/IMAD + scalar FFMA | ~1.10 | Lite fills the other slot |
| ordinary HFMA2 + scalar FFMA | ~2.00 | packed state blocks Lite |

The mixed counted-barrier curves give the same map: independent pairs settle
at one aggregate instruction/cycle, while IMAD+HFMA2 and
HFMA2.MMA+DADD settle at 0.5.

## Clean solo throughput

`probe_sm90_rates.py` uses a 1024-instruction one-warp window:

| family | clocks/instruction |
|---|---:|
| NOP | 1.008 |
| ordinary ALU | 2.008 |
| IMAD/IMUL/IDP.4A | 2.007 |
| IMAD.WIDE/HI | 4.005 |
| FFMA/FADD/FMUL with reuse | 1.008 |
| HFMA2/HADD2 | 2.007 |
| DADD/DFMA | 2.007 |
| MUFU | 7.998 |

FFMA without a useful reuse pattern is RF-bound at about two clocks per
instruction. This is operand collection, not Lite execution throughput.
`yield=1` changes NOP and scalar FP32 from one to two clocks/instruction;
the switch cost hides under the two-cycle floor of most slow domains. DFMA
is the exception and changes from about two to three.

## Limits

- Approximately 12 is an effective outstanding count, not proof of a literal
  twelve-row FIFO.
- Timing distinguishes three slow reservation domains but cannot tell whether
  each combines a FIFO, collector, and in-service token or distributed credits.
- Lite has no measurable deep queue here. “Near-direct dispatch” is preferred
  over asserting exactly zero entries.
- The packed/Lite relation is operational. Timing alone cannot distinguish a
  shared physical array from an interlock between leaves.
