# STAS — Store-async to distributed shared memory (`st.async`)

**Opcode mnemonic:** `STAS` = `0b1110110111101` = **0x1dbd** | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_AGU` (15) | compute-only (`SHADER_TYPE==CS`)

## Semantics
STAS is the SASS lowering of PTX **`st.async.shared::cluster`** — an asynchronous
store into **another CTA's shared memory** across a thread-block cluster
(distributed shared memory, DSMEM), which also signals a target **mbarrier** via
the transaction-count (`mbarrier::complete_tx::bytes`) mechanism. Unlike a plain
`STS`, the store is async (fire-and-forget on `mio_pipe`) and its completion is
tracked by the remote mbarrier, not a local scoreboard.

Operands: `STAS[.sz] [Ra(.64)+URc+off], Rb`
- `Ra` — DSMEM destination address; the **64-bit** register form (`[Ra.64]`)
  packs {mapped remote-shared address, mbarrier handle} (see below)
- `Rb` — the data to store (1/2/4 registers by `sz`)
- `+URc` (uniform base) and `+offset` (24-bit signed) are optional address adders

**Note (this session's correction):** STAS is `st.async`, **not** `st.bulk`.
`st.bulk` (bulk shared-memory zero-init) is a **Blackwell (sm_100+) only** feature
— ptxas rejects it on sm_90 (*"Feature 'st.bulk' requires .target sm_100 or
higher"*) and lowers it to `UMEMSETS.64` on sm_100, an instruction outside the
sm_90 spec.

## Variant overview
| variant | opcode | address form | `input_reg_sz`[90] |
|---|---|---|---|
| `stas_64__Ra64` | 0x1dbd | `[Ra.64+URc+off]` (64-bit reg pair, `NonZeroRegister`) | 1 (ONLY64) |
| `stas_64__RaRZ` [ALT] | 0x1dbd | `[RZ+URc+off]` (no base reg, URc-only) | (RZ form) |
| `stas__Ra32` | 0x1dbd | `[Ra+URc+off]` (32-bit reg, `U32ONLY`) | 0 |

All three share the opcode; the CLASS is chosen by the address-register width.
Empirically ptxas always emits the **64-bit** form `[Ra.64]` (the DSMEM
address+mbarrier pair).

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `sz` | sz | [75:73] | SZ_32_64_128 | 32=4(default,unprinted),64=5,128=6 (0–3,7 INVALID) |
| `sem` | (mem) | [80:77] | WEAKONLY | WEAK (only value) |
| `sco` | (mem) | [80:77] | SCO_redas | nosco_redas=0, SYS=5 |
| `private` | (mem) | [80:77] | PRIVATE | noprivate=0, PRIVATE=1 |
| `input_reg_sz` | input_reg_sz | [90] | ONLY64/U32ONLY | 1=64-bit Ra, 0=32-bit Ra |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

`sem`/`sco`/`private` fuse into the 4-bit `mem` field via
`TABLES_mem_4(sem,sco,private)`; the common `WEAK/nosco/noprivate` → **mem=0**
(observed). `.128` requires `Rb` %4-aligned; `.64` requires %2 — enforced by
CONDITIONS.

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` |
| [112:110] | dst_wr_sb | `*7` |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x1dbd |
| [90] | input_reg_sz | 1=Ra is 64-bit ([Ra.64]) |
| [80:77] | mem | sem/sco/private (via `TABLES_mem_4`) |
| [75:73] | sz | SZ_32_64_128 |
| [69:64] | Ra_URc | uniform base register |
| [63:40] | Ra_offset | 24-bit signed offset |
| [39:32] | Rb | data register |
| [31:24] | Ra | address register |
| [15] / [14:12] | Pg_not / Pg | predicate |

## Cross-comparison
| op | PTX | dest | pipe | completion |
|---|---|---|---|---|
| `STS` | `st.shared` | local CTA shared | mio | synchronous |
| **STAS** | `st.async.shared::cluster` | **remote CTA shared (DSMEM)** | **mio (async)** | **mbarrier tx-count** |
| `REDAS` | `red.async.shared::cluster` | remote CTA shared (reduce) | mio | mbarrier tx-count |
| `UBLKRED.S.S` | `cp.reduce.async.bulk` (cluster) | remote CTA shared | udp | mbarrier tx-count |

STAS/REDAS are the **element-granularity** DSMEM async ops (`mio_pipe`, `VQ_AGU`),
paired opcodes 0x1dbd/0x1dbe. The **bulk** DSMEM path is UBLKCP/UBLKRED on the
uniform datapath. `st.async` differs from `cp.async` (LDGSTS) in that the source
is a register, not global memory.

## Latency (from `sm_90_latencies.txt`)
`STAS` ∈ `mio_pipe` (`sm_90_latencies.txt:3`), `VIRTUAL_QUEUE=VQ_AGU` (address
generation unit queue). Decoupled read-scoreboard op, `IDEST_SIZE=0` (no register
result — the store lands in remote shared and signals the mbarrier).
`ISRC_A_SIZE=64` (address pair), `ISRC_B_SIZE = 32 + {64:+32,128:+96}` (data
width). Observed `dst_wr_sb=*7` (no write scoreboard) and `rd_sb=7` (no read
scoreboard) in the tested cases — completion is entirely mbarrier-based.

## Verified encodings (`tests/stas_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | PTX |
|---|---|---|---|
| `0x0000000002007dbd` | `0x001fe2000c00083f` | `STAS [R2.64], R0` | `st.async…b32` |
| `0x0000000204007dbd` | `0x001fe2000c000a3f` | `STAS.64 [R4.64], R2` | `st.async…b64` |
| `0x0000000402007dbd` | `0x001fe2000c000c3f` | `STAS.128 [R2.64], R4` | `st.async…v4.b32` |
| `0x0000000402007dbd` | `0x001fe2000c000a3f` | `STAS.64 [R2.64], R4` | `st.async…v2.b32` |
| `0x0000000002007dbd` | `0x001fe2000c00083f` | `STAS [R2.64], R0` | `st.async.weak…b32` |

Decoder `tools/decode_stas.py`: **5/5 PASS**. `sz` is Hi64 [75:73] (32→`...08`,
64→`...0a`, 128→`...0c` in the shown Hi64 low bits); the `.weak` form is
bit-identical to the default (WEAK is the only `sem` value, mem=0). `[Ra.64]`
comes from `input_reg_sz`[90]=1.

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `st.async.shared::cluster.mbarrier::complete_tx::bytes.b32 [a],b,[mbar]` | `STAS [Ra.64], Rb` |
| `…b64` | `STAS.64` |
| `…v2.b32` | `STAS.64` (2×32 = 64 bits) |
| `…v4.b32` / `.b128` | `STAS.128` |
| `st.async.weak…` | `STAS` (identical; WEAK is default) |

The destination address `[a]` and the `[mbar]` handle are packed into the single
64-bit `Ra` register pair (the two consts loaded into R2/R3 in the test); the
`mapa`-style remote-CTA mapping is done by the caller.

## Open questions
- Exact split of the `[Ra.64]` pair into {remote-shared address, mbarrier handle}
  — inferred from the two adjacent const loads, not bit-confirmed.
- The `SCO_redas@SYS` scope and `PRIVATE` modifier — which PTX qualifiers emit them
  (the global-scope `st.async.release.{gpu,sys}` form was not probed here; it may
  map to a different mnemonic/state-space).
- `REDAS` (the reduce sibling, 0x1dbe) — analogous DSMEM async reduction, now
  documented in `redas.md`.
