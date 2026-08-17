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

**Width generalization update (2026-08-15).** Structured 8 B/16 B sweeps keep
the fixed per-half/per-quarter-warp write formation described below; allowing
the 4 B dynamic repacker to cross those visible group formations overcounts
them by 1--4 wavefronts.  For scattered traffic, however, the keeper/rank
dynamic schedule is materially better at 8 B.  At 16 B the static formation
remains a lower bound and the schedule saturates at one wavefront per active
lane.  The resulting hybrid scores 24/60 scattered 8 B and 32/60 scattered
16 B (previous code in the current checkout: 5/60 and 25/60), while retaining
all 24 structured `regress816` cases.  This is a predictive improvement, not
yet a closed mechanism: the remaining residuals require group-local
keeper-eviction/repacking probes.

For 4 B, a gate audit corrected an earlier reporting error: the underlying
dynamic v68 candidate was 47/47 on `probe_all`, but v73's broad structured
fallback made the final model 39/47.  The refined boundary keeps the original
low-delta rule for full warps with 32 unique source addresses, and also admits
repeated-source rows only when one address sequence is low-delta (at most four
distinct adjacent deltas) while the other is genuinely scattered (more than
four).  The eight affected probe families have only 2--3 source-delta classes;
the recovered bulk rows have 24--31.  This restores 209/400 while retaining
40/40 canonical probes, the real 47/47 family gate, and 64/64 regress.

Live `probe_bulk --size` checks also reject treating T-stage serialization as
an additive wide-access correction.  At the same TWf, both signs occur: 8 B
TWf=9 includes residuals +3 and -2; 16 B TWf=10 includes +5 and -2.  Low TWf
does not remove the ambiguity (8 B TWf=2 reaches +4, 16 B TWf=3 reaches -2).
Running the dynamic scheduler independently per half/quarter and summing gives
27/60 at 8 B but only 18/60 at 16 B, versus the promoted hybrid's 24/60 and
32/60.  Thus the missing rule is not simple group serialization: formation is
group-local, while keeper eviction/drain/repacking must share some cross-group
state.  No dataset-only selector from this experiment is promoted.

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

**Hit path (CORRECTED 2026-08-13, clean measurement):** `SharedWf` on an
L1 hit is **identical to the cold miss path — 400/400 on data4 (4 B),
60/60 (8 B), 60/60 (16 B)**, measured with warm=1 (LDG preheat), which
pollutes zero `op_ldgsts` counters, and confirmed with zero L2 refetch
(`m_xbar2l1tex` sectors = 0 for the hitting cp.async). The write side is
NOT absorbed into read wavefronts; the full write schedule runs exactly as
on a miss. Since the hit path involves no L2 traffic at all, the extra
write wavefronts beyond `max(R, W_schedule)` **cannot** be latency/return
driven — the data-stage formation is a **pure structural function of
(goff, soff, size, mask)**, reopening the exact-rule search (the clean
warm=1 hit path is the ideal testbed: no arrival timing confounds).

The earlier "hit-exec SharedWf = R, 400/400" claim was a **subtraction
artifact**: warm=2 runs contain two cp.asyncs, and
`warm2_total − cold == R` (400/400) is arithmetically identical to
`preheat_only == R` — verified directly with the new cg=3 preheat-only
mode (400/400). The preheat takes R wavefronts simply because its dst is
the conflict-free scratch (W=1 → `max(R, 1) = R`). Both decompositions
imply the main-on-hit equals cold. warm=4 (cp.async fill + LDG touch
before the main cp.async) behaves exactly like warm=2 (400/400) — no
fill-provenance line state. cp.async never reads the lgds data banks:
`LgdsWf` contribution of a cp.async is 1 on miss AND on hit (400/400);
data movement is counted only as `mem_shared` wavefronts.

**Hit-path conflicts are NOT `R − #groups`** (clean warm=1: 41/400 at
4 B, 4/60 at 8 B, 1/60 at 16 B) and not cold either (99/400 equal at 4 B,
mostly cold + 0..+5 — consistent with miss-path suppression making cold
smaller); also ≠ unsuppressed read_conf + write_conf (75/400). Hit-path
conflict accounting is UNMODELED.

**Extra-ride rule — progress on the clean testbed (2026-08-13, ~200
synthetic probes, `ride_probe.py` + `ride_grid.json`).** With L2 timing
removed (warm=1), the base schedule is `SharedWf = R + W − 1` (one write
pass overlaps per group); extra rides beyond that are gated:

