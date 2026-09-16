# GB202 MIO / LSU / XU topology probes

Silicon: RTX 5090 (GB202, sm_120), 2026-09-14.  These experiments test a
working model in which MIO is the decoupled instruction/scoreboard system,
with subcore-facing queues, an SM-wide arbitration layer, LSU/L1TEX backends,
and subcore-local XU backends.  They distinguish observed boundaries from
physical block names that cannot be proved by counters alone.

## Current best-fit structure

```text
subcore 0..3 scheduler / scoreboard
        |                         |
 local LG/LSU queue        VQ_MUFU / XU issue-admission
 (~4 effective credits)   (MUFU + 32-bit F2F/F2I/I2F)
        \                         /
  per-subcore MIO RF operand collection / packetization
              (~0.5 32-bit GPR operands/clock)
        |                         |
 SM-wide LSU arbitration    local XU queue (~2 effective credits)
        |                         |
        |                    XU per subcore (~0.125 inst/clock)
        |                                      |
 shared LSU data path                          XU return (not MIO2RF)
 (~0.5 warp-inst/clock per SM)                 |
        |                                      |
 L1TEX data-stage / memory system              |
        |                                      |
      MIO2RF return                            |
        +---------- final even/odd RF 1W arbiters ----------+
```

The central dispatcher box is a useful abstraction, but the tests do not
prove that it is one monolithic physical `MIOC`; distributed arbiters with the
same externally visible limits remain possible.

## NCU classification: SHFL is an LSU/L1TEX-data-path operation

`probe_subcore_compute_conflict.py`, N=512, one active warp:

| stream | `pipe_lsu` inst | `pipe_xu` inst | L1TEX LSU data wavefronts | L1TEX T requests | MIO2RF active | MIO throttle | LG throttle |
|---|---:|---:|---:|---:|---:|---:|---:|
| SHFL | 522 | 0 | 530 | 2 | 544 | 23 | 0 |
| LDS `[RZ]` broadcast | 522 | 0 | 531 | 2 | 544 | 23 | 0 |
| MUFU.RCP | 10 | 512 | 18 | 2 | 32 | 3085 | 0 |

The 10/18/2 and 32-cycle residues are harness loads/stores and setup.  After
subtracting them, all 512 SHFLs appear as LSU instructions, one L1TEX LSU
data-stage wavefront, and one MIO2RF cycle each.  They produce **no T-stage
memory request**.  SHFL therefore reaches/reuses the LSU/L1TEX data exchange
path, rather than the subcore XU, but bypasses tag/address memory lookup.

At four different-subcore warps (2048 tested instructions), SHFL and LDS are
again almost identical:

| stream | LSU/XU inst | LSU wavefronts | MIO2RF | MIO throttle | LG throttle |
|---|---:|---:|---:|---:|---:|
| SHFL | 2064 / 0 | 2090 | 2064 | 11934 | 0 |
| LDS | 2064 / 0 | 2090 | 2064 | 11863 | 0 |
| MUFU | 16 / 2048 | 42 | 16 | 12205 | 0 |

Thus SHFL can strongly trigger `mio_throttle`, exactly like LDS at this
throughput point, while not triggering `lg_throttle`.

## Scaling identifies shared LSU and local XU backends

`probe_mio_scaling.py` runs equal streams in selected warps.  Warp-to-subcore
mapping is `warp_id % 4`.

| stream | one warp | same-subcore 2 | different-subcore 2 | four subcores | all 8 warps |
|---|---:|---:|---:|---:|---:|
| SHFL aggregate inst/cycle | 0.497 | 0.495 | 0.502 | 0.504 | 0.500 |
| LDS aggregate inst/cycle | 0.497 | 0.495 | 0.503 | 0.505 | 0.501 |
| MUFU aggregate inst/cycle | 0.125 | 0.125 | 0.250 | 0.501 | 0.500 |

SHFL and LDS share an SM-wide limit of approximately one warp instruction per
two cycles; adding subcores does not increase it.  Mixed SHFL+LDS streams give
the same roughly 0.5-inst/cycle aggregate limit.  MUFU instead scales linearly
through one warp per subcore and stops scaling when a second warp is added to
each subcore.  This is direct evidence for four local XU backends and a shared
LSU data path.  Repeating all streams under `@P6` gives the same curves, so
queue/backend credits are acquired before effective predication.

This is not a generic frontend or clock-measurement ceiling.  Identical actor
sets running fixed-pipe controls give:

| stream | one warp | same-subcore 2 | different-subcore 2 | four subcores | all 8 warps |
|---|---:|---:|---:|---:|---:|
| NOP aggregate inst/cycle | 0.497 | 0.993 | 0.993 | 1.979 | 3.920 |
| IADD3 aggregate inst/cycle | 0.497 | 0.498 | 0.993 | 1.979 | 1.979 |

The four scalar subcores can therefore sustain about 1.98 IADD3s per clock
unit while the LSU-class streams remain capped near 0.50 across the SM.

### Legacy scalar conversions use the XU admission queue

The un-suffixed scalar conversion instructions are MIO operations, unlike
their packed `P`-suffix replacements:

| instruction | static pipe / virtual queue | measured single-warp cadence |
|---|---|---:|
| `F2F.F16.F32` | `mio_pipe`, `VQ_MUFU` | about 8 clocks/instruction |
| `F2I.S32.F32.TRUNC` | `mio_pipe`, `VQ_MUFU` | about 8 clocks/instruction |
| `I2F.F32.S32` | `mio_pipe`, `VQ_MUFU` | about 8 clocks/instruction |
| `MUFU.RCP` control | `mio_pipe`, `VQ_MUFU` | about 8 clocks/instruction |
| `F2FP.F16.F32.PACK_AB` | fixed ALU-Heavy path | about 4 clocks here, including two-source collection |
| `I2FP.F32.S32` | fixed ALU-Heavy path | about 2 clocks/instruction |

Static `VQ_MUFU` is confirmed by two independent dynamic signatures.  First,
the short RZ-source burst curves are identical point for point:

```text
N:                    0  1  2  3  4  5 ...
MUFU/F2F/F2I/I2F T:   5  7  9 16 24 32 ...
```

All four accept the same approximately two effective XU credits; the third
operation reaches the same knee and the remainder drain at exactly eight
clocks per instruction.

Second, the bidirectional long-contender matrix is symmetric.  For every one
of F2F, F2I and I2F, either direction against MUFU gives:

| timed victim / long contender | solo | same subcore active | same subcore `@P6` | different subcore |
|---|---:|---:|---:|---:|
| conversion / MUFU, or MUFU / conversion | 7.961 | 16.648 | 16.523 | 7.953 clocks/instruction |

