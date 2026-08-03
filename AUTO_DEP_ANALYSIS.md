# AUTO_DEP_ANALYSIS — automatic scoreboard/dependency checking for the SASS assembler

Status: **implemented** (`assembler/sass_depcheck.py`, V2 CFG, default-on as
warning).  Catches missing `req`/`wr`/`rd` scoreboard usage in hand-built
SASS — the class of bug that made `S2R` read garbage and `LDG` fault
`ILLEGAL_ADDRESS` (700) before the manual fixes (`tests/asm_construct/test_s2r.py`,
`test_ldg.py`).  `tests/asm_construct/test_depcheck.py` covers the §7.6
negative/positive cases plus control-flow (BRA / BSSY / BSYNC) paths; the
full `tests/asm_construct` suite stays green with the checker on.

**Implemented deviations from the design** (all conservative/behavioral, no
loss of the §5a safety result):
1. **Count lattice is conditional.**  The per-SB `ub` upper bound and the
   `sb_capacity` diagnostic only engage when the kernel contains a
   `DEPBAR.LE SBn, cnt (cnt>0)` partial drain.  Without DEPBAR the count has
   no observer and — since hardware drains `wr`/`rd` on completion with no
   static completion event — it would monotonically accumulate to the 63 cap
   in every loop (massive false `sb_capacity`).  With no partial drain the
   identity lattice alone is exact, per §5a.2.
2. **`rd` claims cover only data sources.**  For `DECOUPLED_RD_SCBD` /
   `DECOUPLED_RD_WR_SCBD` instructions the late-read `rd` claim is limited to
   the *data* operands (`Rb`/`Rc`/…); address bases (`[Ra+off]`) and
   descriptor uniforms (`desc[URx]`) are read at issue, so a later writer to
   an address register is not an anti-dependency.  This removes the bulk of
   false `anti_dep` from store-heavy loops.
3. **`missing_wr_sb` uses a whole-kernel suffix scan** for "is the result
   consumed", so it is a clean positive even across blocks.
4. **Branch edges**: `BRA` → target + (predicated) fall-through; `BSSY Bn,t`
   → linear fall-through; `BSYNC Bn` → edge to the matching `BSSY Bn`
   reconvergence target; `BRX`/`JMP` → conservative any-successor.  All CFG
   paths are treated as feasible (§5a.3 may-analysis).

Two versions are planned (§7, §8): **V1 linear checker** (straight-line
kernels, warnings + strict mode) and **V2 CFG checker** (full gen/kill
dataflow once label/branch support lands). The decidability question is
resolved in §5a: the safety check is exactly reaching-definitions — decidable
and polynomial; the scoreboard counters are a bounded self-draining token
system, not Minsky counters. `DEPBAR.LE` partial drains (`imm > 0`) break
kill-exactness and are handled by a mandatory second count lattice (§5a.4).

## 1. The scoreboard model (formal)

There are 6 scoreboards SB0..SB5 (field `req_bit_set` [121:116], 1 bit each;
`src_rel_sb`/`dst_wr_sb` [115:113]/[112:110], 3 bits, 7 = none).  Each SB is a
**counter starting at 0**.  The scheduler enforces, in program order:

- **`req` (wait list, before issue):** the instruction may issue only when
  every SB in its `req` list has counter 0.
- **`wr` (write scoreboard, at issue):** increment the SB counter; decrement
  it when the instruction has written its result back to RF.  The writeback
  is only *valid* once the counter returns to 0 (a consumer's `req` waits for
  this).
- **`rd` (read scoreboard, at issue):** increment the SB counter; decrement
  it once the instruction has **read all its operands** (late reads, e.g. a
  store reading its data register).  A later writer to those registers must
  `req` this SB so it does not clobber operands the reader still needs.

Because issue is in-order, once an earlier instruction's `req` SBs are all
zero at its issue point, every *later* instruction can be treated as seeing
those SBs satisfied too — until an SB is again used as a `wr`/`rd` target.
So the analysis is over *outstanding* SB uses, not raw counts.

## 2. Why it matters — the two motivating bugs

- `S2R` is `INST_TYPE_DECOUPLED_RD_WR_SCBD` (variable latency).  ptxas emits
  `S2R R7, SR_TID.X &wr=0x0` (set SB0) and the FIRST consumer waits
  `&req={0}`.  Without the wait, the S2R result is garbage; an address
  derived from it faults.
