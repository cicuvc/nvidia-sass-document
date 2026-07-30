# SM120 SASS Assembler — Architecture Plan

Build a text-to-cubin assembler for SM120 (RTX 5090) that parses hand-written
SASS assembly and produces loadable cubin files via `cuModuleLoadData`.

## Syntax

```
MNEMONIC{.MODIFIERS} operands[; scheduling_bracket]
```

Each instruction line has:
1. A **mnemonic** (e.g. `STG`, `MOV`, `LDCU`)
2. Optional dot-separated **modifiers** (`.E`, `.U16`, `.64`)
3. **Operands** separated by commas
4. An optional **scheduling bracket** after `;`

The scheduling bracket specifies the control word explicitly:
```
[wr_sb:rd_sb:{req_bits}:stall:yield]
```

Default bracket (when omitted): `[7:7:{}:1:0]` — no barriers, trans1, no yield.

### Operand types

| Type | Syntax | Example |
|------|--------|---------|
| Regular register | `R<N>` | `R5`, `RZ` |
| Regular register pair | `R<N>.64` | `R2.64` = {R2, R3} |
| Uniform register | `UR<N>` | `UR4`, `URZ` |
| Uniform register pair | `UR<N>.64` | `UR6.64` = {UR6, UR7} |
| Predicate | `P<N>` | `P0`, `PT` (=7) |
| Uniform predicate | `UP<N>` | `UP0`, `UPT` (=7) |
| Unsigned immediate | `0x...` or decimal | `0xcafebabe`, `256` |
| Signed immediate | decimal with `-` | `-4` |
| Float immediate | `0f...` | `0f1.0` |
| Special register | `SR_<NAME>.<SUB>` | `SR_TID.X` |
| Constant bank | `c[bank][offset]` | `c[0x0][0x37c]` |
| Memory descriptor | `desc[UR<N>.64]` | `desc[UR6.64]` |
| Memory address | `[R<N>.64 + offset]` | `[R2.64+0x4]` |

### Modifier encoding

Modifiers map to `/SLOT("default"):name` fields in the FORMAT section. Each
modifier has an enum with named values; the assembler looks up the numeric value
from `sm120.json` enums.

Common modifiers: `.E` (global scope), `.U16` (16-bit size), `.64` (64-bit width),
`.RM/.RP/.RZ/.RN` (rounding), `.SAT` (saturation), `.FTZ` (flush-to-zero).

### Scheduling bracket details

| Field | Bits | Decoded | Notes |
|-------|------|---------|-------|
| `wr_sb` | [112:110] | `dst_wr_sb` | Write scoreboard release. 7 = none. |
| `rd_sb` | [115:113] | `src_rel_sb` | Read scoreboard release. 7 = none. |
| `req_bits` | [121:116] | `req_bit_set` | Wait mask. `{0,3}` = wait for SB0 and SB3. |
| `stall` | [109:105] | `usched_info` | Raw stall value. If yield=0: `usched_info = stall + 16` (transN). If yield=1: `usched_info = stall` (WAITn_END_GROUP). Valid transN: 1–11. |
| `yield` | opex[4] | `usched_info[4]` | 0 = transN (bit4=1), 1 = WAITn_END_GROUP (bit4=0) |

Encoding logic:
```
usched_info = (yield ? stall : stall + 16)
opex = (0 << 5) | usched_info   # batch_t = 0 always
pm_pred = 0                     # perf-monitor predicate, not used
```

### Examples

```
# Store R5 to out[0] using URZ as default descriptor, with write/read barriers
STG.E.U16 desc[URZ][R2.64+0x0], R5;[0x0:0x1:{0}:1:0]

# Load 32-bit constant into R5
MOV R5, 0xcafebabe;[7:7:{}:7:0]

# Exit kernel
EXIT;[7:7:{}:5:0]

# TMA 2D load with cache hint policy
UTMALDG.2D [UR8], [UR4];[7:0x0:{}:12:1]

# Load from constant bank
LDCU.64 UR4, c[0x0][0x358];[7:7:{}:1:0]

# mbarrier init + try_wait
SYNCS.EXCH.64 URZ, [UR9], UR4;[7:7:{}:2:0]
SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR4], RZ;[7:7:{}:2:0]
```

## Architecture

