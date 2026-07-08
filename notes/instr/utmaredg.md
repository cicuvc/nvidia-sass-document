# UTMAREDG — Uniform TMA tensor reduction store (shared → global, atomic reduce)

**Opcode mnemonic:** `UTMAREDG` = `0b1001110110110` = **0x13b6** | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

> TODO: idx 244 was listed as **`UTMREDG`** (ref_memo abbreviation) `-> UTMAREDG`.

## Semantics
UTMAREDG is the SASS lowering of PTX **`cp.reduce.async.bulk.tensor…`** — a TMA
tensor store (shared::cta → global) that **atomically reduces** the tile into the
destination global tensor instead of overwriting it. Identical framing to
`UTMASTG` (single elected thread, uniform datapath, bulk-async-group completion
via `UTMACMDFLUSH` + `DEPBAR.LE`), plus a `RedOp` modifier selecting the reduction.

Operands: `UTMAREDG.<dim>[.IM2COL].<op> [URb], [URa] [, desc[URe]]`
- `URb` — tile **coordinate** block (`Ra_URb`; multi-reg, sized by `dim`)
- `URa` — 64-bit descriptor pointer + shared source (`Sa`, 2-reg aligned)
- `desc[URe]` — optional memory descriptor (the `_desc` variant, `memdesc=1`)

## Variant overview
| variant | opcode | memdesc | when emitted |
|---|---|---|---|
| `utmaredg__UUU` | 0x13b6 | 0 | plain reduction store |
| `utmaredg__UUU_desc` | 0x13b6 | 1 | mem-descriptor form |

Single opcode; `memdesc` [76] discriminates. No multicast / mbarrier URc (same as
UTMASTG — reduction stores use bulk-group completion, no consumer barrier).

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `dim` | rndMode | [81:79] | TENSORDIM | 1D=0,2D=1,3D=2,4D=3,5D=4 (5–7 = INVALID) |
| `im2col` | fc | [82] | IM2COL | noim2col=0, IM2COL=1 (3D/4D/5D only) |
| **`op`** | **Pnz** | **[89:87]** | **RedOp** | **ADD=0,MIN=1,MAX=2,INC=3,DEC=4,AND=5,OR=6,XOR=7** |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 `desc[URe]` |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

The **only structural difference from UTMASTG** is the `op` (RedOp) field at
[89:87] (`Pnz` slot — reused; in arithmetic ops `Pnz` is a predicate-nonzero
output). `ISRC_B_SIZE = 64 + {2D:+32…5D:+128}` — same coordinate payload as UTMASTG.

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard for source |
| [112:110] | dst_wr_sb | `*7` (no write scoreboard) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x13b6 |
| [89:87] | Pnz | op (RedOp) |
| [82] | fc | im2col |
| [81:79] | rndMode | dim (TENSORDIM) |
| [76] | memdesc | 0 plain / 1 desc |
| [45:40] | hdrtblbase6 | URe (descriptor; desc variant only) |
| [37:32] | Ra_URb | URb (coord block / descriptor side) |
| [29:24] | Sa | URa (shared source / descriptor ptr, 64-bit) |
| [15] | Pg_not | `@!` predicate negate |
| [14:12] | Pg | UPg |

## Cross-comparison (TMA family)
| op | PTX | dir | opcode | extra field |
|---|---|---|---|---|
| `UTMALDG` | `cp.async.bulk.tensor` load | g→s | 0x15b4 / 0x13b4 | multicast, URc(mbarrier) |
| `UTMASTG` | `cp.async.bulk.tensor` store | s→g | 0x13b5 | — |
| **UTMAREDG** | `cp.reduce.async.bulk.tensor` | s→g reduce | **0x13b6** | **RedOp [89:87]** |
| `UBLKCP` | `cp.async.bulk` (non-tensor) | g↔s | 0x13ba | dst/src, multicast |

Opcode family low nibble: 0x13b4 load / 0x13b5 store / **0x13b6 reduce** / 0x13ba
blkcp. All `udp_pipe`, `OP_TMA`, `VQ_TMA_UNORDERED_WR`, single-thread `ELECT`.

## Latency (from `sm_90_latencies.txt`)
`UTMAREDG` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. Decoupled
read-scoreboard op, `IDEST_SIZE=0`. Observed **rd_sb=1** on every case — protects
the shared source (WAR) until the copy engine has read it; drained by
`cp.async.bulk.wait_group.read` (`DEPBAR.LE SB0,0`). `dst_wr_sb=*7`. See
`../arch/tma_mbarrier.md` for the `UTMACMDFLUSH`+`DEPBAR.LE` bulk-group flow.

## Verified encodings (`tests/utmaredg_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|---|---|---|
| `0x00000004060073b6` | `0x0023d80008000000` | `UTMAREDG.1D.ADD [UR4], [UR6]` |
| `0x000000040a0073b6` | `0x0003f20008008000` | `UTMAREDG.2D.ADD [UR4], [UR10]` |
| `0x000000040a0073b6` | `0x0003f20008808000` | `UTMAREDG.2D.MIN [UR4], [UR10]` |
| `0x000000040a0073b6` | `0x0003f20009008000` | `UTMAREDG.2D.MAX [UR4], [UR10]` |
| `0x000000040a0073b6` | `0x0003f20009808000` | `UTMAREDG.2D.INC [UR4], [UR10]` |
| `0x000000040a0073b6` | `0x0003f2000a008000` | `UTMAREDG.2D.DEC [UR4], [UR10]` |
| `0x000000040a0073b6` | `0x0003f2000a808000` | `UTMAREDG.2D.AND [UR4], [UR10]` |
| `0x000000040a0073b6` | `0x0003f2000b008000` | `UTMAREDG.2D.OR [UR4], [UR10]` |
| `0x000000040a0073b6` | `0x0003f2000b808000` | `UTMAREDG.2D.XOR [UR4], [UR10]` |
| `0x000000040a0073b6` | `0x0003f20008010000` | `UTMAREDG.3D.ADD [UR4], [UR10]` |
| `0x000000080e0073b6` | `0x0003ee0008020000` | `UTMAREDG.5D.ADD [UR8], [UR14]` |

Decoder `tools/decode_utmaredg.py`: **11/11 PASS**. RedOp is Hi64 [89:87]: each op
step of +1 shifts Hi64 by `0x00800000` (ADD `...08008000` → MIN `...08808000` → …
→ XOR `...0b808000`); `dim` is [81:79] as in UTMALDG/UTMASTG.

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.reduce.async.bulk.tensor.<n>d.global.shared::cta.<op>.tile.bulk_group [tm,{coords}],[s]` | `UTMAREDG.<n>D.<OP> [URb],[URa]` |
| `cp.async.bulk.commit_group` | `UTMACMDFLUSH` |
| `cp.async.bulk.wait_group.read N` | `DEPBAR.LE SBn, N` |

PTX reduction op → RedOp: `add→ADD, min→MIN, max→MAX, inc→INC, dec→DEC,
and→AND, or→OR, xor→XOR` (direct 0–7 mapping).

## Open questions
- Element type / precision of the reduction (f16/bf16/f32/s32/u32) — likely carried
  in the tensor-map descriptor, not the instruction (no type field observed).

- Whether `_desc` (memdesc=1) reduction form is emitted from stock PTX.
