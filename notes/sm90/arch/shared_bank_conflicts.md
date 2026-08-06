# Shared memory & cp.async bank-conflict characterization — Blackwell sm_120

Measured on **RTX 5090 (GB202, sm_120)**, CUDA 13.1, driver 590.48.01.
Cross-refs: `lsu_mio_structure.md`, `memory_model.md`.
Harnesses: `tests/bankconf/` (harness.cu, harness_v2.cu, harness_v4.cu,
harness_cpasync.cu, harness_gld.cu, harness_align.cu, harness_lx2.cu,
zhihu_cpasync.cu + run.py, runcp.py, rungld.py, runlx.py).

---

## 1. Metric reference

All counters from `ncu --csv --metrics`. Short names used throughout; full ncu
paths (under `l1tex__` unless prefixed).

### Shared data-stage

| short | full ncu metric | description |
|-------|-----------------|-------------|
| `SharedWf` | `data_pipe_lsu_wavefronts_mem_shared_op_ldgsts` | Shared-memory data-stage wavefronts for LDGSTS writes. One wavefront = one 128 B (32-bank) pass through the data array. |
| `SharedWfSt` | `…_op_st` | STS data-stage wavefronts. |
| `SharedWfLd` | `…_op_ld` | LDS data-stage wavefronts. |
| `SharedConflict` | `data_bank_conflicts_pipe_lsu_mem_shared_op_ldgsts` | Bank conflicts on the shared-write side (LDGSTS). |
| `SharedConflictSt` | `…_op_st` | STS bank conflicts. |
| `SharedConflictLd` | `…_op_ld` | LDS bank conflicts. |

### Global / L1 data-array

| short | full ncu metric | description |
|-------|-----------------|-------------|
| `GlobalConflict` | `data_bank_conflicts_pipe_lsu_mem_gds` | Global L1 data-array bank conflicts (reads or fills).  Same banking rule as shared: `(addr/4)%32`. |
| `GlobalConflictLd` | `…_gds_op_ld` | Global-load bank conflicts (LDG). |

### T-stage / tag array

| short | full ncu metric | description |
|-------|-----------------|-------------|
| `TstageWf` | `t_output_wavefronts_pipe_lsu_mem_global_op_ldgsts_cache_access` | T-stage output wavefronts (tag→sector pass). One wavefront ≤ 16 sectors ≈ 512 B. |
| `Sectors` | `t_sectors_pipe_lsu_mem_global_op_ldgsts_cache_access` | 32-byte sectors requested from L1/L2. 512 B coalesced = 16 sectors. |
| `SectorHit` | `…_lookup_hit` variant | Sector requests that hit L1 tag+data. |
| `TagConflict` | `t_set_conflicts_pipe_lsu_mem_global_op_ldgsts_cache_access` | Extra cycles from L1 tag set conflicts. `= TstageWf − 1` in all cases. |

### Data-stage totals

| short | full ncu metric | description |
|-------|-----------------|-------------|
| `TotalWf` | `data_pipe_lsu_wavefronts` | Total data-stage LSU wavefronts (read + write, all clients). |
| `CmdReadWf` | `…_cmd_read` | Data-stage read wavefronts. |
| `CmdWriteWf` | `…_cmd_write` | Data-stage write wavefronts. |
| `LgdsWf` | `data_pipe_lsu_wavefronts_mem_lgds` | local/global/dshared data-stage wavefronts (global-side of cp.async). |

### Instruction counts

| short | full ncu metric | description |
|-------|-----------------|-------------|
| `InstCpasync` | `smsp__inst_executed_op_ldgsts` | Warp instructions executed: LDGSTS. |
| `InstGlobalLd` | `smsp__inst_executed_op_global_ld` | Warp instructions executed: global loads. |
| `InstCacheAccess` | `sm__sass_inst_executed_op_ldgsts_cache_access` | `cp.async.ca` instructions (cache L1). |
| `InstCacheBypass` | `sm__sass_inst_executed_op_ldgsts_cache_bypass` | `cp.async.cg` instructions (bypass L1). |

