# wgmma — warpgroup async MMA synchronization (sm_90a)

**Question:** how does the standard wgmma pipeline
(`wgmma.fence` → `wgmma.mma_async`… → `commit_group` → `wait_group`) lower to
SASS, and how is it synchronized?
**Status:** resolved via `tests/wgmma_test.cu`
(`wgmma.mma_async.m64n16k16.f32.f16.f16`), sm_90a.

## PTX → SASS lowering
| PTX | SASS | pipe |
|---|---|---|
| `wgmma.fence.sync.aligned` | **`WARPGROUP.ARRIVE`** | mio |
| `wgmma.mma_async…` | **`HGMMA.64x16x16.F32`** (`IGMMA/BGMMA/QGMMA` for other types) | mio |
| `wgmma.commit_group.sync.aligned` | **(no instruction)** — folded into the group scoreboard writes | — |
| `wgmma.wait_group.sync.aligned N` | **`WARPGROUP.DEPBAR.LE gsb0, N`** | mio |

Observed sequence (accumulator `d[8]` = R24..R31):
```
WARPGROUP.ARRIVE                              wr_sb=7 req=0     # fence
...
HGMMA.64x16x16.F32 R24, gdesc[UR4], RZ,  …    wr_sb=7 req=0     # 1st (scaleD=RZ: no accum)
HGMMA.64x16x16.F32 R24, gdesc[UR4], R24, …    wr_sb=7 req=0     # 2nd (accumulate onto R24)
WARPGROUP.DEPBAR.LE gsb0, 0x0                 wr_sb=7 req=0     # wait_group 0
STG.E … R24                                                     # safe to read accumulators
```

## The two dedicated GMMA scoreboards
wgmma does **not** use the 6 general scoreboards (`SB0–5`) for its own
synchronisation, nor the `usched` stall model — `HGMMA`/`WARPGROUP.*` all show
`wr_sb=7`, `req=0`. Instead there are **two separate GMMA scoreboard resources**
(`sm_90_latencies.txt`):

**1. `GMMA_SCOREBOARD` — the accumulator fence.**
- Writer: `WARPGROUP.ARRIVE` (`OP_WARPGROUP[MODE_ARV]`) and `WARPGROUPSET`.
- Reader: `HGMMA` (and `OP_WARPGROUP[MODE_ARV_WAIT]`).
- `TABLE_TRUE(GMMA_SCOREBOARD) = 6`.
- Role: `wgmma.fence` publishes "the accumulator registers are now consistent and
  reserved for async writes"; each async `HGMMA` waits on it before touching the
  accumulators. This is what **protects the accumulator GPRs** — it orders any
  prior use of those registers ahead of the async MMA that will overwrite them.

**2. `GMMA_GROUP_SCOREBOARD` — the commit/wait counter.**
- Writer: `HGMMA[GSB0]` (each async MMA bumps the group counter) and `WARPGROUPSET`.
- Reader: `WARPGROUP.DEPBAR.LE` (`OP_WARPGROUP[MODE_DEPBAR]`, `mode==2`) and
  subsequent `HGMMA[GSB0]`.
- `TABLE_TRUE(GMMA_GROUP_SCOREBOARD) = 3`.
- Role: counts outstanding wgmma groups; `WARPGROUP.DEPBAR.LE gsb0, N`
  (= `wait_group N`) blocks until `≤ N` groups remain. `commit_group` needs no
  instruction — the group boundary is implicit in the HGMMA group-scoreboard
  writes, and `wait_group N` carries the `gsbcnt` directly.

## Fields
- `WARPGROUP` opcode `0x9c5` (mio). Sub-forms via the `mode` modifier:
  `ARRIVEONLY_syncs` → `WARPGROUP.ARRIVE`; `DEPBARONLY` + `LEONLY` + `GSB0ONLY` +
  `UImm(3):gsbcnt` → `WARPGROUP.DEPBAR.LE gsb0, gsbcnt`.
- `gsbcnt` is **3-bit** (0–7) — narrower than `DEPBAR`'s 6-bit `cnt`, since only a
  few wgmma groups are ever outstanding.
- `HGMMA` (`0x…`, mio) reads a **descriptor** `gdesc[URn]` (uniform-register
  shared-memory matrix descriptor) + accumulator GPRs + `scaleD` (RZ = overwrite,
  else accumulate).

## Comparison to the other sync mechanisms
| mechanism | producer marks | consumer waits | counter unit |
|---|---|---|---|
| fixed-latency (FADD…) | — | — (usched stall) | — |
| general scoreboard (LDG) | `dst_wr_sb` | `req_bit_set` (==0) | per-op, 6 SBs |
| cp.async | `LDGDEPBAR` (commit) | `DEPBAR.LE SBn, k` | **groups**, general SB |
| **wgmma** | `HGMMA` (group SB) | `WARPGROUP.DEPBAR.LE gsb0, N` | **groups**, dedicated GMMA-group SB |
| **wgmma accumulator** | `WARPGROUP.ARRIVE` (fence) | `HGMMA` | dedicated GMMA SB |

So wgmma mirrors the cp.async group-counting idea (`commit`/`wait_group N` ≈
`LDGDEPBAR`/`DEPBAR.LE`) but on a **dedicated** GMMA-group scoreboard, and adds a
second dedicated scoreboard (`GMMA_SCOREBOARD`) driven by `WARPGROUP.ARRIVE` to
fence the accumulator registers — neither consumes the scarce 6 general SBs.

## Accumulator grouping: same vs different (`tests/wgmma_acc_test.cu`)

How the SASS changes when several `wgmma.mma_async` in one commit group write the
**same** accumulator vs **two different** accumulators (matched 2-MMA cases):

**(a) same accumulator** — `MMA(d); MMA(d);`
```
WARPGROUP.ARRIVE                              # 1 fence
HGMMA R24, gdesc[UR4], RZ, !UPT               # 1st (scaleD=RZ, no accumulate)
HGMMA R24, gdesc[UR4], R24, gsb0              # 2nd accumulates; ONLY the last writes gsb0
WARPGROUP.DEPBAR.LE gsb0, 0x0                 # 1 wait
```

**(b) two accumulators** — `MMA(d0); MMA(d1);`
```
WARPGROUP.ARRIVE                              # fence per accumulator group…
WARPGROUP.ARRIVE
HGMMA R24, gdesc[UR8], RZ, !UPT, gsb0         # d0 -> R24, writes gsb0
WARPGROUP.DEPBAR.LE gsb0, 0x0                 # (compiler-injected, ptxas note C7517)
WARPGROUP.ARRIVE
HGMMA R32, gdesc[UR8], R32, gsb0              # d1 -> R32, ALSO writes gsb0
WARPGROUP.DEPBAR.LE gsb0, 0x0                 # wait
```

