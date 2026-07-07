# BAR — CTA named-barrier synchronization (`__syncthreads`)

**Opcode mnemonic:** `BAR` — `0xb1d`/`0x91d`/`0x51d`/`0x31d` (one per operand form) | **Pipe:** `mio_pipe` (Memory-I/O) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_UNORDERED` | compute-only (`SHADER_TYPE==CS`)

The thread-block (CTA) barrier — `__syncthreads()` and the family of **named barriers**
(16 per CTA, index 0–15). Unlike the warp-level `WARPSYNC`/convergence machinery (all on
`cbu_pipe`), BAR lives on the **memory pipe**: it is a block-wide arrive/wait resource, not
a branch.

## Semantics
`@Pg BAR.<mode>[.DEFER_BLOCKING] <baridx>[, <count>][, <Pp>]` operates on named barrier
`baridx` with `count` participating threads (default = whole CTA). `<mode>` = `barmode`
[79:77]:

| mode | meaning | PTX / CUDA |
|------|---------|------------|
| **SYNC** | arrive **and wait** for the barrier | `bar.sync` / `__syncthreads()` (baridx 0) |
| **ARV** | **arrive only**, no wait (split barrier) | `bar.arrive` |
| **RED** | arrive + wait + **reduction** over a predicate | `__syncthreads_count/_and/_or` |
| **SCAN** | arrive + wait + prefix scan | — |
| **SYNCALL** | sync all (no operands) | — |

`.RED` carries `bop` [75:74] = `.POPC` (count of true `Pp`) / `.AND` / `.OR`, and reads a
source predicate `Pp` [89:87]. `.DEFER_BLOCKING` is the sm_90 default lowering of
`__syncthreads()` (arrive, then defer the blocking wait so the scheduler overlaps it).

## Operand forms — the "BAR_INDEXED" variants
The opcode's low bits select whether the barrier index and count are immediate or register:
| opcode | form | barrier idx | count |
|--------|------|-------------|-------|
| 0xb1d | **II** | imm `barname`[57:54] | imm `Sc`[53:42] |
| 0x91d | **IR** | imm `barname`[57:54] | reg `Rc`[39:32] |
| 0x51d | **RI** | reg `Rb`[39:32] | imm `Sc`[53:42] |
| 0x31d | **RR** | reg `Rb`[39:32] | reg `Rc`[39:32] (must equal Rb) |

The register forms (`bar.sync Rreg`) are the **`BAR_INDEXED`** entry (idx 62) — a runtime
barrier index/count, e.g. `BAR.ARV R9, R9`, `BAR.SYNC R8`.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | selects II/IR/RI/RR |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [80] | `defer_blocking` | 1 → `.DEFER_BLOCKING` |
| [79:77] | `barmode` | SYNC/ARV/RED/SCAN/SYNCALL |
| [75:74] | `bop` (RED) | POPC/AND/OR |
| [57:54] | `barname` | named-barrier index 0–15 (imm forms) |
| [53:42] | `Sc` | thread count (imm forms; omitted when 0 for SYNC/RED) |
| [39:32] | `Rb`/`Rc` | barrier/count register (reg forms) |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | source predicate (RED/SCAN) |

## Cross-comparison
- vs **WARPSYNC** (warp, `cbu_pipe`): BAR is **CTA-wide**, on `mio_pipe`, with 16 named
  barriers and participant counts; WARPSYNC syncs a 32-lane mask.
- vs **MEMBAR/FENCE**: those are memory-ordering fences (`MEMBAR.SC.GPU`, opcode 0x992) — a
  different instruction that only *looks* like "BAR" as a substring; not a thread barrier.
- vs cluster: `cluster.sync()` uses `BAR.*` + `MEMBAR` (and mbarrier/`ARRIVES`), not the
  CBU collectives.

## Latency
`mio_pipe`, `BAR_OP` set (`sm_90_latencies.txt:428`). `DECOUPLED_RD_SCBD`, `VQ_UNORDERED`
— it is scheduled through the MIO queue and gated by scoreboards, blocking until the
barrier is satisfied.

## Verified encodings (decoder: `tools/decode_bar.py`)
Self-test 5/5; **14849/14849 `BAR.*` in libcusparse decoded byte-exact**; `tests/bar_test.cu`
7/7 (SYNC/ARV/RED-POPC/AND/OR) and `tests/bar_reg.cu` 3/3 (register forms).

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| 0x0000000000007b1d | 0x000fec0000010000 | `BAR.SYNC.DEFER_BLOCKING 0x0` (`__syncthreads()`) |
| 0x0044000000007b1d | 0x000fe20000010000 | `BAR.SYNC.DEFER_BLOCKING 0x1, 0x100` (named bar 1, 256 thr) |
| 0x0044000000007b1d | 0x000ff00000002000 | `BAR.ARV 0x1, 0x100` |
| 0x0000000000007b1d | 0x000fec0000014000 | `BAR.RED.POPC.DEFER_BLOCKING 0x0, P0` (`__syncthreads_count`) |
| 0x0000000000007b1d | 0x000fec0000014400 | `BAR.RED.AND.DEFER_BLOCKING 0x0, P0` |
| (reg) | | `BAR.ARV R9, R9`, `BAR.SYNC.DEFER_BLOCKING R8` |

Hand-check `BAR.SYNC.DEFER_BLOCKING 0x1, 0x100`: opcode 0xb1d (II); barmode[79:77]=0=SYNC;
defer[80]=1; `barname`[57:54]=1 → `0x1`; `Sc`[53:42]=0x100 → `0x100`.

### PTX→SASS mapping
`__syncthreads()` → `BAR.SYNC.DEFER_BLOCKING 0x0`; `__syncthreads_count/_and/_or(p)` →
`BAR.RED.POPC/.AND/.OR.DEFER_BLOCKING 0x0, p`; `bar.sync n,c` / `bar.arrive n,c` →
`BAR.SYNC`/`BAR.ARV n, c` (register operands when `n`/`c` are dynamic).

## Open questions
- `.SCAN`/`.SYNCALL` and the `noSrc` SYNCALL forms are spec-defined but not emitted by the
  sampled ptxas; their exact rendering/use is unverified.
- Exact micro-semantics of `.DEFER_BLOCKING` (how long the wait is deferred, interaction
  with the MIO scoreboard) is not spec-stated.
