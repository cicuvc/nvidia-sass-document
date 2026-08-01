# AUTO_DEP_ANALYSIS — automatic scoreboard/dependency checking for the SASS assembler

Status: **scoping/analysis** (no implementation yet). Goal: catch missing
`req`/`wr`/`rd` scoreboard usage in hand-built SASS — the class of bug that
made `S2R` read garbage and `LDG` fault `ILLEGAL_ADDRESS` (700) before the
manual fixes (`tests/asm_construct/test_s2r.py`, `test_ldg.py`).

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
straight-line kernels can be checked.  Implementing label/branch support in
the parser + ELF branch encoding is the first task.

## 5. Complexity / decidability concerns

- **Register aliasing**: pairs (`R2.64`), `RZ`, predicates, `.reuse`,
  scoreboard *sharing* (one SB tallying many producers) all blur a simple
  def/use chain.
- **Control flow**: a `req`-wait on one path may be missing on another; SB
  counters are path-sensitive.  Loop-carried SB reuse needs fixpoint
  iteration and may not terminate cleanly (counter model is a *count*, not a
  boolean, so abstract interpretation must bound the tally).
- **Memory**: pointer-derived addresses (`LDG [R6.64+off]`) make operand
  provenance data-flow-dependent, not just register-adjacency dependent.
- **"Possibly undecidable" in the worst case** (unbounded SB counts across
  loops with re-targeted SBs).  A practical checker should target a
  conservative over-approximation: flag *potential* missing `req`/`wr`/`rd`
  on straight-line kernels first, then extend path-sensitively.

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

## 6. Suggested first slice (not yet designed in detail)

1. Add labels + `BRA`/`BRX` to parser and encoder (branch offset math).
2. Build a linear CFG (basic blocks, fall-through + branch edges).
3. Per instruction, emit (defs, uses, latency-class, req/wr/rd).
4. Data-flow over SB counters per path; warn when a register is consumed by a
   `DECOUPLED_*` instruction without its producer's SB in `req`, or a
   variable-latency result is never `wr`-tracked.
5. Start with straight-line kernels; treat branch edges conservatively
   (join = union of outstanding SBs), and iterate to a fixpoint with a cap
   on counter values.

Design/algorithm work deferred until the label/branch prerequisite lands.
