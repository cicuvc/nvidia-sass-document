# AGENTS.md

## What this repo is
Reverse-engineering repo built around two nvdisasm-dumped ISA description files for the **Hopper (sm_90)** SASS instruction set. There is no build/test/lint — do not look for a package manager, CI, or entrypoints. The work is *reading and interpreting* these files to reconstruct how to decode SASS instructions (encoding, functional-unit grouping, latencies) and writing per-instruction reference docs. Tooling (`tools/`) + research notes (`notes/`) + a doc checklist (`TODO.md`) sit on top of the raw dumps.

- `sm_90_instructions.txt` (~159k lines) — full instruction/encoding spec.
- `sm_90_latencies.txt` (~441 lines) — pipe grouping, scoreboard/latency tables.

Both are grep-first: never `Read` them whole. Use `grep -n` to locate a section, then read a bounded window.

### Current state
- **197/207** compute instructions documented (notes + decoder + test kernel). Only `F2FP` and `RTT` remain unchecked.
- **168 notes** (`notes/`) — 143 per-instruction + 25 cross-cutting / infrastructure notes (pipes, scoreboards, memory model, CBU state, tensor-core microarch, etc.).
- **96 decoders** (`tools/decode_*.py`) — one per documented instruction, each validated against real cuobjdump vectors.
- **103 test kernels** (`tests/*.cu`) — CUDA C / PTX inline-asm kernels that exercise encodings and compile → cuobjdump verification.
- **100 tool scripts** total in `tools/` (incl. `parse_sm90.py`, `query_sm90.py`, decoders, shared libs).

### Phase 2: Refinement (current effort)
Initial doc-writing pass is complete. Next: **tighten the notes** — make descriptions precise and consistent, resolve open questions, consolidate related instructions, and improve cross-references. Guidelines below.

## Tooling (`tools/`)
A stdlib-only extractor turns the spec into a queryable JSON DB — prefer it over ad-hoc `grep`/manual parsing for structured lookups.
- `python3 tools/parse_sm90.py` — parses both `.txt` files -> `sm90.json` (~21 MB, gitignore-worthy/regenerable). Has a built-in validation gate; a clean run prints `validation OK` with counts: **1589 variants** (1168 `CLASS` + 421 `ALTERNATE CLASS`), **238 mnemonics**, 414 enums, 84 tables, 2309 FUNIT fields, 277 pipe entries.
- `python3 tools/query_sm90.py <cmd>` — query `sm90.json`. Commands: `mnem <NAME>`, `class <name> [-v]`, `opcode <hex|0b|int>`, `layout <class>` (128-bit field map), `fields <regex>`, `enum <Name>`, `table <Name>`, `pipe <MNEMONIC>`, `stats`.
- Regenerate `sm90.json` after any parser change; trust the validation gate (asserts opcode presence + bit ranges ⊆[0,127] + width==Σ span per field).

