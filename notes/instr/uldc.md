# ULDC — Uniform Load Constant

**Opcode mnemonic:** ULDC  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Loads data from constant memory (`c[bank][addr]`) into a **uniform register** (`UR0`–`UR63`). Unlike LDC which targets regular GPRs, ULDC writes to the uniform register file, enabling downstream uniform ALU operations (`UIADD3`, `UMOV`, `ULOP3`, etc.) on the loaded value.

The load size is configured by the `sz` modifier: loads can be 8-bit, 16-bit, 32-bit, or 64-bit. For sub-32-bit loads, the value is zero/sign-extended into the destination URd.

**Scoreboard:** Coupled (unified read+write scoreboard), consistent with all `udp_pipe` instructions. The source release and destination write scoreboards are hardwired to `*7` (inactive), since constant memory loads on the UDP pipe are serialized through the CBU.

## Variant overview

| Variant | Opcode | Pattern | Description |
|---------|--------|---------|-------------|
| `uldc_const__RCR` | `0xab9` | `ULDC URd, c[bank][offset]` | Constant bank + immediate offset |
| `uldc_const__RCxR` | `0x1ab9` | `ULDC URd, c[URa][offset]` | Register-indexed bank + immediate offset |
| `uldc_ur_offset_` | `0x1abb` | `ULDC URd, c[bank][URa+offset]` | Immediate bank + register+offset index |
| `uldc_imm_` | `0x18b8` | `ULDC URd, imm32` | Zero-UR base + 32-bit immediate |
| `uldc_ur_offs_` | `0x18b8` | `ULDC URd, c[...][URa+offset], @UPx` | Register bank+offset with UPx predicate |
| `uldc_ur_offs_optional_upx_` (ALT) | `0x18b8` | `ULDC URd, c[...][URa+offset]` | Register bank+offset, UPx=UPT (elided) |

The variants sharing opcode `0x18b8` are disambiguated by the `Sa` (source register) field: `Sa=0` means `uldc_imm_` (URZ base), while `Sa≠0` means one of the register-offset variants (distinguished by the `Pnz`/`input_reg_sz_32_dist` predicate fields).

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| `sz` (size) | `sz` | [75:73] | 0=U8, 1=S8, 2=U16, 3=S16, 4=32, 5=64, 6/7=INVALID |

Size effect on register alignment:
- `sz=64`: URd must be even-aligned (`URd%2==0`). URd occupies a pair (URd, URd+1).
- `sz≤32`: URd is a single uniform register.
- The source operand size drives `IDEST_SIZE` = `{1,1,1,1,2,4}` × 32 bits.

## Bit layout

### uldc_const__RCR (opcode 0xab9)

```
[124:122],[109:105]  opex        <= TABLES_opex_1(batch_t, usched_info)
[121:116]            req_bit_set
[115:113]            src_rel_sb   <= *7
[112:110]            dst_wr_sb    <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode       <= 0b101010111001
[75:73]              sz
[58:54]              Sb_bank      <= ConstBankAddress0(Sa_bank, Sa_addr)
[53:38]              Ra_offset    <= ConstBankAddress0(Sa_bank, Sa_addr)
[21:16]              URd
[15:15]              Pg_not
[14:12]              Pg           <= UPg
```

### uldc_ur_offset_ (opcode 0x1abb)

```
[124:122],[109:105]  opex        <= TABLES_opex_1(batch_t, usched_info)
[121:116]            req_bit_set
[115:113]            src_rel_sb   <= *7
[112:110]            dst_wr_sb    <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode       <= 0b1101010111011
[75:73]              sz
[58:54]              Sb_bank      <= ConstBankAddress0(Sa_bank, Sa_offset)
[53:38]              Ra_offset    <= ConstBankAddress0(Sa_bank, Sa_offset)
[29:24]              Sa           <= URa
[21:16]              URd
[15:15]              Pg_not
[14:12]              Pg           <= UPg
```

### uldc_imm_ / uldc_ur_offs_ (opcode 0x18b8)