The predicated-off contender retains nearly the entire collision, locating
it at queue/admission rather than conversion arithmetic or RF writeback.
Moving it to another subcore removes the collision, as expected for the local
XU queue.  In contrast, active or predicated-off F2FP/I2FP changes a MUFU
victim by at most about 0.008 clocks/instruction.

This is not generic MIO contention.  An F2I victim remains at 7.961
clocks/instruction under active or predicated-off SHFL, LDS, LDG, and indexed
LDC contenders in either placement.  Those instructions use the LSU or ADU
admission paths rather than `VQ_MUFU`.

The resulting distinction is architectural rather than merely mnemonic:

```text
F2F / F2I / I2F  -> MIO admission -> local VQ_MUFU/XU queue -> XU-class service
F2FP / F2IP / I2FP -> early fixed-math RF collection -> ALU Heavy
```

The un-suffixed operations remain decoupled, variable-latency producers and
use a write scoreboard.  The packed `P` forms are coupled fixed-math
instructions and do not consume an XU admission credit.

There is an important 64-bit-format exception to interpreting `VQ_MUFU` as
one literal physical FIFO.  Every statically described F2F/F2I/I2F format,
including FP64 and signed/unsigned 64-bit integer forms, carries that same
virtual-queue tag.  A 64-bit source or destination nevertheless exposes a
different dynamic resource:

```text
RZ-source burst       T(0..7) = 5,7,9,11,13,15,17,26
64-bit-source drain   about 18 clocks/instruction
64-bit destination    about 19 clocks/instruction
```

Thus this path absorbs about six requests before the seventh reaches its
knee, rather than the approximately two credits of MUFU and the all-32-bit
conversion forms.  Tested FP64-source, FP64-destination, int64-source, and
int64-destination variants share this signature.  In particular,
`F2I.S64.F32` has the same 19-clock destination cadence despite containing
no FP64 arithmetic, so the distinction is format width, not specifically a
double-precision floating-point execution unit.  They interfere strongly
with one another even across subcores: a 64-element `F2F.F32.F64` victim
rises from 14.67 to about 28.2 clocks/instruction with an
active FP64-conversion stream on another subcore.  But it has no measurable
interaction with MUFU or 32-bit F2F in either direction, even when placed on
the same subcore.

The narrow conclusion is therefore that **32-bit legacy conversions share
the local MUFU/XU admission resource**, whereas a conversion with a 64-bit
source or destination is sent to a distinct, SM-shared slow conversion
resource.  `VQ_MUFU` is a logical MIO queue class broad enough to cover both,
not proof that all tagged formats occupy the same physical admission FIFO.

### Arbitration granularity: fair subcore queues, not flat warps

Two deliberately unbalanced actor sets reveal the shared LSU arbitration
policy.  `skew5={0,1,2,3,4}` puts two warps on subcore 0 and one on each other
subcore.  The three single-warp queues finish at about 8N cycles; the two
subcore-0 warps finish at about 10N.  This is exactly the work-conserving
per-subcore-queue schedule: initially each nonempty subcore receives one
quarter of the 0.5-inst/cycle LSU bandwidth, so the singleton queues empty at
8N.  Each subcore-0 warp has then completed half its work, and the newly free
bandwidth finishes their combined remaining N instructions in another 2N.

`skew6={0,1,2,3,4,5}` repeats the construction with two warps on subcores 0
and 1.  Singleton subcores 2/3 again finish at 8N, while all four warps on the
two loaded subcores finish at about 12N, matching dynamic redistribution of
the two freed queue shares.  SHFL and LDS reproduce these schedules to within
about 1%.  Flat per-warp fairness would instead make all five or six warps
finish together at 10N or 12N and is excluded by `skew5` in particular.

This is strong behavioral evidence for the proposed MIOC view: a
work-conserving SM-wide arbiter selecting fairly among four subcore LSU
queues.  It still does not reveal whether the gates and selection logic are
physically centralized or distributed.

MUFU and LSU can overlap rather than sharing an absolute 0.50-inst/cycle SM
cap.  A bidirectional long-contender matrix gives the more precise picture
below.  The contender is four times longer than the victim, so it remains
backlogged throughout the timed interval; `same` means warp 4 shares warp
0's subcore, while `diff` uses warp 1.

| timed victim | solo cycles/op | same-subcore active contender | same `@P6` control | different-subcore active |
|---|---:|---:|---:|---:|
| MUFU <- SHFL | 7.990 | 7.990 | 7.990 | 7.990 |
| SHFL <- MUFU | 2.010 | 2.645 | 2.020 | 2.012 |
| MUFU <- LDS `[RZ]` | 7.990 | 7.990 | 7.990 | 7.990 |
| LDS `[RZ]` <- MUFU | 2.010 | 2.016 | 2.020 | 2.012 |
| MUFU <- LDG | 7.980 | 7.980 | 7.980 | 7.980 |
| LDG <- MUFU | 3.980 | 5.223 | 3.980 | 3.980 |

Taken alone, this interaction is neither independent nor symmetric
round-robin.
MUFU/XU progress is unchanged by every tested LSU-class contender.  A
backlogged active MUFU instead takes bandwidth from same-subcore SHFL and
LDG, while false-predicated MUFU and a different-subcore MUFU do not.  For
SHFL the rates are especially diagnostic: `1/2.645 + 1/7.990 = 0.503`
instruction/cycle, recovering the same approximately 0.5 local combined
ceiling.  XU retains its full approximately 0.125 rate and SHFL receives the
remainder.  This is compatible with XU reservation/priority at a
work-conserving per-subcore arbitration point, not equal polling between two
queues.  Continuous traffic cannot yet distinguish strict priority plus a
service guarantee from weighted round-robin with an XU-favoring weight.

The apparent LDS exception in this first matrix was caused by the probe's
`LDS Rd, [RZ]`: RZ requires no physical RF source read.  Changing only the
address to a real zero-valued `R26` or `R27` makes LDS slow from 2.020 to
2.625 cycles/instruction under same-subcore MUFU, exactly like one-source
SHFL.  Thus LDS does not bypass the contested path; its zero-register form
simply contributes no operand-read demand.

NCU sharpens the LDG case.  Same-subcore active and `@P6` MUFU runs both
count the same 1024 `pipe_xu` instructions and have nearly identical total
MIO-throttle accumulation.  Making MUFU active nevertheless raises
LG-throttle from about 5863 to 9513 in the profiled run and slows LDG from
4.46 to 5.55 cycles/instruction; the different-subcore active run matches
the control.  Effective XU work therefore delays release of local LSU queue
entries after routing, rather than merely consuming a common instruction
issue slot.  Together with the late-address probe below, this points
specifically at a shared late-RF operand collector at dequeue.  The
operand-count experiment below makes that identification substantially
stronger.

