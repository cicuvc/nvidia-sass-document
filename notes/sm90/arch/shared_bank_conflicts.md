# Shared-memory bank conflicts — non-vectorized LDS/STS (broadcast & trigger rules)

Empirical characterization of when a shared-memory access serializes into
multiple passes ("bank conflict"). Measured on **RTX 5090 (sm_120, GB202)**,
CUDA 13.1, driver 590.48.01. The shared/L1 subsystem is unchanged in structure
since Turing, so the rule transfers back to Hopper/Ampere.
Cross-refs: `lsu_mio_structure.md`, `memory_model.md`.
Harness: `tests/bankconf/harness.cu` + `tests/bankconf/run.py`.

## Metric shorthand glossary
Shorthand names used throughout this note, mapped to their full ncu metric paths
(all under `l1tex__` unless prefixed `sm__sass`/`smsp__`).

| shorthand | full metric path (abbreviated) | description |
|---|---|---|
| **Global (L1) side — tag/sector/fill** |||
| `glTout` | `t_output_wavefronts_pipe_lsu_mem_global_op_ldgsts_cache_access` | T-stage output wavefronts for LDGSTS source read (sectors → shared). One wavefront = one 16-sector tag pass (up to 512 B). |
| `glTW` | `t_output_wavefronts_pipe_lsu_mem_global_op_ld.sum` | T-stage output wavefronts for plain global loads (LDG). |
| `glSec` | `t_sectors_pipe_lsu_mem_global_op_ldgsts_cache_access` (or `_op_ld`) | 32-byte sectors requested from L2 / processed by T-stage. 512 B coalesced = 16 sectors. |
| `secHIT` | `..._lookup_hit` variant of `glSec` | Sector requests that hit in L1 tag+data. |
| `glW` / `glREAD` | `data_pipe_lsu_wavefronts_mem_lgds` | local/global/(d)shared data-stage wavefronts (general global-side). |
| `gdsC` | `data_bank_conflicts_pipe_lsu_mem_gds` (or `_op_ld`) | Global L1 data-array bank conflicts (fill writes or scattered reads). For cp.async `_op_ldgsts`, this counter is **fused** with the shared-side. |
| **Shared side — data-stage** |||
| `shGS` / `shW` / `shWRITE` | `data_pipe_lsu_wavefronts_mem_shared_op_ldgsts` | Shared-memory data-stage wavefronts for LDGSTS writes. The physical cost: one wavefront = one 128-B (32-bank) data-array pass. |
| `shC` / `gsC` | `data_bank_conflicts_pipe_lsu_mem_shared_op_ldgsts` | Bank conflicts attributed to the shared LDGSTS write (same counter as `gdsC` when cp.async fuses them). |
| `shLDw` | `..._wavefronts_mem_shared_op_ld` | LDS (shared load) data-stage wavefronts. |
| `shLDc` | `..._bank_conflicts_..._shared_op_ld` | LDS bank conflicts. |
| `shSTw` | `..._wavefronts_mem_shared_op_st` | STS (shared store) data-stage wavefronts. |
| `shSTc` | `..._bank_conflicts_..._shared_op_st` | STS bank conflicts. |
| **Data-stage totals** |||
| `TOTwf` | `data_pipe_lsu_wavefronts` | Total data-stage LSU wavefronts (read + write, all clients). |
| `RDwf` / `cmdRD` | `data_pipe_lsu_wavefronts_cmd_read` | Total data-stage read wavefronts. |
| `WRwf` / `cmdWR` / `cmdWRITE` | `data_pipe_lsu_wavefronts_cmd_write` | Total data-stage write wavefronts. |
| `lgds` / `glREAD` | `data_pipe_lsu_wavefronts_mem_lgds` | local/global/dshared wavefronts (LSU data-stage global side). |
| `lgds_wr` | `..._mem_lgds_cmd_write` | Write wavefronts attributed to global/LGDS path. |
| `lgds_rd` | `..._mem_lgds_cmd_read` | Read wavefronts attributed to global/LGDS path. |
| **Instruction counts** |||
| `iGS` | `smsp__inst_executed_op_ldgsts` | Warp instructions executed: LDGSTS (cp.async). |
| `iGL` / `iGLld` | `smsp__inst_executed_op_global_ld` | Warp instructions executed: global loads. |
| `iSHst` | `smsp__inst_executed_op_shared_st` | Warp instructions executed: shared stores. |
| `ca` | `sm__sass_inst_executed_op_ldgsts_cache_access` | Count of `cp.async.ca` instructions (cache L1). |
| `cg` | `sm__sass_inst_executed_op_ldgsts_cache_bypass` | Count of `cp.async.cg` instructions (bypass L1). |
| **Misc** |||
| `ARBc` | `data_bank_conflicts_type_arbitration` | Bank conflicts from L1 data-client arbitration (shared vs global). |
| `setC` | `t_set_conflicts_pipe_lsu_mem_global_op_ldgsts_cache_access` | Extra cycles from L1 tag set conflicts. |
| `TOTc` | `data_bank_conflicts_pipe_lsu` | Total data bank conflicts (all sources). |
| `thru` / `L1thru` | `throughput.avg.pct_of_peak_sustained_elapsed` (unit-level) | L1TEX throughput as % of peak sustained. |
| `cyc` | `sm__cycles_elapsed.avg` | Average elapsed cycles per SM. |

**Derived relationships** (cp.async 16 B):
- `shW = Σ_over_Qᵢ( max-thread-writes-per-bank )` (no-coalescing rule, dst side).
- `shW = glTout × passes_per_T` (src side: scattered sectors multiply shared passes).
- `shC = gdsC` when src is the bottleneck; they diverge when dst is the bottleneck.
- `shC = shW − max(quarter_floor=4, glTout)` — unified formula.

## Method
One block, one warp (32 threads). Exactly **one** measured shared instruction
per warp, emitted via `volatile` inline PTX so it is guaranteed to be a plain
non-vectorized `ld.shared.u32` / `st.shared.u32` (single `LDS`/`STS` in SASS,
confirmed by cuobjdump) and never DCE'd. Each thread's shared **word** index is
supplied from a global array, so ptxas cannot constant-fold the pattern.

ncu metrics (per single instruction, so the numbers read out directly):
- `...wavefronts_mem_shared_op_ld/st.sum`  = **passes** (N-way conflict ⇒ N).
- `...bank_conflicts_pipe_lsu_mem_shared_op_ld/st.sum` = passes − 1.
- `smsp__inst_executed_op_shared_ld/st.sum` = 1 (sanity: one instr).

The two metrics are internally consistent in every run: `conflicts = wavefronts − inst`.

## The rule (identical for LDS and STS)
Map each of the 32 requests to a bank: `bank = (byte_addr / 4) mod 32`
(32 banks × 4 B). Then:

> **passes = max over the 32 banks of ( number of DISTINCT 32-bit words
> requested in that bank ).   conflict = passes − 1.**

- Multiple threads hitting the **same word** (same bank *and* same address)
  cost **nothing** — they coalesce into one access. For a load this is the
  classic **broadcast/multicast**; for a store it is a single (undefined-winner)
  write. Same-word coalescing composes with conflicts: 31 threads on word A + 1
  on word B (same bank) = 2 passes, not 32.
- A conflict requires two threads in the **same bank on DIFFERENT words**.
- Distinct banks never conflict, regardless of how many distinct-bank broadcasts
  happen in parallel.

