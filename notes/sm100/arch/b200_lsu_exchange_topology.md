# B200 SM-wide LSU/shared-data/SHFL throughput

Silicon: B200 (sm_100), Modal, no NCU.  Probe:
`tests/asm_construct/probe_sm100_lsu_exchange.py`.  Cubins are assembled as
hand-scheduled sm_100 SASS.  Each warp issues a 512-instruction long stream
(the mixed confirmation uses 1024), rotates destination registers, and records
its own `SR_CLOCKLO` interval.  Aggregate throughput is total warp instructions
over `max(end)-min(start)` for all active warps.

Warp placement follows the established `warp_id % 4` subcore mapping.

## Scalar request streams

| stream / placement | aggregate inst/cycle | interpretation |
|---|---:|---|
| conflict-free LDS, one warp | 0.497 | one local stream presents about half rate |
| register-address LDS, same-subcore two warps | 0.497 | shared late-RF address collector is the limiter |
| zero-address LDS `[RZ]`, same-subcore two warps | 0.965 | removing address reads exposes two local LSU queues |
| register-address LDS, different-subcore two warps | 0.966 | two collectors fill the SM-wide backend |
| register-address LDS, four subcores | 0.958 | approximately one SM-wide request/cycle |
| register-address LDS, all eight warps | 0.988 | approximately one SM-wide request/cycle |
| one-source SHFL, one warp | 0.497 | one local collector stream |
| one-source SHFL, same-subcore two warps | 0.497 | same local late-RF limit as LDS |
| one-source SHFL, different-subcore two warps | 0.966 | two collectors fill the shared backend |
| one-source SHFL, four subcores | 0.950 | approximately one SM-wide request/cycle |
| one-source SHFL, all eight warps | 0.963 | approximately one SM-wide request/cycle |
| zero-source SHFL, four subcores | 0.971 | late-RF-independent control |

Small deviations from 1.0 include common start/end and branch-tail overhead;
the eight-warp LDS and longer mixed tests provide the cleanest asymptotes.

## Data-stage wavefront throughput

Conflict-free `LDS.128` carries four 128-B shared-data wavefronts per warp
instruction:

| placement | instructions | data wavefronts | common span | wf/cycle |
|---|---:|---:|---:|---:|
| one warp | 512 | 2,048 | 3,892 | **0.526** |
| four subcores | 2,048 | 8,192 | 8,113 | **1.010** |

Thus one request stream drains at approximately 0.5 wavefront/cycle, while
enough subcores sustain approximately **one aggregate 128-B data wavefront per
SM clock**.  This is the same single-stream and aggregate behavior measured on
H800/H20.

## LDS/SHFL common exchange backend

A four-subcore mixed stream assigns LDS to warps 0/2 and one-source SHFL to
warps 1/3.  At 1024 instructions per warp it completes 4096 requests in a
4145-cycle common span, or **0.988 request/cycle**.  Mixing does not add the
individual LDS and SHFL ceilings; it retains the same approximately one
request/cycle SM-wide ceiling.  SHFL therefore reaches the same shared
data-stage/exchange backend as LDS, after its subcore-local late operand
collector.

## Hopper / Blackwell comparison

| observable | H800/H20 sm_90 | B200 sm_100 | RTX 5090 sm_120 |
|---|---:|---:|---:|
| one-stream LDS/SHFL request rate | ~0.5/cycle | ~0.5/cycle | ~0.5/cycle |
| SM-wide shared request rate | ~1.0/cycle | **~1.0/cycle** | ~0.5/cycle |
| one-stream data wavefront drain | ~0.5/cycle | **~0.5/cycle** | ~0.5/cycle |
| multi-stream aggregate wavefront drain | ~1.0/cycle | **~1.0/cycle** | ~1.0/cycle |
| late GPR source collection/subcore | ~0.5 operand/cycle | consistent with ~0.5 | ~0.5 |

B200 therefore matches Hopper in both the SM-wide request admission rate and
the data-wavefront backend.  GB202 retains the same aggregate wavefront
capacity but exposes only about half the shared-request admission rate and
shallower queues.  A single B200 LDS/LDS.128 contender is consequently not a
saturating occupancy meter: four different-subcore streams are required when
measuring UTCHMMA shared-port consumption.

The repaired four-contender UTCHMMA experiment now uses a fully assembled
multi-warp allocator and scoreboard-closed LDS.128 streams.  A short saturated
window measures 576 LDS wavefronts in 643 cycles; adding four M128N128K16 BF16
UTCHMMA operations extends the LDS span to 906 cycles.  The 263-cycle delta is
65.75 cycles/MMA, essentially the 64 shared operand wavefronts expected from a
4-KiB A tile plus a 4-KiB B tile.  Thus tensor gdesc reads and LDS share this
SM-wide approximately 128-B/cycle read data stage; arbitration largely
protects tensor traffic (MMA time changes only from 627--629 to 642--647
cycles).  Full protocol and raw per-warp intervals are in `../instr/utchmma.md`.