### Miscellaneous

| short | full ncu metric | description |
|-------|-----------------|-------------|
| `ArbConflict` | `data_bank_conflicts_type_arbitration` | Bank conflicts from L1 client arbitration. |
| `Cycles` | `sm__cycles_elapsed.avg` | Average elapsed cycles per SM. |

---

## 2. Non-vectorized LDS/STS (scalar, 32-bit)

One warp, one `ld/st.shared.u32` (volatile inline PTX). Bank = `(byte_addr/4) % 32`.

### Rule

> **passes = max over the 32 banks of (# distinct 32-bit words in that bank).**
> conflict = passes − 1.

- Same word (same bank + same address) → **coalesces for free**, any fan-out.
- Same bank, different words → conflict.
- Distinct banks → never conflict.

### Evidence

| pattern (word index per thread) | LDS W/C | STS W/C | hottest-bank distinct words |
|---|---|:---:|:---:|:---:|
| identity `t` | 1/0 | 1/0 | 1 |
| broadcast `0` | **1/0** | **1/0** | 1 (coalesce) |
| stride 2 / 4 / 8 / 16 | 2/1 · 4/3 · 8/7 · 16/15 | same | 2 · 4 · 8 · 16 |
| stride 32 (all bank 0) | **32/31** | **32/31** | 32 |
| stride 33 (coprime) | 1/0 | 1/0 | 1 |
| 31 threads→word0 + 1→word32 | 2/1 | 2/1 | 2 |

### Key result: STS same-address does NOT conflict

LDS and STS are **byte-identical** in every pattern. The common belief that "stores
to the same address conflict" is false on this GPU (matches CUDA guide: same
32-bit word → no bank conflict).

---

## 3. Vectorized shared access (LDS/STS)

### 3.1 Unified transaction model

Let `w` = words/lane (1/2/4), `G = 32/w` the lane-group size (32/16/8).

A shared transaction touches all 32 banks (1 word/bank), gathered from a
**contiguous run of `G` lanes:**
- scalar: whole warp (32)
- v2: half-warps {0-15}, {16-31}
- v4: quarter-warps {0-7}, {8-15}, {16-23}, {24-31}

Default number of transactions = `w` (the floor). Conflicts are counted
**independently inside each lane-group** using the scalar rule on `G × w = 32`
words. `wavefronts = Σ passes(group)`. Same-word coalescing still applies within
each group.

### 3.2 v2 (LDS.64 / STS.64) — 64-bit

**Floor: 2** wavefronts. `harness_v2.cu`.

#### Partitioning — per half-warp

Boundary pinned at lane 15|16 (distinguishing patterns: whole-warp aggregation
refuted; even/odd-lane split refuted).

#### Load merge (below floor)

Loads can collapse the two half-warp transactions into **1 wavefront** when:
1. **Warp-scope conflict-free** (≤1 distinct word/bank), AND
2. **Crossbar-routable** lane→word map.

Routable set (empirical): full broadcast; contiguous power-of-2 lane blocks
(tid^1÷2, quad÷4, oct÷8); reversed & rotated contiguous; intra-4-lane
single-bit-flip sharing (tid^1=bit0, tid^2=bit1).

Not routable: tid^3, tid^4+, interleaved runs (half_lo_hi), anything with a real
bank conflict.

**Stores never merge below the floor** (always ≥2). The merge is all-or-nothing;
it's a crossbar-routing property, not just a bank-count property.

#### Load/store asymmetry (scalar + v2)

| | scalar | v2 |
|---|---|---|
| conflict regime | load ≡ store | load ≡ store |
| broadcast/merge | both coalesce to 1 | load →1, store →2 |

The **only** asymmetry is the v2 load merge (below the 2-wavefront floor).

### 3.3 v4 (LDS.128 / STS.128) — 128-bit

