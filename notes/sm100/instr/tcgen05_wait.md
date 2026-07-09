# tcgen05.wait::ld / ::st — completion waits for async TMEM load/store

**PTX:** `tcgen05.wait::ld.sync.aligned` / `tcgen05.wait::st.sync.aligned`
**SASS:**
- `tcgen05.wait::ld` → *(no opcode)* — realized by the **LDTM write-scoreboard**
- `tcgen05.wait::st` → **`FENCE.VIEW.ASYNC.T`** (opcode 0x3c6)

**Status:** resolved empirically on `sm_100a` (CUDA 13.1).

## Question
What SASS do the two tcgen05 completion waits generate? (These block the thread
until prior `tcgen05.ld` / `tcgen05.st` have completed — different from the
`tcgen05.fence::*_thread_sync` code-motion fences, which emit nothing.)

## Answer: the two waits are asymmetric
`::ld` and `::st` use **different** hardware mechanisms, because the underlying
async ops release different scoreboards (see `ldtm.md` / `sttm.md`):

| PTX | SASS | mechanism |
|-----|------|-----------|
| `tcgen05.wait::ld` | none | LDTM's **write** scoreboard `dst_wr_sb`; consumer waits via the [121:116] wait mask |
| `tcgen05.wait::st` | `FENCE.VIEW.ASYNC.T` | a real fence op ordering the async TMEM-view writes |

This is consistent with the load/store scoreboard roles:
- **LDTM** (`INST_TYPE_DECOUPLED_WR_SCBD`) writes registers → releases a **write**
  scoreboard when the TMEM data lands. Any consumer of the loaded registers just
  waits on that scoreboard; no separate wait instruction is needed. So
  `tcgen05.wait::ld` compiles to **nothing** — it only guarantees the compiler
  attaches the wait mask to the first consumer.
- **STTM** (`INST_TYPE_DECOUPLED_RD_SCBD`) writes TMEM (no register dest) →
  there is no result register for a downstream op to wait on. To make the async
  TMEM write *visible* (e.g. before a `tcgen05.mma` reads that TMEM), ptxas emits
  an explicit **`FENCE.VIEW.ASYNC.T`**.

## Empirical verification
`tests/tcgen05_wait_test.cu`, `nvcc -arch=sm_100a`, CUDA 13.1. Three kernels:

### `wait_ld`: LDTM → wait::ld → consume
No `FENCE` anywhere. Ordering is pure scoreboard:
```
LDTM.x2 R4, tmem[UR6]        ; dst_wr_sb = 0  (releases SB0 when data lands)
...
IMAD.IADD R5, R4, 0x1, R5    ; wait_mask = 0x1 (waits on SB0)  <- consumes R4
```
Decoded control words:
| instr | wait mask | `dst_wr_sb` |
|-------|:---------:|:-----------:|
| `LDTM.x2` | 0x0 | **0** (sets SB0) |
| `IMAD.IADD R5,R4` (consumer) | **0x1** (waits SB0) | 7 |

The `tcgen05.wait::ld` produced **no instruction** — it only ensured the SB0 wait
mask landed on the first user of the loaded registers.

### `wait_st`: STTM → wait::st
```
STTM.x2 tmem[UR6], R4        ; src_rel_sb = 0
FENCE.VIEW.ASYNC.T           ; opcode 0x3c6  <- tcgen05.wait::st
```
The `FENCE.VIEW.ASYNC.T` is emitted right after the store.

### `wait_both`: both waits isolated (no async op)
Only a single `FENCE.VIEW.ASYNC.T` appears (from `wait::st`); `wait::ld`
contributes nothing even in isolation. ptxas coalesces to the one real fence.

## FENCE.VIEW.ASYNC.T — the `wait::st` opcode
`FENCE` (opcode 0b1111000110 = 0x3c6, `mio_pipe`) has three memType variants
(all same opcode, distinguished by `memType` [73:72]):

| SASS | memType | PTX driver |
|------|:-------:|-----------|
| `FENCE.VIEW.ASYNC.S` (`fence_`) | 0 (S = shared) | shared-async view fence |
| `FENCE.VIEW.ASYNC.G` (`fence_g_`) | 1 (G = global) | global-async view fence |
| `FENCE.VIEW.ASYNC.T` (`fence_t_`) | **2 (T = tensor)** | **`tcgen05.wait::st`** |

`fence_t_` details: `INST_TYPE_DECOUPLED_WR_SCBD`, `VIRTUAL_QUEUE=$VQ_FENCE_T`.
Modifiers are all single-value enums: `VIEWONLY`=VIEW, `ASYNCONLY`=ASYNC,
`TONLY`=T(2). Verified vector:
```
FENCE.VIEW.ASYNC.T
  Lo64 0x00000000000073c6  Hi64 0x000e620000000200
  opcode=0x3c6  memType[73:72]=2 (T)  src_rel_sb=7  dst_wr_sb=1
```
It is itself a decoupled op (sets its own write scoreboard `dst_wr_sb=1`), so a
following TMEM reader can wait on the fence's completion.

## Summary of the tcgen05 ordering/wait taxonomy
| PTX | SASS | kind |
|-----|------|------|
| `tcgen05.fence::before_thread_sync` | none | compile-time code-motion fence |
| `tcgen05.fence::after_thread_sync` | none | compile-time code-motion fence |
| `tcgen05.wait::ld` | none | scoreboard (LDTM write-SB + wait mask) |
| `tcgen05.wait::st` | `FENCE.VIEW.ASYNC.T` | real async-view fence |

Only `wait::st` emits an opcode. The other three are realized by the compiler via
scheduling + the ordinary control-word scoreboards (see
`notes/sm100/arch/control_codes.md`).

## Cross-references
- `notes/sm100/instr/ldtm.md` — LDTM write-scoreboard model (`wait::ld` target).
- `notes/sm100/instr/sttm.md` — STTM read-scoreboard; already noted
  `wait::st`→`FENCE.VIEW.ASYNC.T`.
- `notes/sm100/instr/tcgen05_fence.md` — the *other* (no-op) fences; don't
  confuse the two families.
- `notes/sm90/arch/memory_model.md` — FENCE.VIEW.ASYNC background (S/G variants
  predate Blackwell; T is the sm100 tensor-memory addition).

## Open questions
- Does `wait::ld` ever need a `FENCE` (e.g. if the loaded value crosses to a
  different memory view rather than staying in registers)?

## Confirmed: FENCE.VIEW.ASYNC.T is sm100-new
sm_90 has only **2** FENCE classes — `fence_` (`.S`) and `fence_g_` (`.G`);
`fence_t_` (`.T`, tensor-memory view) and the `$VQ_FENCE_T` virtual queue are
**Blackwell additions**, added alongside TMEM. The opcode 0x3c6 and the S/G
variants are unchanged from Hopper; only the `.T` memType value (2) is new.
