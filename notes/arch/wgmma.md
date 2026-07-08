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
