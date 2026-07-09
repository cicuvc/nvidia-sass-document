# tcgen05.fence::before/after_thread_sync — no SASS instruction (compile-time fence)

**PTX:** `tcgen05.fence::before_thread_sync` / `tcgen05.fence::after_thread_sync`
**SASS:** *(none — emits zero instructions)*
**Status:** resolved empirically on `sm_100a` (CUDA 13.1).

## Question
What SASS do the two specialized tcgen05 fences generate?

## Answer: nothing
Both `tcgen05.fence::before_thread_sync` and `::after_thread_sync` lower to **zero
SASS instructions**. They are **code-motion / scheduling barriers for the
compiler**, not runtime memory-fence opcodes. This matches the PTX description,
which defines them purely as ordering constraints:
- `::before_thread_sync` — prior async `tcgen05` ops "cannot be hoisted across"
  (a *sink* barrier for earlier tcgen05 ops).
- `::after_thread_sync` — subsequent async `tcgen05` ops "cannot be hoisted
  across" (a *hoist* barrier for later tcgen05 ops).

Both descriptions are about **code motion**; neither implies a hardware fence.
The actual cross-thread visibility is provided by the *execution-ordering*
instruction the fence composes with (a real `st.relaxed`/`ld.relaxed`, barrier,
or `bar.sync`), while the tcgen05.fence only pins the async ops on the correct
side of it in program order.

## Empirical verification
Two test kernels, both `nvcc -arch=sm_100a`, CUDA 13.1:

1. `tests/tcgen05_fence_test.cu` — fences in isolation (`fence_before`,
   `fence_after`, `fence_both`). Disassembly: **no `FENCE`** and no other
   ordering op appears for the intrinsics — only the surrounding `st/ld` and the
   kernel prologue/epilogue.

2. `tests/tcgen05_fence_ctx.cu` — the PTX-doc producer/consumer pattern with
   *real* async tcgen05 ops around the fences:
   - **producer:** `tcgen05.cp` → `tcgen05.fence::before_thread_sync` →
     `st.relaxed.gpu`
   - **consumer:** spin-`ld.relaxed.gpu` → `tcgen05.fence::after_thread_sync` →
     `tcgen05.ld`

   Disassembly still contains **zero `FENCE`** instructions. Confirmed with
   `grep -c FENCE` = 0. The tcgen05 ops themselves are present (`UTCCP.T.S`
   @0x320 in producer, `LDTM.x2` @0x380 in consumer); the fences between them and
   the flag load/store produced no code.

## How ordering is actually achieved (scoreboards, not fences)
Because the tcgen05 async ops are **decoupled** (`INST_TYPE_DECOUPLED_*_SCBD`),
their ordering rides on the ordinary control-word scoreboards, and the compiler
simply places the wait mask on the right instruction. Decoding the producer's
control words:

| instr | wait mask `req_bit_set` | `src_rel_sb` | `usched` |
|-------|:-----------------------:|:------------:|:--------:|
| `UTCCP.T.S` @0x320 | 0x1 | 0 (releases SB0 on shmem read) | 12 |
| `ST.E.STRONG.GPU` (flag) @0x3f0 | 0x2 | 7 | 17 |

The `::before_thread_sync` intended ordering (cp before the visible flag store)
is realized by:
- the async `UTCCP` releasing a **read scoreboard** (`src_rel_sb=0`) — the point
  the compiler treats as "the cp has been issued/its inputs consumed", and
- the visible store being a **`ST.E.STRONG.GPU`** (strong, GPU-scope) — the real
  memory-ordering carrier the fence "composes with".

The fence contributes no opcode; it only guaranteed the compiler kept the
`UTCCP` scheduled before the `ST.STRONG` in program order (no hoist across).
Likewise `::after_thread_sync` keeps the consumer's `LDTM` from being hoisted
above the acquiring `ld.relaxed`.

## Contrast: `tcgen05.wait::ld/st` DO emit
Don't confuse these with the `tcgen05.wait::*` completion waits, which are real:
- `tcgen05.wait::st` → `FENCE.VIEW.ASYNC.T` (see `sttm.md`).
- `tcgen05.wait::ld` → realized via the LDTM write-scoreboard + wait mask
  (see `ldtm.md`).

`tcgen05.fence::*_thread_sync` are ordering/code-motion fences (no code);
`tcgen05.wait::*` are completion waits (real fence/scoreboard). Two different
mechanisms.

## Cross-references
- `notes/sm100/instr/ldtm.md`, `sttm.md`, `utccp.md` — the async ops these
  fences order; all `INST_TYPE_DECOUPLED_*_SCBD`.
- `notes/sm100/arch/control_codes.md` — the scoreboard/wait-mask control word
  that carries the real ordering (unchanged from sm_90).
- `notes/sm90/arch/scoreboards.md` — scoreboard model background.

## Open questions
- Do the fences ever emit under `-O0` or in some scheduling corner case, or are
  they *always* zero-cost? (Both surveyed builds were default `-O3`; isolated and
  in-context both emit nothing.)
- Is there any config where ptxas needs an explicit `FENCE.VIEW.ASYNC.*` to
  realize `::*_thread_sync` (e.g. across a `bar.sync` at CTA scope)?
