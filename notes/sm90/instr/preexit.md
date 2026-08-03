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

### SM120 assembler verification (`tests/asm_construct/test_pdl.py`)
On sm_120 (CUDA 12.8) ptxas emits PREEXIT with `?trans3`: `0x000000000000782d / 0x000fe60000000000` — same opcode, but a different scheduling word than sm_90's `?trans8` (`0x000ff00000000000`). The repo assembler (`assembler/`, backed by sm120.json) reproduces the ptxas encoding bit-for-bit with bracket `[7:7:{}:3:0]`, and the built cubin round-trips through cuobjdump as `PREEXIT ?trans3`. GPU check (RTX 5090): a producer launched with `CU_LAUNCH_ATTRIBUTE_PROGRAMMATIC_STREAM_SERIALIZATION` signals via PREEXIT, and the paired consumer ACQBULK observes the write published before the signal (release/acquire pair).

## Open questions
- Whether `PREEXIT` interacts with the at-exit state (`ATEXIT_PC`/`MATEXIT`) beyond the PDL signal.
