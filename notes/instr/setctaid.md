# SETCTAID — Set CTA (thread-block) ID hardware state

**Opcode mnemonic:** `SETCTAID` = `0b1100011111` = **0x31f** (13-bit slot) | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VIRTUAL_QUEUE=$VQ_ADU` | compute-only (`SHADER_TYPE==CS`) | since **sm_70** (crucible opcode idx 63)

> **Status: NOT empirically verified.** nvcc/ptxas (CUDA 13.1) do not emit `SETCTAID` from
> user CUDA C/C++ or inline PTX, and it is absent from the available libraries. It is a
> **driver/ABI setup instruction** — grouped in the `VQ_ADU` virtual queue with `SETLMEMBASE`
> and `AL2P`, i.e. per-CTA hardware-state / address setup ops that the runtime/trap-handler
> issues, not application code. Crucible confirms it exists (sm_70+) but adds no encoding
> detail. Field layout below is spec-derived; example encodings are round-trip constructions,
> not silicon captures.

## Semantics (speculation)
Writes the executing CTA's **block-index** hardware state (`blockIdx`, the value normally read
via `S2R ..., SR_CTAID.{X,Y,Z}`) from a general register `Ra`. It has no GPR destination
(`IDEST_SIZE=0`) — the "write" is to internal CTA state, hence `DECOUPLED_RD_WR_SCBD` (reads a
GPR, writes hidden state, decoupled through the memory-I/O pipe). `VQ_ADU` (virtual queue 0)
ties it to the address/CTA-setup unit shared with `SETLMEMBASE` (sets local-memory base) and
`AL2P` (local→physical address). Plausible emitters: cooperative-launch / persistent-grid rank
assignment, CDP child-grid setup, or driver relaunch/trap paths that must (re)establish CTA
coordinates. The `.dim` modifier selects which coordinate(s) are written.

## Variant overview (1 CLASS)
Single class `setctaid_`, one opcode (0x31f). Behaviour is parameterized by the `dim` modifier.

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x31f | 13-bit |
| [14:12] / [15] | `Pg` / `Pg_not` | Pg guard | guard predicate (7=PT hidden) |
| [31:24] | `Ra` | Register | source GPR (0xFF=RZ) |
| [79:78] | `stride` | `dim` (CTA_DIM) | 0=X, 1=Y, 2=Z, **3=ALL (default)** |
| [124:122]∥[109:105] | `opex` | TABLES_opex_0(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | scoreboard | **`dst_wr_sb` must be 0x7** (no write scoreboard allowed) |
| [103:102] | `pm_pred` | perfmon predicate | |

**`CTA_DIM`**: `"X"=0, "Y"=1, "Z"=2, "ALL"=3`.

## Operand width (dim-dependent)
`ISRC_A_SIZE = 32 + (dim==ALL)*32`:
- `.X` / `.Y` / `.Z` → `Ra` is a **32-bit** single register (one coordinate).
- `ALL` (default) → `Ra` is a **64-bit register pair** (packed X/Y/Z coordinate), so `Ra` must
  be even-aligned (`MISALIGNED_REG_ERROR`) and leave room (`Ra<=MAX_REG-2`).

`Ra` also may not be `R254` (`OOR_REG_ERROR`). `SETCTAID` cannot specify a write scoreboard
(`dst_wr_sb==0x7` enforced) — consistent with it not producing a scoreboard-tracked GPR result.

## Cross-comparison (VQ_ADU setup ops)
| op | role |
|----|------|
| **SETCTAID** | set CTA block-index hardware state from GPR |
| **SETLMEMBASE** | set the CTA's local-memory window base |
| **AL2P** | convert a local-memory offset to a physical address |

All three: `mio_pipe`, `VQ_ADU`, compute-only, decoupled — the per-CTA address/identity setup
family, normally issued by driver/runtime rather than user code.

## Latency (from sm_90_latencies.txt)
`mio_pipe` member. No GPR destination, so it produces no true/output dependency for consumers;
ordering is via scoreboards (`src_rel_sb`; write scoreboard forbidden). Consumer instructions
reading `SR_CTAID` afterward observe the updated value only through the pipeline's own ordering.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64* | Reconstruction |
|------|-------|----------------|
| `0x000000000200731f` | `0x0001c0000000c000` | `SETCTAID R2` (ALL, R2:R3 pair) |
| `0x000000000400731f` | `0x0001c00000000000` | `SETCTAID.X R4` |
| `0x000000000500731f` | `0x0001c00000004000` | `SETCTAID.Y R5` |
| `0x000000000600731f` | `0x0001c00000008000` | `SETCTAID.Z R6` |

\* Hi64 shows opcode bit[91], `stride`[79:78], and `dst_wr_sb`=0x7[112:110]; real `opex` /
`req_bit_set` scheduling bits are compiler-chosen and unknown. Decoder + round-trip test:
`tools/decode_setctaid.py`.

## Open questions
- **Unconfirmed** whether cuobjdump prints the default `ALL` as a bare `SETCTAID` (assumed) or
  as `SETCTAID.ALL`, and whether the 64-bit `ALL` operand prints as a register pair `Rn` or
  `Rn.64` etc. — no real disassembly captured.
- Exact packing of the 64-bit `ALL` operand (X/Y/Z bit fields within the pair).
- Which runtime/driver path actually emits it (cooperative launch? CDP? trap handler?).
