# ULEA — Uniform Load Effective Address

**Opcode mnemonic:** ULEA  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Computes a uniform-register effective address: `URd = URa + URb + URc + scale*imm` (or `URd = URa + URb * scale + URc + imm` for the imm variant). The result is a 32-bit integer written to a uniform register. Used for computing base+offset addresses for subsequent uniform memory operations.

There are two primary forms:
- **Noimm (URURUR):** pure register arithmetic — `URd = URa + URb + URc` with optional scale
- **Imm (RRI/URIR/URIUR):** register + immediate — `URd = URa + URb + imm` with optional scale

Modifiers control:
- `.HI` / `.LO` — which 32-bit word of a 64-bit result to compute (HI=upper, LO=lower)
- `.X` — extended form with an additional predicate operand (UPp)
- `.SX32` — sign-extend a 32-bit operand

The `[-]` (negate) flag is available on source operands in the noimm form, and `[~]` (invert) in the `.X` form.

## Variant overview

There are **14 variants** grouped by format family:

| Family | Opcode | Pattern | Empirically observed |
|--------|--------|---------|---------------------|
| Noimm | `0x1291` | `URd, UPu, URa, URb, URc, scale` | Yes — `ULEA UR6, UR7, UR6, 0x18` |
| Noimm (UPu≠UPT) | `0x1291` | explicit UPu operand | Yes — `ULEA UR8, UP0, UR4, UR5, 0x7` |
| Noimm `.X` | `0x1291` | adds UPp, `[~]` on sources | Not observed |
| Noimm `.SX32` | `0x1291` | sz bit set, URc=URZ | Not observed |
| Noimm `.X.SX32` | `0x1291` | X + SX32 bits set | Not observed |
| HI_imm (RRI) | `0x1491` | `URd, UPu, URa, URb, imm, scale` | Not observed |
| Imm default (URIUR) | `0x1891` | `URd, URa, imm, scale` | Yes — `ULEA UR6, UR6, 0x400, 0x18` |
| Imm `.HI.X.SX32` (URIUR) | `0x1891` | all bits set + UPp | Yes — `ULEA.HI.X.SX32 UR7, UR7, 0xffffffff, 0x1, UP0` |
| LO variants | `0x1291`/`0x1891` | spec: hilo=0 | Not observed |

## Modifiers

| Modifier | Bit | Field | Values |
|----------|-----|-------|--------|
| HI | [80] | UPq_not / hilo | 1=HI, 0=LO (or implicit HI for noimm) |
| X | [74] | sh | 1=`.X` (extended with UPp) |
| SX32 | [73] | sz | 1=`.SX32` |
| URa negate | [72] | e | 1=`[-]` (noimm) / `[~]` (.X form) |
| URb negate | [63] | Sb_invert | 1=`[-]` (noimm) / `[~]` (.X form) |
| scale | [79:75] | scaleU5 | 0–31 |
| UPu predicate | [83:81] | Pu | UniformPredicate (elided when UPT) |
| UPp predicate | [89:87] | Pnz | UniformPredicate for .X forms |
| UPp not | [90] | input_reg_sz_32_dist | 1=`!UPp` |

Scale encoding: `scaleU5` is a 5-bit value for address arithmetic scaling.

## Bit layout

### Noimm (URURUR) — opcode 0x1291

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[115:113]            src_rel_sb           <= *7
[112:110]            dst_wr_sb            <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode               <= 0b1001010010001
[90:90]              input_reg_sz_32_dist <= UPp@not (.X) / *1 (base)
[89:87]              Pnz                  <= UPp (.X) / *7 (base)
[83:81]              Pu                   <= UPu
[80:80]              UPq_not              <= *hilo (pinned)
[79:75]              scaleU5              <= scaleU5
[74:74]              sh                   <= 0 / *X (1)
[73:73]              sz                   <= 0 / *sx32 (1)
[72:72]              e                    <= URa@negate
[69:64]              Ra_URc               <= URc / *63 (.SX32)
[63:63]              Sb_invert            <= URb@negate
[37:32]              Ra_URb               <= URb
[29:24]              Sa                   <= URa
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
```

### Imm (URIUR) — opcode 0x1891

All empirically observed immediate-form ULEA instructions use this opcode. The 0x1491 (RRI) variant exists in the spec but has not been observed in ptxas output.

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[115:113]            src_rel_sb           <= *7
[112:110]            dst_wr_sb            <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode               <= 0b1100010010001
[90:90]              input_reg_sz_32_dist <= UPp@not (.X) / *1 (base)
[89:87]              Pnz                  <= UPp (.X) / *7 (base)
[83:81]              Pu                   <= UPu
[80:80]              UPq_not              <= hilo
[79:75]              scaleU5              <= scaleU5
[74:74]              sh                   <= 0 / *X (1)
[73:73]              sz                   <= 0 / *sx32 (1)
[72:72]              e                    <= URa@negate
[69:64]              Ra_URc               <= *63
[63:32]              Ra_offset            <= Sb (imm32)
[29:24]              Sa                   <= URa
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
```

