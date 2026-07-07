# UBLKRED — Uniform block reduction (non-tensor `cp.reduce.async.bulk`)

**Opcode mnemonic:** `UBLKRED` = `0b1001110111011` = **0x13bb** | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

## Semantics
UBLKRED is the SASS lowering of PTX **`cp.reduce.async.bulk`** — the *non-tensor*
bulk reduction of a contiguous byte range from shared memory into a destination,
applying an atomic reduction op element-wise. It is to `UBLKCP` what `UTMAREDG` is
to `UTMASTG`: same async bulk engine + a `RedOp` and element `type`. Two
destination modes:
- **`.G.S`** (global ← shared::cta): bulk-async-group completion (`UTMACMDFLUSH` +
  `DEPBAR.LE`), the common case.
- **`.S.S`** (shared::cluster ← shared::cta): mbarrier tx-count completion (remote
  CTA in the cluster), `URc` = mbarrier.

Operands: `UBLKRED.<dst>.S.<op>[.<type>] [URb], [URa], URc [, desc[URe]]`
- `URb` — **destination** address (global or remote shared)
- `URa` — **source** shared address (`Sa`, 32-bit `ISRC_A_SIZE=32`)
- `URc` — **size** in bytes (G.S) / **mbarrier** address (S.S)
- `desc[URe]` — optional cache-policy descriptor (`_desc` variant, `memdesc=1`)

## Variant overview
| variant | opcode | memdesc |
|---|---|---|
| `ublkred_` | 0x13bb | 0 |
| `ublkred_desc_` | 0x13bb | 1 |

Single opcode; `memdesc` [76] discriminates. `.L2::cache_hint` → desc form.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `dst` | sz (bit) | [73] | DST | G=0, S=1 |
| `src` | sh | [74] | SONLY_ublkred | S=1 (only value; source always shared) |
| `op` | Pnz | [89:87] | RedOp | ADD=0,MIN=1,MAX=2,INC=3,DEC=4,AND=5,OR=6,XOR=7 |
| `sz` (type) | sz | [84:81] | SIZE_ublkred | U32=0(default,unprinted),S32=1,U64=2,S64=3,F16.RN=4,F32.RN=5,F32.FTZ.RN=6,F64.RN=7,BF16.RN=8 (9–15 INVALID) |
| `sem`/`sco` | mem | [80:77] | `TABLES_mem_5(sem,sco,0)` | WEAK / STRONG.{scope} |
| `memdesc` | memdesc | [76] | — | 0 / 1 `desc[URe]` |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

**op×type legality** (CONDITIONS): `.dst==S` limits type to U32/S32/U64; `S`+`U64`
→ op must be ADD; `S32`/`U64` forbid INC/DEC; `S64` → only MIN/MAX; `F16.RN`/
`BF16.RN` → only ADD/MIN/MAX; `F32.RN`/`F32.FTZ.RN`/`F64.RN` → only ADD. These
mirror the PTX redOp×type matrix (e.g. no bitwise on floats, no INC/DEC except on
unsigned integer).

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard for source |
| [112:110] | dst_wr_sb | `*7` |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x13bb |
| [89:87] | Pnz | op (RedOp) |
| [84:81] | sz | type (SIZE_ublkred) |
| [80:77] | mem | sem/sco (via `TABLES_mem_5`) |
| [76] | memdesc | 0 / 1 |
| [74] | sh | src (S) |
| [73] | sz | dst (G/S) |
| [69:64] | Ra_URc | URc (size / mbarrier) |
| [45:40] | hdrtblbase6 | URe (desc variant only) |
| [37:32] | Ra_URb | URb (destination) |
| [29:24] | Sa | URa (shared source, 32-bit) |
| [15] / [14:12] | Pg_not / Pg | predicate |

Note the confusingly-named `sz` appears **twice** in ENCODING: [84:81] is the
element **type** (SIZE_ublkred slot), [73] is the **dst** direction bit (both use
the generic `sz` field label in the spec).

## Cross-comparison (bulk / TMA family)
| op | PTX | dir | opcode | RedOp | type field |
|---|---|---|---|---|---|
| `UBLKCP` | `cp.async.bulk` | g↔s | 0x13ba | no | no |
| **UBLKRED** | `cp.reduce.async.bulk` | s→g / s→s reduce | **0x13bb** | **[89:87]** | **[84:81]** |
| `UBLKPF` | `cp.async.bulk.prefetch` | g→L2 | 0x13bc | no | no |
| `UTMAREDG` | `cp.reduce.async.bulk.tensor` | s→g reduce | 0x13b6 | [89:87] | (in descriptor) |

