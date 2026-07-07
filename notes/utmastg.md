# UTMASTG — Uniform TMA tensor store (shared → global)

**Opcode mnemonic:** `UTMASTG` = `0b1001110110101` = **0x13b5** | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

> TODO note: idx 245 is mislabeled **`UTMALST`** ("TMA load/store") — no such
> mnemonic exists in the sm_90 spec (`query_sm90.py mnem UTMALST` → no variants).
> The real store instruction is **`UTMASTG`** (this note).

## Semantics
UTMASTG is the SASS lowering of PTX **`cp.async.bulk.tensor…`** in the *store*
direction (shared::cta → global). One elected thread on the uniform datapath
launches an asynchronous multi-dimensional (1D–5D) **tensor tile** copy from
shared to global driven by a 128-byte tensor-map descriptor. Unlike the load
(`UTMALDG`), there is **no mbarrier / URc operand and no multicast** — stores
complete through the **bulk-async-group** counted scoreboard
(`UTMACMDFLUSH` + `DEPBAR.LE`), see `notes/tma_mbarrier.md`.

Operands: `UTMASTG.<dim>[.IM2COL] [URb], [URa] [, desc[URe]]`
- `URb` — the tile **coordinate** block (`Ra_URb`; multi-reg, sized by `dim`) into the global tensor
- `URa` — 64-bit pointer to the tensor-map descriptor (`Sa`, 2-reg aligned) — actually the **source** shared address + descriptor; ptxas emits `[URb],[URa]` with `URb` = descriptor/coord side, `URa` = shared source (same operand convention as `UTMALDG`)
- `desc[URe]` — optional memory descriptor (the `_desc` variant, `memdesc=1`)

## Variant overview
| variant | opcode | memdesc | when emitted |
|---|---|---|---|
| `utmastg__UUU` | 0x13b5 | 0 | plain tensor store |
| `utmastg__UUU_desc` | 0x13b5 | 1 | mem-descriptor form |

Single opcode; `memdesc` bit [76] discriminates. **No 0x15b4/0x13b4 split** like
UTMALDG — stores always carry the descriptor+coord operands, never an mbarrier URc
(there is no consumer barrier to signal), so there is only one opcode.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `dim` | rndMode | [81:79] | TENSORDIM | 1D=0,2D=1,3D=2,4D=3,5D=4 (5–7 = INVALID) |
| `im2col` | fc | [82] | IM2COL | noim2col=0, IM2COL=1 |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 `desc[URe]` |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

Constraints (CONDITIONS): `.IM2COL` only valid with 3D/4D/5D; `dim` must not be
INVALID5/6/7; `URb` (coordinate block) alignment/range grows with `dim`
(1D ≤MAX−2 & %2==0 … 5D ≤MAX−6 & %8==0). Coordinate payload:
`ISRC_B_SIZE = 64 + {2D:+32,3D:+64,4D:+96,5D:+128}` — note the base is **64** here
(vs **96** for UTMALDG, which also carries the smem-dest register in `URb`).

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard for source |
| [112:110] | dst_wr_sb | `*7` (no write scoreboard) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x13b5 |
| [82] | fc | im2col |
| [81:79] | rndMode | dim (TENSORDIM) |
| [76] | memdesc | 0 plain / 1 desc |
| [45:40] | hdrtblbase6 | URe (descriptor; desc variant only) |
| [37:32] | Ra_URb | URb (coord block / descriptor side) |
| [29:24] | Sa | URa (shared source / descriptor ptr, 64-bit) |
| [15] | Pg_not | `@!` predicate negate |
| [14:12] | Pg | UPg |

No `sz`[75] (multicast) or `Ra_URc`[69:64] fields — the store form omits them.

## Cross-comparison
| op | PTX | dir | opcode(s) | multicast? | mbarrier URc? |
|---|---|---|---|---|---|
| `UTMALDG` | `cp.async.bulk.tensor` load | g→s | 0x15b4 / 0x13b4 | yes | yes (tx-count) |
| **UTMASTG** | `cp.async.bulk.tensor` store | s→g | 0x13b5 | no | no (bulk-group) |
| `UTMAREDG` | `cp.reduce.async.bulk.tensor` | s→g reduce | — | no | no |
| `UBLKCP` | `cp.async.bulk` (non-tensor) | g↔s | 0x13ba | yes(load) | yes(load) |

Opcodes cluster: 0x13b4 (UTMALDG+URc), 0x13b5 (UTMASTG), 0x13ba (UBLKCP) — the low
nibble discriminates load/store/blkcp within the TMA family. All share `udp_pipe`,
`OP_TMA`, `VQ_TMA_UNORDERED_WR`, single-thread `ELECT` issue.

## Latency (from `sm_90_latencies.txt`)
`UTMASTG` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. Decoupled
read-scoreboard op, `IDEST_SIZE=0`. Its `rd_sb` (observed **rd_sb=1** on every
store) protects the **shared source** from a later writer (WAR) until the copy
engine has read it — this is exactly what `cp.async.bulk.wait_group.read`
(`DEPBAR.LE SB0,0`) waits on. `dst_wr_sb=*7` (no write scoreboard). See
`notes/tma_mbarrier.md` for the `UTMACMDFLUSH`+`DEPBAR.LE` completion flow.

## Verified encodings (`tests/utmastg_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|---|---|---|
| `0x00000004060073b5` | `0x0003e20008000000` | `UTMASTG.1D [UR4], [UR6]` |
| `0x00000004080073b5` | `0x0003e20008008000` | `UTMASTG.2D [UR4], [UR8]` |
| `0x000000040a0073b5` | `0x0003e20008010000` | `UTMASTG.3D [UR4], [UR10]` |
| `0x000000080e0073b5` | `0x0003e20008018000` | `UTMASTG.4D [UR8], [UR14]` |
| `0x000000080e0073b5` | `0x0003e20008020000` | `UTMASTG.5D [UR8], [UR14]` |
| `0x000000040a0073b5` | `0x0003e20008050000` | `UTMASTG.3D.IM2COL [UR4], [UR10]` |

Decoder `tools/decode_utmastg.py`: **6/6 PASS**. `dim` is Hi64 bits [81:79]
(0→1D … 4→5D); `.IM2COL` sets bit [82] (3D+IM2COL Hi64 = `0x...050000`).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.async.bulk.tensor.{1..5}d.global.shared::cta.bulk_group [tm,{coords}],[s]` | `UTMASTG.<n>D [URb],[URa]` |
| `…tensor.3d.im2col_no_offs…` | `UTMASTG.3D.IM2COL [URb],[URa]` |
| `cp.async.bulk.commit_group` | `UTMACMDFLUSH` |
| `cp.async.bulk.wait_group.read N` | `DEPBAR.LE SBn, N` |

## Open questions
- Exact coord/descriptor packing inside `URb` (base 64-bit vs UTMALDG's 96-bit).
- `req_bit_set` semantics (same open item as UBLKCP/UTMALDG).
- Whether the `_desc` (memdesc=1) store form is emitted from stock PTX.
