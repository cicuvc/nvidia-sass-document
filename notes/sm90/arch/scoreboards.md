# Scoreboards — the variable-latency dependency mechanism (sm_90)

Consolidates how the 6 scoreboards work, refining the widely-known Volta+ model.
Cross-refs: `control_codes.md` (field layout), `usched_latency.md`
(fixed-latency stalls), `../instr/f2i.md`, `../instr/depbar.md`.

## The baseline model (correct)
- **6 scoreboards** `SB0..SB5`, each a **counter** (not a flag). Index is 3-bit
  (`6/7 = INVALID`).
- **Write barrier** (`dst_wr_sb`, 3-bit, 7=none): a variable-latency producer
  (e.g. `LDG`) **increments** the named counter at issue, **decrements** it when
  its result is written back.
- **Read barrier** (`src_rel_sb`, 3-bit): an instruction that reads its source
  registers *late* (e.g. `STG` reads the store-data late) **increments** at
  issue, **decrements** when the register read completes.
- **`req_bit_set`** (6-bit, one bit per SB): the instruction may not issue until
  **every** scoreboard whose bit is set has counter **== 0**. It is an AND over
  the masked scoreboards and it gates the whole warp's issue.
- **`DEPBAR.LE SBn, m`**: explicit test — wait until counter `SBn ≤ m`
  (partial drain), vs the `req` mask's implicit `== 0`.

## Refinements / additions (what the summary should also say)

**1. Scoreboards are ONLY for variable-latency ops.** Fixed-latency instructions
(FADD, IADD3, FFMA, HMMA, …) never set a scoreboard (`dst_wr_sb=7`). Their
latency is dead-reckoned by the compiler as `usched` **stall counts** (see
`usched_latency.md`). The two mechanisms coexist: stalls for statically
known latency, scoreboards for data-dependent latency (memory, MUFU converts
`F2I/I2F/F2F`, `S2R`, tensor loads, async copy).

**2. One scoreboard is shared by many in-flight ops** — this is *why* it is a
counter. Verified: a single `SB5` tracked **14 concurrent `LDG`s** in one block;
`req` on SB5 then waits for all 14 to retire (counter→0), and `DEPBAR.LE SB5, k`
waits for all-but-k. The compiler batches similar ops onto one SB to conserve
the scarce 6.

**3. Producer/consumer are coordinated by the compiler.** The producer names the
SB in `dst_wr_sb=k`; the later consumer sets `req` bit `k`. ptxas allocates the 6
SBs like registers (allocate at the variable op, free once all waiters passed).
A hazard's `req` sits on whichever instruction is the *later* party:
- **RAW** (read-after-write): consumer of the value → waits the **write** SB.
- **WAW** (write-after-write): a later writer of the same reg also waits the
  **write** SB (so writebacks can't reorder). *The write barrier guards WAW too,
  not just RAW.*
- **WAR** (write-after-read): a later writer of a register that a slow
  instruction still needs to read → waits the **read** SB. This is the whole
  purpose of the read barrier.

**4. A fixed-latency op can still carry `req`.** When a fixed-latency op consumes
a variable-latency result (e.g. `DFMA` waiting on a load), it sets `req` even
though it sets no scoreboard itself (10–32% of math ops in cuBLAS carry a wait
mask). So `req` appears on both fixed and variable consumers.

**5. In-order-queue economy.** Ops in the same execution queue retire in program
order, so waiting on the **newest** producer's SB transitively guarantees older
same-queue producers are done. ptxas therefore scoreboards only *sync-point*
producers and leaves the rest at `dst_wr_sb=7`. Verified with `F2I`: in a chain,
only some F2I set a SB; the consumer waits on the latest, covering all earlier
(`../instr/f2i.md`). This lets one counter stand in for a run of ops.

**6. One instruction can wait and set simultaneously.** `req` (wait) and
`dst_wr_sb`/`src_rel_sb` (set) are independent fields — e.g. an op can wait on
SB2 and set SB3 in the same issue.

**7. Async copy counts GROUPS, not per-issue.** `LDGSTS` (cp.async) does **not**
take an ordinary write SB at issue; instead `LDGDEPBAR` (`cp.async.commit_group`)
increments a **group** counter on a scoreboard once per *group*, and
`DEPBAR.LE SBn, k` (`wait_group k`) drains to k. Verified with asymmetric groups
of 4/1/2 copies: `wait_group 2/1/0` → `DEPBAR.LE SB0, 2/1/0` — `cnt` = the group
count, independent of ops-per-group (all groups bind to one SB). Because raw
loads can complete out of order, this group-level counting is what makes the
count deterministic (`../instr/depbar.md`).

**8. Counter range.** `DEPBAR.LE`'s threshold `cnt` is 6-bit ([43:38], 0–63), so
a scoreboard counter meaningfully ranges to at least 63 — consistent with the
14-deep case observed and deep async pipelines.

**9. `req`/DEPBAR division of labour.** The `req` mask (free, on the consuming
instruction, `==0` semantics) handles the common case. `DEPBAR` is emitted only
when you need what `req` can't express: counted/partial drains (`≤N`, async
multi-buffering), draining a *set* of scoreboards with no natural consumer, or a
dynamic (uniform-register) threshold.

