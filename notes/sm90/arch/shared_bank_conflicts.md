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

## 4. cp.async / LDGSTS

`harness_cpasync.cu`. Bank-conflictable side is the **shared write** (dst
pattern). Sizes: 4 B (`LDGSTS.E`), 8 B (`LDGSTS.E.64`), 16 B (`LDGSTS.E.128`).

### 4.1 LSU partitioning — same as STS, but NO coalescing

| size | SASS | lane-group | floor |
|---:|---|---|:---:|
| 4 B | LDGSTS.E | whole warp | 1 |
| 8 B | LDGSTS.E.64 | half-warps {0-15}{16-31} | 2 |
| 16 B | LDGSTS.E.128 | quarter-warps {0-7}{8-15}{16-23}{24-31} | 4 |

**No same-word coalescing:** each lane is an independent copy descriptor. Multiple
lanes writing the same word counts as multiple distinct writes.

| pattern (16B) | cp.async Wf | STS Wf | why |
|---|---|:---:|:---:|---|
| broadcast | **32** | 4 | 32 independent writes, no coalesce |
| consecutive | 4 | 4 | distinct words, same cost |
| pairshare / quad / oct | 8/16/32 | 2 | ×(lanes sharing) |

### 4.2 Complete pipeline model

```
LSU partition  →  T-stage (tag array)  →  Fill (on miss)  →  Data-stage (data array)
  (warp groups)     (4 banks, 1/cycle)    (per 32 B sector)   (32 banks, 128 B/wf)
```

#### Step 1 — LSU partitioning

cp.async size determines lane-group boundaries (§4.1). No transaction coalescing.

#### Step 2 — T-stage (4-bank tag array)

Each LSU transaction's global addresses are decomposed into cache-line tags
(128 B line, 1 tag each). The 4-bank tag array resolves 1 lookup/bank/cycle. If
tags from different cache lines conflict in the 4-bank array, the LSU transaction
is **split into multiple TAG transactions** (one per non-conflicting tag batch).

| metric | formula |
|---|---|
| `TstageWf` | `= ceil(#cache_lines / 4)` |
| `TagConflict` | `= max(0, TstageWf − 1)` |

#### Step 3 — Fill (on miss)

If a tag lookup misses, an MSHR is allocated and the cache line is filled from L2
in 32 B sectors. Unaccessed sectors within a line may be skipped (consistent with
sector-granularity `Sectors` accounting).

The fill does **not** increase `SharedWf` over the shared-write-only cost. Whether
the fill is genuinely free (dual-row write broadcasting to L1+shared rows in the
same bank cycle), uses a separate write port, or has a cost invisible to the
shared counters is **not determined**. The key fact: `SharedWf` is unchanged by
the presence of a fill.

#### Step 4 — Data-stage (32-bank data array)

Each tag transaction enters the data stage. The hardware determines the data-array
bank-conflict profile of the combined **L1 read + shared write** for that tag
transaction. **L1-read bank conflicts are resolved FIRST** (verified: §4.3
split-order test). After the read split, shared-write conflicts are resolved
within each read-split group.

Each resulting **data transaction** performs one conflict-free 128 B pass (one
word to each of the 32 banks).

> `SharedWf = Σ(data_txs)` across all tag and LSU transactions.
> `SharedConflict = GlobalConflict = Σ(data_txs − 1)` (cp.async fuses counters).

#### Sector-overflow misalignment

If the source base address is not sector-aligned (512 B), the warp load may span
1 extra sector (17 instead of 16), forcing `TstageWf=2`. The 2nd T-wavefront
delivers the overflow sector → 1 extra shared write pass → `SharedWf += 1`.

| src base alignment | TstageWf | SharedWf |
|---|---|:---:|
| aligned (addr%512=0) | 1 | 4 |
| misaligned (addr%512=4) | 2 | 5 |

### 4.3 Data-transaction split order — L1-read FIRST (verified)

Test: 8-thread predicated 16 B cp.async, one tag transaction. L1 read has 3-way
conflict (threads {0,1,2} on bank 0); shared write has 3-way conflict (threads
{0,1,3} on bank 4). Overlap = {0,1}. Both sides conflicted, overlapping subsets.

Measured: **`SharedWf=3, SharedConflict=GlobalConflict=2`**.

- **L1-read-first:** 3-way read split → 3 data txs. Overlapping write conflict
  {0,1,3} lands in different read-split groups → no further splits. shW=3. ✓
- **Write-first:** would split writes → 4 groups (w=3 + rest); read conflict on
  thread 2 is fully resolved within `rest` → shW=4. ✗

**Conclusion:** the data stage resolves L1-read bank conflicts first, then shared
write conflicts within each read-split group.

### 4.4 Key formulas (16 B cp.async)

| quantity | formula | scope |
|---|---|---|
| `TstageWf` | `ceil(#cache_lines / 4)` | source side |
| `TagConflict` | `max(0, TstageWf−1)` | tag pipeline, additive to bank conflicts |
| `SharedWf` | `TstageWf × passes_per_T` | the actual shared-write wavefront cost |
| `SharedConflict` | `SharedWf − max(quarter_floor, TstageWf)` | **=** `GlobalConflict` (fused for cp.async) |

