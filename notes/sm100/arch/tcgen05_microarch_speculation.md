# Blackwell tcgen05 tensor-core hardware — inference from the SASS/ISA (SPECULATION)

**Status: SPECULATION / architectural inference.** As with
`notes/sm90/arch/tensorcore_microarch_speculation.md`, the ISA is dataflow-
agnostic — it cannot prove the multiply-add fabric. This records a reasoned
Blackwell hardware picture built from (a) the Hopper wgmma model we reverse-
engineered, (b) the concrete tcgen05 SASS we decoded (`utchmma.md`, `utccp.md`,
`ldtm.md`, `utcatomsws.md`, `utcbar.md`), and (c) the PTX shape/queue tables.

## Recap: the Hopper wgmma implementation (well-supported)
From `wgmma.md` + `tensorcore_microarch_speculation.md`:
- wgmma is **M=64 fixed**, warpgroup-collective (128 threads). The SM's **4
  subcores** each own one warp of the warpgroup and one tensor unit computing
  **16 of the 64 M-rows** (64 = 4 subcores × 16).
- Per-instruction K is small/fixed (16 fp16, 32 fp8); real accumulation is the
  explicit K-loop into a tensor-core-resident **implicit accumulator collector**
  (register-named, drain-on-read).
- The likely datapath is a **widened Ampere-lineage dot-product / 4-way-fused-FMA
  tree**, one 16×N unit per subcore. The user's reconstruction: each subcore's
  tensor core computes m16n8k16 tiles, the n8k16 B-block is streamed from shared
  memory and **broadcast across the 4 subcores' tensor units** over a dedicated
  data path — cutting shared-memory B-bandwidth to 1/4 and reusing the wmma
  circuit. This is a clean, cheap "4× wmma + broadcast" design.

