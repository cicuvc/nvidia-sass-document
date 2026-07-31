# SM120 SASS Assembler — Reference

A text-to-cubin assembler for NVIDIA SM 12.0 (Blackwell / RTX 5090) SASS
instructions.  Parses hand-written SASS assembly and produces loadable cubin
files via `cuModuleLoadData` or the bundled `CudaModule` Python wrapper.

```
Input text (.sass / .asm)
  ↓ Parser (sass_parser.py)
ParsedInstruction[]
  ↓ Class Matcher (sass_matcher.py)
MatchResult(slot_map)
  ↓ Field Encoder (sass_encoder.py)
(lo64, hi64)
  ↓ ELF Builder (sass_elf.py)
.cubin (bytes)
```

---

## Quick start

### Command-line

```bash
python3 -m assembler.sass_asm kernel.asm -o kernel.cubin
```

### Python library

```python
from assembler import assemble, CudaModule

cubin = assemble("""
    #fn fill(data<8>) {
        LDC.64 R0, #param(data);
        MOV32I R1, 0x3f800000;
        STG.E desc[URZ][R0.64], R1;
        EXIT;
    }
""")

mod = CudaModule(cubin)
d = mod.devmem_alloc(1024)
mod.launch("fill", grid=1, block=256, args=[d])
mod.synchronize()
result = mod.device_read(d, 1024)
```

---

## Instruction syntax

```
[@[!]Px] MNEMONIC{.MODIFIER} [operands] ;[SCHED]
```

| Part | Description |
|------|-------------|
| `@[!]Px` | Optional guard predicate (`@P1`, `@!PT`, etc.) |
| `MNEMONIC` | Instruction mnemonic (e.g. `IADD3`, `STG`, `HFMA2`) |
| `.MODIFIER` | Dot-separated modifiers (`.E`, `.U32`, `.WIDE`, `.X`, etc.) |
| `operands` | Comma-separated operands (see Operand types) |
| `;` | Required separator before scheduling bracket |
| `[SCHED]` | **Required** scheduling bracket (see Scheduling) |

### Operand types

| Type | Syntax | Example | Kind |
|------|--------|---------|------|
| Regular register | `R<N>` | `R5`, `RZ` (zero reg = 255) | REG |
| 64-bit reg pair | `R<N>.64` | `R2.64` = {R2,R3} | REG, width=64 |
| Uniform register | `UR<N>` | `UR4`, `URZ` (255) | UREG |
| Predicate | `P<N>` | `P0`, `PT` (= 7) | PRED |
| Uniform predicate | `UP<N>` | `UP0`, `UPT` (= 7) | UPRED |
| Unsigned immediate | `0x...` / decimal | `0x2a`, `256` | IMM_U |
| Signed immediate | `-` prefix | `-4`, `-0x80` | IMM_S |
| Float immediate | `0fXXXXXXXX` | `0f3f800000` (= 1.0f) | IMM_F32 |
| Special register | `SR_NAME.SUB` | `SR_TID.X`, `SR_CLOCKLO` | SPECIAL_REG |
| Constant bank | `c[bank][offset]` | `c[0x0][0x37c]` | CONST_BANK |
| Memory descriptor | `desc[URx]` | `desc[UR4]` | MEM_DESC |
| Memory address | `[Rx.64+offset]` | `[R2.64+0x4]` | MEM_ADDR |
| Kernel parameter | `#param(name)` | `#param(data)` | (resolves to CONST_BANK) |
| Predicate file token | `PR` | `P2R R0, PR, RZ, 0x7f` | PR (flag token) |
| Label (branch target) | `IDENT:` | `loop:` | LABEL |

### Kernel parameters

```sass
#fn kernel_name(param1<size>, param2<size>, ...) {
    #pragma ATTR_NAME(value)
    LDC.64 R0, #param(param1);
    ...
}
```

- `#fn` declares a kernel with named parameters.
- `param<size>` — parameter name and byte size (`<8>` for pointer, `<4>` for int).
- `#param(name)` in an LDC instruction resolves to `c[0x0][base+offset]`.
- Parameters are laid out sequentially at `param_base` (default 0x380), aligned to
  natural alignment (min 4, up to 8).
