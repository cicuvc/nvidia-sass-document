# Async proxy — PTX→SASS ordering & instructions (sm_90)

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** low  
**Last verified:** unknown  
**Probe:** not recorded in this note  
**Open items:** 2 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: lives under notes/sm90/; no part named, so the default measurement site sm120 is assumed

## Conclusion

Scope: **general proxy vs async proxy** only (texture/tensormap out of scope).
The async proxy is the TMA / bulk-copy access path; it is physically distinct
from the generic proxy, so cross-proxy visibility needs an explicit proxy fence.
Test: `tests/async_proxy_test.cu` (sm_90a). Cross-refs: `memory_order_cta.md`
(generic-proxy ordering), `tma_mbarrier.md`.

## Which PTX ops touch which proxy
**Generic proxy (async *execution*, normal memory path — no proxy fence needed):**
- `cp.async` — spec: "weak memory operation performed in the generic proxy"
- `st.async` — "performed in the generic proxy"
- the `mbarrier` operand of every bulk op — "accesses its mbarrier operand using
  generic-proxy"

**Async proxy (`.async.bulk` family — needs `fence.proxy.async` to order vs generic):**
- `cp.async.bulk` (data copy; mbarrier signal still generic proxy)
- `cp.reduce.async.bulk` — explicit: "memory operations performed in the async proxy"
- `cp.async.bulk.tensor` / `cp.reduce.async.bulk.tensor` (data async; descriptor = tensormap proxy)
- `cp.async.bulk.prefetch[.tensor]`

## SASS vocabulary
| PTX | SASS | pipe |
|---|---|---|
| `cp.async.bulk.shared::cta.global` | `UBLKCP.S.G [dst],[src],size` (gated by `ELECT`) | `udp_pipe` |
| `cp.async.bulk.tensor` (descriptor form) | `UBLKCP…` (`ublkcp_desc_`) | `udp_pipe` |
| `mbarrier.arrive.expect_tx` | `SYNCS.ARRIVE.TRANS64` | `mio_pipe` |
| `mbarrier.try_wait.parity` | `SYNCS.PHASECHK.TRANS64.TRYWAIT` | `mio_pipe` |
| `fence.proxy.async` | `MEMBAR.ALL.GPU` + `FENCE.VIEW.ASYNC.S` | `mio_pipe` |
| `fence.proxy.async.global` | `FENCE.VIEW.ASYNC.G` (no MEMBAR) | |
| `fence.proxy.async.shared::cta` | `MEMBAR.ALL.CTA` + `FENCE.VIEW.ASYNC.S` | |
| `fence.proxy.async.shared::cluster` | `MEMBAR.ALL.GPU` + `FENCE.VIEW.ASYNC.S` | |
| `fence.proxy.alias` (contrast) | `MEMBAR.SC.GPU` + `MEMBAR.SC.SYS` + `CCTL.IVALL` | |

`FENCE.VIEW.ASYNC.{S,G}` is a dedicated instruction (opcode `0x3c6`, `mio_pipe`;
FORMAT `/VIEWONLY:type /ASYNCONLY:syncType /{S,G}ONLY:memType`) — **not** a MEMBAR.
It bridges the async proxy's "view" of memory to the generic proxy. `.S`=shared,
`.G`=global. When a state space is given, only the matching `FENCE.VIEW.ASYNC.*`
is emitted (global → `.G`, no MEMBAR); the unscoped/shared/cluster forms add a
`MEMBAR.ALL.<scope>` for the ordinary-memory side.
`UBLKCP` = uniform bulk copy (TMA), on the **uniform datapath** (`udp_pipe`),
issued by a single elected lane. `SYNCS.*` = the transaction-mbarrier family
(`TRANS64` = 64-bit transaction barrier).

## TMA load pipeline (verified SASS order)
`tma_load` kernel: global→shared bulk copy, mbarrier completion, then read.
```
mbarrier.init            -> SYNCS init
fence.proxy.async.S      -> MEMBAR.ALL.CTA ; FENCE.VIEW.ASYNC.S   # init visible to async proxy
ELECT                                                            # one lane drives the TMA
cp.async.bulk            -> UBLKCP.S.G [smem],[gmem],size         # async-proxy write to shared
mbarrier.arrive.expect_tx-> SYNCS.ARRIVE.TRANS64                 # expect `size` bytes
... (wait loop)
mbarrier.try_wait        -> SYNCS.PHASECHK.TRANS64.TRYWAIT        # completion (generic-proxy signal)
fence.proxy.async.S      -> MEMBAR.ALL.CTA ; FENCE.VIEW.ASYNC.S   # async->generic bridge
ld.shared                -> LDS                                   # generic-proxy read of TMA data
```
**Key point:** the mbarrier wait confirms *completion* of the async copy, but the
data was written via the **async proxy**; the subsequent generic-proxy `LDS` is
not guaranteed to observe it until a `FENCE.VIEW.ASYNC.S` bridges the proxies.
Hence the `fence.proxy.async` between the wait and the read — completion ≠
cross-proxy visibility. This is the async-proxy analog of the acquire/release
machinery studied for the generic proxy in `memory_order_cta.md`.

## Producer side (TMA store, shared→global) + generic-vs-async proxy contrast
Test: `tests/tma_store_test.cu`.

**`cp.async.bulk.global.shared::cta.bulk_group` (async proxy):**
```
STS                                    # fill shared (generic proxy)
BAR.SYNC                               # __syncthreads
MEMBAR.ALL.CTA ; FENCE.VIEW.ASYNC.S    # fence.proxy.async: generic→async BEFORE bulk store
UBLKCP.G.S [gmem],[smem],size          # TMA store (async proxy), udp_pipe, elected lane
DEPBAR.LE SB0, 0x0                     # commit_group + wait_group 0 → DEPBAR
CCTL.IVALL
```
`UBLKCP.G.S` ctrl: `rd_sb=2` (late shared-source read), `wr_sb=7`. `bulk_group`
completion tracked on `SB0`, drained by `DEPBAR.LE SB0, 0x0`.

**`cp.async` (Ampere, generic proxy) — contrast:**
```
LDGSTS.E [smem],[gmem]        # async copy, GENERIC proxy
LDGDEPBAR                     # commit_group
DEPBAR.LE SB0, 0x0            # wait_group 0
BAR.SYNC
LDS                           # read — NO FENCE.VIEW.ASYNC
```

**Decisive confirmation:** `cp.async` (generic proxy) needs **no** `FENCE.VIEW.ASYNC`
before reading landed data — only group-completion + BAR.SYNC. `cp.async.bulk`
(async proxy) **requires** `FENCE.VIEW.ASYNC` on both sides (producer: generic→async
before bulk store; consumer: async→generic after completion, before LDS). The
presence/absence of the view-fence exactly tracks the proxy. Both paths share
the scoreboard-group completion (`DEPBAR.LE SBn`); the proxy fence is the only
extra machinery — the SASS embodiment of PTX §8.6 "different proxies need a proxy
fence."

## History / retracted hypotheses

> Claims below were **superseded, refuted, or never settled** by later work; they are kept
> for provenance. Do not cite them as current.

## Open questions
- `FENCE.VIEW.ASYNC` control-word / scoreboard interaction with `SYNCS`.
- Whether `commit_group` is ever emitted as a distinct opcode (vs folded into the
  following `DEPBAR` or `SYNCS.PHASECHK`).

