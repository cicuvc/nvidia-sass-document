# Memory ordering codegen — PTX→SASS at `.cta` scope (sm_90)

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** medium  
**Last verified:** unknown  
**Probe:** Ran on RTX 5090  
**Open items:** 2 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: hardware named next to a verification verb

## Conclusion

Empirical study of how ptxas (CUDA 13.1) lowers `ld`/`st` with each memory-order
qualifier, restricted to: **general proxy, strong ops, `.cta` scope**, on
`.global` (L1) and `.shared` (SM-local). Complements `memory_model.md` (which
verifies the spec *fields*); this note records the actual *codegen*.
Test: `tests/memorder_cta_test.cu` (one named kernel per variant).
Cross-refs: `scoreboards.md`, `control_codes.md`, `../instr/membar.md`.

## Field recap (from spec)
`LDG`/`STG` carry orthogonal `/SEM /SCO /PRIVATE`, fused into the 4-bit `mem`
field at **[80:77]** via `TABLES_mem_1(sem,sco,private)`.
- `SEM`: `CONSTANT=0, WEAK=1, STRONG=2, MMIO=3`
- `SCO`: `nosco=0, CTA=1, SM=2, VC=3, GPU=4, SYS=5`
- `LDS`/`STS` have **no** SEM/SCO slot — shared is physically SM-local.

## Result table — global (L1)

| PTX (`.cta` unless noted) | SASS | (sem,sco,priv) | `mem` |
|---|---|---|---|
| `ld/st.global` (weak)     | `LDG.E` / `STG.E`               | (WEAK,nosco,0)  | 0  |
| `ld/st.relaxed.cta`       | `LDG.E.STRONG.SM` / `STG.E.STRONG.SM` | (STRONG,SM,0) | 5 |
| `ld.acquire.cta`          | `LDG.E.STRONG.SM` (== relaxed)  | (STRONG,SM,0)   | 5  |
| `st.release.cta`          | `MEMBAR.ALL.CTA` + `STG.E.STRONG.SM` | (STRONG,SM,0) | 5 |
| `ld/st.volatile`          | `LDG.E.STRONG.SYS` / `STG.E.STRONG.SYS` | (STRONG,SYS,0) | 10 |
| `ld/st.mmio.sys`          | `LDG.E.MMIO.SYS` / `STG.E.MMIO.SYS` | (MMIO,SYS,0)  | 12 |

## Three key findings

**1. PTX `.cta` → SASS `.SM` (SCO=2), not `.CTA` (SCO=1).**
A CTA resides on one SM, so its L1 coherence domain is the SM. The `.CTA`
scope value (1) is not emitted for CTA-scoped generic ld/st here.

**2. acquire/release are NOT encoded in the opcode.**
`relaxed` and `acquire` global loads produce a **byte-identical** LDG
(`0x0000000402037981`). Ordering is carried elsewhere:
- **acquire load** — same `.STRONG.SM` opcode as relaxed; the *only* difference
  is the scheduling control word (`0x001eaa00…` relaxed → `0x001ea400…`
  acquire; XOR `0xe00` = usched/scoreboard bits) plus a trailing `NOP`. Acquire
  ordering is enforced by making later dependent instructions wait on the load's
  write-scoreboard, i.e. it is a **scheduling / scoreboard** guarantee, not an
  opcode-semantic one.
- **release store** — a `MEMBAR.ALL.CTA` fence is emitted **before** the strong
  store; the `STG` itself is plain `.STRONG.SM`.

**3. Shared memory collapses all orders to bare `LDS`/`STS`.**
No strong/scope suffix exists on LDS/STS (shared is SM-local; CTA-scope
coherence is structural).
- relaxed / acquire / volatile load → same `LDS`; acquire differs only in the
  control word (`0x000e2200…` → `0x000e6400…`).
- relaxed store → bare `STS`; **release store → `MEMBAR.ALL.CTA` + `STS`**.