- **Ride-gate grid** (R=2 canvas: lane31 re-reads word k of lane k;
  single write-bank conflict pair (a→b); 182-pattern sweep): the spilled
  write lane rides the next wavefront IFF the write conflict does NOT
  involve lane k (the "read-conflict keeper" whose read bank is re-served
  in the later read pass). Consistent with a **keeper-write replay**: at
  a re-serve wavefront, the keeper lane's write bank is re-occupied, and
  pending writes colliding with it are deferred.
- **E-series (class-A/class-B timing)**: a write pass containing a lane
  read at cycle c tends to issue at c (riding its own read wavefront),
  but if that lane's write bank was written at c−1 (WAW-1) the write is
  deferred (E2 vs E3 discriminator). Spilled 1-lane passes with mr=0 ride
  freely into later wavefronts whose write-set (+ keeper replays) leaves
  their bank free; multiple disjoint spill passes can share one wavefront
  (E8). Skip-ahead issue happens (wr1 before wr0 when wr0 isn't ready).
- A consolidated simulator (static write passes; class-A at c=mr with
  fresh-bank gate variants; class-B FIFO-skip with keeper-replay bank
  occupancy) reaches only ~98/400 — the rule is **not closed**. Simple
  cycle-packing variants all lose to the current model (196/400), which
  stays in model.py unchanged. The puzzle is now known to be structural
  and timing-free; the remaining degrees of freedom are the exact
  class-A deferral conditions and how keeper replays interact with
  multi-conflict read formations on random patterns.

**Write-schedule model v68 (2026-08-14 pm — supersedes the static-wave
line v11/v22/v36/v49 for the warm=1 testbed).** Verified ground truth:
40/40 canonical probes (`test_dyn.py`), 47/47 probe families
(`probe_all.py`), 51/52 ride families R/T/U/V/W/X/Y/Z/AA
(`ride_probe2*.py`, only Z3 off by one), 130/400 on
`data4_ldgsts_warmldg.jsonl` (v49 static: 112/400; old `model.py`
196/400 remains the bulk leader but is probe-invalid). The model
(`simulate_v68` in `sched_sim.py`):

- **Rank structure**: per (lane group, global address), occurrences
  sorted by (read cycle, lane): first = rank0 (keeper), rest rank≥1.
- **First passes**: rank0 lanes write in a greedy bank-conflict-free
  pass at cycle = their read-batch index `rc` (from the verified read
  formation). Confirmed: read batches do NOT split across lines
  (W1: 2 lines, 1 batch, 1 write wavefront; K1: 32 lines, 1 wavefront).
- **Same-word WAW (corrected 2026-08-15)**: same-word and different-word
  same-bank collisions have the same scheduling result: keep the earlier
  packed lane and defer the later lane. AC transformations of idx54/42/205
  preserved write banks while changing WAW count from zero through complete
  per-bank collapse; SharedWf and SharedConf were invariant. The earlier
  "later wins / evict earlier" rule was a simulator overconstraint and was
  exactly the source of idx205's 19-vs-18 error.
- **Deferred rank0 pool**: losers drain greedily from cycle
  `R0 = max rank0 rc + 1` — they do NOT merge into later first-pass
  cycles (Z0: 9-lane pass + 8 replays, batch1 16 lanes → 10, not 2).
  But replay drains DO merge across batches once the pool opens
  (W4: four 8-lane single-bank batches → 11, not 32).
- **Rank≥1 lanes** (data buffered from the keeper's read; no re-read of
  the data array): eligible on ANY cycle ≥ max(arrival, keeper written
  + 1), including cycles before R0 (H6c) — arrival = rc, or rc+1 when
  the H-Y floor fires (lane doesn't write its keeper's bank AND some
  rank0 non-keeper lane writes its bank: R0/R9/R10).
- **Keeper-bank gate**: a rank≥1 lane may not share a wavefront with a
  lane writing its keeper's bank (symmetric eviction + re-pack
  fixpoint). G chains, N1/N4/N11, Y3/Y4.
- **Same-global-address exclusion**: rank≥1 lanes of one address write
  in distinct cycles (E6, F4).
- **RB port rule (AB5 refinement, 2026-08-15)**: at a re-read cycle c>0,
  candidates whose write bank ∈ RB[c] are blocked unless the bank is the
  lane's own read bank (flow-through). For rank0 the nonself block is
  unconditional: AB5 uses a clean batch0 and cross-writes fresh words, so it
  has neither a pending deferral nor WAW, yet measures SharedWf=3 and
  SharedConf=1 (v68-before-AB5 predicted 2). The no-pending exemption remains
  only for rank≥1 (X1/W5/Z2/R11). This preserves 40/40 and raises clean 4B
  bulk from 127/400 to 130/400.

