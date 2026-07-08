# JMX — Absolute register-indirect jump (GPR target)

**Opcode mnemonic:** `JMX` = `0b100101001100` = **0x94c** | **Pipe:** `cbu_pipe` (Branch Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The absolute-indirect twin of `BRX` — same "target = register + immediate offset" mechanism, but the *absolute* jump family (as `JMP` is to `BRA`). Reads a **GPR pair**.

## Semantics
`@Pg JMX{.INC/.DEC} {Pp,} Ra [, off]` jumps (for lanes where `Pg` holds) to a target formed from the 64-bit register `Ra` (`ISRC_A_SIZE = 64`, even-aligned pair, `Ra != R254`) and the signed immediate `off = sImm*4`. `Pp` is the divergence predicate; `depth` adjusts the call-depth counter.

## Variant overview
| mnem | opcode `{b91,[11:0]}` | target register |
|------|-----------------------|-----------------|
| `jmx_`  | 0x094c | `Ra` [31:24] (GPR) |

## Operands / fields (128-bit)
| bits | field | JMX |
|------|-------|-----|
| [91]∥[11:0] | opcode | 0x94c |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | divergence pred (≠PT → printed) |
| [86:85] | `depth` `DEPTH` | `.INC`/`.DEC` |
| [31:24] | `Ra` | GPR (RZ=255) |
| [81:34]∥[23:16] | `sImm` | 56-bit signed, offset = `sImm*4` |

Offset rendering: `off = (sImm*4) & 0xffffffffff`, **omitted when `sImm==0`** (`JMX R6`); negatives print masked (`-16 → 0xfffffffff0`).

## Cross-comparison
| | BRA | JMP | BRX | **JMX** |
|--|-----|-----|-----|---------|
| target | rel imm | abs imm/const | GPR+off (rel) | **GPR+off (abs)** |
| opcode | 0x947 | 0x94a/0xb4a | 0x949 | **0x94c** |
| `RPC_WRITERS` | y | y | y | **y** |
| `CBU_OPS_WITH_REQ` | BRA y | JMP n | y | **y** |

## Latency
`cbu_pipe` = `BRU_OPS`. `RPC_WRITERS` → **9-cycle** RPC true-dependency (`sm_90_latencies.txt:411,414`) and `CBU_OPS_WITH_REQ` (line 219, honor `&req=`). `DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_jmx.py`, shared core in `decode_brx.py`)
Not emitted by ptxas. Ground truth via **cubin-patching + nvdisasm**: self-test 7/7, randomized battery 100%.

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x000000040424094c` | `0x000fea0003800000` | `@P0 JMX R4 0x490` |
| `0x000000000600094c` | `0x000fea0003800000` | `@P0 JMX R6` (off=0 omitted) |
| `0xfffffffc06fc094c` | `0x000fea0003800000` | `@P0 JMX R6 0xfffffffff0` (off = -16) |

## Open questions
- The BR*/JM* runtime distinction (relative-indirect vs absolute-indirect target) mirrors the confirmed BRA(rel)/JMP(abs) split but is not observable statically.
- Real jump-table usage is unobserved because ptxas never emitted these in the sampled code.
