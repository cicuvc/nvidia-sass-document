# TMA & mbarrier synchronization → SASS (sm_90a)

How the async-copy / tensor-memory-accelerator (TMA) sync primitives lower.
Verified via `tests/mbarrier_test.cu` and `tests/tma_test.cu`. Completes the trio
of Hopper async-completion mechanisms alongside `../instr/depbar.md` (cp.async) and
`wgmma.md` (GMMA scoreboard).

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). A real sm_90 rerun is currently blocked because the accompanying test source
> uses sm_120 FORMAT shapes the sm_90 spec rejects at match time.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

## mbarrier → the `SYNCS` family (`mio_pipe`)
All mbarrier PTX ops become the shared-memory sync instruction `SYNCS`, with a
`TRANS64` (64-bit transaction barrier) modifier and a shared address in a uniform
register:

| PTX | SASS |
|---|---|
| `mbarrier.init.shared.b64 [b], n` | `SYNCS.EXCH.64 URZ, [UR], UR` |
| `mbarrier.arrive.expect_tx …, [b], txCount` | `SYNCS.ARRIVE.TRANS64 RZ, [UR], R0` (`R0` = tx bytes) |
| `mbarrier.arrive.shared.b64 tok, [b]` | `SYNCS.ARRIVE.TRANS64.A1T0 R2, [UR], RZ` (arrive-count 1, tx 0) |
| `mbarrier.try_wait.parity …, [b], phase` | `SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR], R0` |

### `SYNCS.ARRIVE.TRANS64` — arrive / expect_tx encoding (`tests/mbar_arrive_test.cu`)
`syncs_arrive_` (opcode `0x19a7`) carries a `paramtype` modifier that selects the
{arrive-count, tx-count} sources, a `retval` modifier (`OLDSTATE` = return the
barrier's old state = the phase **token** in `Rd`; `RZ`/`_` = no token), the
barrier address in `Ra`(+const/uniform), and the count value in `Rb`. `PARAMTYPE`
enum: `A`=arrive-count, `T`=tx-count; `1`=+1, `0`=+0, `R`=from register.

| PTX | SASS (paramtype) | arrive+ | tx+ |
|---|---|---|---|
| `mbarrier.arrive [b]` | `.A1T0` | 1 | 0 |
| `mbarrier.arrive [b], n` | `.ART0` (`R6,[UR],R2`) | n (reg) | 0 |
| `mbarrier.expect_tx [b], k` | `.A0TR` | 0 | k (reg) |
| `mbarrier.arrive.expect_tx [b], k` | *default `A1TR`* (no suffix, `RZ,[UR],R0`) | 1 | k (reg) |
| (also) | `.A0T1`, `.A0TX` | 0 | 1 / imm |

So **`.expect_tx` = "arrive 0, tx +k"** (`A0TR`) and **`.arrive.expect_tx` = "arrive 1,
tx +k"** (`A1TR`, the default → printed with no suffix). Observed control codes:
- token-returning arrives set `wr_sb` (the `Rd` token is decoupled-scoreboarded);
  `_`/`RZ`-dest arrives use `wr_sb=7`.
- the register-count form (`.ART0`) `req`-waits and `rd_sb`-reads the SB holding
  its count operand.
- `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VQ_SYNCS_UNORDERED_WR` — SYNCS is a decoupled
  scoreboard op (its token result is scoreboard-tracked, not fixed-latency).

## The `try_wait.parity` polling loop
The classic spin loop
```
LAB_WAIT:
  mbarrier.try_wait.parity.acquire.cluster.shared::cta.b64 P1, [bar], phase;
  @P1 bra DONE;   @!P1 bra LAB_WAIT;
```
compiles to a **non-blocking predicate test + software spin**:
```
        SHF.L.U32 R0, R0, 0x1f, RZ                 # phase bit -> bit31
/*70*/  SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR4], R0   # P0 = has the phase flipped?  (does NOT block)
        @P0 CCTL.IVALL                             # .acquire  -> invalidate L1
        @!P0 BRA 0x70                              # spin
```
Key points:
- **`try_wait` never blocks the warp** — `SYNCS.PHASECHK...TRYWAIT` only *sets a
  predicate* `P0` (phase complete?). The wait is an explicit software spin
  (`@!P0 BRA back`), stall 2 / `bit4=1` (transN, tight spin). This is the
  polling model, distinct from a blocking `mbarrier.wait`.
- **`.acquire` ⇒ `CCTL.IVALL`** — once the phase flips, an L1 **invalidate-all**
  runs under `@P0`, so the consumer's subsequent `LDS`/`LDG` see the freshly
  TMA-delivered data (acquire memory ordering).
- `PHASECHK` writes a scoreboard (`wr_sb=0`) for the `P0` result; the branch
  consumes it.

## TMA load → `UTMALDG` (`udp_pipe`, single-thread) + tx-count mbarrier
`cp.async.bulk.tensor.2d.shared::cluster.global.tile.mbarrier::complete_tx::bytes`:
```
if (elect one thread) {
  SYNCS.EXCH.64 [bar], ...                 # mbarrier.init
  SYNCS.ARRIVE.TRANS64 [bar], R0           # arrive.expect_tx  (R0 = 4096 bytes expected)
  @P0 ELECT P1, URZ, PT                     # elect a single issuing thread
  UTMALDG.2D [smem], [descriptor]          # TMA tile load  (udp_pipe / OP_TMA)
}
BAR.SYNC                                    # __syncthreads
L: SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [bar], R0   # consumer polls
   @P0 CCTL.IVALL ; @!P0 BRA L
```
Mechanism — the **transaction-count** (tx) mbarrier:
1. `arrive.expect_tx` sets the barrier's expected byte count (`SYNCS.ARRIVE.TRANS64`
   with `R0` = bytes).
