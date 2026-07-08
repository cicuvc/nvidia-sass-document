# UTMAPF — Uniform TMA tensor prefetch (global → L2)

**Opcode mnemonics:** `UTMAPF` = `0b1010110111000` = **0x15b8** (plain `.tile`, no `URc`) / `0b1001110111000` = **0x13b8** (with `URc`: im2col) | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

## Semantics
UTMAPF is the SASS lowering of PTX **`cp.async.bulk.prefetch.tensor`** — a
non-blocking prefetch of tensor tile data from global memory into **L2**. No
shared-memory destination and no mbarrier: it only warms the cache. Same
tensor-map descriptor mechanism and single-thread uniform issue as `UTMALDG`,
minus the data landing / completion signalling.

Operands: `UTMAPF.L2.<dim>[.IM2COL] [URb], [URa] [, URc] [, desc[URe]]`
- `URb` — tile **coordinate** block (`Ra_URb`; multi-reg, sized by `dim`)
- `URa` — 64-bit pointer to the tensor-map descriptor (`Sa`, 2-reg aligned)
- `URc` — extra operand (im2col offsets), only in the 0x13b8 form
- `desc[URe]` — optional memory descriptor (`_desc` variant, `memdesc=1`)

## Variant overview
| variant | opcode | URc | memdesc | when emitted |
|---|---|---|---|---|
| `utmapf__UUU` | 0x15b8 | — | 0 | plain `.tile` prefetch (1D–5D) |
| `utmapf__UUU_desc` | 0x15b8 | — | 1 | mem-descriptor form |
| `utmapf_URc__UUU` | 0x13b8 | yes | 0 | `.IM2COL` |
| `utmapf_URc__UUU_desc` | 0x13b8 | yes | 1 | im2col, mem-descriptor form |

Like UTMALDG, the opcode splits on whether a `URc` operand is printed: plain
tile prefetch (1D–5D) → **0x15b8**; im2col → **0x13b8**.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `cache` | — (no bit) | — | L2ONLY | L2 (only value; always printed `.L2`) |
| `dim` | rndMode | [81:79] | TENSORDIM | 1D=0,2D=1,3D=2,4D=3,5D=4 (5–7 = INVALID) |
| `im2col` | fc | [82] | IM2COLONLY | IM2COL=1 (0x13b8 only; 3D/4D/5D only) |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 `desc[URe]` |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

`.L2` is a mandatory printed modifier with **no encoding field** (the L2ONLY enum
has a single value). Coordinate payload: `ISRC_B_SIZE = 32 + {2D:+32…5D:+128}` —
base **32** (smaller than UTMALDG's 96 / UTMASTG's 64: prefetch needs no smem
dest register, just coords).

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard for source |
| [112:110] | dst_wr_sb | `*7` (no write scoreboard) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x15b8 / 0x13b8 |
| [82] | fc | im2col (0x13b8 only) |
| [81:79] | rndMode | dim (TENSORDIM) |
| [76] | memdesc | 0 plain / 1 desc |
| [69:64] | Ra_URc | URc (im2col; 0x13b8 only) |
| [45:40] | hdrtblbase6 | URe (descriptor; desc variant only) |
| [37:32] | Ra_URb | URb (coord block) |
| [29:24] | Sa | URa (tensor-map descriptor ptr, 64-bit) |
| [15] / [14:12] | Pg_not / Pg | predicate |

No `sz`[75] multicast field (prefetch never multicasts).

## Cross-comparison (TMA family)
| op | PTX | dir | opcode(s) | URc | notes |
|---|---|---|---|---|---|
| `UTMALDG` | `cp.async.bulk.tensor` load | g→s | 0x15b4/0x13b4 | multicast+mbarrier | ISRC_B base 96 |
| `UTMASTG` | store | s→g | 0x13b5 | — | base 64 |
| `UTMAREDG` | reduce | s→g | 0x13b6 | — | +RedOp |
| **UTMAPF** | `cp.async.bulk.prefetch.tensor` | g→L2 | **0x15b8/0x13b8** | im2col only | **base 32** |
| `UBLKCP` | `cp.async.bulk` | g↔s | 0x13ba | — | non-tensor |

Opcode family low nibble at 0x13b_: 4=load, 5=store, 6=reduce, **8=prefetch**,
a=blkcp. All `udp_pipe` / `OP_TMA` / `VQ_TMA_UNORDERED_WR`. UTMAPF's plain-form
alias uses the 0x15b_ prefix like UTMALDG's plain load (0x15b4).

## Latency (from `sm_90_latencies.txt`)
`UTMAPF` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. Decoupled
read-scoreboard op, `IDEST_SIZE=0` (no result). Observed **rd_sb=0** (no read
scoreboard set) — prefetch has no smem source buffer to protect and no completion
to await (fire-and-forget into L2), unlike UTMASTG/UTMAREDG (rd_sb=1). `dst_wr_sb=*7`.

## Verified encodings (`tests/utmapf_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|---|---|---|
| `0x00000006040075b8` | `0x0001e40008000000` | `UTMAPF.L2.1D [UR6], [UR4]` |
| `0x00000006040075b8` | `0x0001e40008008000` | `UTMAPF.L2.2D [UR6], [UR4]` |
| `0x00000008040075b8` | `0x0001e40008010000` | `UTMAPF.L2.3D [UR8], [UR4]` |
| `0x00000008040075b8` | `0x0001e40008018000` | `UTMAPF.L2.4D [UR8], [UR4]` |
| `0x00000008040075b8` | `0x0001e40008020000` | `UTMAPF.L2.5D [UR8], [UR4]` |
| `0x00000008060073b8` | `0x0001e40008050004` | `UTMAPF.L2.3D.IM2COL [UR8], [UR6], UR4` |

Decoder `tools/decode_utmapf.py`: **6/6 PASS**. `dim` is Hi64 [81:79]; `.IM2COL`
sets [82] (3D+IM2COL Hi64 = `0x...050004`, opcode switches to 0x13b8).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.async.bulk.prefetch.tensor.{1..5}d.L2.global.tile [tm,{coords}]` | `UTMAPF.L2.<n>D [URb],[URa]` (0x15b8) |
| `cp.async.bulk.prefetch.tensor.3d.L2.global.im2col …, {offs}` | `UTMAPF.L2.3D.IM2COL [URb],[URa],URc` (0x13b8) |

Fire-and-forget — no surrounding `ELECT`/mbarrier/DEPBAR framing needed (a bare
prefetch); the tested kernels issue it unconditionally from all threads (ptxas
does not force single-thread election for prefetch).

## Open questions
- `.L2::cache_hint` (with a `cache_policy` operand) — whether it adds a field or
  another operand; not triggered by the basic `.tile`/`.im2col` kernels here.
- `.tile::gather4` / `.im2col::w` / `.im2col::w::128` load modes — additional
  `load_mode` values that may map to more modifier bits.

