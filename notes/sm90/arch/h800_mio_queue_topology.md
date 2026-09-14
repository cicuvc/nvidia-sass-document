# H800/H20 MIO queue and late-RF throughput probes

Silicon: H800 PCIe and H20 (sm_90), 2026-09-14.  These measurements use
hand-built sm_90 cubins and `SR_CLOCKLO`; NCU permission was unavailable on
both remote systems (`ERR_NVGPUCTRPERM` was confirmed explicitly on H20).
Consequently the results identify throughput, admission knees, placement
scope, and shared credits, but do not attach hardware-counter names to them.

Harnesses:

- `tests/asm_construct/probe_mio_scaling.py`
- `tests/asm_construct/probe_mio_topology.py`
- `tests/asm_construct/probe_mio_queue_depth.py`

## Long-stream topology

Warp-to-subcore placement is `warp_id % 4`.  Rates below are aggregate warp
instructions per clock over the common timed interval.

| stream | one warp | same-subcore 2 | different-subcore 2 | four subcores | all 8 warps |
|---|---:|---:|---:|---:|---:|
| LDS `[RZ]` | 0.497 | 0.978 | 0.976 | 0.993 | 0.989 |
| one-source SHFL | 0.497 | 0.497 | 0.976 | 0.988 | 0.987 |
| MUFU.RCP | 0.125 | 0.125 | 0.249 | 0.494 | 0.497 |
| BMOV/CBU | 0.252 | 0.495 | 0.497 | 0.979 | 0.988 |

The H800 shared LSU path sustains approximately **1 warp request/clock**
across enough subcores, twice the approximately 0.5 measured on GB202.  One
warp can present only about 0.5.  Two zero-source LDS warps can fill the LSU
rate even on one subcore.  One-source SHFL instead stays at 0.5 on the same
subcore and reaches 1.0 only when split across subcores; this is the local RF
collector below, not a weaker SHFL exchange backend.

XU remains local: one subcore sustains approximately 0.125 MUFU/clock and four
subcores approximately 0.5.  A second warp on the same subcore only shares
that rate.  CBU reaches approximately 0.25 with one warp, 0.5 with two warps,
and has an SM-wide ceiling near 1.0.

## Late GPR operand collection

A same-subcore active one-source MUFU contributes approximately 0.125
warp-wide GPR operands/clock.  Zero-source, one-, two-, and three-source
victims isolate the remaining collector bandwidth:

| victim | GPR sources | control clocks/inst | same-subcore MUFU | different-subcore MUFU |
|---|---:|---:|---:|---:|
| SHFL from RZ | 0 | 2.039 | 2.023 | 2.027 |
| SHFL RII | 1 | 2.039 | 2.590 | 2.027 |
| SHFL RRI | 2 | 3.898 | 5.133 | 3.898 |
| SHFL RRR | 3 | 5.824 | 7.695 | 5.820 |
| LDS `[RZ]` | 0 | 2.039 | 2.023 | 2.027 |
| LDS `[Rreg]` | 1 | 2.039 | 2.574 | 2.027 |
| LDG `[Rlo:Rhi]` | 2 | 3.898 | 5.133 | 3.898 |

For the active same-subcore cases,
`sources / victim_cycles + 0.125` gives 0.511, 0.515, and 0.515 operands/clock
for one/two/three-source SHFL.  The H800 therefore has approximately **0.51
warp-wide 32-bit GPR operands/clock per subcore**, effectively the same as
GB202.  False-predicate or different-subcore MUFU has no effect.  H800's lower
observed MIO-pressure tendency is not explained by a wider late-RF collector.

## Effective queue capacities

### XU

A dead-result `MUFU.RCP Rd,RZ` burst accepts two instructions at the frontend
`+2`-clock cadence; the third stalls and steady state is +8 clocks/request.
Two same-subcore warps accept their first request each, then cost +16 clocks
per N (two requests).  The effective XU admission pool is therefore about
**2 requests/subcore**, the same as GB202.

### Local LSU

Four subcores running one-wavefront LDS remain at +2 clocks/N through N=16
and enter the aggregate +4-clock steady state at N=17.  Eight warps (two per
subcore) transition near N=6--7 to +8 clocks/N.  Accounting for each
subcore's fair share of the approximately 1-request/clock SM drain, both
curves imply about **8 local LSU backlog credits/subcore**.  GB202 exposes
about four.

Coalesced LDG independently reproduces this value.  Each LDG has two late GPR
address operands, so a warp arrives at 0.5 request/clock but leaves the local
collector at about 0.25.  It remains frontend-fast through N=15, transitions
at N=16, and then costs +4 clocks/request: approximately eight requests of net
backlog.

### Common post-MIOC LSU pool

A one-warp 32-way-conflict LDS burst remains frontend-fast through N=30,
partially blocks at N=31, and then costs +64 clocks/request.  Inserting
zero-source SHFL requests after the first long LDS shifts this knee exactly
one-for-one:

| inserted SHFL M | first blocked LDS N | N + M |
|---:|---:|---:|
| 0 | 31 | 31 |
| 4 | 27 | 31 |
| 8 | 23 | 31 |
| 16 | 15 | 31 |

