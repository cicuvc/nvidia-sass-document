# Register file bandwidth — empirical limits and HGMMA contention (H800, 2026-08)

Empirical register-file (RF) bandwidth limits on H800 (full GH100, sm_90),
and the demonstration that a heavy CUDA-core register stream can starve the
HGMMA accumulator writeback. Experiments: `rf2_test.cu` (nvcc, verified
SASS counts), logs in the H800 session; overlay storms co-located with an
HGMMA n16k16 bf16 chain (warpgroup 0) on the same SM (warpgroup 1).

## The core measurement: FFMA with 3 fresh register sources is RF-read-bound

Straight-line storm of 1280 `FFMA Rd, Ra, Rb, Rd` (8 independent chains,
A/B operand pairs rotated so every instruction reads 3 distinct registers,
minimal `.reuse` hits), all-storm block scaling:

| warps/SMSP | cyc/FFMA/warp | SMSP aggregate |
|---|---|---|
| 1 (b=128) | 1.56 | 0.64/cyc |
| 2 (b=256) | 3.09 | 0.65/cyc |
| 3 (b=384) | 4.67 | 0.64/cyc |
| 4 (b=512) | 6.25 | 0.64/cyc |

Aggregate is pinned at **~0.64 warp-FFMA/cyc/SMSP independent of warp
count** → not issue-limited (scheduler could do 1.0), not pipe-latency
(ILP=8 ≫ FFMA latency) — the limit is operand delivery. Naively this
looks like a flat ~2-operand/cyc budget (0.64 × 3 reads ≈ 1.9), but the
controlled-parity experiment below shows that operands are split across
**two parity banks**.  The storm's 0.64 is explained by per-bank collection
pressure in ptxas's register allocation, not a flat unbanked cap.  That
experiment does not determine the number or width of physical read ports.

Reference point — cuBLAS SGEMM 8192³ (torch): 39.4 TFLOPS @1635 MHz =
105 FMA/cyc/SM = 0.82 FFMA/cyc/SMSP. cuBLAS beats the storm by register
blocking: high operand-reuse ratios (`.reuse` flags, repeated operands)
reduce fresh RF reads per FMA. So the RF read structure is a real
scheduling constraint for ptxas, not just a microbenchmark curiosity.

## RF structure: two parity banks; single-warp test alone is ambiguous

Controlled hand-written-SASS FFMA storms (512 independent-chain FFMAs,
16 accumulators, one warp, stall=1 → ~2.1-2.4 cyc/op issue floor;
`tests/rf_bank_probe.py`, H800). Sources' register-number parity fully
controlled; `.reuse` flags set via the sched-bracket batch field
(bit0=srcA, bit1=srcB, bit2=srcC):

| kernel | reads (E=even bank, O=odd) | cyc/op | verdict |
|---|---|---|---|
| NOP baseline | — | 2.44 | floor |
| `eee` / `ooo` | 3 on one parity | **3.11** | conflict, +1 cyc |
| `eeo` / `eoe` / `oee` | 2+1 split | 2.11 | **no conflict** |
| `eee` + `.reuse` srcA | 2E (A from cache) | 2.11 | conflict gone |
| `eee` + `.reuse` srcB | 2E | 2.11 | conflict gone |
| `eee` + reuse A+B / A+B+C | ≤1E | 2.43 | = baseline |

The original interpretation called this "2 banks split by register parity,
2R1W each".  The bank mapping and reuse conclusion survive, but the read-port
count was overclaimed:

- **2 banks by register-number LSB parity — CONFIRMED.** `eee` ≡ `ooo`
  (3.11), and every 2-even-1-odd permutation is conflict-free, so the
  bank selector is the register number's low bit, not operand slot or
  register range.