- `LDG` is also `DECOUPLED_RD_WR_SCBD` and additionally depends on the
  `desc[UR4]` descriptor loaded by a variable-latency `LDCU.64 UR4`.  The
  LDG must `req` that descriptor's SB (or the policy is garbage → 700) and
  set a `wr` SB for its result, waited by the first user of the loaded
  register.

Both are fixed *manually*.  An auto-check should detect such gaps.

## 3. What the checker must know per instruction

1. **Register def/use**: dest registers (incl. `.64/.WIDE/.128` pairs),
   source registers, predicates written (`Pu`, `Pv`) vs read (`Pp`, `Pg`).
2. **Latency class** from `INST_TYPE` (sm90 PARAMETERS):
   - `COUPLED_MATH` (0): fixed latency → no SB protocol (consumers rely on
     stall counts).
   - `DECOUPLED_RD_SCBD` (1): `req` on inputs; no result SB.
   - `DECOUPLED_RD_WR_SCBD` (2): `req` on inputs **and** result `wr`.
   - `DECOUPLED_WR_SCBD` (5) / `*_NOREQ_SCBD` (6-8): variants with weaker
     `req` obligations.
3. **The SB protocol rules** to check:
   - Every register read by a `DECOUPLED_*` instruction must have its
     variable-latency producer's `wr` SB in the reader's `req` list (or a
     prior in-order `req` that covers it).
   - Every variable-latency result register must have a `wr` SB, and the
     first consumer that reads it must `req` it.
   - A variable-latency *reader* (store / gather address / descriptor) must
     `req` the producers of the registers it reads late; a later writer to
     those registers must `req` the reader's `rd` SB.
   - Reuse discipline: an SB must not be re-targeted by a new `wr`/`rd`
     before its prior outstanding use is `req`-waited.

## 4. Prerequisite: labels / control flow

The assembler has no label→branch support yet (parses `_label_` placeholders
only).  Any sound analysis needs a **CFG**: `BRA`/`BRX`/`BSSY` targets,
fall-through, and the per-path live/sb state.  Until branches exist, only
straight-line kernels can be checked.  (Superseded by §6: label/branch
support is deferred to V2 — §8; V1 checks straight-line kernels first.)

## 5. Complexity / decidability — resolved (see §5a)

- **Register aliasing**: pairs (`R2.64`), `RZ`, predicates, `.reuse`,
  scoreboard *sharing* (one SB tallying many producers) all blur a simple
  def/use chain.  Handled by per-register claim tracking with width
  expansion (§7.2) — SASS register operands are literal, so def/use is
  exact; there is no indirection.
- **Control flow**: a `req`-wait on one path may be missing on another.
  Handled by union-join may-analysis in V2 (§8).
- **Memory**: pointer-derived addresses (`LDG [R6.64+off]`) make operand
  provenance data-flow-dependent, not just register-adjacency dependent.
  Out of scope: the SB protocol is register-focused; address provenance is
  not checked.
- ~~**"Possibly undecidable"**~~ — **resolved, decidable.**  See §5a.

## 5a. Decidability: the check IS decidable (reaching-definitions)

The earlier worry was "the counter model is a *count*, not a boolean, so
abstract interpretation must bound the tally" and loop-carried counts might
not terminate.  Two observations close the question.

### 5a.1 Net-zero: counters are a bounded self-draining token system

**In normal operation, every instruction's net contribution to every
scoreboard counter is eventually 0.**  Each `wr`/`rd` increment at issue is
necessarily paired with a hardware decrement (writeback completes / all
operands read).  Consequences:

- A counter is not a Minsky counter over unbounded naturals; it is the
  size of a *multiset of in-flight completions*, bounded by hardware
  (pipeline depth, tally width) — range `[0, K_hw]`.  Even exact-count
  questions ("can this SB exceed K?") live in a finite domain and are
  decidable.  Turing-completeness concerns do not apply.
- **`req` is an observation point, not the cause of clearance.**  Claims
  die on their own (hardware liveness); `req` is merely the earliest
  program-order point that *proves* a claim dead.  This is exactly why
  "req acts as kill" is the correct *static* abstraction: with timing
  unknown, a claim is possibly-outstanding at every point until a `req`
  on its SB executes, and certainly-dead afterwards (counter==0 asserted
  + in-order issue).