**Floor: 4** wavefronts. `harness_v4.cu`.

#### Partitioning — per quarter-warp

Boundary pinned at lanes 7|8, 15|16, 23|24. `wavefronts = Σ passes(Qi)`.
Stores follow pQtr everywhere (proven: `dist_q0` = 6 = pQtr, `bnd_in` = 5,
`bnd_cross` = 4).

#### Load merge (below floor)

Load quarter-sum collapses to **2** (not 1) — delivery is limited to 64 bit/lane/
wavefront, so the merged floor is `ceil(4/2)=2`. Same routable set as v2.
All-or-nothing. **Stores never merge** (floor 4).

| pattern (v4) | LDS Wf | STS Wf | note |
|---|---|:---:|:---:|---|
| consec | 4 | 4 | quarter floor |
| broadcast | **2** | 4 | merged load vs store floor |
| share:1/2, quad, oct | **2** | 4 | routable merge |
| share:4/8/16 | 4 | 4 | not routable |
| estride 2/4/8 | 8/16/32 | 8/16/32 | conflict scaling, load=store |
| `dist_q0` / `bnd_in` / `bnd_cross`| 6/5/4 | 6/5/4 | quarter boundaries confirmed |

---

## 4. cp.async / LDGSTS — full execution model

Harness: `l1tex/probe.cu` (per-lane src/dst byte offsets via `__grid_constant__`,
size 4/8/16, active mask, one warp per launch, fresh 8 MB src per launch),
driver `l1tex/drv.py`, reference simulator `l1tex/model.py` (`simulate(goff,
soff, size, mask)`), regressions `l1tex/regress.py` (4 B, 64 cases) and
`l1tex/regress816.py` (8 B/16 B, 24 cases). Random datasets: `l1tex/data4.jsonl`
(400×, 4 B scattered), `data_coal.jsonl` (60×, 4 B dst=coalesced),
`data8/16.jsonl`, `data8/16_coal.jsonl` (60× each).

**Scope.** All formulas below are verified for **isolated single-warp
execution**, which is bit-exact reproducible. Under multi-warp cp.async
interference (`probe_mw.cu`): wavefront/sector counters stay exactly additive
and undisturbed, but `SharedConf`/`GlobalConf`/`TWf`/`TSetAcc`/`TagConf` are
disturbed even on disjoint memory. Offsets must be size-aligned (misaligned
cp.async faults).

### 4.1 LSU partitioning — lane groups, NO coalescing

| size | SASS | lane-group | #groups |
|---:|---|---|:---:|
| 4 B | LDGSTS.E | whole warp | 1 |
| 8 B | LDGSTS.E.64 | half-warps {0-15}{16-31} | 2 |
| 16 B | LDGSTS.E.128 | quarter-warps {0-7}…{24-31} | 4 |

**No same-word/same-sector coalescing:** identical addresses do NOT merge
(verified with all-32-lane broadcast probes at every size). Each lane is an
independent copy descriptor; the lane group is the unit of data-stage
formation (read formation and conflict history do not cross group boundaries).

### 4.2 T-stage (verified exact: 400/400 random 4 B, 60/60 8 B, 60/60 16 B)

- `tags` = distinct 128 B lines touched (lane-appearance order).
- Tag bank: `bank(l) = (l ^ l>>2 ^ l>>4 ^ l>>6 ^ l>>8) & 3` — i.e.
  `bank bit0 = l0^l2^l4^l6^l8`, `bit1 = l1^l3^l5^l7^l9`. Validated for lines
  0–511 (64 KB span); the shorter 3-shift form is identical below line 256,
  which is why the old hash (never validated ≥ line 128) broke exactly on the
  16 B datasets whose patterns reach line 511. Hardware re-verified with
  bank-skew K-sweeps built entirely from lines 256–511 (K8/K12/K16 exact).
  Behavior for lines ≥ 1024 (bits 10+) is untested — the chain may keep
  folding (`l>>12`, …).
