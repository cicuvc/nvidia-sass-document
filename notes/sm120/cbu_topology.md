# GB202 Convergence Barrier Unit topology

Silicon: RTX 5090 (GB202, sm_120), 2026-09-15.  NVIDIA describes the
Convergence Barrier Unit (CBU) as responsible for warp-level convergence,
barrier, and branch instructions.  This note relates that definition to the
separately measured ADU, MIO queues, late operand collector, and warp
scheduler state.

## Best-fit division of responsibility

```text
                    per-subcore warp scheduler
                  execution-group / mask / RPC state
                         ^                 |
                         |                 | local converged fast path
                         |                 | (WARPSYNC.ALL)
                         |                 v
                 CBU state/control service
                    ^                 ^
                    |                 |
       local VQ_CBU (~10--12)   VQ_UNORDERED (BMOV)
                    ^                 ^
                    |                 |
       immediate/group-state     register-dependent request
       BSSY/BSYNC/WARPSYNC.ALL        |
                                      v
                         late RF collector / MIO PQ
                                      |
                                      v
                         ADU split/validation stage
                                      |
                                      +----> CBU state update
```

The cleanest boundary is `WARPSYNC`:

- `WARPSYNC.ALL`, whose participant set is known from the opcode, executes on
  CBU without PQ or ADU activity.
- `WARPSYNC Rmask`, even with `Rmask=0xffffffff`, performs one RF-to-PQ and
  PQ-to-ADU cycle, executes once on ADU, and also executes on CBU.
- A register-target `BRX` similarly traverses ADU and CBU; fixed-target BRA
  has a frontend fast path and traverses neither counted pipe on GB202.

This strongly supports the functional interpretation: **ADU turns
data-dependent lane values into one or more execution/request groups; CBU
commits group-control state, waits for groups, merges them, and tells the
warp scheduler which group is runnable.**  The physical implementation can
still be distributed; the counters do not require one centralized CBU SRAM.

The two descriptions' use of "barrier" is also consistent rather than
duplicated.  Block/CTA `BAR.SYNC` increments ADU but not CBU on this silicon;
CBU handles the warp-level convergence barriers BSSY/BSYNC and WARPSYNC.
The former is a request/arrival split problem, while the latter changes the
execution-group state of one warp.

## Logical queues are not identical to functional pipes

The sm_90 description assigns BSSY, BSYNC, WARPSYNC, YIELD, NANOSLEEP, BRX,
and the other branch/control operations to `VQ_CBU`.  BMOV is different: all
BMOV forms use `VQ_UNORDERED`, even though their functional pipe is CBU.
Consequently, a BMOV short-burst knee must not be called the depth of
`VQ_CBU`.

Conversely, the declared queue is not proof that every instruction reaches a
physical downstream queue.  In a parameter-free N=64 stream, fixed-target
BRA contributes 64 branch-op events but zero scalable `mioc_inst_issued` and
zero scalable `pipe_cbu` events.  It is resolved on a frontend fast path.
BRX contributes exactly 64 to MIOC, ADU, and CBU.

## Pipe and operand-path classification

`probe_cbu_topology.py --profile` removes memory setup and leaves only a
one-warp test stream plus EXIT.  Subtracting the one EXIT event gives:

| N=64 stream | CBU exec | ADU exec | RF -> PQ | PQ -> ADU | MIO2RF |
|---|---:|---:|---:|---:|---:|
| `BMOV Rd,MACTIVE` | 64 | 0 | 0 | 0 | 0 |
| `BMOV OPT_STACK,Rsrc` | 64 | 0 | 64 | 64 | 0 |
| 64 x (`BSSY`; `BSYNC`) | 128 | 0 | 0 | 0 | 0 |
| `WARPSYNC.ALL` | 64 | 0 | 0 | 0 | 0 |
| `WARPSYNC Rmask` | 64 | 64 | 64 | 64 | 0 |
| `YIELD` | 64 | 0 | 128 | 128 | 0 |
| `NANOSLEEP 0` | 64 | 0 | 128 | 128 | 0 |
| fixed-target `BRA` | 0 | 0 | 0 | 0 | 0 |
| `BRX {Rlo,Rhi}` | 64 | 64 | 128 | 128 | 0 |

