# PTX memory model → SASS/hardware mapping (sm_90)

Capstone synthesis: how each PTX §8 memory-consistency concept is realised in the
SASS ISA and the SM hardware, from the reverse-engineering in this repo.
Sub-notes: `memory_order_cta.md` (generic-proxy ordering, ERRBAR/CGAERRBAR),
`lsu_mio_structure.md` (store lifetime / arbiter), `async_proxy.md` (async proxy),
`scoreboards.md`, `control_codes.md`, `memory_model.md` (spec-field verification).
All SASS verified on sm_90/sm_90a; hardware behaviour on RTX 5090 (sm_120, model
unchanged since Turing).

## 1. Operation types (§8.4) → encoding + barrier pattern
The strength/scope live in the `LDG/STG` **`mem` field** (`SEM`×`SCO`, [80:77]);
ordering (acq/rel) is *separate* machinery around the op.

| PTX | SASS op | added ordering |
|---|---|---|
| `ld/st.weak` | `LDG.E`/`STG.E` (SEM=WEAK) | none |
| `ld/st.relaxed.S` | `.STRONG.<SCO>` | none |
| `ld.acquire.S` | `.STRONG.<SCO>` | **post-op**: `NOP` issue-stall (cta) / `CCTL.IVALL` (gpu,sys) |
| `st.release.S` | `.STRONG.<SCO>` | **pre-op**: `MEMBAR.ALL.<scope>` (+`ERRBAR`+`CGAERRBAR` @gpu+) |
| `atom.acq_rel.S` | `ATOMG.STRONG.<SCO>` | pre-`MEMBAR` + post-`NOP`/`CCTL` |
| `ld/st.volatile` | `.STRONG.SYS` (SEM=STRONG,SCO=SYS) | — |
| `ld/st.mmio` | `.MMIO.SYS` (SEM=MMIO) | — |
| `fence.acq_rel.S` | `MEMBAR.ALL.<scope>` (+`ERRBAR`/`CGAERRBAR`@gpu+) | — |
| `fence.sc.S` | `MEMBAR.SC.<scope>` (+`ERRBAR`/`CGAERRBAR`@gpu+) | — |
| `fence.proxy.async` | `FENCE.VIEW.ASYNC.{S,G}` (+`MEMBAR.ALL`) | — |

