# usched_info ↔ latency tables — the stall/yield model (sm_90)

**Question:** how does `usched_info` (the field commonly called "stall count",
with its top bit read as a "yield bit") relate to the data in
`sm_90_latencies.txt`?
**Status:** resolved empirically (spec-grounded + cuBLAS sm_90 corpus, ~2.75M
adjacent instruction pairs). Tooling: `tools/parse_latencies.py` +
`tools/usched_probe.py`.

## TL;DR
- `usched_info` (5 bits, [109:105]) = **{bit4 = end-group/"yield" flag, bits[3:0]
  = stall count}**. `eff_stall = usched & 0xF`; `group = usched >> 4`.
  `0`=DRAIN(yield), `1..15`=`WnEG` (bit4=0, "end group"), `17..27`=`Wn`/transN
  (bit4=1, "transition, no group-end"). Value 16 is unused.
- The **stall count is the issue-to-issue gap ptxas computes from the
  `TABLE_TRUE/OUTPUT/ANTI` latency matrices.** For a fixed-latency producer whose
  immediate successor has a true (RAW) dependency, `eff_stall` equals the
  `TABLE_TRUE(GPR)` producer→consumer latency (exactly for many pipe pairs; a
  small constant less for integer same-pipe chains — forwarding).
- **bit4 is effectively the yield selector, but with the opposite polarity to the
  common "MSB=yield" lore:** `bit4=1` (transN) means *the next instruction is
  independent → keep issuing this warp*; `bit4=0` (`WnEG`/DRAIN) is used when a
  dependency stall / group boundary occurs → the scheduler may switch warps.

## How the latency file encodes dependency cycles
`TABLE_<DEP>(<RES>)` blocks are producer×consumer matrices:
- **rows** = producer op-class writing `Rd`/`Rd2` (`Pu`/`Pv` for PRED),
- **columns** = consumer op-class reading `Ra/Rb/Rc/Re` (`Pr..` for PRED),
- **cell** = dependency latency in cycles; `DEP` ∈ TRUE(RAW)/OUTPUT(WAW)/ANTI(WAR),
  `RES` ∈ GPR/UGPR/PRED/UPRED plus scoreboard resources.

Op-class membership comes from `OPERATION SETS` set-algebra (`int_pipe`,
`fmalighter_pipe`, `FXU_OPS = int_pipe+fe_pipe-…`, `IMAD_OP`, …). Example decoded
cells (`parse_latencies.py lookup TRUE GPR …`):

| producer → consumer | TABLE_TRUE(GPR) |
|---|---|
| FMAI (FFMA/FADD/FMUL) → FMAI | 4 |
| FMAI → FXU (int) | 5 |
| FXU → FXU | 6 |
| IMAD → IMAD | 6 |
| fma64lite (DFMA) → fma64lite | 8 |
| fma64lite → fmalighter | 10 |
| HMMA/IMMA → * | 27 |

## Empirical: eff_stall vs predicted latency (adjacent RAW, fixed-latency producer)
From cuBLAS sm_90 (`usched_probe.py`), per (producer_pipe → consumer_pipe),
share where `eff_stall == predicted TABLE_TRUE`:

| producer → consumer | n | pred | modal stall | match |
|---|--:|--:|--:|--:|
| fma64lite → fma64lite (DFMA→DFMA) | 30416 | 8 | **8** | 100% |
| fma64lite → fmalighter | 1990 | 10 | **10** | 99.9% |
| fma64lite → int | 644 | 10 | **10** | 100% |
| fmalighter → int (e.g. IMAD→LEA) | 24977 | 5 | **5** | 95% |
| fp16 → fmalighter | 298 | 5 | **5** | 97% |
| fmalighter → fmalighter (FFMA→FFMA) | — | 4 | **4** | 100% |
| fmalighter → fmalighter (IMAD→IMAD) | 17304 | 6 | **4** | offset −2 |
| int → int (IADD3/LEA/LOP3→…) | 25000 | 6 | **4** | offset −2 |
| int → fmalighter (IADD3→FFMA) | 8004 | 6 | **5** | offset −1 |

Representative exact-match pairs (modal stall = predicted): `DFMA→DFMA` 8 (100%),
`FFMA→FFMA` 4 (100%), `FADD→FFMA`/`FFMA→FADD` 4 (100%), `VIADD→ISETP` 5 (99%),
`DMUL→DFMA` 8 (100%).

### Cumulative gap vs table — the right model

