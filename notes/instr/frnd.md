# FRND — Float Round (MUFU)

**Opcode mnemonic:** FRND  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

## Semantics

Rounds a floating-point value to the nearest integer within the same floating-point format: `Rd = round(Rb, rnd_mode)`. Dispatched through the MUFU (multi-function unit) pipeline. Supports four formats: F16, F32, F64, and BF16.

Rounding mode is Round3 (ROUND = round-to-nearest-even by default, other modes selectable via the 2-bit field). The `[-]` and `[||]` modifiers on the source operand apply negation/absolute before rounding. FTZ controls flush-to-zero behavior for denormal inputs.

The "swap" ALT variants handle byte-endianness reversal.

## Variants (40 total)

Matrix: {F16, F32, F64, BF16} × {R, I, C, CXb, URb} × {normal, swap ALT}

| Format | Base opcode (Register) |
|--------|------------------------|
| F16 | `0x307` |
| F32 | `0x307` |
| F64 | `0x313` |
| BF16 | `0x307` |

F64 uses opcode 0x313 (others use 0x307). Swap ALTs share the same base opcodes with different fmt bits.

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| fmt | dstfmt.srcfmt | [86:84],[77:75] | Encodes (F16/F32/F64/BF16) |
| rnd | stride | [79:78] | Round3: ROUND, RZ, etc. |
| ftz | UPq_not | [80] | 0=noftz, 1=.FTZ |
| Rb negate | Sb_invert | [63] | 1=`[-]` |
| Rb absolute | Sc_absolute | [62] | 1=`[||]` |

## Bit layout (F32 Register — opcode 0x307)

```
[86:84],[77:75]     dstfmt.srcfmt <= fmt (F32 encoding)
[80:80]             UPq_not       <= ftz
[79:78]             stride        <= rnd (Round3)
[63:63]             Sb_invert     <= Rb@negate
[62:62]             Sc_absolute   <= Rb@absolute
[39:32]             Rb            <= Rb
[23:16]             Rd            <= Rd
[115:113]           src_rel_sb    <= VarLatOperandEnc(src_rel_sb)
[112:110]           dst_wr_sb     <= VarLatOperandEnc(dst_wr_sb)
[91:91],[11:0]      opcode        <= 0b1100000111
```

## Key features

- **mio_pipe**, **VQ_MUFU** dispatch — dispatched alongside other transcendental ops (RCP, RSQ, SIN, COS)
- **Decoupled scoreboard** with variable-latency encoding (`VarLatOperandEnc()`)
- 4 float formats, 5 source types, swap variants for endianness

## Latency

`mio_pipe`, MUFU dispatch. Higher latency than int_pipe ops. Variable latency encoded in scoreboard fields.

## Open questions

- Does ptxas emit FRND or does it prefer an int_pipe/udp_pipe alternative (like RRO or MUFU)?
- The Round3 encoding values map to which specific IEEE 754 rounding modes?
