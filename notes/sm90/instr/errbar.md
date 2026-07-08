# ERRBAR — GPU-scope error barrier

**Opcode mnemonic:** `ERRBAR` = `0b100110101011` = **0x9ab** | **Pipe:** `mio_pipe`

Barrier that **synchronizes/surfaces deferred errors** (asynchronous memory faults, ECC, etc.) from prior GPU-scope operations. The compiler pairs it with wide-scope memory fences: a `__threadfence()` becomes not just an ordering `MEMBAR` but also an error-observation point.

## Semantics
`@Pg ERRBAR` — block until deferred errors from prior (now-fenced) memory operations at GPU scope have been observed. `INST_TYPE_COUPLED_MATH`, `VQ=None` — a fixed-latency, blocking op. Operand-less (guard predicate only).

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x9ab |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |

## Emission — fence scope decides (verified)
| CUDA | SASS |
|------|------|
| `__threadfence_block()` | `MEMBAR.SC.CTA` **only** (no error barrier) |
| `__threadfence()` (GPU) | `MEMBAR.SC.GPU ; **ERRBAR** ; CGAERRBAR` |
| `__threadfence_system()` | `MEMBAR.SC.SYS ; **ERRBAR** ; CGAERRBAR` |
| `fence.cluster.acq_rel` (PTX) | `MEMBAR.ALL.GPU ; ERRBAR ; CGAERRBAR` |

So **error barriers accompany GPU-/SYS-/cluster-scope fences, never CTA(block)-scope**.

## Cross-comparison
| | **ERRBAR** | CGAERRBAR | MEMBAR |
|--|-----------|-----------|--------|
| role | **GPU-scope error barrier** | cluster-scope error barrier | memory-ordering fence |
| INSTRUCTION_TYPE | **COUPLED_MATH** | DECOUPLED_BRU | (mio fence) |
| opcode | **0x9ab** | 0x5ab | 0x992 |

`MEMBAR` provides *ordering*; `ERRBAR`/`CGAERRBAR` provide *error observation*.

## Latency
`mio_pipe`. `ERRBAR` is `COUPLED_MATH` (fixed-latency blocking). Not in `RPC_WRITERS`/`CBU_OPS_WITH_REQ`.

## Verified encodings (decoder: `tools/decode_errbar.py`)
Self-test 2/2; 6/6 in the fence dump, 62/62 in the cluster-kernel dump.

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000000079ab` | `0x000fc00000000000` | `ERRBAR` |

## Open questions
- The exact error class each barrier drains (page-fault vs ECC vs async-copy completion error).
