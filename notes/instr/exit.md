# EXIT — Thread termination

**Opcode mnemonic:** `EXIT` = `0b100101001101` = **0x94d** | **Pipe:** `cbu_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The normal thread terminator. Every compute thread finishes with `EXIT`.

## Semantics
`@Pg EXIT{.mode}{.NO_ATEXIT} [Pp]` — terminates the guarded lanes: they enter the `MEXITED` state and stop fetching. Exiting lanes are removed from convergence-barrier participant sets (so a later `BSYNC` won't wait on them). By default the per-warp **at-exit handler** (`ATEXIT_PC`, part of `CBU_STATE`) is invoked; `.NO_ATEXIT` skips it.

## Variant overview
Single CLASS / opcode. Carries two modifier fields.

## Operands / fields (128-bit)
| bits | field | EXIT |
|------|-------|------|
| [91]∥[11:0] | opcode | 0x94d |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | predicate operand, printed if ≠ PT (`EXIT P1`) |
| [85:84] | `mode` `EXIT_MODE` | 0=–, 1=`.KEEPREFCOUNT`, 2=`.PREEMPTED`, 3=INVALID |
| [86] | `no_atexit` `NO_ATEXIT` | 0=–, 1=`.NO_ATEXIT` |

Modifier order: `EXIT{.mode}{.NO_ATEXIT}`. No target, no register operands.
- **`.PREEMPTED`** — exit path taken on preemption.
- **`.KEEPREFCOUNT`** — exit without decrementing a (CGA/resource) reference count.
- **`.NO_ATEXIT`** — do not run the at-exit handler.

## Latency / scheduling — EXIT waits on async work
`cbu_pipe` = `BRU_OPS`; `DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`. Crucially, EXIT is a member of:
- **`GMMA_SCOREBOARD_READERS`** / `GMMA_GROUP_SCOREBOARD_READERS`, and
- **`CGABAR_READERS`**.

So EXIT **reads the warpgroup-MMA (wgmma/`GMMA`) scoreboards and CGA/cluster-barrier state**: a thread cannot retire while its asynchronous tensor-core MMA or cluster-barrier participation is still outstanding. EXIT is not in `RPC_WRITERS` or `CBU_OPS_WITH_REQ`.

## Cross-comparison
| | **EXIT** | RET |
|--|----------|-----|
| effect | **end thread (`MEXITED`), run at-exit** | return from CALL |
| where | **any shader / compute** | any |
| async wait | **GMMA + CGA barriers** | — |
| lane-state mask | **MEXITED** | — |

## Verified encodings (decoder: `tools/decode_exit.py`)
Self-test 7/7; **16491/16491 EXIT in libcusparse decoded byte-exact**.

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| `0x000000000000794d` | `0x000fea0003800000` | `EXIT` | cusparse |
| `0x000000000000194d` | `0x000fea0003800000` | `@P1 EXIT` | cusparse |
| `0x000000000000594d` | `0x000fea0000800000` | `@P5 EXIT P1` | cusparse |
| `0x000000000000794d` | `0x000fea0003900000` | `EXIT.KEEPREFCOUNT` | patch |
| `0x000000000000794d` | `0x000fea0003a00000` | `EXIT.PREEMPTED` | patch |
| `0x000000000000794d` | `0x000fea0003c00000` | `EXIT.NO_ATEXIT` | patch |

### PTX→SASS mapping
Kernel/thread end and `return` from `main` body → `EXIT` (often `@!P EXIT` for early-return lanes, then a final unconditional `EXIT`).

## Open questions
- Runtime distinction between the EXIT modes (`.KEEPREFCOUNT` vs `.PREEMPTED`) and the exact resource whose refcount `.KEEPREFCOUNT` preserves.