### The 0.5 local limit counts late GPR operands, not instructions

SHFL's operand forms allow RF demand to change without changing the exchange
operation.  Register-addressed LDS and the LDG address pair provide
independent cross-checks:

| instruction form | physical GPR sources | solo cycles/op | with same-subcore MUFU |
|---|---:|---:|---:|
| SHFL RII with `Ra=RZ` | 0 | 2.020 | 2.031 |
| SHFL RII, `PT,Rd,Ra,imm,imm` | 1 | 2.020 | 2.625 |
| SHFL RRI, `PT,Rd,Ra,Rb,imm` | 2 | 3.980 | 5.234 |
| SHFL RRR, `PT,Rd,Ra,Rb,Rc` | 3 | 5.941 | 7.844 |
| LDS `[RZ]` | 0 | 2.020 | 2.016 |
| LDS `[Rreg]` | 1 | 2.020 | 2.625 |
| LDG `[Rlo:Rhi]` | 2 | 3.980 | 5.223 |

The solo SHFL forms consume one source per approximately two clocks: their
operand rates are 0.495, 0.503, and 0.505 GPR operands/clock for one, two,
and three sources.  LDS `[Rreg]` independently reproduces the one-source
case, while LDG's 64-bit address reproduces the two-source case.  LDS `[RZ]`
is instead limited only by the separate approximately 0.5-inst/clock LSU
exchange backend.

MUFU has one GPR source and its XU backend accepts approximately 0.125
instruction/clock.  Subtracting that demand from the collector's 0.5 leaves
approximately 0.375 operand/clock.  This predicts 2.667, 5.333, and 8.000
cycles for competing one-, two-, and three-source operations, close to the
measured 2.625, 5.234, and 7.844.  The earlier SHFL+MUFU combined
0.5-inst/clock was therefore a coincidence of both instructions having one
GPR source: it is an **operand** ceiling, not a common instruction-dispatch
ceiling.

Zero-register substitution is the decisive control.  `SHFL ...,RZ,imm,imm`
still performs the warp exchange and synchronization semantics, yet an
active same-subcore one-source MUFU changes it only from 2.020 to 2.031
cycles/instruction.  Conversely, replacing only MUFU's source with RZ makes
its interference disappear: both one-source SHFL and `LDS [Rreg]` measure
2.031 instead of 2.625 cycles/instruction.  The instructions and their
backends remain active; only the physical RF read has been removed.

Moving SHFL and MUFU sources independently between even and odd registers,
including a two-source SHFL with one source in each bank, does not change any
rate.  This is a narrower MIO late-read injection/collection limit before
parity routing, not ordinary bank capacity alone.  Writing a real predicate
destination (`P1` instead of `PT`) also leaves the rates unchanged, so
predicate writeback is not part of this bottleneck.  SHFL's active-mask
synchronization semantics may still matter to its execution backend, but the
RZ control proves that those semantics do not cause the mixed-stream slowdown.

Partial-lane predicates show that the limit counts complete warp-operand
tokens rather than active bytes.  For yield-zero SHFL streams:

| SHFL GPR sources | full warp | lane 0 only | low/high 16 | even lanes | all off |
|---:|---:|---:|---:|---:|---:|
| 2 (EE or EO) | 4.000 | 4.000 | 4.000 | 4.000 | 2.000 |
| 3 (EEE) | 6.000 | 6.000 | 6.000 | 6.000 | 2.000 |

Thus a nonempty mask always causes each source to consume a complete
two-clock late-read token.  The result is compatible with a 64-byte/tick MIO
transport that always transfers both warp halves, but equally with a
128-byte transfer behind a non-pipelined two-clock request/response or packet
assembly sequencer.  It is not evidence that only active lanes are moved.

An ALU-bank saturation test locates the downstream side of this sequencer.
The victim is one-source `SHFL ...,R24,...` (even bank); the same-subcore
contender writes RZ and therefore contributes only source reads:

| contender | source demand | active-minus-control effect on SHFL |
|---|---:|---:|
| `FADD RZ,R24,R26` | 2E per instruction | about +0.79 clocks/instruction |
| `FADD RZ,R25,R27` | 2O per instruction | approximately 0 |

Moving either contender to a different subcore removes the effect.  Hence a
late-read token eventually arbitrates for the normal selected RF bank; there
is no separate MIO register-file copy.  The combined behavioral path is:

```text
LSU/XU queue operand identities
          |
per-subcore MIO late-read sequencer / packet builder
     (one warp-wide GPR token per about two clocks)
          |
      parity routing
      /            \
normal even-bank  normal odd-bank read-service arbitration
          \
        completed LSU/XU request packet
```

The most conservative explanation for the factor of two is one outstanding
late-read transaction or packet slot: one phase selects/arbitrates a register
row and a following phase captures/installs the returned warp operand before
the next source can start.  A fixed two-beat 64-byte internal transport is
also possible.  Timing cannot distinguish those two implementations, but it
does distinguish both from a half-speed RF bank: ordinary ALU traffic can use
the bank at one operand/clock, and only same-bank saturation delays the MIO
client.

### LDS uniform address operands are captured early and use a separate path

The sm_120 uniform LDS form accepts `[RZ+URb+imm]` and `[Ra+URb+imm]`.
Using a real zero-valued `UR10` gives:

| LDS address | solo cycles/op | with same-subcore one-source MUFU |
|---|---:|---:|
| `[RZ]` | 2.010 | 2.016 |
| `[RZ+UR10]` | 2.010 | 2.016 |
| `[RZ+UR10+4]` | 2.010 | 2.016 |
| `[R26]` | 2.010 | 2.648 |
| `[R26+UR10]` | 2.010 | 2.648 |
| `[R26+UR10+4]` | 2.010 | 2.648 |

Thus neither URb nor the integer immediate consumes a slot in the 0.5
GPR-operand/clock late collector.  Only the Ra GPR controls contention with
MUFU.  A single-operation scoreboard-latency probe independently measures
37 clocks for `[RZ]`, `[RZ+UR10]`, and `[RZ+UR10+4]`, versus 38 for all three
forms containing R26.  UR and immediate add no visible fixed completion
latency; a real GPR base adds one clock in this schedule.