2. `UTMALDG` (issued by **one elected thread** on the uniform datapath) kicks off
   the bulk tensor copy global→shared. The copy engine **decrements the mbarrier's
   tx count** by the bytes delivered as they land (`complete_tx::bytes`).
3. When tx reaches 0 the barrier **phase flips**; the consumer's `try_wait.parity`
   predicate goes true.

### UTMALDG control-code signature
```
UTMALDG.2D [UR8], [UR4]   stall=12 bit4=0(yield) req=…SB1 rd_sb=1 wr_sb=7
```
- **`rd_sb=1` (sets a READ scoreboard)** — TMA reads its descriptor/coordinate
  source registers asynchronously; the read barrier protects them from a later
  writer (WAR) until the engine has consumed them.
- **`wr_sb=7` (no write scoreboard)** — TMA's *completion* is NOT a general
  scoreboard; it is signalled through the **mbarrier tx-count**. So its result
  ordering is entirely mbarrier-based.
- **`bit4=0` (WnEG/yield), stall 12** — the elected thread yields after firing the
  async copy; it does not wait for the transfer.
- Single-thread issue (`ELECT`) + uniform datapath = like `tcgen05` on Blackwell,
  one thread launches the whole bulk op.

## cp.async.bulk group completion — `UTMACMDFLUSH` + `DEPBAR.LE`
TMA has a *second* completion path (`tests/tma_store_test.cu`), the
**bulk-async-group** mechanism, used mainly for TMA **stores** (shared→global)
where there is no consumer mbarrier to signal. `cp.async.bulk.tensor…bulk_group`
store + `commit_group` + `wait_group.read 0`:
```
UTMASTG.2D [UR8], [UR6]     rd_sb=1  wr_sb=7    # TMA store; READ scoreboard protects the shared source
UTMACMDFLUSH               rd_sb=0  wr_sb=7    # commit_group -> flush TMA cmd queue, count group on SB0
DEPBAR.LE SB0, 0x0         cnt=0  bit4=0       # wait_group.read 0 -> wait SB0 count <= 0
```
| PTX | SASS |
|---|---|
| `cp.async.bulk.tensor…bulk_group` (store) | `UTMASTG.2D` |
| `cp.async.bulk.commit_group` | `UTMACMDFLUSH` |
| `cp.async.bulk.wait_group[.read] N` | `DEPBAR.LE SBn, N` |

This reuses the **same counted-scoreboard `DEPBAR.LE`** as cp.async
(`../instr/depbar.md`) — only the commit point differs (`UTMACMDFLUSH` vs
`LDGDEPBAR`). Notable:
- **`.read` ⇒ READ scoreboards.** `UTMASTG` sets `rd_sb`; the commit counts on a
  scoreboard drained by `wait_group.read`, so the wait completes once the async
  engine has finished *reading* the shared source (buffer safe to reuse).
- **Same-thread** completion (issuer waits for its own bulk ops), vs the mbarrier
  path which is cross-thread producer→consumer.
- `DEPBAR.LE` yields (`bit4=0`) while waiting.

So TMA itself has **two** completion styles: the **mbarrier tx-count** (loads,
cross-thread, `SYNCS`+spin) and the **bulk-async-group** (stores, same-thread,
`UTMACMDFLUSH`+`DEPBAR.LE`).

## UBLKCP.G.S shared-service occupancy (H800)

`tests/asm_construct/probe_ublkcp_shared_service.py` measures a warp issuing
contiguous shared-to-global `UBLKCP.G.S` copies while warps 4--7 (one per SMSP)
run a stream of ordinary shared-memory operations.  The producer either commits
and waits after every copy or puts all copies in one bulk group.  A matched
control omits UBLKCP, and independent `SR_CLOCKLO` spans are recorded for the
producer and contenders.

For one group containing 32 copies, the H800 bulk-group **read-completion**
times (`wait_group.read 0`, i.e. shared source safe to reuse) are:

| bytes/copy | total bytes | producer cycles |
|---:|---:|---:|
| 128 | 4 KiB | 254 |
| 512 | 16 KiB | 621 |
| 1 KiB | 32 KiB | 1,133 |
| 4 KiB | 128 KiB | 4,205 |
| 8 KiB | 256 KiB | 8,301 |
| 16 KiB | 512 KiB | 16,493 |