Rejected this round: blanket batch-member RB block (v66, 133/400 but 8
ride families fail by +1), blanket self-exemption (v67, 110/400),
any-pending gate (v71, 125/400), early deferral eligibility (v65,
78/400), pure per-batch serial sum (matches idx54=8 but W4=32 ≠ 11),
sector-bandwidth return gating (K1: 32 sectors, SharedWf=1).

**v73 closure of the three directional ±1 cases (2026-08-15).** AC/AD/AE
probes (`ride_probe31.py`..`ride_probe33.py`) add per-word WAW transforms,
same-bank multiword cases, tag/rank transforms, lane deletion, and active-lane
density sweeps. The resulting additions are:

- Cross-TWF rank0 ordering: a nonself rank0 write cannot pass an older
  deferred write on its bank during the first-pass phase. Compare a baseline
  schedule with the fully ordered schedule; at most one otherwise
  unabsorbable bubble is visible. This closes idx54 7→8 and idx42 12→13.
  TWf=1 has no cross-wave ordering penalty; changing only idx205's source
  tags to TWf=9 supplies the positive discriminator.
- Same-word eviction is removed, closing idx205 19→18. Its SharedWf/SConf
  stay 18/15 for fresh words, original WAWs, and per-bank all-same-word.
- Full-warp sparse-bank requests (≤18 destination banks) retain the measured
  static formation upper bound when it exceeds the dynamic schedule. Partial
  warps always use dynamic scheduling (AE: 13..20 active lanes). Regular
  affine/low-delta full-warp sweeps retain the established static path.

The promoted 4-B model is 40/40 canonical probes, 47/47 families, 64/64
regress, regress816 ALL OK, and 209/400 clean-hit bulk (old static 196/400,
v68-after-AB5 130/400). idx54/42/205 now predict and measure 8/13/18.

The old idx54 return-path lead is
resolved: across all 400 rows, `warmldg.LgdsWf = cold_LDG.LgdsWf + 1`
exactly; 13 is the LDG preheat's miss-path counter plus the constant LDGSTS
contribution, not a cp.async return-arrival clock. Arrival=return-cycle v68
is therefore rejected. LDG miss-path LgdsReadWf formation remains a separate
secondary problem. Z3 (26 vs 25) is still off by one.

**warm=1 caveat (2026-08-13):** the LDG preheat was silently
compiler-eliminated until this date (`v` was dead after `sa += (v & 0)`;
nvcc dropped the whole block — verify SASS!). Fixed by storing the
preheat result to a shared scratch slot (`smem[2048 + t]`), which also
forces completion before the main access issues. All pre-2026-08-13
warm=1 results are void. LDG-allocated lines ARE visible to both LDG and
LDGSTS lookups (SecHit = Sectors, SecMiss = 0, 400/400); the old
"invisible lines" observation was this artifact. The preheat is
size-matched (v2/v4 for 8 B/16 B) so all touched sectors are warm.

**LDG (plain global loads) vs LDGSTS — circuit reuse (2026-08-13):**
same patterns, same warp, cg=2 LDG mode in probe.cu:
- **T-stage fully shared**: TReq/TSetAcc/TagConf/TWf/Sectors identical to
  the LDGSTS model and to LDGSTS hardware counters — 400/400 cold and
  hit (4 B), 60/60 (8 B/16 B).
- **LDG hit data path**: `LgdsReadWf = R` **with same-address broadcast
  merge** (lanes reading the identical word ride free in the same pass;
  per-group greedy bank arbitration otherwise) — exact 400/400 (4 B),
  60/60 (8 B), 60/60 (16 B). SecHit = Sectors, SecMiss = 0.
- **LDG miss data path**: `LgdsReadWf ≠ R` (mostly > R, ≈ TWf + extras)
  — UNMODELED, but perfectly reproducible across runs (deterministic).
- Unlike LDGSTS, plain LDG hits DO read the L1 data banks with the
  bank-arbitrated read formation; LDGSTS hit/miss data movement goes
  straight into shared-mem wavefronts (write-schedule driven).

**Cold path — co-issue/absorption on scattered dst (2026-08-13).** Cold
`SharedWf = R + W_eff − rides`, `rides ≈ #groups`, where the effective
write wavefronts `W_eff` are *fewer* than the lane-greedy W on scattered
dst (hardware absorbs extra writes). Findings from ~30 dedicated probes:

- **Window (truncation) probes V1/V2** (fixed W=2, one 1-lane extra,
  read phase swept R=1..13, extra eligible from c0 or c3): the extra
  **never rides** at any window length ⇒ the simple FIFO co-issue model
  (ride at first eligible cycle) is dead.
- **P2 anomaly** (R=2, 2-lane extra whose lane set and banks *exactly
  equal* the last read pass): the extra DOES ride (SWf=2=R). T2/T3
  variants (same extra, read passes larger so no exact match) do not.
