# ARRIVES — cp.async (LDGSTS) → mbarrier arrive

**Opcode mnemonic:** `ARRIVES` = `0b1100110110000` = **0x19b0** | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_AGU_UNORDERED_WR` | compute-only

The bridge between the **cp.async / LDGSTS** async-copy completion mechanism and an
**mbarrier**: it makes a thread's outstanding `LDGSTS` group signal a shared-memory barrier
when the copies land. It is what PTX `cp.async.mbarrier.arrive[.noinc]` lowers to — distinct
from the general `SYNCS.ARRIVE` (direct mbarrier arrive) because it hooks the LDGSTS engine
(dispatched via the AGU queue, not the SYNCS queue).

## Semantics
`@Pg ARRIVES.LDGSTSBAR.64.<barop> [addr]` records that the current thread's in-flight
`LDGSTS` (cp.async) group must complete before the mbarrier at `[addr]` advances:
- **`.TRANSCNT`** (`barop`=2) ← `cp.async.mbarrier.arrive` — contributes the async group to
  the barrier's pending **transaction** count.
- **`.ARVCNT`** (`barop`=1) ← `cp.async.mbarrier.arrive.noinc` — arrive without incrementing
  (the `.noinc` form).
- **`.LEGACY`** (`barop`=0) — legacy arrive-count form (unsampled).

The barrier address is uniform-register addressed shared memory; a CONDITION requires
`Ra == RZ`, so the address is always `[URc(+off)]`.

## Variant overview
Single CLASS `arrives_`, one opcode. `.LDGSTSBAR` (fixed, from `LDGSTSBARONLY`) and `.64`
(from `sz`, `CInteger_64`) are always present; `barop` selects the count mode.

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x19b0 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [75:73] | `sz` | `CInteger_64` → `.64` |
| [72] | `arrive` | `LDGSTSBARONLY` → `.LDGSTSBAR` |
| [71:70] | `barop` | `LEGACY`(0) / `ARVCNT`(1) / `TRANSCNT`(2) |
| [31:24] | `Ra` | must be RZ |
| [69:64] | `URc` | shared barrier address (uniform) |
| [63:40] | `Ra_offset` | address offset |

## Cross-comparison (mbarrier arrives)
| | **ARRIVES** | SYNCS.ARRIVE.TRANS64 |
|--|-------------|----------------------|
| source | cp.async (LDGSTS) group completion | direct thread arrive / expect_tx |
| PTX | `cp.async.mbarrier.arrive[.noinc]` | `mbarrier.arrive[.expect_tx]` |
| queue | `VQ_AGU_UNORDERED_WR` (AGU) | `VQ_SYNCS_UNORDERED_WR` |
| count | `.TRANSCNT`/`.ARVCNT` | paramtype A/T counts |

Both target the same mbarrier; `SYNCS.ARRIVE` is a plain arrive, `ARRIVES` couples the
async-copy engine so the barrier flips when the copies complete.

## Where it fits — the async-copy → mbarrier flow (verified)
```
SYNCS.EXCH.64 [UR7]                       # mbarrier.init
BAR.SYNC.DEFER_BLOCKING 0x0              # __syncthreads
LDGSTS.E [R5], desc[UR8][R2.64]          # cp.async global->shared
SYNCS.ARRIVE.TRANS64.RED.A0T1 RZ,[UR7]   # expect / arrive
ARRIVES.LDGSTSBAR.64.TRANSCNT [UR7]      # cp.async.mbarrier.arrive     <-- couples LDGSTS
ARRIVES.LDGSTSBAR.64.ARVCNT   [UR7]      # cp.async.mbarrier.arrive.noinc
BAR.SYNC.DEFER_BLOCKING 0x0
```
This is a third cp.async-completion route (alongside `LDGDEPBAR`+`DEPBAR.LE`, see
`notes/depbar.md`): instead of a counted scoreboard, the LDGSTS group signals an **mbarrier**
(then consumed by `SYNCS.PHASECHK` try_wait — see `notes/tma_mbarrier.md`).

## Latency
`mio_pipe`, `DECOUPLED_RD_SCBD`, `VQ_AGU_UNORDERED_WR`. Not in `RPC_WRITERS`/`CBU_OPS_WITH_REQ`.

## Verified encodings (decoder: `tools/decode_arrives.py`)
Self-test 2/2; `tests/arrives_test.cu` (cp.async + `cp.async.mbarrier.arrive`) 2/2.

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| 0x00000000ff0079b0 | 0x000fe20008000a87 | `ARRIVES.LDGSTSBAR.64.TRANSCNT [UR7]` |
| 0x00000000ff0079b0 | 0x000fe20008000a47 | `ARRIVES.LDGSTSBAR.64.ARVCNT [UR7]` |

Hand-check TRANSCNT: opcode 0x19b0; `sz`[75:73]=5→`.64`; `arrive`[72]=0→`.LDGSTSBAR`;
`barop`[71:70]=2→`.TRANSCNT`; `URc`[69:64]=7→`[UR7]`; `Ra`=RZ.

## Open questions
- `.LEGACY` `barop` form (older arrive-count barrier) is unsampled.
- Whether `.TRANSCNT` vs `.ARVCNT` differ only in the count field they touch, or also in
  ordering, is not spec-stated (inferred from the arrive/noinc PTX pairing).
