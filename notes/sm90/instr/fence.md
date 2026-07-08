# FENCE — Async-proxy view fence

**Opcode mnemonic:** `FENCE` = `0b1111000110` = **0x3c6** | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_WR_SCBD` | **VIRTUAL_QUEUE:** `VQ_FENCE_S` (shared form) / `VQ_FENCE_G` (global form)

## Semantics
FENCE is the **async-proxy view fence** — it orders accesses made through the
**async proxy** (TMA / `cp.async` bulk copy engines, which write memory via a
separate hardware path) against accesses through the **generic proxy** (ordinary
LD/ST). It is the SASS lowering of PTX **`fence.proxy.async{.global|.shared::cta}`**.
Always emitted as `FENCE.VIEW.ASYNC.<space>` — the fixed `VIEW.ASYNC` names the
proxy view being synchronized; `memType` selects the memory space (shared vs
global).

This is distinct from `MEMBAR` (`membar.md`): MEMBAR orders the *generic*
memory proxy across a scope; FENCE bridges the *async↔generic proxy* boundary so
that data landed by an async copy engine becomes visible to normal loads/stores
(and vice-versa). `fence.proxy.async` (no space) emits **`MEMBAR.ALL.GPU` +
`FENCE.VIEW.ASYNC.S`** together — the MEMBAR does the scope ordering, the FENCE
does the proxy-view crossing.

## Variant overview
| variant | opcode | memType | space | VIRTUAL_QUEUE |
|---|---|---|---|---|
| `fence_` | 0x3c6 | S (0) | shared::cta | `VQ_FENCE_S` |
| `fence_g_` | 0x3c6 | G (1) | global | `VQ_FENCE_G` |

The two are otherwise identical; the space picks both the printed `.S`/`.G` suffix
and the virtual queue the fence drains.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `type` | (fixed) | — | VIEWONLY | VIEW (only value) |
| `syncType` | (fixed) | — | ASYNCONLY | ASYNC (only value) |
| `memType` | e | [72] | SONLY / GONLY | S=0 (shared) / G=1 (global) |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

`VIEW` and `ASYNC` are single-value enums (always printed, no encoding bit) — the
only real field is `memType` [72]. Maps directly to the TODO's **FENCE_S** (idx
219, shared) and **FENCE_G** (idx 218, global) — one mnemonic, two space forms.

## Bit layout (128-bit)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `7` (pinned — no read scoreboard) |
| [112:110] | dst_wr_sb | `VarLatOperandEnc(wr)` — the fence sets a WRITE scoreboard |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x3c6 |
| [72] | e | memType (S=0 / G=1) |
| [15] / [14:12] | Pg_not / Pg | predicate |

All `ISRC_*`/`IDEST_SIZE`=0 — pure ordering op. Unlike MEMBAR
(`DECOUPLED_RD_SCBD`), FENCE is **`DECOUPLED_WR_SCBD`**: it owns a write
scoreboard (`dst_wr_sb` operand-driven), so a later op can wait on the fence's
completion via that scoreboard.

## Cross-comparison
| op | opcode | orders | INST_TYPE |
|---|---|---|---|
| `MEMBAR` | 0x992 | generic proxy, across scope (SC/ALL) | DECOUPLED_RD_SCBD |
| **FENCE** | 0x3c6 | **async↔generic proxy** view | DECOUPLED_WR_SCBD |
| `ERRBAR`/`CGAERRBAR` | — | error/cluster domain (co-emit with MEMBAR ≥GPU) | — |
| `UTMACCTL.IV` | 0x19b9 | tensormap-proxy descriptor cache | DECOUPLED_RD_SCBD |

The proxy-fence family: **async proxy** ↔ generic uses `FENCE.VIEW.ASYNC`;
**tensormap proxy** ↔ generic uses `UTMACCTL` (`utmacctl.md`). Both are
"proxy-crossing" fences distinct from the scope-ordering MEMBAR.

## Latency (from `sm_90_latencies.txt`)
`FENCE` ∈ `mio_pipe`, `VQ_FENCE_S`/`VQ_FENCE_G`. Decoupled **write**-scoreboard op —
its completion is scoreboard-tracked (a consumer of the async-copied data can wait
on the fence's write SB before reading through the generic proxy).

## Verified encodings (`tests/membar_test.cu` + probe, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | PTX |
|---|---|---|---|
| `0x00000000000073c6` | `0x000fe20000000000` | `FENCE.VIEW.ASYNC.S` | `fence.proxy.async` / `fence.proxy.async.shared::cta` |
| `0x00000000000073c6` | `0x000fe20000000100` | `FENCE.VIEW.ASYNC.G` | `fence.proxy.async.global` |

Decoder `tools/decode_fence.py`: **2/2 PASS**. The only differing bit is Hi64
[72] (`...000`=S, `...100`=G).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `fence.proxy.async` | `MEMBAR.ALL.GPU` + `FENCE.VIEW.ASYNC.S` |
| `fence.proxy.async.shared::cta` | `FENCE.VIEW.ASYNC.S` |
| `fence.proxy.async.global` | `FENCE.VIEW.ASYNC.G` |

**Key findings:**
- The **space qualifier** picks `memType`: `.shared::cta`→`.S`, `.global`→`.G`;
  the bare `fence.proxy.async` defaults to `.S` (shared) but *also* prepends a
  full `MEMBAR.ALL.GPU` (generic-proxy GPU-scope ordering) — the shared-space and
  global-space explicit forms emit the FENCE alone.
- Contrast `fence.proxy.tensormap` → `UTMACCTL.IV` (`utmacctl.md`): the two
  proxy kinds (async vs tensormap) use entirely different SASS ops.

## Open questions
- Why `fence.proxy.async` (no space) additionally emits `MEMBAR.ALL.GPU` while the
  explicit `.shared::cta`/`.global` forms do not — likely the bare form implies a
  broader generic-proxy ordering.
- Whether an `.acquire`/`.release` proxy-fence direction changes the encoding
  (only the plain proxy-async form was probed).
- The write-scoreboard usage — which consumer waits on FENCE's `dst_wr_sb` in a
  real TMA/cp.async pipeline.