## Latency

ULEA is in `udp_pipe`. In the UGPR latency tables it falls under the `UDP_subset` group (since it is not in ULDC_VOTEU_UMOV_ULEPC or R2UR_S2UR):

```
TABLE_TRUE(UGPR):
  UDP_subset:{URa @URaRange, ...} : {URd @URdRange, URd2 @URd2Range} : 4 12 12 8 12 7 9 12 12 10 9

TABLE_OUTPUT(UGPR):
  UDP_subset:{URd @URdRange, URd2 @URd2Range} : 1 4 7 7

TABLE_ANTI(UGPR):
  UDP_subset:{...} : 1 1 1 3
```

Output latency: **1–7 cycles**. True-dependency from uniform register source: **4–12 cycles** (heavily dependent on operand role and size). Anti-dependency: **1–3 cycles**.

## Verified encodings

### From libcublas (sm_90, CUDA 13.1)

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000607067291` | `0x001fe2000f8ec03f` | `ULEA UR6, UR7, UR6, 0x18` |
| `0x0000000406077291` | ..., URc=UR4, scale=0x7 | `ULEA UR6, UR7, UR4, 0x7` |
| `0x0000000408097291` | ... | `ULEA UR9, UR8, UR4, 0x7` |
| `0x000000040c0d7291` | ..., scale=0x8 | `ULEA UR13, UR12, UR4, 0x8` |
| `0x0000040006067891` | `0x002fe2000f8ec03f` | `ULEA UR6, UR6, 0x400, 0x18` |
| `0x000004000d0d7891` | `0x002fe2000f8ec03f` | `ULEA UR13, UR13, 0x400, 0x18` |
| `0xffffffff07077891` | `0x000fe200080f0e3f` | `ULEA.HI.X.SX32 UR7, UR7, 0xffffffff, 0x1, UP0` |
| `0xffffffff06067891` | `0x000fe200080f0e3f` | `ULEA.HI.X.SX32 UR6, UR6, 0xffffffff, 0x1, UP0` |
| `0xffffffff08087891` | `0x000fe200080f0e3f` | `ULEA.HI.X.SX32 UR8, UR8, 0xffffffff, 0x1, UP0` |

### PTX→SASS mapping

ULEA does not map from any PTX instruction directly. It is emitted by ptxas as an internal optimization to compute uniform-register offsets for address generation (e.g., stride*index computations feeding TMA/UTMALDG descriptors, or constant-buffer base+offset calculations).

The typical use case in generated SASS:
```
ULEA UR6, UR7, UR6, 0x18    # UR6 = UR7 + UR6, then scale by something
ULEA UR6, UR6, 0x400, 0x18  # UR6 = UR6 + 0x400 (immediate offset)
```

Observed in libcublas for computing GMMA/TMA descriptor addresses, where uniform registers hold base pointers and ULEA computes `base + index*stride` offsets.

## Open questions

- **Scale encoding:** The `scaleU5` value of `0x18` (=24) appears frequently but its exact meaning in the address formula (`URa + URb*2^{scale}` or similar) is not clear from the spec alone. The CLASS format shows `UImm(5)*` with default no value, suggesting scale is a raw 5-bit field whose semantics are defined by the hardware pipe.
- **LO variants:** No empirical examples of `.LO` variants found in libcublas. The HI variants are the default.
- **Negate/invert:** The `[-]` (negate) and `[~]` (invert on .X forms) modifiers are specified but no empirical examples found. The condition `negateA → !negateB` confirms they are mutually exclusive.
- **RRI vs URIUR:** Both use opcode `0x1891`. The difference is whether URb (Ra_URc field) is a register or pinned to URZ (63). The exact disambiguation between RRI and URIR variants is determined by whether the Ra_URc field equals 63.
