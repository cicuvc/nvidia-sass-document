# BRXU — Register-indirect branch (uniform-GPR target)

**Opcode mnemonic:** `BRXU` = `0b1100101011000` = **0x1958** | **Pipe:** `cbu_pipe` (Branch Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The uniform-register indirect branch: the branch target comes from a **uniform register pair plus an immediate offset**. The uniform-register sibling of `BRX`.

## Semantics
`@Pg BRXU{.INC/.DEC} {Pp,} URa [, off]` branches (for lanes where `Pg` holds) to a target formed from the 64-bit uniform register `URa` (`ISRC_A_SIZE = 64`, even-aligned pair, `URa%2==0`) and the signed immediate `off` (`= sImm*4`). Carries a `cond` modifier.

## Variant overview
| mnem | opcode `{b91,[11:0]}` | target register | cond field | alt |
|------|-----------------------|-----------------|------------|-----|
| `brxu_` | 0x1958 | `URa` [29:24] (UGPR) | [33:32] `COND` | `brxu_rel_` |

`_rel_` alternates only change how the assembler is given the offset (label vs explicit relative), same bits.

## Operands / fields (128-bit)
| bits | field | BRXU |
|------|-------|------|
| [91]∥[11:0] | opcode | 0x1958 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | divergence pred (≠PT → printed) |
| [86:85] | `depth` `DEPTH` | `.INC`/`.DEC` |
| [33:32] | `cond` `COND` | 0=none,1=`.U`,2=`.DIV`,3=`.CONV` |
| [29:24] | `URa` | UGPR (URZ=63) |
| [81:34]∥[23:16] | `sImm` | 56-bit signed, offset = `sImm*4` |

### Offset rendering
`off = (sImm*4) & 0xffffffffff` (40-bit address mask). **Omitted entirely when `sImm==0`** (`BRXU UR4`). Negatives print masked: `sImm=-1 → 0xfffffffffc`.

## Cross-comparison
| | BRA/JMP | BRX | **BRXU** | CALL |
|--|---------|-----|----------|------|
| target | imm/const | GPR pair + off | **UGPR pair + off** | reg/const/imm |
| `RPC_WRITERS` | yes | yes | **yes** | yes |
| `CBU_OPS_WITH_REQ` (`&req=`) | BRA yes / JMP no | yes | **yes** | yes |

BRXU is to BRX what JMXU is to JMX: the uniform-register indirect form.

## Latency
`cbu_pipe` = `BRU_OPS`. `RPC_WRITERS` → **9-cycle** RPC true-dependency (`sm_90_latencies.txt:411,414`) and `CBU_OPS_WITH_REQ` (line 219, honor `&req=`). `DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_brx.py`)
Not emitted by ptxas on sm_90/CUDA 13.1. Ground truth via **cubin-patching + nvdisasm**: self-test 7/7, plus randomized battery of 300 patched encodings decoded 100%.

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000004000958` | `0x000fea000b800000` | `@P0 BRXU UR4` (off=0 omitted) |
| `0x0000000204000958` | `0x000fea000b800000` | `@P0 BRXU.DIV UR4` |
| `0x0000000304000958` | `0x000fea000b800000` | `@P0 BRXU.CONV UR4` |

## Open questions
- Exact runtime target formula (`URa + off` absolute vs. relative-to-anchor) can't be pinned from static disasm alone.