- **Liveness checks vanish.**  No "SB left nonzero at EXIT" diagnostic
  (hardware drains automatically); a `req` on a never-incremented SB is a
  benign no-op (do not warn); **SB waits alone cannot deadlock** (they
  wait on a guaranteed hardware event — deadlock analysis belongs to the
  barrier/BSSY domain, out of scope).
- Predication is consistent: a predicated-off instruction contributes
  0+0 per thread, so per-thread net-zero holds and the MAY-claim model
  (§5b) stands.

### 5a.2 The safety property is a regular path property

The checkable property — "a consumer never reads a register before its
variable-latency producer's writeback" — reduces under the protocol to a
purely program-order statement: *between the producer's `wr` and the
consumer's read, on the executed path, there is a `req` on that SB.*

That is a textbook **gen/kill dataflow problem isomorphic to reaching
definitions**:

- producer `wr` = *gen* (a claim: instruction identity × kind × SB);
- `req` on SB s = *kill* of all outstanding claims on s (exact for the
  zero/nonzero question — no information loss, because `req` waits for
  the full tally; this is the `imm = 0` case, see §5a.4 for
  `DEPBAR.LE` with `imm > 0`);
- consumer read = *use* requiring coverage;
- join at control-flow merges = **union** (may-analysis: conservative,
  reports all potential gaps, never misses one).

The domain is a finite powerset lattice (claims are identified by
instruction, not by count), transfer functions are monotone, so fixpoint
iteration **terminates** (≤ |claims| × |blocks| rounds; bitvector
implementation is polynomial).  Loops need no special handling: a claim
regenerated by the same instruction each iteration is idempotent in the
set, and a `req` inside the loop correctly kills prior-iteration
outstanding claims.

**SB re-targeting is safe by counter semantics.**  A `wr` on an SB with
outstanding tallies just enlarges the multiset; a later `req` waits for
*all* of them.  Re-targeting therefore over-waits (safe, possibly slow),
never under-waits — the set model loses nothing for safety, only the
ability to flag over-waiting (a perf concern, addressable with the
count lattice §5a.4).

### 5a.4 DEPBAR.LE: kill-exactness holds only at imm=0

`DEPBAR.LE SBn, imm` waits for `counter ≤ imm`; the `req` mask is the
`imm = 0` special case (see `notes/sm90/arch/scoreboards.md`).  The
kill-exactness argument in §5a.2 relies on `counter == 0 ⇔ no outstanding
claim`, so it holds **only for imm = 0**:

- **`DEPBAR.LE s, 0x0`** (= `req`, `cp.async.wait_group 0`) — exact kill,
  same as the `req` mask.
- **`DEPBAR.LE s, imm (imm > 0)`** — a *partial* drain: afterwards up to
  `imm` claims remain outstanding, and **their identity is unknown**
  (memory writeback is not program-ordered; the counter decrements on
  completion events, not by claim — `scoreboards.md` §7).  A partial wait
  therefore grants **zero identity coverage**: every prior claim on s
  stays possibly-outstanding in the may-analysis.  A consumer relying on
  a partial wait as its only sync is still flagged `missing_req` —
  correctly, since the surviving claim may be exactly the one it reads:
  ```
  LDG R8, [a]; wr=SB0        ; claim C1
  LDG R9, [b]; wr=SB0        ; claim C2
  DEPBAR.LE SB0, 0x1         ; ≤1 outstanding — but it might be C1
  IADD3 R10, R8, RZ; [no req]; reads R8 — C1 possibly not written back
  ```
- What a partial wait *does* give is a **count fact**: it blocks until
  `counter ≤ imm`, so afterwards the in-flight upper bound is
  `ub[s] := min(ub[s], imm)`.  That requires a second, count-based
  lattice (§7.3/§7.4 steps 6b+8, §8.2 — mandatory, not optional).

**Checker structure becomes a product of two lattices**, both finite →
decidable and polynomial unchanged:

| lattice | domain | transfer | diagnostics |
|---------|--------|----------|-------------|
| identity (original) | powerset of outstanding claims | kill **only** on imm=0 waits; gen on `wr`/`rd` | `missing_req`, `anti_dep`, `divergent_retarget` |
| count (new) | per-SB capped upper bound `ub ∈ {0..63, >63}` | `wr`/`rd`: +1; `DEPBAR.LE s,imm`: `min(ub,imm)`; `req`/imm=0: 0; merge: max | `sb_capacity` (tally overflow), statically-satisfied no-op hint |

