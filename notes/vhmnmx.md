# VHMNMX — Vector Half Min/Max

**Opcode mnemonic:** VHMNMX  |  **Pipe:** `fp16_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Vector half-precision min/max on packed 2-element FP16 vectors: `Rd.16x2 = minmax(Ra.16x2, Rb.16x2, Rc.16x2)`. Operates on two FP16 (or BF16, E6M9) values packed in a single 32-bit register.

The `ofmt` field selects the format: F16_V2, BF16_V2, or E6M9_V2. Each format represents two elements packed in 32 bits. Swizzle controls (`iswzA`, `iswzB`, `iswzC`) select which element from each source contributes to the comparison.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `vhmnmx__RRR` | `0x247` | `VHMNMX.F16_V2 Rd, Ra, Rb, Rc, Pp` |
| `vhmnmx__RIR` | `0x847` | `VHMNMX.F16_V2 Rd, Ra, imm32, Rc, Pp` |
| `vhmnmx__RCR` | `0xa47` | `VHMNMX.F16_V2 Rd, Ra, c[bank][offset], Rc, Pp` |
| `vhmnmx__RCxR` | `0x1a47` | `VHMNMX.F16_V2 Rd, Ra, c[URb][offset], Rc, Pp` |
| `vhmnmx__RUR` | `0x1c47` | `VHMNMX.F16_V2 Rd, Ra, URb, Rc, Pp` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| ofmt | ofmt | [85],[78] | 0=F16_V2, 2=BF16_V2, 3=E6M9_V2 |
| ftz | UPq_not | [80] | 0=noftz, 1=.FTZ |
| nan | loc | [81] | 0=nonan, 1=.NAN |
| xorsign | fc | [82] | XOR sign mode |
| iswzA | bop | [75:74] | Swizzle selector for Ra |
| iswzB | hsel | [61:60] | Swizzle selector for Rb |
| iswzC | insert | [77:76] | Swizzle selector for Rc |
| Ra neg/abs | sz,e | [73],[72] | `[-]`, `[||]` |
| Rb neg/abs | Sb_invert, Sc_abs | [63],[62] | `[-]`, `[||]` |
| Rc neg/abs | OR, clear | [84],[83] | `[-]`, `[||]` |

## Bit layout (RRR — opcode 0x247)

```
[90:90]              input_reg_sz <= Pp@not
[89:87]              Pnz          <= Pp
[85],[78]            ofmt         <= OFMT (F16/BF16/E6M9)
[84]                 OR           <= Rc@negate
[83]                 clear        <= Rc@absolute
[82]                 fc           <= xorsign
[81]                 loc          <= nan
[80]                 UPq_not      <= ftz
[77:76]              insert       <= iswzC
[75:74]              bop          <= iswzA
[73]                 sz           <= Ra@absolute
[72]                 e            <= Ra@negate
[71:64]              Rc           <= Rc
[63]                 Sb_invert    <= Rb@negate
[62]                 Sc_absolute  <= Rb@absolute
[61:60]              hsel         <= iswzB
[39:32]              Rb           <= Rb
[31:24]              Ra           <= Ra
[23:16]              Rd           <= Rd
[91:91],[11:0]       opcode       <= 0b1001000111
```

## Cross-comparison

| Property | FMNMX | VHMNMX | VIMNMX |
|----------|-------|--------|--------|
| Pipe | `fe_pipe` | `fp16_pipe` | `int_pipe` |
| Format | 32-bit FP | 16-bit FP ×2 | 32-bit integer |
| Operands | 2 (Ra, Rb) | 3 (Ra, Rb, Rc) | 2 (Ra, Rb) |
| Packed | No | Yes (2×16) | Yes (16×2 for VIADD) |
| Swizzle | No | Yes (iswz ABC) | No |

## Latency

`fp16_pipe`, `INST_TYPE_COUPLED_MATH`. Coupled scoreboard. FP16 pipeline latency.