## Acquire load — exact implementation (resolved)
Test: `tests/acq_ordering_test.cu` (acquire→independent loads / dependent load /
independent store; relaxed baseline). Control words decoded via
`control_codes.md` field map (`req_bit_set`[121:116]=wait mask,
`dst_wr_sb`[112:110]=write scoreboard).

**A `ld.acquire` is a plain `LDG.E.STRONG.SM` immediately followed by a `NOP`
whose wait-mask is set to the acquire load's own write-scoreboard.** The NOP
stalls the **entire warp's instruction issue** until the acquire load's response
has returned (its SB counter drains to 0), so no later instruction — load, store,
or ALU — can issue (hence cannot be reordered) ahead of the completed acquire.

Evidence (write-SB of acquire load → wait bit of the following NOP):
| kernel | acquire LDG `wr_sb` | NOP `wait` mask |
|---|---|---|
| `acq_then_indep` | SB3 | `001000` (SB3) |
| `acq_then_dep`   | SB2 | `000100` (SB2) |
| `acq_then_store` | SB2 | `000100` (SB2) |

Corollaries:
- The barrier is **unconditional**: it is emitted even in `acq_then_dep` where
  the later load is data-dependent on the acquire value (and would have waited on
  the scoreboard anyway). So acquire ≠ "just a true-dependency"; it is a real
  issue-order fence.
- It gates **independent** ops too: in `acq_then_indep` the two independent
  relaxed loads and in `acq_then_store` the independent relaxed store all issue
  only after the NOP drains the acquire SB.
- **relaxed baseline** (`rlx_then_indep`) has **no** such NOP: the three loads
  get **distinct** write-scoreboards (SB3/SB4/SB2) and pipeline freely; ordering
  is enforced only at the consumers (STGs wait per-SB). Under acquire the first
  independent load instead **reuses** the acquire's SB (SB3→SB3), since the NOP
  already drained it.
- No `MEMBAR` is needed at `.cta` scope: all CTA threads share the SM's L1/LSU,
  so serialising *issue* against the acquire load's completion suffices. (Expect
  `.gpu`/`.sys` acquire to additionally need a fence — not yet tested.)

## Scope scaling — `.gpu` / `.sys` (resolved)
Test: `tests/acq_scope_test.cu`. The acquire barrier **changes mechanism with
scope** — the local-issue NOP is only enough at `.cta`.

**Relaxed load** — `SCO` scales in the opcode, nothing else:
| scope | SASS |
|---|---|
| `.cta` | `LDG.E.STRONG.SM` |
| `.gpu` | `LDG.E.STRONG.GPU` |
| `.sys` | `LDG.E.STRONG.SYS` |

**Release store** — `MEMBAR.ALL.<scope>` before a `STG.E.STRONG.<scope>`, scope
scales on both:
| scope | SASS |
|---|---|
| `.cta` | `MEMBAR.ALL.CTA` + `STG.E.STRONG.SM` |
| `.gpu` | `MEMBAR.ALL.GPU` + `STG.E.STRONG.GPU` |
| `.sys` | `MEMBAR.ALL.SYS` + `STG.E.STRONG.SYS` |

