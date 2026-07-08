# KILL — Fragment discard (thread termination)

**Opcode mnemonic:** `KILL` = `0b100101011011` = **0x95b** | **Pipe:** `cbu_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The pixel-shader `discard` instruction: kills the guarded lanes (state `MKILL`). **Compute-only shaders never emit KILL** — it is legal only in a pixel shader (`SHADER_TYPE ∈ {PS, TRAP, UNKNOWN}`).

## Semantics
`@Pg KILL [Pp]` — kills the guarded lanes (fragment discard). No register operands, no modifier fields. Single CLASS / opcode.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x95b |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | predicate operand, printed if ≠ PT |

Removes lanes from convergence-barrier participation, so `BSYNC`/`BSSY` correctly skip killed lanes.

## Cross-comparison
| | EXIT | **KILL** | RET |
|--|------|----------|-----|
| effect | end thread (`MEXITED`), run at-exit | **discard thread (`MKILL`)** | return from CALL |
| where | any shader / compute | **pixel shader only** | any |
| async wait | GMMA + CGA barriers | — | — |

## Verified encodings (decoder: `tools/decode_exit.py`)
PS-only via cubin-patch:
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x000000000000795b` | `0x000fea0003800000` | `KILL` |
