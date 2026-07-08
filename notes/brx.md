# BRX — Register-indirect branch (GPR target)

**Opcode mnemonic:** `BRX` = `0b100101001001` = **0x949** | **Pipe:** `cbu_pipe` (Branch Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The register-indirect relative of `BRA`/`JMP`: the branch target comes from a **register value plus an immediate offset**, rather than from an immediate/const alone. Used for compiler-built jump tables and computed branches.

## Semantics
`@Pg BRX{.INC/.DEC} {Pp,} Ra [, off]` branches (for lanes where `Pg` holds) to a target formed from the 64-bit register `Ra` and the signed immediate `off` (`= sImm*4`). `Ra` is `ISRC_A_SIZE = 64` and is range/alignment-checked as an **even-aligned register pair** (`Ra%2==0`, `Ra != R254`), i.e. it holds a 64-bit target/base address; the encoded `off` is added to it.

The optional `Pp` is the divergence predicate (same role as in `BRA`); `depth` (`.INC`/`.DEC`) adjusts the call-depth counter.

## Variant overview
| mnem | opcode `{b91,[11:0]}` | target register |
|------|-----------------------|-----------------|
| `brx_`  | 0x0949 | `Ra` [31:24] (GPR) |

`_rel_` alternates only change how the assembler is given the offset (label vs explicit relative), same bits.

## Operands / fields (128-bit)
| bits | field | BRX |
|------|-------|-----|
| [91]∥[11:0] | opcode | 0x949 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | divergence pred (≠PT → printed) |
| [86:85] | `depth` `DEPTH` | `.INC`/`.DEC` |
| [31:24] | `Ra` | GPR (RZ=255) |
| [81:34]∥[23:16] | `sImm` | 56-bit signed, offset = `sImm*4` |

### Offset rendering
`off = (sImm*4) & 0xffffffffff` (40-bit address mask). **Omitted entirely when `sImm==0`**. Negatives print masked: `sImm=-1 → 0xfffffffffc`.

## Cross-comparison
| | BRA/JMP | **BRX** | CALL |
|--|---------|---------|------|
| target | imm/const | **GPR pair + off** | reg/const/imm |
| `RPC_WRITERS` | yes | **yes** | yes |
| `CBU_OPS_WITH_REQ` (`&req=`) | BRA yes / JMP no | **yes** | yes |

BRX is to BRA what JMX is to JMP: the indirect form.

## Latency
`cbu_pipe` = `BRU_OPS`. `RPC_WRITERS` → **9-cycle** RPC true-dependency (`sm_90_latencies.txt:411,414`) and `CBU_OPS_WITH_REQ` (line 219, honor `&req=`). `DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_brx.py`)
Not emitted by ptxas on sm_90/CUDA 13.1. Ground truth via **cubin-patching + nvdisasm**: self-test 7/7, plus randomized battery of 300 patched encodings decoded 100%.

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000404240949` | `0x000fea0003800000` | `@P0 BRX R4 0x490` |
| `0xfffffffc04fc0949` | `0x000fea0003800000` | `@P0 BRX R4 0xfffffffff0` (off = -16) |
| `0x0000000006400949` | `0x000fea0001800000` | `@P0 BRX P3, R6 0x100` (Pp=P3) |
| `0x0000000006400949` | `0x000fea0003a00000` | `@P0 BRX.INC R6 0x100` (depth) |

## Open questions
- Exact runtime target formula (`Ra + off` absolute vs. relative-to-anchor) since `Ra` is a runtime value.
- Real-world jump-table idiom is unobserved because ptxas never emitted these in the sampled code.
