# HMMA pipeline — tensor-core mma.sync scheduling (sm_90)

**Question:** how is the HMMA (warp-level tensor `mma.sync`) pipeline scheduled,
and how does it relate to the `sm_90_latencies.txt` model?
**Status:** resolved empirically via `tests/hmma_test.cu`
(`mma.sync.aligned.m16n8k16.f16…` → `HMMA.16816.F16`), sm_90a.
Companion of `usched_latency.md`.

## Spec position
- Pipe: `HMMA ∈ fp16_pipe` (and the singleton set `HMMA_OP`). Issue occupancy
  `HMMA_OP : FMALITE_Occupancy [2]`.
- `TABLE_TRUE(GPR)` latencies (producer HMMA writing Rd):
  - `HMMA→HMMA {Ra,Rb,Re}` = 28, `HMMA→HMMA {Rc}` (accumulator) = 28,
    `HMMA→FMAI` = 27.
  - `FMAI→HMMA {Rc}` (feeding the accumulator) = 7, `{Ra,Rb,Re}` = 7.
- `TABLE_OUTPUT(GPR)` `HMMA→HMMA` (WAW) = 1; `TABLE_ANTI` small.
- HMMA is **fixed-latency**, not scoreboard-tracked: it never sets a write
  scoreboard (`dst_wr_sb=7` in every observed HMMA), consistent with
  `fp16_pipe` writing a scoreboard 0% of the time. Its ~28-cycle result latency
  is enforced by stall counts, exactly like other math ops (just very large).

## Dependent accumulate chain (serial `C = A*B + C`)
Decoded control words (`tests/hmma_test.cu :: hmma_accum_chain`, 32 serial MMAs):

```
HMMA.16816.F16 R10, R4.reuse, R2.reuse, R10   usched=27 stall=11 grp=1  reuse=011  sb=7/7
@!UPT UIADD3 URZ, URZ, URZ, URZ               usched=27 stall=11 grp=1            (dead filler)
@!UPT UIADD3 URZ, URZ, URZ, URZ               usched=18 stall= 2 grp=1            (dead filler)
HMMA … (next)
```

- Because the accumulator RAW latency (28) **exceeds the 4-bit stall max (15)**,
  ptxas cannot encode it in one `usched`. It spreads the wait across the HMMA's
  own stall (11) **plus two dead `@!UPT UIADD3 URZ,URZ,URZ,URZ` uniform NOPs**
  used purely as stall extenders (11 + 2).
- Reconstructed cumulative issue gap **HMMA→HMMA = 24 cycles** (all 31 edges),
  vs the tabulated 28. The 4-cycle shortfall is an **accumulator-input bypass**:
  the `C` operand is consumed late in the tensor pipeline (same phenomenon as
  the FMA-addend slot in `usched_latency.md`, larger here). So the
  effective back-to-back accumulate latency is ~24, not the nominal 28.
- **`reuse = 011`** (reuse_src_a + reuse_src_b): the A and B fragments (`R4`,
  `R2`) are held in the operand-reuse cache across the whole accumulate chain —
  the tensor inputs are re-read from cache, only the accumulator moves. (Valid
  because `usched=27` is a transN code, satisfying the reuse⇒usched∈17..27 rule.)

### The `@!UPT UIADD3 URZ,…` stall-extender idiom
`@!UPT` is never-true (UPT = always-true uniform predicate), so these UIADD3s
never execute — they exist only to carry additional `usched` stall cycles when a
single instruction's 4-bit field can't cover a long fixed latency. This is how
the scheduler realises >15-cycle gaps without a scoreboard.

## Independent MMAs (`hmma_indep`, distinct accumulators)
```
HMMA R12, R4.reuse, R10.reuse, R12   stall=6  req_mask=001000 (wait SB3)
HMMA R14, R4.reuse, R10.reuse, R14   stall=6  req_mask=010000 (wait SB4)
HMMA R16, R4.reuse, R10.reuse, R16   stall=6  req_mask=100000 (wait SB5)
HMMA R18, R4, R10, R18               stall=7  req_mask=000100 (wait SB2)
```
- With no accumulator dependence, HMMAs issue ~6–7 cycles apart and **wait on the
  input `LDG` scoreboards** (`req_bit_set` references SB2–SB5 set by the loads of
  the A/B/C fragments) rather than on each other. So HMMA *consumes* variable-
  latency (memory) results via the scoreboard wait-mask, while *producing* a
  fixed-latency result via stalls.
- A/B fragments are again `.reuse`d across the group.

## Summary
| aspect | finding |
|---|---|
| latency model | fixed-latency (no write scoreboard); table RAW = 28 (accum), 27 (→FMA) |
| dependent accumulate gap | **24 cyc** (measured), ~4 under table → accumulator bypass |
| >15-cycle encoding | HMMA stall(11) + dead `@!UPT UIADD3 URZ` filler NOPs (11+2) |
| operand reuse | `reuse=011` — A,B fragments cached across the chain |
| input dependence | waits on `LDG` scoreboards via `req_bit_set` mask |
| throughput (indep) | ~6–7 cyc here (load-gated); pipe occupancy = 2 (`FMALITE_Occupancy`) |

## Open questions
- Whether the 24-vs-28 gap is a true accumulator bypass or scheduler granularity;
  a bank of independent accumulate chains would let the min-gap settle it.
- Clean independent-HMMA throughput (not load-gated) — needs a kernel that keeps
  all fragments resident (shared memory / register-resident B).
