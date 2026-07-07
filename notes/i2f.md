# I2F — Integer to Float

**Opcode mnemonic:** I2F  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

## Semantics

Converts an integer to a floating-point value: `Rd = (float)Rb` (or `(double)Rb` for Float64 dest). Supports source widths 8b/16b/32b/64b (signed and unsigned) and destination formats F32/F16/BF16/Float64. Five source types: register, immediate, constant bank, extended constant, uniform register.

## Variant overview (40 total)

Matrix: {F32, Float64} dst × {8b, 16b, 32b, 64b} src × {Rb, IS, IU, Cb, CX, UR}

| Dst | Src width | Rb opcode | Key |
|-----|-----------|-----------|-----|
| F32 | 8/16/32b | `0x306` | Most common pattern |
| F32 | 64b | `0x312` | Long→float |
| F64 | 8/16/32/64b | `0x312` | All use 0x312 base |

## Bit layout (F32/S32 Rb — opcode 0x306)

```
[79:78]              stride   <= rnd (RN=0, RZ=1, etc.)
[77:75]              sz       <= dstfmt (F32=0)
[39:32]              Rb       <= Rb
[23:16]              Rd       <= Rd
[115:113]            src_rel_sb <= VarLatOperandEnc(src_rel_sb)
[112:110]            dst_wr_sb  <= VarLatOperandEnc(dst_wr_sb)
[91:91],[11:0]       opcode    <= 0b1100000110
```

## Empirical status

**Not emitted by ptxas on sm_90.** Modern compilers use `I2FP` (int_pipe, packed format) instead:

```
(float)int_val  →  I2FP.F32.S32 Rd, Rb    (int_pipe)
```

I2F is the legacy mio_pipe/MUFU version. The I2FP variant (idx 197 in ref_memo) is documented separately.

## Latency

`mio_pipe`, MUFU dispatch. Decoupled scoreboard with variable-latency encoding.