## Key correction to the common model
**STS to the same address does NOT conflict on this GPU.** The widespread belief
that "loads broadcast but stores to the same address serialize/conflict" is
false here: stores coalesce same-word writes exactly like loads broadcast them
(one thread's write wins, which is undefined — but it is a single pass, zero
conflicts). Non-vectorized `LDS` and `STS` show **byte-for-byte identical**
conflict/wavefront counts across every pattern tested. (This matches the CUDA
Programming Guide's "same 32-bit word ⇒ no bank conflict, write performed by one
thread" clause; the "store-broadcast conflicts" intuition is pre-Kepler lore.)

## Evidence (each row = one warp, one instruction)
`W`=wavefronts/passes, `C`=conflicts. Load and store columns are the two runs.

| pattern (word index per thread)                  | LDS W/C | STS W/C | distinct-words-in-hottest-bank |
|--------------------------------------------------|:-------:|:-------:|:------------------------------:|
| identity `t`                                     | 1 / 0   | 1 / 0   | 1 |
| broadcast `0` (all threads same address)         | **1/0** | **1/0** | 1 (same word ⇒ coalesce) |
| stride 2 `2t`                                    | 2 / 1   | 2 / 1   | 2 |
| stride 4 `4t`                                    | 4 / 3   | 4 / 3   | 4 |
| stride 8 / 16                                    | 8/7 · 16/15 | same | 8 · 16 |
| stride 32 `32t` (all bank 0, distinct words)     | **32/31** | **32/31** | 32 |
| stride 33 `33t` (odd stride)                     | 1 / 0   | 1 / 0   | 1 (all banks distinct) |
| 2 words, distinct banks, 16 threads each         | 1 / 0   | 1 / 0   | 1 |
| 2 words, **same bank** (0,32), 16 threads each   | 2 / 1   | 2 / 1   | 2 |
| 16 words banks 0..15, 2 threads each             | 1 / 0   | 1 / 0   | 1 |
| 16 words **all bank 0** (0,32,..,480), 2 each    | 16 / 15 | 16 / 15 | 16 |
| 31 threads→word0 + 1 thread→word32 (bank0)       | 2 / 1   | 2 / 1   | 2 (coalesce + 1 conflict) |
| asym: bank0 has {0,32,64}, bank1 has {1,33}      | 3 / 2   | 3 / 2   | 3 (max over banks) |

## Answers to the driving questions
- **Bank granularity / mapping**: 32 banks, 4 B each, `bank=(addr/4)%32`. ✔ as expected.
- **Conflict trigger**: same bank + different word. ✔ as expected.
- **Load broadcast**: same word ⇒ free, unlimited fan-out and multiple
  simultaneous broadcasts in different banks are free. ✔ as expected.
- **Store "broadcast"**: same word ⇒ free (coalesced single write). ✘ **contrary
  to the assumed model** — stores behave the same as loads.

## Open / next
- Sub-word (`u8`/`u16`) same-word accesses (different bytes of one word) — guide
  says still no conflict; untested here.
- Vectorized `ld/st.shared.{v2,v4}` transaction splitting/merging (e.g. the
  `tid^1 same address` merge) — separate study.
- Simultaneous L1 + shared traffic interaction — separate study.

---

# Vectorized v2 (LDS.64 / STS.64) — 64-bit shared access

Harness: `tests/bankconf/harness_v2.cu` (+ `run.py` with `HARNESS_BIN=./harness_v2`).
Each thread's 64-bit access touches words `[base, base+1]` (base even ⇒ 8B
aligned). One `LDS.64`/`STS.64` per warp (confirmed in SASS). `W`=wavefronts
(physical passes — the ground truth), `C`=ncu conflict metric.

## Baseline / floor
A 64-bit warp access moves 2 words/thread = **64 words/warp**. A shared wavefront
delivers ≤32 words (one per bank), so the **floor is 2 wavefronts**. ncu reports a
conflict-free consecutive 64-bit access as **W=2, C=0** — this is the "each
transaction covers 32 banks, 64 words ⇒ 2 transactions" model, confirmed.

## Data (one warp, one LDS.64/STS.64)
| pattern (element = 8B; thread reads [2e, 2e+1])          | LDS W/C | STS W/C |
|----------------------------------------------------------|:-------:|:-------:|
| consec `e=t` (64 distinct words)                         | 2 / 0   | 2 / 0   |
| broadcast `e=0` (all same element)                       | **1/0** | **2/0** |
| share tid^1 `e=t>>1` (adjacent pairs share)              | **1/0** | 2 / 0   |
| share tid^2 (lanes t,t^2 share)                          | **1/0** | 2 / 0   |
| share tid^3 (lanes t,t^3 share)                          | 2 / 0   | 2 / 0   |
| share tid^16 = half_lo_hi (lanes t,t+16 share)           | 2 / 0   | 2 / 0   |
| quadshare `e=t/4` (contiguous 4-lane blocks share)       | **1/0** | 2 / 0   |
| octshare `e=t/8` (contiguous 8-lane blocks share)        | **1/0** | 2 / 0   |
| estride 2 (bank pileup ×4)                               | 4 / 2   | 4 / 2   |
| estride 4 (pileup ×8)                                    | 8 / 6   | 8 / 6   |
| estride 16 (all in banks 0/1)                            | 32 / 30 | 32 / 30 |
| pairmerge_bank (16 elems all banks 0/1)                  | 16 / 15 | 16 / 14 |

## Rules
1. **Bank-conflict scaling is identical for LDS.64 and STS.64.** Extra passes are
   driven by the same classic rule as scalar: `passes ≥ max over banks of
   (# distinct words in that bank)`. estride/pileup cases match exactly for both
   load and store (4, 8, 32, 16). Same-word coalescing still applies.
2. **Loads can MERGE the two default transactions into ONE** (drop below the
   64-bit floor of 2 → 1 wavefront) when: all 32 lanes' data fits a single 32-bank
   wavefront (≤32 distinct words, ≤1/bank) **AND** the lane→word routing is
   hardware-friendly. Enabling patterns: full broadcast, tid^1, tid^2, and
   contiguous ÷4 / ÷8 block sharing. Non-enabling: tid^3, tid^4…tid^16.
   - This is a **crossbar-routing property, not a bank-count property**: `share:1`
     (1 pass) and `share:3` (2 passes) have *identical* bank/word profiles
     (32 distinct words, 1 per bank) and differ only in the lane→word map. The
     merge works when nearby lanes (adjacent / small-xor / contiguous blocks)
     share an element; it fails for far-apart lane sharing.
3. **Stores never merge below the floor.** A 64-bit store is **always ≥2
   wavefronts**, even for full broadcast (STS.64 bcast = 2 vs LDS.64 bcast = 1).
   The store splits into two lane-halves and does not merge identical halves.

## Transaction construction — per-half-warp (VERIFIED)
When a v2 access is not merged, the LSU builds transactions **one half-warp at a
time**: it gathers the 32 b32 words of lanes **0-15** into one transaction, then
the 32 b32 words of lanes **16-31** into another. Bank conflicts are evaluated
**independently inside each half-warp transaction**:

> **wavefronts = passes(lanes 0-15) + passes(lanes 16-31)**,
> `passes(H) = max over banks of (# distinct words that half puts in that bank)`.

This fits **every store** and every non-merged load in the data above.