- **idx1 prefix sweep** (pre0..pre11, W verified per-prefix via
  coalesced-src runs): extra absorption ext = 0,0,0,0,1,0,0,1,2,3,3,4 for
  R = 1..12 — grows roughly with R, and cases exist (pre4 vs pre9 w2)
  where *identical* local eligibility (same mr, same banks, one full read
  pass after) rides in one pattern and not the other.
- **Hit==cold wavefront identity (2026-08-13, see "Hit path" above)
  REFUTES the latency-gating interpretation**: the warm=1 hit path has no
  L2 traffic yet produces byte-identical `SharedWf` (400/400). The
  absorption extras must therefore be a structural function of the
  pattern (queue/position effects, not sector-return timing). The
  pre4/pre9 contradiction needs a structural explanation after all.
- On data4 the over-absorption beyond `R + W − #groups` is 0 on 192/400,
  1 on 134/400, 2 on 40/400, ≥3 on 34/400, with average growing ~linearly
  in R — consistent with a latency effect, not fittable by any f(R) table
  (per-R mode table overfits: 208/400 but modes are noise).

Accuracy status: 4 B regress 64/64, dst sweeps exact at 8 B/16 B; dst=coal
random 60/60 at all sizes; random scattered dst: 4 B 196/400 (FIFO K=1
ride model retained as best-effort; null model `R+W−#groups` = 192/400),
8 B 15/60, 16 B 25/60 with bounded error. Exact SharedWf on scattered dst
is now known to be a **structural** (timing-free) function — hit==cold
identity (2026-08-13) — but the rule is not yet found; the warm=1 hit
path is the clean testbed.

**Deferred-age discriminator update (2026-08-15).**  AF
(`ride_probe34.py`) first showed that keeper admission/eviction is local to
the architectural half/quarter: remote keeper-destination swaps leave
hardware unchanged.  AG (`ride_probe35.py`) then shifted complete 128-byte
source lines while preserving equality/keeper/write topology; idx12/idx20
were invariant across changing TWf/TagConf, rejecting a T-arrival FIFO.

AH (`ride_probe36.py`) changes the write-side topology directly.  Its paired
cases exchange destinations of cross-group non-keepers, while assertions hold
source equality classes, keeper identity, every keeper destination-bank edge,
and the complete destination-bank multiset fixed.  Hardware changes at 8 B
(idx9 26->24, idx26 21->26, idx22 20->19, idx47 11->12) and at 16 B (two
idx54 swaps, both 23->24), despite identical TWf/TagConf.  Thus shared drain
and repack depend on destination-bank ownership/age derived from group-local
equality/keeper topology, not tag arrival order.

`simulate_v68` now provides explicit deferred-age/repack state: first-deferral
age persists for RB/bank losers, packing losers and evicted equality
followers, and older cohorts are visited first during repack.  `model.py`
enables it for scattered 8 B/16 B.  This first version does not improve the
aggregate wide fit, so the narrow shared-drain correction remains.  Current
scores are 4 B 209/400, 8 B 25/60, 16 B 33/60; `test_dyn` is 40/40,
`probe_all` 47/47, `regress` 64/64, and `regress816` all green.

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
  are not counted. (The old "hit path counts everything (`R − #groups`)"
  claim was a warm=2 subtraction artifact — corrected 2026-08-13, §4.4;
  hit-path conflicts are unmodeled but larger than miss-path on average,
  consistent with suppression being a miss-only effect.) Dominant error
  source on random patterns.
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
      error on scattered patterns. NOTE (2026-08-13): the old "hit path
      counts everything (R−#groups)" claim was a warm=2 subtraction
      artifact — clean warm=1 hit-path SharedConf is unmodeled too
      (§4.4), though ≥ cold in ~75% of cases (consistent with miss-path
      suppression).
- **Write/read wavefront co-issue schedule** on scattered dst (4 B ±1
  residual; 8 B/16 B larger); data-arrival gating suspected, unproven.
- 16 B T-stage: 6/60 random cases off by ±1–3 (tag model small gap).
- `SharedWf` occasional −1 at 8 B/16 B dst=coal: sparse passes of adjacent
  groups may merge.
- Tag-bank hash validity for lines ≥ 128.
- ~~Why LDG-allocated lines are invisible to LDGSTS lookups~~ **RESOLVED
  (2026-08-13)**: they were never invisible — the warm=1 LDG preheat was
  compiler-eliminated (dead `v`), so no warming ever happened. Fixed
  probe shows LDG-allocated lines hit fine for both LDG and LDGSTS
  (SecHit = Sectors, zero L2 refetch). Lesson: always verify preheat
  instructions survive in SASS.
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
