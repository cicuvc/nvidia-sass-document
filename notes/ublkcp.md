# UBLKCP — Uniform bulk copy (non-tensor `cp.async.bulk`)

**Opcode mnemonic:** `UBLKCP` = `0b1001110111010` = **0x13ba** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

## Semantics
UBLKCP is the **non-tensor** bulk-copy engine op — the SASS lowering of PTX
`cp.async.bulk` (contiguous byte copy), as opposed to `UTMALDG`/`UTMASTG` which
handle the *tensor* (`cp.async.bulk.tensor`) tiled copies. One elected thread on
the uniform datapath fires an asynchronous bulk transfer between global and
shared memory; completion is signalled either through an **mbarrier tx-count**
(load direction, `.S.G`) or the **bulk-async-group** counted scoreboard (store
direction, `.G.S`, via `UTMACMDFLUSH` + `DEPBAR.LE`), exactly like the tensor
TMA path (`notes/tma_mbarrier.md`).

Operands: `UBLKCP.<dst>.<src>[.mods] [URb], [URa], URc [, desc[URe]]`
- `URb` — **destination** address (64-bit uniform pair; shared or global per `dst`)
- `URa` — **source** address (`Sa` field; when `src==G` it is a 64-bit global pair, else 32-bit shared)
- `URc` — the **mbarrier** address / auxiliary (`Ra_URc`, 32-bit); the tx-count barrier for loads
- `desc[URe]` — optional **memory descriptor** pointer (the `_desc_` variant, `memdesc=1`)

## Variant overview
| variant | opcode | memdesc | extra operand | INST notes |
|---|---|---|---|---|
| `ublkcp_` | 0x13ba | 0 | — | plain bulk copy |
| `ublkcp_desc_` | 0x13ba | 1 | `desc[URe]` | memory-descriptor form (`ISRC_E_SIZE=64`) |

Both share the opcode; `memdesc` bit [76] discriminates (0 vs 1).

## Direction modifiers (`/DST:dst /DST:src`, enum `DST`: 0=G, 1=S)
Printed as `.<dst>.<src>` (dst first). Direction is constrained: you may not have
both sides shared (S/S). Verified forms:
| mnemonic | dst [73] | src [74] | meaning | PTX |
|---|---|---|---|---|
| `UBLKCP.S.G` | S | G | global → shared (**load**) | `cp.async.bulk.shared::cluster.global` |
| `UBLKCP.G.S` | G | S | shared → global (**store**) | `cp.async.bulk.global.shared::cta.bulk_group` |
| `UBLKCP.S.G.MULTICAST` | S | G | multicast load to cluster | `…global…multicast::cluster` |

CONDITIONS enforce: `src==G → dst==S`; `dst==G → src==S`; `MULTICAST → src==G`;
`src==S → sp2==nosp2`; desc variant additionally forbids S/S both ways.
`ISRC_A_SIZE = 32 + (src==G)*32` — the source is 64-bit only when reading global.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `dst` | sz | [73] | DST | G=0, S=1 |
| `src` | sh | [74] | DST | G=0, S=1 |
| `multicast` | sz | [75] | MULTICAST | nomulticast=0, MULTICAST=1 (cluster CTA-mask in `URc`) |
| `sp2` | iswzC | [82:81] | SP2 | nosp2=0, LTC64B=1, LTC128B=2, LTC256B=3 (L2 cache-hint sector size) |
| `seq` | clear | [83] | SEQ_ublkcp | noseq=0, SEQUENCED=1 (ordered; requires a non-WEAK `mem`) |
| `sem`/`sco` | mem | [80:77] | via `TABLES_mem_5(sem,sco,0)` | WEAK(default)/STRONG.{CTA,SM,VC,GPU,SYS} |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 `desc[URe]` |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling/usched control |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

`mem` field (`TABLES_mem_5(sem,sco,0)`): WEAK→0; STRONG.CTA/SM→5; STRONG.VC/GPU→7;
STRONG.SYS→10 (sem=2 rows). sem=3 rows (8,12) are further scopes. `sco` alone with
sem=WEAK is an *illegal encoding* (see `TABLES_mem_5_illegal_encodings`).

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard set for the source |
| [112:110] | dst_wr_sb | `*7` (no write scoreboard) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x13ba |
| [83] | clear | seq |
| [82:81] | iswzC | sp2 |
| [80:77] | mem | sem/sco (via `TABLES_mem_5`) |
| [76] | memdesc | 0 plain / 1 desc |
| [75] | sz | multicast |
| [74] | sh | src (G/S) |
| [73] | sz | dst (G/S) |
| [69:64] | Ra_URc | URc (mbarrier / CTA-mask) |
| [45:40] | hdrtblbase6 | URe (descriptor, desc variant only) |
| [37:32] | Ra_URb | URb (destination addr) |
| [29:24] | Sa | URa (source addr) |
| [15] | Pg_not | `@!` predicate negate |
| [14:12] | Pg | UPg (uniform predicate) |

