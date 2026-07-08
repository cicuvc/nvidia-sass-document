# FMUL — FP32 Multiply

**Opcode mnemonic:** `FMUL`  
**Pipe:** `fmalighter_pipe` (= `FMAI_OPS`)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd = Ra * Rb` — two-operand floating-point multiply on 32-bit floats.

No C operand (`ISRC_C_SIZE = 0`). Ra supports optional **negate** (`-`) and
**absolute** (`||`); Rb supports the same via sign-control bits.

## Variant overview — 5 encoding variants

| Variant | Opcode (13b) | Operand B | B size |
|---------|:-----------:|-----------|:------:|
| `fmul__RRR_RR` | 0x220 | Register | 32 |
| `fmul__RIR_RI` | 0x820 | F32Imm | 32 |
| `fmul__RCR_RC` | 0xa20 | Const bank | 32 |
| `fmul__RCxR_RCx` | 0x1a20 | Const bank + UR | 64 |
| `fmul__RUR_RU` | 0x1c20 | UniformRegister | 32 |

Note: no RRU or RRI variants (B is the second operand, unlike FADD where C is
second). Uniform is B-side → RUR.

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **fmz** | [80],[76] | `nofmz_hfma2`(0), `FMZ`(1), `FTZ`(2), `INVALID3`(3) |
| **scale** | [86:84] | `noscale`(4), `D2`(3), `D4`(2), `D8`(1), `M2`(5), `M4`(6), `M8`(7), `INVALID0`(0) |
| **rnd** (rounding) | [79:78] | `RN`(0), `RM`(1), `RP`(2), `RZ`(3) |
| **sat** (saturation) | [77] | `nosat`(0), `SAT`(1) |

`.RM`, `.RP`, `.RZ`, `.SAT`, `.FMZ`, `.FTZ` appear as suffixes in disassembly.

`.scale` is a **3-bit field** unique to FMUL (not present in FADD or FFMA). The `D*`
values represent division scaling (÷2, ÷4, ÷8); `M*` values represent multiply
scaling (×2, ×4, ×8). Default is `noscale`(=4).

## Bit layout (RRR_RR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 92: 87]               -- gap --
[86:84]                 scale        (3b)   ← FMUL-specific
[83:81]                 -- gap --
[80],[76]               fmz          (2b)
[79:78]                 stride       (2b: rounding)
[77]                    ntz          (1b: sat)
[75:74]                 -- gap --
[73]                    Ra.absolute
[72]                    Ra.negate
[71:40]                 -- gap --
[63]                    Rb.negate
[62]                    Rb.absolute
[61:40]                 -- gap --
[39:32]                 Rb           (8b)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not
[14:12]                 Pg           (3b: predicate, 7=PT)
```

### Variant differences

- **RIR** (imm Sb): Sb F32Imm in [63:32]; no Rb register field
- **RUR** (URb): URb in [37:32] (6-bit uniform reg); URb negate/abs in [63:62]
- **RCR/RCxR**: C operand at [63:32] with bank/offset encoding

## Cross-comparison: FADD vs FMUL

| Aspect | FADD | FMUL |
|--------|------|------|
| Semantics | `Rd = Ra + Rc` | `Rd = Ra * Rb` |
| Opcodes | 0x221, 0x421, 0x621, 0x1621, 0x1e21 | 0x220, 0x820, 0xa20, 0x1a20, 0x1c20 |
| Format suffix | `_RR`, `_RI`, `_RC`... | `_RR`, `_RI` (RIR), `_RC`... |
| Uniform variant | RRU (U in C pos) | RUR (U in B pos) |
| ftz/fmz | 1-bit ftz [80] | 2-bit fmz [80],[76] |
| Scale field | none | 3-bit [86:84] |
| Imm field name | Sc (RRI) | Sb (RIR) |

Both share the same bit layout pattern: Ra at [31:24], 2nd operand at [39:32],
Rd at [23:16], negate/abs for Ra at [73:72], negate/abs for 2nd operand at [63:62].

## Latency (from sm_90_latencies.txt)

FMUL belongs to `FMAI_OPS` (= `fmalighter_pipe`). Same latency class as FADD/FFMA:
4–8 cycles true dependency, 1–2 cycles output/anti.

## Verified encodings (cuobjdump, sm_90)

10/10 matches. Test kernel: `tests/fmul_test.cu`; decoder: `tools/decode_fmul.py`.

| Source | Lo64 / Hi64 | Disassembly |
|--------|------------|-------------|
| kernel | `0x4040000005057820` / `0x001fc60000400000` | FMUL R5, R5, 3 (RIR) |
| kernel | `0x0000000504057220` / `0x001fca000040c000` | FMUL.RZ R5, R4, R5 |
| kernel | `0x0000000504057220` / `0x001fe40000404000` | FMUL.RM R5, R4, R5 |
| kernel | `0x0000000504057220` / `0x001fc60000408000` | FMUL.RP R5, R4, R5 |
| kernel | `0x0000000504057220` / `0x001fe40000400000` | FMUL R5, R4, R5 (plain) |
| kernel | `0x00000006ff057c20` / `0x000fc60008400000` | FMUL R5, RZ, UR6 (RUR) |
| kernel | `0x0000000504057220` / `0x001fe40000410000` | FMUL.FTZ R5, R4, R5 |
| kernel | `0x0000000504057220` / `0x001fe40000402000` | FMUL.SAT R5, R4, R5 |
| cublas | `0x00000013101c0220` / `0x002fe20000400000` | @P0 FMUL R28, R16, R19 |
| cublas | `0x000000131c1c1220` / `0x001fca0000400000` | @P1 FMUL R28, R28, R19 |

Key compiler observations:
- `fmul_rr_negate` (`-a * b`) was lowered to `FFMA -Ra, Rb, -RZ` — compiler
  preferred FFMA over FMUL for the negated case
- `fmul_rr_double_negate` (`-a * -b`) collapsed to plain FMUL (cancelled)
- `fmul_rz` (`a * 0.0f`) → optimized to `FMUL RZ, UR6` (RUR, dead code avoided)
- PTX `mul.rz.f32` / `mul.rm.f32` / `mul.rp.f32` / `mul.sat.f32` / `mul.ftz.f32`
  all map directly to FMUL with corresponding suffix

## Open questions

- `.scale` modifier: what PTX construct triggers D2/D4/D8/M2/M4/M8? Not yet tested
- Const-bank variants (`fmul__RCR_RC`, `fmul__RCxR_RCx`) not yet verified
- `FMUL32I` (pipe-only alias) relationship to FMUL not explored
