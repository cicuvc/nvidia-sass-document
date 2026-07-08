# F2F — Float to Float Conversion

**Opcode mnemonic:** F2F  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

## Semantics

Converts between floating-point formats: F32 ↔ F16, BF16, E8M7, E6M9, and F64 ↔ narrower formats. Two direction families:

- **Downconvert:** F32 → narrower (F16, BF16, E8M7, E6M9)
- **Upconvert:** narrower → F32 or F64
- **F64 ops:** F64 ↔ narrower (F16, F32, BF16)

Modifiers include FTZ (flush-to-zero), rounding mode (RN via Round1), and `[-]`/`[||]` on the source operand. The "swap" ALT variants handle byte-endianness reversal for the source format.

## Variant overview (40 total)

Grouped by: {downconvert, upconvert} × {F32, F64} × {RRR, RIR, RCR, RCxR, RUR}

| Family | Base opcode (RRR) | Source types |
|--------|-------------------|--------------|
| F32 downconvert | `0x304` | RRR, RIR, RCR, RCxR, RUR |
| F32 upconvert | `0x304` | (same, plus swap ALTs) |
| F64 downconvert | `0x310` | RRR, RIR, RCR, RCxR, RUR |
| F64 upconvert | `0x310` | (same, plus swap ALTs) |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| ftz | — | — | noftz=0, .FTZ |
| dstfmt.srcfmt | sz | [77:75] | Combined dst+src format selector |
| rnd | stride | [79:78] | RN=0, RZ, etc. |
| Rb negate | Sb_invert | [63] | 1=`[-]` |
| Rb absolute | Sc_absolute | [62] | 1=`[||]` |

## Bit layout (F32 downconvert RRR — opcode 0x304)

```
[79:78]              stride   <= rnd
[77:75]              sz       <= dstfmt.srcfmt
[63:63]              Sb_invert <= Rb@negate
[62:62]              Sc_absolute <= Rb@absolute
[39:32]              Rb       <= Rb
[23:16]              Rd       <= Rd
[115:113]            src_rel_sb <= VarLatOperandEnc(src_rel_sb)
[112:110]            dst_wr_sb  <= VarLatOperandEnc(dst_wr_sb)
[91:91],[11:0]       opcode    <= 0b1100000100
```

## Empirical status

**Not emitted by pTxas on sm_90.** Modern compilers use `F2FP` (int_pipe) for float-to-float conversion instead of this mio_pipe variant. F2F is the legacy MUFU-dispatched version.

## Latency

`mio_pipe`, MUFU dispatch. Decoupled scoreboard with variable-latency encoding. Higher latency than the int_pipe F2FP equivalent.