`MEMBAR` has two flavours matching `membar_sem`: `.SC` (fence.sc, forms a total
order) vs `.ALL` (fence.acq_rel / release). `red` has **no** acquire form (its
read doesn't form an acquire pattern, §8.11.1) → `REDG` never gets a post-barrier.

## 2. Scope (§8.5) → coherence domain (`SCO` field)
| PTX scope | SASS `SCO` | hardware coherence point |
|---|---|---|
| `.cta` | `.SM` (2) | the SM's L1/shared (single arbiter over 4 sub-partitions) |
| `.cluster` | — | cluster fabric (CGA); `CGAERRBAR` domain |
| `.gpu` | `.GPU` (4) | L2 (device-wide) |
| `.sys` | `.SYS` (5) | system (all devices + host) |

PTX `.cta` maps to SASS `.SM` because a CTA runs on one SM and its coherence point
*is* the SM's L1. The scope is a **radius to the coherence point**: the further the
scope, the further out the strong op must reach and the heavier the fence.

## 3. Proxy (§8.6) → physical access path
| proxy | ops | SASS | engine |
|---|---|---|---|
| generic | `ld/st/atom/red`, `cp.async`, `st.async` | `LDG/STG/LDS/STS/ATOMG`, `LDGSTS` | LSU/MIO |
| async | `cp{.reduce}.async.bulk[.tensor]` | `UBLKCP`/`UBLKRED` | uniform datapath (`udp_pipe`, TMA) |

Different proxy = different physical engine → cross-proxy visibility needs
`fence.proxy.async` → **`FENCE.VIEW.ASYNC`** (the async engine's writes made visible
to the generic LSU's "view"). `cp.async` is *asynchronous execution* but still
generic proxy → needs no view fence (verified: `LDGSTS`→`LDS` has none).

## 4. Morally strong (§8.7) → hardware conditions
Morally strong ⇔ two ops that the hardware actually orders/coheres:
- *strong + scope includes both* ⇒ both carry `SEM=STRONG` with `SCO` ≥ the domain
  containing both threads ⇒ both reach the **same coherence point** (L1 for cta,
  L2 for gpu). Weak ops (`SEM=WEAK`, no SCO) don't → not morally strong.
- *same proxy* ⇒ same engine (`LDG` vs `UBLKCP`).
- *complete overlap* ⇒ same address/size.
Conflicting morally-strong ops are single-copy-atomic because they serialise at the
one arbiter (§8.10.3 ↔ `lsu_mio_structure.md`: single serialization point).

## 5. Release / acquire patterns (§8.8) → barrier placement & mechanism
- **Release** ("prior ops visible before the release write"): a `MEMBAR` *precedes*
  the strong write. Needed because stores are **fire-and-forget** (`wr_sb=7`, no
  completion scoreboard, `lsu_mio_structure.md`) — nothing otherwise guarantees
  prior writes have drained. At gpu+ the `MEMBAR` also drains async write-error
  state (`ERRBAR`) and cluster-fabric error state (`CGAERRBAR`).
- **Acquire** ("later ops see others' writes"): a barrier *follows* the strong read.
  - `.cta`: a `NOP` whose `req` waits on the load's write-scoreboard → stalls warp
    issue until the acquire load's data returns. Enough because reads hit the SM's
    single shared L1 (no stale private copies).
  - `.gpu`/`.sys`: `CCTL.IVALL` invalidates L1 so later loads re-fetch from the L2
    coherence point (L1 is not coherent across SMs).
- The acquire barrier is a **dedicated, unfoldable** instruction (verified: never
  merged onto a neighbour, even a dependent one).

## 6. The orders (§8.9) → hardware mechanisms
| PTX order | hardware realisation |
|---|---|
| program order | in-order issue per warp (issue stops on stall / scoreboard `req`) |
| observation order (W→R via RMW) | single-arbiter serialisation of L1/L2 accesses |
| coherence order (writes) | one coherent array per level (L1@SM, L2@GPU); writes multi-copy-atomic |
| causality order | established by release `MEMBAR` + acquire `NOP`/`CCTL` + scoreboards |
| communication order (visibility) | insertion order at the arbiter |

## 7. Axioms (§8.10) → hardware guarantees (empirically checked)
| axiom | hardware basis (evidence) |
|---|---|
| Coherence / SC-per-location (CoRR) | single coherent L1; weak reads track producer, strictly monotonic (`memory_order_cta.md` liveness) |
| Atomicity (single-copy) | conflicting morally-strong ops serialise at one arbiter; MCA writes — SB never observed |
| No-Thin-Air | in-order issue + real data deps carried by scoreboards; no value speculation |
| Fence-SC | `MEMBAR.SC.<scope>` forms the per-scope total order |
| Causality (MP) | release `MEMBAR` drains writes, acquire `CCTL.IVALL`/issue-stall makes them visible |

## 8. The core asymmetry (ties it together)
Writes and reads are handled differently, which explains the whole barrier layout:
- **Stores** are posted/fire-and-forget (`wr_sb=7`): fast issue, no completion
  tracking → **release must add a `MEMBAR`** to force drain/visibility.
- **Reads** hit the single coherent L1 directly → **acquire is cheap at `.cta`**
  (just an issue-stall), and only needs an L1 **invalidate** at `.gpu`/`.sys`
  (where L1 is not the coherence point).
- **Errors** from posted writes are async → surfaced at the next drain barrier
  (`MEMBAR`/`ERRBAR`/`CGAERRBAR`), not at the store.
- **Async proxy** is a separate engine → an extra `FENCE.VIEW.ASYNC` bridges it to
  the generic LSU, on top of the normal `MEMBAR`.

Net: PTX's abstract *scope × strength × proxy × order* lattice maps to a concrete
*coherence-radius (SCO) × op-strength (SEM) × engine (LSU/TMA) × barrier-placement*
implementation, all resting on one shared-per-SM coherent arbiter with fire-and-
forget stores and scoreboard-tracked variable-latency completion.

## 9. Cache-hierarchy coherence structure (L1 vs L2)
Test: `tests/l2_coherence_test.cu`. The coherence points form a nested structure,
and *only L1 needs explicit management*:

- **L1 (per-SM): NOT coherent across SMs.** Each SM's L1 is private and may hold a
  stale copy. Cross-SM visibility is restored by **software invalidation** —
  `.gpu`/`.sys` acquire emits `CCTL.IVALL` (opcode `…198f`, default `D`=L1 cache)
  to drop L1 lines so later loads re-fetch. This is invalidation, **not** a
  hardware coherence protocol.
- **L2 (GPU-wide): a single coherent point, structurally.** No MESI-style
  coherence tags. Evidence:
  1. **Codegen:** across every scope/order, memory ordering **never emits any
     L2 invalidate/flush/writeback** (`CCTL.IVALL` is always L1; the L2 cache
     ops `PML2/DML2/WBL2/…` only appear for explicit manual cache management, not
     for acquire/release/fence). If L2 held incoherent per-SM copies, cross-SM
     acquire would have to sync L2 — it doesn't.
  2. **Behavioural:** an inter-SM producer (`st.relaxed.gpu` → write-through to L2)
     and consumer on a *different* SM (verified `%smid` 0 vs 1) see strictly
     monotonic, live values (`maxSeen=N`, `backward=0`, no staleness) — for
     `relaxed.gpu`, `acquire.gpu`, **and** weak `LDG.E` — with **no** L2 sync op.
     Coherence-per-location holds at L2 for free.

  Why structural: L2 is one physically-shared, **address-partitioned** cache — each
  line has exactly one home slice, so there is one copy per line and coherence is
  inherent (the GPU-scope analog of the single-arbiter L1 *within* an SM). Caveat
  (as everywhere): behaviour cannot distinguish "single physical copy" from a
  hidden hardware protocol, but the total absence of L2-coherence ops in codegen
  rules out software-managed L2 coherence — the model treats L2 as already
  coherent.

So the scope ladder is a **radius through a nested single-coherent-point
hierarchy**: `.cta` = the SM's L1/shared (single arbiter over 4 SMSPs), `.gpu` =
the single L2, `.sys` = the system fabric. The *only* incoherent layer is the
per-SM L1, and it is reconciled by invalidation (`CCTL.IVALL`) rather than a
protocol — which is exactly why `.gpu`+ acquire needs the L1 invalidate while
`.cta` acquire (staying within the coherent L1) needs only an issue-stall.

## 10. Atomics — performed at the single-copy point (L2 for global)
Test: `tests/atomic_latency_test.cu` (dependent atomic chain, cyc/atomic):
| atomic | SASS | latency |
|---|---|---|
| shared `.cta` | `ATOMS.ADD` | 47 |
| global `.cta` | `ATOMG.STRONG.SM` | 391 |
| global `.gpu` | `ATOMG.STRONG.GPU` | 391 |
| global `.sys` | `ATOMG.STRONG.SYS` | 391 |

**All global atomics cost the same (~L2 round trip) regardless of scope** — the
scope does *not* move the execution site. Conclusion on the mechanism:
- **Global atomics execute at the L2 home slice.** L2 is address-partitioned
  (one home slice per line), so an `ATOMG` is routed to that slice and its atomic
  ALU does the RMW **in place on the single copy**, returning the old value.
- **Atomicity is structural**, not lock-based: all accesses to an address funnel
  to one slice which serialises per-line RMWs, so concurrent atomics from
  different SMs to the same location serialise automatically — this *is* §8.10.3
  single-copy atomicity (Litmus 1). No directory/lock/cross-slice coordination.
- **L1 is never used for global atomics** (it is the incoherent layer — no
  coherent RMW possible on a private stale copy), so even `.cta`-scoped global
  atomics pay the full L2 round trip. The `SCO` field only selects the
  surrounding fences (`MEMBAR`/`CCTL.IVALL`), not the ALU location.
- **Shared atomics** (`ATOMS`) are the exception: executed in the SM's
  shared-memory unit (the SM-local single-copy point) ⇒ ~8× faster.

Same recurring pattern one level up: the RMW runs **at whichever coherence point
holds the single copy** — L2 slice for global, SMEM unit for shared — and that
single-serialisation-per-address is what makes atomicity free.

## 11. Crossbar + L2 model — where reordering comes from (corrected)
Topology: SMs ↔ crossbar ↔ L2 (1–2 monolithic OoO atomic/ordering backends on
recent archs: 1 on RTX 5090, 2 on H100; verified via aggregate-atomic-ceiling,
`notes/sm120/l2_slice_probe.md`). Data-bandwidth path is wide (many banks ⇒ TB/s); the
atomic/ordering commit path is narrow (~1–2 backends ⇒ ~90 Matom/s @ ~27-cyc
aggregate issue period).

**With ~1 monolithic commit point:**
- Same-address atomics serialise at the single backend → structural coherence
  order / single-copy atomicity.
- **Multi-copy atomicity is structural:** all writes commit at the single backend
  at a single instant, visible to all observers simultaneously → a write visible
  to different observers in different orders is structurally impossible.
  This *is* why SB(0,0) and MP-weak were never observed at any scope:
  there is essentially one serializing agent for all global traffic.
- Cross-location reordering within one warp is still possible within the OoO
  backend (speculative issue across addresses, violation replay for hazards), but
  the single commit/serialization point makes it invisible to observers because
  all writes to *all* addresses commit at the same agent → the total order across
  locations is well-behaved even across different addresses.

This corrects the earlier "independent slices → independent xbar paths → rich
cross-location reordering" speculation (§4, §9 in `notes/sm120/l2_slice_probe.md`):
reordering is not *lots* of slices driving independence; it is an **OoO-backend
behaviour** where the one backend speculates addresses apart, retires in program
order, and resolves conflicts by rollback. Still permits the ISA-level reordering
that `MEMBAR` guards against; but the near-SC empirical results now make sense.
