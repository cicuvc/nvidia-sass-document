# GETLMEMBASE — Get local-memory base address

**Opcode mnemonic:** `GETLMEMBASE` = `0b1111000000` = **0x3c0** | **Pipe:** `mio_pipe` | since **sm_70**

> **Status: NOT empirically verified (legacy).** ptxas/nvcc (CUDA 13.1) do not emit this — modern local-memory spill/addressing uses the implicit per-thread ABI local window.

Read the executing thread's **local-memory base address** — the 64-bit pointer to the base of the per-thread local-memory window.

## Semantics (speculation)
`GETLMEMBASE Rd` — reads the current local-mem base into a 64-bit register pair `Rd:Rd+1` (no source; `IDEST_SIZE=64`).

## Variant overview
Single CLASS / opcode, no modifiers — guard predicate and one 64-bit register operand.

## Fields (128-bit)
| bits | field | value |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x3c0 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | dest (64-bit pair) |
| [124:122]∥[109:105] | `opex` | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask |
| [115:113] | `src_rel_sb` | read scoreboard |
| [112:110] | `dst_wr_sb` | write scoreboard |
| [103:102] | `pm_pred` | perfmon predicate |

Register constraint: 64-bit operand must be even-aligned, `!= R254`, `<= MAX_REG-2`; `RZ` allowed.

INSTRUCTION_TYPE: `INST_TYPE_DECOUPLED_RD_WR_SCBD`, VIRTUAL_QUEUE: `$VQ_UNORDERED`.

## Latency (from sm_90_latencies.txt)
`mio_pipe` member. Produces a 64-bit GPR pair; decoupled/unordered — consumers wait on `dst_wr_sb`.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64* | Reconstruction |
|------|-------|----------------|
| `0x00000000000273c0` | `0x0000000000000000` | `GETLMEMBASE R2` (R2:R3) |
| `0x00000000000473c0` | `0x0000000000000000` | `GETLMEMBASE R4` (R4:R5) |

\* Hi64 shows only opcode bit[91]; real scheduling bits are compiler-chosen. Decoder: `tools/decode_lmembase.py`.

## Open questions
- **Unconfirmed** cuobjdump text form (bare `GETLMEMBASE Rd` assumed) and whether the 64-bit pair prints with a `.64` suffix.
- Whether any current path (trap handler, driver context save/restore) still issues it.
