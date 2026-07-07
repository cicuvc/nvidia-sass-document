# ULOP3 — Uniform Three-Input Logic

**Opcode mnemonic:** ULOP3  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Uniform three-input bitwise logic operation. Applies an 8-bit look-up table (LUT) across three source operands `(URa, URb, URc)` producing `URd`. Equivalent to `LOP3` for uniform registers.

Two modes exist:
- **LUT (`LUTOnly`):** An 8-bit LUT value is specified as an immediate. Each bit `i` (0–7) of the LUT encodes the output for input combination `{URa[i], URb[i], URc[i]}` (bit-sliced across the 32-bit word).
- **LOP (`LOP`):** A named logic operation (`AND`=0, `OR`=1, `XOR`=2, `PASS_B`=3) is selected, with optional `[~]` inversions on source operands. The 8-bit SRa field is computed from a lookup table (TABLES_op_0 / TABLES_op_1).

## Variant overview

| Variant | Opcode | Format | Observer?
|---------|--------|--------|----------|
| `ulop3_lut` (noimm) | `0x1292` | `ULOP3.LUT [UPu,] URd, URa, URb, URc, imm8 [, UPp]` | **Yes** |
| `ulop3_lut` (imm) | `0x1892` | `ULOP3.LUT [UPu,] URd, URa, imm32, URc, imm8 [, UPp]` | **Yes** |
| `ulop3_lut_optionalUPp` (both) | ALT | Same as above, UPp pinned to `!UPT` | **Yes** (ptxas default) |
| `ulop3_noimm` (LOP) | `0x1292` | `ULOP3 [UPu,] URd, [~]URa, [~]URb, [~]URc [, UPp]` | Not observed |
| `ulop3_imm` (LOP) | `0x1892` | `ULOP3 [UPu,] URd, [~]URa, imm32, [~]URc [, UPp]` | Not observed |

All observed instances in libcublas use the LUT mode with the optional UPp ALT variant (UPp pinned to !UPT).

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| mode | lut | — | LUT=0 (LUT mode, always) |
| pop | UPq_not | [80] | 0=POR, 1=PAND (always POR=0 observed) |
| imm8 | SRa | [79:72] | 8-bit LUT value |
| URa invert | — | — | `[~]` prefix (LOP mode only, via TABLES_op_0) |
| URb invert | — | — | `[~]` prefix (LOP mode only) |
| URc invert | — | — | `[~]` prefix (LOP mode only) |

For LOP mode, the `[~]` inversion flags and the `lop` enum value (AND/OR/XOR/PASS_B) are encoded through a lookup table into the 8-bit `SRa` field:
- TABLES_op_0 (noimm): `(lop, ~URa, ~URb, ~URc) → SRa[7:0]`
- TABLES_op_1 (imm): `(lop, ~URa, ~URc) → SRa[7:0]`

## Bit layout

### Noimm LUT — opcode 0x1292

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[115:113]            src_rel_sb           <= *7
[112:110]            dst_wr_sb            <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode               <= 0b1001010010010
[90:90]              input_reg_sz_32_dist <= UPp@not (or *1 for ALT)
[89:87]              Pnz                  <= UPp (or *7 for ALT)
[83:81]              Pu                   <= UPu
[80:80]              UPq_not              <= pop (POR=0)
[79:72]              SRa                  <= imm8
[69:64]              Ra_URc               <= URc
[37:32]              Ra_URb               <= URb
[29:24]              Sa                   <= URa
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
```

### Imm LUT — opcode 0x1892

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[115:113]            src_rel_sb           <= *7
[112:110]            dst_wr_sb            <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode               <= 0b1100010010010
[90:90]              input_reg_sz_32_dist <= UPp@not (or *1 for ALT)
[89:87]              Pnz                  <= UPp (or *7 for ALT)
[83:81]              Pu                   <= UPu
[80:80]              UPq_not              <= pop (POR=0)
[79:72]              SRa                  <= imm8
[69:64]              Ra_URc               <= URc
[63:32]              Ra_offset            <= Sb (imm32)
[29:24]              Sa                   <= URa
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
```