Except for the very small transfer, this is almost exactly

```
Tgroup = 109 cycles + total_bytes / 32 B/cycle.
```

A 4-KiB/copy count sweep from 1 through 64 commands gives 237, 365, 621,
1,133, 2,157, 4,205, and 8,301 cycles: `109 + 128*copies` with no kink through
64 commands.  This does **not** prove a 64-entry command FIFO--issue may simply
backpressure at the streaming service rate--but it rules out an exposed
per-command completion bubble in the one-group case.  Committing each of 32
copies separately instead adds about 41 cycles per copy while retaining the
same 32-B/cycle read-completion slope; that overhead is command/group
machinery, not shared-data service occupancy.

The contender result is direction-sensitive:

- `LDS` is delayed by `total_copy_bytes / 64 B/cycle`.  For total transfers of
  16, 32, 128, and 256 KiB, the measured increments are 246.5, 502.5, 2,053.5,
  and 4,086.5 cycles.  Commit-each gives the same slope.
- `STS` has no measurable delay (all points within roughly 12 cycles of the
  matched control), even when UBLKCP remains active longer than the STS stream.
- Changing the LDS address pattern from conflict-free through 2-, 4-, and
  8-way bank conflict changes the LDS baseline as expected, but a 128-KiB copy
  still adds 2,038, 2,049, 2,054, and 2,069 cycles respectively.  Thus the
  64-B/cycle result is not an artifact of one bank pattern.

The current structural model is therefore: the shared-source side of
`UBLKCP.G.S` arbitrates with the SM-wide **shared read** service used by LDS,
but not with the ordinary STS write service.  Its shared-side occupancy is one
service slot per approximately 64 bytes, while its bulk-group read-completion
rate is only approximately 32 B/cycle.  Equivalently, at steady state it occupies
the shared read service about half of the time, leaving interleave opportunity
for LDS; some other TMA ingestion/pipeline stage, rather than the shared read
arbiter, paces source consumption.  `wait_group.read` does not establish when
the global destination becomes visible, so these measurements alone do not
identify that pacing stage as the global write interface.  RTX 5090 gives the
same 64-B/cycle LDS interference and
32-B/cycle producer slopes, which is useful cross-generation corroboration.

## UBLKCP.S.G shared-service occupancy (H800)

The reverse-direction probe is
`tests/asm_construct/probe_ublkcp_load_shared_service.py`.  Warp 0 issues a
group of global-to-shared copies to one transaction-count mbarrier; warps 4--7
run LDS or STS.  The copied first word is checked after every launch, in
addition to waiting for the mbarrier phase, so an accidentally dropped TMA
command cannot look like low contention.

With 16 commands in flight, the H800 results are:

| bytes/copy | total bytes | mbar completion cycles | extra STS cycles | bytes/extra cycle |
|---:|---:|---:|---:|---:|
| 128 | 2 KiB | 399 | 27.0 | 75.9 |
| 512 | 8 KiB | 504 | 77.0 | 106.4 |
| 1 KiB | 16 KiB | 562 | 145.5 | 112.6 |
| 2 KiB | 32 KiB | 692 | 288.5 | 113.6 |
| 4 KiB | 64 KiB | 996 | 564.5 | 116.1 |
| 8 KiB | 128 KiB | 1,611 | 1,124.5 | 116.6 |

The corresponding LDS increments are only 4--5 cycles at every size, i.e.
measurement/alignment noise rather than a byte slope.  Thus S.G is the mirror
of G.S: **TMA loads contend with STS but not LDS**, while TMA stores contend
with LDS but not STS.

At fixed 4 KiB per command, count=1,2,4,8,16,32,64 gives mbarrier completion
times 323, 437, 539, 691, 998, 1,601, and 2,819 cycles.  From four commands
onward the fit is approximately:

```
Tmbar = 386 cycles + 38.0 cycles * commands
      = 386 cycles + total_bytes / 108 B/cycle.
```

The large intercept is the first global-read/TMA latency; multiple queued
commands overlap it.  Over the same count sweep, STS blocking converges to
about 35.1 cycles per 4-KiB command, or approximately 116.7 B per occupied
shared-write cycle.  This is close to, but measurably below, an ideal 128-B
shared wavefront per cycle.  Treat 128 B/cycle as the likely physical beat and
roughly 117 B/cycle as the sustained observed occupancy rate for this command
stream; request boundaries or bubbles account for the difference.

Changing the STS pattern from conflict-free through 2-, 4-, and 8-way bank
conflict changes its baseline from about 2K through 16K cycles, but the same
64-KiB TMA load adds 584, 575, 565, and 560 cycles.  Hence the conclusion does
not depend on one bank-conflict pattern.

The direction-selective model is now:

| UBLKCP direction | shared role | conflicts with | observed H800 occupancy |
|---|---|---|---:|
| `G.S` (shared -> global) | source/read | LDS | ~64 B/read-service cycle |
| `S.G` (global -> shared) | destination/write | STS | ~117 B/write-service cycle |

RTX 5090 preserves the same read/write separation for S.G (STS conflicts, LDS
does not), but has very different rates: approximately 77 B per blocked STS
cycle and only about 32 B/cycle at mbarrier completion for large transfers.
The directionality therefore appears structural across both generations; the
TMA-to-shared port width/pacing does not.

## Locating the TMA/shared arbitration point

Three follow-up probes distinguish ordinary L1TEX wavefront routing from an
arbiter at the shared-memory array boundary.

### UBLKCP versus SHFL: no shared wavefront-frontend conflict

SHFL exercises the L1TEX/exchange path but does not access the shared SRAM
array.  With four contender warps running 2,048 `SHFL.BFLY PT,RZ,RZ`
instructions, neither UBLKCP direction produces a byte-dependent delay:

- G.S totals of 32, 128, and 256 KiB add 0, 15.5, and 10 cycles to an
  approximately 8,162-cycle SHFL stream.
- S.G totals of 64, 256, and 512 KiB all change the approximately 8,177-cycle
  stream by -13 cycles (a fixed control/alignment offset).

Thus TMA does not appear to enter through the normal SHFL/LDS wavefront
frontend or exchange datapath.  It more likely has a bulk path that first
meets ordinary LDS/STS traffic at the shared array read/write entrance.

### UBLKCP versus HGMMA: one blocked TMA cycle per HGMMA wavefront

`tests/asm_construct/probe_ublkcp_hgmma_interaction.py` runs an HGMMA chain on
warpgroup 0 and UBLKCP on warp 4.  SS HGMMA strongly blocks G.S but not S.G:

- 256 SS m64n16k16 HGMMAs take about 5,208 cycles through drain.  Concurrent
  G.S completion is delayed by 5,091 cycles at every sufficiently long copy
  size, while HGMMA issue is unchanged and drain grows by only 82 cycles.
- Concurrent S.G changes HGMMA drain by only 18--20 cycles and has no
  corresponding multi-thousand-cycle delay.

The RS control is especially diagnostic.  The earlier HGMMA operand model
assigns approximately 20 shared wavefronts to each SS m64n16 instruction but
only four to RS.  The measured G.S delays are:

```
SS: 5091 / 256 = 19.89 blocked cycles per HGMMA   (prediction: ~20 wavefronts)
RS: 1017 / 256 =  3.97 blocked cycles per HGMMA   (prediction: ~4 wavefronts)
```

This near-exact correspondence supports one array-read arbitration grant per
HGMMA shared wavefront.  HGMMA has strict or near-strict priority: its own
issue/drain barely changes, while the lower-priority TMA G.S source read is
deferred.  A longer RS run can show about 4.6 cycles/instruction because its
window includes alignment/tail effects; the 4-KiB/copy overlap gives the clean
four-wavefront result.

### G.S plus S.G: shared ports are directional, TMA engine is not full duplex

`tests/asm_construct/probe_ublkcp_duplex.py` places G.S on warp 0 and S.G on
warp 5, hence on different SMSPs, with disjoint shared/global regions.  At 32
commands per warp:

| bytes/command | bytes/direction | G.S solo | S.G solo | G.S dual | S.G dual |
|---:|---:|---:|---:|---:|---:|
| 512 | 16 KiB | 592 | 489 | 678 | 912 |
| 1 KiB | 32 KiB | 1,104 | 615 | 1,397 | 1,639 |
| 2 KiB | 64 KiB | 2,128 | 910 | 2,661 | 2,908 |
| 4 KiB | 128 KiB | 4,176 | 1,514 | 5,189 | 5,479 |
| 8 KiB | 256 KiB | 8,272 | 2,738 | 10,245 | 10,650 |

For the largest point, the two solo times sum to 11,010 cycles, close to the
approximately 10.65K-cycle dual completion.  In dual mode the formerly faster
S.G direction slows until both directions finish at nearly the same time.
Therefore UBLKCP is not end-to-end full duplex: a common bidirectional TMA
data engine/dispatcher approximately serializes or round-robins G.S and S.G,
even though they eventually request different shared-array ports.

The resulting working topology is:

```
 LSU/L1TEX wavefront frontend -- LDS/STS wavefronts --+
                                                    +--> directional shared-array
 TMA command queues --> common TMA data engine ------+    read/write arbiters --> banks
                         (G.S/S.G not full duplex)

 SHFL/exchange datapath -----------------------------X    (does not meet TMA here)
 HGMMA shared fetch ---------------------------------+--> array read arbiter, priority over G.S
```

"Port lock" in this model means a grant/burst at the logical array read or
write arbitration domain, not necessarily a literal monolithic 1R1W SRAM
macro.  The G.S/HGMMA result shows that these grants are visible one-for-one
at wavefront granularity.

## Same-direction multistream arbitration