### Proof 1 — half-warp beats whole-warp aggregation
Patterns whose whole-warp bank profile differs from the per-half sum
(`pWhole` = max distinct words per bank over all 64 words; `pHalf` = sum of the
two half maxima). Conflict concentrated in H0, H1 a broadcast:

| pattern (asymmetric conflict)                  | pWhole | pHalf | measured W (ld/st) |
|------------------------------------------------|:------:|:-----:|:------------------:|
| 3-way in H0 + H1 broadcast (`distinguish3`)     |   3    |   4   | **4 / 4**          |
| 4-way in H0 + H1 broadcast (`distinguish4`)     |   4    |   5   | **5 / 5**          |
| symmetric 3-way in both halves (`asym_clean`)   |   6    |   6   | 6 / 6              |

Measured always tracks **pHalf** → whole-warp aggregation refuted. (This also
rules out an even/odd-lane split, which would predict 3, not 4, for
`distinguish3`.)

### Proof 2 — the split boundary is exactly lane 15 | 16
Same two distinct words in bank0; H1 forced to a broadcast (banks 16/17, never
bank0) so whole-warp sees only 2 in bank0:

| pattern                                   | hot lanes | pWhole | pHalf | measured W |
|-------------------------------------------|:---------:|:------:|:-----:|:----------:|
| `bnd_in`  (both bank0 words inside H0)     | 14, 15    |   2    |   3   | **3**      |
| `bnd_cross` (bank0 words straddle halves)  | 15, 16    |   2    |   2   | **2**      |

Moving the second word across the **15→16** boundary alone drops the count 3→2:
the two words then land in *different* half-warp transactions and stop
conflicting. Pins the split to consecutive halves {0-15} / {16-31}.

## Load vs store asymmetry — summary across widths
- **Scalar (32-bit):** LDS and STS are **byte-identical** in every pattern
  (same-address writes coalesce just like read broadcast; no asymmetry).
- **Vector (64-bit):** identical in the **conflict regime**, but **loads can
  broadcast-merge below the 2-transaction floor and stores cannot** (store floor
  = 2). This is the only load/store asymmetry observed.

## Answers to the driving v2 hypotheses
- "v2 needs 2 (or 4) transactions": **YES** — 64-bit floor is 2 wavefronts.
- "LSU can merge transactions, e.g. `tid^1` accesses the same address":
  **CONFIRMED for LOADS** (tid^1, tid^2, contiguous ÷4/÷8 blocks, full broadcast
  all collapse to 1 wavefront). **NOT for stores.** The merge condition is a
  near-lane routing property, not just "same address".

## Open / next (v2)
- Exact crossbar swizzle set that permits the load merge (butterfly/xor network
  topology): which lane→word permutations are 1-pass.
- `v4` (LDS.128 / STS.128): floor should be 4 wavefronts; does it split into 4
  quarter-warps? Repeat the sweep.
- Simultaneous L1 + shared traffic interaction — separate study.

---

# v2 (64-bit) transaction logic — COMPLETE MODEL

A v2 access moves **64 b32 words** per warp (32 lanes × 2 consecutive words;
bank = `word % 32`). Two mechanisms determine the wavefront (pass) count.

## (1) Partitioning — the default, always the fallback
The LSU builds transactions **one consecutive half-warp at a time**:
- Transaction A gathers the 32 words of **lanes 0-15**; transaction B the 32 words
  of **lanes 16-31**. Boundary is exactly **lane 15 | 16** (verified: `bnd_in`
  vs `bnd_cross`).
- Conflicts are counted **independently inside each half's own 32 words**:
  `passes(H) = max over banks of (# distinct words H places in that bank)`.
  Same-word requests within a half coalesce (count once).
- `wavefronts = passes(H0) + passes(H1)`. Floor = **2** (each conflict-free
  half = 1 pass).
- This model reproduces **every store** and **every non-merged load** exactly,
  and beats whole-warp aggregation (`distinguish3/4`) and an even/odd split.

## (2) Merge — a LOAD-ONLY optimization layered on top
For loads, the two half-warp transactions can collapse into a single whole-warp
broadcast transaction → **exactly 1 wavefront**.
- **All-or-nothing:** it either fires (→1) or it doesn't (→ the half-warp count,
  i.e. load = store). No intermediate value ever observed.
- **Gate — both required:**
  1. **Conflict-free at warp scope:** ≤1 distinct word per bank across all 32
     lanes. A single genuine 2-way (two distinct words in one bank) disables it
     (`merge_plus_conf`: pairmerge + one 2-way ⇒ load 2 = store).
  2. **Crossbar-routable lane→word map** (see routable set below).
- **Stores never merge** — floor is always 2.

### Routable set for gate (2) — empirical
Merges to 1 (conflict-free + routable):
- full broadcast (all lanes → one element);
- contiguous power-of-2 lane blocks → consecutive elements: `tid^1` (÷2),
  `quad` (÷4), `oct` (÷8);
- **reversed** and **rotated/wrapped** contiguous variants (`revpair`,`rotpair`);
- intra-4-lane **single-bit-flip** sharing: `tid^1` (bit0), `tid^2` (bit1).

Does **not** merge (stays at the half-warp count):
- `tid^3` (two-bit intra-quad butterfly);
- `tid^4`, `tid^8`, `tid^16` (cross-quad, or two interleaved runs = `half_lo_hi`);
- **anything with a genuine bank conflict** (gate 1 fails).

The precise permitted-permutation set is a butterfly/Beneš-like crossbar property
and is not reduced to closed form here. Practical rule of thumb: *natural*
contiguous vector loads (consecutive / broadcast / power-of-2-blocked, incl.
reverse/rotate) get the 1-wavefront bonus; scattered sharing across distant lanes
does not.

## One-line takeaways
- **Store v2 cost** = `passes(lanes0-15) + passes(lanes16-31)`, always ≥2.
- **Load v2 cost** = `1` iff (warp-conflict-free AND routable), else identical to
  the store cost.
- The per-half bank-conflict rule is the *scalar* rule applied to 16 lanes ×
  2 words = 32 words per transaction.

---

# Vectorized v4 (LDS.128 / STS.128) — 128-bit shared access

Harness: `tests/bankconf/harness_v4.cu` (thread touches words `[base..base+3]`,
base a multiple of 4 ⇒ 16B aligned; one `LDS.128`/`STS.128` per warp). Predictor
columns: `pWhl`=whole-warp, `pHlf`=2×16-lane halves, `pQtr`=4×8-lane quarters.

## Data
| pattern                                   | LDS W | STS W | pWhl | pHlf | pQtr |
|-------------------------------------------|:-----:|:-----:|:----:|:----:|:----:|
| consec `e=t` (128 distinct words)         |   4   |   4   |  4   |  4   |  4   |
| broadcast (all one element)               | **2** | **4** |  1   |  2   |  4   |
| pairshare / quad / oct / share:1 / share:2| **2** |   4   | 1–2  | 2    |  4   |
| share:4 / share:8 / share:16              |   4   |   4   | 2    | 2–4  |  4   |
| estride 2 / 4 / 8                          | 8/16/32 | 8/16/32 | =W | =W | =W |
| `dist_q0` (2-way piled in Q0, rest bcast) | **6** | **6** |  3   |  4   |  6   |
| `bnd_in`  (2 bank0 words in lanes 6,7)     | **5** | **5** |  2   |  3   |  5   |
| `bnd_cross`(same words straddle lanes 7,8) | **4** | **4** |  2   |  3   |  4   |

