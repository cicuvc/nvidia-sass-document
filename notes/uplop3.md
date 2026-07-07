# UPLOP3 — Uniform Predicate Three-Input Logic

**Opcode mnemonic:** UPLOP3  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Uniform predicate-level logic operation. Produces one or two uniform predicate outputs from a 3-input logic function. Unlike ULOP3 (which produces a uniform register), UPLOP3 computes predicates — single-bit results driven through the uniform predicate register file.

Two modes exist:
- **LUT (`LUTOnly`):** An 8-bit LUT determines the output for each of the 8 possible predicate input combinations. Two LUTs (`uimm8`, `vimm8`) for the 2-output form.
- **LOP (`PLOP_OP_NOREG`):** A named operation (AND=32768, XOR=38400, SEL=51712, OR=65024) without register inputs. No empirical examples.

The 0-register variants take uniform predicates (`UPp`, `UPq`, `UPr` with optional negation) as inputs. The 1/2/3-register variants take uniform registers with `SIGN` modifiers and extract the sign bit as the predicate input.

## Variant overview

| Variant | Opcode | Outputs | Reg inputs | Observed? |
|---------|--------|---------|------------|-----------|
| `uplop3_lut_2out_` | `0x89c` | UPu + UPv | 0 (UPs only) | **Yes** |
| `uplop3_lut_1out_` (ALT) | `0x89c` | UPu only | 0 (UPs only) | No |
| `uplop3_1out_` (LOP, ALT) | `0x89c` | UPu only | 0 | No |
| `uplop3_lut_1out_1reg` (ALT) | `0x129d` | UPu only | 1 (URa) | No |
| `uplop3_lut_2out_1reg` | `0x129d` | UPu + UPv | 1 (URa) | No |
| `uplop3_lut_1out_2reg` (ALT) | `0x129e` | UPu only | 2 (URa, URb) | No |
| `uplop3_lut_2out_2reg` | `0x129e` | UPu + UPv | 2 (URa, URb) | No |
| `uplop3_lut_1out_3reg` (ALT) | `0x129f` | UPu only | 3 (URa, URb, URc) | No |
| `uplop3_lut_2out_3reg` | `0x129f` | UPu + UPv | 3 (URa, URb, URc) | No |

## Modifiers

| Field | Bits | Semantics |
|-------|------|-----------|
| `UPp@not` | [90] | Invert UPp input |
| `UPp` | [89:87] | Predicate input P (3-bit) |
| `UPv` / `cop` | [86:84] | 2nd output (2-out) or *7 (1-out) |
| `UPu` / `Pu` | [83:81] | Primary output predicate |
| `UPq@not` | [80] | Invert UPq input |
| `UPq` | [79:77] | Predicate input Q (3-bit) |
| `uimm8` | [76:72],[66:64] | 8-bit LUT for UPu output |
| `UPr@not` | [71] | Invert UPr input |
| `UPr` | [70:68] | Predicate input R (3-bit) |
| `vimm8` / `Rd` | [23:16] | 8-bit LUT for UPv output (2-out) |

For the 1-reg / 2-reg / 3-reg variants, registers occupy: `URa` [29:24], `URb` [37:32], `URc` [69:64]. Each has a `SIGNONLY` modifier (value 0 = "SIGN") that extracts the sign bit.

## Bit layout

### 0-reg, 2-out LUT — opcode 0x89c

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[115:113]            src_rel_sb           <= *7
[112:110]            dst_wr_sb            <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode               <= 0b100010011100
[90:90]              input_reg_sz_32_dist <= UPp@not
[89:87]              Pnz                  <= UPp
[86:84]              cop                  <= UPv
[83:81]              Pu                   <= UPu
[80:80]              UPq_not              <= UPq@not
[79:77]              UPq                  <= UPq
[76:72],[66:64]      uimm8                <= uimm8
[71:71]              memdesc              <= UPr@not
[70:68]              UPr                  <= UPr
[23:16]              Rd                   <= vimm8
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
```

## Latency

UPLOP3 is in `udp_pipe`, under the `UDP_subset` latency group. Produces uniform predicates (UPu, UPv). The latency file groups it with `WHOLE_UPRED_OPS` via `UPR_UPRED` connector for the 0-reg form, and uses standard UGPR connectors for register-input forms.

## Verified encodings

### From libcublas (sm_90, CUDA 13.1)

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x000000000000789c` | `0x000fe20003f0f070` | `UPLOP3.LUT UP0, UPT, UPT, UPT, UPT, 0x80, 0x0` |
| `0x000000000000789c` | `0x000fd80003f0f070` | `UPLOP3.LUT UP0, UPT, UPT, UPT, UPT, 0x40, 0x0` |

Only the 0-register, 2-output LUT form appears. The LUT values 0x80 and 0x40 appear as bit-position selects (bit 7 or bit 6 of the 8-entry truth table). All predicate inputs are UPT (unconditional) with no negation, making this effectively a constant-true pass-through to UP0 via the LUT.

### PTX→SASS mapping

No direct PTX mapping. UPLOP3 is likely emitted as part of `lop3` predicate logic lowering for uniform predicates, or for internal driver/runtime predicate computation in TMA descriptor setup.

## Cross-comparison

### UPLOP3 vs ULOP3 vs PLOP3

| Property | PLOP3 | UPLOP3 | ULOP3 |
|----------|-------|--------|-------|
| Output | Regular predicate | Uniform predicate | Uniform register |
| Input | Regular pred + reg | Uniform pred + reg | Uniform register |
| Pipe | `int_pipe` | `udp_pipe` | `udp_pipe` |
| LUT width | 8-bit | 8-bit (x2 for 2-out) | 8-bit |

## Open questions

- **Register-input variants (1-reg, 2-reg, 3-reg):** No empirical examples. What instruction sequences would require extracting sign bits from uniform registers into a predicate?
- **LOP mode (AND/XOR/SEL/OR):** Uses large constants (32768, 38400, 51712, 65024) as the op values. These are likely packed representations. What is the exact encoding format?
- **LUT semantics:** The 8-bit LUT encodes the output for all 8 combinations of `{UPp, UPq, UPr}` (bit 0 = all false, bit 7 = all true). With all inputs as UPT, the LUT value effectively becomes a 1-bit constant. Observed values 0x80 and 0x40 both have a single bit set, producing UP0=1 or UP0=0 depending on bit position.
