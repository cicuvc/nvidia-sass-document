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

## 4. Hit/miss dichotomy — ESTABLISHED (one of the main results)

- **L1-hit path** (sectors preheated by a prior LDGSTS to the same lines):
  `SharedConf = R − #groups` **exactly**, pattern-independent (4B corpus
  25/25, 8B/16B 16/16). Every read pass beyond the group's first costs one
  conflict.
- **LDG-preheated lines do NOT hit for LDGSTS** (SecHit stays 0);
  LDGSTS-preheated lines DO hit. The bypass/allocate state is path-specific.
- Therefore `cp.async.ca` is effectively always on the miss path unless the
  same lines were fetched by an earlier cp.async.

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
4. **LDG vs LDGSTS allocate different L1 states** (§4) → separate tag-state
   bits or separate fill destinations for the bypass path.
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
  bounded error term on scattered patterns — the hit-path formula is exact
  and unaffected).
- Write/read wavefront co-issue schedule on scattered dst (4B ±1 residual;
  8B +1..+5, 16B +1..+7 under-prediction; global vs group-scoped delay
  penalties each fit only half the evidence — likely gated on fill arrival,
  the same missing timing ingredient as §6.2).
- MIO queue ordering guarantees; store-buffer drain behavior
  (`lsu_mio_structure.md` Q1/Q2).
- Tag-bank hash for lines ≥ 1024 (bits 10+; validated only to line 511).
- Why LDG-allocated lines are invisible to LDGSTS lookups.
- `cg`/bypass path behavior (all results above are `ca`).
- `Inst=2` (smsp__inst_executed_op_ldgsts) — LDGSTS replays/second issue?