- Tags pack greedily in appearance order into tag wavefronts, one tag per bank
  per wavefront; `TWf` = number of tag wavefronts (= max tag-bank load).
- `TagConf = TWf − 1`; `TSetAcc = #tags`; `TReq = 1`.
- `Sectors` = distinct 32 B sectors touched (union over lanes).
- The old "16 B T-stage gap (6/60 off ±1–3)" was entirely this hash artifact:
  with the extended hash, `TWf` is exact on all 60 scattered + 60 coalesced
  16 B patterns, and all regressions pass (4 B 64/64, 8 B+16 B 24/24).

### 4.3 Data stage — read side (L1 data-array banks)

Per lane group, **read passes** form by greedy bank arbitration:
`read_bank(t) = (src_byte/4 + k) % 32`, `k = 0..size/4−1` (a lane occupies
`size/4` consecutive banks atomically). Scan order is **(twf, lane)
lexicographic** — NOT pure lane order (verified via composition kernels).
Each pass serves ≤1 word per bank. `R` = number of read passes.

**Read conflicts.** Per bank (scoped to the group), remember the set of twfs
served by earlier passes. A pass `i > 0` conflicts once per **distinct twf**
that some lane's bank already served (`SharedConf` read component). Per-pass
multi-lane hits on the same twf count once; different twfs count each.