- **At most one full-warp operand per bank per clock is sufficient to explain
  the result; two independent full-warp reads per bank were not proven.**
  This H800 single-warp harness already has an approximately two-clock
  instruction floor.  A one-operand/bank/clock model predicts
  `T = max(2, n_even, n_odd)`: `eeo` takes two clocks and `eee` takes three,
  exactly the observed 2.11 versus 3.11.  Saying that two same-parity sources
  are "free" only meant that their collection fits under the existing
  two-clock instruction cadence; it did not show that they were read in the
  same clock.  Consequently the old `2 banks x 2R x 128 B` bandwidth
  calculation is withdrawn.
- **1W per bank — not observable at instruction level.** One warp
  issues ≤1 instr/cyc/SMSP so ≤1 write/cyc total; a per-bank write cap
  can never bind. Nothing measured contradicts it.
- **`.reuse` bypasses RF read ports — CONFIRMED.** One reuse flag
  removes one bank read (eee+rA behaves exactly like a native 2-read
  pattern); two/three flags drop to baseline. The reuse cache is fed by
  that operand slot's previous read and does not consume a port.

This also corrects the "second-order effect" caveat above: the 1.56 vs
2.04 cyc/FFMA compile-luck spread *is* the parity-conflict effect, and
it is first-order for 3-fresh-read code. ptxas mitigates by assigning
parities 2:1 across each instruction's sources and inserting `.reuse`;
hand-scheduled SASS must do the same.

The later GB202 yield-zero FADD/FFMA discriminator removes the hidden
two-clock floor: `1E+1O` takes about one clock, `2E` takes two, and `3E` takes
three.  Partial-lane predicates down to lane 0 do not change those slopes.
That directly establishes one *independently addressed full-warp operand* per
bank per clock at the exposed ALU collector on GB202.

### H800 two-warp aggregate resolves the ambiguity (2026-09)

The H20 same-subcore discriminator was subsequently rerun on the full H800.
Warp 0 is timed; warp 4 is the same-subcore contender and warp 1 is the
different-subcore control.  Each body has 512 independent destinations and
the contender is four times longer.  `@P6` uses the identical instruction
with a false predicate.

| victim / contender | aggregate source demand | solo | same active | same `@P6` | different active |
|---|---:|---:|---:|---:|---:|
| FADD balanced / balanced | 2E+2O | 2.094 | 2.096 | — | 2.076 |
| FADD all-even / all-even | 4E | 2.094 | **4.287** | 2.100 | 2.076 |
| FFMA 2E+1O / same phase | 4E+2O | 2.094 | **4.287** | 2.100 | 2.076 |
| FFMA 2E+1O / complement | 3E+3O | 2.094 | **2.992** | 2.100 | 2.076 |
| FFMA all-even / all-even | 6E | 3.090 | **5.574** | 3.086 | 3.072 |

The 128/256/512 length sweep has the same slopes.  Predicate-off and
different-subcore contenders return to the solo rate, excluding a generic
instruction issue or backend conflict.  The demand law is the same as H20:
approximately one independently addressed full-warp operand per parity bank
per clock.  Therefore H800/H20 Hopper does **not** retain the Volta/Ampere
two-operand-per-bank service exposed by the V100/A100 probe.

Assembler quirks found building the probe (arch=sm90, for the manual):
`[7:7:{}:0:0]` is an illegal opex combo for FFMA (stall=0 requires
yield=1, which poisons throughput — 33 cyc/op); reuse flags require
stall≥1; `IMAD.SHL.U32` mis-matches to `IMAD.HI.U32` (matcher bug, use
plain `IMAD`); `IADD3.X` adds **both** carry-in predicates (PT is 1 —
clear a predicate with `PLOP3.LUT P1,PT,PT,PT,PT,0x0` for 64-bit adds);
consumers of `LDC` results must wait its scoreboard (`{0}` req bit)
since `check_deps=False` inserts nothing.

## HGMMA accumulator RMW arbitrates the same RF ports

Overlay: warpgroup 0 runs a 64× HGMMA.64x16x16 chain (desc operands;
solo rate 21.5 cyc/MMA, RF traffic only ~48 B/cyc/SMSP for the RMW),
warpgroup 1 runs a storm with identical structure but different op mix:

