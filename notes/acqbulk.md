# ACQBULK — Programmatic Dependent Launch acquire

**Opcode mnemonic:** `ACQBULK` = `0b100000101110` = **0x82e** | **Pipe:** `cbu_pipe` | compute-only (`SHADER_TYPE==CS`)

Hopper **Programmatic Dependent Launch (PDL)** consumer side — the SASS lowering of PTX `griddepcontrol.wait`. Blocks until prerequisite grids have signaled.

## Semantics
`@Pg ACQBULK` — blocks until the prerequisite grid's data is guaranteed visible. `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` — a fixed-latency *acquire* (same coupled-on-cbu pattern as `ELECT`/`ENDCOLLECTIVE`), i.e. it must complete before dependent work reads shared results.

Operand-less: all `ISRC_*`/`IDEST_*` = 0, guard predicate only.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x82e |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |

Not in `RPC_WRITERS` or `CBU_OPS_WITH_REQ`. Distinct from CGA cluster barrier and `EXIT` — PDL is a **grid-to-grid** launch-overlap mechanism.

## Cross-comparison
| | PREEXIT | **ACQBULK** |
|--|---------|-------------|
| PTX | `griddepcontrol.launch_dependents` | `griddepcontrol.wait` |
| side | producer (signal) | **consumer (wait/acquire)** |
| INSTRUCTION_TYPE | DECOUPLED_BRU | **COUPLED_MATH** |
| VIRTUAL_QUEUE | VQ_UNORDERED | **None** |
| blocks? | no (signal + continue) | **yes (acquire)** |

## Verified encodings (decoder: `tools/decode_preexit.py`)
Self-test 3/3; `tests/griddep2.cu` 2/2 per dump.

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| `0x000000000000782e` | `0x000fcc0000000000` | `ACQBULK` | `griddepcontrol.wait` |

### PTX→SASS mapping
`griddepcontrol.wait` → `ACQBULK`. Emitted for kernels launched with PDL attribute.

## Open questions
- Exact scope of `ACQBULK`'s acquire (grid vs cluster) is not spec-stated.