`tests/asm_construct/probe_ublkcp_multistream.py` gives 1, 2, or 4 producer
warps disjoint global windows, shared windows, and (for S.G) mbarriers.  Warps
0--3 map to distinct SMSPs, so the experiment distinguishes per-SMSP engines
from an SM-wide service.

For 64 commands of 4 KiB per warp (256 KiB per stream), the steady-state H800
results are:

| direction | streams | per-stream completion cycles | aggregate B/cycle |
|---|---:|---|---:|
| G.S (S->G) | 1 | 8,238 | 31.82 |
| | 2 | 16,430, 16,431 | 31.91 |
| | 4 | 32,816, 32,817, 32,814, 32,815 | 31.95 |
| S.G (G->S) | 1 | 2,694 | 97.31 |
| | 2 | 5,119, 5,124 | 102.32 |
| | 4 | 10,059, 10,047, 10,050, 10,051 | 104.24 |

Consequences:

- Same-direction streams do **not** multiply throughput with SMSP count.  G.S
  shares one approximately 32-B/cycle SM-wide service exactly; each of N
  streams receives approximately 1/N.  S.G similarly approaches its earlier
  approximately 108-B/cycle single-engine asymptote as additional streams hide
  the global-read startup latency.
- Long-run fairness is excellent.  Four streams finish within three cycles for
  G.S and twelve cycles for S.G, with no fixed SMSP priority visible.
- More streams help only in the latency-dominated regime.  With one 4-KiB
  command per stream, aggregate throughput rises from 23.5 B/cycle at one G.S
  stream to 29.3 B/cycle at four because outstanding TMA latency overlaps; it
  does not exceed the steady-state shared/TMA service ceiling.

The G.S scheduler is demonstrably finer-grained than a whole UBLKCP command.
When four warps issue exactly one command each, their completion times differ
by only one cycle and follow:

```
size/warp       512 B   1 KiB   2 KiB   4 KiB
four-warp time   111      175     303     559 cycles

T = 47 cycles + (4 * size) / 32 B/cycle.
```

If complete 4-KiB commands were serviced FIFO, the four completions would be
separated by roughly one command service time; instead they are coincident.
The common engine therefore stripes/round-robins G.S at a sub-command bulk-beat
granularity (or has an equivalent parallel request closure with a shared beat
service).

S.G has a different short-request signature.  Four single requests of 512 B
or 1 KiB all complete near the approximately 300-cycle first-response latency,
within four cycles.  At one 4-KiB request per warp the completion spread grows
to roughly 81 cycles and the order is dynamic rather than fixed by warp/SMSP;
with many commands the long-run spread collapses again.  Thus S.G also shares
one fair SM-wide service, but global-return arrival and/or shared-write command
granularity is visible for isolated larger requests.

Combining the same- and opposite-direction results: per-SMSP LSU/TMA issue
queues can hold independent requests, but an SM-wide TMA controller/data engine
arbitrates them.  Same-direction requests share one fixed direction-specific
throughput; opposite directions additionally share the non-full-duplex common
engine described above.

## Outstanding-request capacity and backpressure

`tests/asm_construct/probe_ublkcp_outstanding.py` places one clock immediately
after the final UBLKCP and another after completion.  This separates producer
backpressure (`issue span`) from the final queue drain (`tail`).  The result is
layered: there is no single FIFO depth that describes both directions.

### Per-SMSP command ingress: four-entry burst queue

The multistream probe gives the clearest frontend result.  With one producer
warp on each SMSP, every warp can issue four 4-KiB commands in nine cycles.
The fifth command raises issue span to approximately 20--26 cycles, and the
sixth begins to expose common-controller service order.  This holds for both
directions.  The working interpretation is a **four-command local TMA ingress
queue per SMSP**, above the common SM-wide TMA controller.

The common intake has a second throttle.  A single producer initially emits
four commands at approximately one per cycle, then admits commands at roughly
one per eight cycles.  For large commands this is superseded by a byte-rate
limit: S.G admission is approximately one 128-B beat per cycle (32 cycles for
a 4-KiB command).

### G.S (shared-to-global): ten per stream, approximately 22 per SM

For a single producer, the G.S tail becomes constant as soon as issue
backpressure reaches the final service rate:

| command bytes | saturated tail | final service interval | inferred outstanding |
|---:|---:|---:|---:|
| 1 KiB | 346 cycles | 32 cycles/command | `(346-26)/32 = 10` |
| 2 KiB | 666 cycles | 64 cycles/command | `(666-26)/64 = 10` |
| 4 KiB | 1,306 cycles | 128 cycles/command | `(1306-26)/128 = 10` |

Thus one producer path can have exactly **ten G.S commands** outstanding
(including its local ingress entries).  Beyond the knee, every extra command
delays the final issue by exactly `bytes/32 B/cycle`.

Across four SMSPs, four commands each (16 total) issue immediately, and five
each (20 total) are all accepted before a 4-KiB request can complete.  At six
each (24 total), two producers acquire completion-spaced delays of about one
and two 128-cycle service intervals.  This strongly supports:

