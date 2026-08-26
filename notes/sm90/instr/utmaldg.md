# UTMALDG — Uniform TMA tensor load (global → shared)

**Opcode mnemonics:** `UTMALDG` = `0b1010110110100` = **0x15b4** (plain `.tile`, no `URc`) / `0b1001110110100` = **0x13b4** (with `URc`: im2col and/or multicast) | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). A real sm_90 rerun is currently blocked because the accompanying test source
> uses sm_120 FORMAT shapes the sm_90 spec rejects at match time.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

## Semantics
UTMALDG is the SASS lowering of PTX **`cp.async.bulk.tensor…`** in the *load*
direction (global → shared::cluster). One elected thread on the uniform datapath
launches an asynchronous multi-dimensional (1D–5D) **tensor tile** copy driven by
a 128-byte tensor-map descriptor; the copy engine decrements an mbarrier's
transaction (byte) count as data lands (`complete_tx::bytes`). Contrast with
`UBLKCP` (non-tensor byte-contiguous `cp.async.bulk`) — same engine/pipe, but
UTMALDG carries a tensor `dim` and (optionally) im2col.

Operands: `UTMALDG.<dim>[.mods] [URb], [URa] [, URc] [, desc[URe]]`
- `URb` — **destination** shared address + the **mbarrier** address + the tile
  **coordinate** block (`Ra_URb`; multi-reg, sized by `dim`).  For 2D the block
  is **{URb+0 = dst smem, URb+1 = MBARRIER address, URb+2 = coord[1] (dim1),
  URb+3 = coord[0] (dim0)}** — the load-direction mbarrier is passed *inside*
  the coordinate block (verified hand-built on sm_120; leaving the mbar slot
  0 makes the TMA completion target barrier@0 and the phase never completes).
  The coordinate order in SASS is reversed vs the PTX `{c0, c1}` operand.
- `URa` — **source** = 64-bit pointer to the tensor-map descriptor (`Sa`, 2-reg aligned)
- `URc` — the **mbarrier** address (tx-count) / cluster **CTA-mask** for multicast (`Ra_URc`; only in the 0x13b4 form)
- `desc[URe]` — optional memory descriptor (the `_desc` variant, `memdesc=1`)

## Variant overview
| variant | opcode | URc | memdesc | when emitted |
|---|---|---|---|---|
| `utmaldg__UUU` | 0x15b4 | — | 0 | plain `.tile` load (mbarrier implied by coord block) |
| `utmaldg__UUU_desc` | 0x15b4 | — | 1 | plain load, mem-descriptor form |
| `utmaldg_URc__UUU` | 0x13b4 | yes | 0 | `.IM2COL` and/or `.MULTICAST` |
| `utmaldg_URc__UUU_desc` | 0x13b4 | yes | 1 | im2col/multicast, mem-descriptor form |

**Key observation:** the compiler picks the opcode by whether a printed `URc`
operand is needed. Plain `.tile` loads (1D–5D) use **0x15b4** and print only two
operands; **im2col or multicast** force the **0x13b4** three-operand form. CONDITIONS
confirm: `im2col==noim2col → multicast==MULTICAST` and `multicast==nomulticast →
im2col==IM2COL`, i.e. *the URc form requires at least one of im2col/multicast*.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `dim` | rndMode | [81:79] | TENSORDIM | 1D=0,2D=1,3D=2,4D=3,5D=4 (5–7 = INVALID) |
| `im2col` | fc | [82] | IM2COL | noim2col=0, IM2COL=1 (0x13b4 only) |
| `multicast` | sz | [75] | MULTICAST | nomulticast=0, MULTICAST=1 (0x13b4 only) |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 `desc[URe]` |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

Constraints (CONDITIONS): `.IM2COL` only valid with 3D/4D/5D; `dim` must not be
INVALID5/6/7; `URb` (coordinate block) alignment/range grows with `dim`
(1D needs ≤MAX−3 & %4==0 … 5D needs ≤MAX−7 & %8==0) reflecting the widening
`ISRC_B_SIZE = 96 + {2D:+32,3D:+64,4D:+96,5D:+128}` coordinate payload.

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard for source |
| [112:110] | dst_wr_sb | `*7` (no write scoreboard) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x15b4 / 0x13b4 |
| [82] | fc | im2col (0x13b4 only) |
| [81:79] | rndMode | dim (TENSORDIM) |
| [76] | memdesc | 0 plain / 1 desc |
| [75] | sz | multicast (0x13b4 only) |
| [69:64] | Ra_URc | URc (mbarrier / CTA-mask; 0x13b4 only) |
| [45:40] | hdrtblbase6 | URe (descriptor; desc variant only) |
| [37:32] | Ra_URb | URb (dest smem + coord block) |
| [29:24] | Sa | URa (tensor-map descriptor ptr, 64-bit) |
| [15] | Pg_not | `@!` predicate negate |
| [14:12] | Pg | UPg |