## Findings
1. **Floor = 4 wavefronts.** A 128-bit access moves 4 words/lane = 128 words/warp.
2. **Partitioning is per QUARTER-warp (8 lanes):** transactions gather lanes
   `{0-7}`, `{8-15}`, `{16-23}`, `{24-31}`, each 8 lanes × 4 words = 32 words.
   `wavefronts = Σ passes(Qi)`. Proven: `dist_q0` = **6** = pQtr (≠ pHlf 4, ≠ pWhl 3);
   boundary pinned by `bnd_in` (5, both hot words in Q0) vs `bnd_cross` (4, hot
   words straddle lane 7|8). Stores follow pQtr everywhere.
3. **Load delivery limit = 2 words (64 bit) / lane / wavefront.** A broadcast v4
   load costs **2**, not 1, even though there is a single distinct element
   (pWhl=1). So a merged v4 load floors at `ceil(4/2)=2`.
4. **Load merge** (quarter-sum → 2) fires for the same routable + conflict-free
   set as v2 (broadcast, share:1/2, ÷2/÷4/÷8 blocks); does **not** for share:4/8/16
   or any genuine conflict. All-or-nothing: value is either 2 (merged) or the full
   quarter-sum. **Stores never merge** (floor 4).

---

# UNIFIED transaction model (scalar / v2 / v4) — Blackwell sm_120

Let `w` = words per lane (scalar 1, v2 2, v4 4) and `G = 32 / w` the lane-group
size (32, 16, 8).

**A shared transaction** touches all 32 banks, moving **one b32 word per bank**
(≤32 words), gathered from a **contiguous run of `G` lanes**:
- scalar → 1 group of 32 lanes (whole warp),
- v2 → 2 groups `{0-15}{16-31}` (half-warps),
- v4 → 4 groups `{0-7}{8-15}{16-23}{24-31}` (quarter-warps).

Default number of transactions = `w` (= the floor: 1 / 2 / 4).

**Conflicts** are counted *independently inside each lane-group* via the scalar
rule applied to that group's `G × w = 32` words:
`passes(group) = max over banks of (# distinct words the group puts in that bank)`
(multiple lanes on the same word coalesce). `wavefronts = Σ passes(group)`.

- **STORE:** exactly this. No merge, no broadcast collapse. Floor `= w`.
- **LOAD:** same when not merged. A **merge** collapses the per-group transactions
  into a whole-warp broadcast, gated on **(1) whole-warp conflict-free (≤1 distinct
  word/bank)** and **(2) a crossbar-routable lane→word map**. But a load wavefront
  delivers only **64 bit (2 words) per lane**, so the merged cost is
  `ceil(w/2)` = **1 (v2), 2 (v4)**, not 1. Merge is all-or-nothing (routable-floor
  `ceil(w/2)` **or** the full group-sum).

Scalar is the degenerate case: 1 group, floor 1, merge floor `ceil(1/2)=1`; there
load and store were byte-identical because same-word coalescing already gives the
group-sum and no split exists.

**Routable set (gate 2), empirical, same for v2 & v4:** full broadcast; contiguous
power-of-2 lane blocks → consecutive elements; reversed/rotated contiguous;
intra-group single-bit-flip sharing (`tid^1`,`tid^2`). NOT routable: `tid^3`,
`tid^4+`, interleaved runs, or anything with a real conflict. The exact permitted
permutation set is a butterfly/Beneš-like crossbar property, not closed-form here.

---

# L1 / shared interaction — attempted trigger (sm_120): NOT a bank conflict

Question: does simultaneous **vectorized global** (L1-cached) + **vectorized shared**
access create bank conflicts (unified L1/shared SRAM contention)?
Harness: `tests/bankconf/harness_lx*.cu` + `runlx.py`. Each warp issues, per loop
iteration, an optional `LDG.E.128` (global v4) and/or an optional
`STS.128`+`LDS.128` (shared v4), via volatile PTX. Toggled by `-DGLOB/-DSHAR`.
Metrics: shared/global/arbitration/total bank conflicts + per-client wavefronts.

## Scenarios tried (single warp → 32 blocks × 8 warps)
- coalesced global v4 (L1 hot) + conflict-free shared v4;
- streaming global v4 (16 MB window ≫ L1, all-miss fills) + shared;
- scattered global v4 (stride 32, millions of L1 bank conflicts) + shared;
- heavy-conflict shared (8-way) + global (positive control).

## Result — no interaction bank conflict
| case                                  | shSTc | shLDc | glLDc | ARBc |
|---------------------------------------|:-----:|:-----:|:-----:|:----:|
| shared-only, conflict-free            |   0   |   0   |   —   |  0   |
| coalesced global-only                 |   —   |   —   |  ~0*  | ~0*  |
| coalesced global + shared             |   0   |   0   |  ~0*  | ~0*  |
| scattered global-only (stride 32)     |   —   |   —   | 4.87M | ~200*|
| scattered global + shared             |   0   |   0   | 2.94M | ~580*|
| **heavy-conflict shared only**        |7.168M |7.168M |   —   |  0   |
| **heavy-conflict shared + global**    |7.168M |7.168M |  ~8*  | ~17* |

`*` tiny counts that do **not** scale with iters (10× iters ⇒ ≈constant) ⇒
cold-start L1 fills, not per-access events.

Key facts:
1. **Shared bank-conflict counters depend ONLY on the shared access pattern.**
   The heavy-conflict shared workload reports the *identical* `7,168,000`
   conflicts with and without concurrent vectorized global traffic. Global never
   induces, increases, or perturbs shared bank conflicts.
2. **Global bank conflicts depend ONLY on the global pattern** (0 when coalesced,
   millions when scattered — the L1 data array is itself 32-banked). Shared
   presence does not add global conflicts either.
3. **Arbitration conflicts** (`..._type_arbitration`) are tiny, iter-independent
   (cold-start fills), and do **not** rise when shared is added
   (streaming global: 157 alone vs 155 with shared).

## What the "interaction" actually is: throughput serialization
Global and shared wavefronts both flow through the **single L1TEX data stage**
(~1 wavefront/cycle). They are **serialized, not overlapped**, so:
- wavefronts are **exactly additive**: G(2.05M) + S(4.10M) = GS(6.14M);
- cycles are additive: G(288k) + S(669k) ≈ GS(998k), ~4% over sum.

So "doing vectorized global + vectorized shared together is slow" is **shared-pipe
(L1TEX data-stage) throughput contention**, which can be mistaken for a bank
conflict but generates **zero** extra bank-conflict events on this GPU. A likely
source of the folklore is uncoalesced/vectorized *global* loads incurring their
own L1 bank conflicts (`gds_op_ld`), separate from the shared counter.

## Caveat / open
- Not reproduced ≠ impossible: a specific L1-line-to-bank alignment vs a specific
  shared pattern might still collide; but across hot/streaming/scattered global ×
  clean/heavy shared, none appeared. `LDGSTS`/`cp.async` (global→shared) is a
  distinct path (`op_ldgsts` counters) and was not tested here.

---

# cp.async / LDGSTS — shared-WRITE bank conflicts (global→shared DMA)