## What the Blackwell SASS/ISA actually tells us (facts)
1. **Single-thread issue.** `UTCHMMA` is issued by *one* thread (via `ELECT`
   leader), `udp_pipe`, `$VQ_TC_1CTA`/`2CTA`. No warpgroup co-issue, no
   per-subcore warp partition in the ISA. (PTX §Issue Granularity: "an issue from
   a single thread … initiates the base operation.")
2. **Accumulator + operands in explicit TMEM.** D is `tmem[URc]`; A may be
   `tmem[URa]` or a shared descriptor; B is always a shared descriptor. TMEM is a
   **128 lane × 512 column × 32-bit** 2-D array per CTA (PTX §TMEM).
3. **M scales with cta_group, not subcores.** fp16 dense shapes:
   - `cta_group::1`: **M ∈ {64, 128}**, N = 8..256 step 8, K=16.
   - `cta_group::2`: **M ∈ {128, 256}**, N = 16..256 step 16, K=16.
   The peer-CTA pairing (`.2CTA`, bit[85]) *doubles* the achievable M and the
   `disable-output-lane` mask width (4→8). So the compute tile now spans **two
   CTAs' TMEM**, not four subcores' register files.
4. **N is much wider per instruction** (up to 256) and K stays 16 — same small
   fixed reduction depth as Hopper.
5. **Explicit operand collectors.** A-collector (`.WS`=0, 1 buffer) or B-collector
   (`.WS`=1, 4 buffers) — the *explicit* form of Hopper's implicit `.reuse`.
6. **`UTCCP` stages shmem→TMEM** with shapes named `128dp256bit`,
   `2x64dp128bit_lw02_lw13`, `4x32dp128bit` (see `utccp.md`): "dp" = datapath
   lane-group, and the multicast fan-out (`.warpx2`/`.warpx4`) is baked into the
   copy — data is broadcast into warp-pairs/quads as it lands in TMEM.

## Inferred Blackwell hardware picture
The Hopper design was **"4 per-subcore wmma units + broadcast B, accumulator
hidden in the core."** Blackwell reads as the next step: **pull the tensor core
out of the subcores into one (or two-CTA-paired) SM-level MMA engine backed by
explicit Tensor Memory.**

### 1. From 4 subcore units → one SM-level engine
- Hopper's M=64 = 4×16 is a *subcore* artifact (one warp per subcore). Blackwell's
  M is 64/128 (1CTA) and 128/256 (2CTA) and is **decoupled from the 4-subcore /
  128-thread structure** — issue is single-thread. This strongly suggests the
  MMA fabric is **no longer partitioned one-unit-per-subcore**; it is a shared
  SM-level (or SM-pair-level) engine that a single thread kicks off.
- The `.2CTA` M-doubling ⇒ the engine can be **paired across two CTAs of a
  cluster** to form a 2× taller array — consistent with a physically larger,
  poolable compute fabric rather than fixed 4×16 slices.

### 2. Why TMEM exists (systolic-array corollary)
If the multiply-add fabric became a **systolic array** (the plausible 5th-gen
paradigm shift, per the Blackwell-introduced-systolic hypothesis in the sm90
note), then:
- Partial sums must be **streamed out of the array into a large addressable
  store** — that is exactly TMEM (128×512×32b). Hopper's small hidden collector
  could live inside a dot-product unit; a systolic array's O(M×N) partial-sum
  state cannot, so it is externalized and made programmer-visible.
- The array streams operands in from **staged TMEM/shared** — hence `UTCCP`
  (shmem→TMEM), `LDTM`/`STTM` (TMEM↔RF), and A being allowed **directly in TMEM**
  (`[a-tmem]`, opcode 0x19ea): an activation matrix can be pre-staged in the
  array's feed memory and shifted (`.ashift`) for convolution sliding windows —
  natural for a systolic feed, awkward for the old broadcast-from-shmem model.
- **Single-thread issue** fits an autonomous async engine (fire-and-forget,
  mbarrier completion via `UTCBAR`) far better than 128-thread lockstep.

### 3. What replaced the "broadcast B to 4 subcores" trick
Hopper cut B-bandwidth 4× by broadcasting one n8k16 block to 4 subcore units.
Blackwell's equivalent bandwidth lever moves into the **staging + collector**
layer:
- `UTCCP` multicast (`.warpx2::02_13`/`.warpx4`, fused into the copy `mode`)
  broadcasts a shared-memory matrix into multiple lane-groups of TMEM once.
- The **collector buffers** (1 for A / 4 for B) hold the stationary operand
  in-core across a sequence, so a whole GEMM/conv K-loop reloads only the moving
  operand. This is the explicit, programmable successor to Hopper's implicit
  `.reuse` broadcast — the reuse is now scheduled by software (AS/WS +
  `.collector::*`) instead of wired into a fixed 4-subcore broadcast bus.

### 4. Convolution / `.ashift` as a systolic-feed feature
`.ashift` (shift A's rows down by one, M=128/256 only, A-in-TMEM only) is a
sliding-window primitive that only makes sense if A is resident in a structured
feed memory the engine indexes with a row offset — i.e. TMEM feeding a spatial
array — rather than A arriving fresh from shmem each MMA. This is circumstantial
support for the "A staged in the array's feed store" picture.

## Array geometry deduction (from external hardware clues)
Three additional facts (external RE, not from our dumps, but internally
consistent and cross-checked against the PTX shape table below):
- **F1.** Blackwell TC *is* a systolic array; each PE does a **4-way-fused FMA
  per cycle** (the old 4-way-FMA becomes the PE).
- **F2.** Running a legacy `wmma.m16n8k16` on Blackwell uses only **1/4** of the
  datapath width.
- **F3.** Two ways to fully occupy the TC, both giving a **per-subcore output
  tile of M=32**:
  - *Mode A* (default/AS): each subcore takes **32 of M=128** rows → per-subcore
    output `m32 × N`.
  - *Mode B* (`.ws` required): each subcore takes 32 of M=64 with half the N →
    per-subcore output `m32 × N/2`.

### These pin the per-subcore PE plane to 32(M) × 16(N)
Let the per-subcore PE output plane be `Mpe × Npe`. F3 gives `Mpe = 32`.
F2 says `wmma m16n8` fills 1/4: `(16/Mpe)·(8/Npe) = 1/4`. With `Mpe=32`:
`(16/32)·(8/Npe) = (1/2)(8/Npe) = 1/4` ⟹ **`Npe = 16`**. (Npe=8 would give 1/2,
Npe=32 gives 1/8 — only 16 matches.)

So each subcore's systolic array is **32×16 = 512 PEs**, and per SM:
```
per-subcore PE plane : 32 (M) × 16 (N) = 512 PEs
per-SM (4 subcores)  : 2048 PEs  ×4-way-FMA = 8192 fp16 MACs/cycle
legacy wmma m16n8    : 16×8 = 128 PEs = 128/512 = 1/4 of one subcore  ✓ (F2)
```

### The two full-occupancy layouts are two ways to tile the same 2048 PEs
Both modes use all 4 subcores × 512 PEs = 2048, but partition M vs N differently:
| layout | per-subcore | 4-subcore assembly | total | min shape |
|--------|-------------|--------------------|-------|-----------|
| **A (AS)** | m32 × N=16 | stack 4 subcores in **M** (4×32) | 128 × 16 | needs **M ≥ 128** |
| **B (WS)** | m32 × N=32(=2·16) | **2×2** grid (2 in M, 2 in N) | 64 × 32 | works at **M = 64** |

Mode A stacks the four 32-row slices into one M=128 column ("4×1 in M"). Mode B
arranges them 2×2 (two subcores share M=64, two share the doubled N), so each
subcore's *N* doubles to 32 — hence `m32 × N/2` in per-subcore terms, `m64 × N`
overall.

### Why Mode B *requires* `.ws` — and it matches the ISA exactly
In the 2×2 layout, two subcores hold the **same** M-rows but different N-columns,
so the operand that is broadcast down a subcore column must be the **weights (A)**
while activations (B) differ per column — i.e. the **weights are stationary**.
That is precisely what `.ws` means (collector on B, activations in B; see
`utchmma.md`). The 4×1 M-stack (Mode A) instead broadcasts B across the M-stack
and keeps activations in A (activation-stationary). **The layout dictates which
operand is stationary, so Mode B is only expressible as `.ws`.**

This is confirmed by the PTX shape table (`09.7.17`, fp16):
- **AS (no `.ws`)**: M ∈ {64,128}, **N = {8,16,…,256} step 8**, `cta_group::2`
  → M ∈ {128,256}.
- **`.ws`**: **M ∈ {32,64,128}** (adds M=32!), **N = {64,128,256}** (coarser,
  min 64 not 8), and **`cta_group::2` is *Invalid***.

Every one of these falls out of the geometry:
- `.ws` exposing **M=32** = a single subcore's M-plane (Mode B lets one subcore
  stand alone at M=32; AS min is M=128 = the 4-stack, or M=64 as a half-stack).
- `.ws` **N minimum 64 / coarse steps** = the doubled-N per subcore (2×2 grid
  needs N split across two subcore columns, so N granularity is coarser and
  larger-min).
- `.ws` **cta_group::2 Invalid** = the 2×2 grid already consumes the 4 subcores in
  a fixed M×N tiling; you cannot further pair CTAs to grow M the way the AS
  M-stack does (`cta_group::2` doubles M by stacking, which only composes with
  Mode A's M-stack, not Mode B's 2×2).

### Corollary: cta_group::2 = stack two SMs' arrays in M
AS `cta_group::2` doubles M (128→256) and the disable-output-lane mask (4→8).
Under the M-stack picture, pairing the peer CTA's 4 subcores on top gives an
**8×32 = 256-row** stack — a taller systolic array spanning two CTAs' TMEM. This
is the "poolable across 2 CTAs" claim, now with a concrete row count.

## AS vs WS dataflow (standard GEMM, naïve systolic view)
This works out the per-subcore dataflow for the two full-occupancy layouts,
treating the 32×16 plane as a **plain systolic array** (ignore the 4-way-FMA
packing; ignore the collector — the collector is an *inter-instruction* operand
cache, most relevant to convolution, and is analysed separately). The physical
convention taken (classic systolic + NVIDIA "stationary" naming): the **A
operand is loaded into the PEs and held; B streams in**. In the plane, one axis
is M (32) and the other is the K=16 reduction depth.

### AS, `m128×N×k16` (default) — one broadcast axis
Each subcore loads its own 32 M-rows of A into the PEs: `PE(m,k) = A[m,k]`,
m∈[0,32), k∈[0,16). B streams as K-vectors: cycle *n* feeds `B[:,n]` (16
elements), the array multiply-adds along the 16 K-columns and emits one output
column `C[:,n]` (32 values). After N cycles: a 32×N tile per subcore. The 4
subcores hold **different** 32-row A slices (M stacked to 128) and **share the
same B** — B is **broadcast ×4** down the M-stack. So:
- **A**: private per subcore (4 distinct slices).
- **B**: single broadcast axis, fan-out ×4.
- output: 128×N.

### WS, `m64×N×k16` (`.ws` required) — two broadcast axes
The 4 subcores form a **2(M) × 2(N)** grid tiling a 64×N output:
```
              N[0 : N/2]              N[N/2 : N]
M[0:32]    SC0  hold A[0:32,:]     SC1  hold A[0:32,:]   ← same A  (broadcast →)
                stream B[:,0:N/2]       stream B[:,N/2:N]
M[32:64]   SC2  hold A[32:64,:]    SC3  hold A[32:64,:]  ← same A
                stream B[:,0:N/2]       stream B[:,N/2:N]
              ↑ same B-half          ↑ same B-half
              (broadcast ↓)          (broadcast ↓)
```
Physically still "A held in PEs, B streams" (A is the `[a]` slot = the WS
"weight"; weight-stationary = A resident in the PEs). Each subcore streams only
N/2 columns of B over N/2 cycles and emits 32×(N/2). The difference is purely the
**broadcast topology**:
- **B broadcast down grid columns** (SC0≡SC2 stream `B[:,0:N/2]`; SC1≡SC3 the
  other half) — the AS axis, but fan-out ×2 instead of ×4.
- **A broadcast across grid rows** (SC0≡SC1 hold `A[0:32]`; SC2≡SC3 hold
  `A[32:64]`) — a **second broadcast axis AS does not have**.

| | broadcast axes | A | B |
|---|---|---|---|
| **AS (4×1)** | 1 | private ×4 slices | broadcast ×4 |
| **WS (2×2)** | 2 | broadcast ×2 | broadcast ×2 |

**WS trades M-tile height (128→64) for a second (A) spatial-reuse axis** — the
physical meaning of "weight(A)-stationary": weight A is now shared by two
N-output tiles instead of being private per M-slice. This is also why `.ws` is
mandatory for the 2×2 (different broadcast-network config; it also flips the
collector from A to B).

### What it means for pure GEMM
- **Same compute:** both saturate 2048 PEs (128 K16 dot-products/cycle) — just a
  64M×2N vs 128M×1N tiling of the same fabric.
- **The real win is small-M occupancy:** the 2×2 fills all 4 subcores at **M=64**;
  the AS M-stack at M=64 uses only 2 subcores (half idle). This is exactly the
  ISA constraint — `.ws` exposes M=32/64, and `cta_group::2` is *Invalid* for WS
  (the 2×2 already commits all 4 subcores to a fixed M×N tiling; growing M by
  CTA-pairing only composes with the AS M-stack).
- **Bandwidth:** per output element, B cost and A per-row cost are the same both
  ways — WS is **not** a bandwidth win for dense GEMM. Its payoff is small-M
  utilisation (and, for convolution, the operand-reuse structure the collector
  exploits).

### Confidence
The physical direction ("A in PEs, B streams") and "WS = add an A-broadcast axis
via the 2×2 M↔N retile" are inferred from the AS model + the 32×16 geometry + the
PTX shape constraints; they are self-consistent and predict those constraints.
But **which operand physically sits in the PEs**, and the collector's exact
feed behaviour, are not visible in the ISA — this follows classic systolic
convention and NVIDIA's "stationary" naming, not a proof.

## How convolution is done (inference)
The PTX chapter never states the convolution algorithm — it only gives four
mechanisms (the stationary table, `.ashift`, the collector, and the zero-column
mask). Reconstructing the intent from those four, plus the geometry above.

### The premise: implicit GEMM (im2col done in-fabric)
A convolution `Out[n,p,q,k] = Σ_{c,r,s} In[n, p·str+r, q·str+s, c] · W[k,r,s,c]`
is an implicit GEMM: **M = spatial output positions**, **N = output channels K**
(or vice-versa), **K-contraction = (R·S·C) filter taps × input channels**. The
classic cost is `im2col` — materialising overlapping receptive fields blows up
activation footprint and bandwidth. The tcgen05 convolution features are exactly
the pieces that let the tensor core **avoid explicit im2col** by reusing
overlapping activation rows/columns in-fabric.

### The AS/WS split is a *mirror*, and the SASS confirms it
The two convolution paths carry **mutually exclusive** helper operands (verified
in the PTX + our SASS):

| | activation in | weights in | sliding-window tool | who is reused |
|---|---|---|---|---|
| **AS conv** (default) | A | B | **`.ashift`** (shift A rows) | activation A in collector (1 buf) |
| **WS conv** (`.ws`) | B | A | **`zero-column-mask-desc`** (mask B cols) | activation B in collector (4 buf) |

- AS has `.ashift` and **no** zero-column mask.
- WS has `zero-column-mask-desc` and **no** `.ashift`.
- In both, the **collector holds the activation** (A in AS, B in WS) — because in
  a conv the activation is what overlaps between adjacent output positions and is
  worth caching across the MMA sequence.

So "activation-stationary" vs "weight-stationary" names *which matrix the
activation occupies*, and each gets the sliding-window primitive appropriate to
whether the activation streams as **rows** (A → `.ashift`) or **columns**
(B → zero-column mask).

### `.ashift` = sliding the receptive field by one row (AS)
`.ashift` shifts A's rows down by one (except the last), M=128/256 only, A must
be **TMEM-resident** (opcode 0x19ea), and it is illegal with `.collector::a::use`
/`fill`. Reading this as a convolution step:
- A (activation) is staged in TMEM as a window of input rows. Consecutive output
  rows share all but one input row (stride-1 conv). `.ashift` advances the
  window by one row **in place**, so the next MMA reuses the already-resident
  rows and only the new bottom row is fresh — an in-fabric `im2col` row-slide
  with **no re-staging** of the overlap.
- "except the last row" = the newly-entering row is loaded separately; the rest
  are recycled. That it is TMEM-only and M=128/256-only fits a hardware
  row-rotate of the array's A-feed store (needs the full M-plane resident).
- Illegal with collector `use`/`fill` because `.ashift` **is** the reuse
  mechanism for A here — the two would be redundant/conflicting ways to say "A
  overlaps the previous MMA".

### Zero-column mask = padding / halo / stride gaps (WS)
When the activation is in B (WS), overlap runs along **columns**, so the reuse/
window tool is a per-column mask instead of a row-shift. The descriptor (Table 48)
is a **periodic run-length mask**: `Use Span` consecutive used columns, then
`Skip Span` zeroed columns, repeating, with a `First Span`/`Start Count` phase
and a `Column Shift`. A 1-bit forces that B column to **zero regardless of shared
memory** (§9.7.17.4.3).
- This is exactly what convolution edges need: **halo/padding columns** (receptive
  fields hanging off the image border) are forced to 0, and the periodic
  skip/use pattern expresses **dilation / stride gaps** in the packed activation
  layout — again avoiding an explicit padded im2col buffer.
- Per-M sub-masks (M=128→1, 64→2, 32→4) line up with the 2×2/stack layouts: each
  M-tile of the fabric gets its own column-validity pattern, i.e. different
  output-row groups can sit at different spatial positions with different
  padding.

### The collector closes the loop (why it's "convolution-only" in the syntax)
The user's observation that collector qualifiers appear in the **convolution**
syntax forms (and block-scale), not the plain-GEMM form, fits: in a straight
GEMM each A/B tile is used once, so there is nothing to cache between MMAs. In a
convolution the stationary activation is **reused across the sequence of output
positions** (that is the whole point of avoiding im2col), so the collector's
fill/use/lastuse/discard lifecycle is what makes the overlap reuse explicit and
software-scheduled. `.ashift` (AS) and the zero-column mask (WS) generate the
*window motion*; the collector holds the *overlapping data* the window slides
over.

### Putting it together (AS stride-1 conv, sketch)
```
stage input rows 0..M-1 into A (TMEM)              ; collector::a::fill
for each filter tap (r,s) over the K-contraction:
    UTCHMMA D, A(tmem), Bdesc(weights), idesc, ... ; collector::a::use
    UTCHMMA.ASHIFT D, A(tmem), ...                 ; slide window +1 row
load only the new bottom row; repeat              ; overlap stays resident
commit → mbarrier                                  ; UTCBAR
```
The activation window lives in TMEM/collector; `.ashift` walks it; weights stream
as B descriptors; partial sums accumulate in D (TMEM). WS is the transpose of
this with activation in B and the zero-column mask handling edges.

### Confidence (convolution)
- **From PTX/SASS (fact):** the AS/`.ashift` vs WS/`zero-column-mask` mutual
  exclusivity, collector-holds-activation, collector appearing in conv/block-
  scale forms, `.ashift` semantics (row shift, M=128/256, TMEM-only, ⊥
  collector-use), zero-column-mask being a periodic run-length B-column zeroing
  mask with per-M sub-masks.
- **Inference (not proven):** that these implement **im2col-free convolution**
  via in-fabric overlap reuse — i.e. the *purpose* mapping (ashift = receptive-
  field row slide; zero-column mask = padding/dilation; collector = overlap
  cache). The ISA describes the mechanisms, not their intended convolution use;
  this reading is the simplest one that makes all four features cohere, but it is
  a reconstruction.

## Summary table: Hopper vs inferred Blackwell fabric
| aspect | Hopper (4th-gen, wgmma) | Blackwell (5th-gen, tcgen05) — inferred |
|--------|-------------------------|------------------------------------------|
| unit placement | 4 per-subcore 16×N units | 1 SM-level engine (poolable across 2 CTAs) |
| M origin | 64 = 4 subcores × 16 rows | 64/128 (1CTA), 128/256 (2CTA); decoupled from subcores |
| issue | warpgroup-collective (128 thr) | single thread + `ELECT` |
| datapath (guess) | widened dot-product / 4-way-FMA tree | **systolic array**, PE = 4-way-FMA (partial-sums → TMEM) |
| per-subcore array | 16×N dot-product slice | **32(M)×16(N) = 512 PE systolic plane** |
| B bandwidth trick | broadcast n8k16 to 4 subcores | `UTCCP` multicast into TMEM + collector reuse |
| accumulator | hidden in-core collector (RF-named) | explicit **TMEM** (`[d-tmem]`) |
| operand reuse | implicit `.reuse` | explicit collector (A:1 / B:4 buffers) |
| conv support | (none specific) | `.ashift` sliding window on TMEM-resident A |

## Confidence and what would confirm/refute
- **Well-supported (from SASS):** single-thread issue, explicit TMEM operands/
  accumulator, M-doubling under `.2CTA`, explicit collectors, `UTCCP` multicast,
  `.ashift` only with A-in-TMEM. These are ISA facts, not guesses.
- **Now strongly supported (geometry + ISA cross-check):** the **32×16 per-subcore
  PE plane** and the **two full-occupancy layouts (4×1 M-stack for AS, 2×2 for
  WS)**. The array-geometry deduction from F1–F3 predicts, with no free
  parameters, exactly the PTX `.ws` shape constraints (M=32 minimum, coarse
  N≥64, `cta_group::2` invalid) — a non-trivial three-way match that would be a
  coincidence under a non-systolic or differently-shaped fabric. The systolic +
  stationary-operand-per-layout picture is the simplest thing that explains it.
- **Still not provable from our dumps alone:** F1–F3 are external RE inputs; the
  ISA cannot directly show the multiply-add topology. But given F1–F3, the rest
  (plane size, layouts, why WS is mandatory for the 2×2) is essentially forced,
  not guessed.
- **Possible probes (likely inconclusive, same caveats as sm90 note):**
  latency-vs-M and latency-vs-N dependent-chain microbenchmarks on real
  sm_100 hardware — a systolic array shows fill/drain latency ~linear in the
  array dimension while steady-state throughput saturates; async mbarrier
  completion (`UTCBAR`) would tend to mask fill/drain, so this is suggestive at
  best. We have no sm_100 hardware here — all of the above is from the dumps +
  the F1–F3 external clues.

## Cross-refs
`notes/sm90/arch/wgmma.md` (Hopper subcore/broadcast model),
`notes/sm90/arch/tensorcore_microarch_speculation.md` (dot-product vs systolic),
`notes/sm90/arch/tcgen05_vs_wgmma.md` (accumulator→TMEM transition),
`notes/sm100/instr/utchmma.md` (MMA encoding, AS/WS/conv axes),
`notes/sm100/instr/utccp.md` (shmem→TMEM staging + multicast),
`notes/sm100/instr/ldtm.md` / `sttm.md` (TMEM↔RF), `utcbar.md` (completion).