Parser gotchas already handled (don't reintroduce): sub-section keywords and even the next `CLASS` can be **glued after `;` with no newline** (`;OPCODES`, `ENCODING!..._unused`, `;CLASS "..."`); multiple `BITS_` statements may share one physical line; field names can contain digits, so bit-pairs are consumed until their count equals the declared width; `imad_pseudo_*` classes carry a `REMAP "..."` directive instead of `BITS_` (no opcode field — expected).

## Documentation workflow (current effort)
Goal: write a per-instruction reference doc for every **compute** SASS instruction. Split across sessions.
- `TODO.md` — the master checklist (**197/207 instructions** done), grouped into 10 categories: **Integer/Vector**, **FP32**, **FP16**, **FP64**, **Convert**, **Uniform**, **Memory**, **Tensor**, **Control Flow**, **Misc**. Derived from `ref_memo.txt` (the curated sm_70..sm_90 opcode roster). Texture/surface/graphics instructions and pseudo/lowered opcodes are intentionally excluded (see its "Excluded" section). `-> MNEM` tags map ref_memo names to the canonical sm_90 mnemonic (shape/width/uniform/extended variants collapse to one instruction, so their docs may be consolidated). `LDCU` is unresolved (likely an LDC variant).
- `notes/*.md` — per-instruction reference docs (143) + cross-cutting topic notes (~25: `scoreboards.md`, `memory_model.md`, `cbu_state.md`, `iswz.md`, `hmma_pipeline.md`, `div.md`, `fp64_control.md`, `tma_mbarrier.md`, `tensorcore_microarch_speculation.md`, etc.). Each records: spec-grounded facts, external-reference reconciliation, empirical corroboration (cuobjdump mining), and open questions. Follow this style for new findings.
- Tick the box in `TODO.md` when done.
- `sm90.json` is gitignored/regenerable; `ref_memo.txt` uses a ROT13 column that is not the mnemonic (mnemonic is the 3rd column).

### Phase 2 — Refinement workflow
With the first doc pass complete, focus shifts to **note quality and consistency**:
1. **Cross-check descriptions** against `notes/` sibling instructions — e.g. VIMNMX vs IMNMX, VSADD vs VABSDIFF, all MMA variants consistent in terminology.
2. **Resolve open questions** — many notes have `## Open questions` sections; answer or prune stale ones.
3. **Consolidate** related instructions (e.g. HADD2/HADD2_F32 into one note, DADD/DADD_F64, IMAD/IMAD_WIDE/IMAD_HI/IMAD_X).
4. **Verify encodings** — run decoder round-trips against real cuobjdump vectors (decoder scripts should all pass).
5. **Improve cross-references** — link between notes (e.g. SHF → PRMT, I2FP → I2F, RED → ATOMS).

Key conventions for notes:
- Record both spec-derived facts AND empirical observations
- If the compiler does something unexpected (lowers to different instruction, prefers uniform regs, skips a variant), document it
- When an instruction exists in spec but ptxas doesn't emit it (e.g. IMNMX on sm_90), document the relationship and the arch that does emit it
- Latency tables: map the instruction's pipe to the correct row in TABLE_TRUE/TABLE_OUTPUT/TABLE_ANTI

### Per-instruction documentation steps (the repeatable recipe)

Follow this flow for every new instruction. Each step feeds the next; skip a step = miss a detail.

**Step 1 — Spec lookup (`query_sm90.py`)**
```bash
query_sm90.py mnem <NAME>        # variant count, opcodes, format preview, pipe
query_sm90.py pipe <NAME>        # pipe membership (maps to latency section)
query_sm90.py class <name> -v    # full CLASS block: FORMAT, slots, PROPERTIES, PREDICATES, CONDITIONS, ENCODING
query_sm90.py layout <class>     # 128-bit field map (table + ASCII visual)
```
From the CLASS output, read:
- `FORMAT` — slot names & their types (Register, Predicate, UniformRegister, F32Imm, etc.)
- `ENCODING` — exact bit positions; note gaps, `*<n>` fills, TABLE-based fields (opex)
- `PROPERTIES` — INSTRUCTION_TYPE, IDEST_SIZE, ISRC_A/B/C/E_SIZE (0 = absent operand)
- `PREDICATES` — operand sizes that feed latency connector math
- `CONDITIONS` — register-range constraints and illegal-encoding guards

**Step 2 — Enum cross-check**
```bash
query_sm90.py enum <TypeName>    # modifier value maps: FCMP, MUFU_OP, REDUX_SZ, Round1, ...
```
Map each format modifier to its numeric encoding. Note any `INVALID*` values that trigger `ILLEGAL_INSTR_ENCODING_ERROR`.

**Step 3 — Disassembly hunting (cuobjdump)**
```bash
# Check cublas for real-world usage (fast grep; timeout if needed)
cuobjdump -arch sm_90 -sass /usr/local/cuda/lib64/libcublas.so | grep -A1 "<MNEMONIC>" | head -20

# Check both hex lines — sm_90 is 128-bit: lo64 (first /*...*/) + hi64 (second /*...*/)
# Decode one by hand to confirm opcode bits [91]∥[11:0] match the spec
```
Collect a few representative encodings: plain form, negated operand, all modifier combos visible.

**Step 4 — Write a test kernel (`tests/<mnem>_test.cu`)**

Cover every observable variant + modifier:
- Plain form (C++ or PTX inline asm)
- Negate/absolute on each source operand
- Each rounding mode (.RM, .RP, .RZ, .RN default)
- Saturation (.SAT)
- Flush mode (.FMZ/.FTZ if applicable)
- Immediate operand (trigger RIR/RRI variant)
- Uniform register variant (trigger RUR/RRU by loading params into uniform regs via `ULDC` — ptxas on sm_90 often does this automatically for kernel parameters)

For instructions the compiler won't emit from C/C++ (e.g. legacy IMNMX on sm_90), try:
- `nvcc -arch=sm_75` (older arch may emit different mnemonic)
- PTX inline asm with the exact PTX mnemonic
- If neither works, document the compiler's chosen mnemonic (e.g. VIMNMX vs IMNMX) and note it as a relationship

**Step 5 — Compile & disassemble**
```bash
nvcc -arch=sm_90 -O3 -cubin -o tests/<mnem>_test.cubin tests/<mnem>_test.cu
cuobjdump -arch sm_90 -sass tests/<mnem>_test.cubin
```
Verify: every case generated the expected SASS mnemonic. If some cases lowered to different instructions (e.g. `-a*b` → FFMA instead of FMUL, or compiler split into UISETP+USEL), record the pattern in the note.

**Step 6 — Write a decoder (`tools/decode_<mnem>.py`)**

Minimal Python script that:
- Extracts fields from lo64+hi64 via bit positions from ENCODING
- Reconstructs the full SASS assembly as cuobjdump would print it
- Validates against the test vectors from Steps 3 & 5
- Prints match/mismatch for each test vector

Spec essentials:
- 128-bit instruction = hi64 (bits [127:64]) + lo64 (bits [63:0])
- Opcode is 13-bit: `{bit[91], bits[11:0]}`
- Bit positions in `BITS_<width>_<hi>_<lo>` are MSB:LSB, so extract MSB-first
- Registers: 8-bit for normal (R0–R255, where 0xFF=RZ), 6-bit for uniform (UR0–UR63)
- Predicates: 3-bit (P0–P6, 7=PT), plus a 1-bit `.not` at the adjacent position
- Immediate floats: 32-bit IEEE754 at [63:32], big-endian (use `struct.unpack('>f', struct.pack('>I', val))`)

**Step 7 — Write the note (`notes/<mnem>.md`)**

Structure (follow existing notes for consistency):
```
# MNEMONIC — One-line description
**Opcode mnemonic:** ...  |  **Pipe:** ...  |  **INSTRUCTION_TYPE:** ...
## Semantics
## Variant overview (table with opcodes)
## Modifiers (table with field positions)
## Bit layout (128-bit map)
## Cross-comparison (vs related instructions, if applicable)
## Latency (from sm_90_latencies.txt)
## Verified encodings (table with Lo64/Hi64 → Disassembly)
### PTX→SASS mapping
## Open questions
```

**Step 8 — Tick TODO**
```markdown
- [x] **MNEMONIC** (idx N) — description
```

Key conventions for notes:
- Record both spec-derived facts AND empirical observations
- If the compiler does something unexpected (lowers to different instruction, prefers uniform regs, skips a variant), document it
- When an instruction exists in spec but ptxas doesn't emit it (e.g. IMNMX on sm_90), document the relationship and the arch that does emit it
- Latency tables: map the instruction's pipe to the correct row in TABLE_TRUE/TABLE_OUTPUT/TABLE_ANTI

## Critical gotchas
- The header says `ARCHITECTURE "Volta"` and `WORD_SIZE 64`, but this is the **sm_90** file and each SASS instruction is **16 bytes / 128 bits** (`FUNIT uC` -> `ENCODING WIDTH 128`; bit positions in `BITS_*`/`FUNIT` masks run [127:0], MSB-left). Trust the 128-bit width, not `WORD_SIZE`.
- Opcode names carry a pipe suffix in the latency file (e.g. `IADD3` and `IADD3int_pipe` are the same op; the suffixed form is the pipe-bound variant). Both appear in OPERATION SETS.
- "Illegal encoding" tables (`TABLES_*_illegal_encodings`) map input tuples to error codes; they are *rejections*, not valid decodes.

## `sm_90_instructions.txt` layout (locate via `grep -n`)
Top-level sections in order:
- `ARCHITECTURE` / `RELOCATORS` (line 1+) — ELF ids and `R_CUDA_*` relocation bitfields.
- `PARAMETERS`, `CONSTANTS` (~158+) — enums referenced everywhere: `VQ_*` (virtual queue / functional unit), `INST_TYPE_*` (scoreboard class), `IOPERAND_TYPE_*`, `IERROR_*`, `ISHADER_*`.
- `REGISTERS` (~307) — register-class and `SIDL_NAMES` definitions.
- `TABLES`, then many `TABLES_<name>` (~1771+) — reusable decode tables (e.g. `FixLatDestMap`, `DestPred`, `IntSize`) plus per-opcode `TABLES_mem_*`, `TABLES_opex_*`, `TABLES_op_*`, `TABLES_URb_*`; `*_illegal_encodings` list forbidden tuples.
- Enum definitions (~1326+) — modifier value maps like `ATOMICINTSIZES "U32"=0 ...`, `UniformRegister "UR0"=0 ...`. These decode modifier/subop fields to names.
- `OPERATION PROPERTIES` / `OPERATION PREDICATES` (~5042) — the list of per-class property/predicate keys.
- `FUNIT uC` (~5106) — control-bit bitfield layout. Each line is `Name '<128-char mask>'` where `X` marks the bits (MSB-left). This is the schedule/control-word field map (e.g. `Pred`, `PredNot`, `Dest`, `RegA/B/C`, `Imm32`, `Sync`, `NODEP`).
- `CLASS "..."` blocks (~7422 onward, **1168 primary + 421 `ALTERNATE CLASS` = 1589 encoding variants**; note one `CLASS` is glued after a `;`, so `grep "^CLASS "` undercounts by 1) — one per instruction encoding variant.

### Anatomy of a `CLASS` block (the core decode unit)
Each `CLASS` has these sub-sections:
- `FORMAT` — assembler syntax template of named **slots** written `Type("default"):slotname` (modifiers use a leading `/`, e.g. `/AIO("I"):io`; operands like `Register:Rd`, `SImm(11)*:Ra_offset`). The `slotname` after the `:` is exactly the identifier used on the RHS of `ENCODING` `BITS_...=` lines, and `Type` is the enum from the value-map section (`AIO`, `AInteger`, ...) that converts the mnemonic to the field's numeric value. See "FORMAT->ENCODING" below.
- `CONDITIONS` — legality assertions. Each is `<ERROR_TYPE>` / `<predicate>` `:` / `"message"`; the **predicate must hold, and the named error fires when it is FALSE** (e.g. `OOR_REG_ERROR` lists the *valid* register set). `ERROR_TYPE`s and their severity (`ERROR`/`WARNING`/`INFO`) are declared in the header `CONDITION TYPES` block (~line 136). Predicate language: FORMAT slot names as operands (`Rd`, `sz`, `io`, ...); `` `Type@value `` enum-literal compares (`` sz==`AInteger@"64" ``, `` Rd==`Register@RZ ``); `%NAME` = `PARAMETERS`, `$NAME` = `CONSTANTS`; `A -> B` implication (gates a requirement on a modifier/size slot); `DEFINED TABLES_x(...)` / `!DEFINED TABLES_x_illegal_encodings(...)` table-membership guards. Size-driven idiom: `(sz==`AInteger@"64") -> (Rd==RZ || Rd<=%MAX_REG_COUNT-2)` (multi-reg operands need room + N-alignment); `(Rd+(Rd==`Register@RZ))%2` adds 1 so `RZ` always passes.
- `PROPERTIES` — `INSTRUCTION_TYPE` (`INST_TYPE_*`), `MEM_SCBD*`, `VALID_IN_SHADERS`, per-operand `*_OPERAND_MAP`/`*_OPERAND_TYPE`.
- `PREDICATES` — operand sizes (`ISRC_A_SIZE`, `IDEST_SIZE`, ...) that drive register-range math (`RaRange` etc.).
- `OPCODES` — exactly two lines, `<name><pipe_suffix> = <op>;` and `<name> = <op>;`, both the same value. The opcode is a **13-bit** field but the `0b` literal drops leading zeros (e.g. `ACQBULK = 0b100000101110;` and `ALD = 0b1100100001;` both fill the same 13-bit slot).
- `ENCODING` — the bit-to-field mapping. Field names encode their bit position:
  `BITS_<width>_<hi>_<lo>[_<hi2>_<lo2>...]_<name> = <source>;`
  e.g. `BITS_3_14_12_Pg = Pg` (3 bits, [14:12]). `<hi>_<lo>` may repeat to span disjoint bitfields: the opcode is always `BITS_13_91_91_11_0_opcode` = bit [91] (MSB) concatenated with [11:0]. RHS may be a literal, a modifier field, `*<n>` (default/reserved), or a `TABLES_*(...)` lookup.

### FORMAT->ENCODING (how slots become bits)
The `ENCODING` RHS references `FORMAT` slot names. Verified RHS forms:
- `slotname` — value parsed for that slot; converted via the slot's enum `Type` (e.g. `AIO "I"=0,"O"=1` -> `BITS_1_79_79_op=io`).
- `slotname@attr` — an operand sub-attribute: `Pg@not` (predicate negate), `Sb@negate`/`Sb@absolute` (const-operand `[-]`/`[||]`).
- `TABLE(slot,...)` — one or more slots re-encoded through a `TABLES_*`/relocator fn; the LHS may list several `BITS_` targets at once, e.g. `BITS_5_58_54_Sb_bank,BITS_14_53_40_Sb_offset = ConstBankAddress2(Sb_bank,Sb_addr)`. Multiple slots can also fuse into one field: `BITS_8_..._opex=TABLES_opex_0(batch_t,usched_info)`.
- `*<n>` (`*7`,`*0`,`*255`) — fixed/reserved fill when no operand drives the field (an optional `$(...)$` scoreboard group absent -> `*7`; present -> `VarLatOperandEnc(src_rel_sb)`).
- `*<slotname>` — a slot the class pins/reserves rather than freely encoding (e.g. `*Ra` when `Ra` is constrained to `RZ`/non-`RZ`; `*dstfmt.srcfmt` mandatory discriminator with no default).

## `sm_90_latencies.txt` layout
- `OPERATION SETS` — functional-unit pipe membership: `int_pipe`, `mio_pipe`, `fe_pipe`, `fmalighter_pipe`, `fp16_pipe`, `cbu_pipe`, `fma64lite_pipe`, `fma64heavy_pipe`, `udp_pipe`, plus derived sets via set algebra (`FXU_OPS = int_pipe + fe_pipe - ...`). This is the authoritative **functional-unit grouping**.
- `HARD RESOURCE`, `CONNECTOR NAMES`, `CONNECTOR CONDITIONS`/`SETS` — register files (`GPR`, `UGPR`) and per-operand range formulas keyed on the `*_SIZE` predicates from the instruction file.
- `TABLE_TRUE` / `TABLE_OUTPUT` / `TABLE_ANTI` (GPR and UGPR) — producer×consumer **latency matrices** (true/output/anti dependency cycles). Rows/columns are pipe-group×operand-role; the trailing numbers are latencies in cycles.

The `*_SIZE`/`*Range` predicates tie the two files together: instruction `PREDICATES` set sizes, latency `CONNECTOR CONDITIONS` convert them to register spans used to index the latency tables.

## PTX→SASS quick reference (`~/cs/project/documented-ptx/`)
NVIDIA PTX ISA 9.3 documentation converted to markdown, plus empirical PTX→SASS mapping files. Use these when documenting an instruction to map user-visible PTX constructs to the SASS encodings studied here.

- `ptx2sass-int-mad.md` — `mad`/`mul`/`mad.cc`/`madc` → IMAD/IMAD.WIDE/IMAD.HI/IMAD.X/UIMAD (verified sm_90, CUDA 13.1).
- `ptx2sass-int-add.md` — `add`/`sub`/`add.cc`/`addc` → IADD3/IADD3.X/UIADD3 (verified sm_90, CUDA 13.1).
- `instructions/` — per-PTX-instruction reference files (216 files).
- `09.7.*.md` — per-instruction-family PTX spec chapters.

Workflow: when documenting a SASS instruction, first check this dir for a PTX mapping file. If none exists for that instruction family, create one by writing a small CUDA kernel → `nvcc -arch=sm_90 -O3 -cubin` → `cuobjdump -arch sm_90 -sass` → cross-reference with `tools/query_sm90.py opcode <hex>`.

## Reference (unreliable, use with care)
`~/cs/project/crucible-notes` — AI-generated RE notes on NVIDIA/other toolchains; explicitly "best-guess, not authoritative." The `ptxas/extracted/*.json` files are the most relevant cross-check (e.g. `opcode_pipeline_map.json`, `per_sm_latency_tables.json`, `encoding_*`, `opcode_master.json`). Treat these two txt dumps as the source of truth over the notes when they conflict.