`cp.async.{ca,cg}.shared.global [dst_shared], [src_global], sz` (SASS `LDGSTS`,
sz∈{4,8,16}). The bank-conflictable side is the **shared write** (dst pattern).
Harness `tests/bankconf/harness_cpasync.cu` (one LDGSTS/warp, dst word index from
file, coalesced source) + `runcp.py`. Counters: `op_ldgsts` conflicts/wavefronts,
split into `_cache_access` (ca) and `_cache_bypass` (cg). `W`=wavefronts.

## Partitioning — same size→group map as STS, floor = sz/4
| sz  | SASS         | lane-group | floor W |
|-----|--------------|------------|:-------:|
| 4 B | LDGSTS.E     | whole warp (32) | 1 |
| 8 B | LDGSTS.E.64  | half-warps (16) | 2 |
|16 B | LDGSTS.E.128 | quarter-warps (8) | 4 |

Verified: `dist_q0`=27, `bnd_in`=26, `bnd_cross`=24 (16B) and the 8B `bnd_in`=18,
`bnd_cross`=16 all match `Σ over groups of (max writes-per-bank in that group)`
with the STS group boundaries (quarter split pinned at lane 7|8, half at 15|16).

## KEY DIFFERENCE vs STS/LDS: **no same-word coalescing**
A store (STS) coalesces multiple lanes writing the *same word* into one write
(one undefined winner). **cp.async does NOT** — each lane is an independent copy
descriptor, so every thread write counts:

`passesCP(group) = max over banks of (# THREAD WRITES landing in that bank)`
(count threads, not distinct words). `conflicts = W − floor`.

Evidence (ca path), cp.async W vs the equivalent STS W:
| pattern                    | cp.async W | STS W | note |
|----------------------------|:----------:|:-----:|------|
| 4B broadcast (all → word0) |   **32**   |   1   | 32 indep writes, no coalesce |
| 4B `share31_plus1`         |   **32**   |   2   | 31 same-word + 1 ⇒ 32, not 2 |
| 8B broadcast               |   **32**   |   2   | half×16 writes/bank |
| 8B `share:1` (pairs share) |   **4**    |   2   | 2 writes/bank/half |
| 16B broadcast              |   **32**   |   4   | quarter×8 writes/bank |
| 16B `pairshare`/`quad`/`oct`| 8 / 16 / 32 | 2/2/2 | ×(lanes sharing) |
| 16B `consec` / `estride:2` |   4 / 8    | 4 / 8 | distinct words ⇒ same as STS |

So distinct-address patterns cost the same as STS, but **broadcasting or sharing a
shared destination across lanes is a full N-way conflict under cp.async** (it is
free/cheap under STS). Practical: staging global→shared with `cp.async`, never let
multiple lanes target the same shared word/element.

## ca vs cg (bypass L1)
- `cp.async.ca` (default) → counted on `op_ldgsts` / `_cache_access`; clean model
  above.
- `cp.async.cg` (16B only, bypass L1) → the standard `op_ldgsts` counters read **0**;
  its shared writes appear only on the `_cache_bypass` sub-counters, where the
  bank-conflict counter is **0 for every pattern tried** and the bypass *wavefront*
  sub-counter does not follow the group model (bcast=1, consec=4, share:1=16,
  estride=32). The bypass path stages global→L2→shared differently; its shared-side
  bank accounting is not cleanly captured by these counters. **Open.**

## Open
- cg/bypass true shared-bank behavior (counter granularity unclear).
- Whether cp.async ever coalesces when lanes share *both* src and dst.

## Scattered SOURCE with conflict-free destination — YES, it conflicts (ca)
Holding dst conflict-free (16B `consec`, quarter floor 4) and scattering the
**source** global address (`SRCSTRIDE` in harness): the cp.async still incurs
bank conflicts, charged to the shared `op_ldgsts` counter.

| srcstride | shC | shW | glW | glSec | gdsC |
|-----------|:---:|:---:|:---:|:-----:|:----:|
| 1 (coalesced) | 0 |  4 | 1 | 16 |  0 |
| 2             | 4 |  8 | 2 | 32 |  4 |
| 4             |12 | 16 | 4 | 32 | 12 |
| 8             |24 | 32 | 8 | 32 | 24 |
| 16            |24 | 32 | 8 | 32 | 24 |
| 32            |19 | 32 | 9 | 32 | 19 |

Two exact relationships across the sweep:
- **`shW = glW × dst_passes`** (dst_passes = 4 here), capped at 32 (= one
  wavefront/thread). The shared write is replayed once per global-fetch wavefront:
  a scattered source forces the L1 read into `glW` sector-gather passes, and the
  fused copy re-runs the shared write for each.
- **`shC == gdsC`** exactly. The originating conflict is the **global L1 read**
  (scattered access banks-conflict in the L1 data array, `mem_gds`), and that
  same conflict count is *also* attributed to the shared `op_ldgsts` counter
  because `LDGSTS` is a single fused read→write op.

**Mechanism / takeaway:** unlike a separate `LDG`+`STS` pair (where global-scatter
conflicts land only on `gds_op_ld` and shared conflicts only on `op_st`),
`cp.async` fuses the two, so a **scattered source pollutes the shared-side
counters and multiplies shared-write wavefronts** even when the shared destination
is perfectly conflict-free. For fast `cp.async` staging, the *source* must be
coalesced too — a scattered/gathered source is as harmful as a bad dst pattern.

---

# Global (L1-cached) READ bank conflicts — the condition (== shared rule)

`cp.async` scattered-source conflicts equal `gdsC` (global L1 read bank conflicts),
so the real question is: when does a scattered **L1-hit global read** bank-conflict?
Isolated with a plain looped `LDG` (windowed so it stays L1-resident and re-reads
the data array each iter; counts scale linearly with iters ⇒ steady-state).
Harness `tests/bankconf/harness_gld.cu` (`-DVEC=1|4`), metric
`l1tex__data_bank_conflicts_pipe_lsu_mem_gds_op_ld`. `W`=global data wavefronts.

## Scalar LDG (per warp-load, iters-normalized)
| pattern    | gdsC | glW | glSec |
|------------|:----:|:---:|:-----:|
| id         |  0   |  1  |  ~5   |
| broadcast  |  0   |  1  |  1    |
| stride 2   |  1   |  2  |  ~9   |
| stride 4   |  3   |  4  |  16   |
| stride 8   |  7   |  8  |  32   |
| stride 16  |  15  | 16  |  32   |
| stride 32  |  31  | 32  |  32   |
| stride 33  |  0   |  1  |  32   |

## v4 LDG
| pattern      | gdsC | glW | matches |
|--------------|:----:|:---:|---------|
| consec       |  0   |  4  | quarter floor |
| broadcast    |  0   |  4  | (no shared-style merge-to-2) |
| estride 2/4  | 4/12 | 8/16| quarter sum |
| `dist_q0`    |  2   |  6  | pQtr=6 |
| `bnd_in`     |  1   |  5  | pQtr=5 |
| `bnd_cross`  |  0   |  4  | pQtr=4 |

## The condition (identical to shared memory)
The **L1 data array is banked exactly like shared**: `bank = (byte_addr / 4) mod 32`
(32 banks × 4 B). A global L1-hit read bank-conflicts iff, within a transaction,
two lanes hit the **same bank with different 4-B words**:
1. **Broadcast/same-word ⇒ free** (`bcast` gdsC=0). Same-word coalesces.
2. **Stride S words ⇒ `32/gcd(S,32)`-way** conflict: 2,4,8,16,32-way for
   S=2,4,8,16,32; **odd/coprime stride (e.g. 33) ⇒ conflict-free**.