DEPBAR.LE adds no increment (pure observer), so the net-zero property
(§5a.1) is untouched, and with the count capped the product domain stays
finite — the §5a.3 bottom line stands.

### 5a.3 Where inexactness remains (and why it is acceptable)

1. **Path feasibility.**  Data-dependent branch conditions (`@P0 BRA`
   with `P0` from runtime data) make exact path enumeration undecidable
   in general.  Standard fix: treat all CFG paths as feasible → possible
   false positives (missing-`req` reported on an infeasible path), never
   false negatives.  This is the generic static-analysis boundary, not
   specific to scoreboards.
2. **Hardware timing.**  Writeback latency is data-dependent (memory
   system); we check *protocol conformance*, a structural property, not
   actual RF state.  A violating program may still run correctly by luck
   of timing — so diagnostics mean "potential stale read", not "certain
   fault".

**Bottom line:** protocol safety checking is decidable and polynomial
(reaching-definitions); liveness is free from hardware; the only
approximation is path feasibility, which every static analysis shares.
The §5 "possibly undecidable" concern is retired.

## 5b. Predication and ITS warp-splitting (per-thread scoreboards)

Volta+ ITS (independent thread scheduling) makes the scoreboard counters
**per-thread**, and the scheduler may **split the warp**: a consumer can
issue on the threads whose `req` SBs are all zero while other threads still
wait.  Example:

```
MOV32I R2, 0x12345678        ; R2 = default value
@P1    S2R R2, SR_TID.X      ; SB0 set ONLY on threads where P1 holds
< ... uses of R2 ... >       ; must req={0} before reading R2
```

For threads with P1=false, SB0 stays 0 and R2 holds the MOV32I value — they
may issue the consumer immediately (ITS split).  For P1=true, SB0 is set
until the S2R writes back; they must wait.  The *same* SASS is correct for
both, precisely because the wait is per-thread.

Checker implications:

- **Predicated SB effects are MAY-effects, not MUST-effects.**  A
  predicated variable-latency producer "may set SB" → the consumer's `req`
  is still *required* (the threads that executed the producer need it).
  The checker must never drop a `req` because a producer was predicated.
  This is a must-analysis on req-presence (conservative union over the
  predication).
- **Predication introduces a hidden control split** before a real CFG even
  exists: `@P1` forks the thread set, and each arm has its own SB state.
  For straight-line analysis, treat a predicated `wr`/`rd`/`req` as applying
  to a "may" subset, and require the `req` whenever the SB may be set.
- **Divergent re-targeting is the hazard**: if an unrelated instruction
  later `wr`s the same SB that the predicated producer set on a *subset* of
  threads, the per-thread counters can diverge and the ITS split exposes a
  consumer to a stale/never-waited value on some threads.  The checker must
  conservatively forbid (or flag) SB re-targeting before the prior may-set
  use is req-waited on every path/thread set.

### 5b.1 Empirical test — does the scheduler split the warp? (SM120)

Probe (`@P0 LDG` injected into a ptxas cubin via binary patch; cold 64 MB
strided loads; 20-iter post-load FADD loop; ncu with root):

| metric | pred (16/32 lanes load) | all (32/32 lanes load) |
|--------|:--:|:--:|
| `gpu__time_duration` | 2.46–2.50 µs | 2.50–2.53 µs |
| `smsp__warp_issue_stalled_long_scoreboard_per_warp_active` | 38.8–40.4 % | 41.8–47.3 % |

