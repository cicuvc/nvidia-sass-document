# B2R / R2B — Barrier register ↔ GPR move

**Opcode mnemonics:** `B2R` = `0b1100011100` = **0x31c** | `R2B` = `0b1100011110` = **0x31e** | **Pipe:** `mio_pipe` (MIO_SLOW_OPS) | **VIRTUAL_QUEUE:** `$VQ_BAR_EXCH` (barrier-exchange, =33) | compute-only (`SHADER_TYPE==CS`) | since sm_70

Move data between the block's **barrier hardware** and a GPR. `B2R` reads barrier state into a
register (Barrier-to-Register); `R2B` writes a GPR into barrier state (Register-to-Barrier).

## Semantics
### B2R (0x31c) — 3 modes via `stride`[79:78]
| mode | `BarmdBAR/RESULT/WARP` | SASS | use |
|------|-----------------------|------|-----|
| 0 | BAR | `B2R Rd, barname` | read named-barrier `barname` (0–15) state into `Rd` |
| 1 | RESULT | `B2R.RESULT Rd[, Pu]` | read the result of a preceding `BAR.RED` |
| 2 | WARP | `B2R.WARP Rd` | read warp-level barrier/convergence state into `Rd` |

**RESULT mode is verified** — it is how `__syncthreads_count/and/or` extract the block-wide
barrier reduction:
```
BAR.RED.POPC.DEFER_BLOCKING 0x0, P0 ;  B2R.RESULT R7        ; __syncthreads_count -> count in R7
BAR.RED.AND .DEFER_BLOCKING 0x0, P0 ;  B2R.RESULT RZ, P0    ; __syncthreads_and   -> bool in P0
BAR.RED.OR  .DEFER_BLOCKING 0x0, P0 ;  B2R.RESULT RZ, P0    ; __syncthreads_or    -> bool in P0
```
`BAR.RED` performs the reduction at the barrier; `B2R.RESULT` then reads it out — popc gives a
count in `Rd` (`Pu`=PT hidden); and/or give a boolean in predicate `Pu` (`Rd`=RZ).

### R2B (0x31e) — GPR → barrier register
`R2B[.WARP] barname, Rb` — write GPR `Rb` (32-bit) into named-barrier `barname` (BAR mode,
default) or warp barrier state (WARP mode). `MODE_BAR_WARP`: BAR=0, WARP=2 (1,3 illegal).
No destination; `dst_wr_sb` pinned 0x7. `INST_TYPE_DECOUPLED_RD_SCBD`.

Likely a barrier **state save/restore** primitive (context switch / trap handler) — not
observed from nvcc; B2R.BAR/.WARP and R2B are documented from spec + round-trip only.

## Fields (128-bit)
| bits | field | B2R | R2B |
|------|-------|-----|-----|
| [91]∥[11:0] | `opcode` | 0x31c | 0x31e |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard |
| [23:16] | `Rd` | dest GPR (32-bit) | — |
| [39:32] | `Rb` | — | source GPR (32-bit) |
| [57:54] | `barname` | named barrier (BAR mode) | named barrier (4-bit) |
| [79:78] | `stride`=mode | 0=BAR,1=RESULT,2=WARP | 0=BAR,2=WARP |
| [83:81] | `Pu` | RESULT dest predicate | — |
| [112:110] | `dst_wr_sb` | scoreboard | pinned 0x7 |
| [124:122]∥[109:105] | `opex` | scheduling | scheduling |

INSTRUCTION_TYPE: B2R = `DECOUPLED_RD_WR_SCBD` (writes GPR); R2B = `DECOUPLED_RD_SCBD`
(no GPR result). `Rd`/`Rb` ≠ R254.

## Cross-comparison (barrier-state family)
| op | dir | what |
|----|-----|------|
| **B2R** | barrier→GPR | read barrier result / named-barrier / warp state |
| **R2B** | GPR→barrier | write named-barrier / warp state |
| **BMOV** (idx 56) | GPR↔convergence-barrier reg (B0–B15) | separate convergence-barrier move |
| **BAR.RED** | — | block reduction that B2R.RESULT reads |

## Latency (from sm_90_latencies.txt)
Both `mio_pipe` and in `MIO_SLOW_OPS`. `VQ_BAR_EXCH` decoupled: B2R's GPR result is consumed
via the write scoreboard; R2B has no GPR result.

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | source |
|------|------|-------------|--------|
| `0x000000000007731c` | `0x000e2800000e4000` | `B2R.RESULT R7` | **real** `__syncthreads_count` |
| `0x0000000000ff731c` | `0x000e240000004000` | `B2R.RESULT RZ, P0` | **real** `__syncthreads_and/or` |

### Round-trip only (not observed on sm_90)
`B2R R4, 0x3` (BAR), `B2R.WARP R5`, `R2B 0x1, R6`, `R2B.WARP 0x2, R7`.
Decoder: `tools/decode_b2r_r2b.py` (real + round-trips pass). Test: `tests/b2r_test.cu`.

### PTX→SASS mapping
- `__syncthreads_count(p)` → `BAR.RED.POPC …` + `B2R.RESULT Rd`
- `__syncthreads_and(p)` → `BAR.RED.AND …` + `B2R.RESULT RZ, Pu`
- `__syncthreads_or(p)` → `BAR.RED.OR …` + `B2R.RESULT RZ, Pu`

## Open questions
- Whether cuobjdump prints the B2R/R2B `BAR` default mode as a bare mnemonic (assumed) or
  `.BAR` — only `.RESULT` was captured.
- Exact meaning of `B2R.WARP`/`R2B` named-barrier state (save/restore semantics) and which
  driver/trap path emits them.
