# ERRBAR / CGAERRBAR — Error barriers

**Opcode mnemonics:** `ERRBAR` = `0b100110101011` = **0x9ab**; `CGAERRBAR` = `0b10110101011` = **0x5ab** | **Pipe:** `mio_pipe`

Barriers that **synchronize/surface deferred errors** (asynchronous memory faults, ECC,
etc.) from prior operations. The compiler pairs them with wide-scope memory fences: a
`__threadfence()` becomes not just an ordering `MEMBAR` but also an error-observation point.

## Semantics
- **`ERRBAR`** — error barrier: block until deferred errors from prior (now-fenced) memory
  operations at GPU scope have been observed. `INST_TYPE_COUPLED_MATH`, `VQ=None` — a
  fixed-latency, blocking op.
- **`CGAERRBAR`** — the **CGA (thread-block cluster) scope** error barrier (distributed
  shared memory / cluster ops). `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`, `VQ_UNORDERED`.

Both are operand-less (guard predicate only).

## Emission — fence scope decides (verified)
`tests/fence_variants.cu`, sm_90/CUDA 13.1:

| CUDA | SASS |
|------|------|
| `__threadfence_block()` | `MEMBAR.SC.CTA` **only** (no error barrier) |
| `__threadfence()` (GPU) | `MEMBAR.SC.GPU ; **ERRBAR** ; **CGAERRBAR**` |
| `__threadfence_system()` | `MEMBAR.SC.SYS ; **ERRBAR** ; **CGAERRBAR**` |
| `fence.cluster.acq_rel` (PTX) | `MEMBAR.ALL.GPU ; ERRBAR ; CGAERRBAR` (+`CCTL.IVALL` on acquire) |
| (no fence) | neither |

So **error barriers accompany GPU-/SYS-/cluster-scope fences, never CTA(block)-scope** —
consistent with the idea that only wide-scope ops have an asynchronous error path that a
fence must flush. They also appear in kernel cleanup/cluster-exit sequences.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x9ab ERRBAR / 0x5ab CGAERRBAR |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |

## Cross-comparison
| | **ERRBAR** | **CGAERRBAR** | MEMBAR |
|--|-----------|---------------|--------|
| role | GPU-scope error barrier | cluster-scope error barrier | memory-ordering fence |
| INSTRUCTION_TYPE | COUPLED_MATH | DECOUPLED_BRU | (mio fence) |
| opcode | 0x9ab | 0x5ab | 0x992 |

`MEMBAR` provides *ordering*; `ERRBAR`/`CGAERRBAR` provide *error observation* — a fence
emits both. (`MEMBAR.SC.GPU`/`.ALL.GPU`, opcode 0x992, is a separate instruction — note the
"BAR" substring is unrelated to the CTA barrier `BAR`, see `bar.md`.)

## Latency
`mio_pipe`. `ERRBAR` is `COUPLED_MATH` (fixed-latency blocking); `CGAERRBAR` is
`DECOUPLED_BRU`/`VQ_UNORDERED`. Neither is in `RPC_WRITERS`/`CBU_OPS_WITH_REQ`.

## Verified encodings (decoder: `tools/decode_errbar.py`)
Self-test 2/2; **6/6** in the fence dump, **62/62** in the cluster-kernel dump.

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| 0x00000000000079ab | 0x000fc00000000000 | `ERRBAR` |
| 0x00000000000075ab | 0x000fec0000000000 | `CGAERRBAR` |

### PTX→SASS mapping
GPU/system/cluster-scope fences and acquire/release atomics with those scopes emit
`ERRBAR`/`CGAERRBAR` after the `MEMBAR`. `ERRBAR` is TODO idx 0 (labeled "internal
pseudo-instruction") — but it is a real, emitted opcode, not a pseudo-op.

## Open questions
- The exact error class each barrier drains (page-fault vs ECC vs async-copy completion
  error) and whether `CGAERRBAR`'s decoupled nature means it only *posts* an error-check
  (drained later) vs `ERRBAR`'s blocking observe, is not spec-stated.