```
4 local entries/SMSP * 4 SMSPs + approximately 6 common closures
    = approximately 22 software-visible outstanding G.S requests/SM.
```

Equivalently, the single-stream ten is four local plus the same approximately
six common slots.  The 22 value counts queued plus executing commands; the
common backend itself appears to maintain about six closures.

### S.G (global-to-shared): size-dependent effective window

S.G first admits a 4-KiB stream at 32 cycles/command (128 B/cycle), faster than
its approximately 38--39-cycle completion interval.  Its backlog therefore
grows gradually until a second knee makes issue rate match completion rate.
Arming `expect_tx` before rather than after the UBLKCP sequence produces the
same curve, ruling out a pending-mbarrier-credit artifact.

The issue/tail knees imply these approximate single-stream effective windows:

| command bytes | effective outstanding commands | approximate outstanding payload |
|---:|---:|---:|
| 1 KiB | 120--128 | 120--128 KiB |
| 1.5 KiB | 88--90 | 132--135 KiB |
| 2 KiB | 63--64 | 126--128 KiB |
| 3 KiB | 43--44 | 129--132 KiB |
| 3.5 KiB | about 48 | about 168 KiB |
| 3.75 KiB | about 48--51 | about 180--191 KiB |
| 4 KiB | about 48--50 | about 192--200 KiB |

For commands up to roughly 3 KiB, the limit behaves like an approximately
128-KiB in-flight payload/sector-credit window.  Larger commands bottom out at
roughly 48 command closures rather than falling below that count.  A concise
empirical description is therefore:

```
effective S.G commands per producer ~= max(48, 128 KiB / command_bytes)
```

This `max` shape is not the behavior of two ordinary independent hard limits.
It suggests that small UBLKCPs can be packed/coalesced within a sector or
closure tracking structure, while large requests receive at least one of
roughly 48 command closures.  Treat that implementation explanation as a
hypothesis; the effective capacities and knees are measured.

### Mixed small and large S.G requests

`tests/asm_construct/probe_ublkcp_mixed_sizes.py` tests whether the two arms of
the empirical `max` expression are actually independent pools.  One producer
issues the same multiset of 128 1-KiB commands and 48 4-KiB commands in three
orders: all small first, all large first, or evenly interleaved.  Commands
rotate over four disjoint 4-KiB global and shared windows.  Clocks bracket the
order-dependent split, end of issue, and mbarrier completion.

| order | first half (commands, bytes) | phase 1 | phase 2 | tail | total |
|---|---:|---:|---:|---:|---:|
| small first | 128, 128 KiB | 1,008 | 1,271 | 1,084 | 3,363 |
| large first | 48, 192 KiB | 1,255 | 1,264 | 848 | 3,367 |
| interleaved | 88, 160 KiB | 1,167 | 1,280 | 916 | 3,363 |

The two interleaved halves contain the same mix (64 small plus 24 large), yet
the second half takes 113 cycles longer because it inherits the first half's
backlog.  The pure prefixes provide another useful comparison: 128 small
requests take 1,008 cycles and 48 large requests take 1,255 cycles when first.
After the large prefix, the same 128-small population takes 1,264 cycles; after
the small prefix, the large population takes 1,271 cycles.  Thus size classes
are **not independent FIFO/service domains**.  Large requests can backpressure
subsequent small requests through a shared resource.  The asymmetry says only
that their credit consumption or expansion behavior differs, not that one
class has strict priority.

Order changes the point at which the producer stalls, but not the final
service time.  All three totals agree within four cycles, with the shorter
issue span compensated by a longer tail.  Two larger mixtures reproduce this:

| small requests | large requests | payload | total-cycle range |
|---:|---:|---:|---:|
| 128 | 96 | 512 KiB | 5,209--5,219 |
| 256 | 48 | 448 KiB | 4,607--4,618 |

For the 512-KiB case, subtracting the approximately 300-cycle first-return
latency gives `512 KiB / (5210 - 300) = 106.8 B/cycle`, matching the independent
approximately 105--108-B/cycle S.G completion limit.  This supports a common
progressive request/sector path and common completion backend:

```
per-SMSP four-command ingress
    -> command/sector expansion (up to about 128 B/cycle admitted)
    -> shared finite credits or staging, with size-dependent accounting
    -> global-return/shared-write completion (about 107 B/cycle)
```

The earlier `max(48, 128 KiB / bytes)` remains a useful empirical description,
but it should not be drawn as two isolated queues.  Plausible implementations
include a common credit pool in which a command's charged in-flight extent is
capped, or size-selected packing/streaming modes that still feed the same
backpressured sector path.  The present timing cannot distinguish those two.

## Tensor-mode G2S: descriptor cache and shared backend

