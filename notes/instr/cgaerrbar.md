# CGAERRBAR — CGA-scope error barrier

**Opcode mnemonic:** `CGAERRBAR` = `0b10110101011` = **0x5ab** | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

Thread-block cluster-scope error barrier — synchronizes/surfaces deferred errors (asynchronous memory faults, ECC, etc.) from prior cluster-scope operations.

## Semantics
Operand-less (guard predicate only). A **CGABAR_READERS** member — the cluster-scope sibling of `ERRBAR`. Accompanies cluster-scope memory fences.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x5ab |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |

## Emission — fence scope decides (verified)
Accompanies GPU-/SYS-/cluster-scope fences, never CTA(block)-scope:
| CUDA | SASS |
|------|------|
| `__threadfence()` (GPU) | `MEMBAR.SC.GPU ; ERRBAR ; **CGAERRBAR**` |
| `__threadfence_system()` | `MEMBAR.SC.SYS ; ERRBAR ; **CGAERRBAR**` |
| `fence.cluster.acq_rel` (PTX) | `MEMBAR.ALL.GPU ; ERRBAR ; **CGAERRBAR**` |

## Cross-comparison
| | ERRBAR | **CGAERRBAR** | MEMBAR |
|--|--------|---------------|--------|
| role | GPU-scope error barrier | **cluster-scope error barrier** | memory-ordering fence |
| INSTRUCTION_TYPE | COUPLED_MATH | **DECOUPLED_BRU** | (mio fence) |
| opcode | 0x9ab | **0x5ab** | 0x992 |

## Latency
`mio_pipe`. `DECOUPLED_BRU`/`VQ_UNORDERED`. Not in `RPC_WRITERS`/`CBU_OPS_WITH_REQ`.

## Verified encodings (decoder: `tools/decode_errbar.py`)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000000075ab` | `0x000fec0000000000` | `CGAERRBAR` |

## Open questions
- The exact error class each barrier drains (page-fault vs ECC vs async-copy completion error).