## Cross-comparison
| op | PTX | dir | shape | opcode |
|---|---|---|---|---|
| **UTMALDG** | `cp.async.bulk.tensor` | g→s | tensor 1D–5D (+im2col) | 0x15b4 / 0x13b4 |
| `UTMASTG` | `cp.async.bulk.tensor`(store) | s→g | tensor | 0x73b5 |
| `UTMAREDG` | `cp.reduce.async.bulk.tensor` | s→g reduce | tensor | — |
| `UBLKCP` | `cp.async.bulk` | g↔s | non-tensor bytes | 0x13ba |

All share `udp_pipe`, `OP_TMA` latency grouping, `VQ_TMA_UNORDERED_WR`, and
single-thread `ELECT` issue. Note UTMALDG's `dim` reuses the `rndMode` field slot;
`im2col` reuses `fc`; `multicast` reuses the `sz` bit — the same physical bits
that carry unrelated meanings in arithmetic ops.

## Latency (from `sm_90_latencies.txt`)
`UTMALDG` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. Decoupled
read-scoreboard op, `IDEST_SIZE=0` (writes no register result). Its `rd_sb`
protects the descriptor/coordinate uniform registers from a later writer (WAR)
until the engine consumes them; **completion is signalled out-of-band via the
mbarrier tx-count**, never a write scoreboard (`dst_wr_sb=*7`). Register-range
connectors use `OP_TMA` mappings (line 182). See `../arch/tma_mbarrier.md` for the
producer→consumer flow (`SYNCS.ARRIVE.TRANS64` expect_tx → UTMALDG →
`SYNCS.PHASECHK.TRYWAIT` spin + `CCTL.IVALL`).

## Verified encodings (`tests/utmaldg_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|---|---|---|
| `0x00000008040075b4` | `0x0011d80008000000` | `UTMALDG.1D [UR8], [UR4]` |
| `0x00000008040075b4` | `0x0011d80008008000` | `UTMALDG.2D [UR8], [UR4]` |
| `0x00000008040075b4` | `0x0011d80008010000` | `UTMALDG.3D [UR8], [UR4]` |
| `0x00000008040075b4` | `0x0011d80008018000` | `UTMALDG.4D [UR8], [UR4]` |
| `0x00000008040075b4` | `0x0011d80008020000` | `UTMALDG.5D [UR8], [UR4]` |
| `0x00000008060073b4` | `0x0011d80008050004` | `UTMALDG.3D.IM2COL [UR8], [UR6], UR4` |
| `0x00000008060073b4` | `0x0011d80008008804` | `UTMALDG.2D.MULTICAST [UR8], [UR6], UR4` |

Decoder `tools/decode_utmaldg.py`: **7/7 PASS**. The `dim` field is directly
visible: plain forms differ only in Hi64 bits [81:79] (0→1D … 4→5D, i.e.
`0x0000`→`0x8000`→`0x10000`→`0x18000`→`0x20000` in the shown Hi64).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.async.bulk.tensor.{1..5}d.shared::cluster.global.tile.mbarrier::complete_tx::bytes [s],[tm,{coords}],[bar]` | `UTMALDG.<n>D [URb],[URa]` (0x15b4) |
| `…tensor.3d.im2col…, {offs}` | `UTMALDG.3D.IM2COL [URb],[URa],URc` (0x13b4) |
| `…tile…multicast::cluster …, mask` | `UTMALDG.2D.MULTICAST [URb],[URa],URc` (0x13b4, URc=mask) |

Framing: preceded by `mbarrier.init`/`arrive.expect_tx` (`SYNCS.EXCH.64` /
`SYNCS.ARRIVE.TRANS64`) and issued under `@P0 ELECT P1` (single elected thread).

## Open questions
- 3D–5D coordinate-block packing (mbar slot position for higher ranks, im2col
  offset slots) — only the 2D layout was empirically verified.

- Whether the `_desc` (memdesc=1) form is ever emitted from stock PTX, and what
  `desc[URe]` carries (cache/L2 policy descriptor).

## Hand-built SASS reproduction (verified on sm_120)

`tests/asm_construct/test_utmaldg.py` reproduces `UTMALDG.2D` end-to-end with
hand-written SASS (global-memory tensor-map descriptor, simple
`ELECT P0` + 8 NOPs + `@!P0 BRA` producer guard, mbarrier tx completion):

- producer: `mbarrier.init` (`SYNCS.EXCH.64`) → `FENCE`/`MEMBAR`/`FENCE` →
  `SYNCS.ARRIVE.TRANS64` (A1TR expect_tx = tile bytes) → single
  `UTMALDG.2D [UR8], [UR16]` issue.
- **`?WAIT12_END_GROUP` usched on the UTMALDG is required** — changing it to
  `?WAIT5` faults with CUDA 719 (illegal instruction), even though the
  instruction encoding is otherwise identical.
- The ptxas `@P0 ELECT P1` / `@P1 PLOP3` / `@P0 BRA.U.ANY` retry handshake is
  **not** required (single issue works; verified by NOP-patching it out of the
  ptxas cubin too).
- consumer: tight `PHASECHK.TRANS64.TRYWAIT P0; @!P0 BRA poll` loop (the
  loop-back must be the PHASECHK's own predicate — same rule as UBLKCP).
- coords `{0,0}` and `{0,8}` verified: UR10 (URb+2) = dim1 offset,
  UR11 (URb+3) = dim0 offset.
