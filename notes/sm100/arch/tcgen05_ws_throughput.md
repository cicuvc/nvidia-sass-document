# B200 WS throughput and B collector: CUDA/PTX (2026-11-17)

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

**Evidence:** sm100-silicon, Modal NVIDIA B200
**Probe:** `tests/tcgen05_ws_throughput.cu`
**Runner:** `tools/modal_tcgen05_ws.py`
**Analysis:** `tools/analyze_tcgen05_ws_throughput.py`

Follow-up: [handwritten SASS controls](tcgen05_ws_sass_throughput.md) remove
per-MMA election, separate buffer ID from B address, and test A from TMEM.
The results below remain the CUDA/PTX measurements.

## Conclusion

Explicit PTX election removes compiler retry-loop overhead. B reuse reaches the 4096 MAC/cycle/SM baseline for the listed larger WS shapes and reduces shared-load contention. The completion slopes and contention meter do not provide exact physical shared-read byte counts.

## Evidence

## Measurement protocol

Dense BF16×BF16→FP32, K16, A/B in shared, one CTA of 160 threads. One issuing
warp, four TMEM reader warps, and optional shared contenders on warps 1–4.
The validated [WS layouts](tcgen05_ws_behavior.md) determine the full output
footprint. Every measured launch checks all output elements; contender launches
also verify the sum of all loaded values. A=1 and B buffers=1,2,3,4; expected
D is 16×ops for one-buffer modes and 40×ops for four-buffer rotation. D starts
at zero and all timed MMA instructions accumulate.

Each configuration gets one unreported warmup followed by five samples. MMA
`clock64` timing starts before the first MMA and ends after one commit and
mbarrier completion wait. Initialization, allocation, output validation and
release are outside timing. Lengths 256/1024/4096 separate fixed overhead;
the reported slope is `(median(T4096)-median(T256))/3840`. One MAC is two FLOPs.
No SASS has been written, patched or reassembled; cuobjdump is inspection only.

Modes:

| ID | sequence |
|---:|---|
| 0 | b0 discard each instruction |
| 1 | b0 fill each instruction (forces refetch) |
| 2 | b0 fill, use stream, lastuse |
| 3 | b0→b3 rotation, discard each instruction; four distinct B addresses |
| 4 | fill b0→b3, use rotation, lastuse b0→b3 |

All modes have exactly the same MMA count. The first/last four instructions
bracket a statically expanded loop (default eight MMAs); additional U4/U16/U32
controls use the same total count. ptxas may further unroll this loop.

## Explicit PTX election: current result

The retry completed on CUDA 12.8.93 / Modal B200: **1242 launches, zero errors**,
including full-output and LDS-sum checks. [Raw samples, exact source, flags and
SASS excerpt](data/tcgen05_ws_throughput_elect_20261117.json.gz).

With `-DWS_EXPLICIT_ELECT`, all lanes of issuing warp 0 enter the sequence;
each inline PTX block uses `elect.sync` and predicates its MMA on the elected
thread. cuobjdump confirms the per-MMA retry loops disappear. Remaining
`BRA.U.ANY` loops belong to commit lowering (one per kernel), not each MMA.
This remains entirely CUDA/PTX, with no binary changes.

Cycles/MMA from the same 256→4096 completion slope, unroll=8:

| M | N | discard | refill | reuse b0 | rotate discard | rotate reuse | reuse MAC/cycle |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 64 | 28 | 28 | 16.594 | 24.125 | 16.594 | 1975 |
| 32 | 128 | 44 | 44 | 19.031 | 40 | 19.031 | 3444 |
| 32 | 256 | 76 | 76 | **32** | 72 | **32** | **4096** |
| 64 | 64 | 32 | 32 | 23.531 | 32 | 23.531 | 2785 |
| 64 | 128 | 48 | 48 | **32** | 48 | **32** | **4096** |
| 64 | 256 | 80 | 80 | **64** | 80 | **64** | **4096** |
| 128 | 64 | 48 | 48 | 39 | 48 | 39 | 3361 |
| 128 | 128 | 74 | 74 | **64** | **64** | **64** | **4096** |
| 128 | 256 | 138 | 138 | **128** | **128** | **128** | **4096** |

