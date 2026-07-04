# AGENTS.md

## What this repo is
Data-only repo: two nvdisasm-dumped ISA description files for the **Hopper (sm_90)** SASS instruction set. There is no build/test/lint — do not look for a package manager, CI, or entrypoints. Work here is *reading and interpreting* these files to reconstruct how to decode SASS instructions (encoding, functional-unit grouping, latencies).

- `sm_90_instructions.txt` (~159k lines) — full instruction/encoding spec.
- `sm_90_latencies.txt` (~441 lines) — pipe grouping, scoreboard/latency tables.

Both are grep-first: never `Read` them whole. Use `grep -n` to locate a section, then read a bounded window.

## Tooling (`tools/`)
A stdlib-only extractor turns the spec into a queryable JSON DB — prefer it over ad-hoc `grep`/manual parsing for structured lookups.
- `python3 tools/parse_sm90.py` — parses both `.txt` files -> `sm90.json` (~21 MB, gitignore-worthy/regenerable). Has a built-in validation gate; a clean run prints `validation OK` with counts: **1589 variants** (1168 `CLASS` + 421 `ALTERNATE CLASS`), **238 mnemonics**, 414 enums, 84 tables, 2309 FUNIT fields, 277 pipe entries.
- `python3 tools/query_sm90.py <cmd>` — query `sm90.json`. Commands: `mnem <NAME>`, `class <name> [-v]`, `opcode <hex|0b|int>`, `layout <class>` (128-bit field map), `fields <regex>`, `enum <Name>`, `table <Name>`, `pipe <MNEMONIC>`, `stats`.
- Regenerate `sm90.json` after any parser change; trust the validation gate (asserts opcode presence + bit ranges ⊆[0,127] + width==Σ span per field).

Parser gotchas already handled (don't reintroduce): sub-section keywords and even the next `CLASS` can be **glued after `;` with no newline** (`;OPCODES`, `ENCODING!..._unused`, `;CLASS "..."`); multiple `BITS_` statements may share one physical line; field names can contain digits, so bit-pairs are consumed until their count equals the declared width; `imad_pseudo_*` classes carry a `REMAP "..."` directive instead of `BITS_` (no opcode field — expected).

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

## Reference (unreliable, use with care)
`~/cs/project/crucible-notes` — AI-generated RE notes on NVIDIA/other toolchains; explicitly "best-guess, not authoritative." The `ptxas/extracted/*.json` files are the most relevant cross-check (e.g. `opcode_pipeline_map.json`, `per_sm_latency_tables.json`, `encoding_*`, `opcode_master.json`). Treat these two txt dumps as the source of truth over the notes when they conflict.
