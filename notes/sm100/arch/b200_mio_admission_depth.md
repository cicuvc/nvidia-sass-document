# B200 MIO-side admission windows

Silicon: B200 (sm_100), Modal, 2026-09-20.  The main harness is
`tests/asm_construct/probe_sm100_mio_admission_modal.py`, which assembles
sm_100a cubins from `probe_mio_queue_depth.py` and measures a short burst
between two `SR_CLOCKLO` reads.  Instructions use rotating dead destinations;
the ending timestamp has no result dependency.  A change from the frontend
issue slope to the backend drain slope locates backpressure.

These are **effective usable admission/backlog credits**, not necessarily the
number of cells in a literal FIFO.  A distributed reservation table, tagged
warp slots, or credits for a downstream shared queue can produce the same
curve.  In particular, a stream whose arrival and service cadences are equal
has no measurable burst window even if storage exists physically.

Warp placement uses the established `warp_id % 4` subcore mapping.

## Summary

| path | B200 observation | narrow interpretation |
|---|---|---|
| local LSU | about **8 requests/subcore** | four-subcore LDS and coalesced LDG knees agree |
| post-MIOC LSU | about **28--30 requests/SM** | long-conflict LDS and scattered LDG decomposition agree |
| XU | about **2 requests/subcore** | third one-warp MUFU admission blocks |
| SHFL | about **8 backlog credits/subcore**, ~1 request/SM/clock drain | four- and eight-warp knees agree |
| CBU | 12/warp alone, 8/warp with four subcores, 3/warp with eight warps | no placement-independent scalar depth |
| FP64 (`DADD`, `DFMA`) | no separable fast-admission window; isolated from SHFL | service already matches the +2-cycle frontend cadence |
| UTCHMMA | about **6 usable instructions/subcore** | shared by same-subcore warps; independent of N8 versus N128 |

## LSU

Four different subcores issuing conflict-free scalar `LDS [RZ]` give:

- `T(N)=6+2N` through N=16;
- N=17 takes 41 clocks instead of 40;
- N>=18 settles at +4 clocks per N (four requests).

Eight warps, two per subcore, remain at the +2-clock frontend slope through
N=5, are partially blocked at N=6, and settle at +8 clocks/N from N=7.  After
accounting for each subcore's share of the approximately one-request/clock
SM-wide drain, both placements imply about **8 local backlog credits per
subcore**.

Coalesced `LDG` supplies an independent operand-collector control.  Its
two-register address makes one warp arrive at +2 clocks/request but leave the
local collector at +4.  The curve is +2 through N=15, partially transitions at
N=16, and is +4 from N=17, again giving roughly eight requests of net local
backlog.

A one-warp, 32-way-conflict LDS burst isolates the slower downstream data
service.  N=29 still takes 63 clocks (`5+2N`), N=30 jumps to 92, and every
additional instruction costs 64 clocks.  Thus the first blocking admission is
at N=30 and the common post-MIOC domain is approximately **29--30 requests per
SM** at this experiment's boundary resolution.

Scattered LDG (one 128-byte line per lane) gives the same decomposition by a
different route.  It costs +4 clocks/request through N=34, partially blocks at
N=35, and then costs +32.  Approximately 35 total accepted requests minus the
roughly eight local credits leaves about 27 downstream.  Taken together, the
LDS and LDG bounds support **about 28--30 common post-MIOC credits**.  They do
not by themselves prove that LDS, LDG, and SHFL occupy one physical mixed
FIFO.

## XU

For active dead-result `MUFU.RCP Rd,RZ`, one warp gives:

| N | 0 | 1 | 2 | 3 | 4 and later |
|---:|---:|---:|---:|---:|---:|
| clocks | 5 | 7 | 9 | 19 | +8/request |

The first two requests enter at the +2 frontend cadence and the third waits
for service.  Two same-subcore warps accept one request each before the common
span changes to +16/N.  The effective pool is therefore **about two XU
requests per subcore**, shared rather than replicated per warp.

## SHFL

Active dead-result SHFL has no one-warp knee through N=60 because its
half-instruction/clock arrival rate is below the shared service rate. Four
different-subcore streams expose the queue: N=16 remains at the +2-clock
frontend slope, N=17 is transitional, and N>=18 adds four clocks per round of
four requests. Eight warps remain fast through N=5, transition at N=6, and
then add approximately eight clocks per round. Both curves imply an aggregate
drain near **one SHFL warp-instruction per SM per clock** and roughly **eight
usable backlog credits per subcore** under balanced traffic.