```
Input text (.sass)
  ↓ Lexer/Parser
Parsed instructions (IR)
  ↓ Class Matcher
CLASS from sm120.json + operand-to-slot mapping
  ↓ Field Encoder
(lo64, hi64) pairs
  ↓ ELF Builder
Output .cubin
```

### Component 1: Parser (`tools/sass_parser.py`)

**Input:** text source
**Output:** list of `ParsedInstruction` objects

```
ParsedInstruction:
  mnemonic: str         # e.g. "STG"
  modifiers: [str]      # e.g. ["E", "U16"]
  operands: [Operand]   # typed operands
  sched: Optional[Sched] # scheduling bracket (None if omitted)

Operand:
  kind: OperandKind     # register, immediate, const_bank, mem_desc, etc.
  value: int | str      # register number or literal
  width: int            # 32, 64, 128 (for vector registers)
  negated: bool         # for [-R5]
  absolute: bool        # for [|R5|]

Sched:
  wr_sb: int
  rd_sb: int
  req_bits: set[int]    # e.g. {0, 3}
  stall: int
  yield: int
```

**Lexer:** Token types: `REG`, `UREG`, `PRED`, `UPRED`, `NUMBER`, `HEX`, `DOT`,
`COMMA`, `COLON`, `SEMICOLON`, `LBRACKET`, `RBRACKET`, `LBRACE`, `RBRACE`,
`PLUS`, `MINUS`, `IDENT`.

**Syntax:** Simple recursive-descent parser.

### Component 2: Class Matcher (`tools/sass_matcher.py`)

**Input:** `ParsedInstruction` + sm120.json `variants`
**Output:** `(class_info, slot_map)`

Algorithm:
1. Filter variants by mnemonic (`v["mnemonic"] == instruction.mnemonic`)
2. For each candidate CLASS, parse its FORMAT section into a list of typed slots
3. Match operand list against slot list:
   - Regular slots: match 1-to-1 by position, checking type compatibility
   - Composite slots (e.g. `memoryDescriptor[...][...]`): consume multiple operands
   - Starlight slots (`*`): skip (pinned/reserved)
4. Validate matched pairs against CONDITIONS:
   - `OOR_REG_ERROR`: register within valid range
   - `MISALIGNED_REG_ERROR`: register aligned for vector width
   - `ILLEGAL_INSTR_ENCODING_ERROR`: modifier values valid
5. If multiple CLASSes match, warn and use first
6. Return the CLASS info + mapping from operand index → slot name

**Vector register handling:** `R2.64` produces TWO Operand entries with `width=64`
metadata. The class matcher aligns them with adjacent slot positions. Alignment
validation: low register must be a multiple of `width/32` (e.g. R2 for 64-bit,
R4 for 128-bit).

**Slot type compatibility:**
- `Register` ↔ OperandKind.REG (`R<N>`)
- `UniformRegister` ↔ OperandKind.UREG (`UR<N>`)
- `Predicate` ↔ OperandKind.PRED (`P<N>`)
- `UniformPredicate` ↔ OperandKind.UPRED (`UP<N>`)
- `UImm(N/M)*` ↔ OperandKind.IMM_U
- `SImm(N/0)*` ↔ OperandKind.IMM_S
- `F32Imm` ↔ OperandKind.IMM_F32
- `SpecialRegister` ↔ OperandKind.SPECIAL_REG
- `DESC:memoryDescriptor[...]` ↔ OperandKind.MEM_DESC + MEM_ADDR
- `C:Sa[...]` ↔ OperandKind.CONST_BANK

**Modifier matching:** The `/MODIFIER("default"):slot_name` fields in FORMAT are
matched against the dot-separated modifiers in the instruction. The modifier's
enum name is looked up in `sm120.json` enums to get the numeric value.

### Component 3: Field Encoder (`tools/sass_encoder.py`)

**Input:** CLASS info + slot→operand mapping + Sched
**Output:** `(lo64, hi64)` pair

For each `BITS` field in CLASS.ENCODING:
1. Parse `BITS_<width>_<hi>_<lo>[_...]_<name>`
2. Look up RHS kind:
   - `opcode`: Use 13-bit value from CLASS opcode (`{bit[91]∥bits[11:0]}`)
   - `slot`: Look up operand value from slot map; encode per slot type
   - `slot_attr`: Look up sub-attribute (e.g. `Pg@not` → `{Pg, "not"}`)
   - `num`: Literal numeric value
   - `star_num`: Fixed/pinned default from spec
   - `star_slot`: Pinned slot value from format default
   - `table_fn`: Execute table lookup (see below)
