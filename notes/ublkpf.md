# UBLKPF — Uniform block prefetch (non-tensor `cp.async.bulk.prefetch`)

**Opcode mnemonic:** `UBLKPF` = `0b1001110111100` = **0x13bc** | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

## Semantics
UBLKPF is the SASS lowering of PTX **`cp.async.bulk.prefetch`** — the *non-tensor*
bulk prefetch of a contiguous byte range from global memory into **L2**. It is the
prefetch counterpart of `UBLKCP` (the non-tensor bulk copy), just as `UTMAPF` is
the prefetch counterpart of `UTMALDG` for tensor tiles. Non-blocking,
fire-and-forget into L2; no shared-memory destination, no mbarrier.

Operands: `UBLKPF.L2 [URa], URc [, desc[URe]]`
- `URa` — **source** global address (64-bit uniform pair, `Sa`, 2-reg aligned)
- `URc` — **size** in bytes (32-bit, `Ra_URc`; must be a multiple of 16)
- `desc[URe]` — optional memory/cache-policy descriptor (`_desc` variant, `memdesc=1`)

## Variant overview
| variant | opcode | memdesc | when emitted |
|---|---|---|---|
| `ublkpf__UUU` | 0x13bc | 0 | plain bulk prefetch |
| `ublkpf__UUU_desc` | 0x13bc | 1 | with `.L2::cache_hint` policy (desc[URe]) |

Single opcode; `memdesc` bit [76] discriminates. The `.L2::cache_hint` PTX
qualifier (with a `cache_policy` operand) triggers the **desc** form — the policy
rides in the descriptor `desc[URe]`, not a separate instruction field.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `cache` | — (no bit) | — | L2ONLY | L2 (only value; always printed `.L2`) |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 `desc[URe]` |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

No `dim`/`im2col` (non-tensor — flat byte range, not a tile) and no direction
modifier (prefetch is always global→L2).

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard for source |
| [112:110] | dst_wr_sb | `*7` (no write scoreboard) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x13bc |
| [76] | memdesc | 0 plain / 1 desc |
| [69:64] | Ra_URc | URc (size, 32-bit) |
| [45:40] | hdrtblbase6 | URe (cache-policy descriptor; desc variant only) |
| [29:24] | Sa | URa (source global addr, 64-bit) |
| [15] / [14:12] | Pg_not / Pg | predicate |

No coordinate block (`ISRC_B_SIZE=0`), no smem operand. `ISRC_A_SIZE=64` (source
addr), `ISRC_C_SIZE=32` (size).

## Cross-comparison (bulk / TMA family)
| op | PTX | dir | opcode | tensor? | operands |
|---|---|---|---|---|---|
| `UBLKCP` | `cp.async.bulk` | g↔s | 0x13ba | no | [URb],[URa],URc |
| `UBLKRED` | `cp.reduce.async.bulk` | s→g reduce | 0x13bb | no | (reduce) |
| **UBLKPF** | `cp.async.bulk.prefetch` | g→L2 | **0x13bc** | no | [URa],URc |
| `UTMAPF` | `cp.async.bulk.prefetch.tensor` | g→L2 | 0x15b8/0x13b8 | yes | [URb],[URa][,URc] |

Opcode family low nibble at 0x13b_: a=blkcp, **b=blkred, c=blkpf**. The
non-tensor bulk trio (0x13ba/bb/bc) sits just past the tensor ops (0x13b4–b8).
All `udp_pipe` / `OP_TMA` / `VQ_TMA_UNORDERED_WR`.

## Latency (from `sm_90_latencies.txt`)
`UBLKPF` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. Decoupled
read-scoreboard op, `IDEST_SIZE=0`. Observed **rd_sb=0** (no read scoreboard) —
like `UTMAPF`, prefetch is fire-and-forget with no source buffer to protect and no
completion to await (contrast `UBLKCP`/`UTMASTG` which set rd_sb=1). `dst_wr_sb=*7`.
Notably ptxas issues it **unconditionally from all threads** (no `ELECT`
single-thread gating), unlike the data-moving bulk ops.

## Verified encodings (`tests/ublkpf_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|---|---|---|
| `0x00000000060073bc` | `0x0001e40008000004` | `UBLKPF.L2 [UR6], UR4` |
| `0x00000600080073bc` | `0x0001e40008001004` | `UBLKPF.L2 [UR8], UR4, desc[UR6]` |

Decoder `tools/decode_ublkpf.py`: **2/2 PASS**. In the desc form, `memdesc` [76]
= 1 and `URe` [45:40] = 6 (Lo64 `...0600...`, i.e. bits [45:40] hold UR6).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.async.bulk.prefetch.L2.global [src], size` | `UBLKPF.L2 [URa], URc` |
| `cp.async.bulk.prefetch.L2.global.L2::cache_hint [src], size, policy` | `UBLKPF.L2 [URa], URc, desc[URe]` |

## Open questions
- `desc[URe]` layout — carries the L2 cache-eviction policy (from
  `createpolicy`/`cache_policy`); exact descriptor bitfield not decoded here.
- `req_bit_set` semantics (shared open item across the TMA/bulk family).