UBLKRED is the **non-tensor** analogue of UTMAREDG. Unlike UTMAREDG (type lives in
the tensor-map), UBLKRED carries the element **type explicitly** in [84:81] because
there is no descriptor. Opcode family low nibble: a=blkcp, **b=blkred**, c=blkpf.
All `udp_pipe` / `OP_TMA` / `VQ_TMA_UNORDERED_WR`.

## Latency (from `sm_90_latencies.txt`)
`UBLKRED` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. Decoupled
read-scoreboard op, `IDEST_SIZE=0`. **rd_sb=1** on the `.G.S` (global) form —
protects the shared source (WAR) until the engine reads it, drained by
`wait_group.read` (`DEPBAR.LE`); **rd_sb=0** on the `.S.S` (mbarrier/cluster) form,
which uses the tx-count barrier + single-thread `ELECT` framing like a load.
`dst_wr_sb=*7`.

## Verified encodings (`tests/ublkred_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|---|---|---|
| `0x00000008040073bb` | `0x0023d80008000406` | `UBLKRED.G.S.ADD [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80008800406` | `UBLKRED.G.S.MIN [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80009000406` | `UBLKRED.G.S.MAX [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80009800406` | `UBLKRED.G.S.INC [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d8000a000406` | `UBLKRED.G.S.DEC [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d8000a800406` | `UBLKRED.G.S.AND [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d8000b000406` | `UBLKRED.G.S.OR [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d8000b800406` | `UBLKRED.G.S.XOR [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80008020406` | `UBLKRED.G.S.ADD.S32 [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80008040406` | `UBLKRED.G.S.ADD.U64 [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80008860406` | `UBLKRED.G.S.MIN.S64 [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d800080a0406` | `UBLKRED.G.S.ADD.F32.RN [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d800080e0406` | `UBLKRED.G.S.ADD.F64.RN [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80008080406` | `UBLKRED.G.S.ADD.F16.RN [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80008100406` | `UBLKRED.G.S.ADD.BF16.RN [UR8], [UR4], UR6` |
| `0x00000008040073bb` | `0x0023d80008880406` | `UBLKRED.G.S.MIN.F16.RN [UR8], [UR4], UR6` |
| `0x0000000a040073bb` | `0x0011d80008000608` | `UBLKRED.S.S.ADD [UR10], [UR4], UR8` (mbarrier form) |

Decoder `tools/decode_ublkred.py`: **17/17 PASS**. `op` is Hi64 [89:87] (+1 step =
`+0x00800000`); `type` is [84:81] (U32=0 unprinted, S32 `...02...`, U64 `...04...`,
F32.RN `...0a...`, F64.RN `...0e...`, F16.RN `...08...`, BF16.RN `...10...`); when
both op and type set, they add (e.g. MIN.S64 = `...86...`, MIN.F16.RN = `...88...`).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.reduce.async.bulk.global.shared::cta.bulk_group.<op>.<type> [g],[s],n` | `UBLKRED.G.S.<OP>[.<TYPE>] [URb],[URa],URc` |
| `cp.reduce.async.bulk.shared::cluster.shared::cta.mbarrier::complete_tx::bytes.<op>.<type> [d],[s],n,[bar]` | `UBLKRED.S.S.<OP> [URb],[URa],URc` |
| `cp.async.bulk.commit_group` | `UTMACMDFLUSH` |
| `cp.async.bulk.wait_group.read N` | `DEPBAR.LE SBn, N` |

PTX type → SIZE field: `.u32→U32(default), .s32→S32, .u64→U64, .s64→S64,
.f16→F16.RN, .f32→F32.RN, .f64→F64.RN, .bf16→BF16.RN`. `.b32` bitwise ops print
without a type suffix (encoded U32=0). f16/bf16 `.add` require PTX `.noftz`.

## Open questions
- `F32.FTZ.RN` (sz=6) — which PTX qualifier emits the FTZ variant (not triggered;
  the `.noftz` path gave F32.RN/F16.RN, not FTZ).
- The `.S.S` cluster-reduce completion detail (mbarrier vs remote scoreboard) —
  observed rd_sb=0 + ELECT, consistent with the load-style tx-count path.
- `req_bit_set` semantics (shared open item across the TMA/bulk family).
