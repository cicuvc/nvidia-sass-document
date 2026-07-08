# SASS Encoding Classification — Top-Down Analysis

![Encoding diagrams](encoding_diagrams.png)

All SASS instructions are **128-bit** (hi64 [127:64] + lo64 [63:0]) with a common
control-word overlaying a variable operands+opcode region.

## Invariant Fields — Every Instruction

These bit positions are fixed across all 1589 encoding variants (1168 CLASS + 421 ALT):

| bits | field | purpose |
|------|-------|---------|
| [124:122],[109:105] | `opex` | scheduling (batch_t + usched_info), routed through `TABLES_opex_*` |
| [121:116] | `req_bit_set` | scoreboard wait mask (which SBk this op waits on) |
| [115:113] | `src_rel_sb` | source release scoreboard (which SBk to release on read) |
| [112:110] | `dst_wr_sb` | destination write scoreboard (which SBk to release on write) |
| [103:102] | `pm_pred` | performance-monitor predicate |
| [91],[11:0] | **opcode** | 13-bit opcode — **always** bit 91 (MSB) concatenated with bits [11:0] |
| [15] | `Pg_not` | predicate guard negate |
| [14:12] | `Pg` | predicate guard (3-bit, 7=PT hidden) |

Instructions that consume no scoreboard (coupled, fixed-latency ops) pin
`src_rel_sb` = `dst_wr_sb` = 7 (star-pinned, no-OP value).

## Opcode Bit — Why [91] is Special

The opcode is 13-bit: `{bit[91], bits[11:0]}`. Bit [91] acts as a **page selector**:
- **0**: 12-bit opcode (0x000–0xFFF) — simpler instructions, immediate/const variants
- **1**: 13-bit opcode (0x1000–0x1FFF) — uniform/memory/complex variants

Many instruction families use the same lower 12 bits and flip bit 91 to toggle
between GPR and uniform-register forms (e.g. LDG 0x381 / 0x1981, IADD3 0x233 / 0x1233).

## Operand Slot Conventions

### GPR Registers (8-bit, R0–R255, RZ=255)

| slot | bits | typical role |
|------|------|-------------|
| `Rd` | [23:16] | destination register |
| `Ra` | [31:24] | source A / address |
| `Rb` | [39:32] | source B / second source |
| `Rc` | [71:64] | source C / third source (RRR form) |

### Uniform Registers (6-bit, UR0–UR63, URZ=63)

| slot | bits | typical role |
|------|------|-------------|
| `URd` | [21:16] | destination uniform register |
| `URa` / `Sa` | [29:24] | source A / address |
| `URb` | [37:32] | source B |
| `URc` | [69:64] | source C / uniform base address |

### Predicate Registers (3-bit, P0–P6, PT=7)

| slot | bits | role |
|------|------|------|
| `Pg` | [14:12] | guard predicate |
| `Pp`/`Pu`/`Pv` | [89:87],[86:84],[83:81] | predicate operands (output/chaining) |

---

## Instruction Formats — The Encoding Taxonomy

### R-Type (Register–Register, 3 inputs)

**RRR** — canonical 3-register compute (IADD3, LOP3, IMAD, DFMA, FFMA, …)

```
           opex            opcode/field    Rc      Rb      Ra      Rd   Pg
[127]     [124:122]  [109:105]       [91]   [71:64]  [39:32] [31:24] [23:16] [14:12]
[109:105] opex (8b)  [121:116] req   [11:0] opcode
```

| bits | operand |
|------|---------|
| [71:64] | `Rc` — third source register |
| [39:32] | `Rb` — second source register |
| [31:24] | `Ra` — first source register |
| [23:16] | `Rd` — destination register |

Used by: IADD3, LOP3, IMAD (and .WIDE/.HI/.X), DFMA, DMUL, DADD, FFMA,
FADD, FMUL, ISETP, I2I, I2F, F2I, LEA, SHF, and all packed vector ops.

### RI-Type (Register–Immediate)

**RIR** — Rb replaced by 32-bit immediate at [63:32]

| bits | operand |
|------|---------|
| [63:32] | `imm32` — 32-bit immediate (replaces Rb) |
| [31:24] | `Ra` |
| [23:16] | `Rd` |

**RRI** — Rc replaced by 32-bit immediate at [63:32]

| bits | operand |
|------|---------|
| [71:64] | `Rc` |
| [63:32] | `imm32` — replaces Rb slot |
| [31:24] | `Ra` |
| [23:16] | `Rd` |

**RsIR** — Ra replaced by 32-bit immediate at [63:32] (source-immediate form,
e.g. `IADD3 Rx, 0x42, Ry, Rz`)

**RRsI** — FP64 immediate: high 32 bits at [63:32], low 32 bits implied 0

### RC-Type (Register–Constant Bank)

**RCR** — second operand from constant bank: bank + offset at [63:40],[39:38]