3. Call `set_bits128(lo, hi, hi_bit, lo_bit, width, value)`

**Slot type → value encoding:**
```
Register:        value = reg_number         (R5→5, RZ→255)
UniformRegister: value = ureg_number        (UR6→6, URZ→255)
Predicate:       value = pred_number        (P0→0, PT→7)
UniformPredicate:value = upred_number       (UP0→0, UPT→7)
UImm(N/M):       value = imm               (0xcafebabe for N=32, masked to N bits)
SImm(N/0):       value = imm & ((1<<N)-1)  (sign-extended in encoding)
F32Imm:          value = struct.pack('>f', imm)[0]  → 32b big-endian IEEE754
Modifier enum:   value = enum_lookup(mod_name, "str")
```

**Table function handling:**
- `TABLES_opex_N(batch_t, usched_info[, reuse_*])`: Compute opex from scheduling bracket
- `TABLES_mem_N(order, sem, sco, private)`: Encode memory ordering modifiers
- `ConstBankAddress0/2(bank, offset)`: Pack bank+offset into 32-bit field
- For unrecognized tables: warn and use 0

**Table lookup fallback:** If table rows are present in sm120.json, look up the
(input → output) mapping. If no match, use output value 0 with a warning.

### Component 4: ELF Builder (`tools/sass_elf.py`)

**Input:** (lo64, hi64) list + kernel name + parameter list
**Output:** bytes (loadable .cubin file)

#### 4a. ELF Header

```
e_machine = 190 (EM_NVIDIA_CUDA)
e_type = 2 (ET_EXEC)
e_flags = 0x6007802 (SM120)
OS/ABI = 0x41 (CUDA)
ABI version = 8
```

#### 4b. Required sections

| Section | Type | Content |
|---------|------|---------|
| `.shstrtab` | STRTAB | Section name strings |
| `.strtab` | STRTAB | Symbol/program strings |
| `.symtab` | SYMTAB | 1 kernel function entry |
| `.text._Z<name>` | PROGBITS (AX, align 128) | SASS code (padded to 256B) |
| `.nv.info._Z<name>` | CUDA_INFO (0x70000083) | Per-kernel EIATTR |
| `.nv.info` | CUDA_INFO (0x70000083) | Device-wide EIATTR |
| `.nv.constant0._Z<name>` | PROGBITS | Driver preset + kernel params |
| `.nv.shared.reserved.0` | NOBITS (WA, size=0x40) | Reserved shared memory slot |
| `.note.nv.tkinfo` | NOTE | Toolkit version info |
| `.note.nv.cuver` | NOTE | CUDA version info |

**Optional (can omit):** `.nv.compat`, `.nv.callgraph`, `.debug_frame`,
Mercury/capmerc sections.

#### 4c. `.text` section

Instructions packed as little-endian `lo64, hi64` pairs. Section aligned to
128 bytes. Padded with NOPs to fill. Minimum 16 slots (256 bytes).

#### 4d. `.nv.info` — EIATTR encoding

Each attribute is a 3-field record: `uint32_le type, uint32_le value_length, value_bytes`.
Pad value to 4-byte alignment.

Required attributes for a minimal kernel:
```
EIATTR_REGCOUNT         (0x082f04) : 8  → registers used
EIATTR_FRAME_SIZE       (0x081104) : 0  → no stack frame
EIATTR_MIN_STACK_SIZE   (0x081204) : 0
EIATTR_MAX_STACK_SIZE   (0x081304) : 0  (if no calls or CRS)
EIATTR_CUDA_API_VERSION (0x043704) : <api_version>
EIATTR_KPARAM_INFO      (0x0c1704) : parameter offset/size pairs
EIATTR_CBANK_PARAM_SIZE (0x1b03)   : total param bytes
EIATTR_PARAM_CBANK      (0x1c04)   : (bank_section << 16) | 0x210
EIATTR_EXIT_INSTR_OFFSETS (0x1903) : offset of EXIT in .text
EIATTR_MAXREG_COUNT     (0x3604)   : 0xff
EIATTR_CRS_STACK_SIZE   (0x0a04)   : 0 (no CRS calls)
```

