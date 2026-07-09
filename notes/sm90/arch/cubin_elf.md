# cubin ELF layout — sections, symbols, relocations, `.nv.info` metadata (sm_90)

How a `nvcc -cubin`/`ptxas` output is structured, and how the loader wires up
constant banks, global variables, external functions, and device-to-device calls.
Grounded in `RELOCATORS` (spec lines 10–127) + empirical dumps of a relocation-rich
kernel (`tests/reloc_demo.cu`: a `__constant__` array, a `__device__` global, a
`__noinline__` device call, and `printf`).

Repro:
```
nvcc -arch=sm_90 -cubin   -o reloc_linked.cubin reloc_demo.cu   # linked EXEC cubin
nvcc -arch=sm_90 -rdc=true -dc -o reloc_rdc.o    reloc_demo.cu   # relocatable object
cuobjdump -elf <file>        # CUDA-aware sections/EIATTR/relocations
readelf -hSsrW <file>        # generic ELF view
```

## ELF container
- `type=ET_EXEC` (linked cubin) or `ET_REL` (relocatable device object), `Machine =
  NVIDIA CUDA`, `OS/ABI = 0x41` (CUDA), `ABI Version = 8`.
- `sm=90` and toolkit version are encoded in the header `flags` (`0x6005a04`) and in
  the `.note.nv.tkinfo` / `.note.nv.cuinfo` notes (ptxas version, command line,
  virtual SM). Entry point is 0 (kernels are entered by symbol, not by ELF entry).

## Section taxonomy
| Section | Type | Role |
|---------|------|------|
| `.text._Z…` | PROGBITS AX | SASS for one kernel (align 128). `Info` links its `.nv.constant0` |
| `.nv.info` | CUDA_INFO | **device-wide** per-function attrs (`EIATTR_REGCOUNT`, `EIATTR_FRAME_SIZE`, `MIN/MAX_STACK_SIZE`) |
| `.nv.info._Z…` | CUDA_INFO | **per-kernel** attrs (params, cbank, exit/syscall offsets, externs, …) |
| `.nv.constant0._Z…` | PROGBITS (`0x42`) | per-kernel **bank 0**: driver preset region + kernel params (`c[0x0]`, see `../instr/ldc.md`) |
| `.nv.constant3` | PROGBITS (`0x2`) | user `__constant__` storage → **bank 3** (`c[0x3]`) |
| `.nv.constant4` | PROGBITS (`0x2`) | **bank 4** (`c[0x4]`): 64-bit **addresses** of globals / extern funcs / string literals, filled by relocation |
| `.nv.global` | NOBITS WA | `__device__` variables (uninitialized/BSS) |
| `.nv.global.init` | PROGBITS WA | initialized global data incl. string literals (`$str`) |
| `.nv.shared.reserved.0` | NOBITS WA | driver-reserved static shared slot (`__nv_reservedSMEM_offset_0_alias`) |
| `.nv.callgraph` | CUDA_CALLGRAPH | caller→callee edges (for CRS/stack sizing) |
| `.rela.<target>` | RELA | relocations applied to `.text`, `.nv.constant4`, `.debug_frame` |
| `.debug_frame` | PROGBITS | DWARF CFA: `R1` frame base + size (stack unwind) |
| `.symtab`/`.strtab`/`.shstrtab` | (STR/SYM)TAB | symbols & names |

## The three constant banks (how kernel data is reached)
1. **Bank 0** (`c[0x0]`, `.nv.constant0._Z…`) — per-launch preset region + kernel
   parameters from `0x210`. Fully mapped in `../instr/ldc.md`.
2. **Bank 3** (`c[0x3]`, `.nv.constant3`) — the actual bytes of user `__constant__`
   variables. Accessed directly, e.g. `LDC R0, c[0x3][R2]` for `cbuf[i]`. The bank
   offset is patched by an `R_CUDA_ABS16_32` / `R_CUDA_CONST_FIELD*` relocation into
   the instruction's 16/19/21-bit const-address field (via the `ConstBankAddress0/2`
   encoders named in `RELOCATORS`).
3. **Bank 4** (`c[0x4]`, `.nv.constant4`) — an **address table**: one 64-bit slot per
   referenced global symbol / extern function / string literal, each an
   `R_CUDA_64` relocation. The kernel loads the pointer from `c[0x4]` then dereferences
   it (global load) or `CALL.ABS` it. This is the `c[0x4]` table seen in library
   kernels (e.g. cusolver `LDC.64 R2, c[0x4][R0]`).

Empirical bank-4 table for `reloc_demo` (`.rela.nv.constant4`):
| c[0x4] offset | symbol | reloc |
|---------------|--------|-------|
| `0x00` | `vprintf` (extern func) | `R_CUDA_64` |
| `0x08` | `gvar` (`__device__` var) | `R_CUDA_64` |
| `0x10` | `$str` (`"hit %d\n"` in `.nv.global.init`) | `R_CUDA_64` |

## Relocation types (spec `RELOCATORS` → patched instruction field)
Each relocator is `{name, mask, [encoder], is_pcrel, …, {{shift,width}…}}`; the
trailing bit-fields say which instruction bits are patched. `RELATIVE_ADDRESS_BASE =
CURRENT_INSTRUCTION + 16` (PC-relative base = next 128-bit instruction).