NVIDIA patent application
[US20230289292A1](https://patents.google.com/patent/US20230289292A1/en)
gives an unusually concrete TMAU pipeline in its FIG. 6 description:

```
SM -> MIOC 604 -> internal request queue 606
                         | tensor request
                         v
                 descriptor cache 608 -> setup 610
                         |                  |
                         +------------------+
                                    v
                           request generator 616
                                    v
             GNIC 614 <-> completion tracker 618 <-> response processor 620
```

The text says queue 606 can contain tensor and non-tensor requests and may be
FIFO or select by request type, size, direction, or other characteristics.
Tensor requests obtain their global-address-tagged descriptor from cache 608
and pass through setup 610.  While one request is processed, the next
descriptor may be prefetched through GCC 622.  Linear block requests may
bypass descriptor cache/setup and go directly to generator 616.  Both forms
are split by the generator into memory-system-sized subrequests and tracked by
completion circuit 618.  The patent permits alternative implementations, so
these names alone are not silicon proof; the following H800 measurements match
the structure closely.

### Descriptor-cache hit, miss, invalidate, and prefetch

`tests/asm_construct/probe_utmaldg_descriptor_cache.py` performs two sequential
256-byte `UTMALDG.2D` operations.  Every launch gives the first operation a
previously unused descriptor address.  The second operation either reuses it,
uses a fresh but byte-identical descriptor, or applies `UTMACCTL.IV` first.
Both maps point to the same tensor data, equalizing data-cache warmth.

| second operation | first fresh descriptor | second latency | interpretation |
|---|---:|---:|---|
| same descriptor address | 572 | 319 | descriptor-cache hit |
| fresh descriptor address | 572 | 577 | descriptor-cache miss |
| `UTMACCTL.IV`, same address | 572 | 539 | TMA entry invalidated; lower path warm |

Thus the H800 descriptor cache is observably tagged by descriptor address, as
the patent states.  A hit saves approximately 258 cycles relative to a fresh
address.  Invalidation followed by reuse is about 38 cycles faster than a
wholly fresh descriptor.  A likely explanation is that `UTMACCTL.IV` removes
the TMA-local decoded/cache entry while the same 128-byte descriptor remains
warm below it (GCC/L2); this distinction is an inference.

Explicit `UTMACCTL.PF` confirms asynchronous descriptor prefetch.  A fresh
descriptor without PF takes 577 effective cycles.  With 32 stall-8 NOPs (about
256 cycles) between PF and UTMALDG, the measured interval is 580 cycles
including the gap, hence about 324 cycles after subtracting it--essentially the
319-cycle hit path.  A no-op control remains 833 cycles including the same gap.
Additional spacing gives no further improvement.  The descriptor fetch/setup
miss penalty is therefore about 250--260 cycles and is hideable by the
look-ahead prefetch mechanism described in the patent.

### Descriptor-hit UTMALDG issue and completion

`tests/asm_construct/probe_utmaldg_outstanding.py` prefetches one descriptor
before timing, then emits repeated same-descriptor `UTMALDG.2D` requests and
separately clocks end-of-issue and mbarrier completion.

The tensor instruction/setup frontend has a fixed 12-cycle issue interval:

- 256-byte and 1-KiB tiles remain exactly 12 cycles/request through 256
  requests.  Their request stream is only 21.3 and 85.3 B/cycle respectively,
  so the data generator/backend keeps up and no issue backpressure appears.
- 2-KiB tiles begin at 12 cycles/request, then change to exactly 16
  cycles/request (`2048 / 128 B/cycle`) around 32 requests.
- 4-KiB tiles issue at 12 cycles/request through 12 requests, show a knee by
  16, and settle at exactly 32 cycles/request from 24 onward.
- 8-KiB tiles similarly settle at exactly 64 cycles/request after the initial
  burst.

This exposes a tensor request/setup queue capable of absorbing roughly a dozen
large descriptor-hit requests, followed by a common request-generator ceiling
of approximately 128 B/cycle.  It also explains why tensor mode is inefficient
for a stream of many tiny tiles: its fixed 12-cycle UTMALDG/setup cadence, not
the shared-write datapath, is the limit.

A second knee is indistinguishable from non-tensor S.G:

| tile | tensor-mode observation | matching UBLKCP.S.G observation |
|---:|---|---|
| 4 KiB | 192--224 requests: 32 -> 38.9 cyc/request; tail 1849--1892 | about 192-request knee; 38--39 cyc/request; tail about 1870 |
| 8 KiB | high-count slope about 77--85 cyc/request | `8192 / 105--108 B/cycle` = 75.9--78.0 cycles |

Consequently the working H800 model is now:

```
tensor: descriptor cache -> setup --+
                                     +-> common ~128-B/c request generator
linear UBLK: ------------------------+        -> shared credits/staging
                                              -> ~105--108-B/c completion
```

Identical downstream knees strongly imply shared generator/credit/completion
resources.  A direct interleaved UTMALDG+UBLKCP experiment is still needed to
determine whether the patent's upstream request queue 606 is also one physical
queue on Hopper, or whether separate ingress queues merely converge below it.

## Tensor-mode S2G: descriptor setup collapses onto the linear G.S path

`tests/asm_construct/probe_utmastg_outstanding.py` is the store-direction
counterpart.  It prefetches a tensor descriptor, issues repeated
`UTMASTG.2D`, clocks the end of issue, then measures bulk-group completion via
`UTMACMDFLUSH` plus `DEPBAR.LE`.  Unlike UTMALDG's mandatory 12-cycle control
shape, descriptor-hit UTMASTG initially issues at nearly one instruction per
cycle.

The first run was made on RTX 5090 (sm_120), because the H800 instance was
temporarily unreachable.  For every tested size, the steady request interval
is exactly tile bytes divided by 32 B/cycle:

| tile bytes | steady UTMASTG issue interval | rate |
|---:|---:|---:|
| 256 | 8 cycles | 32 B/cycle |
| 1,024 | 32 cycles | 32 B/cycle |
| 2,048 | 64 cycles | 32 B/cycle |
| 4,096 | 128 cycles | 32 B/cycle |
| 8,192 | 256 cycles | 32 B/cycle |

At 64 commands, end-to-end time is approximately `50 + total_bytes/32`
cycles for every tile size.  The producer can initially hand off about two
commands almost immediately; backpressure develops over the next few commands
and the issue interval then equals the shared-read/TMA service time.  The
constant tails are 89, 257, 481, 929, and 1825 cycles for the five sizes,
equivalent to roughly seven to eight large requests left in the service window
when issue ends.

Most importantly, a same-GPU control using
`probe_ublkcp_outstanding.py --arch sm120 --direction gs` is nearly bit-for-bit
identical after descriptor prefetch.  Representative 4-KiB totals are:

| commands | 1 | 2 | 4 | 8 | 12 | 16 | 32 | 64 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| UTMASTG | 178 | 306 | 562 | 1074 | 1586 | 2098 | 4146 | 8242 |
| UBLKCP.G.S | 180 | 308 | 564 | 1076 | 1588 | 2100 | 4148 | 8244 |

Both have a 929-cycle saturated tail and a 128-cycle steady 4-KiB issue
interval.  The same approximately two-cycle offset holds throughout the 1-KiB
comparison, whose common steady interval and tail are 32 and 257 cycles.

This is stronger than merely sharing a bandwidth ceiling.  Once the descriptor
has been fetched and decoded, UTMASTG appears to submit a linearized transfer
into essentially the same command window, shared-array read service, and
bulk-group completion path as UBLKCP.G.S:

```
UTMASTG: descriptor cache/setup + tensor address traversal --+
                                                          +-> common G.S path
UBLKCP.G.S: explicit address + byte count -----------------+   (~32 B/cycle)
```

The exact H800 correspondence remains to be rerun; these numbers are sm_120
silicon evidence and should not be silently generalized to Hopper.  A direct
UTMASTG/UBLKCP overlay will further distinguish a literally shared request
queue from two queues feeding the same 32-B/cycle service.

Adding the other three SMSPs' unused four-entry ingress queues gives an
estimated whole-SM software-visible capacity near 60 commands for 4-KiB S.G
(`48 + 3*4`).  Unlike the approximately 22-command G.S result, downstream S.G
continues draining while the relatively slow common intake is filling, so 60
is a topology-based estimate rather than a directly frozen occupancy count.

## The four Hopper async-completion mechanisms
| producer | SASS | completion tracked by | consumer waits via |
|---|---|---|---|
| `cp.async` (LDGSTS) | `LDGDEPBAR` (commit) | general scoreboard, **group count** | `DEPBAR.LE SBn, k` |
| `cp.async.bulk` / TMA **store** | `UTMASTG` + `UTMACMDFLUSH` | general scoreboard, **group count** (read) | `DEPBAR.LE SBn, k` |
| TMA **load** (`…mbarrier::complete_tx`) | `UTMALDG` | **mbarrier transaction (byte) count** | `SYNCS.PHASECHK.TRYWAIT` spin (+`CCTL.IVALL`) |
| `wgmma` | `HGMMA` | **dedicated GMMA group scoreboard** (`gsb0`) | `WARPGROUP.DEPBAR.LE gsb0, N` |

TMA uses the **most general** primitive — the mbarrier — which is also what
Blackwell `tcgen05.commit` targets (`tcgen05_vs_wgmma.md`). The byte-level
`expect_tx`/`complete_tx` tx-count lets one mbarrier track an arbitrary bulk
transfer size, unlike the group/instruction counters of cp.async and wgmma.

## Open questions
- The non-parity `mbarrier.try_wait` / `mbarrier.test_wait` blocking forms (with
  suspend/timeout) — whether they emit a different `SYNCS` sub-op than the
  `PHASECHK...TRYWAIT` spin.
- `UTMASTG`/`UTMAREDG` control-code shapes (store/reduce) vs `UTMALDG`.
  (`UBLKCP` — the non-tensor `cp.async.bulk` — is now documented in `../instr/ublkcp.md`.)