## Latency

ULOP3 is in `udp_pipe`, under the `UDP_subset` latency group (same as ULEA, UMOV etc.):

```
TABLE_TRUE(UGPR):  UDP_subset:{...} : {URd} : 4 12 12 8 12 7 9 12 12 10 9
TABLE_OUTPUT(UGPR): {URd} : 1 4 7 7
TABLE_ANTI(UGPR): {...} : 1 1 1 3
```

Output latency: **1–7 cycles**. True-dependency: **4–12 cycles**.

## Verified encodings

### From libcublas (sm_90, CUDA 13.1)

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x000000053f067292` | `0x000fe2000f8e333f` | `ULOP3.LUT UR6, URZ, UR5, URZ, 0x33, !UPT` |
| `0x0000000709047892` | `0x000fe2000f80c03f` | `ULOP3.LUT UP0, UR4, UR9, 0x7, URZ, 0xc0, !UPT` |
| `0x0000000f09047892` | — | `ULOP3.LUT UP0, UR4, UR9, 0xf, URZ, 0xc0, !UPT` |
| `0xfffffff004047892` | — | `ULOP3.LUT UR4, UR4, 0xfffffff0, URZ, 0xc0, !UPT` |
| `0xfffffff004057892` | — | `ULOP3.LUT UR5, UR4, 0xfffffff0, URZ, 0xc0, !UPT` |
| `0x0000001f05057892` | — | `ULOP3.LUT UP0, UR5, UR5, 0x1f, URZ, 0xc0, !UPT` |
| `0x0000001f080d7892` | — | `ULOP3.LUT UP1, UR13, UR8, 0x1f, URZ, 0xc0, !UPT` |

### PTX→SASS mapping

ULOP3 does not map directly from a PTX instruction. It is emitted by ptxas as part of the lowering of `lop3` (PTX bitwise INLINE ASM) or for uniform-predicate address computations.

Common patterns:
- `ULOP3.LUT URd, URZ, URb, URZ, 0x33, !UPT` — XOR pass-through (LUT=0x33 = 00110011 = XOR logic)
- `ULOP3.LUT URd, URa, imm32, URZ, 0xc0, !UPT` — bit-extract / mask (LUT=0xc0 selects bits)
- The `!UPT` suffix is the UPp predicate, always appearing as `!UPT` in ptxas output

## Cross-comparison

### ULOP3 vs LOP3

| Property | LOP3 | ULOP3 |
|----------|------|-------|
| Pipe | `int_pipe` (FXU) | `udp_pipe` |
| Registers | Regular (`Rd`, `Ra`, `Rb`, `Rc`) | Uniform (`URd`, `URa`, `URb`, `URc`) |
| Predicate | Regular (`Pg`) | Uniform (`UPg`) |
| Opcodes | Multiple (0xE72, 0x672, etc.) | 0x1292 / 0x1892 |
| LUT immediate | 8-bit at [25:18] | 8-bit at [79:72] |
| Imm32 operand | Not available (separate LOP32I) | Yes, at [63:32] |

### ULOP32I vs ULOP3 imm

ULOP32I is a 2-input logic operation with a 32-bit immediate. ULOP3 imm extends this to 3 inputs (URa, imm32, URc) with an 8-bit LUT, making it a superset of ULOP32I.

## Open questions

- **LOP mode (AND/OR/XOR/PASS_B):** No empirical examples found. Does ptxas ever emit the non-LUT variants, or does it always use LUT mode with explicit LUT values?
- **PAND pop mode:** Only POR=0 observed. What is PAND (1) and when is it used?
- **UPp as non-UPT:** The optional UPp variant allows arbitrary UPp values, but ptxas only uses `!UPT`. What instruction sequences require a different UPp result?
- **LUT values:** Common LUTs observed: 0x33 (XOR?), 0xc0 (mask?), 0x1f (5-bit mask). What exact logic does each LUT encode?