The WAR/liveness probe distinguishes a separate late UR port from early
capture.  It places 0--64 global stores ahead of LDS in the local LSU queue,
issues `LDS [RZ+UR10]` with UR10=0, and then overwrites UR10 with 4 without a
source-release barrier.  Across prefix depths 0/4/16/64 and overwrite gaps
0/8/16/20, all 160 runs load the old shared[0] sentinel.  The exact same
kernel using `[R26]` instead reads the new shared[4] sentinel in 9--10/10
runs through gaps 0--16 once the prefix contains at least four stores,
proving that the queue retention is sufficient to expose a late read.

An additional timing control rules out an implicit UR WAR interlock hiding a
late read.  `LDS; UMOV UR10,4; MOV R,UR10` always observes 4 and takes the
same 17--21 clocks as the corresponding GPR overwrite sequence as queue
depth changes.  The UR writer is not held until LDS dequeues.  The best model
is therefore that URb is read before or during LSU-queue enqueue and its
scalar value is stored in the request entry; Ra remains an RF register index
and is collected later at dequeue.  The immediate is already part of the
encoded request.

### STG late-reads both store data and the GPR address pair

`probe_stg_operand_latch.py` puts a target 32-bit STG behind 0--16 older
STG.E.128 requests and deliberately omits its source-release barrier.  Two
independent WAR writes either move the 64-bit GPR address from target+0 to
target+0x100 or change the store data from `0x11223344` to `0x55667788`.
With an empty queue even gap-zero overwrites are too late.  Once queued, both
overwrites take effect: STG retains live register identities for both its
address and its data until operand collection.

The dense boundary scan also establishes a collection order:

| older STG.E.128 prefix | last gap selecting new data | first gap locked to old data | last gap selecting new address-low | first gap locked to old address-low |
|---:|---:|---:|---:|---:|
| 2 | 7 | 8 | 9 | 10 |
| 4 | 17 | 18 | 19 | 20 |

When both registers are overwritten, the two-clock middle window stores the
**old data at the new address**, even though the program overwrites the
address first and data second.  The collector therefore samples the 32-bit
store-data operand first and the observed low half of the address pair about
two clocks later.  This matches the approximately one warp-wide GPR operand
per two clocks found above and suggests the order `data, address-low,
address-high`.  The high address half has not been isolated safely, so the
last element of that order remains an inference rather than a direct result.

The uniform-address form behaves differently.  For
`STG [{R20,R21}+UR10],R30`, changing UR10 from 0 to 0x100 after issue never
changes the address across prefixes 0/2/4/8/16 and gaps 0--20 (600/600 old
addresses).  Like LDS, the UR offset pair is captured at or before queue
enqueue, while the GPR address pair and store-data GPRs are read late at
dequeue.  A store read scoreboard must consequently cover **all GPR address
and data sources** until the last collector read; it need not retain them to
memory completion.

### LDGSTS late-reads both global and shared addresses

`probe_ldgsts_operand_latch.py` applies the same WAR method to cp.async's
`LDGSTS.E.32`.  Distinct source sentinels and two shared destinations show
that both the 64-bit global source address and the shared destination GPR can
be changed after SASS issue when older LSU work keeps the request pending.
They are collected during the same short local dispatch episode rather than
at two widely separated global-read and shared-write backend stages.

An eight-NOP separation between the two overwrites yields mirror-image hybrid
regions when their order is reversed: global-first temporarily copies new
data to the old shared slot, while shared-first copies old data to the new
slot.  This proves that both are late and localizes both samples to the same
collection window; it does not prove same-clock RF reads.

Equal-cost prefix streams are especially diagnostic.  `STG.32` and
`LDGSTS.32` produce the same full boundary table, whereas `STG.E.128` delays
the target much more because its four data GPRs add collector work.  Conversely,
eight 32-way bank-conflicted LDS operations do not delay the target at all:
shared-memory replay can accumulate downstream without holding this local RF
collector.  A `SHFL` stream with an RZ source is also inert.  These controls
tie LDGSTS to the ordinary LSU late-RF/admission path and prevent interpreting
the STG.128 delay as a fixed request-count FIFO depth.

LDGSTS's architectural read scoreboard exposes this boundary directly.  An
SB2-waiting overwrite of either the global or shared address is released in
7 clocks on an empty path, then 19/30/40/50 clocks behind 1/2/3/4 older
STG.128 requests, saturating near 53 clocks at six or more.  Full cold-copy
completion remains 357--410 clocks away.  Thus the source-release event is
the local collector handoff, not global-data return or shared writeback, and
one SB release protects both sides of the copy.

The same release times hold for LDGSTS.32/.64/.128 even though `.128` copy
completion is about 20 clocks longer in this probe.  The copy-width-dependent
128-byte token/lane-group work modeled by L1TEX therefore begins after this
local RF-release boundary.

These results argue against modeling MIOC as one single-issue global
dispatcher, although a wider central controller remains compatible with the
data.  The best behavioral model is separate LSU and XU queues/backends
sharing a per-subcore MIO RF operand collector of about 0.5 32-bit GPR
operands/clock.  An LSU entry retains a GPR index and uses the collector at
dequeue; an XU source is collected as its instruction obtains an admission
credit, before waiting behind older XU work.  XU and LSU need not have a special instruction-level
priority policy: MUFU is capped by its backend at 0.125 operand/clock and the
collector remains work-conserving for LSU demand.  Whether simultaneous
ready requests are selected by fixed priority or round-robin is still below
the resolution of these sustained-throughput tests.

## Local admission backlog: XU about 2, LSU about 4 per subcore

`probe_mio_queue_depth.py` measures short bursts without waiting for their
results.  RZ operands remove RF-collector demand, so the initial fast segment
is queue absorption and the post-knee slope is backend drain.  These are
effective admission credits; an internal implementation may count an
executing/transfer slot separately from a storage-array entry.

For one XU warp, elapsed clocks including the fixed ending-clock cost are:

```text
N MUFUs:  0  1  2  3  4  5 ...
clocks:   5  7  9 16 24 32 ...
delta:       2  2  7  8  8 ...
```

Two requests are accepted at the frontend rate; the third must wait for the
approximately eight-clock MUFU backend drain.  Activating two or four
different subcores reproduces the same knee independently on each subcore.
With two warps on the same subcore, the first request from each warp is
absorbed, but the second pair is already throttled and each later pair costs
16 clocks.  The effective XU admission capacity is therefore approximately
**2 requests per subcore**, shared among its warps rather than private per
warp.

The MUFU late-source control also clarifies where its operand is captured.
After 0--6 older `MUFU RZ` requests, a target `MUFU R80,R24` followed
immediately by an unbarriered overwrite of R24 always uses the old value.
When the XU credits are full, the target remains blocked before admission;
once admitted, its GPR value is collected immediately and stored with the XU
request.  This differs from LSU, which can enqueue a register index and
late-read it at dequeue.

