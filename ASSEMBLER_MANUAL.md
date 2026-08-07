# SM120 SASS Assembler — Syntax, Features & Usage Notes

The `assembler/` package is a hand-written SASS (Sierra/SM120 assembly) parser,
matcher and encoder that turns source text into loadable cubin bytes, plus a
CTypes CUDA runner for executing those cubins on a GPU and a scoreboard
dependency checker.  It targets the **sm_120** ISA spec (`sm120.json`,
regenerated from `sm_90_instructions.txt` / `sm_90_latencies.txt` by
`tools/parse_sm90.py`); every SASS instruction is **16 bytes / 128 bits**
(hi64 + lo64), regardless of the `WORD_SIZE 64` header line.

---

## 1. Entry points

| Function | Returns | Purpose |
|---|---|---|
| `assemble(source, kernel_name="", check_deps=True, strict_deps=False)` | `bytes` (cubin) | Full pipeline. Accepts a `#fn` kernel or standalone instructions (kernel_name required for the latter). |
| `assemble_kernel(source, check_deps=True, strict_deps=False)` | `AssembleResult` | Like `assemble` for a `#fn` block; also gives `.encoded` (list of `(lo64, hi64)`) and `.params`. |
| `assemble_flat(source)` | `list[(lo64, hi64)]` | Parse + encode only, no ELF. Fast for decoder/round-trip tests. |

`AssembleResult` fields: `code` (cubin bytes), `kernel_name`, `encoded`,
`params` (`[(ordinal, 0x380+ordinal, size)]`).

CLI: `python -m assembler.sass_asm input.sass [-o out.cubin] [-n kernel] [--dump-text ...] [--strict-deps] [--no-check-deps] [--debug-tokens]`.

---

## 2. Kernel declaration

```
#fn my_kernel(out<8>, flag<4>) {
    ... instructions ...
}
```

- Parameters: `name<size>` where **`size` is the parameter's byte width in the
  kernel parameter block** — 8 for a pointer, 128 for a `__grid_constant__
  CUtensorMap — **not** the size of the buffer a pointer points at** (allocate
  buffers with `CudaModule.devmem_alloc`, don't write that size here).  Layout
  is computed with natural alignment (≤8 bytes, min 4) from a `param_base` of
  `0x380`.  Inside the body, `#param(name)` resolves to the parameter's
  `c[0x0][offset]`.
- **`#spec_const(NAME)`** resolves to a fixed const-bank slot; the only one
  defined is `SLOT_DEFAULT_CDESC` = `c[0x0][0x358]`, the per-kernel default
  cache descriptor used as `desc[...]` for global accesses.
- **`#pragma NAME(value)`** sets kernel attributes: `MAXREG_COUNT`,
  `SHARED`, `SHADER_TYPE`, `NUM_MBARRIERS`, `MBARRIER_*`.  These flow into
  the ELF pragma/metadata.
- **`#def_label(name)`** defines a label; **`#label(name)`** references one
  (used as the target of `BRA`, `BSSY`, `BSSY`-style branches).  A bare
  `name:` also defines a label.
- Bare labels (`.L_x:`) and `#def_label` are legal; control-flow targets use
  `#label(...)`.

Example used throughout the tests:

```
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]
    LDG.E.128 {R16,R17,R18,R19}, desc[{UR4,UR5}][{R6,R7}+0x0];[5:7:{0,1}:8:1]
    ...
}
```

---

## 3. Instruction syntax

```
[@[!]Px] MNEMONIC[.MOD]... op1, op2, ... ;[wr:rd:{req}:stall:yield[:batch_t]]
```

- **Predicate guard**: `@P0`, `@!P3`, `@PT` before the mnemonic.
- **Modifiers**: dot-separated, order-insensitive per matcher (`LDG.E.128`,
  `HMMA.16816.F32.BF16`, `QMMA.SF.16832.F32.E4M3.E5M2.E8`, …).
- **Operands** are comma-separated and match the instruction's `FORMAT`
  slots by type.

### 3.1 Operand kinds

| Kind | Example | Notes |
|---|---|---|
| Register | `R4`, `RZ` | `RZ` = 255, always means the zero register |
| Register group | `{R2,R3}`, `{R16,R17,R18,R19}` | See §4 — **mandatory for 64/128-bit operands** |
| Uniform register | `UR4`, `URZ` | 6-bit (0–63); `URZ` = 63 |
| Predicate | `P0`..`P6`, `PT` | guard = `@Px` |
| Uniform predicate | `UP0`..`UP6`, `UPT` | used by some MMA/async forms |
| Special register | `SR_TID.X`, `SR_CLOCKLO`, … | via `S2R` |
| Const-bank | `c[0x0][0x358]`, `c[0x3][0x20]` | direct constant access |
| Cache descriptor | `desc[{UR4,UR5}]` | descriptor + address (global accesses) |
| Memory | `[R6.64+0x10]`, `[R6+0x10]`, `[UR4+0x0]` | address operand |
| Barriers | `B0`..`B15` | `B15` is special (global barrier) |
| Scoreboard | `SB0`..`SB5` | as `&req=` / `&rd=` forms where applicable |
| Immediate | `0x400`, `1`, `-1`, `0f3F800000` | `0f` + 8 hex digits = raw FP32 bits |