The predicated kernel (only half the lanes set the load's SB) stalls on the
long scoreboard just as much as the uniform-load kernel, and runs in the same
time.  **The scheduler does NOT split the warp at a divergent scoreboard
wait — it stalls the whole warp until the req SBs are satisfied.**  (The
small pred edge, ~2% faster / ~3% less stall, is consistent with half the
loads being issued, not with thread-level splitting: a true split would
collapse the long-scoreboard stall toward ~0% and hide the load behind the
post-load loop.)  Supports the wait-not-split microarchitecture for the
checker: a predicated variable-latency producer must still be treated as
setting its SB for the *warp*, and the consumer's `req` is mandatory.
Caveat: single-warp test; multi-warp latency hiding is the SM scheduler's
normal mechanism and does not change the per-warp wait behavior.

## 6. Prerequisites status

- ~~Labels / control flow~~ — deferred to V2.  V1 checks straight-line
  kernels only; every current `tests/asm_construct` kernel is
  branch-free, so V1 covers the whole existing test suite.
- The checker runs **after matching** (needs `variant.properties`), so it
  consumes the same `(ParsedInstruction, MatchResult)` pairs the encoder
  already produces.  All required inputs exist today:
  - `ParsedInstruction.sched` (`wr_sb`, `rd_sb`, `req_bits`) and
    `pred`/`pred_not` — parsed (`assembler/operand.py`);
  - `variant["properties"]["INSTRUCTION_TYPE"]` — latency class per
    variant, mapped to numbers via `db["constants"]["INST_TYPE_*"]`
    (0 = `COUPLED_MATH`, 1 = `DECOUPLED_RD_SCBD`,
    2 = `DECOUPLED_RD_WR_SCBD`, 5 = `DECOUPLED_WR_SCBD`, 6-8 = `*_NOREQ_*`);
  - `variant["format"]["slots"]` — stable slot naming for def/use roles
    (`Rd`/`Rd2`/`URd`/`Pu`/`Pv` vs `Ra`/`Rb`/`Rc`/`Re`/`URa`/`Sb`/`Pg`);
  - `MatchResult.slot_map` — resolved register numbers per slot.

## 7. V1 — linear checker (straight-line kernels)

Forward symbolic simulation of outstanding SB claims over the instruction
sequence.  Warnings by default; `--strict-deps` turns them into errors.

### 7.1 Register model

`RegKey = (file, index)` over four namespaces `R / UR / P / UP`.
Width expansion: `.64` → `{n, n+1}`, `.128` → `{n..n+3}`, `.256` (LDG
`Rd2` form) → 8.  Writes to `RZ`/`URZ` (255) are discarded.  Predicates
`P0-P6` are tracked like registers (e.g. `IADD3` writes `Pu`/`Pv`).

### 7.2 def/use extraction

Role table over FORMAT slot names, applied to `variant["format"]["slots"]`
with values from `slot_map`:

| role | slots |
|------|-------|
| def  | `Rd`, `Rd2`, `URd`, `Pd`, `Pu`, `Pv` (+ per-mnemonic overrides, e.g. LDG `Pnz`) |
| use  | `Ra`, `Rb`, `Rc`, `Re`, `URa`, `URb`, `URc`, `Sb` (only when the operand kind is REG/UREG — immediates skipped), `desc[URx]` UR, `[Ra.64+off]` base, `Pp`-style source predicates |
| guard use | `Pg`, `UPg` |

Instructions of class `DECOUPLED_RD_SCBD` (stores etc.) mark their uses as
**late reads** (operands read after issue → anti-dependency exposure).

### 7.3 State

- `reg_prod: dict[RegKey → Claim]` — latest variable-latency producer per
  register.
- `outstanding: list[Claim]` per SB0..SB5, where
  `Claim = {instr_idx, kind: wr|rd, regs: set[RegKey], sb, predicated: bool}`.
  Bounded (≤ producers not yet waited), no counters.
- `ub: dict[sb → int]` — per-SB in-flight **upper bound** (count lattice,
  §5a.4), capped at 63 (DEPBAR.LE `cnt` is 6-bit) with `>63` = top.

### 7.4 Per-instruction algorithm (at instruction i)

1. Extract `(defs, uses, late_uses)` and the latency class.
2. **True-dependency check (uses).**  For each used register r: if
   `reg_prod[r]` has a `wr` claim still outstanding (no `req` on its SB at
   any instruction j with producer < j < i), require
   `claim.sb ∈ i.sched.req_bits`; else diagnose `missing_req`.
   Coverage is **transitive** (in-order issue: any earlier wait clears it
   for all later instructions) and applies to **all** consumers including
   `COUPLED_MATH` ones — the S2R→IADD3 bug was a coupled consumer.
3. **Anti-dependency check (defs).**  For each defined register r: if an
   outstanding `rd` claim (late reader, e.g. STG data) covers r, require
   `rd_claim.sb ∈ i.sched.req_bits`; else diagnose `anti_dep`.
4. **Producer discipline.**  If class ∈ {`DECOUPLED_RD_WR_SCBD`,
   `DECOUPLED_WR_SCBD`} and the instruction has a real dest:
   - `wr_sb == 7` → diagnose `missing_wr_sb` **only if the result has a
     consumer** (unknown in V1 without liveness — see rule adjustments
     below); per §5a.1 the counter self-drains, so tracking a
     never-consumed result is optional, not a bug.
   - `wr_sb != 7` → register a `wr` claim on the defs.  If the SB carries
     an outstanding **predicated** claim never waited, also diagnose
     `divergent_retarget` (§5b).  Non-predicated re-targeting (shared
     tally) is legal — per-claim coverage handles it, no false positive.
5. **req settlement.**  For each `sb ∈ i.sched.req_bits`, drop all claims
   on `sb` with `instr_idx < i`; set `ub[sb] := 0`.
6. **rd claim registration.**  If `rd_sb != 7` and the instruction has
   late reads, register an `rd` claim covering `late_uses`.
6b. **DEPBAR.LE recognition.**  A `DEPBAR` instruction is
   `INST_TYPE_COUPLED_MATH` with its wait expressed by **operands**, not
   the bracket req mask: target SB(s) from the `sbidx` operand (or the
   `scoreboard_list` bitset form), threshold from the `cnt` operand.
   - `cnt == 0` (`cp.async.wait_group 0`) → treat exactly like a `req` on
     the target SB(s): kill claims, `ub := 0`.
   - `cnt > 0` → **no identity kill** (§5a.4); only
     `ub[s] := min(ub[s], cnt)`.  If `ub[s] ≤ cnt` already, the wait is
     statically known satisfied → no-op (emit info, change nothing).
   - `.LE URb` (uniform-register threshold) → statically unknown: set
     `ub[s] := >63` (top), still no identity kill.
   - bare / `.ALL` DEPBAR forms (`le=0`, `MEM_SCBD_TYPE=BARRIER_INST`)
     belong to the barrier domain — ignored by this checker (noted).
7. **Predication.**  Predicated producers register MAY-claims; the
   consumer `req` requirement is **not** weakened (§5b/§5b.1: whole-warp
   stall semantics).
8. **Count updates.**  After steps 4/6, `ub[sb] += 1` for each SB named by
   `wr_sb`/`rd_sb`; if `ub[sb]` exceeds the cap, diagnose `sb_capacity`
   (tally overflow without an intervening drain).

### 7.5 Diagnostic levels

| code | level | meaning |
|------|-------|---------|
| `missing_req` | warning (error in strict) | consumer of variable-latency result lacks covering `req` |
| `anti_dep` | warning (error in strict) | writer clobbers a late-read register without waiting the reader's `rd` SB |
| `missing_wr_sb` | warning if result is consumed; perf-info otherwise | variable-latency result untracked |
| `divergent_retarget` | warning | SB re-targeted while a predicated claim is outstanding (§5b hazard) |
| `sb_capacity` | warning | in-flight upper bound on an SB exceeds the tally cap without an intervening drain (count lattice, §5a.4) |

DEPBAR.LE specifics: a partial wait (`cnt > 0`) never clears a dependency —
a consumer relying on it alone is reported as `missing_req`, not via a
special code.  A statically-satisfied DEPBAR.LE (`ub ≤ cnt`) is info-level.

V1 liveness approximation for `missing_wr_sb`: scan the remaining
instruction suffix for any use of the def'd registers (cheap, exact on
straight-line code).