Where `passes_per_T` = number of data-array passes needed to write one T-wavefront's
data through the shared destination (depends on dst bank-conflict profile).

For ideal (coalesced src, conflict-free dst): `TstageWf=1, passes_per_T=4`
→ `SharedWf=4, SharedConflict=0`.

### 4.5 Source-stride sweep (16 B, conflict-free consecutive dst)

| src stride (bytes) | TstageWf | SharedWf | SharedConflict | TagConflict |
|---|---:|---:|:---:|:---:|:---:
| 16 (coalesced) | 1 | 4 | 0 | 0 |
| 32 | 2 | 8 | 4 | 1 |
| 64 | 4 | 16 | 12 | 3 |
| 128 (Zhihu k2) | 8 | 32 | 24 | 7 |
| 256 | 8 | 32 | 24 | 7 |

Relationships: `SharedConflict = GlobalConflict` (cp.async fusion) across all rows.
`SharedWf = TstageWf × 4` (conflict-free dst, quarter floor).

### 4.6 Worked examples — the two Zhihu kernels

Both kernels use 16 B `cp.async.ca` (`LDGSTS.E.LTC128B.128`).

#### Kernel 2 — scattered source, consecutive dst

| | value | breakdown |
|---|---|:---|
| Source | `d_ptr + tid*32` (stride 128 B) | 32 distinct cache lines |
| Dst | `smem + 4*tid` (consecutive) | conflict-free |
| TstageWf | 8 | 32 lines ÷ 4 tag banks |
| SharedWf | 32 | 8 × 4 quarter floor |
| SharedConflict | **24** | L1 read bank conflict: all lanes→banks {0,1,2,3}, each T-wavefront has 4 distinct words per bank → 3-way → 8×3=24 |
| TagConflict | **7** | TstageWf−1, additive |

**Root cause:** source stride is a multiple of 32 words → every lane maps to banks
{0,1,2,3} on the L1 read. Even though the shared destination never conflicts, the
L1 read bank conflicts are charged to `SharedConflict` (cp.async fusion).

#### Kernel 3 — coalesced source, scattered dst

| | value | breakdown |
|---|---|:---|
| Source | `d_ptr + tid*4` (coalesced) | 4 cache lines |
| Dst | `smem + 32*tid` (stride 128 B) | heavily conflicted |
| TstageWf | 1 | 4 lines ÷ 4 tag banks |
| SharedWf | 32 | 4 quarters × 8 writes/bank/quarter |
| SharedConflict | **28** | shared write bank conflict: all lanes→banks {0,1,2,3}, 8 writes/bank/quarter → 7-way per quarter × 4 = 28 |
| TagConflict | **0** | TstageWf=1 |

**Root cause:** destination stride is a multiple of 32 words → every lane writes
to banks {0,1,2,3} on the shared write. L1 read is conflict-free (coalesced
source), so `GlobalConflict=0` but `SharedConflict=28`.

#### Comparative penalties

| | SharedConflict | TagConflict | **total overhead** |
|---|---|:---:|:---:|:---:|
| kernel 2 | 24 | 7 | **31** |
| kernel 3 | 28 | 0 | **28** |

Kernel 2 has **more** total penalty despite fewer bank conflicts, because the 7
tag serializations more than offset the clean-dst advantage.

### 4.7 The `+tid*4` fix

Adding `+tid*4` (4-word offset) to either source or destination rotates the base
address by `(4t)%32 = 4t`, which within each quarter maps all 8 threads to 8
distinct banks (for each of the 4 k values). Across k=0..3, every bank receives
exactly 1 write per quarter → conflict-free.

- **kernel 2 + `tid*4` on source** (`k2fix`): `GlobalConflict=0` (L1 read banks spread), `TagConflict=8` (scattered sectors remain).
- **kernel 3 + reverse dst** (`smem + 4*(31−tid)` = `−4t` rotation): `SharedConflict=0, SharedWf=4`.
- **Predicated 8-thread variant** (both sides +4t): `GlobalConflict=0, SharedConflict=0`.

The root cause of both kernels' conflicts is **stride ≡ 0 (mod 32 words).**
Breaking that alignment with `+4t` distributes across all banks.

### 4.8 ca vs cg (bypass L1)

- `cp.async.ca` (default): all counters above; clean model.
- `cp.async.cg` (16 B only, bypass L1): standard counters read **0**; shared
  writes appear on `_cache_bypass` sub-counters where the bank-conflict counter
  is **0 for every tested pattern** and the wavefront sub-counter does not follow
  the group model. The bypass path stages global→L2→shared differently. **Open.**

### 4.9 Open questions

- cg/bypass true shared-bank behavior (counter granularity unclear).
- Exact crossbar swizzle set that permits the v2/v4 load merge (butterfly/Beneš
  topology).
- v4 cp.async (`LDGSTS.128`) full characterization (only 16 B covered here).

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