For LSU, one `LDS [RZ]` warp arrives no faster than the approximately
0.5-inst/clock shared backend and cannot fill the queue.  Multiple warps make
the knee visible:

| placement | fast segment | transition | steady increment per N | inference |
|---|---:|---:|---:|---|
| two different subcores | N=1--6: +2 clocks | N=7 | +4 clocks | about 4 credits/subcore |
| four different subcores | N=1--5: +2 clocks | N=6 | +8 clocks | about 4 credits/subcore |
| two warps, same subcore | net backlog reaches about 4 near N=4--5 | N about 5 | +4 clocks | one shared local pool |

For two active subcores, each queue receives one request per two clocks and
is serviced every four clocks, so it accumulates about half a request per N;
the N=7 transition corresponds to roughly 3--4 queued requests.  With four
subcores each receives only one quarter of LSU service and accumulates about
0.75 request per N; the N=6 transition again corresponds to roughly four.
The same-subcore pair reaches the knee when their combined local backlog is
about four, excluding four private entries per warp.  The earlier LDS/LDG
late-GPR overwrite becoming mutable with a four-request prefix is an
independent consistency check.

The safest statement is consequently **approximately four local LSU backlog
credits and two effective XU credits per subcore**.  The LSU number describes
the first, local-arbitration knee and is not the total number of requests the
full LSU/L1TEX path can hold.  Determining whether the physical local FIFOs
have exactly 4/2 storage entries, or one fewer waiting entry plus a handoff
slot, requires visibility below the admission-credit boundary.

## LDS bank-conflict wavefronts expose a second downstream queue

The original depth probe used one-wavefront `LDS [RZ]`.  Setting each lane's
address to `lane_id * 4k` creates k-way bank conflicts for
k=1/2/4/8/16/32.  A single warp then has the following short-burst behavior:

NCU confirms the construction exactly.  For 32 tested LDS instructions,
k=1 reports 32 shared-load data wavefronts and zero bank conflicts; k=32
reports 1024 wavefronts and 992 conflicts, i.e. 32 wavefronts and 31 excess
bank-conflict passes per instruction.  Both runs count the same 32 tested
LSU instructions after subtracting harness traffic.

| conflict k | last request at +2 clocks | first throttled request | steady clocks/request |
|---:|---:|---:|---:|
| 1 | beyond 24 tested | none | 2 |
| 2 | 20 | 21 | 4 |
| 4 | 18 | 19 | 8 |
| 8 | 17 | 18 | 16 |
| 16 | 17 | 18 | 32 |
| 32 | 17 | 18 | 64 |

Thus one conflicted LDS remains one request for queue accounting; it does not
consume k entries.  Once executing, however, it occupies the L1TEX data path
for k serialized wavefronts and the sustained service cost is exactly 2k
clocks for a single stream.  For k>=8, approximately 17 requests are absorbed
before the first backend-completion wait becomes visible, revealing a much
deeper downstream request/handoff capacity beyond the approximately
four-request local backlog.

Multiple subcores separate the two knees especially clearly for k=32:

| active subcores | frontend-fast region | MIOC-arbitration region | backend-full transition | final increment per N |
|---:|---:|---:|---:|---:|
| 2 | N<=6, +2 | N=7--12, +4 | N=13 | +64 |
| 4 | N<=5, +2 | N=6--8, +8 | N=9 | +128 |

Here N adds one LDS to every active subcore.  The first knee is the local
approximately-four-entry backlog reaching the shared approximately
0.5-request/clock MIOC service rate.  During the middle region MIOC continues
moving requests into a downstream pool while the data stage is occupied by
old wavefronts.  The second knee occurs after roughly 16--18 requests have
crossed that handoff; only then does issue become governed by bank-conflict
drain.  This downstream capacity is SM-wide to the resolution of the test,
although the exact split between queued requests, an active request, and
L1TEX internal wavefront state remains ambiguous.

The experiment therefore qualifies the earlier queue-depth result rather
than invalidating the local-queue model:

```text
per-subcore LSU admission backlog       about 4 requests
SM-wide post-MIOC/downstream capacity   about 16--18 requests
wavefront cost per request              k, not k queue entries
```

The one-subcore and multi-subcore final slopes also show that multiple
conflicted requests can overlap their wavefront processing: a single k=32
stream costs 64 clocks/request, while two or four subcore streams deliver an
aggregate near one wavefront/clock.  Therefore “one shared LSU instruction
every two clocks” and “L1TEX data wavefront throughput” are separate limits;
the latter becomes visible only when requests contain multiple wavefronts.

`LDS.128` provides a vector-width control using the coalescing rules measured
in `notes/sm90/arch/shared_bank_conflicts.md`.  Eight instructions give the
following exact NCU counts and the same short-burst curves as scalar LDS with
the corresponding wavefront count:

| LDS.128 lane addresses | wavefronts/inst | conflicts/inst | last +2 request | steady clocks/request | matching scalar LDS |
|---|---:|---:|---:|---:|---:|
| broadcast `[RZ]` | 2 | 0 | 21 | 4 | k=2 |
| consecutive `16*lane` | 4 | 0 | 18 | 8 | k=4 |
| extended stride `32*lane` | 8 | 4 | 17 | 16 | k=8 |

The NCU totals are respectively 16/0, 32/0, and 64/32
wavefronts/conflicts for eight instructions.  In particular, the ordinary
non-coalesced `LDS.128` floor really is four wavefronts even though it has no
bank conflicts.  Its first throttled request is N=19 and its final +8-clock
slope are identical to scalar four-way-conflict LDS.  Queue accounting is
therefore by one instruction/request entry carrying a wavefront workload,
not by vector width or by pre-expanded wavefront entries.

This also explains why the downstream capacity was invisible in the original
one-wavefront experiment.  MIOC moves at most approximately 0.5 LSU requests
per clock into the downstream side, while a single one-wavefront stream drains
at approximately the same 0.5 requests per clock.  Occupancy stays nearly
constant.  With `w>1` wavefronts/request, request-equivalent drain falls to
approximately `0.5/w` for one stream while arrival remains approximately 0.5,
so the 16--18-entry capacity fills and produces the second knee.

### Shared and global traffic share downstream backpressure

`probe_lsu_downstream_sharing.py` uses two warps mapped to different subcores,
so the producer cannot fill the victim's private LSU queue.  Warp 0 presents
24 LDS requests; warp 1 times eight dead-result LDGs.  Keeping the LDS request
count fixed but changing each request from one to 32 shared-data wavefronts
changes the LDG issue span as follows:

