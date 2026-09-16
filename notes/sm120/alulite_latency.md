# GB202 ALU-Lite pipeline latency

Silicon: RTX 5090 (GB202, sm_120), 2026-09-16.  Reproducer:
[`probe_alulite_latency.py`](../../tests/asm_construct/probe_alulite_latency.py).

```bash
python3 tests/asm_construct/probe_alulite_latency.py --isolated --reps 3
```

## Scope

This is the first simulator-facing fixed-latency calibration.  It covers the
common ALU-Lite instructions `FMNMX`, `FSEL`, `FSET`, `FSETP`, `IADD`,
`IADD32I`, `IMNMX`, `ISETP`, `MOV`, and `SEL`.  NCU previously established
that they execute on `fmaheavy_subpipe_alulite`; this note measures when their
GPR and predicate results become visible to particular consumers.

The latency dump alone is insufficient for a cycle model.  Its
`DUALALU_OPS` row gives a conservative GPR RAW separation of 6 for the scalar
math columns.  For predicate results it gives 6 to ordinary math predicate
readers but 14 to branch/non-math readers.  Silicon exposes earlier, distinct
forwarding points.

## Method

Every test first settles a poison destination, issues one ALU-Lite producer,
and then lets a consumer observe the destination after a controlled nominal
issue gap.  The consumer result distinguishes the old poison from the new
value.  No dependency barrier is used, because fixed-latency RAW correctness
is the scheduler's responsibility and a barrier would obscure the forwarding
boundary.

Two equal nominal-gap shapes are tested:

- **fine:** `gap-1` separate stall-1 NOPs;
- **coarse:** as few NOPs as possible, carrying a larger stall count.

The reported boundaries were confirmed with `--isolated`, which compiles one
module per gap so the producer has a fixed instruction position and earlier
instances cannot change its PC/fetch phase.  The default combined mode is a
much faster survey but should not be used to interpret isolated early windows.

The distinction matters.  A few paths have issue-group/alignment-sensitive
windows even when the sum of the encoded stalls is the same.  `permanent` in
the raw output means the first fresh observation after which every larger gap
is also fresh.  It is the useful safe boundary; an isolated earlier fresh
sample is not a general bypass guarantee.

## GPR results

| producer | ALU Lite `MOV` consumer | ALU Heavy `IADD3` consumer | FMA Lite `FADD` consumer |
|---|---:|---:|---:|
| `FMNMX` | 2 | 2 | 2 |
| `FSEL` | 2 | 2 | 2 |
| `FSET` | 2 | 2 | 2 |
| `IMNMX` | 2 | 2 | 2 |
| `SEL` | 2 | 2 | 2 |
| `MOV` | 2 | 3 fine / **4 safe coarse** | 2 |
| `IADD` | 2 | 3 fine / **4 safe coarse** | 2 |
| `IADD32I` | 2 | 3 fine / **4 safe coarse** | 2 |

All values are nominal producer-to-consumer issue gaps.  Gap 1 reads the old
destination on every tested edge.  Thus ALU Lite has a genuine result bypass,
normally visible at gap 2, far earlier than the table value 6.

`MOV` and the legacy adders have a narrower path to ALU Heavy.  Before its
permanent boundary, isolated `MOV -> IADD3` can return launch/residue garbage
rather than merely the old destination.  At the intermediate invalid schedule
points `IADD/IADD32I -> IADD3` reproducibly expose the addend `Ra`
(`0x3f7fffff`) instead of either the old destination (`0x40000000`) or the
finished sum (`0x3f800000`).  This is strong evidence that the observed value
is a pipeline/operand-routing transient, not delayed RF commit.  A functional
simulator may classify underscheduled reads as undefined; a microarchitectural
simulator attempting to reproduce malformed SASS can model a pre-adder/pass-
through payload on that edge.

The result is incompatible with one global "ALU latency".  At minimum the
model needs a producer-family/result tag and a consumer collection point.

## Predicate results

`FSETP`, `ISETP`, and the carry predicates (`Pu`) produced by `IADD` and
`IADD32I` are indistinguishable at their permanent boundaries:

| predicate consumer | fine permanent boundary | coarse permanent boundary | interpretation |
|---|---:|---:|---|
| ALU-Lite selector operand (`SEL ..., P0`) | 3 | **4** | local math-predicate forwarding |
| ALU-Heavy predicate-file read (`P2R ..., PR`) | 3 | **4** | local predicate read/forwarding |
| instruction guard (`@P0 MOV32I`) | 7 | **12** | effective-predicate issue distribution |
| CBU branch (`@P0 BRA`) | 7 | **12** | effective-predicate/CBU distribution |

The primary predicate destination was tested.  `FSETP`'s second/complementary
destination is expected to share the same production event but still needs a
separate alias/output-port check before being marked proven.

The guard and branch paths can also contain isolated early fresh windows whose
position depends on the producer, filler shape, and surrounding code layout.
Adding the `P2R` cases to the same generated kernel removed a window visible in
an earlier layout; the older equality-compare branch probe shows yet another
window.  These are alignment effects, not a monotonic ready time.

The adders' GPR and carry-predicate outputs therefore have independent timing:
their GPR sum reaches the usual local bypass at gap 2 (except for the special
ALU-Heavy consumer edge), while `Pu` follows the predicate timings above.

The `P2R` result rules out a simple "predicate file itself is slow" model.
Both an ALU-Lite selector and the ALU-Heavy predicate-file transfer see the
new value at gap 3--4, while an instruction guard and CBU do not see stable
state until 7/12.  Therefore predicate production has at least two observable
destinations:

```text
ALU-Lite compare
    +--> local predicate read/forwarding (SEL, P2R) ready 3 fine / 4 safe
    `--> effective guard / CBU distribution         ready 7 fine / 12 coarse
```

Treating a predicate write as ordinary GPR writeback would be substantially
wrong for branch timing.

## Initial simulator parameters

For correctly scheduled SASS, a conservative first implementation is:

```text
ALU-Lite GPR -> ALU-Lite or FMA-Lite input:       ready = issue + 2
most ALU-Lite GPR -> ALU-Heavy input:             ready = issue + 2
MOV/IADD/IADD32I GPR -> ALU-Heavy input:          ready = issue + 4
FSETP/ISETP/IADD-Pu -> selector/P2R input:        ready = issue + 4
FSETP/ISETP/IADD-Pu -> instruction guard/CBU:     ready = issue + 12
```

These are **consumer-visible ready times**, not final RF/PRED-file commit
times and not initiation intervals.  Operand collection, execution occupancy,
result-queue residence, and final parity-bank write arbitration remain
separate state in the simulator.  In particular, the static latency table's
6/14 values should remain available as conservative scheduling metadata, but
must not replace the measured bypass-ready events.

The next fixed-latency work should add ALU Heavy, FMA Lite, FMA Heavy, and
packed-FP producers to the same consumer matrix, then locate architectural RF
commit independently by suppressing or bypassing the local forwarding paths.