CBU-state reads materialize a GPR without using the LSU/ADU `MIO2RF`
interface.  CBU therefore has a dedicated result path or writes from a local
state-read port into the final RF arbitration; it is not an LSU-like return.

The GPR-source BMOV is also instructive.  Its operand packet is labelled
`pipe_adu` by the PQ counter, but the instruction does not increment
`inst_executed_pipe_adu`; ADU can be an operand/request preprocessing route
without performing a counted ADU execution.  Register WARPSYNC and BRX do
increment both pipes because target/mask-dependent group formation is real
ADU work.

YIELD and immediate NANOSLEEP have no explicit GPR operand but generate two
PQ/ADU packet cycles.  These are best treated as an implicit 64-bit group-PC
or scheduler-state transaction, not ordinary user RF reads.  The counter's
short description, "register operands", is too narrow for these events.

False predication preserves MIOC and CBU pipe counts for all tested classes,
but removes every PQ transaction and all scheduler stalls.  Register
WARPSYNC still increments ADU execution under `@P6`, resembling the earlier
predicated-off LDC reservation behavior.  Thus pipe classification/admission
precedes the effective predicate, while actual operand collection and CBU
state mutation follow it.

## Throughput exposes several CBU paths

The timed probe selects warp 0+4 for the same subcore and 0+1 for different
subcores.  Long-stream aggregate rates are CBU instructions per clock; the
BSSY/BSYNC row counts both instructions.

| stream | one warp | same-subcore 2 | different-subcore 2 | four subcores, one warp each | 32 warps |
|---|---:|---:|---:|---:|---:|
| `BMOV Rd,MACTIVE` | 0.259 | 0.468 | 0.487 | 0.913 | 0.995 |
| `BMOV OPT_STACK,Rsrc` | 0.244 | 0.244 | 0.470 | 0.491 | 0.494 |
| BSSY+BSYNC | 0.105 | 0.209 | 0.208 | 0.410 | 0.997 |
| `WARPSYNC.ALL` | 0.198 | 0.386 | 0.386 | 0.729 | 3.835 |
| `WARPSYNC Rmask` | 0.027 | 0.054 | 0.054 | 0.107 | 0.498 |
| `YIELD` | 0.019 | 0.038 | 0.038 | 0.076 | 0.249 |
| `NANOSLEEP 0` | 0.0106 | 0.021 | 0.021 | 0.042 | 0.248 |

NCU declares a peak CBU rate of 680 instructions/clock summed over 170 SMs,
i.e. **4 per SM or 1 per subcore**.  Only the already-converged
`WARPSYNC.ALL` fast path approaches that peak.  The CBU counter is therefore
a functional classification, not one uniform four-lane execution pipeline.

The remaining ceilings identify narrower state operations:

- ordinary CBU state reads and convergence-stack updates approach 1/clock
  across the SM;
- one-GPR CBU state writes and register-mask WARPSYNC approach 0.5/clock;
- group handoff/suspension operations YIELD and NANOSLEEP approach 0.25/clock.

One subcore can obtain a larger share when the others are idle, so these are
compatible with a work-conserving SM-wide CBU-state/control arbiter above
local input queues.  Fixed per-subcore engines behind an additional shared
dispatch limit remain observationally equivalent.

The enormous difference between equivalent full masks is architectural:
one warp takes about 5 clocks per `WARPSYNC.ALL`, but about 37 clocks per
`WARPSYNC Rmask`.  The register form must collect and validate a
data-dependent participant set through ADU before CBU can release the warp;
the immediate-all form can check local converged state directly.

## Scheduler-stall signatures