```
[124:122],[109:105]  opex                   <= TABLES_opex_1(batch_t, usched_info)
[121:116]            req_bit_set
[115:113]            src_rel_sb              <= *7
[112:110]            dst_wr_sb               <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode                  <= 0b1100010111000
[90:90]              input_reg_sz_32_dist    <= UPx@not (ur_offs) | *1 (imm)
[89:87]              Pnz                     <= UPx (ur_offs) | *7 (imm)
[75:73]              sz
[69:38]              Sa_offset               <= 32-bit immediate
[29:24]              Sa                      <= *URa (pinned: URZ for imm, NonZeroURa for ur_offs)
[21:16]              URd
[15:15]              Pg_not
[14:12]              Pg                     <= UPg
```

### uldc_const__RCxR (opcode 0x1ab9)

```
[124:122],[109:105]  opex        <= TABLES_opex_1(batch_t, usched_info)
[121:116]            req_bit_set
[115:113]            src_rel_sb   <= *7
[112:110]            dst_wr_sb    <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode       <= 0b1101010111001
[75:73]              sz
[53:38]              Ra_offset    <= Sa_offset
[29:24]              Sa           <= URa
[21:16]              URd
[15:15]              Pg_not
[14:12]              Pg           <= UPg
```

## Cross-comparison

### ULDC vs LDC

| Property | LDC | ULDC |
|----------|-----|------|
| Pipe | `mio_pipe` | `udp_pipe` |
| Dest register | Regular (`Rd`) | Uniform (`URd`) |
| Predicate | Regular (`Pg`) | Uniform (`UPg`) |
| Opcode base | `0xb82` / `0x1582` | `0xab9` / `0x1ab9` / `0x18b8` / `0x1abb` |
| Scoreboard | `INST_TYPE_DECOUPLED_RD_WR_SCBD` | `INST_TYPE_COUPLED_MATH` |
| Sub-word loads | 8/16-bit via separate opcodes | Via `sz` field (U8/S8/U16/S16) |

### Empirical lowering (sm_90, CUDA 13.1)

ptxas aggressively lowers `ld.const` to ULDC when the address is register-indexed or when the loaded value feeds uniform-register consumers:

| PTX | SASS |
|-----|------|
| Kernel parameter load | `ULDC URd, c[0x0][offset]` |
| Kernel parameter load (64-bit) | `ULDC.64 URd, c[0x0][offset]` |
| `__constant__[idx]` indexed | `ULDC URd, c[bank][URa]` (opcode 0x1abb) |
| `__ldg(const_*)` for U8/S8/U16/S16 | Lowered to `LDG.E.{U8,S8,U16,S16}.CONSTANT` via LDC-constructed desc |

Only fully-immediate constant loads (stack frame, explicit offsets) remain as LDC.

## Latency

ULDC is in `udp_pipe`. In the UGPR latency tables, it sits in `ULDC_VOTEU_UMOV_ULEPC`:

```
TABLE_TRUE(UGPR):
  ULDC_VOTEU:{...} : {URd @URdRange, URd2 @URd2Range} : 2 5 5 2 5 2 2 5 5 3 2

TABLE_OUTPUT(UGPR):
  ULDC_VOTEU_UMOV_ULEPC:{URd @URdRange, URd2 @URd2Range} : 1 4 1 1

TABLE_ANTI(UGPR):
  OP_ULDC:{URa ...} : 1 1 1 1
```

Output latency to a uniform-register consumer (e.g., UIADD3 using the loaded value) is **1–4 cycles** depending on operand size. True-dependency latency from a CW (constant-writer) producer is **2–5 cycles**. Anti-dependency from a prior uniform-register writer is **1 cycle**.

Constant memory itself has a fixed 2-cycle true-dependency latency through the CBU (visible in the GPR TABLE_TRUE as `ALL_OPS:MIO_CBU_OPS:2`), but for ULDC→uniform consumers the UGPR tables above apply.

## Verified encodings