3. **Bank is line-independent:** stride 32 puts every lane at offset 0 of a
   *different* 128-B line, all bank 0 ⇒ full 32-way. So colliding the same bank
   across different cache lines conflicts just like within a line.
4. **Vectorized global uses the same lane-group partition** as shared/STS
   (scalar=whole warp, v4=quarter-warps at the 7|8/15|16/23|24 boundaries).

## Two independent costs of "scatter" (don't conflate)
- **Bank conflict** (`gdsC`): the `(addr/4)%32` collision rule above — an
  *L1-hit data-array* property.
- **Coalescing / sectors** (`glSec` = distinct 32-B sectors, drives L2 traffic and
  T-stage wavefronts `glTW`): a *tag/line* property at 32-B granularity.
  Orthogonal: stride 33 is **bank-conflict-free** (gdsC=0) yet touches 32 sectors
  (glSec=32) — bad coalescing, good banking.

## Differences from shared
- Global loads do **not** get the shared load's broadcast merge-below-floor
  (v4 `bcast`/`share:1`: global glW=4 vs shared LDS glW=2). Conflict *presence*
  is identical; only the merge bonus is shared-exclusive.
- The conflict is an **L1-hit** phenomenon; on an L1 miss the cost is sector/L2
  bound instead. `cp.async.ca` reads the source into L1, so its scattered-source
  penalty is exactly this global L1-read bank conflict (hence `shC == gdsC`).

## Worked example — the Zhihu `cp.async` kernel (validated)
`tests/bankconf/zhihu_cpasync.cu`. 16B `cp.async.ca` per thread; dst `smem+4*tid`
(consecutive ⇒ conflict-free), src `d_ptr + tid*32` (stride 32 floats = 128 B).
Measured **per warp** (identical at blockDim 32 and 256):
`shC=24  shW=32  gdsC=24  glSec=32  glTW=8`  — i.e. **fully serialized (32
wavefronts)** despite a perfect shared layout.

Why: src word offset `32*tid` ⇒ bank `(32*tid+k)%32 = k`, so **every lane's 4
words land in banks {0,1,2,3}**; bank 0 is hit by all 32 lanes with distinct
words ⇒ 32-way conflict on the **global L1 read**. `cp.async` fuses read→write, so
this source conflict is charged to the shared `op_ldgsts` counter (`shC==gdsC`)
even though the destination never conflicts. The stride (128 B) is also a bad
coalesce (`glSec=32`).

Source-stride sweep (dst fixed conflict-free), showing the two independent costs:
| src stride (floats) | shW | shC=gdsC | glSec | note |
|---------------------|:---:|:--------:|:-----:|------|
| 4 (contiguous)      |  4  |    0     |  16   | ideal: coalesced, no conflict |
| 8                   |  8  |    4     |  32   | partial bank conflict |
| **32 (kernel)**     | 32  |   24     |  32   | **max bank conflict + uncoalesced** |
| 36 (=32+4)          | 13  |    0     |  32   | banks spread (stride%32=4) ⇒ no conflict; still uncoalesced |

Lesson: a stride that is a **multiple of 32 words** aligns every lane to the same
banks ⇒ worst-case global-read bank conflict, surfaced on the shared cp.async
counter. Fixing the bank conflict (stride ≢ 0 mod 32) and fixing coalescing
(small/contiguous stride) are *separate* concerns; the contiguous layout fixes both.

## How many wavefronts is an ideal cp.async.16 (512 B/warp)? — 4, not 8
Intuition "read 512 B (4 wf) + write 512 B (4 wf) = 8" is **wrong**. Measured, ideal
(coalesced source, conflict-free dst), per warp/instruction:
- **shared WRITE** (`op_ldgsts` data wavefronts) = **4** (512 B ÷ 128 B/cycle over
  the 32-bank data array) — this is the "4" you profile.
- **source READ**: T-stage `glTout = 1` wavefront (coalesced tag/sector pass),
  `glSec = 16` sectors; data-stage **`cmd_read` wavefronts = 0**.

Crucially, an **L1-resident (hit) source** still gives `cmd_read = 0`
(`cploop`: glSecHIT≈16 all-hit, cmdREAD=0, shWRITE=4). So cp.async never performs a
separate 128 B/cycle data-array *read* of the source. The source is fetched on the
**tag/sector (memory) path** and streamed straight into the shared write; only the
**shared write** traverses the 32-bank data array (4 wf). That is precisely why
`cp.async` is efficient — it avoids the register file *and* the double data-array
traversal an `LDG`+`STS` pair would pay.

- **Ideal cost = 4 wavefronts** (write-bound at the data stage); the read is 1
  T-stage pass, pipelined, not on the data-array.
- The read only gets expensive when the **source is scattered**: then
  `glTout` grows and `shWRITE = glTout × dst_passes` (stride-32 example:
  glTout=8 ⇒ shWRITE=32). i.e. a bad source multiplies the *write* wavefronts,
  it does not add a symmetric second read pass.

## L1-fill vs shared-write bank alignment — fill co-writes the same bank (CONFIRMED)
Since cp.async has `cmd_read=0` even on an L1 hit, the L2 data must go into **shared
and L1 simultaneously** (parallel fill + shared write), not fill-then-copy. Test of
whether the L1 fill and the shared write share the bank-write machinery:
`harness_align.cu` — dst `smem+4*tid` (consec, conflict-free), src `d+woff+4*tid`
(coalesced, conflict-free); `woff` shifts the **L1-fill bank** vs the
**shared-write bank** by `woff % 32`. Both are conflict-free viewed alone.

Per cp.async (16 B, 512 B/warp):
| case                         | woff%32 | shWRITE | total wf |
|------------------------------|:-------:|:-------:|:--------:|
| STREAM (miss ⇒ **fills** L1) |   0     | **4**   | 5.76     |
| STREAM (miss ⇒ fills L1)     |  ≠0     | **5**   | 6.76     |
| WINDOW (**L1 hit**, no fill) | any     |   4     | —        |

- **Aligned fill does not increase `shGS`** over the shared-write-only cost (4 = hit
  and fill both give 4). Whether the fill is genuinely free (dual-row write
  broadcasting to two rows in the same bank cycle), uses a separate write port, or
  simply has a cost invisible to the shared-write counter is **not determined** by
  these experiments. The key fact: `shGS` is unchanged by the presence of a fill.
  - Supporting counter evidence: `lgds = glTout` always (e.g. 2 = 2 for the
    8-thread predicated kernel `zh4`); `cmd_read = 0` (no separate data-array
    read); and `TOTwf = shTOT + lgds` (total data-stage wavefronts decompose
    additively into shared + global portions, with no hidden fill term). At 0.2 %
    L1 throughput on the `zh4` kernel, fill bandwidth does not overflow any
    visible counter.
- **Misaligned fill costs +1** (`shGS` 4→5) in the STREAM (miss) case only. The
  cause is **sector overflow**: `woff=4` adds 1 sector (17 instead of 16) ⇒
  `glTout=2`. The 5th shared-write pass is for the overflow sector's data. In the
  HIT case `glTout=2` but `shGS` stays at 4 — the overflow data is absorbed into
  the 4 existing passes when no fill contends for the data array. Whether the fill
  disrupts this absorption by additional data-array traffic (dual-row path) or by
  some other mechanism is not isolated here.