## Cross-comparison
| op | PTX | direction | shape |
|---|---|---|---|
| **UBLKCP** | `cp.async.bulk` | g↔s (byte-contiguous) | non-tensor |
| `UTMALDG` | `cp.async.bulk.tensor` | g→s | tensor tile (`.2D`…) |
| `UTMASTG` | `cp.async.bulk.tensor`(store) | s→g | tensor tile |
| `UTMAREDG` | `cp.reduce.async.bulk.tensor` | s→g reduce | tensor tile |
| `UBLKRED` | `cp.reduce.async.bulk` | s→g reduce | non-tensor (sibling, idx nearby) |
| `UBLKPF` | `cp.async.bulk.prefetch` | g→L2 | non-tensor prefetch |

All share `udp_pipe`, `OP_TMA` latency grouping, and single-thread `ELECT` issue.

## Latency (from `sm_90_latencies.txt`)
`UBLKCP` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. It is a decoupled
**read-scoreboard** op (`INST_TYPE_DECOUPLED_RD_SCBD`, `IDEST_SIZE=0` — writes no
GPR/UGPR result). Register-range connectors use `OP_TMA` mappings
(`URa @URaRange, URb @URbRange, URc @URcRange, URe @UReRange`, line 182). Its
`rd_sb` protects the source/descriptor uniform registers from a later writer (WAR)
until the copy engine has consumed them; completion is tracked out-of-band
(mbarrier tx-count or bulk-group count), not by a write scoreboard (`dst_wr_sb=*7`).

## Verified encodings (`tests/ublkcp_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | ctrl |
|---|---|---|---|
| `0x000000060a0073ba` | `0x0011d80008000a08` | `UBLKCP.S.G.MULTICAST [UR6], [UR10], UR8` | rd_sb=0 wr_sb=7 req=0x1 |
| `0x00000006040073ba` | `0x0003e20008000405` | `UBLKCP.G.S [UR6], [UR4], UR5` | rd_sb=1 wr_sb=7 req=0x0 |
| `0x00000004080073ba` | `0x0023d80008000206` | `UBLKCP.S.G [UR4], [UR8], UR6` | rd_sb=1 wr_sb=7 (arrive-SB1) |

Decoder `tools/decode_ublkcp.py`: **3/3 PASS**.

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.async.bulk.shared::cluster.global.mbarrier::complete_tx::bytes [s],[g],n,[bar]` | `UBLKCP.S.G [URb],[URa],URc` (URc = mbarrier) |
| `…global…multicast::cluster … , mask` | `UBLKCP.S.G.MULTICAST` (URc = CTA mask) |
| `cp.async.bulk.global.shared::cta.bulk_group [g],[s],n` | `UBLKCP.G.S` + `UTMACMDFLUSH` + `DEPBAR.LE SB0,0` |
| `cp.async.bulk.commit_group` | `UTMACMDFLUSH` |
| `cp.async.bulk.wait_group.read 0` | `DEPBAR.LE SB0, 0x0` |

The load path is preceded by `SYNCS.EXCH.64` (mbarrier.init) +
`SYNCS.ARRIVE.TRANS64` (arrive.expect_tx) and issued under `@P0 ELECT P1` (single
elected thread), identical framing to `UTMALDG` (`notes/tma_mbarrier.md`).

## `multimem.cp.async.bulk` → the *same* `UBLKCP.G.S`
PTX **`multimem.cp.async.bulk`** (async bulk copy shared→**multimem** global, i.e.
broadcast a shared buffer to every GPU's copy of a multicast address range) lowers
to a **plain `UBLKCP.G.S` + `UTMACMDFLUSH`** — with a **bit-identical encoding** to
an ordinary `cp.async.bulk` shared→global store:
```
multimem.cp.async.bulk.global.shared::cta.bulk_group [d],[s],n
  →  UBLKCP.G.S [URb], [URa], URc   (0x...73ba / 0x0003e20008000406)
     UTMACMDFLUSH                   (commit_group)
```
Decoded fields (dst=G, src=S, sem=WEAK, **no** MULTICAST, rd_sb=1, wr_sb=7) are
indistinguishable from a normal bulk store — only the register operands differ.

**Key insight:** there is **no dedicated multimem opcode or discriminator bit**.
The multicast-to-all-GPUs semantics live entirely in the **destination pointer** —
a fabric/multimem-mapped virtual address set up host-side via the multicast-object
APIs. The memory system resolves the multimem address into per-device writes; the
SASS instruction is unaware. (Same philosophy as DSMEM `mapa` addressing and TMA
descriptors: the encoding stays generic, the addressing layer carries the special
semantics.)

Caveat: CUDA 13.1 `ptxas` uses an **older grammar** for this instruction — it
rejects the PTX-9.3 `.weak` / `.relaxed.scope` / `.cp_mask.b128` qualifiers; only
the bare `.global.shared::cta.bulk_group` form assembles, so the `cp_mask`/
`byteMask` partial-copy variants could not be probed.

## Open questions
- Exact meaning of `req_bit_set` (=0x1 seen on the multicast case, 0x2 on the plain
  load) — appears to be the scoreboard-wait mask, not fully decoded.
- `sp2` (LTC64B/128B/256B) L2 sector cache-hint: which PTX `.L2::cache_hint` /
  policy operand emits it (not triggered by the basic kernels here).
- `SEQUENCED` (`.SEQ`) ordering form and its interaction with the `STRONG.<sco>`
  memory scope (spec requires a non-WEAK `mem` when `seq==SEQUENCED`).