Exemption (4 B only): the LAST read pass is free if it is a single lane
hitting only the final twf (`TWf ≥ 2`), the word is first-time on its bank,
and `R−1 ≤ 2·TWf` (rides the final twf's data drain).

**Read side is dst-invariant** (verified: same src with 4 different dst
patterns → identical read-conflict counts; ±1 deltas trace to the write side).

**Hit vs miss dichotomy (verified).** Warm the pattern's sectors, then re-run
the identical cp.async and subtract the cold execution's counters:

- **L1-hit path** (`SecHit = Sectors`): `SharedConf = R − #groups` **exactly**
  (4 B 25/25 kernel corpus, 8 B/16 B 16/16 random). Every read pass beyond
  each group's first costs exactly one conflict, pattern-independent. This is
  the old floor formula `SharedWf − max(#groups, TstageWf)` with
  `TstageWf = 1` (lookups hit).
- **L1-miss path** (fresh src): the twf-history rule above applies, but some
  predicted hits are **suppressed** (miss-stream absorption; mechanism below).
  Structured sweeps have zero suppression (hit rule exact, e.g. A32's 28 = all
  its actual hits); random scattered patterns suppress up to ~30 % of hits.
- **LDG-warmed lines do NOT produce LDGSTS hits** (`SecHit = 0` after an LDG
  warm of every touched sector); LDGSTS-warmed lines DO hit for a later
  LDGSTS. LDGSTS lookups appear to consult different L1 state than LDG
  allocations (eviction class or fill path), so in practice cp.async.ca source
  reads are effectively always on the miss path unless a prior cp.async
  fetched the same lines.

Accuracy (miss path): structured sweeps exact at all sizes; random scattered
src, dst=coal: 4 B 47/60, 8 B 17/60, 16 B 7/60 — all misses are small
over-predictions from suppression. Suppression is absent on the hit path, so
it is a miss-stream phenomenon: re-served banks whose sectors are still in
flight appear to be satisfied without a new data-array access. Exact trigger
(sector arrival order/rate vs pass issue cycle) **not yet isolated**.

### 4.4 Data stage — write side (shared-memory banks)

Write passes form **per lane group** (whole warp / half / quarter, same
groups as the read side) by lane-greedy arbitration on
`write_bank(t) = (dst_byte/4 + k) % 32` — verified with dst-pairing probes
(8 B: 16 contiguous lanes on banks {0,1} + 16 on {2,3} give 32 write
wavefronts, NOT 16; alternating lanes pair and give 16; 16 B: quarter
blocks behave the same). Lanes pair only within their own group; there is
no cross-group write merging.

Passes issue **FIFO riding the read wavefronts**: pass `j` issues at
`c = max(maxread_j, prev+1)` where `maxread_j` = read cycle of its last
lane. At **4 B only**, a pass delayed inside the read phase
(`maxread < c < R`) pays a +1-cycle penalty.
`SharedWf = max(R, last_write_cycle + 1)`.

R=1 probes (coalesced src, k lanes to one dst bank): `SharedWf = k`
(per-bank chain serializes 1/cycle; two hot banks drain in parallel — chain
lengths combine by max), `SharedConf = k−1` = number of deferred writes.

A write pass whose banks are all free in the current read wavefront rides it
for free — this is why dst=coal adds **zero** wavefronts (`SharedWf = R`).

Accuracy: 4 B regress 64/64, dst sweeps exact at 8 B/16 B; **dst=coal random
60/60 at all sizes** (per-group formation fixed the old 8 B/16 B "−1 merge"
cases — they were write-side, not read-side). Random scattered dst: 4 B
196/400 (residual ±1, symmetric), 8 B 5/60, 16 B 25/60.

**Open — co-issue schedule on scattered dst.** The FIFO `max(mr,prev+1)`
rule under-predicts 8 B/16 B by up to +7. Variants tried (2026-08-06): a
global "delayed-in-read-phase" +1 penalty for all sizes fits random 8 B
(26/60) but breaks the structured coal/dst sweeps (+1 ghost wavefront when
group A's second write rides group B's read); a group-scoped penalty
(`c ≤ group_read_end`) keeps structured exact but fits random poorly
(8/60). No single rule fits both ⇒ the true schedule likely gates writes on
fill/sector arrival, not just read-pass indices — the same missing
timing ingredient as the read-side suppression (§4.10). Interim: 4 B
penalty retained (64/64 + 196/400); 8 B/16 B scattered-dst SharedWf has a
bounded (+1..+7) error.

### 4.5 Conflict-counter composition

- `SharedConf` = read-side hits (§4.3) + write-side deferrals (§4.4).
- `GlobalConf` tracks the read-side portion (4 B: `= SharedConf` when
  read_conf > 0 else 0; this fusion rule is approximate on scattered dst).
- On dst sweeps at 8 B/16 B, write-side conflicts appear in `SharedConf`
  with `GlobalConf = 0`.

### 4.6 Structured sweep tables (all exact vs model)

4 B (dst=coal): `SharedWf = R`, `SharedConf` = hit rule; src stride
s∈{1,2,3,4,5,8,16,31,32,33,64} all exact; broadcast: R=32, conf=31.

8 B (dst=coal): coal: SWf=2, conf=0; src*2: 4/2; src*4: 8/6; src*8: 16/12;
src*16/32: 32/24; broadcast: 32/30. dst sweeps: dst*2: 4/2; dst*4: 8/6;
dst*8: 16/14; dstBcast: 32/30.

16 B (dst=coal): coal: SWf=4, conf=0; src*2: 8/4; src*4: 16/12; src*8/16/32:
32/24; broadcast: 32/28. dst sweeps: dst*2: 8/4; dst*4: 16/12; dst*8: 32/28;
dstBcast: 32/28.

On these structured patterns the hit rule reduces to
`SharedConf = SharedWf − max(TWf, #groups)` (every pass beyond the group's
first `max(TWf, #groups)` wavefronts conflicts). This formula does NOT
generalize to sparse random patterns (see §4.3).

### 4.7 Data-transaction split order — L1-read FIRST (verified)

Test: 8-thread predicated 16 B cp.async, one tag transaction. L1 read has
3-way conflict (threads {0,1,2} on bank 0); shared write has 3-way conflict
(threads {0,1,3} on bank 4). Overlap = {0,1}.

Measured: **`SharedWf=3, SharedConf=GlobalConf=2`**.

- **L1-read-first:** 3-way read split → 3 data txs. Overlapping write conflict
  {0,1,3} lands in different read-split groups → no further splits. ✓
- **Write-first:** would give shW=4. ✗

### 4.8 Sector-overflow misalignment

If the source base is not sector-aligned (512 B), a warp load may span 1 extra
sector (17 instead of 16), forcing `TWf=2`; the 2nd tag wavefront delivers the
overflow sector → 1 extra shared pass → `SharedWf += 1`.

### 4.9 ca vs cg (bypass L1)

- `cp.async.ca` (default): all counters above; clean model.
- `cp.async.cg` (16 B only, bypass L1): standard counters read **0**; shared
  writes appear on `_cache_bypass` sub-counters where the bank-conflict counter
  is **0 for every tested pattern** and the wavefront sub-counter does not follow
  the group model. The bypass path stages global→L2→shared differently. **Open.**

### 4.10 Open questions

- **Miss-path conflict suppression:** on the miss path some twf-history hits
  are not counted; hit path counts everything (`R − #groups`). Suppression =
  miss-stream absorption of in-flight re-reads; the precise arrival-vs-issue
  timing rule is not isolated. Dominant error source on random patterns.
  **Candidate mechanisms (2026-08, ranked):**
  - **H-I: return-buffer residency.** Miss data lands in a small LSU-internal
    return buffer (FIFO or a small cache with unknown replacement policy)
    before consumption. A multi-lane pass completes only when ALL its lanes'
    sectors arrived; early data idles in the buffer during the wait, and
    re-serves issued during that window are served from the buffer → free.
    Explains: single-lane chains suppress nothing (consumed immediately),
    random multi-lane passes suppress (arrival skew), hit path suppresses
    nothing (data already in array), dst-invariance.
  - **H-B: fill-stream scheduling.** The miss-path data stage is driven by the
    physical fill stream; logical passes that re-serve banks/sectors the
    stream has not reached yet merely wait (free); re-serving data the stream
    already passed requires an array re-read (conflict). Suppression =
    order-mismatch between logical passes and physical arrival order.
  - **H-A: MSHR merge accounting.** Re-serves of still-in-flight sectors merge
    into outstanding MSHRs (free); only landed re-reads count. Narrow window,
    weaker than H-I.
  - **H-D: per-bank-group sector staging buffer** (fixed depth; window counted
    in sectors, not cycles).
  - Ruled out: dual-row SRAM write on bank match (12/12 no diff), bank
    swizzle (sequential `word%32` fits 400/400), dst-pattern interference
    (dst-invariance), hit/miss equivalence (disproven — they differ).
  - **Discriminating experiment (H-I/H-B):** p0 = {lane A early sector,
    lane B sector ~6 twfs late}, p1 = re-serve of A's bank+twf. If A's
    re-serve is free while p0 is gated on B → buffer/stream ride confirmed;
    if it counts → strict sequential completion (H-I/H-B dead).
  - **Experiment results (2026-08):**
    - Gate probe DONE: re-serve of an already-served early sector counts
      (conf=1) even when its pass is gated ~6 twfs late → H-I pipelined
      buffer-ride form DEAD; re-serve after consumption always costs.
    - Dual-row-write probe DONE: dst bank aligned vs shifted vs src bank:
      12/12 identical → no bank-match write merge.
    - Current best suppression rule: hit free iff the HIT LANE'S OWN sector
      is still in flight at its pass index (per-lane arrival, distinct-twf
      counting): corpus 20/25 + coal60 42/60 — still worse than the §4.3
      exemption rule (24/25 + 47/60); arrival order/rate model unphysical
      (rho≈16 fits best). Pass issue timing (gating feedback into pass
      cycles) is the missing ingredient for a causal model.
  - **Suppression deep-dive (2026-08-06, ~40 probes, NEGATIVE results):**
    - Delivery-timing model families all fit WORSE than the §4.3 exemption
      rule: twf-order delivery (23/25+11/60), pass-request-order delivery
      (20/25+37/60+d4 15/200), own-sector-in-flight (20/25+42/60),
      T-stage concurrency windows {i−1,i}/{i−1} (corpus 2/25 — artifact).
    - Delta-debugged minimal suppression case saved to
      `l1tex/mincase32.json` (9 lanes, R=4, TWf=3, Sectors=7; model
      predicts 4 hits, measured SharedConf=3 → exactly one free hit).
    - Attribution: the free hit is lane7 (bank4, twf0, hit@pass1, line12
      with tag-bank 3). Line-specific (line12 tb3 free, line11 tb1 /
      line8 tb2 same twf0 counted), sector-insensitive within line
      (sec48/sec49 both free), NOT first-touch-of-line (pre-touching
      line12 @p0 with same sector keeps it free), NOT same-word
      (same word as bank's first serve COUNTS), window = pass1 only
      (deferring the hit to pass2/3 makes it count).
    - HYPERSENSITIVE: removing ANY of the other 3 hit lanes makes all
      remaining hits count; an isolated single-hit replica (any bank,
      TWf 1..7, 2..16 sectors) ALWAYS counts. Suppression strength grows
      with pattern complexity (a 11-lane probe showed gap 4 = 4 free hits
      of 7). No local per-hit rule fits; consistent with a global
      queue/MSHR-occupancy effect depending on the whole fill stream.
    - Counter forensics: conflicts are `cmd_read` (write side clean),
      SecHit=0, TotalWf/ShAllWf invariant across variants (they include
      write wavefronts: TotalWf = ShAllWf + LgdsWf).
    - Also observed: a bank serving the same twf TWICE before a hit may
      charge 2 conflicts for that hit (S3 probe: 1 hit but conf=2) —
      per-serve-occurrence accounting, needs confirmation.
    - Status: miss-path suppression UNMODELED; exemption rule remains
      best-effort. Recommend: statistical correction term or bounded
      error on scattered patterns; hit-path (warm) formula R−#groups is
      exact and unaffected.
- **Write/read wavefront co-issue schedule** on scattered dst (4 B ±1
  residual; 8 B/16 B larger); data-arrival gating suspected, unproven.
- 16 B T-stage: 6/60 random cases off by ±1–3 (tag model small gap).
- `SharedWf` occasional −1 at 8 B/16 B dst=coal: sparse passes of adjacent
  groups may merge.
- Tag-bank hash validity for lines ≥ 128.
- Why LDG-allocated lines are invisible to LDGSTS lookups (fill-state or
  eviction-class difference); whether LDGSTS hits exist for mixed LDG→LDGSTS
  producer-consumer code (relevant for real kernels that LDG-warm then
  cp.async).
- cg/bypass true shared-bank behavior.
- `ShAllWf`/`TotalWf`/`LgdsWf` composition (≈SharedWf+const with anomalies);
  `Inst`=2 per single LDGSTS.
---

## 5. L1 + shared interaction — serialization, not bank conflict

`harness_lx2.cu`. Simultaneous vectorized global load (`LDG.E.128`) and
vectorized shared store (`STS.128`+`LDS.128`).

**Result:** no cross-source bank conflict on sm_120. Global and shared wavefronts
are **exactly additive** (serialized through the single L1TEX data stage, ~1
wavefront/cycle), and cycle counts are additive: G + S ≈ GS within 4 %. The
`ArbConflict` counter is tiny, iter-independent (cold-start fills), and does not
rise when shared is added. Shared bank-conflict counters depend **only** on the
shared access pattern — heavy-conflict shared reports identical `7,168,000`
conflicts with and without concurrent global traffic.

**Folklore source:** uncoalesced global loads incur their own L1 bank conflicts
(`GlobalConflictLd`), separate from the shared counter. This can be mistaken for a
"shared vs L1 interaction" but is purely a global-side phenomenon.
