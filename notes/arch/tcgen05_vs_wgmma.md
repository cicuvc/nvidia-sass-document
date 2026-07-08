# Blackwell tcgen05 vs Hopper wgmma — the accumulator becomes Tensor Memory

Forward-looking comparison (PTX ISA 9.3, `~/cs/project/documented-ptx`) tying the
empirically-derived Hopper model (`wgmma.md`, `hmma_pipeline.md`) to
Blackwell's 5th-gen tensor core (`tcgen05.*`, sm_100+). Confirms the user's
observation: **Hopper's implicit, register-named, tensor-core-resident
accumulator is made explicit in Blackwell as an addressable state space —
Tensor Memory (TMEM).**

## What we inferred on Hopper
From `tests/wgmma_acctc_test.cu`: chained same-accumulator `wgmma.mma_async` need
no inter-instruction wait (the running sum is forwarded *inside* the tensor
core), a normal read of the accumulator forces a `wait_group` drain to the
register file, and resuming needs a re-`fence`. I.e. the accumulator behaves as
if it lives in a dedicated collector inside the tensor core, only materialising
to registers on demand. **Blackwell turns that inferred collector into a
first-class, programmer-visible memory.**

## Tensor Memory (TMEM)
- A new state space, **explicitly allocated**: `tcgen05.alloc [dst], nCols`
  (unit = 32 columns × all lanes; `nCols ∈ [32,512]`, power of two), address
  written to shared memory; freed with `tcgen05.dealloc`; permit relinquished
  with `tcgen05.relinquish_alloc_permit`. Register allocation of accumulators is
  gone — you manage TMEM columns.
- The MMA accumulator `D` is addressed as `[d-tmem]` and stays in TMEM across
  MMAs. `A` may be in TMEM (`[a-tmem]`) or shared (descriptor); `B` is a shared
  descriptor.
- To *use* the result you must **explicitly move TMEM→RF**: `tcgen05.ld` (async
  collective load) + `tcgen05.wait::ld`. Initial values go RF→TMEM via
  `tcgen05.st`. This is the explicit form of Hopper's implicit `wait_group`
  drain.

## The MMA instruction
`tcgen05.mma.cta_group.kind [d-tmem], a-desc|[a-tmem], b-desc, idesc, …,
enable-input-d {, scale-input-d}`:
- **Asynchronous**, `D = A*B + D` in TMEM.
- **Single-thread semantics** — one thread launches the entire MxNxK op (Hopper's
  `wgmma` was warpgroup-*collective*, 128 threads). Big issue-model change.
- `enable-input-d` (predicate, false ⇒ `D = A*B`) is the analog of Hopper's
  `scaleD=RZ` overwrite; `scale-input-d` gives `D = A*B + D*2^-s` accumulator
  scaling.
- **Explicit A-operand collector**: `.collector::a::{fill,use,lastuse,discard}`
  manages an A-matrix buffer across MMAs — the *explicit* version of Hopper's
  implicit operand `.reuse` (e.g. "activation-stationary" K-loops reuse A).

## Synchronization mapping

| concept | Hopper wgmma (sm_90a) | Blackwell tcgen05 (sm_100+) |
|---|---|---|
| accumulator location | RF-named, tensor-core-resident (implicit) | **TMEM**, explicit addressable |
| accumulator lifetime mgmt | register allocation | `tcgen05.alloc`/`dealloc` (32-col units) |
| issue granularity | warpgroup collective (128 thr) | **single thread** |
| A / B operands | shared-mem descriptors | A: `[a-tmem]` or s-desc; B: s-desc |
| overwrite vs accumulate | `scaleD` (RZ = overwrite) | `enable-input-d` pred; `scale-input-d` |
| read accumulator → regs | `wait_group` (implicit drain) | **`tcgen05.ld` + `tcgen05.wait::ld`** (explicit) |
| init accumulator | zero regs + fence | `tcgen05.st` (RF→TMEM) |
| protect-accumulator fence | `wgmma.fence` → `WARPGROUP.ARRIVE` | **not needed** for RF aliasing; `tcgen05.fence::before/after_thread_sync` orders async ops |
| commit / completion | `commit_group`/`wait_group` via **dedicated GMMA group scoreboard** (`WARPGROUP.DEPBAR.LE`) | `tcgen05.commit` → **mbarrier** arrive; consumer `mbarrier.try_wait` |
| A-operand reuse | implicit `.reuse` flags | explicit `.collector::a::*` |

## Key differences and why they follow from the model
1. **Fence semantics change because the hazard changes.** On Hopper the
   accumulator aliases real GPRs, so `wgmma.fence` exists to order RF accesses
   against the async write-back (`wgmma.md` §"Architectural model"). On
   Blackwell the accumulator is *not* in the RF, so that specific fence
   disappears; `tcgen05.fence::{before,after}_thread_sync` are code-motion fences
   that order async `tcgen05` ops among themselves. RF↔TMEM traffic is instead
   explicit (`ld`/`st` + `wait`).
2. **No accumulator-switch penalty.** Hopper serialised alternating accumulators
   (drain + re-fence per switch) because one collector aliased the register file.
   In TMEM, independent accumulators are just different addresses/columns and can
   all stay resident (up to 512 columns), so multi-tile accumulation no longer
   pays the switch cost — directly addressing the two-accumulator finding.
3. **Completion via mbarrier, not a dedicated scoreboard.** Hopper used a
   *dedicated* GMMA-group scoreboard drained by `WARPGROUP.DEPBAR.LE`. Blackwell
   folds MMA completion into the **general async mbarrier** mechanism
   (`tcgen05.commit.mbarrier::arrive::one` → `mbarrier.try_wait`), unifying it
   with `cp.async.bulk`/TMA. The counted-group idea (`../instr/depbar.md`) is
   replaced by the more general mbarrier arrive/wait.
4. **Single-thread issue** frees the warpgroup: one thread launches the MMA,
   whereas Hopper required all 128 threads to co-issue.
5. **The "internal collector" is now two explicit things**: the *accumulator*
   collector → TMEM (`d-tmem`); the *A-operand* collector → the explicit
   `.collector::a::*` buffer. Hopper had both implicit.

## Continuity
Conceptually the pipeline is the same shape, just externalised:

```
Hopper:     fence            → wgmma.mma_async×N (D in RF/collector) → commit_group → wait_group → (D in RF)
Blackwell:  alloc + st(init) → tcgen05.mma×N   (D in TMEM)          → commit(mbar) → mbar.wait  → tcgen05.ld (D→RF)
```

The Hopper `wait_group`-drain and `wgmma.fence`-protect that we reverse-engineered
as evidence for an internal accumulator are, in Blackwell, replaced by explicit
`tcgen05.ld`/`st` moves to/from a named Tensor Memory — i.e. the hidden
accumulator became addressable. This is a clean architectural confirmation of the
model in `wgmma.md`.

## Sources
`documented-ptx/instructions/182` (alloc), `183` (ld), `184` (st), `185` (wait),
`195` (mma), `199` (fence), `200` (commit).
