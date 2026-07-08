# Integer Division — software synthesis on sm_90

**No hardware integer divider.** `div.u32` / `div.s32` are synthesized by ptxas
into a ~40-instruction Newton-Raphson reciprocal sequence.

## Algorithm

1. Recip computed via float: `rcp ≈ 1.0 / float(b)`
2. Quotient approximate: `q0 = int(a * rcp)`
3. Multiply-high correction: `q = IMAD.HI_U32(q0, b, carry)`
4. Remainder check + sign correction + divide-by-zero guard

## Core instructions used

| Step | SASS | Purpose |
|------|------|---------|
| | `IABS R0, Rb` | |b| for sign handling |
| | `I2F.RP R11, R0` | int → float (round positive) |
| | `MUFU.RCP R11, R11` | 1/x reciprocal approx |
| | `F2I.FTZ.U32.TRUNC.NTZ R9, R8` | float → int (trunc) |
| | `IMAD.HI.U32 R9, R9, R13, R8` | multiply-high for quotient correction |
| | `IMAD R7, R0, R11, R10` | a * rcp(b) for remainder |
| | `ISETP.GT.U32 P4, PT, R0, R7, PT` | remainder > divisor? |
| | `LOP3.LUT ..., 0x33/0x3c, !PT` | sign/zero merge |
| | `@!P4 IADD3 R7, R7, -R0, RZ` | remainder -= divisor |
| | `@!P4 IADD3 R8, R8, 0x1, RZ` | quotient += 1 |

## Both u32 and s32 use same core

`div.u32` and `div.s32` share the same underlying sequence. The signed variant
adds `IABS` (absolute value), `LOP3` for sign reconstruction, and `ISETP.NE`
for the negative divisor branch.

## Related instructions

- `MUFU.RCP` — reciprocal approximation (mio_pipe)
- `I2F.RP` / `F2I` — int-float conversion
- `IMAD.HI.U32` — 32×32→64 multiply, return upper 32 bits
- `VIADD` / `IADD3` — fast integer add/sub
- `IABS` — integer absolute value
- `LOP3.LUT` — logical operation with LUT