**M32 is not intrinsically half-throughput in these experiments.** At N256,
M32's 131072 MACs take 32 cycles with B reuse, reaching the same 4096 MAC/cycle
(8192 FLOP/cycle) as M64N128 and M128N128. M32N64 is about half that effective
rate in this program, but M32N128 is already about 84%, and M32N256 reaches it.
The N64 results for M64/M128 also fall below that baseline; shape, operand
fetch and remaining compiler scheduling must be separated before asserting
an intrinsic arithmetic limit.

For M32N128 reuse, increasing unroll from 4/8/16/32 gives measured 4096-op
averages of 20.1895/19.1150/18.8726/18.8545 cycles/MMA. Thus even explicit
thread election has remaining issue/scheduling sensitivity in the short cases;
19.031 is a measured program slope, not a demonstrated 19-cycle tensor wave.
M64N128 reuse stays ~32.05–32.14 and M128N128 ~64.05–64.06 across these controls.
No claim of an exact peak for every small shape is made.

The no-reuse values also have a useful payload correspondence. BF16 K16 A+B
occupies `(M+N)/4` logical 128-byte wavefronts. M64 discard takes exactly
32/48/80 cycles for N64/128/256, matching that operand count. Rotating discard
at M128N128 takes64, also matching operand count; M128N256 takes128, above its
96-wavefront payload and at the measured compute floor. M32 rotation takes
~24/40/72, matching its payload count. This is consistent with a common
128-byte/cycle operand service, but is not an independent proof of physical
broadcast multiplicity. The extra4 cycles for single-buffer M32 discard and
extra10 for single-buffer M128N128/N256 require buffer/address controls before
being assigned a mechanism.

### Collector effect on the shared contender

LDS-only common span is150155 cycles (0.873 wavefront/cycle). With1024 MMAs:

| M | N | LDS span, discard | LDS span, reuse | saved cycles/MMA | logical B wavefronts/MMA |
|---:|---:|---:|---:|---:|---:|
| 32 | 64 | 171108 | 151838 | 18.82 | 16 |
| 32 | 128 | 186026 | 156291 | 29.04 | 32 |
| 32 | 256 | 218325 | 155443 | 61.41 | 64 |
| 64 | 64 | 180221 | 163538 | 16.29 | 16 |
| 64 | 128 | 198137 | 160612 | 36.65 | 32 |
| 64 | 256 | 230693 | 159569 | 69.46 | 64 |
| 128 | 64 | 198150 | 177161 | 20.50 | 16 |
| 128 | 128 | 209912 | 172448 | 36.59 | 32 |
| 128 | 256 | 239251 | 173691 | 64.02 | 64 |

The same qualitative conclusion survives the lowering change: B reuse reduces
shared contention, with the saved time broadly scaling with N; refill matches
discard. At N256, reuse leaves LDS span near155k/160k/174k as M rises32→64→128,
consistent with remaining A traffic increasing with M. The partially saturated
meter and overlapping-client scheduling prevent exact byte accounting.

Single-buffer and four-buffer reuse have the same standalone slope for all nine
shapes. Four collectors support several B streams without an observed throughput
penalty here, but do not increase the measured arithmetic ceiling. Since mode3
rotates both buffer IDs and B addresses, its benefit over mode0 must not be
attributed to either change in isolation.

## Reproduction

```bash
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_tcgen05_ws.py --source tests/tcgen05_ws_throughput.cu --reps 5 --output /tmp/tcgen05-ws-throughput
python3 tools/analyze_tcgen05_ws_throughput.py /tmp/tcgen05-ws-throughput/result.json
```

Explicit-election reproduction (recommended for further throughput probes):

```bash
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_tcgen05_ws.py --source tests/tcgen05_ws_throughput.cu --nvcc-flags=-DWS_EXPLICIT_ELECT --reps 5 --output /tmp/tcgen05-ws-elect
python3 tools/analyze_tcgen05_ws_throughput.py /tmp/tcgen05-ws-elect/result.json
```

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