`probe_sm100_fp64_shfl_queue.py` then uses warps 1/2/3 to saturate this path
while timing warp 0. For a 64-instruction victim and a 256-instruction
background:

| timed victim | NOP background | predicated-off SHFL background | active SHFL background |
|---|---:|---:|---:|
| NOP | 135 | 135 | 135 |
| SHFL | 135 | 230--232 | 230 |
| DADD | 135 | 135 | 135 |

The result is invariant over background-start delays of 0, 2, 4, and 8
stall-8 NOPs and 21 repetitions per cell. Predicated-off SHFL therefore still
reserves the cross-subcore SHFL admission/dispatch domain, providing a strong
positive control. In the reverse direction, active and predicated-off DADD
backgrounds both leave a SHFL victim at exactly 135 clocks.

Thus **FP64 does not consume SHFL's SM-wide MIO admission/service domain**.
This rejects an SM-shared-FP64 model specifically implemented through that
queue, but does not logically exclude a centralized FP64 unit with its own
independent ingress and backend.

## CBU

Active `BMOV.32 Rd,MACTIVE` reproduces the placement-dependent behavior seen
on Hopper:

| placement | last fully frontend-fast N per warp | steady common-span slope |
|---|---:|---:|
| one warp | 12 | +4/N |
| four warps on four subcores | 8 | +4/N (four requests) |
| all eight warps | 3 | +8/N (eight requests) |

For one warp, N=12 is 29 clocks (`5+2N`) and N=13 is 33.  For four subcores,
N=8 is 22 and N=9 begins the +4 slope.  For eight warps, N=3 is 14 and N=4
jumps to 22.  These windows combine warp scheduling, local admission state,
and an approximately one-request/clock SM-wide CBU service.  Reporting a
single CBU physical queue depth would therefore overstate what the experiment
identifies.

## FP64

The ISA metadata assigns both `DADD` and `DFMA` to `fma64lite_pipe`.  Although
this path is grouped with the MIO-side admission question here, it is not
named `mio_pipe` in the static description.

One warp of active zero-source, dead-result `DADD` is exactly `T(N)=5+2N` for
N=0..20.  `DFMA` independently gives the identical exact curve.  Four
different-subcore DADD streams also add only two clocks to the common span per
four instructions through N=16.  There is no slope transition from which to
extract a queue capacity: admission and service already keep pace from the
first instruction.  The defensible result is therefore **zero measurable
extra burst window / no separable effective admission depth**, not “the
physical queue has zero entries.” The saturated-SHFL experiment above also
shows that any FP64 ingress is distinct from the shared SHFL MIO domain.

## UTCHMMA

`probe_sm100_utchmma_admission_modal.py` uses a different admission bound.
Each producer saves a timestamp before every UTCHMMA.  Timestamp i+1 can
execute only after instruction i has left the warp's blocked entrance, so its
difference from timestamp i upper-bounds admission of instruction i plus the
following `CS2R`.  With the UTCHMMA static stall reduced to one, the
uncontended fast interval is seven clocks.

Delay the second producer by 32 `NOP` instructions so the leading producer
fills its own subcore first.  Five repeated B200 runs give the following
median intervals for producer 0:

| producer placement | M128N8 intervals | M128N128 intervals |
|---|---|---|
| different subcores (warps 0/1) | `7,7,7,7,7,7,15` | `7,7,7,7,7,7,15` |
| same subcore (warps 0/4) | `7,7,7,7,8,8,13` | `7,7,7,7,8,8,13` |

The first six instructions pass at the baseline cadence; the seventh attempted
admission is backpressured.  Removing the observer entirely and using
overwrite UTCHMMA (`!UPT`) preserves the same boundary, excluding TMEM
observation traffic and accumulator RAW effects.  N8 and N128 also have the
same boundary even though their downstream service times differ greatly.

The narrow model is therefore **about six usable UTCHMMA instruction credits
per subcore**, counted in whole instructions rather than N waves.  Same-subcore
competition perturbs the final fast intervals while different subcores fill
independently, confirming that the credits are subcore-scoped and shared by
warps.  A lower SM-wide tensor dispatcher still determines subsequent service
order.  As with the other results, six is an effective admission capacity; it
does not distinguish a six-cell FIFO from an equivalent distributed-credit
implementation.

## Comparison with Hopper

Within the resolution of these probes, B200 matches the already measured H800
values for local LSU (about 8), downstream LSU (about 30), XU (about 2), and
the placement-dependent CBU windows.  The UTCHMMA queue is Blackwell-specific;
its approximately six whole-instruction credits should not be compared
directly with Hopper HGMMA without applying the same post-instruction
admission-bound method.
