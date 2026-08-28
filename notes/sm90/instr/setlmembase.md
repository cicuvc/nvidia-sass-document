# SETLMEMBASE — Set local-memory base address

**Opcode mnemonic:** `SETLMEMBASE` = `0b1111000001` = **0x3c1** | **Pipe:** `mio_pipe` | since **sm_70**

> **Status: silicon-verified on H20 (sm_90), 2026-08.** ptxas/nvcc does not
> normally emit this instruction, but a hand-assembled cubin executes it.

Write the executing warp's **local-memory backing-aperture base** from a GPR
pair — the reverse of `GETLMEMBASE`.

## Semantics
`SETLMEMBASE Ra` writes the executing warp's local-memory backing base from a
64-bit register pair `Ra:Ra+1` (no destination; `ISRC_A_SIZE=64`).

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

## Constructed encodings
| Lo64 | Hi64* | Reconstruction |
|------|-------|----------------|
| `0x00000000020073c1` | `0x0001c00000000000` | `SETLMEMBASE R2` (R2:R3) |
| `0x00000000060073c1` | `0x0001c00000000000` | `SETLMEMBASE R6` (R6:R7) |

\* Hi64 shows pinned `dst_wr_sb`=0x7; real scheduling bits unknown. Decoder: `tools/decode_lmembase.py`.

## Open questions
- Real cuobjdump text form unconfirmed.
- Shares `SETCTAID`'s `VQ_ADU` queue — possibly used during kernel prologue.

## H20 silicon verification and correction (2026-08)

The full switch experiment now passes on both H20 / sm_90 and RTX 5090 /
sm_120. On H20, switching `A → B → A → B` made the same local address alternate
between two independent backing words. Every one of these checks passed 32/32:

- `GETLMEMBASE` immediately reported `B`;
- an `STL` under `B` was visible through the transformed global VA in `B`;
- the old word under `A` remained unchanged;
- `LDL` selected the `B`, then `A`, then `B` value as the base was switched;
- a host read of the ordinary allocation `B` observed the redirected store.

The earlier text here claimed that hand-built cubins could not exercise
`LDL`/`STL` and that modern ptxas spills used `LDG`/`STG`. Both claims were
incorrect: the newer probe forms the ABI local address correctly, and sm_120
ptxas emits real `LDL`/`STL` for register spills. The previous faults reflected
an invalid address/context assumption, not unsupported instructions.

This establishes the backing-base side effect on real sm_90 silicon. The exact
state scope under divergent execution is still open; all lanes in the test warp
executed the SET convergently.

See the dedicated [sm_120 SETLMEMBASE note](../../sm120/instr/setlmembase.md)
and the [full local-memory backing study](../../sm120/arch/local_memory_backing_va.md).
