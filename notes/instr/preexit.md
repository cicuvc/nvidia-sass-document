# PREEXIT — Programmatic Dependent Launch signal

**Opcode mnemonic:** `PREEXIT` = `0b100000101101` = **0x82d** | **Pipe:** `cbu_pipe` | compute-only (`SHADER_TYPE==CS`)

Hopper **Programmatic Dependent Launch (PDL)** producer side — the SASS lowering of PTX `griddepcontrol.launch_dependents`. Signals that the grid has advanced enough that its dependent grids may begin launching.

## Semantics
`@Pg PREEXIT` — announces the grid is near its productive end so the driver can begin launching dependents. `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`, `VQ_UNORDERED` — it signals and continues (decoupled); the compiler hoists it early so dependents launch ASAP.

Operand-less: all `ISRC_*`/`IDEST_*` = 0, guard predicate only.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x82d |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |

Not in `RPC_WRITERS` or `CBU_OPS_WITH_REQ`.

## Cross-comparison
| | **PREEXIT** | ACQBULK |
|--|-------------|---------|
| PTX | `griddepcontrol.launch_dependents` | `griddepcontrol.wait` |
| side | **producer (signal)** | consumer (wait/acquire) |
| INSTRUCTION_TYPE | DECOUPLED_BRU | COUPLED_MATH |
| blocks? | no (signal + continue) | yes (acquire) |

## Verified encodings (decoder: `tools/decode_preexit.py`)
Self-test 3/3; `tests/griddep2.cu` 2/2 per dump.

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| `0x000000000000782d` | `0x000ff00000000000` | `PREEXIT` | `griddepcontrol.launch_dependents` |
| `0x000000000000182d` | `0x000ff00000000000` | `@P1 PREEXIT` | guard (spec-inferred) |

### PTX→SASS mapping
`griddepcontrol.launch_dependents` → `PREEXIT`. Emitted for kernels launched with PDL attribute (`cudaLaunchAttributeProgrammaticStreamSerialization`).

## Open questions
- Whether `PREEXIT` interacts with the at-exit state (`ATEXIT_PC`/`MATEXIT`) beyond the PDL signal.
