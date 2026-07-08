# SETLMEMBASE — Set local-memory base address

**Opcode mnemonic:** `SETLMEMBASE` = `0b1111000001` = **0x3c1** | **Pipe:** `mio_pipe` | since **sm_70**

> **Status: NOT empirically verified (legacy).** ptxas/nvcc (CUDA 13.1) do not emit this.

Write the executing thread's **local-memory base address** from a GPR pair — the reverse of `GETLMEMBASE`.

## Semantics (speculation)
`SETLMEMBASE Ra` — writes the local-mem base from a 64-bit register pair `Ra:Ra+1` (no destination; `ISRC_A_SIZE=64`).

## Variant overview
Single CLASS / opcode, no modifiers — guard predicate and one 64-bit register operand.

## Fields (128-bit)
| bits | field | value |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x3c1 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [31:24] | `Ra` | src (64-bit pair) |
| [124:122]∥[109:105] | `opex` | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask |
| [115:113] | `src_rel_sb` | read scoreboard |
| [112:110] | `dst_wr_sb` | pinned 0x7 |
| [103:102] | `pm_pred` | perfmon predicate |

Register constraint: 64-bit operand must be even-aligned, `!= R254`, `<= MAX_REG-2`; `RZ` allowed.

INSTRUCTION_TYPE: `INST_TYPE_DECOUPLED_RD_SCBD`, VIRTUAL_QUEUE: `$VQ_ADU`.

## Latency (from sm_90_latencies.txt)
`mio_pipe` member. No GPR result, forbids write scoreboard; ordering via `src_rel_sb`.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64* | Reconstruction |
|------|-------|----------------|
| `0x00000000020073c1` | `0x0001c00000000000` | `SETLMEMBASE R2` (R2:R3) |
| `0x00000000060073c1` | `0x0001c00000000000` | `SETLMEMBASE R6` (R6:R7) |

\* Hi64 shows pinned `dst_wr_sb`=0x7; real scheduling bits unknown. Decoder: `tools/decode_lmembase.py`.

## Open questions
- Real cuobjdump text form unconfirmed.
- Shares `SETCTAID`'s `VQ_ADU` queue — possibly used during kernel prologue.