- `#pragma MAXREG_COUNT(N)` overrides register allocation hint.
- `#pragma NUM_MBARRIERS(N)` overrides the mbarrier count (default 0xffff).

#### Standalone instructions (no #fn)

Without `#fn`, provide `kernel_name` to `assemble()`:

```python
cubin = assemble("NOP;[...]\nEXIT;[...]", kernel_name="my_kernel")
```

---

## Scheduling bracket

**Required** on every instruction after `;`:

```
[wr_sb:rd_sb:{req_list}:stall:yield:batch_t]
```

| Field | Bits | Range | Description |
|-------|------|-------|-------------|
| `wr_sb` | [112:110] | 0–7 | Write scoreboard release. 7 = none. |
| `rd_sb` | [115:113] | 0–7 | Read scoreboard release. 7 = none. |
| `req_list` | [121:116] | bitmask | Wait mask. `{0,3}` = wait for SB0 and SB3. |
| `stall` | [109:105]* | 0–31 | Raw stall value. |
| `yield` | opex[4] | 0–1 | 0 = transN (yield=0), 1 = WAITn_END_GROUP (yield=1). |
| `batch_t` | [124:122] | 0–7 | Optional 6th field. On classes with reusable register sources it is the **reuse mask** (`reuse_a`=1, `reuse_b`=2, `reuse_c`=4) and `batch_t` is forced to 0; otherwise it is a batch marker. Default 0. |

`*` — usched_info is encoded as opex[4:0]; opex = (batch_t << 5) | usched_info.

### Examples

```sass
NOP;[7:7:{}:0:1]                  # WAIT0, no SB, yield=1
EXIT;[7:7:{}:5:0]                 # trans5, yield=0
IADD3 R0, R1, R2, R3;[7:7:{}:5:1] # WAIT5, yield=1
STG.E desc[UR4][R2.64], R5;[7:7:{1}:1:0]  # wait for SB1, trans1
MOV32I R0, 0x5;[7:7:{}:5:1:3]     # batch_t=3 → bits[124:122]=011
```

### Yield bit encoding

| `yield` | Mode | opex[4] | usched_info |
|---------|------|---------|-------------|
| 0 | transN | 1 | `stall + 16` |
| 1 | WAITn_END_GROUP | 0 | `stall` |

trans1–trans11 map to yield=0, stall=1..11 → usched=17..27.
WAIT1–WAIT15 map to yield=1, stall=1..15.

---

## Instruction modifiers (common)

| Modifier | Attaches to | Effect |
|----------|-------------|--------|
| `.E` | LD/ST | Global scope (default for STG, LDG) |
| `.U32` / `.S32` | IMAD, IADD3 | Signedness |
| `.WIDE` | IMAD | 64-bit multiply-add |
| `.HI` | IMAD | High-part multiply |
| `.X` | IADD3, IMAD | Extended precision / carry chain |
| `.64` | LDC, STG, MOV | 64-bit width |
| `.F32` / `.F64` / `.BF16` | F2F, F2I, HFMA2 | Float format |
| `.SAT` | Various | Saturation |
| `.FTZ` | FADD, FMUL, FFMA | Flush denormals to zero |
| `.RP` / `.RM` / `.RZ` / `.RN` | FRND, FADD, etc. | Rounding mode |

---

## Predicate guards

```sass
@P1  STG.E desc[UR4][R2.64], R5;   # execute if P1 = true
@!P0 IADD3 R0, R1, R2, R3;         # execute if P0 = false
@PT  IADD3 R0, R1, R2, R3;         # always (default, same as omitted)
@!PT STG.E desc[UR4][R2.64], R5;   # never execute (valid encoding)
```

Encoding: Pg at [14:12], Pg_not at [15].

---

## Constant bank parameters

```sass
#fn example(in<8>, val<4>) {
    LDC.64 R0, #param(in);          # c[0x0][0x380]
    LDC    R1, #param(val);         # c[0x0][0x388]
    ...
}
```

Layout: parameters aligned consecutively at `param_base` (0x380 by default).
Alignment: min 4, natural alignment for pointer types (8).

---

## KPARAM_INFO / EIATTR — kernel parameter metadata

The assembler automatically emits:

