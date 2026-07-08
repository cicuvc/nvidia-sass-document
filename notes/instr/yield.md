# YIELD — Warp-scheduler yield hint

**Opcode mnemonic:** `YIELD` = `0b100101000110` = **0x946** | **Pipe:** `cbu_pipe` (Branch / Convergence-Barrier Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

A hint to the **warp scheduler** to switch away from the issuing warp/divergent group at
this issue slot — the explicit "let someone else run" instruction. It is the ISA-level
lever behind Volta+ Independent Thread Scheduling's **forward-progress** behavior: dropped
into spin/poll loops so a waiting warp deprioritizes itself and lets the warp/group holding
the awaited resource make progress.

## Semantics
`@Pg YIELD [Pp]` requests the scheduler to yield the current warp's turn (favor another
ready warp / PC-group on the next cycle) for the lanes where `Pg` holds. It performs no
data movement and takes no target — only the guard predicate `Pg` and an optional
predicate operand `Pp`. It does not *block* (unlike `BSYNC`) or *sleep for a duration*
(unlike `NANOSLEEP`); it just relinquishes priority for one scheduling decision.

## Variant overview
Single CLASS `yield_inst_`, one opcode 0x946. No target, no register/immediate operands
(all `ISRC_*`/`IDEST_*` sizes = 0).

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x946 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | predicate operand, printed if ≠ PT (`YIELD P3`) |

Same skeleton as `BSYNC`/`BREAK` **minus the `barReg` field**. Standard scheduling control
word occupies the usual hi-bits (`req_bit_set`, `src_rel_sb`/`dst_wr_sb`=7, `pm_pred`,
`opex`).

`Pp` on YIELD must be PT — a non-PT predicate operand is an illegal encoding.

## Rendering
`YIELD` (bare), `@P0 YIELD` (guarded), `YIELD P3` / `YIELD !PT` (predicate operand, space,
no comma).

## Cross-comparison
| | **YIELD** | NANOSLEEP | BSYNC | WARPSYNC |
|--|-----------|-----------|-------|----------|
| effect | yield one scheduling turn | sleep N ns | block until barrier participants arrive | reconverge/sync a warp mask |
| blocks? | no | timed | yes | yes |
| operands | — | ns count | `Bi` | mask |

All are `cbu_pipe` / `DECOUPLED_BRU`. YIELD and NANOSLEEP are the two "back off / let others
run" primitives; YIELD is the lightweight, untimed one.

## Latency / scheduling
`cbu_pipe` = `BRU_OPS`. YIELD **is** an `RPC_WRITERS` member (`sm_90_latencies.txt:411`) →
9-cycle true-dependency on the `RPC` resource (it interacts with warp reconvergence/
scheduling state). It is **not** in `CBU_OPS_WITH_REQ`, so it does not gate on the `&req=`
scoreboard. `MIN_WAIT_NEEDED=1`. (Distinct from the per-instruction control-word `stall`/
`usched_info` scheduling knobs carried by *every* instruction; YIELD is the explicit,
standalone strong yield.)

## Verified encodings (decoder: `tools/decode_yield.py`)
Self-test 3/3; **1742/1742 YIELD in libcusparse decoded byte-exact**; `tests/yield_test.cu`
(spin-wait + spin-lock) emits YIELD (1/1). Guarded/predicated forms via cubin-patch.

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| 0x0000000000007946 | 0x000fea0003800000 | `YIELD` | libcusparse / spin kernel |
| 0x0000000000000946 | 0x000fea0003800000 | `@P0 YIELD` | patch |
| 0x0000000000007946 | 0x000fea0001800000 | `YIELD P3` | patch |

### Empirical usage pattern (CUDA 13.1, sm_90)
The compiler emits `YIELD` at the **top of poll / spin-wait loop bodies**, right before the
awaited access:
```
        MOV   R4, RZ
        YIELD                              ; hint: let other warps run
        ATOMG.E.CAS.STRONG.GPU PT, R0, [R2], R4, R5   ; atomicCAS(lock,0,1)
        ISETP.NE.AND P0, PT, R0, RZ, PT
        @P0 BRA <back to YIELD>            ; keep spinning if CAS failed
```
and before strong/global polling loads:
```
        ISETP.GE ...
        YIELD
        BSSY B3, JOIN
        @!P2 BRA ...
        LDG.E.STRONG.GPU ...              ; read shared state another warp updates
        BSYNC B3
```
This is the concrete realization of the ITS forward-progress guarantee (see the branch
control-flow overview): the spinning warp yields each iteration so the lock/flag holder is
interleaved, can complete, and release — breaking the pre-Volta warp-internal spin deadlock.

## Open questions
- The exact scheduler policy (how strongly/for how long YIELD deprioritizes the warp, and
  its interaction with the control-word `stall`/`usched_info` bits) is not exposed by the
  spec — only that YIELD is the explicit yield op on the CBU pipe.