| LDS producer | LDG timing placement | eight-LDG issue span |
|---|---:|---:|
| one wavefront/request | every tested delay | 27--28 clocks |
| 32 wavefronts/request | before backlog forms | 27--28 clocks |
| 32 wavefronts/request | delay 12 | 267 clocks median |
| 32 wavefronts/request | delay 20 | 251 clocks median |
| 32 wavefronts/request | delay 36 | 219 clocks median |

The reverse direction is also positive.  Twenty-four coalesced global loads
leave an eight-LDS issue span at 23--25 clocks.  Changing only the global lane
layout to 32 separate 128-byte lines/request raises it to 78 clocks at delay
28, 133 at delay 32, and 117 at delay 40.  The global-side result is noisier
because cache/miss closure timing is variable, but the effect is repeatable
and disappears in the coalesced control.

Thus the post-MIOC capacity is **not operationally shared-memory-only**:
shared work backpressures global admission and global work backpressures
shared admission across subcores.  The observable result is a common
SM-wide credit/backpressure domain.  Timing alone cannot distinguish one
literal mixed FIFO from separate shared/global FIFOs coupled by common LSU
data-stage credits or an arbiter, so “shared downstream queue” should be read
as the former behavioral abstraction rather than a proven SRAM layout.

### SHFL consumes the same downstream request credits

The same cross-subcore probe replaces the LDG victim with
`SHFL.BFLY PT,Rd,RZ,1,0x1f`.  Using RZ is important: it removes SHFL's late
GPR read and therefore isolates downstream admission from the independently
measured MIO RF-collector limit.  Eight SHFLs take about 21 clocks once the
other subcore is idle.  A 24-request, one-wavefront LDS producer changes this
only to 21--35 clocks depending on frontend overlap; changing only the LDS
addresses to 32 wavefronts/request raises the SHFL issue span to 601--649
clocks throughout the downstream-backlog window.  SHFL admission is therefore
strongly backpressured by outstanding LDS wavefront work.

A request-credit substitution test distinguishes this from contention only
at the final data-array/crossbar outlet.  One 32-wavefront LDS is issued first
to block drain, followed by M zero-source SHFLs and then more 32-wavefront
LDS requests:

| inserted SHFL M | first blocked LDS N | total requests N+M |
|---:|---:|---:|
| 0 | 18 | 18 |
| 4 | 14 | 18 |
| 8 | 10 | 18 |

Each inserted SHFL advances the long-LDS capacity knee by exactly one request.
Thus SHFL itself consumes one of the same approximately 18 post-MIOC request
credits.  It then contributes only one LSU data-stage wavefront and no T-stage
memory request, explaining why queued SHFL entries drain much faster than the
32-wavefront LDS entries once the blocking request completes.  Operationally,
the downstream pool is therefore shared by LDS, SHFL, and at least the common
admission/backpressure side of global traffic.

## CBU is MIO-throttled but is not just another LSU/XU queue

> Follow-up: `cbu_topology.md` now separates true `VQ_CBU` from BMOV's
> `VQ_UNORDERED`, identifies an approximately 10--12-credit per-subcore CBU
> ingress, and resolves distinct 4/1/0.5/0.25-inst-per-clock CBU paths.  The
> older BMOV-only results below remain valid but do not by themselves measure
> a physical CBU queue.

`BMOV.32 Rd, MACTIVE` provides a constant-latency CBU stream.  NCU classifies
512 active instructions per warp as `pipe_cbu`; four subcores execute 2056
CBU instructions including harness residue, produce very large MIO-throttle
stall accumulation, and add no material MIO2RF traffic.  Thus CBU admission
is accounted by the MIO throttle mechanism, while its result does not use the
LSU MIO2RF return branch.

The active scaling curve differs from both LSU and XU:

| actors | one | same-subcore 2 | different-subcore 2 | four subcores | all 8 |
|---|---:|---:|---:|---:|---:|
| BMOV aggregate inst/cycle | 0.249 | 0.495 | 0.498 | 0.993 | 0.998 |

One warp reaches about 0.25 instruction/cycle; two warps can interleave to
about 0.5 even on one subcore; four subcores reach the SM-wide ceiling near
1.0, and eight warps do not raise it.  Two-warps-on-each-of-two-subcores
tests give about 0.58--0.60, identically for subcore pairs 0+1, 0+2, and 0+3.
That pair symmetry excludes a simple fixed pairing such as one CBU backend
for {0,1} and another for {2,3}.  The nonuniform intermediate rates mean the
data do not yet identify a unique physical CBU count or arbitration policy;
the robust constraints are multi-warp latency hiding, an SM-wide throughput
ceiling, and no privileged subcore pairing.

Effective predication exposes a further distinction.  Four active warps give
about 0.99 BMOV/cycle and heavy MIO throttle, whereas `@P6 BMOV` follows the
NOP-like frontend curve (about 1.94 encoded instructions/cycle for four
warps) and reports zero MIO throttle.  NCU nevertheless counts the same 2056
predicated-off instructions in `pipe_cbu`.  Therefore the pipe counter marks
decode/routing, while the false predicate suppresses acquisition of the
throttled CBU execution resource.  This differs from SHFL/LDS/MUFU, whose
predicated-off streams retain their active structural scaling.

## LG throttle is exposed at a subcore-local admission boundary

`probe_mio_topology.py` issues unique-line LDGs.  With 256 victim and 1024
contender instructions, same- and different-subcore active cases execute the
same 1282 LSU instructions and generate the same 5120 L1-miss sectors:

| placement | victim issue cycles/op | LG throttle | MIO throttle | SM pending-LG integral |
|---|---:|---:|---:|---:|
| solo | 4.42 | 471 | 80 | 256272 |
| same-subcore `@P6` | 5.35 | 1075 | 80 | 300032 |
| same-subcore active | 9.01 | 4131 | 80 | 1234624 |
| different-subcore `@P6` | 4.34 | 586 | 80 | 267776 |
| different-subcore active | 4.52 | 2339 | 80 | 1662864 |

Concentrating requests on one subcore gives much more LG throttle even though
the distributed case has a *larger* whole-SM pending-instruction integral.
Moreover, the same-subcore predicated-off contender generates no extra L1TEX
T requests or misses but still raises LG throttle from 471 to 1075.  This
falsifies an interpretation in which LG throttle is exclusively an internal
L1TEX congestion counter.  It is consistent with the documented meaning:
failure to obtain a local LSU instruction-queue entry.  L1TEX congestion can
of course retain those entries and indirectly cause the backpressure.