Differences:
- **Same accumulator** → the HGMMAs form one **dependent chain** (each reads+writes
  the same GPRs). They are ordered by the in-order tensor pipe, so **only the last
  HGMMA writes the group scoreboard** (`gsb0`) and a **single fence + single wait**
  suffice — the in-order-queue economy again (cf. `scoreboards.md` §5).
- **Different accumulators** → two **independent lifetimes**. **Each accumulator
  group needs its own `WARPGROUP.ARRIVE` fence** before its first async write, and
  **every HGMMA writes `gsb0`** so each is individually tracked; ptxas also injects
  intermediate `WARPGROUP.DEPBAR.LE` to gate register reuse (ptxas info **C7517**:
  "wgmma.wait_group is injected … to allow use of registers defined by GMMA").
  Net: more fences and more waits.

Take-away: one accumulator = one fence/wait with a single tail group-scoreboard
write; N independent accumulators = N fences and N group-scoreboard writes, with
the compiler serialising/tracking each. Real GEMMs therefore accumulate a K-loop
into **one** large accumulator (case a) to minimise sync, and only split
accumulators when output tiling forces it. (The heavy fence/wait duplication above
is partly ptxas being conservative with the artificial inline-asm liveness.)

### Same accumulator, changing inputs (K-loop) — `tests/wgmma_acc2_test.cu`
Four MMAs into the same `d[8]` but with **different** descriptors each iteration:
```
WARPGROUP.ARRIVE
HGMMA R24, gdesc[UR4], RZ, !UPT          # k=0
  UIADD3 UR4, UR10, 0x800 ; ULOP3 ; USHF…  # recompute A/B descriptors for k=1
HGMMA R24, gdesc[UR4], R24               # k=1
  UIADD3 UR4, UR10, 0x1000 ; …             # descriptors for k=2
HGMMA R24, gdesc[UR4], R24               # k=2
  UIADD3 UR4, UR10, 0x1800 ; …
HGMMA R24, gdesc[UR4], R24, gsb0         # k=3 (last writes gsb0)
WARPGROUP.DEPBAR.LE gsb0, 0x0
```
The **sync skeleton is identical** to the constant-input case — one fence, a
chain of HGMMA on R24, only the tail writes `gsb0`, one wait. The only addition is
a block of **uniform-datapath** ops between MMAs that rebuild the matrix
descriptor (`UIADD3` advances the shared-memory tile address, `ULOP3.LUT`/`USHF`
pack it into the descriptor's `>>4` / swizzle layout). So "different inputs"
costs descriptor arithmetic on the `udp` pipe, not extra tensor-sync.

### Large-n accumulator (multiple register groups) — `large_n64`
`wgmma.m64n64k16.f32` needs 32 accumulator regs/thread (4 groups of 8):
```
WARPGROUP.ARRIVE
HGMMA.64x64x16.F32 R24, gdesc[UR4], RZ, !UPT, gsb0   # writes R24..R55 (all 32)
WARPGROUP.DEPBAR.LE gsb0, 0x0
```
A large accumulator is **still one HGMMA instruction** — it writes the whole
contiguous register block `R24..R55` (confirmed by the store range). The multiple
8-register "groups" are internal to the instruction's shape field, not separate
instructions, and the fence/commit/wait structure is unchanged. The only effect
of a bigger `n` is that register allocation reserves a larger aligned contiguous
block for the accumulator; instruction scheduling and synchronisation do not
change. (Splitting into multiple HGMMA only happens when *you* write multiple
distinct accumulators — case b above.)

## Architectural model: the accumulator lives inside the tensor core

The observations above are all explained by one model: **Hopper's tensor core
holds the wgmma accumulator in dedicated internal storage (an accumulator
collector), not in the general register file, for the duration of a chain to the
same target.** The `Rd` register name is the *architectural* handle; the running
sum only materialises to the RF on a drain.

Evidence:
1. **Chained same-accumulator wgmma need no inter-instruction wait** despite a
   textbook RAW on `R24` (each reads `R24` as C and writes `R24` as D). If the
   intermediate landed in the RF, each next HGMMA would have to wait on a
   scoreboard for the prior write-back — it does not. The partial sums are
   forwarded **inside** the tensor core; only the *last* HGMMA writes the group
   scoreboard.
2. **A non-tensor read of the accumulator mid-chain forces a drain**
   (`tests/wgmma_acctc_test.cu`). Inserting `x = d[0]*2+1` between MMAs makes
   ptxas emit, per MMA: `HGMMA … gsb0` → `WARPGROUP.DEPBAR.LE gsb0,0` (drain to
   RF) → `WARPGROUP.ARRIVE` (re-fence). The `FFMA`/`FADD` that reads the
   accumulator can only run **after** a `wait_group` — i.e. the value is not in
   the RF until the tensor core is drained (ptxas note **C7517**: wait injected
   "to allow use of registers defined by GMMA").
3. **Resuming accumulation after such a read needs a re-`fence`** — because the
   normal FFMA just accessed the RF copy, `WARPGROUP.ARRIVE` must re-establish
   that the register range is owned by the async accumulator engine.

This directly explains the earlier findings:
- **Why the fence exists** (`wgmma.fence` → `WARPGROUP.ARRIVE`): it orders any
  prior RF accesses to the accumulator registers against the async tensor-core
  write-back, i.e. it hands the register range over to (or reclaims it for) the
  internal accumulator. Needed at the start and after any non-tensor touch.
- **Why switching accumulators costs extra sync**: the collector holds one
  running accumulator target; alternating `d0`/`d1` forces materialise-and-reload
  (drain + re-fence) at each switch — exactly the extra fences/waits seen in the
  two-accumulator test.
- **Why a K-loop into one accumulator is cheap**: the sum stays resident inside
  the tensor core across all iterations; the RF is written once at the final
  `wait_group`.

Caveat: this is an *observationally consistent* model — the SASS cannot prove a
physically separate SRAM vs a deferred/async-RF-writeback microarchitecture. But
"internal accumulator, drained on read" predicts every scheduling change we see
(no inter-chain wait, drain-on-read, re-fence-on-resume, switch penalty), which a
plain async-RF model does not (it would require a scoreboard wait between chained
MMAs).

## Multi-warpgroup: HGMMA control codes & the "contiguous batch" model

**Question:** with several warpgroups doing wgmma at once, how is the tensor core
shared, and can cross-warpgroup accumulator state be corrupted? (Rumor: >3
warpgroups → random fp precision loss.)

### HGMMA control-code signature (`query_sm90.py layout hgmma_URa_Rc_`)
| field | bits | value |
|---|---|---|
| `src_rel_sb` | [115:113] | **7 (pinned)** — no read scoreboard |
| `dst_wr_sb` | [112:110] | **7 (pinned)** — **no general write scoreboard** |
| `req_bit_set` | [121:116] | input waits only (e.g. on the LDGSTS/TMA/LDG that filled shared) |
| `gsb` (`cop`) | [86:84] | GMMA group scoreboard selector — only `gsb0` valid (single) |
| `opex`/`usched` | [124:122]∥[109:105] | normal `TABLES_opex_0(batch_t,usched_info)` |

So HGMMA's *completion* is never tracked by the 6 general scoreboards — only by
the **dedicated, single** `GMMA_SCOREBOARD` (fence, latency 6) and
`GMMA_GROUP_SCOREBOARD` (`gsb0`, latency 3), which are per-warp resources. The
general SBs are used purely for HGMMA's *inputs*.

### Stall / yield pattern (decoded across the tests)
- **Every HGMMA: `stall 3–4`, `bit4=1` (transN, non-yielding).** After dispatching
  an async MMA the warp waits only 3–4 cycles and **keeps issuing the same
  warpgroup's next HGMMA** — it does not request a warp switch between MMAs.
- **`WARPGROUP.DEPBAR.LE` (wait_group) and `WARPGROUP.ARRIVE` (fence): often
  `bit4=0` (WnEG) / low DRAIN** — the warp yields *at the wait/fence*, not between
  MMAs.

**Interpretation (supports the single-queue / contiguous-batch model).** The
transN codes bias the scheduler to keep a warpgroup's whole HGMMA chain issuing
**contiguously** (no yield between MMAs); the warp only yields when it blocks on
the tensor core at `wait_group`. So different warpgroups tend to feed the shared
tensor core as **contiguous per-warpgroup batches**, separated by their
wait/fence yields, rather than finely interleaving MMA-by-MMA. Dispatch is cheap
(3–4 cyc) and decoupled — the warp never waits on the MMA's execution latency
(that is hidden behind the GMMA scoreboard). This is a scheduling *tendency* from
the control codes, not a hardware guarantee of zero interleave.

### `WARPGROUP.ARRIVE` is a cross-subcore barrier (BRU-routed)
All three `WARPGROUP.*` ops carry a **branch/convergence-barrier-unit** type:
- `WARPGROUP.ARRIVE` : `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`
- `WARPGROUP.DEPBAR` / `WARPGROUP.WAIT` : `..._BRU_DEPBAR_RD_NOREQ_SCBD`
all with `VIRTUAL_QUEUE = $VQ_UMMA`. The **BRU** is the same unit that implements
warp convergence and named barriers (`BSYNC`/`BSSY`/`BAR`), not the plain MIO
scoreboard path. So `wgmma.fence` → `WARPGROUP.ARRIVE` is a **barrier-class**
operation, not just a scoreboard write.

Architecturally a warpgroup's 4 warps are distributed one-per-subcore across the
SM's 4 subcores (each subcore has its own tensor core computing a 16×N slice — the
"16×N accumulator per subcore"). Because `WARPGROUP.ARRIVE` runs on the BRU, it
**synchronizes the warpgroup's 4 warps across the 4 subcores**: it rendezvouses
all four subcore schedulers onto the *same* warpgroup before its wgmma group
starts (and `WARPGROUP.WAIT`/`DEPBAR` again at the end). This is exactly the
mechanism that makes the contiguous-batch model hold: the ARRIVE barrier aligns
the four subcores on one warpgroup, they issue that warpgroup's HGMMA chain in
lockstep and non-yielding (transN), then rendezvous again at the wait — so a
warpgroup's wgmma occupies the tensor core(s) as one coherent, subcore-aligned
batch rather than four subcores drifting onto different warpgroups. The observed
`WnEG`/yield on `ARRIVE`/`WAIT` (vs transN on HGMMA) is consistent: the warp
yields *at the barrier* while waiting for its peers, not between MMAs.

