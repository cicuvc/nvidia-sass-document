# GB202 register-file writeback conflict probes

**Status:** first negative/diagnostic round, RTX 5090 / sm_120, 2026-09-14.
Probe: `tests/asm_construct/probe_rf_writeback_conflict.py`.

## Motivation

The RF model suggested by the controlled H800 experiment is two banks selected
by register-number parity.  Later GB202 tests expose about one independently
addressed full-warp operand/bank/clock at the ALU collector, plus one observed
architectural write/commit service per bank.  A single subcore issues at
most one instruction per cycle, so a steady stream cannot exceed one 32-bit
destination write per cycle.  The write limit can nevertheless matter when
instructions issued in different cycles and with different pipeline depths
complete in the same cycle and target the same bank.

This is distinct from the already-proven 3R same-bank source conflict.  In
fact, correcting the compute-conflict harness from accidental E/E/E sources to
E/O/E reduced the GB202 IADD3/FFMA/HFMA2 solo slope from about 3 to about 2
clock units/instruction.  Source parity must therefore remain fixed in every
writeback experiment.

## Double-completion construction

The initial candidate was:

```text
issue t+0: HADD2 RdA, ...   nominal fp16 writeback near t+5
issue t+1: FFMA  RdB, ...   nominal fmal writeback near t+5
```

Only destination parity changes: EE/OO should request two writes from one bank,
while EO/OE should request one write from each bank.  Sources are fixed at
bank-balanced E/O or E/O/E layouts; 20 rotating destinations give a 40-issued-
instruction reuse distance.

### Sustained issue/backpressure result

Lengths 16/32 initially and longer validation runs give the same fitted slope
for all four layouts:

```text
EE = EO = OE = OO = 2.0000 clock units / issued instruction
same-bank - opposite-bank = 0.0000
```

This does **not** refute 1W/bank.  The collision produces two writes in one
cycle followed by an empty write cycle, so a one-entry completion buffer can
smooth it while maintaining an average of one write/cycle.

## RAW visibility boundary

After one HADD2/FFMA pair, an FADD consumer was swept over global issue gaps
2..8.  Each producer was first read separately:

```text
                 gap 2 3 4 5 6 7 8
HADD2 result         F F F F F F F
FFMA result          S S S F F F F
```

The patterns are identical for EE/EO/OE/OO.  Thus neither individual result
shows a same-bank writeback delay through the normal forwarding/RAW path.

A consumer reading **both** results exposes a parity effect:

```text
EE/OO combined: FS FS FF FF FF FF FF
EO/OE combined: FS FS FS FF FF FF FF
```

Same-bank operands make the FFMA value visible one issue slot earlier.  This
effect persists when the producer issue gap is changed from 1 to 2 or 3, where
the nominal producer writebacks no longer coincide.  It is therefore a
consumer operand-collection/forwarding phase effect, not evidence that the
HADD2/FFMA writebacks collided.  It also illustrates why a consumer of two
same-bank results is not a clean write-port probe.

## Triple-completion construction

To exceed a one-entry smoothing case, three pipeline depths were aligned:

```text
issue t+0: IADD3  (nominal w ~6)
issue t+1: HADD2  (nominal w ~5)
issue t+2: FFMA   (nominal w ~4)
```

All eight destination layouts EEE..OOO were tested, with each result consumed
separately over global gaps 3..10.  Ten repeats were deterministic and every
layout produced the same boundaries:

```text
IADD3: FFFFFFFF
HADD2: FFFFFFFF
FFMA : SSSFFFFF
```

No loser or extra one/two-cycle delay is visible.  A deliberately unsafe WAW
probe then overwrote each result with an FFMA at issue gaps 3..7.  In all eight
layouts and all ten repetitions the younger overwrite won; no delayed older
write overtook it.

## Current conclusion

The tested fixed math pipelines do not expose a destination-parity-dependent
writeback delay through sustained issue, ordinary RAW observation, a three-way
completion burst, or an unsafe WAW race.  This is compatible with several
architectures:

1. per-pipe completion/bypass queues absorb collisions before a 1W bank port;
2. fixed-pipe results use separate staging paths and only serialize at a later
   RF commit point that consumers bypass;