The stall count on one instruction is only the *local residual*. The true
constraint is on the **cumulative issue gap** `G = pos_C − pos_P = Σ eff_stall`
across all intervening instructions: the scheduler must satisfy `G ≥ L_table`.
Analysing all RAW GPR edges over ~1.05M adjacent and non-adjacent producer→consumer
pairs (`usched_probe.py --cumulative`):

- **82% of edges satisfy `G ≥ L_table`.** The 18% `G < L_table` violations are
  clustered in integer chains — these are the cases where hardware result
  forwarding makes the table value *conservative*, i.e. the true hardware-
  effective latency is smaller than the table.
- The **minimum observed G per pipe pair** (on "pure" edges with no DRAIN/scoreboard
  distortion, distance≥1) reveals the *effective* latency the hardware enforces:

  | pipe pair | L_table | minG (hw latency) | overlap (L−minG) |
  |---|---|---:|---:|
  | FFMA→FFMA | 4 | 4 | 0 |
  | FFMA→FADD | 4 | 4 | 0 |
  | FADD→FADD | 4 | 4 | 0 |
  | VIADD→ISETP | 5 | 5 | 0 |
  | DFMA→DFMA | 8 | 8 | 0 |
  | DMUL→DFMA | 8 | 8 | 0 |
  | **IMAD→IMAD** | 6 | **4** | **2** |
  | **IADD3→IADD3** | 6 | **4** | **2** |
  | **IADD3→LEA** | 6 | **4** | **2** |
  | **LEA→LEA** | 6 | **4** | **2** |
  | **IADD3→IMAD** | 6 | **5** | **1** |
  | **IMAD→IADD3** | 5 | **3** | **2** |
  | **IMAD→LEA** | 5 | **3** | **2** |
  | IMAD→LDG | 6 | 5 | 1 |
  | LEA→LDG | 6 | 9 | −3 (mio occupancy, not tight) |

  Interpretation: the **table encodes the worst-case separation** `w_P − r_C`
  (writeback latency minus consumer operand-collect offset). For FMAI and fma64
  pipes, `r_C` = 0 for the consumer, so `L_table = w_P` exactly — no overlap.
  For **integer (FXU) pipes**, there is a 2-cycle hardware operand-forwarding /
  coupled-dispatch overlap: the consumer reads operands `r_C ≈ 2` cycles into
  its pipeline. So the effective separation is `w_P − 2` = 4. This explains
  the `−2` offset in all the empirical results. The `−1` offset on
  `FXU→FMAI` is a half-span: the FXU producer still forwards early, but the
  FMAI consumer needs 1 cycle of operand settlement.
- **`LEA→LDG`**: `minG > L_table` (= 9 vs 6) — not a tight forwarding edge.
  The LDG is held up by the `mio_pipe` issue occupancy, not the pure integer
  forwarding path.

This reframes the entire relationship: **`L_table` is an upper bound, not a
precise cycle target.** ptxas tries to push edges to `L_table − overlap(P,C)`,
and the overlap is a pipe-pair-specific constant that comes from the per-pipe
operand-collect / forwarding mechanism (`w_P` and `r_C`). The `−2` integer
pattern is a hardware fact, not a compiler heuristic.

### WAW / WAR and a per-pipe w/r decomposition

Extending the cumulative-gap method to WAW (`TABLE_OUTPUT`, `G ≥ w_P−w_N`) and
WAR (`TABLE_ANTI`, `G ≥ r_P−w_N`) over the same corpus (`usched_probe.py --solve`):

- **WAR edges are non-binding.** Observed minimum gaps floor at ~1–2 cycles for
  *every* pipe pair, far below the `TABLE_ANTI` values — an anti-dependence is
  satisfied as soon as the earlier reader has collected operands (~1 cyc), so
  real code never exercises the tabulated WAR latency. `TABLE_ANTI` is a loose
  upper bound in practice.
- **WAW is binding only for heavy→light** (`w_P > w_N`): `fma64lite→fmalighter`
  and `fma64lite→int` bottom out at `minG=6` (a slow DFMA writeback must not be
  overtaken by a later fast write). Same-pipe and light→heavy WAW floor at 1–2.
- Fitting the **binding** constraints (all RAW + heavy WAW) to a separable model
  `L = w[producer] − r[consumer]` by least squares (anchor `r[fmalighter]=0`)
  gives, at **RMS ≈ 1.7 cyc**:

  | pipe | w (writeback lat) | r (read/collect offset) |
  |---|--:|--:|
  | fmalighter (FFMA/FADD/IMAD) | ~4.7 | 0 (anchor) |
  | int (FXU) | ~4.5 | ~0.5 |
  | fp16 | ~5.6 | ~0.6 |
  | fma64lite (DFMA/DADD) | ~9.2 | ~−0.5 |

  The `w` values recover the visible same-pipe RAW latencies (FFMA≈4, DFMA≈8–10);
  the small positive `r` for the integer/fp16 consumers is the operand-forwarding
  offset that produces the `−2`/`−1` RAW overlaps above. The model is only
  *approximately* separable (residual ~1.7, worst on sparse fp16-WAW edges), so
  the tables are best read as **consistent per-family upper bounds**, not a
  globally-exact `(w,r)` factorization.

