# EXIT / KILL — Thread termination

**Opcode mnemonics:** `EXIT` = `0b100101001101` = **0x94d**; `KILL` = `0b100101011011` = **0x95b** | **Pipe:** `cbu_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The two thread terminators. **EXIT** ends a thread normally (every compute thread finishes
with `EXIT`); **KILL** discards a thread and is **pixel-shader only** — it never appears in
compute SASS.

## Semantics
### EXIT `@Pg EXIT{.mode}{.NO_ATEXIT} [Pp]`
Terminates the guarded lanes: they enter the `MEXITED` state and stop fetching. Exiting
lanes are removed from convergence-barrier participant sets (so a later `BSYNC` won't wait
on them). By default the per-warp **at-exit handler** (`ATEXIT_PC`, part of `CBU_STATE`) is
invoked; `.NO_ATEXIT` skips it.

### KILL `@Pg KILL [Pp]`
Fragment-`discard`: kills the guarded lanes (state `MKILL`). Legal only in a pixel shader
(`CONDITION: SHADER_TYPE ∈ {PS, TRAP, UNKNOWN}`), so ptxas never emits it for CUDA compute.

## Variant overview
Each is a single CLASS / opcode. EXIT carries two modifier fields; KILL carries none.

## Operands / fields (128-bit)
| bits | field | EXIT | KILL |
|------|-------|------|------|
| [91]∥[11:0] | opcode | 0x94d | 0x95b |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | predicate operand, printed if ≠ PT (`EXIT P1`) | same |
| [85:84] | `mode` `EXIT_MODE` | 0=–, 1=`.KEEPREFCOUNT`, 2=`.PREEMPTED`, 3=INVALID | — |
| [86] | `no_atexit` `NO_ATEXIT` | 0=–, 1=`.NO_ATEXIT` | — |

Modifier order: `EXIT{.mode}{.NO_ATEXIT}`. No target, no register operands.
- **`.PREEMPTED`** — exit path taken on preemption.
- **`.KEEPREFCOUNT`** — exit without decrementing a (CGA/resource) reference count.
- **`.NO_ATEXIT`** — do not run the at-exit handler.

## Latency / scheduling — EXIT waits on async work
`cbu_pipe` = `BRU_OPS`; `DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`. Crucially, EXIT is a member of
- **`GMMA_SCOREBOARD_READERS`** / `GMMA_GROUP_SCOREBOARD_READERS` (`sm_90_latencies.txt:386,400`), and
- **`CGABAR_READERS`** (line 369).

So EXIT **reads the warpgroup-MMA (wgmma/`GMMA`) scoreboards and CGA/cluster-barrier state**:
a thread cannot retire while its asynchronous tensor-core MMA or cluster-barrier
participation is still outstanding. EXIT is not in `RPC_WRITERS` or `CBU_OPS_WITH_REQ`.

## Cross-comparison
| | **EXIT** | **KILL** | RET |
|--|----------|----------|-----|
| effect | end thread (`MEXITED`), run at-exit | discard thread (`MKILL`) | return from CALL |
| where | any shader / compute | **pixel shader only** | any |
| async wait | GMMA + CGA barriers | — | — |
| lane-state mask | `MEXITED` | `MKILL` | — |

Both remove lanes from convergence-barrier participation, so `BSYNC`/`BSSY` correctly skip
exited/killed lanes (this is what keeps the barriers from deadlocking — see the branch
control-flow overview).

## Verified encodings (decoder: `tools/decode_exit.py`)
Self-test 7/7; **16491/16491 EXIT in libcusparse decoded byte-exact** (bare + `@Pg` +
`EXIT Pp` forms). EXIT modifiers and KILL via cubin-patch (KILL is PS-only → patch-derived).

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| 0x000000000000794d | 0x000fea0003800000 | `EXIT` | cusparse |
| 0x000000000000194d | 0x000fea0003800000 | `@P1 EXIT` | cusparse |
| 0x000000000000594d | 0x000fea0000800000 | `@P5 EXIT P1` | cusparse |
| 0x000000000000794d | 0x000fea0003900000 | `EXIT.KEEPREFCOUNT` | patch |
| 0x000000000000794d | 0x000fea0003a00000 | `EXIT.PREEMPTED` | patch |
| 0x000000000000794d | 0x000fea0003c00000 | `EXIT.NO_ATEXIT` | patch |
| 0x000000000000795b | 0x000fea0003800000 | `KILL` | patch (PS-only) |

### PTX→SASS mapping
Kernel/thread end and `return` from `main` body → `EXIT` (often `@!P EXIT` for
early-return lanes, then a final unconditional `EXIT`). `.KEEPREFCOUNT`/`.PREEMPTED`/
`.NO_ATEXIT` are runtime/driver-inserted (preemption, trap, at-exit management) — not from
ordinary C. `KILL` corresponds to graphics `discard`, absent from CUDA.

## Open questions
- Runtime distinction between the EXIT modes (`.KEEPREFCOUNT` vs `.PREEMPTED`) and the
  exact resource whose refcount `.KEEPREFCOUNT` preserves (CGA/cluster membership?) is not
  spec-stated.
- The `Pp` operand's effect on EXIT/KILL (vs the `@Pg` guard) is unverified; only guard-only
  and `Pp`-present renderings are confirmed.