Values templated from a minimal compiled SM120 kernel.

#### 4e. `.nv.constant0._Z<name>`

First 0x398 bytes copied from the minimal template cubin. Contains:
- 0x000–0x20F: driver preset region (launch config, descriptors, etc.)
- 0x210+: kernel parameter area (offset from PARAM_CBANK)

Kernel parameters are placed at offsets starting from 0x210 (or wherever
PARAM_CBANK specifies). Each pointer parameter takes 8 bytes.

#### 4f. Template

A minimal compiled SM120 kernel provides the template bytes for:
- EIATTR records in `.nv.info*` sections
- Constant bank 0 preset region
- NOTE sections (.nv.tkinfo, .nv.cuver)

The assembler embeds these template bytes and adjusts the variable fields
(EXIT offset, register count, parameter info).

### Component 5: CLI (`tools/sass_asm.py`)

```
usage: sass_asm.py input.sass [-o output.cubin] [-n kernel_name] [--template template.cubin]
```

Flow:
1. Parse input text → instruction list
2. For each instruction: match CLASS, encode lo64/hi64
3. Build ELF container using template
4. Write .cubin file

## Implementation Plan

### Phase 1 — Core pipeline (minimal coverage, ~6 instructions)

1. **Type system + Parser** — registers, immediates, modifiers, scheduling brackets
2. **Class Matcher** — initially hard-coded map for 6 core instructions:
   `STG, EXIT, MOV32I, UMOV, LDC.64, LDCU.64`
3. **Field Encoder** — handle slot/opcode/star_num/table_fn reference encoding
4. **Scheduling Encoder** — compute opex + barriers from bracket
5. **ELF Builder** — construct valid SM120 cubin from scratch
6. **End-to-end test**: assemble `STG.E desc[URZ][R2.64], R5` → load → launch → verify global write

### Phase 2 — Automatic class matching + full ISA expansion

1. Parse FORMAT templates into typed slot lists
2. Generic operand-to-slot matching with type compatibility checks
3. Multi-operand composite slot handling (memoryDescriptor, const_bank)
4. Modifier enumeration lookup
5. CONDITIONS validation (register ranges, alignment, illegal encodings)
6. Table function lookup from sm120.json table rows
7. Support all 259 mnemonics

### Phase 3 — ELF builder hardening

1. Correct EIATTR generation based on instruction analysis
2. Parameter-to-cbank-offset mapping
3. Relocation support (for future use)
4. Mercury/capmerc section generation (if ever needed)

## Verification Strategy

For each instruction: assemble with our tool, also compile an equivalent kernel
with nvcc, compare SASS via cuobjdump. The encodings should be bit-identical
(modulo control word barriers/stalls which we set explicitly).

Test harness:
```bash
# Assemble
python3 tools/sass_asm.py test.sass -o test.cubin -n my_kernel
# Verify
cuobjdump -arch sm_120 -sass test.cubin
# Execute
python3 tools/launch_test.py test.cubin my_kernel --verify-global-write 0xCAFEBABE
```

## Key Risks

| Risk | Mitigation |
|------|------------|
| CLASS matching picks wrong variant for complex operands | Warn first; iteratively add disambiguation rules |
| TABLES_opex_* lookup needs runtime table evaluation | Load table rows from sm120.json; fallback to opex=0 |
| ELF builder EIATTR values may not match driver expectations | Use exact templated bytes from verified reference cubin |
| CONST_BANK slot immediates mix 16/17/24-bit widths | Mask per spec-defined width; validate range via CONDITIONS |
| Register vector alignment (R3.64 is invalid) | Assert low register % (width/32) == 0 |

## Related Files

- `sm120.json` — ISA spec database (regenerated by `parse_sm120.py`)
- `tools/query_sm120.py` — Query CLI for field layout, class info, enums
- `tools/build_sm120_cubin.py` — Current template-based cubin builder (to be superseded)
- `notes/sm90/arch/sm120_findings.md` — Encoding discoveries and cache policy analysis
- `notes/sm90/arch/control_codes.md` — Control word / scheduling field documentation
- `notes/sm90/arch/encoding_classification.md` — 128-bit field taxonomy
- `notes/sm90/arch/cubin_elf.md` — cubin ELF structure reference