| Reloc (ELF type) | Bits patched | Used for |
|------------------|--------------|----------|
| `R_CUDA_64` (2) | `{0,64}` (data) | 64-bit address slot in `.nv.constant4` / `.debug_frame` |
| `R_CUDA_32` (1) | `{0,32}` | 32-bit data word |
| `R_CUDA_ABS32_LO_32` / `_HI_32` | `{32,32}` | lo/hi half of a 64-bit address into a `MOV`/`UR` imm32 (e.g. return address, `$str` ptr, `gvar` ptr) |
| `R_CUDA_ABS16_32` | `{32,16}` | 16-bit **const-bank offset** (bank-3 `__constant__` ref) |
| `R_CUDA_ABS55_16_34` | `{16,8}+{34,47}` | 55-bit **`CALL.ABS` target** address |
| `R_CUDA_CONST_FIELD{19,21,22}_*` | via `ConstBankAddress0/2` | generic const-bank address fields |
| `R_CUDA_FUNC_DESC*` (`fdesc`) | 8/32/64-bit | function-descriptor slots for indirect calls |
| `R_CUDA_PCREL_IMM24_*` | `{26/23,24}` | PC-relative branch immediates |
| `R_CUDA_UNUSED_CLEAR64` | `{0,64}` | zero a placeholder (debug frame) |

## Verified offset ↔ reloc ↔ SASS (linked `reloc_demo`)
| `.text` off | SASS | wired to |
|-------------|------|----------|
| `0x080` | `CALL.REL.NOINC 0x200` | internal `helper` — **PC-relative after linking, no reloc** |
| `0x0d0` | `LDC R0, c[0x3][R2]` | `cbuf` (bank 3) |
| `0x140` | `ULDC.64 UR4, c[0x4][0x10]` | `$str` address (bank 4) |
| `0x170` | `LDC.64 R2, c[0x4][R0]` | `vprintf` address (bank 4, off 0) |
| `0x1a0` | `CALL.ABS.NOINC R2` | `vprintf` — matches `EIATTR_SYSCALL_OFFSETS = 0x1a0` |
| `0x1f0` | `EXIT` | matches `EIATTR_EXIT_INSTR_OFFSETS = 0x1f0` |
| `0x200` | `LDC.64 R2, c[0x4][0x8]` | `gvar` address (inside `helper`) |

**Linked vs. relocatable:** in the relocatable object the same sites carry
`R_CUDA_ABS55_16_34` (call target) + `R_CUDA_ABS32_HI/LO_32` (pushed return address),
and `helper` is reached by `CALL.ABS`. Device-linking resolves the intra-module
`helper` call to `CALL.REL` with an immediate (its `.rela.text` becomes empty), while
`vprintf` stays external (`EIATTR_EXTERNS: vprintf`) and keeps its bank-4 slot.

## `.nv.info` attribute catalog (observed)
Device-wide (`.nv.info`): `EIATTR_REGCOUNT` (e.g. 24), `EIATTR_FRAME_SIZE`,
`EIATTR_MIN_STACK_SIZE`, `EIATTR_MAX_STACK_SIZE` — emitted for **every** function incl.
the split-out `$_Z5mainkPi$_Z6helperi` local.
Per-kernel (`.nv.info._Z…`): `EIATTR_CUDA_API_VERSION`, `EIATTR_KPARAM_INFO`
(ordinal/offset/size, `cbank 0x1f`), `EIATTR_CBANK_PARAM_SIZE`, `EIATTR_PARAM_CBANK`
(`sec, (size<<16)|0x210`), `EIATTR_MAXREG_COUNT` (0xff), `EIATTR_EXTERNS`,
`EIATTR_SYSCALL_OFFSETS` (call sites), `EIATTR_EXIT_INSTR_OFFSETS`,
`EIATTR_CRS_STACK_SIZE` (call/return reconvergence stack), `EIATTR_SPARSE_MMA_MASK`,
`EIATTR_SW_WAR`, `EIATTR_MERCURY_ISA_VERSION`.
`.nv.compat` (`EICOMPAT_*`): `ISA_CLASS`, `MERCURY_ISA_MAJOR_MINOR_VERSION` (1.1),
`INST_TENSORMAP_V1`, `CAN_FASTPATH_FINALIZE`, `CUDA_ACCELERATOR_TARGET`.

## Symbols & callgraph
- `cbuf` → `.nv.constant3`; `gvar` → `.nv.global`; `$str` → `.nv.global.init`
  (`"hit %d\n"` = `68 69 74 20 25 64 0a 00`).
- Non-inlined device functions are emitted as a **local** `FUNC` with a fused name
  `$<kernel>$<callee>` (here `$_Z5mainkPi$_Z6helperi`) inside the kernel's `.text`.
- `vprintf` is an `UND GLOBAL FUNC` (satisfied at device link).
- `.nv.callgraph` lists `<callerSymIdx, calleeSymIdx>` edges (`<16,17>` = `maink`→
  `vprintf`); negative callee sentinels (`-1..-4`) flag leaf/indirect/external/no-return
  cases used to bound the CRS stack.

## Cross-references
- Constant **bank 0** preset region + params: `../instr/ldc.md`.
- `LDC`/`ULDC` addressing modes and bank selection: `../instr/ldc.md`, `../instr/uldc.md`.
- Global-memory descriptor (`c[0x0][0x208]`, distinct from the bank-4 address table):
  `memory_model.md`.
- `EIATTR_MERCURY_ISA_VERSION` here is just a version tag; the actual Mercury/capmerc
  **capsule sections** appear only in `sm_100+` cubins — see
  `../../sm100/arch/mercury_capmerc.md`.
