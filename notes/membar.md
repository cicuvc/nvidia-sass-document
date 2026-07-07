# MEMBAR — Memory barrier / fence

**Opcode mnemonic:** `MEMBAR` = `0b100110010010` = **0x992** | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_UNORDERED`

## Semantics
MEMBAR enforces **memory ordering** at a chosen semantic strength and scope: it
makes prior memory accesses from this thread visible (in order) to other threads
within the scope before subsequent accesses. It is the SASS lowering of PTX
`membar.*` and `fence.*`. No operands — just semantic + scope modifiers.

For **GPU-and-wider scopes**, ptxas emits MEMBAR **followed by `ERRBAR` +
`CGAERRBAR`** (error-barrier / cluster-error-barrier), completing the fence across
the error/exception domain and the thread-block cluster. CTA-scope fences emit
MEMBAR alone.

## Variant overview
| variant | opcode | purpose |
|---|---|---|
| `membar_` | 0x992 | general fence (sem × sco modifiers) |
| `membar_async_` | 0x992 | async-proxy fence (sco=VC, mmio=ASYNC pinned) |
| `membar_tma_` [ALT] | 0x992 | TMA/multicast proxy fence (sco=VC, mmio=MULTICAST) |

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `sem` | sem | [80:79] | MEMBAR_SEM | SC=0, ALL=1, nomembar_sem=2(unprinted), MMIO=3 |
| `sco` | sco | [78:76] | SCO_CTA_SM_GPU_SYS_VC_CTAPARTIAL | CTA=0,SM=1,GPU=2,SYS=3,VC=5,CTA.PARTIAL=6 (4,7 illegal) |

**`sem` — barrier strength:**
- `SC` (0) — **sequential consistency** fence (`fence.sc`, `membar.gl`/`membar.sys`)
- `ALL` (1) — **acquire-release** / all-ops fence (`fence.acq_rel`)
- `MMIO` (3) — MMIO-ordering fence

**Note:** the `sco` enum here is the **MEMBAR-specific scope numbering**
(`GPU=2, SYS=3, VC=5`) — genuinely different from the load/store `SCO` enum
(`CTA=1,SM=2,VC=3,GPU=4,SYS=5`). See `notes/memory_model.md`: the two scope fields
use different encodings. `CTA.PARTIAL` (6) is a MEMBAR-only partial-CTA scope.

## Bit layout (128-bit)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` |
| [112:110] | dst_wr_sb | `7` (pinned) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x992 |
| [80:79] | sem | MEMBAR_SEM |
| [78:76] | sco | scope |
| [73] | sz | `0` (pinned; `mmio` slot in async/tma variants) |
| [15] / [14:12] | Pg_not / Pg | predicate |

All `ISRC_*`/`IDEST_SIZE`=0 — a pure ordering op with no data operands.

## Cross-comparison
| op | role |
|---|---|
| **MEMBAR** | memory ordering fence (this note) |
| `ERRBAR` | error-barrier (co-emitted for ≥GPU scope) |
| `CGAERRBAR` | cluster-error-barrier (co-emitted for ≥GPU scope) |
| `FENCE` | view/proxy fence (`FENCE.VIEW.ASYNC.S` for `fence.proxy.async`) |
| `BAR.SYNC` | execution barrier (thread sync, `notes/bar.md`) |
| `SYNCS` | shared-memory/mbarrier sync |

MEMBAR orders *memory*; BAR synchronizes *execution*. `fence.proxy.async` emits
`MEMBAR.ALL.GPU` + a separate `FENCE.VIEW.ASYNC.S` (the async-proxy view fence).

## Latency (from `sm_90_latencies.txt`)
`MEMBAR` ∈ `mio_pipe`, `VQ_UNORDERED`. Decoupled read-scoreboard op; the fence
drains outstanding memory ops per its scope. No register result.

## Verified encodings (`tests/membar_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | PTX |
|---|---|---|---|
| `0x0000000000007992` | `0x000fec0000000000` | `MEMBAR.SC.CTA` | `membar.cta` / `fence.sc.cta` |
| `0x0000000000007992` | `0x0001ec0000008000` | `MEMBAR.ALL.CTA` | `fence.acq_rel.cta` |
| `0x0000000000007992` | `0x000fec000000a000` | `MEMBAR.ALL.GPU` | `fence.acq_rel.gpu` (+ERRBAR+CGAERRBAR) |
| `0x0000000000007992` | `0x000fec000000b000` | `MEMBAR.ALL.SYS` | `fence.acq_rel.sys` (+ERRBAR+CGAERRBAR) |
| `0x0000000000007992` | `0x000fec0000002000` | `MEMBAR.SC.GPU` | `fence.sc.gpu` / `membar.gl` (+ERRBAR+CGAERRBAR) |

Decoder `tools/decode_membar.py`: **5/5 PASS**. `sem` is Hi64 [80:79]
(bit79 = ALL vs SC: `...0000`=SC, `...8000`=ALL) and `sco` is [78:76]
(`0`=CTA, `2000`=GPU, `a000`=ALL+GPU, `b000`=ALL+SYS).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `membar.cta` / `fence.sc.cta` | `MEMBAR.SC.CTA` |
| `membar.gl` / `fence.sc.gpu` | `MEMBAR.SC.GPU` + `ERRBAR` + `CGAERRBAR` |
| `membar.sys` / `fence.sc.sys` | `MEMBAR.SC.SYS` + `ERRBAR` + `CGAERRBAR` |
| `fence.acq_rel.cta` | `MEMBAR.ALL.CTA` |
| `fence.acq_rel.gpu` | `MEMBAR.ALL.GPU` + `ERRBAR` + `CGAERRBAR` |
| `fence.acq_rel.sys` | `MEMBAR.ALL.SYS` + `ERRBAR` + `CGAERRBAR` |
| `fence.acq_rel.cluster` | `MEMBAR.ALL.GPU` + `ERRBAR` + `CGAERRBAR` |
| `fence.proxy.async` | `MEMBAR.ALL.GPU` + `FENCE.VIEW.ASYNC.S` |

**Key findings:**
- **`fence.sc` → `MEMBAR.SC`, `fence.acq_rel` → `MEMBAR.ALL`** — the PTX semantic
  qualifier picks the `sem` field (SC vs ALL). `membar.gl`/`membar.sys` (legacy)
  are SC-strength.
- **`.gpu`/`.sys`/`.cluster` scopes co-emit `ERRBAR`+`CGAERRBAR`**; only `.cta`
  is MEMBAR-alone. The error barriers extend the fence across the exception and
  cluster domains (see `notes/errbar.md`).
- **`fence.acq_rel.cluster` collapses to `MEMBAR.ALL.GPU`** — cluster scope is
  realized as GPU-scope MEMBAR plus the cluster-error-barrier `CGAERRBAR`, not a
  distinct MEMBAR scope value.

## Open questions
- `MMIO` sem and `CTA.PARTIAL`/`VC`/`SM` scopes — which PTX emits them (not
  triggered by the standard fence forms here).
- The `membar_async_`/`membar_tma_` (VC-scope, ASYNC/MULTICAST) variants — likely
  from `fence.proxy.tensormap`/TMA paths; here `fence.proxy.async` gave a separate
  `FENCE.VIEW.ASYNC.S` rather than a `membar_async_` encoding.
- `FENCE` (the `FENCE.VIEW.ASYNC.S` op, 0x3c6) — a distinct mnemonic, now
  documented in `notes/fence.md` (TODO FENCE_G/FENCE_S idx 218/219).
