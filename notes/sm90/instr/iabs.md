# IABS — Integer absolute value (32-bit)

**Opcode mnemonic:** `IABS` = `0b1000010011` = **0x213** (RRR) + 4 operand-form variants | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70

`Rd = |src|` — 32-bit signed integer absolute value. No modifiers (no saturation, no size:
strictly 32-bit).

## Semantics (verified)
`abs(int)` → `IABS Rd, Rb`. 32-bit only; `INT_MIN` wraps to itself (two's-complement).
`llabs`/64-bit abs does **not** use IABS — ptxas lowers it to `IADD3`-based negate + select.

## Variant overview (5 CLASS variants — source operand shape)
| opcode | form | source |
|--------|------|--------|
| 0x213  | RRR  | `Rb` register [39:32] |
| 0x813  | RsIR | 32-bit signed immediate [63:32] |
| 0xa13  | RCR  | const bank c[bank][off] |
| 0x1a13 | RCxR | const bank, extended addressing |
| 0x1c13 | RUR  | uniform register `URb` [37:32] |

In practice ptxas emits only **RRR** — a constant/uniform source is first loaded to a GPR
(`LDC`/`UMOV`) and then `IABS Rd, Rd`. The imm/const/uniform forms exist in the ISA but were not
observed from nvcc.

## Fields (128-bit, RRR)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x213 (+ high bits select operand form) |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | result (≠R254) |
| [39:32] | `Rb` | source register (RRR; `.reuse` supported) |
| [63:32] | `Sb` | 32-bit signed imm (RsIR) |
| [37:32] | `Ra_URb` | uniform src (RUR) |
| [58:54]/[53:40] | `Sb_bank`/`Sb_offset` | const-bank addr (RCR) |

IDEST/ISRC_B = 32. No dedicated modifier bits.

## Cross-comparison
| op | operation | note |
|----|-----------|------|
| **IABS** | `|x|` (32-bit) | dedicated abs |
| **IADD3** | `-x` / add | used for 64-bit abs (negate+select) |
| **IMNMX** | min/max | abs sometimes ≡ max(x,-x) on older archs |

Many other int ops fold abs of a source via a per-operand `|.|` modifier; `IABS` is the
standalone form.

## Latency (from sm_90_latencies.txt)
`int_pipe` member (FXU_OPS), fixed-latency `COUPLED_MATH` — a fast ALU op.

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000200007213` | `0x004fc80000000000` | `IABS R0, R2` |

Round-trip (synthetic) also covers `IABS R5, R7`, `IABS R5, UR3`, `IABS R5, 0x100`.
Decoder: `tools/decode_iabs.py`. Test: `tests/iabs_test.cu`.

### PTX→SASS mapping
- `abs(int)` / `abs.s32` → `IABS Rd, Rb`.
- 64-bit `llabs` → `IADD3`-based negate + select (not IABS).

## Open questions
- None significant; the non-RRR operand forms are unverified in text form (ptxas prefers RRR).
