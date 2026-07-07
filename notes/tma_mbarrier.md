# TMA & mbarrier synchronization → SASS (sm_90a)

How the async-copy / tensor-memory-accelerator (TMA) sync primitives lower.
Verified via `tests/mbarrier_test.cu` and `tests/tma_test.cu`. Completes the trio
of Hopper async-completion mechanisms alongside `notes/depbar.md` (cp.async) and
`notes/wgmma.md` (GMMA scoreboard).

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
(`notes/depbar.md`) — only the commit point differs (`UTMACMDFLUSH` vs
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

## The four Hopper async-completion mechanisms
| producer | SASS | completion tracked by | consumer waits via |
|---|---|---|---|
| `cp.async` (LDGSTS) | `LDGDEPBAR` (commit) | general scoreboard, **group count** | `DEPBAR.LE SBn, k` |
| `cp.async.bulk` / TMA **store** | `UTMASTG` + `UTMACMDFLUSH` | general scoreboard, **group count** (read) | `DEPBAR.LE SBn, k` |
| TMA **load** (`…mbarrier::complete_tx`) | `UTMALDG` | **mbarrier transaction (byte) count** | `SYNCS.PHASECHK.TRYWAIT` spin (+`CCTL.IVALL`) |
| `wgmma` | `HGMMA` | **dedicated GMMA group scoreboard** (`gsb0`) | `WARPGROUP.DEPBAR.LE gsb0, N` |

TMA uses the **most general** primitive — the mbarrier — which is also what
Blackwell `tcgen05.commit` targets (`notes/tcgen05_vs_wgmma.md`). The byte-level
`expect_tx`/`complete_tx` tx-count lets one mbarrier track an arbitrary bulk
transfer size, unlike the group/instruction counters of cp.async and wgmma.

## Open questions
- The non-parity `mbarrier.try_wait` / `mbarrier.test_wait` blocking forms (with
  suspend/timeout) — whether they emit a different `SYNCS` sub-op than the
  `PHASECHK...TRYWAIT` spin.
- `UTMASTG`/`UTMAREDG` control-code shapes (store/reduce) vs `UTMALDG`.
  (`UBLKCP` — the non-tensor `cp.async.bulk` — is now documented in `notes/ublkcp.md`.)