| bits | operand |
|------|---------|
| [63:40] | `const_offset` (24-bit) |
| [39:38] | `const_bank` (2-bit), or absorbed into upper bits |
| [31:24] | `Ra` |
| [23:16] | `Rd` |

**RCxR** — extended constant bank (bindless): URb at [37:32] selects the
uniform register holding the bank base, offset at [63:40].

### RU-Type (Register–Uniform Register)

**RUR** — second operand is a uniform register:

| bits | operand |
|------|---------|
| [37:32] | `URb` — uniform register (6-bit), replaces Rb |
| [31:24] | `Ra` |
| [23:16] | `Rd` |

**RRU** — third operand is a uniform register:

| bits | operand |
|------|---------|
| [69:64] | `URc` — uniform register, replaces Rc |
| [39:32] | `Rb` |
| [31:24] | `Ra` |
| [23:16] | `Rd` |

### U-Type (Uniform Register only)

**URURUR** — all operands in uniform registers:

| bits | operand |
|------|---------|
| [69:64] | `URc` — third source |
| [37:32] | `URb` — second source |
| [29:24] | `URa` / `Sa` — first source / address |
| [21:16] | `URd` — destination |

Used by: UIADD3, ULOP3, UIMAD, ULEA, USHF, UBMSK, UBREV, UFLO, UF2FP, UPOPC.

**URIR** — URb replaced by 32-bit immediate at [63:32]:

| bits | operand |
|------|---------|
| [63:32] | `imm32` |
| [29:24] | `URa` |
| [21:16] | `URd` |

### M-Type (Memory Access — LD/ST)

**sImmOffset** — base register + signed 24-bit offset:

| bits | operand |
|------|---------|
| [63:40] | `offset` (24-bit signed) |
| [39:32] | `Rb` (store data) or unused |
| [31:24] | `Ra` — base address register |
| [23:16] | `Rd` (load data) or unused |

**uImmOffset** — adds uniform base register URc:

| bits | operand |
|------|---------|
| [69:64] | `URc` — uniform base (added to Ra) |
| [63:40] | `offset` (24-bit signed) |
| [39:32] | `Rb` / data |
| [31:24] | `Ra` — base address |
| [23:16] | `Rd` / data |

**memdesc** — global-memory LDG/STG/ATOMG/REDG form with memory descriptor:

| bits | operand |
|------|---------|
| [69:64] | `URc` — descriptor + base |
| [63:40] | `offset` |
| [39:32] | `Rb` / data |
| [31:24] | `Ra` — register offset (may be RZ=URc-only) |
| [23:16] | `Rd` / data |

### B-Type (Branch / Control Flow)

**Branch immediate** — target is a signed PC-relative offset:

| mnemonic | opcode | offset bits | operand |
|----------|--------|-------------|---------|
| BRA | 0x947 | [81:34]∥[23:16] (56-bit sImm*4) | GPR target optional |
| JMP | 0x94a | [81:34]∥[23:16] (56-bit sImm*4) | GPR target optional |
| BRX | 0x949 | [81:34]∥[23:16] (56-bit sImm*4) | Ra[31:24] + offset |
| JMX | 0x94c | [81:34]∥[23:16] (56-bit sImm*4) | Ra[31:24] + offset |
| CALL | 0x94e | [81:34]∥[23:16] | reg/const/imm target |

**Uniform branch** — branch indirect via uniform register:

| mnemonic | opcode | offset bits | operand |
|----------|--------|-------------|---------|
| BRXU | 0x1958 | [81:34]∥[23:16] | URa[29:24] + offset |
| JMXU | 0x1959 | [81:34]∥[23:16] | URa[29:24] + offset |

All branch offsets are 56-bit signed immediate, multiplied by 4, rendered as
`offset = sImm*4 & 0xffffffffff` (40-bit address mask). Offset=0 is omitted.

### A-Type (Atomic / Reduction — LDG-like addressing)

All atomic/reduction instructions (ATOM, ATOMG, ATOMS, RED, REDG, REDAS) share
a common operand layout derived from LDG/STG:

| bits | field |
|------|-------|
| [90:87] | `op` — atomic operation (ADD/MIN/MAX/INC/DEC/AND/OR/XOR/EXCH) |
| [86:84] | `cop` — `.E` / `.EN` |
| [83:81] | `Pu` — write predicate |
| [80:77] | `mem` — sem/sco/private (via `TABLES_mem_*`) |
| [75:73] | `sz` — data size (U32/S32/U64/S64/U128) |
| [72] | `e` — 1 = 64-bit address (`Ra.64`), 0 = 32-bit |
| [63:40] | `Ra_offset` — 24-bit signed offset |
| [39:32] | `Rb` — source value |
| [31:24] | `Ra` — address register (`*Ra` = pinned for RaRZ) |
| [23:16] | `Rd` — old value (absent in RED/REDG fire-and-forget) |