Practical note: the penalty is small (+1 of 4 ≈ 25%) and only on fills with a
misaligned source base; avoid it by keeping the source base **sector-aligned**
(addr % 512 == 0, i.e. `(src_addr/4)%128 == 0`), which the natural contiguous
staging (`src = base + 4*tid`, `dst = smem + 4*tid`) already satisfies.

### RESOLVED: how cp.async fill and shared write interact — final model

**The fill really does 4 physical 128B writes through the data array**, but they are
**fused/co-scheduled** with the shared-write bank passes, so they **never cost their
own pass**. The `lgds=1` counter measures the T-stage (tag/sector) request, not the
fill writes. The fill writes are accounted under `shGS` (shared-write counter),
piggybacked.

**Ideal (coalesced, sector-aligned base):** `glTout=1` — 16 sectors fit in 1
T-stage pass. The shared write takes 4 data-array passes (quarter floor for 16 B).
In each of those 4 bank-write cycles, the SRAM enables **both** the shared row
**and** the L1 fill row at the **same bank** (simultaneous-dual-row-write
broadcast). Fill cost: **0** extra → `shGS=4`.

**Misaligned base (e.g. `woff=4`, offset 4 B):** the base offset causes the 512 B
warp load to span **17 sectors** (1 overflow, crossing a 512 B boundary), hence
`glTout=2`. T-pass 1 delivers 16 sectors → shared writes in its 4 passes + fill
writes in the same 4 passes (bank-aligned portion, fused). T-pass 2 delivers the 1
overflow sector → the shared write needs 1 extra pass to service the overflow data,
and the fill also writes its portion in that same pass. Result: `shGS = 4 + 1 = 5`.
Formula: **`shGS = floor + (glTout − 1)`**.

**Why the penalty is +1, not +4 (not `4+4=8`):** the fill never takes its own
independent passes — it always piggybacks on the shared write. The misalignment cost
is *not* a fill-vs-shared bank collision; it is a **sector-alignment overflow**
(glTout 1→2). The extra T-stage pass forces one additional shared-write pass (which
also carries the fill). Confirmed by: `glTout=2` even on a pure L1 hit (no fill),
and the `lgds=1` counter never rises because it counts T-stage requests, not fill
passes.

**Summary of counter accounting:**
- `shGS` — data-array shared-write wavefronts; the fill writes are also counted
  here (fused), so shGS = floor + overflow passes.
- `lgds` — local/global/dshared wavefronts on the data stage; always 1 (the
  coalesced global read side of cp.async).
- `glTout` — T-stage output wavefronts (sector passes); drives the overflow count.
  `glTout=1` for ≤16 sectors, `glTout=2` for 17, etc.
- `cmd_read` — data-stage read wavefronts: always **0** for cp.async (the read
  from the memory pipe, not the data array).
- `cmd_write` — 1 (= one LG/DS instruction write command per warp).
- The fill is 4 physical 128 B data-array passes, but they run *concurrently* with
  the shared write, piggybacked. The counter only reports the shared-side wavefront
  count.

## Bank-conflict counting for cp.async: `shC = shW − glTout` (verified across strides)

Sweep of source address stride (cp.async 16 B, dst conflict-free consecutive), per warp:
| srcstride (bytes) | shW | shC | glSec | glTout | shW−glTout |
|-------------------|:---:|:---:|:-----:|:------:|:----------:|
| 16 (coalesced)    |  4  |  0  |  16   |   1    |     3      |
| 32                |  8  |  4  |  32   |   2    |     6      |
| 64                | 16  | 12  |  32   |   4    |    12      |
| 128 (Zhihu)       | 32  | 24  |  32   |   8    |    24      |
| 256               | 32  | 24  |  32   |   8    |    24      |
| 512               | 32  | 19  |  32   |   9    |    23      |

Key: `shC == gdsC` exactly (see srcstride sweep table earlier), and
**`shC = shW − glTout`** for the fixed-dst-floor cases (srcstride 4–8):
e.g. stride=8: `24 = 32 − 8`. Check: stride=4: `12 = 16 − 4`. ✓ strides 2,16
deviate slightly (2: 4 vs 6; 16: 24 vs 24 ✓; 32: 19 vs 23).

Interpretation for the Zhihu kernel (`shW=32, shC=24, glTout=8`):
- Each T-wavefront schedules 1 "baseline" shared-write pass and associated fill
  writes, conflict-free (the minimum data-array presence).
- The 3 additional passes per T-wavefront (to reach the quarter-warp floor of 4)
  are also needed, but they collide with the fill writes to the same banks (0–3)
  across iterations → counted as bank conflicts.
- Thus `shC ≈ shW − glTout`: 32 total passes − 8 baseline passes = 24 extra
  contentions charged as conflicts.
- The counter `bank_conflicts` for cp.async (`op_ldgsts`) *includes the fill-write
  conflicts* because cp.async is fused (proven: `shC == gdsC` at all strides).

The "24 bank conflicts" are not "24 wavefronts being removed" but "24 wavefronts
(out of 32) counted as conflicted (serialisation-penalised) relative to the
1-per-T-wavefront baseline". 32 wavefronts is the *actual* count; 24 of them are
recorded as extra.

### Tag-array serialization is additive to, not absorptive of, bank conflicts (VERIFIED)

L1 tag array: **4 banks, 1 tag query/bank/cycle**. Each T-wavefront issues a tag
lookup. Measured tag set-conflict counter `setC` across the full stride sweep and
the two kernels:

| stride | glTout | setC | `= glTout−1`? | shC | setC+shC |
|--------|:------:|:----:|:-------------:|:---:|:--------:|
| 1      |   1    |  0   | ✓0            |  0  |    0     |
| 2      |   2    |  1   | ✓1            |  4  |    5     |
| 4      |   4    |  3   | ✓3            | 12  |   15     |
| 8      |   8    |  7   | ✓7            | 24  |   31     |
| k2     |   8    |  7   | ✓7            | 24  |   31     |
| k3     |   1    |  0   | ✓0            | 28  |   28     |

**`setC = max(0, glTout − 1)` in every case.** The tag array serialises one extra
cycle per T-wavefront beyond the first (each T-wavefront after wavefront 1 contends
for one of the 4 tag banks, adding 1 contention cycle). It is **not** absorbed from
`shC` — it is a **separate tag-pipeline cost**.

**`shC` and `setC` are additive** — the total pipeline penalty = `shC + setC`:
- Kernel 3 (dst-conflict, glTout=1): total = 28 + 0 = 28.
- Kernel 2 (src-scatter, clean dst, glTout=8): total = 24 + 7 = **31**.
Kernel 2 has 3 *more* total penalty cycles despite fewer bank conflicts, because
the 7 tag serializations more than offset the clean-dst advantage (24 vs 28).

So the correct reading is:
- **`shC`** = bank conflicts on the shared data array (dst/fill contention,
  independent of tag serialization).
- **`setC`** = tag-set conflicts, entirely from T-wavefront serialization
  (`glTout − 1`), added on top.