3. the write side on GB202 differs from the simple parity-bank 1W model;
4. nominal dependency latency is not the actual RF commit phase, so the chosen
   completions were never simultaneous.

The experiments do establish what **not** to infer: matching table latencies
does not prove matching RF commit cycles, and a parity-dependent early RAW
result can come from operand collection rather than writeback arbitration.

## Round 2: scoreboard-visible MIO completion under an ALU write storm

The fixed-pipe experiments above are hidden by forwarding, so
`tests/asm_construct/probe_mio_rf_writeback.py` uses completion rather than a
table latency:

1. warm one global-memory line;
2. issue a hot `LDG.32 Rd` claiming SB4;
3. before the first `req={4}` consumer, issue N independent FFMAs whose
   destinations are all one parity;
4. time from LDG issue through the req-waiting consumer.

The LDG destination parity and FFMA destination parity are independently E/O.
FFMA sources are fixed E/O/E.  With reuse mask 7, consecutive FFMAs reuse all
three sources and approach the NOP issue cadence, leaving an almost pure
one-32-bit-write-per-issued-instruction stream.

### Decisive same-bank result

Twenty-repeat best/median measurements are parity symmetric:

| N | E-load/E-writes | E-load/O-writes | delta | O-load/O-writes | O-load/E-writes | delta |
|---:|---:|---:|---:|---:|---:|---:|
| 24 | 46 | 46 | 0 | 46 | 46 | 0 |
| 28 | 48 | 46 | +2 | 48 | 46 | +2 |
| 32 | 52 | 46 | **+6** | 52 | 46 | **+6** |
| 36 | 56 | 48 | **+8** | 56 | 48 | **+8** |
| 40 | 60 | 52 | **+8** | 60 | 52 | **+8** |
| 48 | 64 best / 66 common | 60 | +4 / +6 | same | same | +4 / +6 |
| 64 | 80 | 76 | +4 | 80 | 76 | +4 |

For N≤24 the hot load commits before the write stream reaches its return
window.  At N≈28 the windows overlap; the penalty grows to eight clock units.
Longer streams retain a four-to-six-unit delay after the instruction body
itself becomes the timing floor.

Controls are decisive:

- E/E and O/O give the same penalty; E/O and O/E do not.
- Predicated-off FFMAs exactly match NOP and show no parity effect.
- Plain, non-reuse E/O/E FFMAs take about two clock units/instruction and show
  no same-bank penalty (`N=40`: 92 vs 92).  Their write cadence leaves enough
  bank-port holes for the load to commit.
- Reuse-mask scan at N=40:

| reuse mask (A/B/C = 1/2/4) | same bank | opposite bank | best delta | behavior |
|---:|---:|---:|---:|---|
| 0 | 92 | 92 | 0 | full source reads, slow issue |
| 2 | 92 | 92 | 0 | removes odd source only; two even sources remain |
| 1 / 4 | 55 | 53 | +2 (median +8) | removing either even source reaches fast cadence |
| 3 / 6 | 55 | 53 | +2 (median +8) | fast cadence, bimodal phase |
| 5 / 7 | 60 | 52 | **+8** | both even sources reused; strongest stable conflict |

This is the first direct GB202 evidence for one bank-local architectural write
service:
an effective FFMA write every issue slot can delay a scoreboarded MIO result
only when both target the same register-number parity bank.  The result is not
explained by source reads, opcode dispatch, instruction count or the LDG
latency table.

The exact +4/+6/+8 values should not yet be interpreted as a raw queue depth.
They include discrete usched/operand-collector phases, and the 20-register
destination rotation may expose a periodic completion phase.

### Nsight Compute limitation and supporting counters

Profiling the selected launch perturbs this short hot-load experiment badly:
the profiled same and opposite cases both expand to ~132 clock units instead of
the naked ~60/~52.  Therefore profiler-run clocks are discarded.  Both cases
report `smsp__mio2rf_writeback_active.sum = 5`: the amount of MIO writeback work
is unchanged, consistent with delayed arbitration rather than extra writes.
The long-scoreboard aggregate is higher for same-bank (92000 vs 74700), but its
`.pct` aggregation exceeds 100 for this sparse one-warp kernel and is only
supporting evidence, not a calibrated latency measure.