| EIATTR | Scope | Generation |
|--------|-------|------------|
| `REGCOUNT` (0x2f) | device | Auto from max register; `ceil(max/8)*8` |
| `FRAME_SIZE` (0x11) | device | 0 (leaf kernel) |
| `MIN_STACK_SIZE` (0x12) | device | 0 |
| `MAX_STACK_SIZE` (0x23) | device | 0 |
| `CUDA_API_VERSION` (0x37) | per-kernel | 0x80 (128) |
| `KPARAM_INFO` (0x17) | per-kernel | One per `#fn` parameter |
| `MAXREG_COUNT` (0x1b) | per-kernel | 0xff |
| `SPARSE_MMA_MASK` (0x50) | per-kernel | 0 |
| `VRC_CTA_INIT_COUNT` (0x4a) | per-kernel | 0 |
| `EXIT_INSTR_OFFSETS` (0x1c) | per-kernel | **Auto**: scans for EXIT opcode |
| `CBANK_PARAM_SIZE` (0x19) | per-kernel | Total parameter bytes |
| `PARAM_CBANK` (0x0a) | per-kernel | (sym_idx, base=0x380 \| size<<16) |
| `SW_WAR` (0x36) | per-kernel | 0 |
| `NUM_BARRIERS` (0x4c) | per-kernel | **Auto**: max `BAR.SYNC n` + 1 |
| `MBARRIER_INSTR_OFFSETS` (0x39) | per-kernel | **Auto**: SYNCS.EXCH / PHASECHK offsets |
| `NUM_MBARRIERS` (0x38) | per-kernel | 0xffff, override via `#pragma NUM_MBARRIERS(N)` |

---

## Known-good instruction encodings

| Instruction | lo64 | hi64 |
|-------------|------|------|
| `NOP` | `0x0000000000007918` | `0x000fc00000000000` |
| `EXIT` | `0x000000000000794d` | `0x000fea0003800000` |
| `LDC R1, c[0x0][0x37c]` | `0x0000df00ff017b82` | `0x000fe20000000800` |
| `LDC.64 R2, c[0x0][0x380]` | `0x0000e000ff027b82` | `0x000e240000000a00` |
| `S2R R5, SR_TID.X` | `0x0000000000057919` | `0x000e220000002100` |
| `STG.E desc[UR4][R2.64], R5` | `0x0000000502007986` | `0x001fe2000c101904` |
| `MOV32I R7, 0x3f800000` | `0x3f80000000077802` | `0x000fca0000000f00` |
| `IADD3 R0, R1, R2, R3` | `0x0000000301027210` | `0x000fe200047f00ff` |
| `IMAD.WIDE.U32 R2, R5, 0x4, R2` | `0x0000000405027825` | `0x001fca00040e0802` |
| `HFMA2 R7, -RZ, RZ, 1.0, 0` | `0x3f800000ff077431` | `0x000fe200000001ff` |

---

## Cubin structure (generated sections)

| # | Section | Type | Content |
|---|---------|------|---------|
| 0 | (null) | NULL | — |
| 1 | `.shstrtab` | STRTAB | Section name strings |
| 2 | `.strtab` | STRTAB | Symbol strings |
| 3 | `.symtab` | SYMTAB | 8 symbols (text, const0, callgraph, etc.) |
| 4 | `.note.nv.tkinfo` | NOTE | CUDA toolkit version info |
| 5 | `.note.nv.cuver` | NOTE | CUDA ABI version |
| 6 | `.nv.info` | CUDA_INFO | Device-wide EIATTR |
| 7 | `.nv.info._Z<name>` | CUDA_INFO | Per-kernel EIATTR |
| 8 | `.nv.compat` | COMPAT | ISA class, tensormap, etc. |
| 9 | `.nv.callgraph` | CALLGRAPH | Edge list (leaf kernel → 4 sentinels) |
| 10 | `.text._Z<name>` | PROGBITS | SASS code (256B min, NOP-padded) |
| 11 | `.nv.shared.reserved.0` | NOBITS | Reserved shared mem (64B) |
| 12 | `.nv.constant0._Z<name>` | PROGBITS | All zeros, driver fills at launch |

---

## Assembly tips & traps

### Scoreboard / data hazards