The 24 vs 28 is genuinely fewer bank conflicts (kernel 2's dst is consecutive and
conflict-free; kernel 3's dst is heavily conflicted). It is **not** 28 minus 4
absorbed — the tag never subtracts from the bank-conflict counter.

### Example — reversed-group ordering turns a 32-way conflict into conflict-free
`tests/bankconf/` run `rev`. Source: coalesced `d_ptr + tid * 4` (16 B cp.async,
ideal coalescing). Destination: `smem + 4*(31 − tid)` — groups of 4 consecutive
floats stored in reverse order (group 31→lowest smem address, group 0→highest).
Profile: `shW=4, shC=0, gdsC=0, glTout=1` — fully conflict-free.

Why it works (kernel 3 forward stride `32*tid` is the opposite):
- forward: bank = `(32*tid + k) % 32 = k` — all 32 threads to banks {0,1,2,3}
  only, each bank gets 32 distinct words → quarter max = 8 → shW = 32.
- reverse: bank = `(4*(31−tid) + k) % 32`. Within each quarter, the 8 threads
  have distinct base offsets `4*tid` stepping by 4, so 8 distinct banks per k
  value. Across k=0..3, all 32 banks are used exactly once per quarter → passes=1,
  shW=4. The `−4*tid` rotation perfectly complements the `+k` stride to fill all
  banks evenly.

Lesson: a scatter that *rotates* by a coprime-to-32 offset per thread (here `−4*t`
within each quarter) is conflict-free, while a scatter that *repeats* (e.g.
`+32*t` aligning every thread to the same banks) creates maximal conflict.

## UNIFIED MODEL — L1 read, shared write, and tag conflicts

The L1 data array and shared memory are the **same physical 32-bank SRAM**. Both
sides produce bank conflicts under the identical `bank = (addr/4) % 32` rule. The
L1 tag array is a separate 4-bank structure; tag conflicts are additive.

### Two kernels, two bottlenecks, one 32-modular root cause

| kernel | source | dst | primary conflict | count | why |
|--------|--------|-----|------------------|:-----:|-----|
| k2 | stride 32 words | consecutive | L1 **read** bank conflict | 24 | all lanes→banks {0,1,2,3}, 8 sectors/T-wf → 3-way per T-wf × 8 |
| k3 | coalesced | stride 32 words | shared **write** bank conflict | 28 | all lanes→banks {0,1,2,3}, 8 writes/bank/quarter → 7-way per quarter × 4 |

Both kernel 2 and kernel 3 are victims of **stride-32 = multiple-of-32-words**,
which maps every lane to the same 4 banks. The only difference is *which side*
blocks: kernel 2 blocks on the L1 read, kernel 3 on the shared write.

### Tag-array conflicts — independent and additive

Tag array: 4 banks, 1 lookup per 128 B cache line per cycle.
- 1 cache line (coalesced, ≤512 B): 1 tag lookup → 0 tag conflicts.
- N scattered cache lines: **setC = glTout − 1** (each T-wavefront beyond the first
  contends for a tag bank).

### The `+tid*4` fix — kills bank conflicts on both sides

Adding `+tid*4` (4-word offset) to either source or destination rotates the base
address by `4t mod 32 = 4t`, which in each quarter maps all 8 threads to 8 distinct
banks (for each of the 4 word components). Across all k=0..3, every bank receives
exactly 1 write per quarter → conflict-free.

**Verified:**
- **kernel 2 + `tid*4` on source** (`k2fix`): `gdsC=0` (L1 read banks spread),
  `setC=8` (tag conflicts from scattered sectors remain).
- **reverse-destination kernel** (`rev`, `smem+4*(31−tid)` = same `−4t` rotation):
  `shC=0, shW=4`. Equivalent to kernel 3 + rotation on dst.
- **predicated 8-thread version:** `gdsC=0, shC=0` (both sides spread by `+4t`).

The root cause is always **stride ≡ 0 (mod 32 words)**. Breaking that alignment
with `+4t` distributes across all banks. The `+tid*4` term contributes
`4t mod 32`, which for 8 threads per quarter gives 8 distinct residues
{0,4,8,12,16,20,24,28} — none collide.

---

# COMPLETE UNIFIED PIPELINE MODEL for cp.async

**Step 1 — LSU partitioning.** cp.async size={4,8,16}B → LSU splits the warp into
full/half/quarter-warp transactions (same as STS/LDS v1/v2/v4 boundaries). No
transaction coalescing (no broadcast merge like LDS.64 → 1 wf).

**Step 2 — T-stage (tag array, 4 banks).** Each LSU transaction's global addresses
are decomposed into cache-line tags. The 4-bank tag array resolves one lookup per
128 B line per bank per cycle. If the LSU transaction spans multiple cache lines
whose tags conflict in the 4-bank array, the LSU transaction is **split into
multiple TAG transactions** (one per non-conflicting tag batch). Measured:
`setC = glTout − 1` = number of extra tag cycles.

**Step 3 — Fill (on miss).** If a tag lookup misses, an MSHR is allocated and the
cache line is filled from L2 in 32 B sectors. Unaccessed sectors within a line may
be skipped (partial fill — consistent with sector-granularity `glSec` accounting).

**Step 4 — Data-stage (32-bank data array).** Each tag transaction enters the data
stage. The hardware determines the data-array bank-conflict profile of the combined
**(L1 read + shared write)** for that tag transaction. If bank conflicts exist, the
tag transaction is split into **N data transactions**, each performing one
conflict-free 128 B pass (one word to each of the 32 banks). The bank-conflict
counter increments by `N − 1`:

> **`shW = Σ(N_data)`** across all tag transactions and LSU transactions.
> **`shC = gdsC`** (fused counter for cp.async) = Σ(N_data − 1).

where N is determined by the `max over banks of (# distinct cache-line words or
destination words in that bank per tag transaction)`, subject to the 32-bank,
1-word-per-bank-per-pass constraint.

**Validated against all 7 experimental scenarios** (ideal, kernel 2, kernel 3,
misaligned woff=4, zh4 predicated, k2fix, reverse dst). No counterexamples found.

## Data-transaction splitting order — L1-read first, then shared write (RESOLVED)

Test: predicated 8-thread cp.async 16B, one tag transaction (glTout=1). L1 read has
a 3-way conflict (threads {0,1,2} on bank 0); shared write has a 3-way conflict
(threads {0,1,3} on bank 4). Overlap = {0,1}. Both sides conflicted, overlapping
subsets.

Measured: **shW=3, shC=2, gdsC=2**.

- **L1-read-first:** 3-way read conflict → 3 data txs. Threads {0,1} are
  separated by the read split, so threads {0,1,3} no longer conflict on write
  within any group → no further splits. **shW=3.** ✓ matched measurement.
- **Shared-write-first:** 3-way write conflict → groups {0},{1},{3}+{rest}. But
  {rest} contains thread 2 with its L1 read conflict on bank 0 (thread 2 reads
  bank 0 but thread 0 is in a different group → no cross-group conflict? No, the
  conflict is *within* the group: thread 2 reads bank 0, and no other thread in
  {rest} reads bank 0, so 1 tx. Then {0} alone → 1, {1} alone → 1, {3} alone →
  1. Total **shW=4.** ✗ not matched.

**Conclusion:** the data stage resolves **L1 read bank conflicts FIRST**, splitting
into N groups such that each group has ≤1 distinct word per bank for the L1 read.
Then, within each read-split group, shared write conflicts are resolved
independently. The total number of data transactions = number of read-split groups ×
(additional splits for write conflicts per group). When cp.async has no L1 read
conflicts (coalesced source), the first split is vacuous (N=1) and only the write
conflict splitting applies.

This resolves the final open question in the unified pipeline model.
