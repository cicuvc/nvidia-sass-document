# B2R — Barrier register → GPR move

**Opcode mnemonic:** `B2R` = `0b1100011100` = **0x31c** | **Pipe:** `mio_pipe` (MIO_SLOW_OPS) | **VIRTUAL_QUEUE:** `$VQ_BAR_EXCH` (barrier-exchange, =33) | **INSTRUCTION_TYPE:** `DECOUPLED_RD_WR_SCBD` | compute-only (`SHADER_TYPE==CS`) | since sm_70

Move data from the block's **barrier hardware** into a GPR. `B2R` reads barrier state into a register.

## Semantics — 3 modes via `stride`[79:78]
| mode | `BarmdBAR/RESULT/WARP` | SASS | use |
|------|-----------------------|------|-----|
| 0 | BAR | `B2R Rd, barname` | read named-barrier `barname` (0–15) state into `Rd` |
| 1 | RESULT | `B2R.RESULT Rd[, Pu]` | read the result of a preceding `BAR.RED` |
| 2 | WARP | `B2R.WARP Rd` | read warp-level barrier/convergence state into `Rd` |

**RESULT mode is verified** — it is how `__syncthreads_count/and/or` extract the block-wide barrier reduction:
```
BAR.RED.POPC.DEFER_BLOCKING 0x0, P0 ;  B2R.RESULT R7        ; __syncthreads_count -> count in R7
BAR.RED.AND .DEFER_BLOCKING 0x0, P0 ;  B2R.RESULT RZ, P0    ; __syncthreads_and   -> bool in P0
BAR.RED.OR  .DEFER_BLOCKING 0x0, P0 ;  B2R.RESULT RZ, P0    ; __syncthreads_or    -> bool in P0
```

## Fields (128-bit)
| bits | field | value |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x31c |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [23:16] | `Rd` | dest GPR (32-bit) |
| [57:54] | `barname` | named barrier (BAR mode) |
| [79:78] | `stride`=mode | 0=BAR, 1=RESULT, 2=WARP |
| [83:81] | `Pu` | RESULT dest predicate |
| [112:110] | `dst_wr_sb` | scoreboard |
| [124:122]∥[109:105] | `opex` | scheduling |

`Rd` ≠ R254.

## Cross-comparison (barrier-state family)
| op | dir | what |
|----|-----|------|
| **B2R** | barrier→GPR | read barrier result / named-barrier / warp state |
| **R2B** | GPR→barrier | write named-barrier / warp state |
| **BMOV** (idx 56) | GPR↔convergence-barrier reg (B0–B15) | separate convergence-barrier move |
| **BAR.RED** | — | block reduction that B2R.RESULT reads |

## Latency (from sm_90_latencies.txt)
`mio_pipe`, `MIO_SLOW_OPS`. `VQ_BAR_EXCH` decoupled: B2R's GPR result is consumed via the write scoreboard.

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | source |
|------|------|-------------|--------|
| `0x000000000007731c` | `0x000e2800000e4000` | `B2R.RESULT R7` | **real** `__syncthreads_count` |
| `0x0000000000ff731c` | `0x000e240000004000` | `B2R.RESULT RZ, P0` | **real** `__syncthreads_and/or` |

Round-trip only (not observed on sm_90): `B2R R4, 0x3` (BAR), `B2R.WARP R5`.
Decoder: `tools/decode_b2r_r2b.py` (real + round-trips pass). Test: `tests/b2r_test.cu`.

### PTX→SASS mapping
- `__syncthreads_count(p)` → `BAR.RED.POPC …` + `B2R.RESULT Rd`
- `__syncthreads_and(p)` → `BAR.RED.AND …` + `B2R.RESULT RZ, Pu`
- `__syncthreads_or(p)` → `BAR.RED.OR …` + `B2R.RESULT RZ, Pu`

## Open questions
- Whether cuobjdump prints the B2R `BAR` default mode as a bare mnemonic (assumed) or `.BAR` — only `.RESULT` was captured.
- Exact meaning of `B2R.WARP` state (save/restore semantics) and which driver/trap path emits it.
