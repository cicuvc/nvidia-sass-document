# UTMACMDFLUSH — TMA command-queue flush / bulk-async-group commit

**Opcode mnemonic:** `UTMACMDFLUSH` = `0b100110110111` = **0x9b7** | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

## Semantics
UTMACMDFLUSH is the SASS lowering of PTX **`cp.async.bulk.commit_group`** — it
**closes the current bulk-async group**, binding every bulk TMA op issued since the
last commit (UTMASTG / UTMAREDG / UBLKCP.G.S / UBLKRED.G.S / multimem bulk) into
one countable group on a completion scoreboard. It is the bulk/TMA analogue of
`LDGDEPBAR` (which commits `cp.async`/LDGSTS groups): the *commit point* of the
same counted-group mechanism drained by `DEPBAR.LE` (`depbar.md`).

It takes **no operands** — just an optional predicate. The instruction has no
source or destination registers (`ISRC_*`/`IDEST_SIZE` all 0); its entire effect
is on the TMA command queue / group counter.

## Variant overview
| variant | opcode | operands |
|---|---|---|
| `utmacmdflush_` | 0x9b7 | none (predicate only) |

Single variant. Note the 12-bit opcode (bit [91]=0), like the other short
control-only TMA ops (`UTMACCTL.IVALL` 0x9b9).

## Modifiers
| modifier | field | bits | notes |
|---|---|---|---|
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` scheduling |
| `pm_pred` | pm_pred | [103:102] | perfmon predicate |
| `req_bit_set` | req | [121:116] | scoreboard wait mask |

No functional modifiers — it is a bare barrier/commit op.

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard |
| [112:110] | dst_wr_sb | **`*7` (star-pinned)** — see below |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x9b7 |
| [15] / [14:12] | Pg_not / Pg | predicate |

## The commit/count mechanism — a subtlety vs LDGDEPBAR
`LDGDEPBAR` (the `cp.async` commit) encodes a **freely-settable `dst_wr_sb`**
(`VarLatOperandEnc(wr)`) so ptxas can choose *which* scoreboard SBk counts the
group (`wr_sb=k` → increment SBk). **UTMACMDFLUSH's `dst_wr_sb` is pinned to `*7`
in the ENCODING** (a fixed star, not operand-driven). Yet the bulk-store pipeline
still waits via `DEPBAR.LE SB0, 0`:
```
UTMASTG.2D [UR8], [UR6]     rd_sb=1  wr_sb=7    # TMA store; READ scoreboard on shared source
UTMACMDFLUSH               (dst_wr_sb=*7)       # commit_group -> counts the group
DEPBAR.LE SB0, 0x0                              # wait_group.read 0
```
So the group counter behind UTMACMDFLUSH is **not** selected by a per-instruction
`wr_sb` field the way cp.async does; the commit implicitly counts on the fixed TMA
group scoreboard (observed SB0). This matches `INST_TYPE_DECOUPLED_RD_SCBD` (it
declares only a *read* scoreboard role in its type, unlike LDGDEPBAR's
`DECOUPLED_RD_WR_SCBD`).

## Cross-comparison (async-group commit ops)
| op | PTX | family | commit-SB selection | pipe |
|---|---|---|---|---|
| `LDGDEPBAR` | `cp.async.commit_group` | per-thread cp.async | `wr_sb=k` (operand-driven) | mio |
| **UTMACMDFLUSH** | `cp.async.bulk.commit_group` | bulk/TMA | **fixed (`*7`, implicit SB0)** | udp |
| `WARPGROUP.DEPBAR` | wgmma group wait | GMMA | dedicated GMMA group SB | mio |

All feed the same `DEPBAR.LE SBn, N` counted-wait; only the commit instruction and
scoreboard-selection differ. UTMACMDFLUSH is used for **store-direction** TMA/bulk
completion (there is no consumer mbarrier for stores); the load direction uses the
mbarrier tx-count path instead (`../arch/tma_mbarrier.md`).

## Latency (from `sm_90_latencies.txt`)
`UTMACMDFLUSH` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. Decoupled
read-scoreboard op with all operand sizes 0 — a pure control instruction. Its
completion isn't fixed-latency; the *group* it commits is drained by a later
`DEPBAR.LE`.

## Verified encodings (multiple test cubins, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | context |
|---|---|---|---|
| `0x00000000000079b7` | `0x0001e20000000000` | `UTMACMDFLUSH` | `tests/tma_store_test.cubin` (after UTMASTG) |
| `0x00000000000079b7` | `0x0001e20000000000` | `UTMACMDFLUSH` | `tests/utmastg_test.cubin` |
| `0x00000000000079b7` | `0x0001e20000000000` | `UTMACMDFLUSH` | multimem bulk (after UBLKCP.G.S) |

Control word decode: opcode 0x9b7, `src_rel_sb=0`, `dst_wr_sb=7` (pinned),
`req_bit_set=0x0`, `Pg=UPT`. The encoding is invariant (no operands/modifiers in
these cases) — the same 16 bytes regardless of which bulk op precedes it.

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.async.bulk.commit_group` | `UTMACMDFLUSH` |
| `cp.async.bulk.wait_group[.read] N` | `DEPBAR.LE SBn, N` |

Appears after every store-direction bulk/TMA op group: `UTMASTG` (tensor store),
`UTMAREDG` (tensor reduce), `UBLKCP.G.S` (bulk store), `UBLKRED.G.S` (bulk reduce),
and `multimem.cp.async.bulk` (all lower their commit to this op).

## Open questions
- Exact width of the implicit TMA group counter behind the fixed commit scoreboard
  (shared open item with `depbar.md`).