### 7.6 Implementation

- New module `assembler/sass_depcheck.py`:
  `RegKey`, `expand(op) → set[RegKey]`, `extract_def_use(inst, match)`,
  `classify(inst_type_str) → LatencyClass`,
  `DepChecker.check(insts, results) → list[Diagnostic]`
  (`Diagnostic = {instr_idx, code, reg, sb, producer_idx, message}`).
- CLI: `sass_asm.py --check-deps` (print warnings, still emit cubin) and
  `--strict-deps` (exit 1 on any warning-level diagnostic).
- API: `assemble(..., check_deps=False, strict_deps=False)` in
  `assembler/__init__.py`, invoked between match and encode.
- Tests `tests/asm_construct/test_depcheck.py`:
  - negative: S2R without consumer `req={0}` → `missing_req`;
  - negative: LDG without the `LDCU.64 UR4` descriptor wait, or LDG with
    `wr=7` and a consumed result → `missing_req` / `missing_wr_sb`;
  - positive: current corrected `test_s2r.py` / `test_ldg.py` sources
    produce zero diagnostics;
  - `@P1 S2R` predicated producer, consumer without `req` → still
    `missing_req`; predicated claim re-targeted without intervening wait
    → `divergent_retarget`;
  - two LDGs sharing `wr=0`, single consumer `req={0}` → zero
    diagnostics (guards against shared-tally false positives);
  - DEPBAR.LE negative: two LDGs on `wr=SB0`, `DEPBAR.LE SB0, 0x1`, then a
    consumer of the first LDG's register with no `req` → `missing_req`
    (partial wait grants no coverage, §5a.4);
  - DEPBAR.LE positive: `cp.async.wait_group 0` form (`DEPBAR.LE SB0,
    0x0`) treated as a full wait — equivalent to `req={0}`, zero
    diagnostics (`tests/depbar_test.cu` `depbar_waitall` shape);
  - DEPBAR.LE no-op: `DEPBAR.LE SB0, 0x1` when `ub[SB0] ≤ 1` statically →
    info only, no state change;
  - DEPBAR.LE `.LE URb` (uniform-register threshold) → `ub := >63`
    (top), no identity kill, no crash;
  - capacity: an SB driven past the tally cap without a drain →
    `sb_capacity`.

