# LSU / MIO pipeline structure — store register lifetime & the SM arbiter (sm_90)

Microarchitecture inferred from scoreboard codegen + latency timing on the memory
pipe. Question driving this: within an SM, how do the 4 sub-partitions' load/store
requests flow through the MIO/LSU, and **when is a store's source register read
and released** relative to issue vs. global completion?
Validated on RTX 5090 (sm_120); memory model unchanged since Turing so the
structure transfers to Hopper.
Cross-refs: `memory_order_cta.md` (single-arbiter coherence result),
`scoreboards.md`, `control_codes.md`, `usched_latency.md`.
Tests: `tests/st_readsb.cu`, `tests/readsb_timing.cu`, `tests/readsb_contend.cu`,
`tests/readsb_xsm.cu`.

## Working mental model (the thing being tested)
- Each sub-partition (SMSP) issues **in program order**; issue continues until a
  stall / pipe-throttle / warp-swap / a `req` scoreboard-mask block.
- Memory instructions enter a per-SMSP **MIO queue**; a single per-SM **arbiter**
  pulls requests from the 4 SMSP queues, executes against L1/shared, and returns
  responses.

> **External corroboration (NVIDIA forums):** the MIO is described there as the
> point that communicates the SM's **4 subcores with the parts they share** — i.e.
> the MIO/LSU arbiter + L1/shared are the SM-scoped shared resource, one per SM
> (not per subcore), with a queue per SMSP. This matches the empirical model above
> (per-SMSP queues + single per-SM arbiter) and explains the timing results: a
> store's source register is consumed at an LSU-internal latch shortly after issue
> (not held to completion), and a load's write-SB clears only when the shared
> L1/shared response returns.
- A **load** clears its *write* scoreboard (`dst_wr_sb`) only when the response
  arrives (full memory latency). Established.
- Open: (Q1) do memory ops stay in order inside the MIO queue, or can they
  reorder? (Q2) when does a **store's *read* scoreboard** (`src_rel_sb`, which
  lets the store read its data/addr register late) release —
  (a) at MIO-enqueue (register must be ready at ~issue),
  (b) when the arbiter/LSU consumes/latches the request (a bit after issue,
      memory-path-dependent), or
  (c) only at store completion (register held for the whole round-trip)?

## Codegen facts (store control word)
Forcing a WAR on the store-data register inside a **loop** (physical regs are
fixed across iterations, so ptxas cannot rename the hazard away — a one-shot gets
renamed, `st_readsb.cu`):

```
STG.E.STRONG.SM [.], R6   rd_sb=0  wr_sb=7  stall=6
IADD R6, R6, 1            wait=000000            # WAR covered by STG's stall, not a req
```
- **`wr_sb=7`** — a store installs **no write/completion scoreboard**: it is
  *fire-and-forget*. The issuing warp never waits for the store to become
  globally visible. (All plain `STG`/`STS` we have seen use `wr_sb=7`.)
- **`rd_sb=0`** — the store *does* take a **read scoreboard** for its source. So
  the operand read is **deferred past issue** (else no scoreboard would be needed;
  an issue-time consume would use only stall counts). ⇒ rules out the strict
  "consumed exactly at issue" reading.
- **`stall=6` covers the WAR** — the compiler dead-reckons that ~6 cycles after
  the store, the source has been read, and lets the overwriter issue with no
  `req`. A *fixed* stall only works if the read latency is short and
  deterministic. The `rd_sb` is the dynamic backstop when the pipe is busier.

## Timing (single thread, cyc/iter; `readsb_timing.cu`)
| loop | cyc/iter | Δ over no-reuse |
|---|---|---|
| ALU add (floor) | 23 | — |
| STG global, **no** reuse | 24 | — |
| STG global **+reuse** (read-SB WAR) | 35 | **+11** |
| STS shared **+reuse** | 29 | **+5** |

Global store *completion* is ~400–800 cyc, yet the read-SB WAR adds only ~11 cyc
(global) / ~5 cyc (shared).

## Conclusions
- **(c) EXCLUDED.** The source register is released ~5–11 cyc after issue — two
  orders of magnitude below store completion. The arbiter does **not** hold the
  register file operand until the store completes, and does **not** re-read it
  repeatedly through completion. Any replay/error path (`ERRBAR`/`CGAERRBAR`)
  must therefore work from a **latched copy in the memory pipe**, not from a live
  RF read.
- **Store is fire-and-forget** (`wr_sb=7`): issue does not stall for completion;
  many stores from one warp can be outstanding at once.
- **Register read is early + low-latency**, at an **LSU/operand-collect latch**
  a handful of cycles after issue — after which the register is free. This is
  between (a) and (b): the read is *deferred* past issue (needs a scoreboard, not
  pure issue-time consume → not strict (a)) but happens *early and cheaply*, well
  before completion.
