# FMNMX — FP32 Min/Max

**Opcode mnemonic:** `FMNMX`  
**Pipe:** `int_pipe` (integer execution pipe — not fmalighter_pipe!)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd = MIN(MAX)(Ra, Rb)` — two-operand floating-point min/max on 32-bit floats,
with a predicate output `Pp` that captures the comparison result (which operand
was selected).

The min/max sense is selected by the `Pp@not` bit:
- `Pp@not=1` (`!PT` in disasm) → **MAX**: `Rd = (Ra >= Rb) ? Ra : Rb`
- `Pp@not=0` (`PT` in disasm) → **MIN**: `Rd = (Ra >= Rb) ? Rb : Ra`

The `Pp` output predicate records whether Ra was selected (Pp=true) or Rb was
selected (Pp=false). When Pp=PT (7), this output is discarded.

## Variant overview — 5 base + 5 `_pred` = 10 variants

### Base variants (isA=0, no Pu input)

| Variant | Opcode (13b) | Operand B |
|---------|:-----------:|-----------|
| `fmnmx__RRR_RRR` | 0x209 | Register |
| `fmnmx__RIR_RIR` | 0x809 | F32Imm |
| `fmnmx__RCR_RCR` | 0xa09 | Const bank |
| `fmnmx__RCxR_RCxR` | 0x1a09 | Const bank + UR |
| `fmnmx__RUR_RUR` | 0x1c09 | UniformRegister |

### Pred variants (isA=1, Pu predicate input)

Same opcodes, but format changes to `FMNMX Rd, Pu, Ra, Rb, Pp` where `Pu` is
an input predicate selector. The `isA` bit at [65] discriminates base(0) vs pred(1).

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **ftz** | [80] | `noftz`(0), `FTZ`(1) |
| **nan** | [81] | `nonan`(0), `NAN`(1) — NaN propagation |
| **xorsign** | [82] | `noxorsign`(0), `XORSIGN`(1) — XOR sign bits |
| **isA** (pred mode) | [65] | 0=base, 1=pred variant |
| **Pu** (pred input) | [68:66] | Predicate, only valid when isA=1 |

`.FTZ`, `.NAN`, `.XORSIGN` appear as suffixes in disassembly.

## Bit layout (RRR_RRR base, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 92: 91]               -- gap --
[91],[11:0]             opcode       (13b)
[90]                    Pp.not       (1b: min/max selector)
[89:87]                 Pp           (3b: output predicate, 7=PT=discard)
[86:83]                 -- gap --
[82]                    xorsign      (1b)
[81]                    nan          (1b)
[80]                    ftz          (1b)
[79:74]                 -- gap --
[73]                    Ra.absolute
[72]                    Ra.negate
[71:69]                 -- gap --
[68:66]                 Pu           (3b: pred input, only when isA=1)
[65]                    isA          (1b: 0=base, 1=pred)
[64]                    -- gap --
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

- **RIR**: Sb F32Imm in [63:32]; no Rb register
- **RUR**: URb in [37:32] (6-bit); URb negate/abs in [63:62]
- **Pred**: `isA=1`, Pu at [68:66], adds `Pp` input operand

## Unique: runs on `int_pipe`

FMNMX is on the **integer** pipe, unlike FADD/FMUL/FFMA which all run on
`fmalighter_pipe`. This means it shares execution resources with integer
arithmetic (IADD3, IMAD, LOP3, etc.), not the FP pipeline.

## Latency (from sm_90_latencies.txt)

FMNMX belongs to `FXU_OPS` on `int_pipe`:

| Dependency | Pipe group × operand role | Cycles |
|-----------|--------------------------|:------:|
| TABLE_TRUE | `FXU_OPS`{Rd} | 6–8 |
| TABLE_OUTPUT | `FXU_OPS`{Rd} | 1–2 |
| TABLE_ANTI | `FXU_OPS`{Ra,Rb} | 1–2 |

## Verified encodings (cuobjdump, sm_90)

10/10 matches. Test kernel: `tests/fmnmx_test.cu`; decoder: `tools/decode_fmnmx.py`.

| Source | Lo64 / Hi64 | Disassembly |
|--------|------------|-------------|
| kernel | `0x0000000504057209` / `0x001fc60007800000` | FMNMX R5, R4, R5, !PT (fmaxf→MAX) |
| kernel | `0x0000000504057209` / `0x001fc60003800000` | FMNMX R5, R4, R5, PT (fminf→MIN) |
| kernel | `0x0000000504057209` / `0x001fc60007810000` | FMNMX.FTZ R5, R4, R5, !PT |
| kernel | `0x0000000504057209` / `0x001fc60007820000` | FMNMX.NAN R5, R4, R5, !PT |
| kernel | `0x437f000005057809` / `0x001fc60007800000` | FMNMX R5, R5, 255, !PT (RIR) |
| kernel | `0x00000006ff057c09` / `0x000fe2000b800000` | FMNMX R5, RZ, UR6, PT (RUR) |
| cublas | `0x437f00000000e809` / `0x000fc80003800000` | @!P6 FMNMX R0, R0, 255, PT |
| cublas | `0x00000000ff00e209` / `0x000fc80007800000` | @!P6 FMNMX R0, RZ, R0, !PT |
| cublas | `0x437f00000606d809` / `0x000fe20003800000` | @!P5 FMNMX R6, R6, 255, PT |
| cublas | `0x00000006ff06d209` / `0x000fe40007800000` | @!P5 FMNMX R6, RZ, R6, !PT |

### PTX→SASS mapping

| PTX | SASS |
|-----|------|
| `max.f32 d, a, b` | `FMNMX d, a, b, !PT` |
| `min.f32 d, a, b` | `FMNMX d, a, b, PT` |
| `max.ftz.f32 d, a, b` | `FMNMX.FTZ d, a, b, !PT` |
| `min.ftz.f32 d, a, b` | `FMNMX.FTZ d, a, b, PT` |
| `max.NaN.f32 d, a, b` | `FMNMX.NAN d, a, b, !PT` |
| `min.NaN.f32 d, a, b` | `FMNMX.NAN d, a, b, PT` |

### Common compiler pattern: clamp via min+max pair

Found in cublas:
```
FMNMX R0, R0, 255, PT    ; Rd = min(R0, 255) — clamp upper bound
FMNMX R0, RZ, R0, !PT    ; Rd = max(RZ, R0) — ReLU (clamp lower to 0)
```

This implements `clamp(R0, 0, 255)` → ReLU then saturation.

## Open questions

- `_pred` variants (isA=1 with Pu predicate input) not yet triggered in any test
- `.XORSIGN` modifier not yet tested — needs PTX `max.xorsign.abs.f32`
- Const-bank variants (RCR, RCxR) not yet verified
- 3-input `max.f32 d, a, b, c` — does this map to `_pred` or get lowered differently?
