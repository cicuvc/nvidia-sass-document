# GETLMEMBASE / SETLMEMBASE — Get/Set per-thread local-memory base address

**Opcode mnemonics:** `GETLMEMBASE` = `0b1111000000` = **0x3c0** | `SETLMEMBASE` = `0b1111000001` = **0x3c1** | **Pipe:** `mio_pipe` | since **sm_70** (crucible idx 65 / 64)

> **Status: NOT empirically verified (legacy).** ptxas/nvcc (CUDA 13.1) do not emit these —
> modern local-memory spill/addressing uses the implicit per-thread ABI local window (`LDL`/
> `STL` address it directly), so no explicit base-pointer register is needed. Absent from the
> available libraries; crucible confirms both exist since sm_70 but adds no encoding detail.
> Field layout below is spec-derived; example encodings are round-trip constructions, not
> silicon captures.

## Semantics (speculation)
A matched **get/set pair** for the executing thread's **local-memory base address** — the
64-bit pointer to the base of the per-thread local-memory window (the region `LDL`/`STL` /
register spills target).
- **`GETLMEMBASE Rd`** — reads the current local-mem base into a 64-bit register pair `Rd:Rd+1`
  (no source; `IDEST_SIZE=64`).
- **`SETLMEMBASE Ra`** — writes the local-mem base from a 64-bit register pair `Ra:Ra+1` (no
  destination; `ISRC_A_SIZE=64`).

Historically the driver/kernel prologue could establish or relocate the local window base
(e.g. for context switch / trap save-restore, or ABI setup). On sm_90 the pair still occupies
ISA opcode slots but is unused by ptxas because local addressing is now implicit. They live in
the `mio_pipe` alongside the other per-CTA address-setup ops (`SETCTAID`, `AL2P`); `SETLMEMBASE`
even shares `SETCTAID`'s `VQ_ADU` queue.

## Variant overview
Each is a single CLASS / single opcode, no modifiers — just a guard predicate and one 64-bit
register operand.

## Fields (128-bit)
| | **GETLMEMBASE** (0x3c0) | **SETLMEMBASE** (0x3c1) |
|--|------------------------|-------------------------|
| direction | HW state → GPR | GPR → HW state |
| register | `Rd` [23:16] (dest, 64-bit pair) | `Ra` [31:24] (src, 64-bit pair) |
| INSTRUCTION_TYPE | `INST_TYPE_DECOUPLED_RD_WR_SCBD` | `INST_TYPE_DECOUPLED_RD_SCBD` |
| VIRTUAL_QUEUE | `$VQ_UNORDERED` | `$VQ_ADU` |
| IDEST_SIZE / ISRC_A_SIZE | 64 / 0 | 0 / 64 |
| write scoreboard | allowed (`dst_wr_sb`) | forbidden (`dst_wr_sb` pinned 0x7) |

Common encoding fields (both):
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x3c0 / 0x3c1 |
| [14:12] / [15] | `Pg` / `Pg_not` | guard predicate (7=PT hidden) |
| [124:122]∥[109:105] | `opex` | TABLES_opex_0(batch_t,usched_info) scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask |
| [115:113] | `src_rel_sb` | read scoreboard |
| [112:110] | `dst_wr_sb` | GET: write scoreboard; SET: pinned 0x7 |
| [103:102] | `pm_pred` | perfmon predicate |

**Register constraints (both):** the 64-bit operand must be even-aligned
(`MISALIGNED_REG_ERROR`), `!= R254`, and `<= MAX_REG-2` (room for the pair); `RZ` is allowed
(the `(Ra + (Ra==RZ)) % 2` idiom lets RZ pass the alignment check).

## Latency (from sm_90_latencies.txt)
`mio_pipe` members. `GETLMEMBASE` produces a 64-bit GPR pair (true/output deps tracked via the
write scoreboard, since it is decoupled/unordered — consumers must wait on `dst_wr_sb`).
`SETLMEMBASE` has no GPR result and forbids a write scoreboard; ordering is via `src_rel_sb`.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64* | Reconstruction |
|------|-------|----------------|
| `0x00000000000273c0` | `0x0000000000000000` | `GETLMEMBASE R2` (R2:R3) |
| `0x00000000000473c0` | `0x0000000000000000` | `GETLMEMBASE R4` (R4:R5) |
| `0x00000000020073c1` | `0x0001c00000000000` | `SETLMEMBASE R2` (R2:R3) |
| `0x00000000060073c1` | `0x0001c00000000000` | `SETLMEMBASE R6` (R6:R7) |

\* Hi64 shows only opcode bit[91] and (for SET) the pinned `dst_wr_sb`=0x7; real `opex` /
`req_bit_set` scheduling bits are compiler-chosen and unknown. Decoder + round-trip test:
`tools/decode_lmembase.py`.

## Open questions
- **Unconfirmed** cuobjdump text form (bare `GETLMEMBASE Rd` / `SETLMEMBASE Ra` assumed) and
  whether the 64-bit pair prints as `Rn` or with a `.64` suffix — no real disassembly captured.
- Whether any current path (trap handler, driver context save/restore) still issues them, or
  they are fully vestigial on Hopper.
- Address space / semantics of the "base" (generic 64-bit pointer vs a HW window descriptor).