### 3.2 Scheduling bracket

`[wr:rd:{req}:stall:yield[:batch_t]]`

- `wr` / `rd` — destination / source scoreboard (SB0–SB5, **7 = "none"**;
  **6 does not exist** and is rejected).
- `req` — comma-separated set of scoreboards to wait on before issue
  (`{0,1,4}`), encoded as a 6-bit BITSET (bits > 5 rejected).
- `stall` — wait-after-reuse cycles (0–7 in the visible encoding).
- `yield` — 0/1 (`?trans`-style yield hint).
- `batch_t` — optional 6th field (0–5).

`usched_info = stall + 16` when `yield == 0`, else `stall`.  The matcher
checks the resulting `opex` against the instruction's `TABLES_opex_*`; an
illegal combination raises `EncodeError: ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR`.

---

## 4. Register groups (the most important gotcha)

**Every 64-bit or 128-bit operand must list ALL its registers explicitly:**
`{Ra,Rb}` for 64-bit, `{Ra,Rb,Rc,Rd}` for 128-bit. Wide MMA accumulator
operands list the full group too: 8 registers for `HGMMA.64x16x16`, and
16/32/64/128 registers for the larger `HGMMA.64xNx16` shapes (e.g.
`{R24,…,R55}` for `64x64x16`). Legacy/implicit forms are rejected by the
matcher:

- `MOV.64 R0` ✗ → `MOV.64 {R0,R1}` ✓
- `LDC.64 R6` ✗ → `LDC.64 {R6,R7}` ✓
- `STG desc[UR4][R6.64+0x0]` ✗ → `STG desc[{UR4,UR5}][{R6,R7}+0x0]` ✓
- `LDG.E.128 R16` ✗ → `LDG.E.128 {R16,R17,R18,R19}` ✓

Notes:
- A **single register where a 64/128-bit operand is expected** raises the
  "list every register explicitly, e.g. `{R3,R4}`" error, not a silent
  reinterpretation.
- `RZ` is the exception: it encodes as 255 and is never expanded.
- **cuobjdump still *prints* the scalar shorthand** (`HMMA.16816.F32.BF16 R4, R4, R2, R8`,
  `LDG.E.128 ...`); the explicit-group requirement applies to the assembler
  *source dialect* only.  The `tools/decode_*.py` decoders accept the printer
  form.

---

## 5. Dependency checker (`sass_depcheck`)

`assemble`/`assemble_kernel` run a scoreboard/Raw/WAW dependency analysis by
default (`check_deps=True`).  It builds a CFG, classifies each instruction
via the spec's `INSTRUCTION_TYPE`/scoreboard properties, and reports:

- **missing_req** — a consumer reads a register produced by an instruction
  whose scoreboard isn't covered by the consumer's `req` set.
- **stall_too_small** — a true-dependency with insufficient stall.
- **war / raw hazards** around scoreboard reuse.

Diagnostics are printed to stderr in the form

```
[depcheck] k line:4 [missing_req] IADD3 R2, R0, R1, RZ: reads R0 produced by inst 0 (wr=SB0) ...
```

`line:N` is the 1-based source line of the offending instruction.  Warnings
are non-fatal; `strict_deps=True` turns them into errors.  `--no-check-deps`
skips the pass.

**Practical rule**: every producer you read must appear in the consumer's
`req`.  A classic trip-up in the test kernels is an LDG whose *address*
depends on a `S2R` (SB4), a `LDC` (SB1) *and* a desc load (SB0) — the LDG
must carry `req={0,1,4}`; a later store reading the loaded data needs
`req` covering the LDG's scoreboard too.

---

## 6. Running kernels (`assembler.runner`)

```python
from assembler import assemble, CudaModule
mod = CudaModule(assemble(src))
d = mod.devmem_alloc(2048 * 4)               # device buffer
mod.device_write(d, struct.pack("<2048I", *data))
mod.launch("k", grid=(1,), block=(32,), args=[d, sel])
mod.synchronize()
out = mod.device_read(d, 128)
```

- `CudaModule(cubin, device=0)` — loads the cubin (CTypes driver API, no
  nvcc needed at runtime).  Per-parameter byte sizes are extracted from the
  cubin's `EIATTR_KPARAM_INFO` records (size code `(size<<2)|1`), so a launch
  packs each argument at the right width.
- `launch(func_name, grid=(1,1,1), block=(256,1,1), args=[...],
  shared_mem=0, stream=0)` — kernel args are pointers to each argument value:
  an `int`/pointer becomes an 8-byte slot; a `bytes`/`bytearray` argument
  (e.g. a 128-byte tensor-map descriptor) is passed at its full size.
  `func_name` accepts the plain kernel name (auto mangles).
- `devmem_alloc(size)` / `devmem_free(ptr)` / `device_read(ptr,size)` /
  `device_write(ptr,data)` / `devmem_set(ptr,val,count)`.