## Round 3: wide MIO results and independent read/write ports

`probe_mio_rf_writeback.py --width-scan N` applies the same scoreboard-visible
measurement to `LDG.32`, `LDG.64 {R40,R41}` and
`LDG.128 {R40,R41,R42,R43}`.  The first consumer reads only R40 but waits SB4;
therefore it cannot pass until the complete destination group has retired.

Before the FFMA stream becomes the timing floor, the stable hot-load endpoints
are 46, 50 and 58 clock units respectively.  At N=40:

| width | even-destination FFMA stream | odd-destination FFMA stream | pred/NOP |
|---:|---:|---:|---:|
| 32 (R40, even only) | 60 | 52 | 52 |
| 64 (one word/bank) | 62 | 60 | 52 |
| 128 (two words/bank) | 66 | 64 | 58 |

Both E-only and O-only streams delay the wide loads, unlike LDG.32, which is
delayed only by an E stream.  This directly shows that a wide MIO result
consumes write capacity in both parity banks.  The extra work also delays SB4
release: relative to LDG.32, the unobscured `.64` and `.128` endpoints add 4
and 12 units.

The E stream is normally two units worse than the O stream for `.64/.128` in
the overlap window.  Since both wide destinations start at R40, this is
consistent with a fixed per-word/per-bank submission order, but does not by
itself identify whether the order is in MIO2RF, a per-bank FIFO, or scoreboard
retirement.  At long N the instruction body becomes the timing floor and the
two-unit difference disappears.

### Sustained reads can overlap the 1W completion

`--read-scan N` replaces the FFMA stream with repeated ISETP instructions.
Each ISETP reads two GPRs from one selected parity bank and writes only a
predicate, so it drives sustained same-bank collection without producing GPR
writeback.
At the load-return boundary:

| N | load dst | read-E | read-O | same minus opposite |
|---:|:---:|---:|---:|---:|
| 18 | E | 49 | 48 | +1 |
| 18 | O | 49 | 48 | -1 |

The one-unit E/O difference follows the read instruction encoding/phase, not
the load bank: changing the LDG destination parity reverses the calculated
same-minus-opposite sign.  For N<=16 every combination remains at the 46-unit
load floor; for larger N the same parity-independent pattern continues while
the ISETP body becomes the floor.  Thus sustained reads from the selected bank
do not selectively block its LDG write.  This supports distinct
read-collection and architectural-write service domains rather than one
shared operation slot; it does not count physical read ports.

## Round 4: two independently scoreboarded LDG.32 results

`tests/asm_construct/probe_mio_writeback_burst.py` issues two warmed LDG.32s
to different cache lines, claims SB4 and SB5, and uses one consumer with
`req={4,5}`.  It compares EE/EO/OE/OO destinations while scanning the issue
gap.

Without an ALU storm all four layouts are identical: 50 units for gaps 0--2,
then exactly the instruction-gap timing floor (51, 52, 54, 56, 60, 64 for
gaps 3, 4, 6, 8, 12, 16).  Adjacent hot loads therefore emerge from this MIO
path already ordered far enough apart that destination parity alone does not
make them collide.

An E-only FFMA storm at N=32 and gap 0 gives EE=56, EO=56, OE=54, OO=50; the
O-only mirror gives EE=50, EO=54, OE=56, OO=56.  The earlier load experiences
the larger overlap.  EE never exceeds the slowest mixed layout: the joint
wait observes the maximum of the two scoreboard completion times, with no
additional same-bank burst penalty.  This is a useful negative constraint,
not evidence for a second write port: these two MIO returns were not
simultaneous to begin with.

## Round 5: cross-warp localization to the subcore RF bank

`tests/asm_construct/probe_subcore_rf_writeback.py` is the decisive
localization experiment.  Warp 0 issues a hot `LDG.32 R40` and times its real
SB4 release.  While warp 0 is scoreboard-stalled, a contender issues a dense
reuse-fed FFMA stream:

- warp 4 is on the same subcore as warp 0; warp 1 is the different-subcore
  control (mapping independently established by `test_subcore_yield.py`);
