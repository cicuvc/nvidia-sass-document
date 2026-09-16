# GB202 FP64 / CLMAD redirect latency

Silicon: RTX 5090 (GB202, sm_120), 2026-09-17.  Reproducer:
[`probe_fp64_latency.py`](../../tests/asm_construct/probe_fp64_latency.py).

This domain is deliberately separated from the true fixed-latency scalar
leaves.  `DADD/DMUL/DFMA/DSETP/CLMAD` use a redirectable admission path into
one SM-shared FP64 backend.  Their result must be protected with a scoreboard;
a constant no-scoreboard stall is not a generally valid dependency rule.

## Isolated unsafe-schedule observations

Each row below uses one producer in a fresh CUDA context, poisons both result
halves, omits the required scoreboard wait, and observes one half through an
ALU-Lite consumer.  Low and high halves always agree.

| producer | fine stall-1 NOP stream: permanent fresh boundary | coarse few-NOP layout |
|---|---:|---|
| `DADD` | nominal gap **16** | stale through 40; permanent fresh from 48 |
| `DMUL` | nominal gap **16** | stale through 40; permanent fresh from 48 |
| `DFMA` | nominal gap **20** | stale/non-stable through 48; fresh from 56 |
| `CLMAD.LO` | nominal gap **20** | non-monotonic phase window; permanently fresh from 56 in the tested sweep |

The tested gaps were `8,12,16,20,24,28,32,40,48,56,64`.  `CLMAD` could be
fresh at one shorter coarse layout and stale again at a longer nominal gap.
That is decisive evidence against treating these numbers as arithmetic
pipeline latencies.

A combined multi-instance kernel is even less suitable: outstanding
redirected operations overlap, successive producers reuse the same
destination pair, and later observations can see completions from another
instance.  The probe retains the combined mode because it is useful for
studying completion ordering, but `--isolated` is mandatory for the table
above.

## Simulator consequence

Model this path as:

```text
subcore redirect/admission credits (7 usable measured)
        -> one SM-shared FP64 service
        -> asynchronous two-GPR / predicate completion
        -> scoreboard release
```

Do not put `16` or `20` into the ordinary fixed-latency bypass table.  Those
are favorable issue-layout observations after an empty redirect path, not an
architectural guarantee.  Correct execution waits for the producer's write
scoreboard; queue occupancy, SM-wide arbitration, and completion release
determine the actual cycle.  The previously measured approximately
18--19-clock service cadence and seven usable admission credits describe
throughput/backpressure, while this probe shows why completion timing needs
an event-driven scoreboard model.