- **Mild lean to (b) over (a).** The read-SB hold is memory-type-dependent
  (global +11 vs shared +5). If the operand were latched at a uniform pre-enqueue
  ISA stage, the two would match. The gap suggests the latch happens once the
  request is being processed on its memory-type-specific path (MIO/LSU consume),
  i.e. the arbiter/LSU pulls the operand as it accepts the request. Not proven:
  clean (a)-vs-(b) separation needs isolated arbiter contention, which on a
  single SM is confounded by issue-slot contention (`readsb_contend.cu`: adding
  same-CTA flood blew the loop to ~610 cyc/iter — issue contention, not arbiter);
  a cross-SM persistent-flood attempt (`readsb_xsm.cu`) hung and is unresolved.

**Practical model to use downstream:** treat a store's source registers as read
~6–12 cyc after issue at an LSU-internal latch **when the queue is light**; the
register frees then and the store completes asynchronously from the latched copy
(fire-and-forget, no completion scoreboard). Do **not** model the register as
held to completion. **But under a deep queue the latch slides arbitrarily late**
— see below.

## Deep-queue confirmation of (b) — the latch waits for the arbiter (2026-08)

A wgmma experiment accidentally became a clean (a)-vs-(b) discriminator
(wgmma.md Round 3, exp11v3): 64 back-to-back `STG.E.128`s (8 accumulator
groups × 8) issued with **no `rd_sb`** (`[7:7:{}:4:0]`), followed immediately
by `MOV32I` rewrites of all source registers. Result: the **last store group
(deepest in the queue) stored the rewritten value** (2000.0 exactly, 128/128
threads), while earlier groups stored the correct old values. Padding 100 cyc
of NOPs between the last store and the rewrite did **not** help — the last
group's data sample lagged its issue by **hundreds of cycles**, bounded below
by the drain time of ~56 queued 16 B/thread stores.

- This is **decisive for (b) over (a)**: a pre-enqueue/issue-stage latch (a)
  cannot depend on how many requests are queued ahead of the store. The source
  register is read only when the arbiter/LSU accepts the request, and that
  acceptance is rate-limited by the memory path, so the hold time scales with
  queue depth (from ~5–11 cyc when light to ≥100s of cycles when deep).
- It also validates the codegen economy: ptxas's fixed `stall=6` dead-reckoning
  is safe only because real code rarely floods the LSU with 64 unrestricted
  stores; the `rd_sb` backstop (plus `DEPBAR.LE SBn`) is what actually covers
  deep-queue cases. Hand-written SASS without it silently corrupts — this
  artifact produced three phantom tensor-core findings (see wgmma.md Round 2
  retractions: "commit capacity ~35", "retired accumulator", "back-to-back
  commit loss").

## Q1 (MIO in-order vs reorder) — resolved with caveat
The MP litmus (Message-Passing: `D=1 ; F=1 // rf=F; rd=D`) tests whether two
stores to *different* addresses can complete out of program order. It is the
canonical store→store reorder test. However, MP also allows a weak outcome from
**consumer load→load reorder**, conflating the two axes. To isolate
**store→store only**, the consumer's data load must be pinned by a genuine
address-carrying data dependency on the flag value — ptxas must not constant-fold
it. Two additional gotchas fixed:
- **Intra shared D/F** must be padded apart to defeat `STS.64` coalescing (the
  original `mp_spin.cu` had D & F adjacent and ptxas fused them to one 64-bit
  store — no store→store pair exists).
- **Inter D[0]/D[1]** lookup-table indices must not be adjacent to defeat
  per-index `STG` → 64-bit fusion.

Fixed test: `tests/mp_dep.cu` (v4). Consumer data-load address genuinely computed
from flag value (`SHF→LOP3(f&1)→IMAD→LDG` for inter; `LOP3→SEL→LDS` for intra),
verified in sm_90 and sm_120 SASS. Intra STS confirmed 3 separate 32-bit stores.

**Result** (9.6M inter cross-SM + 200k intra, relaxed no-fence, placement
confirmed `diffSM`):
- **Store→store reorder never observed** (`WEAK(data==0)=0` for both inter and
  intra, relaxed with no fence).
- Fence variant also shows `WEAK=0` (fence is sufficient but not necessary — the
  HW simply never reorders this pattern for plain generic-proxy ld/st).
- Combined with earlier SB results: neither W→R nor W→W reorder is observable
  for generic-proxy relaxed ops on this silicon, at any scope.

This does **not** mean store→store is prohibited; the `MEMBAR` requirement in
`st.release` codegen proves the ISA permits it. But the hardware's
multi-copy-atomic coherence point (single SM arbiter for intra-SM, single L2
coherence point for cross-SM) appears to serialize stores fast enough that
concurrent observers never catch a reorder. A genuine positive reorder on this
GPU would likely need asymmetric proxy/path semantics (`.mmio`, texture, or
mixed-state-space).

## Open questions
- Clean (a)-vs-(b): isolate arbiter contention from issue contention (needs a
  concurrent flood on *other* SMs without perturbing the timed SM's issue).
- Does a store ever receive an arbiter *response* at all (for ECC/fault via
  `ERRBAR`/`CGAERRBAR`), or is the only back-signal the load write-scoreboard?
- Whether the per-SMSP MIO queue is strictly FIFO or a small reorder buffer.
