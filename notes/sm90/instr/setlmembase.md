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

## Resolved: verified (SM120, 2026-08)

`tests/asm_construct/test_lmembase.py` (MOV32I builds the 64-bit pair, then
`SETLMEMBASE` → `GETLMEMBASE` round-trip):

- `SETLMEMBASE R10` then `GETLMEMBASE R8` returns **exactly** the same 64-bit
  value (verified for a device-buffer address and the default local base).
  The two instructions face the SAME 64-bit address value.
- Default `GETLMEMBASE` (no SET) returns the per-thread default local window
  base (e.g. `0x3fffcd800000`), a valid address (STG-able).
- `SETLMEMBASE` to an invalid address (e.g. `0x1111...`) faults with
  `CUDA_ERROR_ILLEGAL_ADDRESS` (700) — the driver validates the window.

**STL/LDL limitation**: "SETLMEMBASE then STL" could not be exercised — `STL
[RZ+off]` (and the register-base form) fault 700 in a hand-built cubin.
STL/LDL are legacy instructions that rely on a driver-established local-window
context (the `R1` stack pointer / window) that a hand-built ELF does not
provide; modern ptxas never emits them (local spill uses generic LDG/STG via
the `c[0x0][0x28]` stack pointer).  SETLMEMBASE/GETLMEMBASE themselves are
fully functional.