## 8. V2 — CFG checker (after label/branch support)

Prerequisite (old §4): labels + `BRA`/`BRX` parsing and branch-offset
encoding.  Then the linear algorithm lifts to a bitvector dataflow — the
claim model is unchanged, only the state representation moves from lists
to per-block gen/kill sets.

### 8.1 CFG construction

Basic blocks over the instruction stream; edges = fall-through +
`BRA`/`BRX` targets (+ `BSSY` reconvergence noted but treated as normal
edges).  Unknown/indirect targets (`BRX`) → edge to a conservative
"any successor" approximation or reject with a diagnostic (V2 scope
decision; `BRX` jump tables are rare in hand-written kernels).

### 8.2 Dataflow — product lattice (identity × count)

- **Identity lattice** (claims).  Claim ids are global (instruction index
  × kind).  Per block B, precompute by folding the linear algorithm over
  the block:
  - `gen[B]` — claims created in B and still outstanding at B's exit;
  - `kill[B]` — claim ids killed by `req`s / `DEPBAR.LE …,0x0` in B
    (settlement is order-sensitive within the block: a wait kills claims
    from predecessors and from earlier instructions in B, not later ones;
    partial waits `cnt > 0` **never** enter `kill`, §5a.4);
  - per-instruction snapshots for the final diagnostic pass.
  - `IN[B] = ∪ OUT[P]`;  `OUT[B] = (IN[B] − kill[B]) ∪ gen[B]`.
- **Count lattice** (`ub` per SB, mandatory — DEPBAR.LE needs it).
  - block transfer: fold the linear count updates (`wr`/`rd` +1,
    `DEPBAR.LE s,imm` → `min(ub,imm)`, imm=0/`req` → 0);
  - `IN[B][s] = max_P OUT[P][s]` (upper bound over paths), capped at
    `{0..63, >63}`.
- Iterate both to fixpoint (union/max joins, monotone, finite product
  domain → terminates; bitvectors + 6 small integers make it polynomial).
- Loop check the count lattice enables: the
  `LDG wr=SB0 … DEPBAR.LE SB0,0x1 … BRA` pipelining idiom verifies that
  `ub` stays bounded across the loop (fixpoint converges below cap).

### 8.3 Diagnostic pass

Re-run the linear per-instruction checks inside each block seeded with
`IN[B]` (both lattices).  Same five diagnostic codes; a claim outstanding
on **any** incoming path without coverage on the consumer's path →
`missing_req` (may-analysis: conservative, no false negatives; false
positives possible only on infeasible paths, §5a.3).

### 8.4 Optional extensions (deferred, not in initial V2)

- **Stall-count check** for `COUPLED_MATH` pairs (consumer issued fewer
  cycles than the producer's fixed latency along some path) — per-path
  cycle accounting over the CFG.
- **Loop trip-count-sensitive refinement** — explicitly out of scope;
  the set-based fixpoint already gives the exact may-outstanding answer
  at loop headers (§5a.2).
- ~~Capped-count abstraction~~ — **promoted to mandatory** (§8.2 count
  lattice); it is the only thing `DEPBAR.LE imm>0` contributes.

### 8.5 Evolution path from V1

`DepChecker`'s claim/settlement semantics carry over unchanged; V2 adds
(1) CFG builder, (2) block-level gen/kill precompute for both lattices,
(3) fixpoint loop, (4) seeded re-run for diagnostics.  The V1 linear pass
is the special case of a single-block CFG, so the V1 test suite must keep
passing unmodified.
