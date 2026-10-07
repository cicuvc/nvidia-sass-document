# REDAS — Reduce-async to distributed shared memory (`red.async`)

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** low  
**Last verified:** unknown  
**Probe:** not recorded in this note  
**Open items:** 4 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: lives under notes/sm90/; no part named, so the default measurement site sm120 is assumed

## Conclusion

**Opcode mnemonic:** `REDAS` = `0b1110110111110` = **0x1dbe** | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_AGU` (15) | compute-only (`SHADER_TYPE==CS`)

## Semantics
REDAS is the SASS lowering of PTX **`red.async.shared::cluster`** — an atomic
reduction into **another CTA's shared memory** across a thread-block cluster
(distributed shared memory, DSMEM), which also signals a target **mbarrier** via
the transaction-count (`mbarrier::complete_tx::bytes`) mechanism. It is the
reduction sibling of `STAS` (`st.async`): same 64-bit `[Ra.64]` address+mbarrier
pair, same `mio_pipe`/`VQ_AGU`, plus a `REDAS_OP` reduction selector.

Operands: `REDAS.<op>[.<sz>] [Ra(.64)+URc+off], Rb`
- `Ra` — DSMEM destination; 64-bit `[Ra.64]` packs {remote-shared address, mbarrier}
- `Rb` — the value to reduce (1 or 2 registers by `sz`)
- `+URc` (uniform base) / `+offset` (24-bit signed) optional address adders

## Variant overview
| variant | opcode | address form | 64-bit reg |
|---|---|---|---|
| `redas_64__Ra64` | 0x1dbe | `[Ra.64+URc+off]` (`NonZeroRegister`) | e[72]=1 |
| `redas_64__RaRZ` [ALT] | 0x1dbe | `[RZ+URc+off]` (URc-only) | (RZ form) |
| `redas__Ra32` | 0x1dbe | `[Ra+URc+off]` (32-bit reg) | e[72]=0 |

Same opcode; CLASS chosen by address-register width. ptxas emits the 64-bit form
`[Ra.64]` (address+mbarrier pair), exactly like STAS.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `op` | op | [90:87] | REDAS_OP | ADD=0,MIN=1,MAX=2,INC=3,DEC=4,AND=5,OR=6,XOR=7 (8–15 INVALID) |
| `sz` | sz | [75:73] | REDAS_SZ | U32=0(default,unprinted),S32=1,U64=2 (3–7 INVALID); SASS prints U64 as `.64`, S32 as `.S32` |
| `sem` | (mem) | [80:77] | WEAKONLY | WEAK (only value) |
| `sco` | (mem) | [80:77] | SCO_redas | nosco_redas=0, SYS=5 |
| `private` | (mem) | [80:77] | PRIVATE | noprivate=0, PRIVATE=1 |
| `e` (input_reg_sz) | e | [72] | ONLY64/U32ONLY | 1=64-bit Ra ([Ra.64]) |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

**op×type legality** (CONDITIONS, mirrors the PTX matrix):
- `.INC`/`.DEC` require `.U32`/`.32`.
- `.MIN`/`.MAX`/`.AND`/`.OR`/`.XOR` forbid U64/64 (only U32/32/S32 allowed).
- `.ADD` is the only op valid with `.U64`/`.64`.

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` |
| [112:110] | dst_wr_sb | `*7` |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x1dbe |
| [90:87] | op | REDAS_OP |
| [80:77] | mem | sem/sco/private (via `TABLES_mem_4`) |
| [75:73] | sz | REDAS_SZ |
| [72] | e | 1=Ra is 64-bit ([Ra.64]) |
| [69:64] | Ra_URc | uniform base register |
| [63:40] | Ra_offset | 24-bit signed offset |
| [39:32] | Rb | data register |
| [31:24] | Ra | address register |
| [15] / [14:12] | Pg_not / Pg | predicate |

**vs STAS:** REDAS reuses STAS's exact layout but the `op` field grows to 4 bits
[90:87] (STAS has no op; its bit [90] is the address-width discriminator). REDAS
carries the 64-bit-reg flag in a separate bit **[72] `e`** instead (STAS uses [90]).