### Empirical hazard probe (`tests/wgmma_hazard*.cu`, H800, CUDA 12.8)
Bit-exact comparison of each warpgroup's accumulator against its isolated
1-warpgroup reference, with **different random fp8 data per warpgroup** (so any
cross-warpgroup contamination shows as a bit difference):

| config | checks | mismatches |
|---|---|---|
| fp8 n16, wgs 1–8, M≤256 | ~1.5e8 | **0** |
| fp8 n128 (16×128 acc), wgs 1–6, M≤128 | ~6.7e8 | **0** |

**No hazard reproduced** up to 8 warpgroups / large accumulators / ~10⁹ checks.
(An earlier "hazard" at wgs≥2 was a *test artifact* — a crude descriptor
over-reading into the neighbour warpgroup's shared slice; isolating fully-filled
slices removed it entirely.) Consistent with: each warpgroup's accumulator is
register-resident and private, the GMMA scoreboards are per-warp, and the
contiguous-batch issue tendency avoids fine-grained context thrash. The rumored
">3 warpgroups → precision loss" is most plausibly a *software* mis-sync
(missing `wgmma.fence`/`wait_group`, which ptxas otherwise auto-injects — C7517/
C7519), not a hardware hazard, at least on this H800 + CUDA 12.8.

## Contrast with synchronous HMMA
`HMMA` (warp-level `mma.sync`, `hmma_pipeline.md`) is fixed-latency: stall
counts + dead `@!UPT UIADD3` fillers cover its ~28-cyc latency. `HGMMA` (warpgroup
`wgmma.mma_async`) is **asynchronous**: it returns immediately and its completion
is tracked by the GMMA group scoreboard, waited on explicitly by
`WARPGROUP.DEPBAR.LE`.

## Open questions
- Whether `wgmma.commit_group` ever emits a distinct op (e.g. `WARPGROUPSET`) in
  multi-stage pipelines, vs always folding into the HGMMA group-SB writes.
- Exact `WARPGROUP.ARRIVE` placement policy (it is scheduled early, before the
  descriptors are fully built) and how the fence orders accumulator reads.

## H20 empirical verification (2026-08, hand-written SASS via `assembler/`, sm_90)

Experiments in `/root/sass90/exp/` (H20, driver CUDA 13.x) against the claims
above. Kernel derived from `test_hgmma_full.py` (nvcc HGMMA skeleton).

**Confirmed:**
1. **Lowering** (CUDA 12.8 nvcc re-check): 1 `WARPGROUP.ARRIVE`, first HGMMA
   `RZ, !UPT` (scaleD=false), 15 chained `R24` accumulates, tail `gsb0`, one
   `WARPGROUP.DEPBAR.LE gsb0, 0` — exactly the skeleton above.
2. **Chained same-accumulator HGMMAs need no inter-MMA wait** — 16 chained
   MMAs, only tail gsb0, single DEPBAR: bit-exact (0/1024 bad).