### Tensor Core Types

**HMMA** (warp-level): custom layout with size/srcfmt/dstfmt in [83:76], [75:73]:
- Dense (0x23c): RRR-like with Ra[31:24], Rb[39:32], Rc[71:64], Rd[23:16]
- Sparse: adds `Re` at [49:44], `id` at [43:42]

**GMMA** (warpgroup-level, 0x1df0/0x1df1/0x1df2/0x1df3): shared-memory descriptor
based:
- `Ra_URb_Rc_`: Ra[31:24] (A in GPR), URb[37:32] (B descriptor), Rc[71:64] (accum)
- `URa_Rb_Rc_`: URa[29:24] (A descriptor), Rb[39:32] (B in GPR), Rc[71:64]
- `URa_Rc_`: URa[29:24] (both descriptors), Rc[71:64], no Rb
- Size: [59:53] (7-bit), srcfmt [77:76], dstfmt [75], gsb [86:84]

### Special Types (Operand-less)

Instructions with no register/immediate operands (only predicate):

| instruction | opcode | note |
|-------------|--------|------|
| NOP | 0x50b | single uniform variant also exists |
| YIELD | 0x946 | Pp predicate operand |
| EXIT | 0x94d | mode at [85:84], no_atexit at [86] |
| PREEXIT | 0x82d | PDL producer signal |
| ACQBULK | 0x82e | PDL consumer acquire |
| ERRBAR | 0x9ab | GPU error barrier |
| CGAERRBAR | 0x5ab | cluster error barrier |
| MEMBAR | 0x992 | scope at [78:77] |
| BAR | 0x890/0x894 | barrier register at [16:12] |
| BSYNC | 0x98d | barReg at [57:54] |
| WARPSYNC | 0x950 | mask at [31:24] |
| NANOSLEEP | 0x9b0 | ns count at [53:32] |
| DEPBAR | 0x9b6 | SB select at [84:82], count at [89:87] |
| UTMACMDFLUSH | 0x9b7 | TMA group commit |
| UTMACCTL | 0x9b9/0x19b9 | descriptor cache control (no data) |

## Format Naming Convention

Class names encode the operand format as a suffix after `__`:

| Suffix | Meaning | Example classes |
|--------|---------|-----------------|
| `RRR` | 3 GPR operands | `iadd3_noimm__RRR`, `lop3_lut__RRR_RRR` |
| `RIR` | GPR + immediate | `iadd3_imm__RsIR`, `lop3_imm__RIR_RIR` |
| `RRI` | GPR + immediate at Rc | `hfma2_mma_relu__RRI` |
| `RCR` | GPR + const bank | `iadd3_noimm__RCR_RCR` |
| `RCxR` | GPR + const (bindless) | `iadd3_noimm__RCxR_RCxR` |
| `RUR` | GPR + uniform | `iadd3_noimm__RUR_RUR` |
| `RRU` | GPR + uniform at Rc | `imad_pseudo__RRU_RRU` |
| `RRsI` | GPR + FP64 imm (high) | `dfma__RRsI_RRI` |
| `URURUR` | 3 uniform regs | `uiadd3__URURUR_URURUR` |
| `URIR` | uniform + immediate | `uiadd3__URsIUR_RIR` |
| `URuIUR` | uniform + uniform imm | `ulop3_lut__URuIUR_URIR` |
| `sImmOffset` | RA + signed offset | `ld__sImmOffset` |
| `uImmOffset` | RA + uniform + offset | `ld__uImmOffset` |
| `memdesc` | memory descriptor | `ldg__memdesc` |
| `RaNonRZ` | address reg ≠ RZ | `atom_int__RaNonRZ` |
| `RaRZ` | address reg = RZ | `atom_int__RaRZ` |
| `Ra32` | 32-bit address | `atom_int_uniform__Ra32` |
| `Ra64` | 64-bit address | `atom_int_uniform__Ra64` |

## Summary: The Encoding Space

```
 127                                                                   0
 +-----------------------------------------------------------------------+
 |  opex   |req|sr|dw|pm|  opcode(hi)  | modifiers/operands  |opc|Pg|Pg| |
 |  [124:122] [109:105] | [121:116] | [115:113] | [112:110] | [103:102] | [91] ... [11:0] | [15] | [14:12] |
 +-----------------------------------------------------------------------+
  <-scheduling+scoreboard (18b)-> |1|   opcode(12b)  |     variable operand fields (93b)    |   Pg(4b)
                                  | <- fixed 13b ->  |
```

**128 bits total = 18 scheduling + 13 opcode + 93 operands/modifiers + 4 predicate guard**

The invariant prefix ([127:104], [103:102], [91:91], [15:12]) occupies 27 bits;
the remaining **101 bits** encode opcode extension, modifiers, register/immediate
operands, and instruction-specific fields — laid out differently per format family.
