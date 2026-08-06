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
looks like a flat ~2-reads/cyc budget (0.64 × 3 reads ≈ 1.9), but the
controlled-parity experiment below shows the real structure is **2 banks
× 2R** and the storm's 0.64 is explained by parity conflicts in ptxas's
register allocation, not a flat cap.

Reference point — cuBLAS SGEMM 8192³ (torch): 39.4 TFLOPS @1635 MHz =
105 FMA/cyc/SM = 0.82 FFMA/cyc/SMSP. cuBLAS beats the storm by register
blocking: high operand-reuse ratios (`.reuse` flags, repeated operands)
reduce fresh RF reads per FMA. So the RF read structure is a real
scheduling constraint for ptxas, not just a microbenchmark curiosity.

## RF structure: 2 banks by register-number parity, 2R per bank (proven)

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

Verdicts on the folklore claim "2 banks split by register parity, 2R1W
each":

- **2 banks by register-number LSB parity — CONFIRMED.** `eee` ≡ `ooo`
  (3.11), and every 2-even-1-odd permutation is conflict-free, so the
  bank selector is the register number's low bit, not operand slot or
  register range.
- **2 reads per bank per instruction — CONFIRMED.** 2 same-parity reads
  are free; the 3rd costs exactly ~+1 cyc (the operand collector
  pipelines the extra read). A flat-2R-total model is REJECTED: it
  predicts `eeo` = `eee`, measured 2.11 vs 3.11. (Total RF read
  capacity is thus 2 banks × 2R × 128 B = 1024 B/cyc/SM, not ~512.)
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

## Open questions

- Exact budget decomposition: read-only ~256 B/cyc/SMSP vs combined
  read+write ~330 B/cyc/SMSP (current points fit both). Discriminator:
  storms with tunable read:write ratios (e.g. MOV chains = 1r/1w,
  LOP3.LUT with immediates = 1r/1w+imm).
- Bank structure: 2 vs 4 banks, conflict replay cost — needs hand-SASS
  storms with controlled operand parities (the assembler gives exact
  register numbers). The 1.56-vs-2.04 compilation-luck spread suggests
  ~30% bank effects.
- Does the TC RMW have any dedicated RF write port, or is it fully
  behind ALU traffic? (The constant +30 cyc suggests "mostly behind".)
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

1. **2R1W does explain the storm side**: 3-fresh-read FFMA caps at
   ~1.9 lane-reads/cyc/SMSP (0.64 instr/cyc) — the 2R budget — flat over
   warp count.
2. **The RMW does not trickle through the shared 2R ports per register.**
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
