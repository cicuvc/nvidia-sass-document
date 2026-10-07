# R2B — GPR → Barrier register move

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** low  
**Last verified:** unknown  
**Probe:** not recorded in this note  
**Open items:** 1 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: lives under notes/sm90/; no part named, so the default measurement site sm120 is assumed

## Conclusion

**Opcode mnemonic:** `R2B` = `0b1100011110` = **0x31e** | **Pipe:** `mio_pipe` (MIO_SLOW_OPS) | **VIRTUAL_QUEUE:** `$VQ_BAR_EXCH` (barrier-exchange, =33) | **INSTRUCTION_TYPE:** `DECOUPLED_RD_SCBD` | compute-only (`SHADER_TYPE==CS`) | since sm_70

Write a GPR into the block's **barrier hardware** (Register-to-Barrier). The reverse of `B2R`.

## Semantics
`R2B[.WARP] barname, Rb` — write GPR `Rb` (32-bit) into named-barrier `barname` (BAR mode, default) or warp barrier state (WARP mode). `MODE_BAR_WARP`: BAR=0, WARP=2 (1,3 illegal). No destination; `dst_wr_sb` pinned 0x7. `INST_TYPE_DECOUPLED_RD_SCBD`.

Likely a barrier **state save/restore** primitive (context switch / trap handler) — not observed from nvcc; documented from spec + round-trip only.

## Fields (128-bit)
| bits | field | value |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x31e |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [39:32] | `Rb` | source GPR (32-bit) |
| [57:54] | `barname` | named barrier (4-bit) |
| [79:78] | `stride`=mode | 0=BAR, 2=WARP |
| [112:110] | `dst_wr_sb` | pinned 0x7 |
| [124:122]∥[109:105] | `opex` | scheduling |

`Rb` ≠ R254.

## Cross-comparison (barrier-state family)
| op | dir | what |
|----|-----|------|
| **B2R** | barrier→GPR | read barrier result / named-barrier / warp state |
| **R2B** | GPR→barrier | write named-barrier / warp state |
| **BMOV** (idx 56) | GPR↔convergence-barrier reg (B0–B15) | separate convergence-barrier move |

## Latency (from sm_90_latencies.txt)
`mio_pipe`, `MIO_SLOW_OPS`. `VQ_BAR_EXCH` decoupled: no GPR result, no write scoreboard dependency.

## Evidence

## Verified encodings (round-trip only — not observed on sm_90)
`R2B 0x1, R6`, `R2B.WARP 0x2, R7`.
Decoder: `tools/decode_b2r_r2b.py` (round-trips pass). Test: `tests/b2r_test.cu`.

## History / retracted hypotheses

> Claims below were **superseded, refuted, or never settled** by later work; they are kept
> for provenance. Do not cite them as current.

## Open questions
- Exact meaning of `R2B` named-barrier state (save/restore semantics) and which driver/trap path emits them.  <!-- open-question: answered answered by "§Semantics" in this note -->

