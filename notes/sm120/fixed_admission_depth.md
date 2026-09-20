# GB202 fixed scalar-pipeline admission windows

Silicon: RTX 5090 (GB202, sm_120), 2026-09-21.  Probe:
[`probe_scalar_admission_depth.py`](../../tests/asm_construct/probe_scalar_admission_depth.py).
Cubins are emitted directly by the repository assembler; ptxas is not used.

## Corrected construction

The old one-warp `CS2R; burst; CS2R` experiment could not measure these
depths.  One warp supplies the tested operation at least as slowly as the
relevant service/retirement path, so it does not build a backlog.  Its
apparent one-credit result was a cadence measurement, not an admission-depth
measurement.

The corrected experiment uses producer warps 0 and 4 on one subcore and an
observer warp 1 on another.  After a common start barrier, each producer
issues N independent operations and reaches a counted `BAR.SYNC` on MIO/CBU;
only the clean-subcore observer reads the ending clock.  Two producers can
initially feed the target domain faster than it drains, exposing the point at
which the producer can no longer advance past its final admitted operation.

Targets write `RZ`, use `yield=0`, and use `RZ` sources in the barrier form.
Architecturally-false and active targets give the same curves.  Different-
subcore producer controls retain only the linear service slope and have no
5/12-credit knee.  The measured resources are therefore predicate-
insensitive and subcore-local.  “Credit” remains an effective outstanding
operation; it does not require a literal FIFO cell.

## Homogeneous depths

Four families reproduce the B200 homogeneous results, but GB202 ALU Lite
splits by opcode/form despite every member incrementing the same NCU leaf:

| leaf / subclass | representatives | effective outstanding capacity/subcore |
|---|---|---:|
| ALU Heavy | IADD3, LOP3, SHF | about **12** |
| ALU Lite, register transport/add/select | IADD, MOV, SEL | about **3** alone |
| ALU Lite, other tested forms | IADD32I, MOV32I, MOV64IUR, FMNMX, FSEL, FSET, FSETP, IMNMX, ISETP, VIMNMX, VIADD | **5** |
| FMA Heavy | IMAD.LO, IMUL, FSWZADD | about **12** |
| FMA Lite | FFMA, FADD, FMUL | **5** |
| coupled packed FP16 | HFMA2, HADD2, HMUL2 | about **12** |

ALU Heavy, FMA Heavy, and packed FP16 share the curve
`47,48,50,52,56,...,72,76,80,...`: N=12 is the last filling-region
point, and every additional N from N=13 costs four clocks for the two added
operations.  FMA Lite and the second ALU-Lite subclass give the exact shallow curve
`47,48,49,50,51,52,54,56,...`, with the transition after N=5.
IADD/MOV/SEL instead give `47,49,51,54,58,62,...`: they settle at +4
clocks/N from N=4, corresponding to only about three effective outstanding
operations in a homogeneous stream.

This form split is repeatable under active and false predication.  It is not
a destination-file split: the five-credit group contains both GPR-producing
and predicate-producing operations, while the approximately-three group is
specifically register IADD, register MOV, and SEL.  Notably, immediate IADD32I
and MOV32I are in the five-credit group.

## Mixed-leaf matrix

Both producers were then changed to alternate the two named leaves, using
register `IADD` as the initial ALU-Lite representative.  N is
still the number of operations per producer; an even N therefore contributes
N total operations from each leaf across the two warps.

Seven of ten pairs reproduce B200 almost cycle for cycle:

| alternating pair | GB202 result | B200 result |
|---|---:|---:|
| ALU Heavy + ALU Lite | ~12 | ~12 |
| ALU Heavy + FMA Heavy | 5 | 5 |
| ALU Heavy + FMA Lite | 5 | 5 |
| ALU Heavy + FP16 | 5 | 5 |
| FMA Heavy + FMA Lite | 5 | 5 |
| FMA Heavy + FP16 | ~12 | ~12 |
| FMA Lite + FP16 | ~12, phase-irregular | ~12, phase-irregular |

The three pairs containing ALU Lite and a non-ALU leaf are the generational
difference:

| alternating pair | GB202 | B200 |
|---|---|---|
| ALU Lite + FMA Heavy | deep ~12 boundary; then alternating +6/+2 clocks/N | exact 5-credit curve |
| ALU Lite + FP16 | identical to ALU Lite + FMA Heavy | exact 5-credit curve |
| ALU Lite + FMA Lite | mixed-service transition near N=5; then alternating +4/+2 clocks/N | exact 5-credit curve |