The naked timing cross-check is equally local.  A cold-LDG contender changes
SHFL from 4.22 to 6.17 cycles/instruction beyond its same-subcore `@P6`
control, but only 3.75 to 3.84 on a different subcore.  LDS behaves the same;
MUFU is unaffected in either placement.  This separates local LSU admission
from the local XU queue/backend.

## Completion tracking is out-of-order, not a strict unified ROB

LDGSTS is the important exception at the software-visible **group** layer.
Its individual memory requests still use the decoupled LSU machinery, but
`LDGDEPBAR` creates ordered warp-private closure records.  Long-head probes
find 54 effective committed-group credits per warp; the 55th commit waits for
the oldest group to close.  Two warps on the same subcore retain independent
54-credit domains, so these records are not part of the approximately
four-credit subcore LSU ingress queue.

Within one warp the accounting is further partitioned by scoreboard index:
SB0 alone stalls on its 55th group, while a balanced SB0/SB1 stream holds 108
groups and stalls only when one side receives its 55th.  This reinforces that
LDGSTS group closure state belongs to the warp scoreboard machinery rather
than the shared LSU request queue.

`probe_mio_completion_order.py` issues an older cold LDG on SB4 followed by a
younger warmed LDG on SB5, then waits for SB5 and SB4 independently.  Across
31 fresh cold lines:

- younger-hot SB5 release: exactly 50 cycles;
- older-cold SB4 release: median 371 cycles (329--394 observed).

The younger request therefore completes and releases its scoreboard hundreds
of cycles before the older request.  A strict program-order completion ROB is
ruled out.  MIO still needs per-request identity, scoreboard association, and
request/response closure tracking; those structures need not impose in-order
retirement.

## LDG address sampling occurs at local-queue dispatch

`probe_ldg_address_latch.py` deliberately omits an anti-dependency before
overwriting an issued LDG's address register.  The old and new addresses hold
different sentinels.  With an empty LSU path, even an immediate (`gap=0`)
overwrite is too late and LDG returns the old value.  Putting only four
`STG.E.128` instructions ahead of LDG changes the result: overwrites through
16 one-stall NOP gaps select the new address, while gap 20 selects the old
address.  Prefixes from 4 through 64 have nearly the same boundary because
issue is backpressured once the finite local queue is full; increasing source
instruction count no longer increases queue occupancy at the moment LDG is
admitted.

The cross-subcore discriminator is decisive.  `probe_ldg_address_latch_cross.py`
runs 32--256 `STG.E.128`s in a contender warp, gives it a 64-NOP head start,
and then performs the target LDG plus address overwrite:

| flood placement | gap 0 | gap 8 | gap 16 | gap 20 |
|---|---:|---:|---:|---:|
| different subcore | 20/20 old | 20/20 old | 20/20 old | 20/20 old |
| same subcore | 20/20 new | 20/20 new | 20/20 new | 20/20 old |

Every flood depth gives the same table.  A same-subcore flood delays the RF
sample because the LDG remains in that subcore's LSU queue.  A different-
subcore flood loads the shared LSU backend but never extends the mutable-
address window, even at `gap=0`.  The address is therefore sampled when MIO
selects/removes the request from its local LSU queue and packetizes it for the
shared LSU path.  It is not re-read from RF later in the LSU/L1TEX backend.

Black-box timing cannot separate a MIOC output latch from the immediately
adjacent LSU-pipe input latch if both participate in the same handoff cycle.
In the terminology used for this experiment, the evidence supports option
**(a), local-queue dispatch/handoff**, and excludes a materially later option
**(b), post-transfer backend RF read**.  This also explains why normal code
can use a small fixed anti-dependency delay when the queue is empty, while a
deep queue requires a real read scoreboard for instruction forms such as STG
whose late source is scoreboard-covered.

### A late collector can consume a fixed-pipe result before RF commit

Late collection does not imply that the value must already reside in the RF
array.  Three poison/fresh boundary probes put a fixed-pipeline producer
immediately before a MIO consumer:

| producer -> MIO consumer | latency-table gap | first reliable fresh gap |
|---|---:|---:|
| INT `MOV.64 {R10,R11}` -> LDG address | 6 | 1 |
| FMA Lite `FFMA R10`; `FFMA R11` -> LDG address | 6 | 1 after the last producer |
| FP16 `HADD2 R10` -> `MUFU.RCP R10` source | 6 | 2 |

The LDG address detector is especially useful here.  The address-latch probe
above shows that an empty LSU queue samples its address at the local dispatch
handoff; an overwrite issued after LDG is already too late.  Thus the fresh
gap-1 result cannot be explained by the request sitting for a long time in an
empty downstream queue.  Independently, forcing a fixed producer through an
explicit `wr`/`req` scoreboard measures approximately 5.4--5.8 clocks to
architectural completion, much later than these consumer-visible boundaries.

The supported model is therefore:

```text
INT / FMA / FP16 execution
          |
    bypass / result staging --------+
          |                          |
       RF commit                     +--> MIO late collector
                                          (or an equivalent pending-result
                                           interlock followed by forwarding)
```

The latency-table value is a conservative **producer-to-consumer availability
contract**, not proof that the result has committed to RF by that clock.  For
the tested fixed-pipe-to-MIO edges, normal scheduling at the table gap is safe
even if the architectural write is still buffered, because the late collector
can obtain the pending value or is held until that value is forwardable.

This also removes the need for a result FIFO to promise RF commit within every
consumer latency.  It still must guarantee eventual progress.  The narrowest
plausible mechanism is finite completion credits allocated before fixed-pipe
admission, bounded/age-aware arbitration at the parity write ports, and
backpressure before the staging queues can overflow.  A sustained same-bank
FFMA stream measurably delays a scoreboarded LDG return, so variable-latency
MIO completion can absorb at least some of the arbitration variability.  The
reverse experiment--whether an already queued MIO completion can delay a
fixed result's architectural commit--has not yet been isolated, so strict
fixed-over-MIO priority remains a likely but unproved refinement.

## Two return paths converge at the RF bank arbiters

NCU distinguishes the return paths:

- 512 SHFL or LDS results add about 512 `mio2rf_writeback_active` cycles;
- 512 MUFUs add zero after subtracting the harness, despite 512 XU ops.

`probe_mio_completion_rf.py` aligns each scoreboarded completion against an
even-only or odd-only reuse-fed FFMA write stream.  LDS and SHFL show symmetric
same-bank penalties (best-case up to 2 cycles, distribution medians up to
8--9).  MUFU shows a smaller but stable symmetric +1 cycle once the windows
overlap.  Hence LSU-class results use MIO2RF and XU has a distinct return path,
but both converge on the same final parity-banked 1W RF commit arbiters already
identified in `rf_writeback_conflict.md`.