**Bottom line for the three table families:** `TABLE_TRUE` (RAW) is the one the
compiler tracks tightly — its values minus a per-pipe forwarding overlap are what
`usched` stall counts (cumulatively) enforce. `TABLE_OUTPUT` (WAW) binds only
when a slow producer precedes a fast writer. `TABLE_ANTI` (WAR) is essentially
never the binding constraint in real SASS.

### Which pipes forward? (RAW overlap = `L_table − minG`)

Full producer×consumer survey (`usched_probe.py --overlap`, cuBLAS sm_90),
rolled up by **consumer** pipe (forwarding is a consumer-read-timing property):

| consumer pipe | wt.mean overlap | n | forwarding? |
|---|--:|--:|---|
| int_pipe (FXU) | **1.6** | 306k | **yes (~2 cyc)** |
| fmalighter_pipe | 0.7 | 391k | **only its integer ops** (IMAD), float=0 |
| udp_pipe | 2.0 | 379 | yes, but tiny sample |
| fp16_pipe | 1.0 | 536 | **no pipe-wide bypass** (see targeted test below) |
| mio_pipe | 0.06 | 137k | no (loose, occupancy-bound) |
| fma64lite_pipe (double) | ~0 | 202k | **no** |

The decisive detail is **per-op, not per-pipe**: within `fmalighter_pipe`,
`IMAD→IMAD` shows overlap **2** (L=6, minG=4) while `FFMA→FFMA` shows **0**
(L=4, minG=4). Every non-zero-overlap pair is an **integer-ALU** pair
(`IMAD, IADD3, LEA, ISETP, SHF, LOP3` in any combination); every
floating-point pair (`FFMA/FADD/FMUL→…`, `DFMA→DFMA`) has overlap **0**.

**Conclusion: forwarding is an integer-datapath feature.** Integer arithmetic
(the FXU *and* the integer-multiply path in the FMA-lighter pipe) bypasses
results ~1–2 cycles ahead of the tabulated writeback latency, so dependent
integer chains issue at `L_table − 2` (`−1` when crossing into the FMA pipe).
The **float pipes carry no bypass**: `FFMA/FADD/FMUL` (fmalighter float) and
`DFMA/DADD` (fma64lite) hit `minG == L_table` exactly — the table latency *is*
the enforced separation. `fp16` and `udp` have too little clean data in cuBLAS
to decide (fp16 samples are dominated by HMMA, whose 27-cyc entries and
cross-domain edges give noisy/negative "overlap").

Negative "overlaps" (`LEA→LDG` = −3, `int→mio` < 0) are not anti-forwarding —
they are `mio` consumers scheduled *looser* than the address latency requires,
bound by `mio_pipe` issue occupancy rather than the RAW edge.

### fp16 targeted test (`tests/hfp16_test.cu`)

cuBLAS has too few clean fp16 chains, so a dedicated kernel builds purely serial
(zero-ILP) dependent chains — where each producer's stall must equal the exact
effective latency. Decoded pure `fp16→fp16` adjacent edges (table `L=5` for all
`FP16_OPS→FP16_OPS`):

| edge | stall (=minG) | overlap |
|---|--:|--:|
| HADD2 → HFMA2 | 4 | **1** |
| HADD2 → HMNMX2 | 5 | 0 |
| HMNMX2 → HADD2 | 5 | 0 |
| HMNMX2 → HMUL2 | 5 | 0 |
| HMUL2 → HMNMX2 | 5 | 0 |

**Verdict: the fp16 pipe has no forwarding network.** 4 of 5 pairs sit exactly at
the tabulated latency (overlap 0), like the float/double pipes. The lone
exception, `HADD2→HFMA2` (overlap 1), is *not* a producer or pipe property —
the same producer `HADD2→HMNMX2` is 5. It is an **operand-slot bypass**: the
result feeds the FMA **accumulator (C) input**, which is consumed a cycle later
in the pipeline than the multiplicands, so its effective latency is 1 less. That
is a per-slot artifact, not the datapath-wide 2-cycle bypass the integer pipe
has for *every* op pair.

