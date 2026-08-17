# SM memory microarchitecture — synthesis (sm_90 family, validated on sm_120)

Consolidated picture of the SM-internal memory path: what is **established**
(directly measured, reproducible), what is **inferred** (model fits, mechanism
unproven), and what is **open**. Sources: `lsu_mio_structure.md` (MIO/arbiter,
scoreboards), `memory_order_cta.md` (single-arbiter coherence), `scoreboards.md`,
`control_codes.md`, `async_proxy.md` (two data movers), `sm120_findings.md`
(encoding substrate), `shared_bank_conflicts.md` (LDGSTS/L1TEX model — the
primary source for §2–§4 below).
Tests: `tests/bankconf/*`, `arch/l1tex/*` (probe + regress + datasets),
`tests/st_readsb.cu`, `tests/readsb_*.cu`, `tests/async_proxy_test.cu`.

## 1. Pipeline skeleton — ESTABLISHED

- Each SM: 4 SMSPs, each with a per-SMSP **MIO queue** → a **single per-SM
  arbiter** → shared L1TEX (L1 data + shared memory). NVIDIA forum description
  of the MIO as the SM-scoped shared block matches this. Single arbiter also
  explains CTA-scope strong-op coherence without fences
  (`memory_order_cta.md`).
- Issue is in-order per SMSP until stall/throttle/warp-swap/scoreboard block.
- Scoreboard discipline (`scoreboards.md`, `control_codes.md`):
  - **Stores are fire-and-forget**: `wr_sb=7` (no completion scoreboard); the
    warp never waits for global visibility.
  - Store source register read is **deferred past issue** (`rd_sb` taken);
    ptxas dead-reckons ~6 cycles (`stall=6`) for the WAR and uses the
    scoreboard as dynamic backstop → source read happens at an LSU-internal
    latch shortly after issue, not at completion.
  - Loads hold the **write scoreboard** until the response returns (full
    memory latency).
- sm_120 shares the exact encoding substrate with sm_90/sm_100 and the memory
  model is unchanged since Turing → the microarchitecture is largely inherited
  (`sm120_findings.md`).

## 2. L1TEX tag stage (LDGSTS) — ESTABLISHED

Exact model (`shared_bank_conflicts.md` §4; 4B 400/400, 8B 60/60, 16B 60/60):

- Tag unit handles **distinct 128B lines**; **4 tag banks** with hash
  `bank = (l ^ l>>2 ^ l>>4 ^ l>>6 ^ l>>8) & 3` (validated for lines 0–511,
  i.e. 64KB span; bits 10+ untested — chain may keep folding).