| storm (wg1) | storm rate | storm RF reads | HGMMA cyc/MMA | Δ |
|---|---|---|---|---|
| — (solo) | — | — | 21.5 | — |
| FFMA, 3 fresh regs | 1.60 cyc/i | ~960 B/cyc/SM | **52.0** | **+140%** |
| FFMA, 2 operands `.reuse`-cached | 1.69 cyc/i | ~470 B/cyc/SM | 23.8 | +11% |
| IMAD, 3 fresh regs (int pipe) | 2.31 cyc/i | ~665 B/cyc/SM | 21.8 | +1% |
| LDS+FADD (LSU + 2r/1w) | 5.90 cyc/i | ~173 B/cyc/SM | 22.4 | +4% |

Decisive comparisons:
- **FFMA-reuse vs FFMA-rot**: same instruction, same FP32 pipe, same
  issue rate — only the RF-read traffic differs. Contention collapses
  from +140% to +11% → the contested resource is **register bandwidth,
  not issue slots, not the FP32 pipe**.
- **IMAD-rot**: same 3r+1w shape on the integer pipe, but issued slower
  (int-pipe cap ~0.43/cyc/SMSP/warp) so its RF-read rate stays under the
  threshold → no contention. Confirms the limit is a bandwidth threshold
  (~700-900 B/cyc/SM ≈ 175-225 B/cyc/SMSP of ALU RF reads), not a
  per-instruction arbitration penalty.
- **LDS**: LSU/smem path does not touch the contested resource.

Mechanism: the HGMMA accumulator RMW (read old acc + write new acc at
completion, ~8 KB/wg/MMA for n16 f32) shares the RF ports with ALU
traffic. When co-resident ALU reads saturate the ports, the RMW stalls,
completion (and gsb0 release) is delayed, and the chain backs up through
the ~7-entry TC input queue into issue backpressure. The penalty is
roughly constant per MMA (+30 cyc) rather than proportional to the MMA's
own RF traffic — consistent with the RMW being serialized behind ALU
reads, not with a proportional slowdown of a wide write port.

This also explains the **A-from-registers HGMMA penalty (~+24% at
n16k16)**: the A-tile RF reads (2 KB/wg/MMA) add to the same budget on
top of the RMW.

## Consequences for modelling

- Sustained HGMMA rate models (`wgmma.md` Rounds 3-5: smem-operand-path
  bound ~112 B/cyc/SM, MAC-bound on H20) hold when ALU RF traffic is
  quiet. Under a heavy ALU register stream, a third bound appears:
  **RF-port contention can dominate** (n16 chain: 21.5 → 52 cyc/MMA,
  worse than any smem/TC limit seen).
- Real GEMM kernels interleave FFMA address math/FMA epilogues with
  wgmma — but at far lower RF-read rates than a 3-fresh-read storm, so
  the practical impact is small; the +140% figure is the adversarial
  ceiling.

## Open questions (before the hand-SASS write-only probe)

- Exact budget decomposition: read-only ~256 B/cyc/SMSP vs combined
  read+write ~330 B/cyc/SMSP (current points fit both). Discriminator:
  storms with tunable read:write ratios (e.g. MOV chains = 1r/1w,
  LOP3.LUT with immediates = 1r/1w+imm).
- Bank structure: 2 vs 4 banks, conflict replay cost — needs hand-SASS
  storms with controlled operand parities (the assembler gives exact
  register numbers). The 1.56-vs-2.04 compilation-luck spread suggests
  ~30% bank effects.
- Does the TC RMW have any dedicated RF write port, or is it fully
  behind ALU traffic?  Round 3 below resolves the architectural-port
  part of this question, though not the exact location of the mux.
