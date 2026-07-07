# I2FP — Integer to Float, Packed

**Opcode mnemonic:** I2FP  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Converts an integer to a 32-bit floating-point value on the integer pipeline: `Rd = (float)Rb`. This is the **modern replacement for I2F** — ptxas on sm_90 exclusively emits I2FP for `(float)int_val` and `cvt.f32.u32` PTX operations.

Destination format is always F32 (packing not relevant for single conversion). Source format can be U32 or S32. Rounding mode is RN (round-to-nearest) or RZ (round-to-zero).

## Why int_pipe instead of mio_pipe?

I2FP dispatches to the **integer pipeline** with coupled scoreboard, avoiding the MUFU dispatch latency of the legacy I2F (mio_pipe). This is a Hopper-era optimization — integer-to-float conversion is common enough to warrant a dedicated int_pipe instruction rather than dispatching to the multi-function unit.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `i2fp__RRR` | `0x245` | `I2FP.F32.S32 Rd, Rb` |
| `i2fp__RuIR` | `0x845` | `I2FP.F32.U32 Rd, imm32` |
| `i2fp__RsIR` | `0x845` | `I2FP.F32.S32 Rd, imm32` |
| `i2fp__RCR` | `0xa45` | `I2FP.F32.S32 Rd, c[bank][offset]` |
| `i2fp__RCxR` | `0x1a45` | `I2FP.F32.S32 Rd, c[URb][offset]` |
| `i2fp__RUR` | `0x1c45` | `I2FP.F32.S32 Rd, URb` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| srcfmt | srcfmt | [85:84],[74] | 4=U32, 5=S32 |
| dstfmt | sz | [77:75] | 2=F32 |
| rnd | stride | [79:78] | 0=RN, 3=RZ |

## Bit layout (RRR — opcode 0x245)

```
[85:84],[74]        srcfmt   <= srcfmt (U32=4, S32=5)
[79:78]             stride   <= rnd (RN=0, RZ=3)
[77:75]             sz       <= dstfmt (F32=2)
[39:32]             Rb       <= Rb
[23:16]             Rd       <= Rd
[91:91],[11:0]      opcode   <= 0b1001000101
```

## Verified encodings

From `(float)int_val` compilation (sm_90, CUDA 13.1):

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000200077245` | `0x004fca0000201400` | `I2FP.F32.S32 R7, R2` |

## Cross-comparison

| Property | I2F | I2FP | I2IP |
|----------|-----|------|------|
| Pipe | `mio_pipe` | `int_pipe` | `int_pipe` |
| Scoreboard | Decoupled (VarLat) | Coupled | Coupled |
| pTxas emits? | No | **Yes** | — |
| Destination | F32/F16/F64 | F32 only | Packed narrower int |

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. Coupled scoreboard, standard integer-pipe latency (1 cycle typical). Significantly lower latency than the legacy mio_pipe I2F.
