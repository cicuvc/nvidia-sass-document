# H20 scalar ALU/FMA structural conflicts

> **2026-09-20 correction:** this note measured everything with
> `SCHED=[7:7:{}:1:1]` (yield=1 per instruction).  After the yield switch-cost
> discovery (`notes/sm120/yield_dispatch_cost.md`), the solo "~2 clocks" numbers
> here must be re-read: on H100 the clean FFMA/FADD/FMUL solo rate is **1.0
> cyc/inst** (32 FP32 lanes/SMSP), and yield halves it to 2.0.  The conflict
> *pairing* conclusions below are relative and stand; absolute slopes carry
> per-instruction switch noise.  Clean H100 rates + full latency matrices:
> [`h100_fixed_pipeline.md`](h100_fixed_pipeline.md).

Silicon: NVIDIA H20 (sm_90), 2026-09-14.  NCU is installed but performance
counters are disabled (`ERR_NVGPUCTRPERM`), so this note uses hand-built SASS,
`SR_CLOCKLO`, active versus `@P6` contenders, and same/different-subcore
placement.  Harness: `tests/asm_construct/probe_subcore_compute_conflict.py`.

Warp 0 is the victim.  Warp 4 is the same-subcore contender and warp 1 is the
different-subcore control (`warp_id % 4`).  Forty independent destinations
remove RAW/WAW serialization.  The contender is four times longer than the
victim except for FP64-victim tests, where its factor is 64 because H20 FP64
is unusually slow.  Multiple lengths are fit to remove fixed harness cost.

## Family-level results

Every ordinary stream runs near two clocks/instruction in one warp.  The
following table gives the fitted victim clocks/instruction with a sustained
same-subcore contender.  `off` means the contender has the identical opcode
and schedule but is guarded by architecturally false P6.

| victim <- contender | off | active | different-subcore active | dominant boundary |
|---|---:|---:|---:|---|
| IADD3 <- IADD3 | 4.33 | 4.19 | 1.96 | early INT admission |
| IADD3 <- LOP3/SHF | 4.3--4.6 | 4.1--4.5 | ~2.0 | early INT admission |
| HFMA2 <- HFMA2 | 4.32 | 4.37 | 2.05 | early packed-FP admission |
| HFMA2 <- HADD2 | 4.34 | 4.13 | 2.03 | early packed-FP admission |
| IMAD <- IMAD | 4.53 | 4.15 | 2.02 | early IMAD admission |
| FFMA <- FFMA | 2.04 | 4.34 | 1.97 | active RF collection |
| FADD <- FADD | 1.97 | 2.05 | 1.95 | no saturated pipe at 1 inst/clock |

Simple INT, packed FP16, and IMAD therefore each expose an approximately
0.5-instruction/clock local admission limit which is acquired before the
predicate suppresses execution.  FP32 FADD/FFMA do not show that early self
limit.  Two balanced FADD streams sustain approximately one aggregate
instruction/clock on a subcore.

Cross-family controls identify two kinds of sharing:

| victim <- contender | off | active, original sources | active, complementary source banks |
|---|---:|---:|---:|
| IADD3 <- FFMA | 2.02 | 4.11 | 2.98 |
| FFMA <- IADD3 | ~2.0 | 3.96 | not required for conclusion |
| IADD3 <-> HFMA2 | ~2.0 | 3.9--3.93 | not tested |
| FFMA <-> HFMA2 | 4.29--4.37 | 4.07--4.38 | n/a: early conflict dominates |
| FADD <-> HFMA2 | 4.30--4.33 | 4.07--4.39 | n/a: early conflict dominates |
| IMAD <-> HFMA2 | 3.96--4.30 | 3.98--4.04 | n/a: early conflict dominates |
| IMAD <-> FFMA | ~2.0 | 4.05--4.10 | 3.04--3.08 |
| IADD3 <-> FADD | ~2.0 | 2.93--3.00 | same bank count for FADD |

INT versus FMA-class instructions has no predicate-insensitive cross-family
conflict; its active conflict changes with operand-bank placement and is the
shared RF collector described below.  Packed FP16 is different: an encoded
FP16 stream and any tested fmalighter stream (FADD, FFMA, or IMAD) mutually
block near four clocks even when the contender is predicated off.  There is
an additional early shared FP16/fmalighter dispatch or mode-selection credit.
The timing cannot distinguish one queue from a shared dispatch switch.

## Banked RF collection is the main active cross-pipe bottleneck