3. **`DEPBAR.LE gsb0,N` = wait until ≤N groups outstanding; completion is
   strictly in-order.** 8 MMAs (each gsb0, distinct accumulators, sentinel
   1000.0, 64 trials): thresh=6 → acc0/acc1 100% fresh, acc2 racy (17%),
   acc3..7 always stale; thresh=4 → acc0..3 fresh, acc4 ~50%, rest stale.
   The guaranteed-complete accumulators are always the FIRST issued ones.
4. **Reading the accumulator without DEPBAR is stale** — FADD read right after
   HGMMA+gsb0: 1024/1024 stale (sentinel). STG right after: 608/1024 stale
   (STG's late data read catches some completions).
5. **scaleD**: `…, RZ, !UPT` → D=A×B overwrite (preset 1000.0 ignored);
   `…, {R}, UPT` → accumulate.
6. **Interleaved accumulators are correct with a single ARRIVE** — alternating
   2 or round-robin 4 accumulator groups, no per-switch fence/wait: bit-exact.
7. **Multi-warpgroup**: 4 warpgroups × own A/B slices × 16-MMA chains:
   0/4096 bad, max rel err 2e-6. No "precision loss" on H20 either.

**Refuted / refined:**
1. **"Switch penalty" does not exist at the hardware level.** 513-MMA loops:
   chain-1-acc = rr-2-acc = rr-4-acc = **32.49 cyc/MMA identical**. The extra
   fences/waits ptxas emits for multi-accumulator code are pure conservatism.
2. **"Running sum only materialises to the RF on a drain" is WRONG** — after
   ~2000 NOP cycles with NO DEPBAR, RF reads are 1024/1024 fresh. The RF is
   written back **asynchronously at MMA completion**; `WARPGROUP.DEPBAR.LE`
   is a pure wait, not a drain trigger. This selects the note's
   "deferred/async-RF-writeback" alternative over the strict collector model.
 3. **Writeback is an additive RMW, not a computed-value store.** A `MOV32I`
    overwrite of the accumulator mid-chain (after 1st MMA, before 2nd) yields
    deterministically `MOV32I_value + Σ(all AB deltas)` — the original base
    (1.0) vanishes entirely, the new RF value is adopted as the base. Model:
    ~~each accumulating HGMMA queues its A×B into an internal delta collector~~
    each HGMMA carries its own A×B delta in-pipe and performs
    `RF := RF_now + delta` per register **at its own completion** (refined in
    Round 3 — no collector exists; the MOV32I simply lands before the first
    MMA's RMW and every later RMW piles on top).
    A second `WARPGROUP.ARRIVE` does NOT flush pending deltas (same result).
    (Post-MMA / pre-DEPBAR overwrite is racy per-register: 648 lanes
    `7+2ref`, 256 `1+2ref`, 120 torn — consistent with per-register RMW.)
4. **`WARPGROUP.ARRIVE` is not a hard requirement on H20.** Omitting it
   entirely: correct. Skewing warp 0 by ~10k cycles before an unfenced chain:
   correct — the warpgroup is (re)aligned by the HGMMA issue path itself.
   ptxas's conservative fence/wait injection (C7517/C7519) remains the safe
   contract, but the hardware tolerates far sloppier SASS.

**H20 throughput (SR_CLOCKLO, loop amortised):**
| shape | cyc/MMA | FLOP/cyc/SM | note |
|---|---|---|---|
| m64n16k16 bf16 | 32.4 | ~1011 | ≈100% of H20 TC peak (148 TFLOPS ⇒ 1024 FLOP/cyc/SM @78 SM, ~1.85 GHz) |
| m64n64k16 bf16 | 128.7 | ~1018 | exactly 4× n16 — peak scales with FLOPs |
| m64n16k16, 2 warpgroups | 64.9 each | ~1010 aggregate | TC is shared; no per-wg throughput gain |

**Side findings:**
- ISETP→`@P0 BRA` (INT/FE→CBU) needs **stall ≥ 13**; at ≤12 the branch reads
  a stale predicate (loop degenerates to 1 iteration). Yield bit
  (transN vs WnEG) is irrelevant to this hazard. (Matches nvcc's `13:1`.)
- One 715 (`ILLEGAL_INSTRUCTION`) poisons the CUDA context for the whole
  process — later module loads fail too. Isolate faulting experiments into
  their own processes.
- The assembler's explicit-register-group rule now extends to wide MMA
  accumulators: `{R24,…,R55}` (32 regs) etc. (16/32/64/128) for
  `HGMMA.64x64x16`+ — verified on hardware.

## Round 2 — writeback trigger, latency, commit capacity (H20, 2026-08)

> **Round 3 (below) retracts three of these findings** — "commit-tracking
> capacity ~35", "retired accumulator", and "back-to-back commit loss" were
> all artifacts of the STG source-register late-read hazard. The latency,
> trickle, and throughput measurements stand.

**The writeback model** (supersedes "drain on read" and the plain
"async RF writeback" phrasing above; refined after follow-up probes):
- ~~The tensor core keeps a single **in-order delta stream** per warpgroup.~~
  **RETRACTED (Round 3)**: there is no delta stream/collector; each HGMMA
  RMWs its own delta at its own completion. The `noGsb(acc0), gsb0(acc1)`
  observation (acc0's delta lands) is equally explained by per-MMA writeback
  at completion — gsb0 plays no role in data movement.
- A `gsb0`-marked HGMMA (a) bumps the group counter and (b) ~~on completion,
  **flushes all pending deltas up to and including itself**~~ — **RETRACTED**:
  nothing is pending; the writeback happens per-MMA at completion.
- ~~**An accumulator that was already committed is "retired": a later
  un-committed HGMMA on it NEVER writes back**~~ — **RETRACTED (Round 3,
  exp13/T2)**: trailing no-gsb MMA writes back normally (1024/1024 lanes =
  2×ref after +500 cyc). The original +2000-cyc × 6-reps experiment was
  corrupted by the STG/re-init hazard.
- **A never-committed accumulator**: a no-gsb HGMMA on a fresh accumulator
  writes back at its own completion, no commit needed — **CONFIRMED** and
  generalised: this is simply what every HGMMA does (Round 3).
- ~~Boundary races exist: back-to-back gsb0 commits on the SAME accumulator
  lose one delta deterministically~~ — **RETRACTED (Round 3, exp13/T3)**:
  back-to-back same-acc commits are lossless at any post-DEPBAR delay
  (1024/1024 lanes = 2×ref). Also an STG-hazard artifact.
- Writeback **is** an additive RMW, not a computed-value store — **CONFIRMED**
  (the MOV32I-mid-chain experiment below remains valid and becomes the key
  evidence for the Round-3 model).

**Completion latency & the writeback trickle (m64n16k16, DEPBAR-timed):**
- t(1 MMA) ≈ 57 cyc; t(k chained) slope = 33 cyc/MMA (n64: 81/144; n256: 177/552).
- Without any DEPBAR, RF lanes flip fresh over a **~40-cycle window**:
  first lane fresh ~15 cyc after issue, all 8 lanes by ~55 cyc.
- Writeback order ~~is **high register → low register** (R31 first, R24 last),
  ~1 reg per 4-5 cyc~~ — **RETRACTED (exp16)**: the apparent direction was a
  store-issue-order artifact. Single-STG probes stored lanes in ascending
  order and "saw" 7→0; storing in descending order flips the observation to
  0→7 — the fresh-lane order always follows the *store* order (later-issued
  STGs read later), never the lane index. The "~40-cyc window" was likewise
  just the 8×~4-cyc STG sequence. What survives: the t(1) scaling
  (57/81/177 cyc for n16/n64/n256 = **~49 cyc fixed + ~1.0 cyc/reg**), which
  is DEPBAR/scoreboard-timed and read-order-free — there is a per-register
  serial component of ~1 cyc/reg in the completion path (drain or pass
  pipeline), but its **direction is below measurement resolution** and there
  is no evidence the drain order interacts with the MMA's internal
  column-pass order (k-dim partial sums live in the engine's accumulator
  cells and never map to registers anyway).

**Shape scaling (m64nNk16 bf16, 513-MMA chains):** cyc/MMA ≈ 2N (+~2 fixed):
n8 18.1, n16 32.5, n32 64.7, n64 128.7, n128 255.4, n256 504.9 →
**1010-1040 FLOP/cyc/SM** flat = the TC datapath cap. Per subcore that's
**128 MAC/cyc** (H100 has 512; H20 is a 4×-cut tensor core).
The HGMMA scheduling stall (1..7) makes **zero** difference — dispatch is
fully hidden behind the TC queue.

**Commit-tracking capacity:** ~~**~35 outstanding gsb0 groups.**~~ **RETRACTED
(Round 3, exp11v3)** — the K=36..64 "permanently lost deltas" were the STG
source-register late-read hazard (see Round 3): the phase stores' data
registers were overwritten by the next round's re-init MOV32Is before the
deeply-queued STGs sampled them. With proper `rd:SBn` + `DEPBAR.LE SBn`
protection, K up to 128 is bit-exact for every shape (n8..n128). The
"~36-entry TC input queue" inference drawn from K=36 is likewise void —
no capacity limit of any kind was observed (exp12: 31-deep uncommitted
chains per accumulator × 8 accs, and 28 concurrent accumulators = 56 KB of
n16 accumulator footprint, both bit-exact at flat 32.5 cyc/MMA).

**Async decoupling:** 2048-instr FFMA stream + 513-MMA chain:
T_both == T_mma exactly (100% overlap) — the tensor path is fully decoupled
from the FP32 pipe.

**2-warpgroup interleave:** timestamps every 8 MMAs show both warpgroups
progressing **concurrently and roughly uniformly** (~58-67 cyc/MMA each,
max pause ~1μs-scale bursts, no full-stop batching) — on H20 the TC time-slices
warpgroups at fine grain rather than running strict contiguous batches; the
transN control-code "tendency" is not a hard batching guarantee.

## Round 3 — corrected writeback model (H20, 2026-08; exp11v3/exp12/exp13)

All "lost delta" phenomena from Round 2 trace back to one **generic MIO
hazard, unrelated to the tensor core**:

**The STG source-register late-read hazard.** An STG samples its data
register when the instruction reaches the head of the LSU/MIO pipe, not at
issue. With ~60 queued STG.E.128s the last group's sample lags issue by
hundreds of cycles; any rewrite of the source register in that window
(hand-written kernels without the `rd:SBn`/`wr:SBn` interlock — ptxas always
emits it) silently stores the NEW value. Signature: the stored value equals
a later overwrite exactly. Proven decisively: phase-1 stores read 2000.0
after a re-init wrote 2000.0 (128/128 threads, only the LAST store group,
the deepest in the queue). Fix: give the STGs `rd:SB5` and insert
`DEPBAR.LE SB5, 0` before any rewrite of the stored registers → 0 bad.
This one hazard produced the phantom "K=36 capacity", "retired accumulator",
and "back-to-back commit loss" findings (all retracted above).

**The corrected writeback model** (supersedes the collector/flush/retire
narrative; everything below verified with SB-protected stores):

1. **Each HGMMA carries its own delta δ = A·B through the tensor pipe and
   performs a per-register RMW at completion**: `RF_lane := RF_lane + δ_lane`.
   δ lives only inside the pipe for that MMA's own lifetime — there is **no
   delta collector, no commit-flush, no retire state, no capacity limit**.
   The accumulate/overwrite distinction is exactly the P flag (scaleD):
   accumulate = RMW, `P=false` = plain store of A·B. Evidence:
   - MOV32I overwrite mid-chain (Round 2 item 3): final = MOV_value + Σ(ALL
     deltas) — the MOV lands before the first MMA's RMW and every RMW piles
     on top. Only per-completion RMW explains the vanished original base.
   - exp12 depth sweep: d = 1..32 uncommitted MMAs per acc (M=8, K≤256),
     final-round commits only: bit-exact vs the fully-drained reference at
     every depth, flat 32.5 cyc/MMA. Per-delta storage would need 496 KB.
   - exp12 width sweep: M = 2..28 concurrent accumulators (footprint up to
     56 KB of n16 tiles / 28 KB of n8 tiles), d=3: bit-exact, flat
     throughput (n16 ~33, n8 ~20 cyc/MMA). No byte limit, no entry limit.
2. **The writeback has a per-register serial component of ~1 cyc/reg** —
   from t(1) = 57/81/177 cyc for n16/n64/n256 = **~49 cyc fixed + 1.0×nregs**,
   which is DEPBAR/scoreboard-timed and free of read-order bias. ~~The RMW
   trickle is lane-serial, highest register first~~ — **RETRACTED (exp16)**:
   the apparent high→low drain order was a store-issue-order artifact of the
   single-STG probes (descending stores flip the observation to low→high);
   the drain direction is below measurement resolution and probably
   architecturally irrelevant. Unsynced reads (no gsb0/DEPBAR) do race the
   writeback — but what they race is a ~1-cyc/reg completion path, not a
   ~40-cyc high→low trickle.
3. **gsb0 is a pure scoreboard; it releases only after the writeback has
   fully landed.** Post-DEPBAR immediate stores of the just-completed acc
   are 100% coherent — every lane fresh, zero delay needed (exp13/T3).
   DEPBAR.LE gsb0,N therefore fully synchronizes RF readers; the only way
   to observe the trickle is to read WITHOUT the scoreboard.
4. **gsb0 has no effect on data movement.** Same-acc back-to-back commits:
   lossless at any delay (exp13/T3, 1024/1024 = 2×ref). Trailing no-gsb
   MMA after a commit: writes back normally (exp13/T2). Commits neither
   flush nor gate anything — they only count groups for DEPBAR.
5. **No commit-group capacity limit.** K = 128 chained gsb0 MMAs,
   round-robin 8 accs, all shapes n8..n128: bit-exact vs both the
   fully-drained reference and the exact CPU ref (exp11v3). PTX's
   `commit_group`/`wait_group` discipline remains the correct contract,
   but H20 hardware imposes no outstanding-group bound we could reach.

**Open microarch questions that survive Round 3:**
- Where δ lives in-pipe (per-MMA pipeline registers vs a small forwarding
  network) and how the RMW arbitrates the RF write port with FFMA/IADD
  traffic — **answered (H800, `register_bandwidth.md`)**: the RMW shares
  the RF ports with ALU traffic; a 3-fresh-reads FFMA storm (~960 B/cyc/SM
  of RF reads, saturating the ~250 B/cyc/SMSP read budget) starves it and
  slows an n16 chain 21.5 → 52 cyc/MMA. Reuse-cached FFMA at the same
  issue rate causes almost no contention.
- Same-acc chained MMAs (~33 cyc apart) never corrupt each other: each
  RMW must be ordered/atomic against the previous one — presumably
  guaranteed by in-order completion within a warpgroup.
- Whether the scoreboard release waits the full trickle or is itself
  trickle-aligned (post-DEPBAR reads are always clean, so the release is
  at/after the last lane's write).

**TC input-queue depth: ~5-7 outstanding MMAs, entry-limited, acc-agnostic
(exp14).** Clocking the *issue burst* itself (before any DEPBAR): the issue
slope is ~4.2 cyc/MMA while the queue absorbs MMAs, then snaps to the
completion rate (2N) at K* ≈ 7 (n8) / ≈ 5 (n16, n64). Nearly shape-invariant
knee ⇒ the queue holds **command entries, not tiles** (byte-limited would
put n8's knee ~8× later than n64's). Identical knee for same-acc chains and
8-acc round-robin ⇒ queue entries carry **no per-accumulator state** — more
evidence against any internal per-acc accumulator. Overflow manifests as
**issue backpressure** (the warp stalls; steady-state slope = completion
rate), never as data loss — the accumulation state is in the RF. The voided
"~36-entry queue" inference (from the K=36 artifact) is replaced by these
measured ~5-7 entries. Practical headroom: 5-7 outstanding × ~33 cyc ≈
~200 cyc of run-ahead, which is why `commit_group`/`wait_group` discipline
never throttles real GEMM K-loops.

## Round 4 — the ptxas wgmma-DCE trap; sustained throughput is plain MAC-bound (H20, 2026-08; nvcc variant chains)

**ptxas dead-code-eliminates `wgmma.mma_async` when the kernel never
writes shared memory.** If every smem byte a descriptor could point at is
unwritten, ptxas treats the A/B tiles as *undef* and silently drops MMAs
from a chained accumulator sequence: a 64-iteration `#pragma unroll` loop
of textually identical `wgmma.mma_async` (same descs, serial accumulator)
compiles to **50 SASS HGMMAs** (bf16 f32-acc n16), **35** (f16 f16-acc
n16), 50 (fp8 k32), 50 (A-reg). PTX is straight-line 64; SASS is not.
Adding *any* smem store before the chain (even a single token write)
restores exactly K HGMMAs (`dce_test.cu`: k_nofill=50 vs k_write=64;
numerics exact: ones matrices → d = 16·64 = 1024.0). Consequences:
- Every nvcc-compiled timing chain that reads unwritten smem measures
  **fewer MMAs than the source says** — all cross-kernel cyc/MMA
  comparisons must use the SASS instruction count, never the loop bound.
- Kernel *results* are equally wrong (d reflects the culled count), but
  since undef smem is UB anyway, this only bites microbenchmarks, not
  real kernels (which always fill their tiles).
- This artifact, not any hardware effect, produced the "fill_test 25%
  slower than variants_test" mystery and everything chased in its wake
  (code layout, dead-code presence, BAR, branch targets, ICache,
  globaltimer/DVFS): fill kernels wrote smem (64 real MMAs → 33.7/MMA),
  the variants kernels didn't (50 real MMAs → spurious "26.9/MMA").

**Renormalized sustained rates** (`sweep_test.cu`: smem always written,
verified K HGMMAs each, K = 16/32/64/128 sweep, wall = max(t2)−min(t0),
fixed cost F ≈ 110 cyc):

| variant | R (cyc/MMA) | MACs/MMA | MAC/cyc/SM |
|---|---|---|---|
| bf16 k16, f32 acc | 32.4 | 16384 | 506 |
| f16 k16, **f16 acc** | 32.4 | 16384 | 506 |
| **fp8 k32**, f32 acc | 32.4 | 32768 | 1011 |
| bf16 k16, **A from regs** | ~40 (K≤32) | 16384 | ~410 |

1. **Sustained wgmma throughput on H20 is MAC-bound, period.** f16-acc
   (half the accumulator registers) is NOT faster than f32-acc — the
   Round-2-era "accumulator writeback drain drives throughput" model is
   **retracted** (its supporting 19-vs-27 measurement was a DCE-count
   artifact). fp8 k32 does exactly 2× the MACs in exactly the same time,
   i.e. the fp8 MAC rate is exactly 2× the fp16 rate. 506 fp16
   MAC/cyc/SM ≈ H20's dense fp16 TC spec (148 TFLOPS ÷ 78 SMs ÷ 1.98 GHz
   = 479) within ~5%; a chained-MMA loop runs the nerfed H20 tensor core
   at ~100% MAC utilization. Everything else (acc width, k-depth, dtype)
   is irrelevant to sustained rate once MACs/cyc is fixed.
2. ~~**t(1) re-reads cleanly under MAC-bound**: ~57 cyc for one n16 MMA ≈
   32 MAC-cycles + ~25 cyc fixed pipeline latency~~ — **RETRACTED (Round
   5)**: t(1) is identical on H800's 2×-faster-per-chain TC, so it cannot
   contain a MAC-array-speed term; it is fixed pipeline latency + operand
   delivery + writeback tail.
3. **A-from-registers costs ~24%** (~40 vs 32.4 cyc/MMA at K≤32): the
   A-tile RF reads compete with accumulator RMW writeback on the register
   file. At K≥64 ptxas additionally **serializes the wgmma chain**
   (warning C7511: "insufficient register resources for the wgmma
   pipeline"; R degrades to 58-78 cyc/MMA) — a compiler scheduling
    artifact layered on top of the hardware cost. ptxas's own desc-based
    chains (32.4) are also ~4 cyc/MMA slower than an equivalent
    hand-written SASS chain (~28-30); the bracket/control-word difference
    responsible is not yet isolated.

## Round 5 — H800 (full-rate TC) vs H20: the real sustained limiter is the smem operand path (2026-08)

Same experiment suite re-run on an H800 PCIe (114 SMs, sm_90, boost
1755 MHz, 350 W cap). Ground truth from cuBLAS (torch.matmul 8192³):
**531.6 bf16 TFLOPS at a power-throttled 1020 MHz = ~4570 FLOP/cyc/SM ≈
2286 MAC/cyc/SM** — the H800 tensor core is the full Hopper array, ~4×
H20's per-SM rate (H20 = same chip with the TC quartered; measured 506 vs
spec 479 MAC/cyc/SM, ~100% utilized by a single chain).

**wgmma chains on H800 are NOT MAC-bound — they are bound by the smem
operand-delivery path at ~112 B/cyc/SM** (`shape_test.cu`, m64n{8..128}k16
bf16, K=32, verified counts):

| shape | cyc/MMA | MAC/cyc/SM | operand B/cyc |
|---|---|---|---|
| m64n8k16  | 21.0 | 390  | 109 |
| m64n16k16 | 22.8 | 717  | 112 |
| m64n32k16 | 27.0 | 1212 | 113 |
| m64n64k16 | 35.3 | 1854 | 115 |
| m64n128k16| 67.4 | **1944** | 91 (drops) |

Bytes/cyc is flat ~112 for n8..n64 (smem-path-bound: MAC/cyc scales
exactly with bytes-per-MAC); at n128 the B/cyc *drops* — the crossover
where the TC array itself (~1944-2048 MAC/cyc/SM, 85% of the cuBLAS rate
with a single-accumulator dependent chain) becomes the binding limit.
Corollary: **narrow-N wgmma cannot come near the TC array peak on
full-rate silicon** (n16 reaches 35%); real GEMMs win by using n128-n256
shapes (better MAC/byte ratio) plus TMA + multi-accumulator interleave.
On H20 this entire regime is invisible: its quartered TC (506 MAC/cyc)
binds before the operand path does (n16 needs only 79 B/cyc there).

**Multi-warpgroup (one SM, `mwg_test.cu`, n16k16): aggregate throughput
is flat ~800 MAC/cyc for 1, 2, 3, 4 warpgroups** — wall scales exactly
linearly with total MMAs (21.5 → 81.6 cyc/MMA/wg). The smem operand
path/TC complex is a single SM-wide work-conserving resource fairly
timeshared between warpgroups; one warpgroup already saturates it.

**Everything else is identical between H20 and H800** (same silicon,
same microarchitecture, only the TC width differs):
- No commit-group capacity limit: K≤128, all shapes n8..n128, 0 loss
  (exp11v3; the K=36 exact-ref blip reproduces on H800 → confirmed as
  the exact_check K%M keying artifact, not hardware).
- No collector/flush/retire: depth sweep (32 pending/acc) and width
  sweep (28 accs, 56 KB) bit-exact, flat rate (exp12, bad=0 everywhere).
- **TC input queue: ~7 entries, entry-limited, acc-agnostic** (exp14:
  issue slope ~3.8-4.2 cyc/MMA until knee K*≈7 for n8/n16/n64, M=1 and
  M=8 identical). Slightly deeper than H20's measured ~5 for n≥16 (n8
  was 7 on both). Same burst slope on both chips.
- **Completion latency t(1) is TC-rate-INDEPENDENT: ~53/57/81 cyc for
  n8/n16/n64 on BOTH chips** (exp14 K=1 issue+drain). This kills the
  Round-4 "t(1) ≈ 32 MAC-cycles + 25 latency" reading (a 2× faster array
  does not shorten t(1)): t(1) is dominated by fixed pipeline latency,
  operand delivery (~23 cyc of smem reads for n16), and the writeback
  tail — not by MAC-array speed.
- Writeback race window: unsynced early reads see the stale sentinel
  1024/1024, +2000 cyc → all fresh (exp2_drain, identical); trickle
  visibility window ~40 cyc with the same store-issue-order artifact
  (exp15/exp16: observed lane order follows STG issue order, not an
  architectural drain direction); back-to-back commits lossless
  (exp13 T3 = 2.00×); accumulate = per-completion RMW vs P=false plain
  store (mid_intpipe D = 2×ref exact).
- STG SB-protection discipline required identically (exp11v3 with
  `rd:SB5`+DEPBAR: 0 loss everywhere).

**RF-bandwidth contention (rf2/rf3_test.cu, see `register_bandwidth.md`
for the full dataset):** co-resident ALU traffic can become the dominant
bound on an HGMMA chain. A 3-fresh-register FFMA storm (itself RF-read
-bound at ~0.64 FFMA/cyc/SMSP ≈ the 2R budget, flat 1→4 warps/SMSP)
slows the n16 chain 21.5 → 52.0 cyc/MMA; the same storm with
`.reuse`-cached operands costs only +11%, an equal-shape IMAD storm
under the bandwidth threshold costs +1%. Crucially the penalty is
**flat ~+30 cyc/MMA across n8/n16/n64** (rf3) — independent of
accumulator width — so the RMW does not trickle through the shared 2R
ports per register; each MMA's completion carries a fixed arbitration
step that serializes only when ALU RF reads exceed ~650-700 B/cyc/SM.

## SS vs RS operand modes (ssrs*_test.cu, H800 2026-08)

`wgmma.mma_async` takes A either from a shared-memory descriptor (SS)
or from registers (RS; B is always a descriptor). bf16 m64nNk16,
single warpgroup, same protocol as the sweeps (walls include ~110 cyc
fixed overhead; marginals are per-MMA):

| metric | SS | RS |
|---|---|---|
| completion latency t(1), n16 / n32 | 117 / 125 cyc | **99 / 107 cyc** (−18) |
| burst marginal, n16 K≤8 | 20.3 cyc/MMA | **14.3 cyc/MMA** (−30%) |
| burst wall/MMA, n32 K=8 | 36.1 | **28.6** |
| steady rate, n16 (K=32..128 fit) | 20.0 cyc/MMA | ~22-24 cyc/MMA |
| steady rate, n32 (K=32 wall) | 27.0 cyc/MMA | 26.0 cyc/MMA |
| 2 output tiles sharing one A (16 MMAs each) | 21.8 (ss2_16) | 22.7 (rs2_16) |
| 4 output tiles sharing one A (ss4/rs4_16) | 20.8 | 58.1 (serialized, see below) |

Facts:

- **RS lowers latency, not throughput.** t(1) is ~18 cyc shorter (no A
  smem fetch on the completion path) and the first ≤8 MMAs of a chain
  issue ~30% faster, but the steady-state rate converges to SS's.
- **The RS steady limit is not operand delivery.** In RS mode smem
  traffic halves (B only: 512 B vs 2560 B per n16 MMA) and A's 2 KB
  comes from RF — yet the rate stays ~22-24 cyc/MMA at n16, *worse*
  than SS's 20.0 which is itself smem-path-bound. The limiter is the
  wgmma pipeline's in-flight capacity for register-A MMAs (drain-side),
  not bandwidth.
- **A-register reuse across output tiles does not pay** (at n16/n32):
  rs2_16 ≈ ss2_16 ≈ single-chain rate × 2 tiles. Sharing the A
  *descriptor* across two SS MMAs gives no speedup either (ss2_16 =
  21.8) — the smem path re-fetches A per MMA, no observable caching.
- **C7511 serialization is RS-specific and in-flight-count-driven.**
  Any RS chain with >32 in-flight MMAs (regardless of acc width: n8
  with 4-reg accumulators trips it at K=64 just like n16) is fully
  serialized by ptxas at ~50-58 cyc/MMA — a ~2.5× penalty. SS chains
  of 128 MMAs are never serialized. This is what "insufficient register
  resources for the wgmma pipeline" means: each in-flight RS MMA holds
  an internal staging slot for its A fragment, and the pool is ~32
  deep. Real kernels that use RS must commit/wait in bursts ≤32 (paced
  bursts of 16 restore full speed: 16×2 = 23.7/MMA ≈ steady).
- Practical codegen guidance: use SS for long mainloop chains; RS only
  helps when A reuse spans multiple N-tiles *and* chains stay short —
  on H800 even then it merely matches SS. cuBLAS's preference for SS in
  its big Hopper kernels is consistent with this.

## Accumulator switching & fence discipline (fence_test.cu / exp19, H800 2026-08)

Why does ptxas emit `DEPBAR.LE gsb0` + `WARPGROUP.ARRIVE` around
accumulator-group boundaries, and when is that actually required?

**The ptxas pattern** (self-documented by its own info messages: C7519
"warpgroup.arrive is injected … to allow use of registers **in** GMMA",
C7517 "warpgroup.wait is injected … to allow use of registers **defined
by** GMMA"):
- Fences appear **only at accumulator init/epilogue boundaries, never at
  steady-state group switches**. `interleave_pure` (two independent acc
  groups alternating every MMA): after the setup fences, the whole
  d0/d1 alternation is fence-free.
- `switch_reinit` (chain → epilogue → MOV re-init of the registers →
  new chain): `[chain][last MMA gsb0][DEPBAR][epilogue reads][re-init
  MOVs][ARRIVE][new chain]` — the DEPBAR+ARRIVE pair brackets the
  non-wgmma register accesses.
- One observed over-conservative case: a startup DEPBAR+ARRIVE after the
  first accumulator's first MMA before the second accumulator's first
  MMA (its MOV-init races the first in-flight MMA). One-time ~t(1) cost,
  irrelevant in practice.

**Hardware necessity, per the Round-3 model:**
- **Pure group switches need no fence** (PTX grants default ordering for
  accumulator accesses across same-shape wgmma.mma_async): the issue
  side never reads accumulator registers (RMW happens at completion),
  completion is in-order across the warpgroup regardless of which acc
  group an MMA targets, and the TC input queue carries no per-acc state.
  Verified bit-exact: exp19/E2a (2 groups × 32, single fence) and the
  earlier 8-group round-robins (exp11v3/exp12).
- **Re-initialization is different — DEPBAR is hardware-mandatory**:
  in-flight RMWs from the pre-re-init MMAs race the re-init MOVs in both
  directions (E4a: without DEPBAR the result is neither `MOV + old` nor
  `MOV + new` but per-lane nondeterministic garbage from partial RMW
  pile-on; E4b with DEPBAR: bit-exact `1000 + 16×ref`). The following
  ARRIVE orders the MOV writes against subsequent wgmma (async-proxy
  register ordering) and is nearly free. So at re-init ptxas is exactly
  as conservative as the hardware forces it to be.
- Gotcha discovered en route: **DEPBAR only tracks COMMITTED groups** —
  MMAs without gsb0 belong to the open group and are invisible to
  DEPBAR.LE gsb0; a mid-chain DEPBAR before any gsb0-marked MMA is a
  no-op even with dozens of MMAs in flight. ptxas-style pacing (gsb0 on
  the last MMA of each K-iteration/group) is what makes waits meaningful.

**Cost of over-fencing (exp19b, in-kernel clock, 2 groups × 32 MMAs):**
fence-free interleave = 1317 cyc (20.6/MMA); per-switch DEPBAR+ARRIVE
(with per-MMA commits so the waits bite) = 2588 cyc (40.4/MMA) —
**~2×**, because each DEPBAR pays the full t(1) drain instead of
pipelined completion. Conclusion for codegen: interleaved multi-tile
accumulation should stay fence-free in steady state (ptxas already does
this); the DEPBAR+ARRIVE pair belongs only where non-wgmma instructions
touch accumulator/A-fragment registers (tile epilogues, re-init,
spills) — there it is mandatory, not conservative.

**Non-zero accumulator init with minimal fences (verify_init.cu, H800):**
one wgmma.fence covers ALL prior register writes of ALL groups, so the
minimum for G groups with arbitrary init is **1 ARRIVE + 1 DEPBAR
(epilogue)**, regardless of G. Two ptxas behaviours produce extra fences,
both avoidable from source:
- *Sunk init MOVs*: ptxas schedules some groups' init MOVs after another
  group's first MMA (issue-gap filling) and must re-fence (C7519).
  Fix: **fence-operand barriers** (`asm volatile("":"+f"(d[i])::"memory")`
  on every group's registers right before the fence, CUTLASS's
  `warpgroup_fence_operand` idiom) — pins all init before the single
  fence. Verified: with barriers 1 ARRIVE / without 3 ARRIVEs, numerics
  exact either way (d = init + Σref).
- *CSE register copies*: if two groups' first MMAs have identical
  inputs, ptxas replaces later ones with `MOV R?, R?` copies of the
  first group's accumulator — non-wgmma READS of GMMA-defined registers
  → mandatory DEPBAR+ARRIVE. Fix: break input symmetry (swap descriptor
  order, distinct tiles) and/or use scale-d=0 first MMAs (no init MOVs
  at all). Verified on `wgmma_interleave_acc.cu`: the rewritten
  `chain_endread_ff` compiles to 1 ARRIVE + 4 real MMAs (both firsts in
  `RZ,!UPT` overwrite form) + 1 DEPBAR, numerically identical output.
- Low-rank init (e.g. bias) can avoid register writes entirely: fold it
  into an extra rank-1 K-slice (A′=ones column, B′=bias row, zero-padded
  to k16) so the first MMA delivers `A·B + bias` with zero fences beyond
  the mandatory opening one.