- FFMA destinations are either all even or all odd;
- `@P6 FFMA` retains identical fetch/issue/dispatch and scheduling fields but
  suppresses execution and GPR writeback;
- all active E/O cases use the same E/O/E source registers and reuse mask 7,
  so only destination parity changes.

For each destination parity the score is:

```text
(same_active - same_pred) - (different_active - different_pred)
```

At phase 0, 100 repetitions give these median endpoints:

| FFMA count | same E active/pred | same O active/pred | different E active/pred | different O active/pred | E score | O score |
|---:|---:|---:|---:|---:|---:|---:|
| 16 | 46 / 46 | 46 / 46 | 46 / 46 | 46 / 46 | 0 | 0 |
| 24 | 54 / 47 | 47 / 47 | 46 / 46 | 46 / 46 | **+7** | 0 |
| 32 | 63 / 55 | 55 / 55 | 46 / 46 | 46 / 46 | **+8** | 0 |
| 40 | 67 / 63 | 63 / 63 | 46 / 46 | 46 / 46 | **+4** | 0 |
| 48 | 75 / 71 | 71 / 71 | 46 / 46 | 46 / 46 | **+4** | 0 |
| 64 | 91 / 87 | 87 / 87 | 46 / 46 | 46 / 46 | **+4** | 0 |

The main distribution, not merely the best sample, shifts.  For example at
N=32, same/E/active is 63 in 97/100 runs; its primary control modes are 55 or
57.  All four different-subcore cases are exactly 46 in 100/100 runs.

This localizes the conflict sharply:

1. it crosses warp boundaries, so it is not an intra-warp dependency or
   forwarding artifact;
2. it occurs only for warps mapped to the same subcore;
3. it occurs only when FFMA and LDG target the same destination parity bank;
4. predicated-off and opposite-bank streams reproduce all parity-independent
   scheduler/dispatch delay but not the extra 4--8 units.

The simplest model consistent with all results is two subcore-local GPR banks,
each with one shared architectural write/commit opportunity per service slot.
Fixed-pipeline consumers can receive forwarded values before that commit, which
explains why the original RAW tests did not reveal the collision.  A
scoreboarded MIO producer exposes it because SB4 release tracks actual result
retirement closely enough for an occupied same-bank port to delay it.

### Important scheduler control

`probe_subcore_mio_writeback.py` attempted to align one LDG from each warp by
padding their issue phases.  At phases 23--40, same-subcore victim time rises
linearly with contender padding (47--64) while different-subcore time remains
46.  Replacing the contender LDG plus consumer with two NOPs reproduces every
median and nearly every histogram exactly; E and O destinations are also
identical.  Thus that apparent same-subcore "return conflict" is only shared
scheduler issue occupancy.  Active-minus-control, rather than same-minus-diff
alone, is required for this class of probe.

## Next discriminators

- Use scoreboarded MIO producers, whose completion can be observed through
  `smsp__mio2rf_writeback_active`, and collide their returned registers with a
  calibrated fixed-pipe write.  **Done for LDG.32 + FFMA; extend to other MIO
  producers.**
- Compare `.64`/`.128` destinations.  **Done for LDG; both banks are occupied
  and wider groups release the scoreboard later.  The internal word order is
  still unresolved.**
- Construct completion bursts with one scoreboard wait releasing several MIO
  results together, then sweep destination parity and width.  **Two adjacent
  LDG.32s are done; their naturally ordered returns do not collide.  A future
  version needs independently phase-controlled producers or separate warps.**
- Repeat the return-alignment experiment across two resident warps on one
  subcore.  **Done for LDG-vs-LDG, but NOP control shows only scheduler
  occupancy.  Done successfully for LDG-vs-FFMA: same-bank writeback conflict
  is subcore-local and crosses warp boundaries.**
- Reverse the cross-warp roles (fixed-pipe victim observed through a later
  non-forwardable operation, MIO contender) and test whether arbitration
  priority is symmetric or MIO/fixed-pipe specific.
- Measure latency distributions, not only best-of slopes: a buffered collision
  may appear as a rare +1-cycle tail while leaving steady throughput intact.
- Probe source-read traffic and write completion together.  If collection and
  1W commit are independent, a saturated read stream should not move write latency; a
  shared crossbar/arbitration design may.