The original three sources are R24/R27/R28, i.e. two even-bank and one
odd-bank warp operands.  A complementary contender uses R25/R26/R29, i.e.
one even and two odd.  Destination parity is independently flipped without
changing sources.

| active pair | source demand per pair | victim clocks/inst |
|---|---|---:|
| FADD + FADD, both balanced | 2E + 2O | ~2.0 |
| FADD + FADD, both all-even | 4E | ~4.06 |
| FFMA + FFMA, same 2E+1O phase | 4E + 2O | ~4.17--4.34 |
| FFMA + complementary FFMA | 3E + 3O | ~2.99 |
| FFMA + FADD, original | 3E + 2O | ~2.96--3.17 |
| FFMA + complementary FADD | 3E + 2O | ~2.95--3.01 |
| all-even FFMA, one stream | 3E | ~3.0 |
| all-even FFMA, two streams | 6E | ~5.6 |
| all-even IADD3/HFMA2, one stream | 3E | ~3.0 |
| all-even IADD3/HFMA2, two streams | 6E | ~5.6--5.7 |

This is a direct capacity law: each even/odd RF bank supplies approximately
one warp-wide 32-bit operand per `SR_CLOCKLO` tick, equivalently two operands
over the normal two-clock single-warp issue interval.  The time for a mixed
pair is approximately `max(E_reads, O_reads)`.  It explains the apparent
2/3/4-clock occupancy weights without requiring one unified arithmetic array.

The same matrix was later rerun on a full H800 and reproduced this law:
balanced FADD/FADD stays at 2.10 clocks, all-even FADD/FADD rises to 4.29,
same-phase FFMA/FFMA rises to 4.29, complementary FFMA/FFMA takes 2.99, and
all-even FFMA/FFMA takes 5.57 clocks.  Thus this is a Hopper subcore property,
not an H20 product-cut artifact.

Flipping only the contender destination parity leaves every tested curve
unchanged: IADD3 self ~4.00, FFMA self ~4.17, HFMA2 self ~4.04, FADD self
~2.03, IADD3<-FFMA ~4.11, and FFMA<-FADD ~3.01.  The sustained conflicts are
therefore source collection/execution admission, not the known 1W-per-bank
RF writeback collision.  This does not deny transient writeback conflicts;
dead-result fixed-pipe streams simply schedule around them in this test.

IADD3 and HFMA2 remain at about four clocks under complementary source banks,
whereas FFMA drops to three.  Their own approximately 0.5-inst/clock pipe
admission limits dominate once the RF demand is balanced.  IMAD behaves like
them for self traffic, but IMAD/FFMA cross traffic drops to three under
complementary banks, showing separate execution admission plus a common RF
frontend.

## FP64 is a separate narrow backend

H20 DADD and DFMA both run at approximately 64 clocks/instruction.  A second
same-subcore DADD/DFMA stream raises the victim to approximately 136 clocks,
and the predicated-off contender produces essentially the full conflict.
All combinations of DADD and DFMA share this subcore-local `fma64lite`
admission/backend; moving the contender to another subcore restores ~64.

A 64x-long IADD3, FFMA, or HFMA2 contender changes a DFMA victim only from
about 64 to 64--66 clocks.  Conversely a sustained DFMA changes those fast
victims negligibly from about two clocks.  The FP64 execution backend is
therefore independent of INT, FP32, and FP16, with only small common frontend/
RF effects.

## Best-fit datapath

```text
subcore schedulers / predicate-insensitive per-family admission
        |             |             |              |             |
   INT (~0.5)    IMAD (~0.5)   FP16 (~0.5)   FP32 (>=1)   FP64 (~1/64)
        \             |             |              |             /
         +------------+--- shared even/odd GPR collectors -------+
                         (~1 operand/bank/clock tick)
                                      |
             specialized INT / FP32-FMA / FP16 / fma64lite bodies
                                      |
                           bypass / result queues
                         |
                even/odd 1W RF commit arbiters
```

Additional constraint: packed FP16 and the tested fmalighter operations share
an early predicate-insensitive dispatch/mode resource.  The diagram leaves it
as an ingress cross-link rather than asserting that their arithmetic arrays
are identical.

The conservative sm_90 latency file assigns occupancy 2 to FXU/FMAI/FMALITE,
but silicon does not implement that as one uniform physical throughput rule:
two FADD streams reach one instruction/clock, while source-bank demand and
per-family admission explain the slower cases.  Static occupancy tables remain
safe scheduling abstractions, not literal execution-array descriptions.