So the forwarding taxonomy is: **integer datapath = real ~2-cyc bypass on all
edges; float / fp16 / double = none, apart from the universal FMA-addend slot
being 1 cycle cheaper.**

## bit4 = end-group / yield (polarity of the "yield bit")
Correlating `group = usched>>4` with whether the immediate successor is
dependent (RAW GPR or PRED), over all adjacent pairs:

| next-insn dependent? | group_bit | share |
|---|--:|--:|
| no  | 1 (transN) | 69.5% |
| no  | 0 (WnEG)   | 20.5% |
| yes | 0 (WnEG)   |  8.5% |
| yes | 1 (transN) |  1.5% |

Derived conditionals:
- `P(group=1 | independent-next) = 77%`; **`P(independent-next | group=1) = 98%`.**
- `P(group=0 | dependent-next) = 85%`.

So **transN (bit4=1) almost always marks an independent successor** — the warp
keeps issuing back-to-back (throughput case, `eff_stall` ≈ 1–2, encoded `W1/W2`
= 17/18). **`WnEG` (bit4=0) / `DRAIN`** appear at dependency stalls and group
boundaries, where yielding to another warp during the wait is useful.

This reframes the common "MSB is a yield bit that makes the scheduler switch
warps": the flip bit is bit4, but it is **`bit4=0` (`WnEG`/DRAIN) that is the
yield-friendly / group-ending state**, not `bit4=1`. `transN` (`bit4=1`) is the
"stay on this warp, no group end" state. DRAIN(0) is the strongest yield.

## Fixed-latency vs variable-latency (why the stall model only applies to some ops)
Per-pipe scoreboard usage in cuBLAS sm_90 (`writes a dst scoreboard` =
`dst_wr_sb≠7`):

| pipe | n | writes dst scoreboard | sets wait mask (`req≠0`) |
|---|--:|--:|--:|
| int_pipe | 705733 | 0.0% | 9.5% |
| fmalighter_pipe | 690629 | 0.0% | 20.3% |
| fp16_pipe | 11568 | 0.0% | 19.9% |
| fma64lite_pipe | 266300 | 0.1% | 32.1% |
| cbu_pipe | 249248 | 0.0% | 14.1% |
| **mio_pipe** | 610396 | **62.8%** | 14.5% |
| udp_pipe | 153969 | 7.1% | 7.1% |

Fixed-latency math pipes (int/fmalighter/fp16/fma64) **never set a write
scoreboard** — their consumers are protected purely by the producer's
`usched_info` stall count (the mechanism analysed above). Variable-latency
`mio_pipe` (loads, MUFU, shared/global mem, GMMA) sets a write scoreboard 63% of
the time and relies on `TABLE_TRUE(SCOREBOARD)` + the `req_bit_set` wait mask,
not on the stall count. Fixed-latency ops still set `req_bit_set` (10–32%) when
they *consume* a scoreboarded (memory) result — e.g. DFMA waiting on a load.

## Method / reproduce
```
tools/parse_latencies.py table TRUE GPR      # decoded matrix
tools/parse_latencies.py lookup TRUE GPR FFMA FFMA
tools/usched_probe.py <sass>                 # adjacent RAW stall vs latency + group/yield
tools/usched_probe.py <sass> --cumulative    # cumulative issue-gap G vs L across distance
tools/usched_probe.py <sass> --overlap       # RAW forwarding overlap (L-minG) per pipe pair
tools/usched_probe.py <sass> --solve         # tri-family minG + per-pipe w/r least-squares
```
`usched_probe.py` decodes control fields from lo64/hi64, does a best-effort
GPR/PRED def-use parse (op0 + trailing predicate operands = dests; `.64/.WIDE`
adds Rd+1), reconstructs issue positions via `pos_{i+1}=pos_i+eff_stall_i`, and
pairs each producer with its downstream consumer/writer.

## Open questions
- Whether the integer forwarding is a true bypass vs merely a conservative table
  entry (the two are indistinguishable from stalls alone: `IMAD` tabulates 6 but
  behaves as 4). A controlled latency microbenchmark would separate them.
- `udp` (uniform datapath) forwarding is still undetermined — the cuBLAS signal
  (overlap 2) rests on only 379 samples. A uniform-register serial chain
  (`UIADD3`/`ULOP3`/`UMOV` via `ULDC` params) would settle it, analogous to the
  `tests/hfp16_test.cu` approach.
- Distance>1 scheduling (stall spread across intervening independent instrs) is
  not modelled here — only the adjacent (distance-0) case is measured.
- `DRAIN` vs `WnEG` differentiation at group boundaries (both bit4=0): what makes
  ptxas pick a full drain over a counted end-group wait.