Two additional boundaries rule out treating that XU return as the ordinary
INT/FP result path.  `test_mio_int_fma_forward.py` observes stale input through
stall 7 for both `MUFU -> IADD3` and `MUFU -> FADD`; the first fresh result is
at an approximately 8.4-clock gap.  Fixed-pipe producers reach the same
consumers through their bypass network in roughly 2--3 clocks.  Conversely,
a cross-warp extension of `probe_subcore_rf_writeback.py` finds the same
+1-clock even-bank penalty at `N=32`, phases -12/-8 (100 repeats), while a
different-subcore contender does not.  Therefore the narrowest supported
model is **separate XU completion/return staging, no fixed-pipe fast bypass,
then convergence with INT/FP at the final RF-bank commit arbiter**.  The
experiment cannot exclude a very small generic merge buffer immediately in
front of that arbiter.

The early visibility is not confined to XU.  `probe_mufu_self_forward.py`
uses one identical producer/setup and changes only the consumer.  In isolated
kernels, the first-fresh nominal gaps are **7 for both** `MUFU.RCP ->
MUFU.RCP` and STG store data, versus 8 for the same producer into `IADD3` or
`FADD`.  `probe_mufu_lsu_forward.py` reproduces the STG boundary independently:
gaps 1--6 are stale and gaps 7--32 are fresh, with or without a younger MOV
overwriting the source immediately after STG.  Thus an XU-private loopback
alone is excluded; the early visibility reaches the LSU-side late collector.

This is an opportunistic early path, not a hidden dependency scoreboard.
`probe_mufu_lsu_collect_timing.py` times the STG read/source-release barrier:
no prefix takes 29 clocks, while an independent MUFU and a data-producing
MUFU both take 31.  The dependent case receives no additional wait for the
MUFU result and stores poison at an underscheduled gap.  The path is therefore
not a hidden dependency scoreboard.

`probe_mufu_forward_under_rf_block.py` resolves the remaining RF-versus-bypass
ambiguity.  Warp 0 produces even-bank R40 with MUFU and samples it through STG
near the stale/fresh boundary.  One same-subcore contender warp emits 32
parity-only FFMA writes; opposite-bank, predicated-off, and different-subcore
streams are controls.  At gaps 7 and 9 the same-even stream delays MUFU's
scoreboard completion by about 6--9 clocks relative to same-odd/off, while all
STG observations remain fresh.  More decisively, at the scheduler-bimodal
gap-5 edge over 300 repetitions at each of three phases:

| contender | median completion | fresh observations (three phases pooled) |
|---|---:|---:|
| same subcore, even writes | 54--55 clocks | 885/900 |
| same subcore, odd writes | 50--51 clocks | 891/900 |
| same subcore, predicated-off even | 49--50 clocks | 885/900 |
| different subcore, even writes | 28 clocks | 0/900 |

The same-subcore scheduling shift explains why the first three cases usually
cross the gap-5 boundary.  On top of that matched shift, same-bank writes add
another 4--5 clocks to final completion but cause no systematic loss of fresh
values relative to odd or predicated-off controls.  If STG obtained R40 only
after final RF commit, this bank-specific delay would move the critical value
boundary.  It does not.  The supported physical model is consequently a real
**XU result-staging -> common MIO late-collector forwarding path**, before the
final parity-banked RF commit arbiter.  It still has no dependency interlock.

Both XU admission and an empty LSU dequeue reach this forwarded-result point
at the same measured gap-7 boundary.  Back-to-back dependent MUFUs and STGs
still read stale data, and scoreboarded chains still cost about 18 clocks per
operation; normal code must use the scoreboard.

### MIO2RF completion staging also forwards to the MIO collector

The same mechanism is not limited to the independent XU return.
`probe_mio2rf_mufu_forward.py` uses SHFL and LDS as two independently verified
MIO2RF producers and compares poison/fresh boundaries with no producer
scoreboard wait:

| producer | -> MUFU | -> STG late collector | -> IADD3 |
|---|---:|---:|---:|
| SHFL | gap 12 | gap 12 | gap 14 |
| LDS | gap 11 | gap 11 | gap 13 |

For both producers the XU/LSU consumers sharing the MIO late collector see the
new result two nominal clocks before the fixed INT collector.  LDS reproduces
the geometry without SHFL's exchange/predicate behavior, ruling out a SHFL-
specific feedback path.

`probe_mio2rf_forward_under_rf_block.py` then claims a real scoreboard for an
even-bank SHFL result and overlaps its final commit with a same-subcore FFMA
write stream.  At phase -23 and consumer gap 13, 300-run medians are 75 clocks
for same-even writes and 71 for same-odd or predicated-off controls.  All
three cases produce the fresh dependent MUFU result in 300/300 runs.  The
bank-specific four-clock final-commit delay is larger than the one-gap margin
above SHFL's gap-12 boundary, yet it does not move that boundary.  Thus this
is another genuine pre-commit edge:

```text
LSU/SHFL MIO2RF completion staging --+--> final parity RF commit
                                     |
                                     `--> common MIO late collector
                                          (no dependency interlock)
```

The combined collector can therefore obtain pending results from at least
three domains: fixed INT/FMA result staging, the independent XU return, and
MIO2RF completion staging.  This resembles a tagged pending-result lookup or
small completion bypass fabric around the MIO collector, not merely a raw RF
read port.  None of these opportunistic edges replaces scoreboard scheduling.

## Status of the proposed model

- **Strongly supported:** MIO as the decoupled scheduling/completion umbrella;
  subcore-local LSU admission; subcore-local XU; shared SM LSU/L1TEX data path;
  common scoreboard-aware closure tracking; final RF-bank convergence.
- **Qualified:** “one MIOC” matches the visible arbitration behavior, but its
  physical centralization is not distinguishable from a distributed fabric.
- **Falsified as stated:** LG throttle is not purely inside L1TEX; all MIO work
  does not return through MIO2RF; completion is not globally in program order.
- **Partially constrained:** CBU is MIO-throttled, has an approximately
  1-inst/cycle SM ceiling and no simple fixed subcore pairing; its exact queue
  placement and backend count remain open.
- **Effective credit depths:** approximately 4 local LSU backlog requests and
  2 XU requests per subcore, plus a distinct roughly 16--18-request SM-wide
  post-MIOC/downstream LSU capacity.  Physical FIFO storage versus included
  handoff/execution slots remains ambiguous.
- **Still open:** barrier queue placement, arbitration priority among the four
  subcore LSU queues, exact throttle reserve thresholds, and whether any
  ordering domain narrower than the tested independent LDGs is in-order.