## Cross-comparison
| op | PTX | dest | pipe | reduces? |
|---|---|---|---|---|
| `STS` | `st.shared` | local CTA shared | mio | no |
| `ATOMS`/`RED` | `atom.shared`/`red.shared` | local CTA shared | mio | yes (sync) |
| `STAS` | `st.async.shared::cluster` | remote CTA shared (DSMEM) | mio | no |
| **REDAS** | `red.async.shared::cluster` | **remote CTA shared (DSMEM)** | **mio** | **yes (async)** |
| `UBLKRED.S.S` | `cp.reduce.async.bulk` (cluster) | remote CTA shared | udp | yes (bulk) |

STAS/REDAS = element-granularity DSMEM async ops (paired 0x1dbd/0x1dbe). REDAS is
the async, cross-CTA counterpart of `RED`/`ATOMS`.

## Latency (from `sm_90_latencies.txt`)
`REDAS` ∈ `mio_pipe` (`sm_90_latencies.txt:3`), `VIRTUAL_QUEUE=VQ_AGU`. Decoupled
read-scoreboard op, `IDEST_SIZE=0` (no register result — reduction lands remotely,
signals the mbarrier). `ISRC_A_SIZE=64` (address pair), `ISRC_B_SIZE = 32 +
(U64/64)*32`. Observed `dst_wr_sb=*7`, `rd_sb=7` — completion is mbarrier-based.

## Evidence

## Verified encodings (`tests/redas_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|---|---|---|
| `0x0000000002007dbe` | `0x001fe2000800013f` | `REDAS.ADD [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000880013f` | `REDAS.MIN [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000900013f` | `REDAS.MAX [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000880033f` | `REDAS.MIN.S32 [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000900033f` | `REDAS.MAX.S32 [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000980013f` | `REDAS.INC [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000a00013f` | `REDAS.DEC [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000a80013f` | `REDAS.AND [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000b00013f` | `REDAS.OR [R2.64], R0` |
| `0x0000000002007dbe` | `0x001fe2000b80013f` | `REDAS.XOR [R2.64], R0` |
| `0x0000000204007dbe` | `0x001fe2000800053f` | `REDAS.ADD.64 [R4.64], R2` |

Decoder `tools/decode_redas.py`: **11/11 PASS**. `op` is Hi64 [90:87] (+1 step =
`+0x00800000`: ADD `...0800`, MIN `...0880`, MAX `...0900`, … XOR `...0b80`);
`sz` [75:73] is the low nibble (`...01`=U32, `...03`=S32, `...05`=U64 with e=1).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `red.async.relaxed.cluster.shared::cluster.mbarrier::complete_tx::bytes.<op>.u32 [a],b,[mbar]` | `REDAS.<OP> [Ra.64], Rb` |
| `…min.s32` / `…max.s32` | `REDAS.MIN.S32` / `REDAS.MAX.S32` |
| `…add.u64` | `REDAS.ADD.64` |
| `…inc.u32` / `…dec.u32` | `REDAS.INC` / `REDAS.DEC` |

PTX op→REDAS_OP is direct (add/min/max/inc/dec/and/or/xor → 0–7). The
destination `[a]` and `[mbar]` handle are packed into the single 64-bit `Ra` pair.

## History / retracted hypotheses

> Claims below were **superseded, refuted, or never settled** by later work; they are kept
> for provenance. Do not cite them as current.

## Open questions
- Exact split of `[Ra.64]` into {remote-shared address, mbarrier handle} — inferred
  from adjacent const loads (as in STAS), not bit-confirmed.
- `SCO_redas@SYS` scope and `PRIVATE` modifier — which PTX qualifiers emit them.
- `.f32`/`.f16` floating reductions in the PTX `red.async` — whether they map to
  REDAS (REDAS_SZ only exposes U32/S32/U64, no float types), or a different op.
- `req_bit_set` semantics (shared open item).