Thus H800 has approximately **30 post-MIOC LSU request credits**, and SHFL
consumes one credit just like LDS.  GB202 has approximately 17--18.

Four subcores issuing the same long LDS block near N=16 per warp, after about
60 total instructions have entered.  This matches `4*8 + 30 = 62` local plus
downstream credits.  The final +128 clocks/N drains 128 data wavefronts, or
approximately one aggregate wavefront/clock.  A single request stream drains
at only approximately 0.5 wavefront/clock.

Scattered LDG gives the same capacity decomposition without NCU.  With one
128-byte line per lane, one warp first hits the local two-operand collector
knee at N=16, remains at +4 clocks/request through N=35, and then costs +32.
The roughly 35 accepted requests minus eight local credits leaves 27; four
subcores block after roughly 60 total requests, minus 32 local credits leaves
28.  No earlier independent global-only admission limit is visible.  LDS,
SHFL, and global traffic therefore share an approximately 28--30-entry
post-MIOC credit/backpressure domain, although this does not prove one literal
mixed physical FIFO.

### CBU

CBU does not yield one placement-independent FIFO depth.  A single warp
accepts 12 BMOVs at +2 clocks before settling at +4; two different-subcore
warps remain fast through N=10 each, four through N=8 each, and eight through
N=3 each.  Long-stream throughput is unambiguous (0.25 one warp, 0.5 two,
approximately 1.0 SM-wide), but the admission window combines per-warp
latency hiding, local state, and an SM-wide backend.  It should not be labeled
as an exact physical queue depth from these data.

## Hopper versus GB202 summary

| observable | H800 sm_90 | H20 sm_90 | RTX 5090 sm_120 |
|---|---:|---:|---:|
| shared LSU aggregate requests/clock | ~1.0 | ~1.0 | ~0.5 |
| aggregate LSU data wavefronts/clock | ~1.0 multi-stream | ~1.0 multi-stream | ~1.0 multi-stream |
| one-stream data wavefronts/clock | ~0.5 | ~0.5 | ~0.5 |
| local LSU backlog credits/subcore | ~8 | ~8 | ~4 |
| post-MIOC LSU credits/SM | ~30 | ~30 | ~17--18 |
| late GPR operands/clock/subcore | ~0.51 | ~0.51 | ~0.50 |
| XU credits/subcore | ~2 | ~2 | ~2 |
| XU throughput/subcore | ~0.125 | ~0.125 | ~0.125 |

The practical difference is consequently concentrated in LSU request
admission and buffering: Hopper has about twice the SM-wide request rate, twice
the local backlog capacity, and nearly twice the downstream credits.  Its
late-RF and XU limits are essentially unchanged.  This combination directly
explains why ordinary Hopper kernels are less likely to expose MIO throttle
from LDS/SHFL mixtures than the same schedules on GB202.

## Independent H20 reproduction

The complete topology matrix and targeted queue knees were repeated on an H20
(sm_90, driver 580.105.08) using the identical cubin generator and schedules.
Long-stream results are **identical to H800 at every reported median clock**:

| stream | one | same-subcore 2 | different-subcore 2 | four subcores | all 8 |
|---|---:|---:|---:|---:|---:|
| LDS `[RZ]` | 0.497 | 0.978 | 0.976 | 0.993 | 0.989 |
| one-source SHFL | 0.497 | 0.497 | 0.976 | 0.988 | 0.987 |
| MUFU | 0.125 | 0.125 | 0.249 | 0.494 | 0.497 |
| BMOV/CBU | 0.252 | 0.495 | 0.497 | 0.979 | 0.988 |

The late-RF values differ only by a few clocks over 256 instructions.  Under
a same-subcore active MUFU, one/two/three-source SHFL takes 2.598/5.152/7.695
clocks per instruction, yielding 0.510/0.513/0.515 total GPR operands/clock
after adding MUFU's 0.125.  Zero-source SHFL and LDS remain at 2.027; register-
addressed LDS is 2.594 and LDG is 5.117.  Different-subcore and false-predicate
controls remove the slowdown exactly as on H800.

Every capacity boundary also reproduces H800 exactly:

- XU: two fast admissions, third MUFU blocks; about 2 credits/subcore.
- Local LSU: four-subcore LDS changes +2 to +4 at N=17; eight-warp LDS reaches
  +8 at N=7; about 8 credits/subcore.
- Long LDS: N=30 remains fast, N=31 partially blocks, N=32 costs +64; about 30
  common post-MIOC credits.
- SHFL substitution: M=0/4/8/16 moves the first blocked LDS to
  N=31/27/23/15, preserving `N+M=31` exactly.
- Coalesced LDG changes +2 to +4 at N=16--17.  Scattered LDG changes +4 to
  +32 at N=36--37; four subcores change to +128 at N=16--17.  The same
  `8 local + about 28 downstream` decomposition applies.
- CBU: one-warp N=13, four-subcore N=9, and eight-warp N=4 admission knees are
  identical to H800, including their steady +4/+4/+8 slopes.

No tested MIO structural parameter distinguishes H20 from H800.  Within the
resolution of these probes, the two Hopper products use the same LSU, SHFL,
late-RF, XU, and CBU configuration; their product-level performance
differences lie elsewhere.