For N=64 one-warp streams, cumulative warp-stall cycles are:

| stream | branch resolving | sleeping | interpretation |
|---|---:|---:|---|
| `WARPSYNC.ALL` | 8 fixed residue | 0 | already-converged fast path |
| `WARPSYNC Rmask` | 2056 | 0 | about 32 resolving clocks/instruction |
| `YIELD` | 2696 | 0 | about 42 clocks/instruction in group handoff |
| `NANOSLEEP 0` | 372 | 3226 | explicit scheduler sleeping state |
| BSSY+BSYNC pairs | 584 | 0 | convergence/RPC state serialization |

This distinguishes YIELD from NANOSLEEP more precisely than total timing.
YIELD leaves the group in control-flow resolution/handoff; NANOSLEEP enters a
dedicated non-runnable sleeping state and self-wakes.  It also explains why
NANOSLEEP fixes divergent-group starvation more robustly than a one-shot
YIELD in the debugger probes.

## VQ_CBU effective credits

To avoid BMOV's `VQ_UNORDERED`, `bssy_burst` arms distinct B0--B15 slots with
back-to-back BSSY instructions.  There is no RPC dependency, late operand, or
matching BSYNC inside the timed interval.  The short-burst issue slope changes
at approximately:

| actor placement | knee per warp | total queued BSSYs near knee |
|---|---:|---:|
| one warp | 12--13 | 12--13 |
| two warps, same subcore | 5--6 each | 10--12 |
| two warps, different subcores | 10--11 each | 20--22 |
| four different subcores | 8--9 each | 32--36 |

The same-subcore pair sharing the one-warp total, while different subcores
roughly duplicate it, is direct evidence for **per-subcore VQ_CBU ingress**.
The isolated effective capacity is about 10--12 requests.  The apparent knee
moves slightly earlier when all four downstream shares are active, so this is
an effective credit count including in-flight service, not a claim of exactly
12 physical SRAM entries.

## Cross-queue arbitration

Long contenders distinguish CBU state service from the LSU/XU datapaths:

- `BMOV Rd,MACTIVE`, BSSY/BSYNC, and `WARPSYNC.ALL` are unaffected by SHFL,
  LDC, and (apart from a tiny scheduling effect) MUFU.
- A one-GPR BMOV write slows from 4.05 to 12.02 clocks under a same-subcore
  active SHFL, while the false-predicated control is 3.96 and a
  different-subcore SHFL is 4.05.  Register WARPSYNC similarly changes from
  39.02 to 45.90 only for active same-subcore SHFL.  These are collisions in
  the local late collector before ADU/CBU.
- An indexed LDC contender slows BMOV-write from 4.05 to about 5.2 clocks in
  both same- and different-subcore placement.  Both requests reach the
  SM-wide ADU-side service, where LDC has effective priority; reversing victim
  and contender leaves LDC unchanged.

BMOV and true `VQ_CBU` traffic share a later state endpoint but retain
distinct queues.  A BSSY+BSYNC victim costs 19.04 clocks/pair alone, 27.39
with a same-subcore BMOV-read contender, and 47.67 with a same-subcore
BMOV-write contender; false-predicated controls remain 19.05.  The effects
fall to 22.35 and 19.83 respectively across subcores.  Reversing the test
leaves the BMOV victim unchanged.  This is consistent with a work-conserving
CBU state arbiter that gives the unordered BMOV path priority over VQ_CBU,
with an additional local penalty for register-dependent BMOV writes.

## Probe entry points

- `tests/asm_construct/probe_cbu_topology.py`: clean NCU classification,
  scaling, scheduler stalls, and BSSY credit knee.
- `tests/asm_construct/probe_mio_topology.py`: CBU/ADU/LSU/XU contention.
- `tests/asm_construct/probe_mio_queue_depth.py --mode cbu`: historical BMOV
  short-burst probe; this measures `VQ_UNORDERED`, not true `VQ_CBU`.