- The CUDA context is process-global and shared; `reset_context()` tears it
  down.  Do not destroy it inside `CudaModule.__del__` (see source).

---

## 7. Features currently exercised

- **Tensor-core MMA**: `HMMA.16816.F32.BF16/.F16` (m16n8k16) and
  `QMMA.16832.F32.E4M3.E4M3` (m16n8k32 fp8), plus block-scaled
  `QMMA.SF.16832.F32.<f>.<f>.E8 ... Re, Rh, URi` (MXFP8) and `MXQMMA`
  (`S2_6`).  A bit-accurate FDA model lives in `tools/hmma_model.py`.
- **Memory**: `LDG`/`STG` with `.E`/`.U8`/`.U16`/`.32`/`.64`/`.128`, `desc[]`
  descriptor addressing, `LDS`/`STS` (shared, incl. static window
  `#spec_const`), `LDCU` (uniform const load, the sm_120 name of `ULDC`),
  `LDGSTS` (cp.async), `LDSM` (ldmatrix), `ATOMS`, `RED`.
- **Control flow**: `BRA`, `BSSY`/`BSYNC`/`BREAK`, `BSSY`-style labels,
  `EXIT`, `NOP`, barriers `BAR`.
- **Integer/FP**: `IADD3(.X)`, `IMAD(.WIDE/.HI/.X)`, `SHF`, `LOP3`, `LEA`,
  `FADD`/`FMUL`/`FFMA`, `F2FP`, conversions, `MOV32I`/`MOV`, `S2R`, `P2R`,
  uniform ops (`UIADD3`, `ULOP3`, `USEL`, `UMOV`, …).
- **Decoder scripts** (`tools/decode_*.py`) validate encodings against real
  cuobjdump vectors and double as printers for the scalar form.

---

## 8. Known limits & sharp edges

1. **Result wait for MMA (HMMA/QMMA)**: these are
   `INST_TYPE_COUPLED_EMULATABLE` and emit **no write scoreboard**.  Reading
   `Rd` too early faults with `CUDA_ERROR_ILLEGAL_INSTRUCTION` (0x715).
   Use **≥16 NOP after the MMA** before consuming the result (8 NOP is not
   enough with register-immediate operands; an LDG-fed operand that the MMA
   `req`'s delays it enough that 8 NOP can suffice, but 16 is the safe rule).
2. **QMMA srcFmt enum is not the spec's order**: probed values are
   `E4M3=0, E3M4=1, E2M3=2, E5M2=4, E3M2=5, E2M1=6` (grouped by mantissa
   width).  `decode_qmma.py` uses this table.
3. **QMMA fp8 specials**: fp8 inputs carry no NaN/inf specials — the
   all-ones exponent is an *ordinary* exponent (`0x7C` = 384); only the fully
   all-ones byte `0x7F/0xFF` is NaN.  Only the FP32 accumulator propagates
   NaN/inf.  (`HMMA` bf16/f16 *do* have NaN/inf semantics.)
4. **LDCU is the sm_120 name of ULDC** (`ULDC` as written for sm_90 won't
   match).
5. **Scoreboards are SB0–SB5 only**: `wr`/`rd` = 6 is rejected; 7 means
   "none".  A missing `req` is flagged by the dependency checker — read its
   `line:N` diagnostics.
6. **`#param` offsets are computed, not free-form**: `param_base = 0x380`,
   aligned layout.  Two parameters do not land at consecutive 0x358-style
   offsets you might guess; read `AssembleResult.params`.
7. **Fragments for MMA are probed, not from PTX tables**: the m16n8k16/m16n8k32
   slot→matrix layout (4× repetition of each a/b pair) is an *observed*
   equivalence that the FDA model relies on.  It is verified bit-exact but
   not re-derived from the ISA tables.
8. **Parallel test runs drift timing/descriptor tests**: tests that read
   per-stream driver state (`test_cache_desc` uses
   `cuStreamSetAttribute` access-policy windows) or measure cycles are moved
   to the serial set in `tools/run_tests.py`.  When adding a new GPU test,
   prefer independent buffers/streams.
9. **`0f<8 hex>` is the raw FP32 bit literal** (e.g. `0f3F800000` = 1.0).
   Decimal and `0x` integers are accepted for integer immediates.
10. **Errors**: `MatchError` = no variant matched (operand/modifier list
    included in the message); `EncodeError` = matched but the encoding
    failed a `CONDITIONS`/`TABLES_*` legality check.  Both carry enough
    context to act on.
11. **ncu profiling needs `STO_ENTRY` on the kernel symbol**: `st_other` bit 4
    (`0x10`, printed by `cuobjdump -symbols` as `STO_ENTRY`) marks the symbol
    as a kernel entry point.  ptxas sets it; the assembler does too now.
    Without it the cubin loads and runs normally, but ncu's counter-enabled
    replay fails with `LaunchFailed` for kernels that touch memory.  It is a
    flag bit, not a section/symbol index (verified on sm_120: any value with
    `0x10` set passes; regcount and `st_size` are not involved).