The first two deep curves agree with GB202's physical hierarchy: the
ALU-Lite leaf is inside the **Shared FMA Heavy** macro-pipe beside the
FMA-Heavy leaf, while packed FP16 occupies FMA Heavy and FMA Lite together.
On B200 the supplied counter hierarchy treats ALU Lite as the peer of ALU
Heavy for this admission experiment instead.  Register IADD + FMA Lite has
no shared execution leaf on GB202; its +4/+2 alternation is a cross-leaf
steering/service effect, so this experiment does not assign it a clean
standalone 5- or 12-credit FIFO depth.

The result is not uniform across the ALU-Lite leaf.  Replacing IADD by ISETP
changes every tested mixed pair to a shallow approximately-five-credit/service
curve: ALU Heavy + ISETP and ISETP + FMA Lite reproduce the exact five-credit
curve, while ISETP + FMA Heavy/FP16 reach their steady +2 clocks/N by about
N=5.  IADD32I + FMA Heavy behaves like ISETP, whereas MOV + FMA Heavy and SEL
+ FMA Heavy reproduce register IADD's deep curve.  Thus the two homogeneous
ALU-Lite subclasses also remain distinct under substitution.

The effective GB202 relationship is consequently not one flat queue:

```text
ALU admission relation:            ALU Heavy -- register IADD/MOV/SEL (~12 mixed)
Shared-FMA-Heavy relation:          register IADD/MOV/SEL -- FMA Heavy (~12 mixed)
packed-FP coupled domains:         FMA Heavy -- FP16 -- FMA Lite (~12)

cross-domain Heavy pairs expose a common ~5-credit admission window
fast ALU-Lite forms and FMA Lite have 5-credit homogeneous curves
register IADD/MOV/SEL have only ~3 effective credits alone
```

The register-transport ALU-Lite subclass participates in both a logical-ALU
admission relationship and the physical Shared-FMA-Heavy relationship.
Packed FP16 similarly occupies both FMA leaves.  Queue ownership is therefore
not a partition of mnemonics into five independent leaf FIFOs; even one NCU
leaf contains at least two observably different admission classes.

## NCU cross-check

NCU 2026.3.0 was run as root with 170 CTAs to amplify the short-burst events.
The probe's `--grid 170` option exists for this purpose.  Exact target-count
increments reconfirm the leaf classification:

| instruction | leaf counters incremented |
|---|---|
| IADD3 | `aluheavy` |
| IADD | `fmaheavy_subpipe_alulite` |
| IMAD | `fmaheavy_subpipe_fmaheavy` |
| FFMA | `fmalite` |
| HFMA2 | FMA Heavy + FMA Lite + FP16 type |

At N=12, the aggregate `math_pipe_throttle` samples divided by 170 CTAs are:

| alternating pair | samples/CTA (approximately) |
|---|---:|
| ALU Heavy + ALU Lite | 11.0 |
| ALU Heavy + FMA Heavy | 0.35 |
| ALU Lite + FMA Heavy | 22.9 |
| ALU Lite + FMA Lite | 0.70 |
| ALU Lite + FP16 | 22.6 |
| FMA Heavy + FMA Lite | 0.34 |
| FMA Heavy + FP16 | 23.0 |
| FMA Lite + FP16 | 25.1 |

The ALU-Lite form split also appears directly in the throttle counter:

| stream at N=12 | math-pipe-throttle samples/CTA |
|---|---:|
| homogeneous register IADD | 21.3 |
| homogeneous ISETP | 0 |
| register IADD + FMA Heavy | 22.7 |
| IADD32I + FMA Heavy | 3.6 |
| ISETP + FMA Heavy | 3.7 |

IADD, IADD32I, and ISETP all increment
`fmaheavy_subpipe_alulite`; the admission/throttle split exists below that
counter label rather than being a misclassified execution leaf.

This separates execution/physical-leaf pressure from the cross-domain
five-credit timing boundary, while also showing that merely sharing the
ALU-Lite counter is insufficient to predict throttle.  Independent leaf
pairs have only the near-zero sampling residue, even when the naked timing
curve has the five-credit knee.  `dispatch_stall` is exactly zero for all
profiled pairs.  A sweep of every scheduler stall reason found no precise
counter for the five-credit event; the profiler mostly reports the waiting
warp as `no_instruction`, mixed with barrier and inactive-scheduler time.

Thus the five-credit boundary is best described as an upstream effective
admission/backpressure window, not as saturation of either named execution
leaf.  Conversely, register-IADD's deep mixed relationships and the packed-FP
relationships are corroborated by strong `math_pipe_throttle`.
NCU replay perturbs the in-kernel `CS2R` spans, so all credit depths above are
from unprofiled runs; NCU is used only for counter classification.
