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

## Resolved: target = next_pc + Ra + off — Ra is a KERNEL-RELATIVE offset (SM120)

Empirically verified (`tests/asm_construct/test_brx.py`): `BRX Ra, off` branches
to **`next_pc + (sign-extended Ra:R(a+1)) + off*4`** — the register holds a
**signed byte offset relative to the next instruction**, NOT an absolute target:

```
BRX R4, #label(x)   with R4 =  0 -> lands on x (assembler fills off=(x-next_pc)/4)
                      R4 = 0x10 -> lands at x+0x10
                      R4 = 0x20 -> lands at x+0x20
```
A huge/absolute `Ra` (e.g. TRAP_RETURN_PC = an absolute address) makes
`target = next_pc + huge` → out of range → ILLEGAL_ADDRESS / INVALID_PC,
confirming Ra is not an absolute target. This is why libcusparse sign-extends
the 32-bit jump-table entry with `SHF.R.S32.HI R5, RZ, 0x1f, R4` before `BRX
R4 -0x110`: the table entries are kernel-relative offsets and BRX adds them to
the next-PC base plus the encoded offset.