`MOV32I` does **not** write to a scoreboard.  A dependent `IADD3` reading its
result must use `yield=1` (WAITn_END_GROUP) to synchronise, or source from a
scoreboard-writing instruction (LDC, S2R).

```sass
MOV32I R0, 0x5;[7:7:{}:5:1]         # writes R0, no SB release
IADD3  R1, R0, R0, RZ;[7:7:{}:5:1] # WAIT5 ensures R0 is ready
```

### Register pair alignment

`LDC.64 Rd` and `STG.E desc[UR][Rd.64]` require `Rd` **even**.  Odd
destinations cause `CUDA_ERROR_ILLEGAL_INSTRUCTION`.

### Valid stall ranges

Not all stall×yield combinations are valid for every instruction.  Use
stall=1..5 (trans1..5, yield=0) or stall=1..11 (WAIT1..11, yield=1) for
broad compatibility.  stall=15 with yield=0 (usched=31) is invalid for
most instructions.

### Descriptor for global memory stores

`desc[URZ]` does not contain a valid global memory descriptor.  Load one
first:

```sass
LDCU.64 UR4, c[0x0][0x358];[1:7:{}:1:0]
STG.E desc[UR4][R2.64], R5;[7:7:{1}:1:0]
```

### Opcode bits [11:0] for instruction detection

| Instruction | opcode [11:0] | Full 13-bit |
|-------------|---------------|-------------|
| EXIT | 0x94d | 0x94d |
| BAR.SYNC | 0xb1d | 0xb1d |
| SYNCS.EXCH | 0x5b2 | 0x15b2 |
| SYNCS.PHASECHK | 0x5a7 | 0x15a7 |
| NOP | 0x918 | 0x918 |

---

## Python API reference

### `assembler.assemble(source, kernel_name="")` → bytes

Assembles SASS source → cubin bytes.  Accepts `#fn` kernel declarations or
standalone instructions (requires `kernel_name` for the latter).

### `assembler.assemble_kernel(source)` → AssembleResult

Parses a `#fn` block and returns a structured result:
- `.code` — cubin bytes
- `.kernel_name` — unmangled kernel name
- `.encoded` — list of `(lo64, hi64)` tuples
- `.params` — list of `(ordinal, cbank_offset, size)` tuples

### `assembler.assemble_flat(source)` → list[(lo64, hi64)]

Assembles plain SASS (no `#fn`) → raw encoded instructions.

### `assembler.CudaModule(cubin, device=0)`

Loads a cubin and provides GPU launch capability.

- `mod.device_name` — GPU name string
- `mod.devmem_alloc(size)` → device pointer
- `mod.devmem_free(ptr)`
- `mod.devmem_set(ptr, value, count)` — fill with 32-bit value
- `mod.device_read(ptr, size)` → bytearray
- `mod.device_write(ptr, data)`
- `mod.launch(func_name, *, grid, block, args, shared_mem, stream)`
- `mod.synchronize()`

---

## File structure

```
assembler/
├── __init__.py        # Public API: assemble(), assemble_kernel(), CudaModule
├── operand.py         # Data types: Operand, Sched, KernelDecl, ParsedInstruction
├── sass_parser.py     # Lexer + recursive-descent parser
├── sass_matcher.py    # CLASS variant matching (1414 variants across 259 mnemonics)
├── sass_encoder.py    # 128-bit instruction encoding, table function support
├── sass_elf.py        # From-scratch cubin ELF builder (no template needed)
├── sass_asm.py        # CLI entry point
├── runner.py          # CUDA Driver API wrapper (CudaModule)
├── minimal.cubin      # Reference template (for NOTE section content only)
```

---

## Implementation notes

- `sm120.json` (gitignored) — regenerable via `python3 tools/parse_sm120.py`.
  Contains 1414 encoding variants, 259 mnemonics, 449 enums, 89 decode tables.
- The assembler **does not** do register allocation, instruction scheduling,
  or control-flow analysis.  These are the user's responsibility.
- All 128-bit instructions use little-endian byte order in the cubin file.
- `batch_t` bits [124:122] encode reuse hints for the 3 source operand slots
  (bit 0 → reuse_src_a, bit 1 → reuse_src_b, bit 2 → reuse_src_c).