### From libcublas + test kernels (sm_90, CUDA 13.1)

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00008d00000a7ab9` | `0x000fe20000000800` | `ULDC UR10, c[0x0][0x234]` |
| `0x0000820000087ab9` | `0x000fcc0000000a00` | `ULDC.64 UR8, c[0x0][0x208]` |
| `0x0000000000047ab9` | `0x000fe20000000800` | `ULDC UR4, c[0x0][0x0]` |
| `0x0000880000047ab9` | `0x000fc80000000800` | `ULDC UR4, c[0x0][0x220]` |
| `0x00008a0000047ab9` | `0x000fc60000000a00` | `ULDC.64 UR4, c[0x0][0x228]` |
| `0x00008e0000047ab9` | `0x000fc60000000a00` | `ULDC.64 UR4, c[0x0][0x238]` |
| `0x0000900000047ab9` | `0x000fc60000000a00` | `ULDC.64 UR4, c[0x0][0x240]` |
| `0x0000860000047ab9` | `0x000fe40000000800` | `ULDC UR4, c[0x0][0x218]` |
| `0x0000890000067ab9` | `0x000fcc0000000800` | `ULDC UR6, c[0x0][0x224]` |
| `0x0000840000077ab9` | `0x000fe20000000800` | `ULDC UR7, c[0x0][0x210]` |
| `0x00008a0000067ab9` | `0x000fcc0000000a00` | `ULDC.64 UR6, c[0x0][0x228]` |
| `0x00008c0000047ab9` | `0x000fc60000000a00` | `ULDC.64 UR4, c[0x0][0x230]` |
| `0x00008f0000077ab9` | `0x000fe40000000800` | `ULDC UR7, c[0x0][0x23c]` |
| `0x00000a00ff017b82` | `0x000ff00000000800` | `LDC R1, c[0x0][0x28]` (comparison) |

### Register-indexed (uldc_ur_offset_)

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00c0000004047abb` | `0x000fe40008000800` | `ULDC UR4, c[0x3][UR4]` |

### PTX→SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| Kernel parameter (float/int) | `ULDC URd, c[0x0][offset]` (sz=32) |
| Kernel parameter (double/int64) | `ULDC.64 URd, c[0x0][offset]` (sz=64) |
| `__constant__[idx]` (32-bit) | `ULDC URd, c[bank][URa]` (opcode 0x1abb) |
| `__constant__[idx]` (64-bit) | Lowered to LDC.64 (register-indexed, bank 3) |
| `ld.const.u32 [addr], _` | `ULDC URd, c[bank][URa]` (ptxas lowers all reg-indexed ldc to ULDC) |
| `ld.const.u32 [addr+imm], _` | `ULDC URd, c[bank][URa+imm]` |
| Sub-word constant loads | `LDG.E.{U8,S8,U16,S16}.CONSTANT` (not ULDC directly) |

## Open questions

- **uldc_imm_ (0x18b8) variant:** No empirical examples found. When would ptxas emit a ULDC with an immediate value instead of a constant-bank load? Possibly for driver-internal uniform-register initialization or for the `uldc_ur_offs_` pattern.
- **uldc_ur_offs_ (0x18b8) vs uldc_ur_offset_ (0x1abb):** Both handle register-indexed constant loads, but ptxas on sm_90 exclusively uses `0x1abb` (the variant with explicit bank+ConstBankAddress0). The `0x18b8` variant has a 32-bit immediate offset field (vs 16-bit in 0x1abb), suggesting it supports larger offsets. Under what circumstances is it preferred?
- **uldc_const__RCxR (0x1ab9):** The CX extended-constant variant with a register-indexed bank and 16-bit immediate offset. The `CX` type likely encodes a different constant-address space. No empirical examples found.
- **RTV banks (24-31):** The spec allows bank 24-31 with an offset-≤255 constraint. What are RTV banks? Likely run-time-value banks populated by the driver at kernel launch. No empirical examples.
- **PTX `uldc` instruction:** PTX ISA 9.3 includes a `ld.const` instruction that maps to ULDC but does not document a standalone `uldc` PTX mnemonic. The hardware instruction is internal.
