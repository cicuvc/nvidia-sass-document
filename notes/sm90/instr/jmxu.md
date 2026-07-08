# JMXU — Absolute register-indirect jump (uniform-GPR target)

**Opcode mnemonic:** `JMXU` = `0b1100101011001` = **0x1959** | **Pipe:** `cbu_pipe` (Branch Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The absolute-indirect uniform-register jump: target from a **uniform register pair plus immediate offset**. The uniform-register sibling of `JMX`.

## Semantics
`@Pg JMXU{.INC/.DEC} {Pp,} URa [, off]` jumps (for lanes where `Pg` holds) to a target formed from the 64-bit uniform register `URa` (`ISRC_A_SIZE = 64`, even-aligned pair) and the signed immediate `off = sImm*4`. Carries a `cond` modifier.

## Variant overview
| mnem | opcode `{b91,[11:0]}` | target register | cond field | alt |
|------|-----------------------|-----------------|------------|-----|
| `jmxu_` | 0x1959 | `URa` [29:24] (UGPR) | [33:32] `COND` | `jmxu_rel_` |

## Operands / fields (128-bit)
| bits | field | JMXU |
|------|-------|------|
| [91]∥[11:0] | opcode | 0x1959 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | divergence pred (≠PT → printed) |
| [86:85] | `depth` `DEPTH` | `.INC`/`.DEC` |
| [33:32] | `cond` `COND` | 0=none,1=`.U`,2=`.DIV`,3=`.CONV` |
| [29:24] | `URa` | UGPR (URZ=63) |
| [81:34]∥[23:16] | `sImm` | 56-bit signed, offset = `sImm*4` |

Offset rendering: `off = (sImm*4) & 0xffffffffff`, **omitted when `sImm==0`**; negatives print masked.

## Cross-comparison
| | BRA | JMP | BRXU | **JMXU** |
|--|-----|-----|------|----------|
| target | rel imm | abs imm/const | UGPR+off (rel) | **UGPR+off (abs)** |
| opcode | 0x947 | 0x94a/0xb4a | 0x1958 | **0x1959** |
| `RPC_WRITERS` | y | y | y | **y** |
| `CBU_OPS_WITH_REQ` | BRA y | JMP n | y | **y** |

## Latency
`cbu_pipe` = `BRU_OPS`. `RPC_WRITERS` → **9-cycle** RPC true-dependency (`sm_90_latencies.txt:411,414`) and `CBU_OPS_WITH_REQ`. `DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_jmx.py`, shared core in `decode_brx.py`)
Not emitted by ptxas. Ground truth via **cubin-patching + nvdisasm**: self-test 7/7, randomized battery 100%.

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000004000959` | `0x000fea000b800000` | `@P0 JMXU UR4` |
| `0x0000000204000959` | `0x000fea000b800000` | `@P0 JMXU.DIV UR4` |
| `0x0000000304000959` | `0x000fea000b800000` | `@P0 JMXU.CONV UR4` |

## Open questions
- The BR*/JM* runtime distinction (relative-indirect vs absolute-indirect target) mirrors the confirmed BRA(rel)/JMP(abs) split but is not observable statically.