**10. Checker implication (AUTO_DEP_ANALYSIS §5a.4).** For the assembler's
dependency checker, `req` / `DEPBAR.LE SBn, 0x0` are *exact kills* of all
outstanding claims on SBn, but `DEPBAR.LE SBn, m (m>0)` grants **no per-claim
coverage** — the ≤m surviving claims have unknown identity (completion is not
program-ordered), so a consumer relying on a partial drain alone must still be
flagged as missing its `req`.  A partial drain contributes only a count fact
(in-flight upper bound `ub[SBn] ≤ m`), which a separate count lattice uses for
tally-capacity checks, not for data-dependency clearance.

## Field recap (per `control_codes.md`)
`req_bit_set`[121:116] · `src_rel_sb`[115:113] · `dst_wr_sb`[112:110]
(`VarLatOperandEnc`, 7=none). `DEPBAR.LE`: `sbidx`[46:44], `cnt`[43:38],
`scoreboard_list`[37:32].

## Virtual Queue vs Pipe — and why scoreboard ops need a VQ

Two orthogonal execution attributes per CLASS, from different spec files:

- **VQ** (`VIRTUAL_QUEUE`, `sm_90_instructions.txt` `PROPERTIES`) — the
  execution-queue identity: `VQ_AGU`, `VQ_TEX`, `VQ_MUFU`, `VQ_CBU`,
  `VQ_FMA64`, `VQ_HMMA/IMMA/DMMA/UMMA`, `VQ_UNORDERED`, plus the
  `*_UNORDERED_WR` set (`VQ_AGU_UNORDERED_WR`, `VQ_ATOM_UNORDERED`,
  `VQ_TMA_UNORDERED_WR`, `VQ_SYNCS_UNORDERED_WR`).  The `*_UNORDERED*`
  flavours encode that the queue executes out of order (relaxed memory
  ordering).  **Not every instruction has one** — FFMA/IADD3/IMAD report
  `VIRTUAL_QUEUE=None`.
- **Pipe** (`sm_90_latencies.txt` `OPERATION SETS`) — functional-unit
  grouping (`int_pipe`, `fmalighter_pipe`, `fp16_pipe`, `mio_pipe`,
  `cbu_pipe`, `udp_pipe`, `fma64lite/heavy_pipe`, `fe_pipe`) used **only as
  the row/column index into the latency matrices**
  (`TABLE_TRUE/OUTPUT/ANTI`), combined with `MD_PRED(ISRC_*_SIZE)` range
  formulas from the instruction `PREDICATES`.  Every instruction belongs to
  ≥1 pipe.

Short hand: **VQ says which queue it runs in (execution identity, incl.
ordering), Pipe says how many cycles it takes (latency index)**; `INST_TYPE`
says whether the consumer must wait on a scoreboard.  VQ is finer-grained
(≈40 enum values vs ~10 pipes).  VQ and pipe usually agree (VQ_AGU → mio_pipe,
VQ_CBU → cbu_pipe, VQ_HMMA → fp16_pipe, VQ_UDP → udp_pipe) but are not bound:
`USETSHMSZ` is `udp_pipe` yet `VIRTUAL_QUEUE=$VQ_UNORDERED`.

**Empirical invariant (all 1167 sm_90 CLASSes): a scoreboard op implies a VQ.**

| INST_TYPE | has VQ | no VQ |
|-----------|--------|-------|
| `DECOUPLED_*` (RD_WR/RD/WR/BRU_DEPBAR …) | 575 | **0** |
| `COUPLED_MATH` (FFMA/IADD3/…) | 4 | 549 |
| `COUPLED_EMULATABLE` (HMMA/QMMA/DMMA…) | 39 | 0 |

So **`dst_wr_sb`/`src_rel_sb`/`req` (the variable-latency scoreboard
mechanism) are only ever present on instructions that also name a VQ** —
the VQ is the queue whose completion event the scoreboard waits on; a
DECOUPLED result has data-dependent latency, so it must carry a VQ to have
somewhere to complete.  The converse is false: **a VQ does not imply
scoreboard semantics**.  (a) tensor ops are `COUPLED_EMULATABLE`
(`VQ_HMMA/IMMA/DMMA/REDIRECTABLE`, 39) — they queue like variable ops but
their latency is compiler-known (fixed stall/NOP pad, cf. `hmma_pipeline.md`),
so no `dst_wr_sb`; (b) four `COUPLED_MATH` outliers carry VQs for
synchronization semantics without variable latency: `ENDCOLLECTIVE`
(VQ_CBU), `R2UR` (VQ_AGU), `UCGABAR_WAIT`, `USEL` (VQ_UNORDERED).

Mental model: **VQ is the carrier, scoreboard is the tracking** — VQ is
necessary for the scoreboard, not identical to it.

## Open questions
- Exact decrement timing (issue+fixed vs true writeback) per op class.
- Whether the read-barrier is ever used for operand-collect of ordinary loads or
  only for stores / async / late-read ops (only `STG`/`LDGSTS`-style seen so far).
- Whether the DECOUPLED⇒VQ invariant holds on sm_120.  The sm90 numbers above
  were parsed from the raw `sm_90_instructions.txt` (the `sm90.json`/`sm120.json`
  extractors do **not** carry `VIRTUAL_QUEUE`, so it cannot be verified from the
  JSON DB); the sm120 raw dump is not on hand, and nvcc-emitted SASS for
  DECOUPLED ops (`ATOM`/`LDG`/…) shows `wr`/`rd`/`req` scoreboard fields, so the
  VQ side is inferred, not yet verified from a sm120 text dump.