- Tags pack into **tag wavefronts** greedily in appearance order, one tag per
  bank per wavefront: `TWf = max per-bank load`, `TagConf = TWf − 1`,
  `TSetAcc = #tags`, `TReq = 1` (whole warp's tag stage = 1 request).
- Misses tracked at **32B sector** granularity (`Sectors` = distinct sectors).
  On sm_120 cold path, `SecHit` is always 0 for `cp.async.ca`.

## 3. Data-stage formation rules — ESTABLISHED

- **Lane groups**: 4B = whole warp, 8B = half-warps {0-15}{16-31},
  16B = quarter-warps. Formation and conflicts never cross group boundaries.
- **Read passes** form per group by greedy bank arbitration, scan order
  (tag-wavefront, lane); a multi-word lane occupies consecutive banks
  atomically (`bank = (src_word + k) % 32`, k = 0..size/4−1).
- **No same-word coalescing** for LDGSTS: identical addresses in a group do
  not merge (unlike normal LSU shared ops).
- **L1 bank mapping is sequential `word % 32`, no swizzle** (fits 400/400).
- **Read/write separation**: read passes on src banks; write passes form
  **per lane group** (no cross-group pairing, verified with dst-pairing
  probes) and issue FIFO riding read wavefronts
  (`c = max(maxread_j, prev+1)`); a write delayed inside the read phase pays
  **+1 cycle (4B only)**. `SharedWf = max(R, last_write+1)`. With one read
  pass, SharedWf = per-bank dst chain length (chains combine by max, not sum).
- Read side is **dst-invariant** (same src × 4 dst patterns → identical
  read conflicts). Conflicts are on the **`cmd_read`** path.
- Structured patterns: zero suppression — per-(bank, tag-wavefront) re-serve
  history rule is exact (64/64 4B regress, 24/24 8B+16B regress).

## 4. Hit/miss dichotomy — CORRECTED 2026-08-13 (clean measurements)

- **cp.async `SharedWf` is hit/miss-invariant**: on an L1 hit the shared
  write wavefronts are **byte-identical to the cold miss path** (400/400
  4B, 60/60 8B, 60/60 16B), measured with warm=1 (LDG preheat, zero
  op_ldgsts pollution) and zero L2 refetch (xbar sectors = 0). The write
  side is NOT absorbed into read wavefronts on hits.
- The earlier "hit-path `SharedWf = R` / `SharedConf = R − #groups`"
  results were **subtraction artifacts** of warm=2 (two cp.asyncs per
  run): `warm2 − cold == R` ⟺ `preheat-only == R`, and the preheat takes
  R wavefronts only because its scratch dst is conflict-free (W=1).
  Verified directly with the new cg=3 preheat-only probe mode (400/400).
- **No fill-provenance line state**: warm=4 (cp.async fill + LDG touch,
  then main cp.async) ≡ warm=2 (400/400).
- **cp.async never reads the lgds data banks**: LgdsWf contribution = 1
  on both miss and hit (400/400); data movement shows only as
  `mem_shared` wavefronts.
- **LDG-preheated lines DO hit** for both LDG and LDGSTS (SecHit =
  Sectors, SecMiss = 0, 400/400). The old "LDG lines invisible to
  LDGSTS" claim came from the warm=1 preheat being **silently
  compiler-eliminated** (dead result register) — fixed by storing the
  preheat value to a shared scratch slot; always check SASS.
- **Hit-path SharedConf is unmodeled** (≠ R−#groups, ≠ cold, ≠
  unsuppressed read+write; ≈ cold + 0..+5).
- **Consequence**: since hits involve no L2 traffic yet produce identical
  wavefronts, the scattered-dst extra write wavefronts are **structural,
  not latency-driven** — the exact-rule search is reopened with the
  warm=1 hit path as a timing-free testbed.
- **Plain LDG circuit reuse**: the T-stage is fully shared with LDGSTS
  (all tag counters identical, 400/400 cold+hit). LDG hits read the L1
  data banks: `LgdsReadWf = R` with **same-address broadcast merge**
  (400/400 4B, 60/60 8B/16B). LDG miss-path `LgdsReadWf` is unmodeled
  (≈ TWf + extras) but exactly reproducible.

## 5. Two data movers into shared memory — ESTABLISHED

- `cp.async` (LDGSTS) = **generic proxy**, per-lane LSU-driven; no proxy
  fence needed vs normal ld/st.
- `cp.async.bulk[.tensor]` (TMA) = **async proxy**, physically distinct
  engine; cross-proxy visibility needs `fence.proxy.async`
  (`async_proxy.md`, `tma_mbarrier.md`).

## 6. INFERRED (model-consistent, mechanism unproven)

1. **T-stage / data-stage overlap**: tag wavefronts are processed one per
   cycle, and data passes run in rough lockstep with them (the free-hit
   cases cluster at tag-wavefront ≈ pass index − 1 in small patterns).
2. **Miss-path suppression = global fill-queue / MSHR occupancy effect**:
   re-serve hits are sometimes free on random scattered patterns (up to 7 of
   18 in one case). The effect is *hypersensitive* — removing any one hit
   lane from the minimal case kills it; isolated single-hit replicas never
   show it; strength grows with pattern complexity. No local per-lane rule
   fits ~40 probes. Consistent with a small number of SM-shared fill/return
   buffers whose occupancy feeds back into conflict accounting.
3. **Fill bypass to the data stage**: miss data likely services the waiting
   access directly from the fill/return path without a data-array read —
   the simplest explanation for free re-serves.
4. ~~LDG vs LDGSTS allocate different L1 states~~ **DISPROVEN 2026-08-13**:
   LDG-allocated lines hit normally for both LDG and LDGSTS; the apparent
   difference was a compiler-eliminated preheat (§4).
5. **Shared SRAM is 1R+1W ported**: write chains and read passes timeshare
   (dual-row-write conjecture disproven experimentally; sequential bank map
   fits 400/400).
6. **Per-warp formation, SM-shared queues**: multi-warp interference disturbs
   timing-sensitive counters (SharedConf/GlobalConf/TWf) but not
   SharedWf/Sectors → pass formation is warp-local, queue/fill structures
   are SM-shared.
7. **Per-serve-occurrence conflict accounting** (needs confirmation): a bank
   that served the same tag wavefront *twice* before a hit appears to charge
   2 conflicts for that hit (S3 probe).
8. Composite wavefront counters: `TotalWf = ShAllWf + LgdsWf`; the shared
   pipe interleaves shared-op wavefronts and LDGSTS write-back wavefronts.

## 7. OPEN

- Exact trigger of miss-path conflict suppression (see §6.2; best-effort
  heuristic in `shared_bank_conflicts.md` §4.3 exemption rule; recommend a
  bounded error term on scattered patterns — hit-path conflicts are now
  known to be unmodeled too, §4).
- Scattered-dst extra write wavefronts (2026-08-14 pm update): the
  write side is now modeled as rank0 first passes at read-batch cycles
  + a deferred pool draining from cycle R0 + rank≥1 (buffered) lanes
  eligible from their H-Y-floored arrival on any cycle, with per-word
  WAW eviction (later lane wins), keeper-bank gating, and an
  RB read-port block (`simulate_v68`,
  `shared_bank_conflicts.md` §4.4). Verified: 40/40 probes, 47/47
  families, 51/52 ride families, 130/400 clean 4B bulk (v49 static:
  112; `model.py` 196/400 remains the bulk leader but is probe-invalid
  — its FIFO+penalty wins are coincidental). Key structural facts
  established: read batches don't split across lines; deferred replays
  merge across batches after R0 (W4=11) but never into first-pass
  cycles (Z0=10); rank≥1 lanes mix into any cycle unless a packed lane
  writes their keeper's bank. AB5 further shows that rank0 nonself writes
  are RB-blocked even with clean batch0/no pending/no WAW; only rank≥1 keeps
  the no-pending exemption. Still open: the ±1–2 residual on random
  multi-batch patterns (idx54/42/205 remain +1/+1/−1, with SharedConf
  6/9/15), Z3 off-by-one, 8B/16B write-schedule generalization
  (v68: 9/60, 28/60 — untouched).
- LDG miss-path `LgdsReadWf` formation (≈ TWf + extras, deterministic but
  unmodeled). This is independent of cp.async SharedWf arrival timing: all
  400 rows satisfy `warmldg.LgdsWf = cold_LDG.LgdsWf + 1`, resolving idx54's
  13 as preheat miss-path pollution and rejecting arrival=return cycle.
  LDGSTS hit-path SharedConf formation is also open.
- MIO queue ordering guarantees; store-buffer drain behavior
  (`lsu_mio_structure.md` Q1/Q2).
- Tag-bank hash for lines ≥ 1024 (bits 10+; validated only to line 511).
- ~~Why LDG-allocated lines are invisible to LDGSTS lookups~~ RESOLVED
  2026-08-13 (compiler-eliminated preheat artifact; they hit fine).
- `cg`/bypass path behavior (all results above are `ca`).
- `Inst=2` (smsp__inst_executed_op_ldgsts) — LDGSTS replays/second issue?