**Acquire load** — barrier differs by scope:
| scope | acquire load | post-load barrier |
|---|---|---|
| `.cta` | `LDG.E.STRONG.SM`  | `NOP` (issue-stall on load's write-SB) |
| `.gpu` | `LDG.E.STRONG.GPU` | **`CCTL.IVALL`** (L1 invalidate-all) |
| `.sys` | `LDG.E.STRONG.SYS` | **`CCTL.IVALL`** |

At `.gpu`/`.sys` the acquire is a strong-scoped load **plus a local-L1
invalidation**: the STRONG.GPU/SYS load coheres at the scope's coherence point
(L2 for gpu, system for sys), then `CCTL.IVALL` flushes the SM's L1 so any
*subsequent* load — even relaxed/weak — must re-fetch fresh data through that
coherence point. That is precisely the acquire guarantee across SMs, which a
mere issue-stall cannot provide (L1 is not coherent between SMs).

Ordering is scoreboard-carried (decoded control words, acq_gpu):
- acquire `LDG.E.STRONG.GPU` → `dst_wr_sb = SB2`
- `CCTL.IVALL` → `req` wait mask = **SB2** (blocks the invalidate until the
  acquire load's data has returned), then invalidates; later loads issue after.

The `CCTL.IVALL` is **scope-agnostic** — byte-identical encoding
(`0x00000000ff00798f`) for both gpu and sys; all scope information lives in the
`LDG` `SCO` field. `CCTL` default cache = `D` (L1 data); sub-op `IVALL=4`.

## Summary
| order | `.cta` (SM/L1) | `.gpu` (L2) | `.sys` |
|---|---|---|---|
| relaxed ld/st | `LDG/STG.E.STRONG.SM` | `.STRONG.GPU` | `.STRONG.SYS` |
| **acquire** ld | strong ld + `NOP` (issue-stall) | strong ld + `CCTL.IVALL` | strong ld + `CCTL.IVALL` |
| **release** st | `MEMBAR.ALL.CTA` + strong st | `MEMBAR.ALL.GPU` + strong st | `MEMBAR.ALL.SYS` + strong st |

Scope+strength → `mem` field (opcode). Acquire → post-load barrier (NOP at cta,
L1-invalidate at gpu/sys). Release → pre-store `MEMBAR.ALL.<scope>`.

## SM-internal coherence model — is L1/shared a single arbiter or tagged/coherent?
Ran on RTX 5090 (sm_120, Blackwell); the memory model is unchanged since Turing
so the microarch answer transfers to Hopper. Tests:
`tests/sb_litmus.cu`, `tests/sb_inter.cu`, `tests/coherence_test2.cu`.

**Q:** within one SM, do the 4 sub-partitions (SMSPs) hold private cached copies
with coherence *tags*, or is L1/shared a single shared array with accesses
serialized at one arbiter/port?

**Experiment 1 — Store Buffering litmus, two actors on different SMSPs of one CTA,
tightly aligned via a shared arrival barrier** (8.19M aligned samples/config):
- relaxed `.cta` (LDG/STG.STRONG.SM) and shared LDS/STS: outcome mix of
  (0,1)/(1,0)/(1,1); **`SB(0,0)` = 0, never observed.** Fences shift the
  distribution toward (1,1) (both stores visible) but (0,0) stays 0.
- Inter-CTA control (`.gpu` scope, likely different SMs, `sb_inter.cu`): also
  `SB(0,0)`=0; `fence.gpu` forces 100% (1,1), proving the actors truly race and
  the fence works.
- ⇒ writes are **multi-copy-atomic**: no store-buffer reordering is observable at
  any scope. A store becomes visible to all observers at a single point.

**Experiment 2 — coherence/liveness across SMSPs** (producer warp0 increments a
counter 1..N; consumer warp1 spin-reads). *Must* defeat ptxas LICM: a naive weak
spin-load is **hoisted out of the loop** (weak loads carry no ordering) and reads
a register forever — a **compiler** artifact, not hardware staleness. With a
hoist-proof runtime address mask so the load genuinely re-issues:
- relaxed `.cta` **and weak** (`LDG.E`/`LDS`), global and shared:
  `maxSeen=N`, `backward=0` — every load observes fresh, strictly monotonic
  values from the peer SMSP.
- ⇒ the SM-internal L1/shared is a **single coherent structure** for all 4 SMSPs;
  there are **no private per-SMSP copies that go stale**. If tagged private
  copies existed (and `.cta` emits no invalidation, see above), a re-issued weak
  load would read a stale copy — it does not.

**Conclusion.** Model SM-internal L1/shared as **one shared array behind a single
serialization point (arbiter)** that all 4 sub-partitions funnel through — *not*
a set of per-SMSP caches kept in sync by a tag/coherence protocol:
- multi-copy-atomic writes (no observable SB) = single write-ordering point;
- weak loads stay coherent+monotonic once actually re-issued = single readable copy;
- `.cta` acquire needs no cache invalidation = L1 *is* the CTA coherence point.

The only two "incoherences" are elsewhere and consistent with this:
1. **Compiler layer** — weak (`ld` w/o `.relaxed/.acquire/.volatile`) loads are
   hoistable/CSE-able, so polling needs a *strong* qualifier for the **compiler**,
   not for the hardware.
2. **Cross-SM** — each SM has its own L1, so `.gpu`/`.sys` acquire adds
   `CCTL.IVALL` (see scope table) to flush L1 against another SM's writes; this is
   inter-SM incoherence, orthogonal to the intra-SM single-array result.

### Hardening (placement-pinned + positive-control attempts)
Test: `tests/litmus_pinned.cu`, `tests/mp_spin.cu`, `tests/mp_scope_ctrl.cu`.
- **Placement confirmed, not assumed.** Each actor reads `%smid` and `%warpid`;
  samples are counted only when the two actors are **same `%smid` and different
  `%warpid % 4`** (sub-partition). Across 6.14M counted samples, **rejected = 0**
  (example warp pairs (0,1),(2,3), same SM) — the earlier warp0→SP0/warp1→SP1
  assumption holds. `SB(0,0)` stays **0** on these confirmed cross-SMSP samples.
- **Harness is proven live/racing:** `fence.cta`/`fence.sc` measurably shift the
  SB and MP outcome distributions (e.g. SB relaxed (1,1)≈0.48M → fence.cta
  ≈2.1M), so the actors do race and the harness is ordering-sensitive.
- **Coherence pillar (strongest):** hoist-proof liveness test — a re-issued
  *weak* load already tracks the producer fresh + strictly monotonic across
  SMSPs (Exp 2). This alone rules out stale private per-SMSP copies.

**Honest limitation.** No *positive* weak-behaviour control could be produced on
this GPU: SB (intra/inter-SM), spin-until-flag MP (intra/inter-SM, relaxed, no
fence), and even a *wrong-scope* MP (inter-SM communication using `.cta` ops) all
show strong, correct, multi-copy-atomic behaviour (0 weak outcomes; `.cta`
inter-SM still propagates because `STG.E.STRONG.SM` write-throughs to L2 and
strong loads fetch fresh — scope governs *guarantees*, not *propagation*). This
is the documented reality that Volta+/Blackwell silicon is much stronger than the
PTX model permits. Consequence: "SB never observed" is *consistent with* the
single-arbiter model but cannot by itself exclude "hardware too strong to ever
show it". The conclusion therefore rests mainly on the **coherence liveness**
result + the **no-`.cta`-invalidation codegen**, with SB/MP as corroboration.

### Structural probe — store-own / load-peer, forwarding excluded
Test: `tests/sb_struct.cu`. Each actor stores its OWN cell then loads the PEER's
cell (no same-address forwarding) then loads its OWN cell (forwarding control).
Placement-confirmed same-SM / different-SMSP, 6.14M counted samples/space.
- **`self-miss = 0`** (both spaces): an actor's own store is always immediately
  visible to its own later load — forwarding / same-cycle commit works.
- **`peer(0,0) = 0`** (both spaces): never do both peer-loads miss both stores.
  Only (0,1)/(1,0)/(1,1) occur → **every outcome is explainable by one total
  interleaving of the 4 ops**; the only outcome needing a per-actor W→R slip
  (0,0) never appears.
- Global-L1 and shared behave identically (same unified SM SRAM).

**Structural conclusion.** `peer(0,0)` would require a *peer-invisible per-SMSP
store buffer* (a warp's store lingers unseen by peers while it races to its
load). It is never observed, and the codegen shows `STG` is fire-and-forget
(`wr_sb=7`, no completion wait) so nothing in the pipe *forces* the ordering —
yet peers still never see the pre-store value out of order. Most parsimonious
model: **one serialization point (arbiter) per SM into which all 4 sub-partitions'
accesses are placed in a single total order; a store is inserted at commit and is
then visible to every later load in that order (multi-copy-atomic), with no
peer-invisible store buffer.** Own-store visibility is immediate but not private.
Caveat: cannot strictly exclude "a store buffer that drains to the shared array
faster than the ~few-cycle sample window", but a peer-invisible buffer is exactly
what would yield (0,0), and it doesn't — on either space.

For the follow-on microarchitecture (MIO/LSU queue, store register lifetime, when
the store's read scoreboard releases relative to issue vs completion), see
`lsu_mio_structure.md`: stores are fire-and-forget (`wr_sb=7`), the source
register is read ~6–12 cyc after issue at an LSU latch (not held to completion),
and the arbiter is the single total-order point.

## RMW path — `atom` / `red` ordering SASS (resolved)
Test: `tests/atom_order_test.cu` (sm_90). Covers the full order×scope matrix for
global atom, shared atom, and global red. RMWs naturally inherit the barrier
patterns from both loads and stores, combined on the same instruction.
- The ATMO/REDG opcode itself carries the `.STRONG.<SCO>` scope suffix and the
  `mem` field — no separate `ld`/`st` needed.
- **acquire** → RMW + post-barrier (same as acquire load).
- **release** → pre-barrier + RMW (same as release store).
- **acq_rel** → both (same as `st.release` then `ld.acquire`).

### atom (global .add) — order × scope matrix

| PTX | `.cta` | `.gpu` | `.sys` |
|---|---|---|---|
| `.relaxed` | `ATOMG.E.ADD.STRONG.SM` | `.STRONG.GPU` | `.STRONG.SYS` (not tested, same pattern) |
| `.acquire` | ATOMG + `NOP` | ATOMG + `CCTL.IVALL` | ATOMG + `CCTL.IVALL` |
| `.release` | `MEMBAR.ALL.CTA` + ATOMG | `MEMBAR.ALL.GPU` + `ERRBAR` + `CGAERRBAR` + ATOMG | same + `.SYS` |
| `.acq_rel` | `MEMBAR.ALL.CTA` + ATOMG + `NOP` | `MEMBAR.ALL.GPU` + `ERRBAR` + `CGAERRBAR` + ATOMG + `CCTL.IVALL` | same + `.SYS` |

### atom (shared .add) — `.cta` only
Same barrier structure as global .cta atom (`ATOMS` replaces `ATOMG`):
| `.relaxed` | `ATOMS.ADD` |
|---|---|
| `.acquire` | ATOMS + `NOP` |
| `.release` | `MEMBAR.ALL.CTA` + ATOMS |
| `.acq_rel` | `MEMBAR.ALL.CTA` + ATOMS + `NOP` |

### red (global .add, write-only) — no acquire variant (no read side)
| PTX | `.cta` | `.gpu` |
|---|---|---|
| `.relaxed` | `REDG.E.ADD.STRONG.SM` | `.STRONG.GPU` |
| `.release` | `MEMBAR.ALL.CTA` + REDG | `MEMBAR.ALL.GPU` + `ERRBAR` + `CGAERRBAR` + REDG |

Note: `red` lacks `.acquire` (no value read back, per spec §8.11.1), so the
load-side post-barrier is absent. `.acq_rel` on red would be equivalent to
`.release`.
- `ERRBAR` / `CGAERRBAR` appear only on GPU/SYS release/acq_rel — they are
  scope-barrier companions (error-barrier + cooperative-grid-array error
  barrier), not present on CTA (the SM-local CTA domain does not need them).
- `atom_cas_acqrel_gpu` follows the same pattern (MEMBAR + ERRBAR + CGAERRBAR +
  ATOMG.CAS + CCTL.IVALL), so CAS also conforms.

### Observed rule
All 4 RMW forms (global atom, shared atom, global red, atom CAS) follow exactly
one template:
```
relaxed = RMW_OP.STRONG.<SCO>
acquire = RMW_OP.STRONG.<SCO>  + {NOP(CTA) | CCTL.IVALL(GPU/SYS)}
release = MEMBAR.ALL.<SCO> [+ERRBAR+CGAERRBAR] + RMW_OP.STRONG.<SCO>
acq_rel = MEMBAR + RMW_OP + CCTL/NOP   (both, only available when RMW reads back)
```
where `ERRBAR`/`CGAERRBAR` accompany MEMBAR at GPU+ scopes only.

### ERRBAR / CGAERRBAR — error-report barriers (why they exist)
Test: `tests/errbar_probe.cu`. They are **general companions of `MEMBAR` at gpu+
scope**, not release-specific:

| C call | SASS |
|---|---|
| `__threadfence_block()` (cta) | `MEMBAR.SC.CTA` |
| `__threadfence()` (gpu) | `MEMBAR.SC.GPU` + `ERRBAR` + `CGAERRBAR` + `CCTL.IVALL` |
| `__threadfence_system()` (sys) | `MEMBAR.SC.SYS` + `ERRBAR` + `CGAERRBAR` + `CCTL.IVALL` |

Both are standalone `mio_pipe` instructions, no operands, `usched=DRAIN`; ERRBAR
is `COUPLED_MATH`, CGAERRBAR is `DECOUPLED_BRU_DEPBAR`; neither has a scope field.

**Inference (to be experimentally verified — see `tests/errbar_fault_patch/`):**
1. ERRBAR/CGAERRBAR are **error-report synchronization barriers**, not ordering
   ops. Stores are fire-and-forget (`wr_sb=7`) — the warp never waits for a
   store's fault status. A `MEMBAR` at gpu+ scope must guarantee prior writes are
   both *visible* and *correct*, so `ERRBAR` drains the MIO pipe and surfaces any
   accumulated write faults (DRAM ECC, bad translation, illegal address) into
   precise per-warp error state at the barrier point.
2. `CGAERRBAR` does the same for cluster-scale (CGA) fabric errors.
3. `.cta` needs neither: writes stay in the SM's L1, faults are local and
   deterministic.
4. `ERRBAR` has no scope because it only drains *this SM's* outstanding writes;
   scope lives on the preceding `MEMBAR`.

**Planned verification (SASS patching).** Construct `STG [invalid]; MEMBAR;
ERRBAR; CGAERRBAR; STG …`, then patch a malformed/illegal instruction at two
positions and compare the fault attributed by the runtime:
- Sequence A: `STG[invalid]; MEMBAR; <illegal instr>; ERRBAR; …`
- Sequence B: `STG[invalid]; MEMBAR; ERRBAR; <illegal instr>; …`
If ERRBAR is the point that materialises the store fault, then A should still
raise an illegal-instruction error (fault not yet collected), while B should
raise the illegal-**memory-access** error first (ERRBAR already surfaced the bad
store before the illegal instr executes). The exit reason (illegal instruction
vs illegal memory access) reveals whether ERRBAR is the fault-collection point.

**Verification result — two fault classes; barriers surface the async one.**
Test: `tests/errbar_fault_patch/` (SASS binary patcher + Driver-API launch;
opcode-0 = illegal instruction, error 715; illegal-memory-access = 700).
The first attempt used an **unmapped** wild address, which turned out to be the
wrong fault class. Using the CUDA VMM API to map a page **read-only**
(`cuMemSetAccess` PROT_READ) then storing to it exposes the right class.

Two distinct fault behaviours:
- **Synchronous** — unmapped address / translation fault. `STG[bad]; <illegal>`
  with *no* barrier → **700**: the warp is killed at the faulting store before
  executing the next instruction. Barrier-independent (patching MEMBAR/ERRBAR/…
  to illegal all still 700). Address translation faults land at the memory pipe
  synchronously.
- **Asynchronous** — permission fault (store to a mapped read-only page).
  `STG[ro]; <illegal>` with *no* barrier → **715**: the warp **continues past**
  the store and executes the illegal instruction. The posted write's permission
  violation is detected later on the write path; the fault is surfaced only at
  the next memory-drain barrier (or at kernel EXIT — it is never lost).

Walking an illegal instruction through `STG[ro]; MEMBAR; ERRBAR; CGAERRBAR; CCTL;
STG[good]` (async RO fault):

| illegal replaces | MEMBAR present? | result | meaning |
|---|---|---|---|
| MEMBAR (right after store) | no | **715** | fault not yet collected |
| ERRBAR (after MEMBAR) | yes | 700 | MEMBAR already collected |
| CGAERRBAR / CCTL / good-store | yes | 700 | collected |
| ERRBAR slot, MEMBAR nop'd out | no | **715** | not collected yet |
| CGAERRBAR slot, MEMBAR nop'd out | no | 700 | **ERRBAR** collected it |

Interpretation: **both `MEMBAR.SC.GPU` and `ERRBAR` act as memory-drain barriers
that force a pending asynchronous write fault to register** — the fault surfaces
at whichever drain executes first after the store. In the compiler's emitted
sequence MEMBAR is first, so it is the de-facto collection point; remove it and
ERRBAR does the job. So the original "barriers surface the posted-store fault"
intuition is **confirmed for asynchronous (permission/durability) faults**, but
the collector is **not uniquely ERRBAR** — MEMBAR.SC also drains. ERRBAR /
CGAERRBAR are additional error-drain coverage (CGA fabric + gpu/sys error
classes) that the compiler pairs with every gpu+ `MEMBAR`.

Corollary: the store's `wr_sb=7` fire-and-forget (`lsu_mio_structure.md`) is why
the async permission fault is posted and the warp runs on — completion (and its
error status) is not tracked at the store; a drain barrier is what waits for it.

**DSMEM fault validation** (`tests/errbar_fault_patch/dsmem_probe.cu`,
`dsmem_fence.cu`, `dsmem_walk.cu`). An invalid `st.shared::cluster` to a
non-existent peer rank produces an **asynchronous cluster-fabric fault** (error
719, "unspecified launch failure" — distinct from IMA=700). The warp continues
past the DSMEM store; the fault is collected by **any** memory-drain barrier
(`MEMBAR.SC.CTA` alone suffices, even without CGAERRBAR). Without a barrier the
fault surfaces at the nearest implicit drain or kernel exit.

So CGAERRBAR is *sufficient* but not *necessary* for draining a cluster-fabric
write fault — the pending error is CTA-local state that any drain catches.
CGAERRBAR's reason-to-exist on CGA-capable archs: (a) a dedicated CGA-fabric drain
path (latency/coverage), and (b) it is paired with every `MEMBAR`@gpu+ because a
gpu+ barrier must also account for the cluster path this CTA may have in-flight
writes on — the compiler cannot know at compile time whether the kernel uses
DSMEM, so it emits conservatively on all CGA-capable archs.

## History / retracted hypotheses

> Claims below were **superseded, refuted, or never settled** by later work; they are kept
> for provenance. Do not cite them as current.

## Open questions
- **Resolved: the acquire barrier is never folded.** Test `tests/acq_fold_test.cu`
  (sm_90). Five variants (use, indep, load, atom, fence) × two scopes, all show
  the `NOP`/`CCTL.IVALL` as a dedicated standalone instruction. Even when the
  next instruction is data-dependent on the acquire result (would naturally wait
  on the same write-scoreboard), ptxas still emits the barrier NOP. Adjacent
  `CCTL.IVALL` (from acquire + from fence) are both present — no merging.
  The acquire barrier is modelled as an unconditional issue-drain point, not an
  ordering constraint on a specific consumer.
- A genuine positive weak-behaviour control on Volta+ (may require mixed-proxy /
  texture path, or async-copy, rather than plain generic-proxy ld/st).

