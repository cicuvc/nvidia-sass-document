# SEL — Register Select

**Opcode mnemonic:** SEL  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Conditional select between two sources controlled by a predicate: `Rd = Pp ? Ra : Rb` (or `Rd = Pp ? Ra : imm32` / etc.). Equivalent to the PTX `selp` instruction.

Unlike USEL (uniform register select), SEL operates on **regular** GPRs and has a **regular** predicate `Pp` (not `UPp`). The source can be a register, 32-bit immediate, constant memory, or uniform register.

## Variant overview

| Variant | Opcode | Format |
|---------|--------|--------|
| `sel__RRR_RRR` | `0x207` | `SEL Rd, Ra, Rb, [!]Pp` |
| `sel__RuIR_RIR` | `0x807` | `SEL Rd, Ra, imm32, [!]Pp` |
| `sel__RCR_RCR` | `0xa07` | `SEL Rd, Ra, c[bank][offset], [!]Pp` |
| `sel__RCxR_RCxR` | `0x1a07` | `SEL Rd, Ra, c[URb][offset], [!]Pp` |
| `sel__RUR_RUR` | `0x1c07` | `SEL Rd, Ra, URb, [!]Pp` |

## Bit layout (RRR — opcode 0x207)

```
[90:90]              input_reg_sz_32_dist <= Pp@not
[89:87]              Pnz                  <= Pp (3-bit predicate)
[39:32]              Rb                   <= Rb (8-bit register)
[31:24]              Ra                   <= Ra (8-bit register)
[23:16]              Rd                   <= Rd (8-bit register)
[15:15]              Pg_not               <= Pg@not
[14:12]              Pg                   <= Pg
[91:91],[11:0]       opcode               <= 0b1000000111
```

RI variant: Rb replaced with 32-bit immediate at [63:32].

## Cross-comparison

| Property | SEL | USEL |
|----------|-----|------|
| Pipe | `int_pipe` | `udp_pipe` |
| Dest | `Rd` (GPR) | `URd` (uniform register) |
| Select predicate | `Pp` (regular) | `UPp` (uniform) |
| Guard predicate | `Pg` (regular) | `UPg` (uniform) |
| Opcode base | `0x207` | `0x1287` |

SEL is the GPR counterpart of USEL. Compilers use both: SEL for regular control flow, USEL for uniform address computation.

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. `FXU_OPS` group: output 1 cycle typical.