- Does the same threshold hold on H20 (its HGMMA chain is MAC-bound at
  32.4 cyc/MMA with more RF headroom per cycle — prediction: FFMA-rot
  storm slows it less in absolute cyc/MMA)?

## Round 2 — testing the 2R1W model against the RMW (rf3_test.cu)

Naive 2R1W model: per SMSP per cycle the RF sustains 2 lane-reads
(256 B) + 1 lane-write (128 B), and the HGMMA accumulator RMW spends
shared read slots (n16: 8 lane-reads + 8 lane-writes per MMA per warp).
Then an FFMA-3R storm at r lane-reads/cyc should stretch each MMA to
`max(T_solo, RMW_reads/(2−r), RMW_writes/(1−w))`. Calibrating r on the
n16 point (r_e = 2 − 8/51.8 = 1.846 ≈ the storm's 1.875) the model makes
four parameter-free predictions — and fails two decisively:

| overlay | measured | 2R1W prediction | verdict |
|---|---|---|---|
| n16 + FFMA-3R | 51.8 | 64 (calibration) | ~ok |
| n16 + FFMA-2R-imm | 25.3 | ~21.4 (no slowdown) | +18% off |
| n16 + xorshift (low RF) | 21.5 | 21.4 | exact |
| **n8 + FFMA-3R** (RMW = 4 regs) | **49.2** | **26** | refuted |
| **n64 + FFMA-3R** (RMW = 32 regs) | **64.3** | **208** | refuted |

**The contention penalty is FLAT: Δ = +30.4 / +29.7 / +30.7 cyc/MMA for
n8/n16/n64 — completely independent of accumulator width.** A per-register
shared-2R model is therefore wrong for the RMW. What survives:

1. **Two parity banks with about one independently addressed full-warp
   operand/bank/clock explain the storm side**: 3-fresh-read FFMA caps at
   ~1.9 operand-reads/cyc/SMSP (0.64 instr/cyc), flat over warp count.
2. **The RMW does not trickle through the ordinary ALU collector per
   register.**
   Instead, each MMA's writeback/completion carries a **fixed-cost
   arbitration step (~+30 cyc) that serializes only when co-resident ALU
   RF-read traffic exceeds ~650-700 B/cyc/SM** (threshold probes: ffma2
   628 B/c → +4 cyc; IMAD-3R 665 B/c → +0; xorshift 96 B/c → +0;
   ffma3 960 B/c → +30). This is consistent with the accumulator living
   on a dedicated wide TC↔RF path (per `wgmma.md` Round 3's
   in-pipe/in-order completion model), with only its arbitration
   (or gsb0-release) step competing with ALU RF traffic.
3. ALU has arbitration priority: the storm's own rate is unchanged in
   the overlay (1.60 vs 1.56-2.05 solo) while the MMA chain absorbs the
   entire penalty.
4. The per-MMA serialization means completions do not pipeline under
   contention — in-order completion per warpgroup turns the fixed
   arbitration wait into a throughput term, not just latency.

(Compiler traps hit while building the probes, for the record: an
`add.f32 c, c, 0.5` storm was constant-folded to nothing — all inputs
compile-time; an `add.s32 v, v, 7` chain was linear-folded to one IMAD.
Only non-foldable recurrences (xorshift) or register-operand forms
survive ptxas/cicc.)

## Round 3 — H800 bank calibration and a zero-read HGMMA write probe

Hand-SASS probes on the same H800 remove the two ambiguities left by
the compiler-generated storms.

First, a delayed `LDG.32` completion was overlaid with an all-`.reuse`
FFMA stream whose destinations were forced to one register parity.  A
same-bank completion is delayed by 7--8 cycles while the opposite-bank
completion is not (for example at 40 FFMA instructions: 60 versus 52
cycles).  Swapping even/odd gives the exact mirror image.  Predicated-off
instructions and no-reuse controls have no parity effect.  Thus this
H800's normal completion path independently confirms **two RF banks with
one architectural write service per bank per cycle**; this is not an
assumption imported from Blackwell.

The HGMMA discriminator uses four contender warps, one on each SMSP,
and a warpgroup running 64 dependent SS HGMMA instructions.  The clean
contender is `MOV32I`:

- `MOV32I R_even, imm` has no GPR source operand, so it is a pure RF
  write stream.
- `MOV32I RZ, imm` has identical instruction/scheduler pressure but no
  architectural RF write.
- All measurements compare against this simultaneous `RZ` control;
  comparing with an isolated HGMMA is invalid because a non-yielding
  four-warp contender changes warpgroup scheduling by itself.

| HGMMA shape | accumulator regs/thread | real-GPR Hissue | `RZ` Hissue | write-only penalty |
|---|---:|---:|---:|---:|
| m64n8k16 | 4 | 66.484 | 64.609 | **+1.875 cyc/MMA** |
| m64n16k16 | 8 | 68.469 | 64.578 | **+3.891 cyc/MMA** |
| m64n64k16 | 32 | 80.328 | 64.641 | **+15.687 cyc/MMA** |

The penalty is proportional to destination width: approximately
0.49 cycle per accumulator register per MMA.  The contender is also
backpressured (`MOV32I` issue rises from 2.002 cycles solo to 2.510 in
the n64 overlay), so this is mutual arbitration rather than merely an
HGMMA scheduling side effect.  Even-only, odd-only, and balanced
contender destinations give the same total penalty.  This is expected:
every legal HGMMA accumulator group is even-aligned and spans both banks
equally, so moving all contender writes to either bank conserves the
aggregate number of collisions.

Two controls locate the effect:

1. Replacing the real destination with `RZ` removes it, excluding
   decode, issue, constant generation, and source collection.
2. `scaleD=0` overwrite and `scaleD=1` RMW chains give the same result,
   excluding the old-accumulator read.  The shared resource is the
   final architectural destination write/commit.

**Conclusion:** HGMMA does not have a fully independent RF write port.
It may have a dedicated wide TC-to-RF transport or completion buffer,
but its final architectural writes enter the same per-bank 1W service
domain as ordinary GPR writes.  The experiment cannot determine whether
the physical mux is before the bank write driver or one stage earlier
at a bank-local commit arbiter; "shared final per-bank commit" is the
narrowest model justified by the data.

A direct one-word WAW boundary probe does not sharpen that conclusion.
An immediately following scalar write switches winner at a fixed
schedule boundary, but external same/opposite-parity writer traffic does
not shift it.  Dependency/forwarding ordering hides the physical word
commit time.  Nor can HGMMA create a one-bank-only destination: even the
smallest F16 n8 result is an aligned two-register `{even,odd}` group.

Probe sources:
`tests/asm_construct/probe_mio_rf_writeback.py`,
`tests/asm_construct/probe_hgmma_mio_interaction.py`, and
`tests/asm_construct/probe_hgmma_rf_write_port.py`.

## Round 4 — does RMW consume a normal RF read port?

The direct discriminator is a read-only contender:

```text
FFMA RZ, R_even_i, R_odd_j, R_even_k
```

The three sources rotate through 60 registers, carry no `.reuse` flags,
and the destination is `RZ`; therefore it stresses normal operand
collection without generating an architectural RF write.  Its solo rate
is 2.014 cycles/instruction versus 1.165 for the otherwise similar fixed-
source, all-`.reuse` `FFMA RZ` control, confirming that the source reads
were not elided merely because the result is discarded.

With four such warps and 64 SS HGMMAs, all-overwrite (`scaleD=0` on every
MMA) versus RMW (first overwrite, 63 `scaleD=1` MMAs) gives:

| shape | overwrite issue / drain | RMW issue / drain | RMW minus overwrite |
|---|---:|---:|---:|
| n8 | 80.844 / 82.922 | 80.875 / 82.953 | +0.031 / +0.031 |
| n16 | 82.656 / 84.984 | 82.719 / 85.047 | +0.063 / +0.063 |
| n64 | 93.469 / 97.297 | 93.719 / 97.547 | +0.250 / +0.250 |

Those small 64-MMA differences initially look width-proportional, but
they are only 2/4/16 clocks over the *entire* chain.  Repeating n64 at
32 and 128 MMAs makes RMW and overwrite exactly equal:

| n64 chain | overwrite issue / drain | RMW issue / drain |
|---:|---:|---:|
| 32 | 90.375 / 98.094 | 90.375 / 98.094 |
| 128 | 95.094 / 96.961 | 95.094 / 96.961 |

Thus an HGMMA RMW logically reads the current architectural accumulator
(the WAW probes prove that), but it does **not** consume the ordinary ALU
ordinary ALU collector once per accumulator register.  Otherwise 31 extra n64
RMWs under saturated read traffic would add a large repeatable cost, not
zero.  The old value is more likely obtained through a dedicated TC
accumulator-read path or a bank-local read-before-write primitive.  Only
the resulting write/commit is observably shared with the normal per-bank
1W domain.  A small fixed arbitration action below timing resolution is
not excluded; a per-register ordinary-read-port implementation is.

## Round 5 — directly exposing the bank-local RMW aperture

`probe_hgmma_rmw_window.py` races one scalar marker write against one
n64 accumulating HGMMA.  Every accumulator starts at 1.0, the HGMMA
adds exactly 16.0, and the racing `MOV32I` writes 2.0.  After DEPBAR the
three possible values locate the marker relative to the RMW stages:

- 18.0 (`marker + delta`): marker committed before the old-value read;
- 17.0 (`base + delta`): marker committed after read but before write;
- 2.0 (`marker`): marker committed after the HGMMA write.

This is intentionally undefined async-proxy ordering, but the observed
boundaries are completely deterministic across 30 runs x 128 threads.
For tail pair `{R54,R55}`, with HGMMA stall=4 and stall-1 delay NOPs:

| delay-NOP count | final value | interpretation |
|---:|---:|---|
| 0--24 | 18.0 | marker before RMW read |
| 25--30 | 17.0 | marker inside read-to-write aperture |
| 31+ | 2.0 | marker after RMW write |

Even and odd words have identical boundaries.  Sweeping HGMMA's own
stall field from 1 through 7 merely translates the phase: every case
retains exactly six intermediate delay slots.  A stall-1 NOP stream is
independently measured at 2.003 cycles/instruction, making the exposed
read-to-write aperture approximately **12 clocks** (allow a one-clock
endpoint convention uncertainty).  Stall-0 NOPs are not a usable finer
ruler: one such instruction jumps across completion while further ones
do not translate it, apparently due to batch/scheduler semantics.

Scanning the n64 accumulator pair gives the first post-write (`2.0`)
boundary:

| pair | registers | first post-write delay |
|---:|---|---:|
| 0 | R24/R25 | 17 |
| 4 | R32/R33 | 21 |
| 8 | R40/R41 | 25 |
| 12 | R48/R49 | 29 |
| 15 | R54/R55 | 31 |

Thus four successive `{even,odd}` pairs move the boundary by four NOP
slots = about eight clocks: the completion sequencer processes roughly
**one even+odd pair every two clocks**.  Pair 0 to pair 15 spans about
28 clocks, consistent with the same cadence within endpoint quantization.

The resulting concrete model is a bank-local pipelined RMW engine.  It
starts a dedicated old-value read, carries the value and TC delta through
an approximately 12-clock RMW datapath (including FP32 add and staging),
then requests the already-proven
shared per-bank 1W commit.  The engine initiates/commits one register from
each bank every two clocks.  "Shared address sequencer" is plausible;
literally one unpipelined decoder is not, because steady state must overlap
a future read with an older write.  Separate read/write decode phases or a
pipelined decoder can implement the observation.

Probe source: `tests/asm_construct/probe_hgmma_rmw_window.py`.
