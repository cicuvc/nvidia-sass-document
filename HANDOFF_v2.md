# HANDOFF_v2.md — typed-IR migration status & next tasks

Status snapshot for anyone resuming the **decoded-IR migration** in `semu/` (SM120
SASS simulator, CUDA-agnostic C++20). The 2b checkpoint is committed, and 2b-3
(the typed-storage cleanup) is **nearly final**: all interpreter families read
the typed `Decoded*` storage and 3 of the 4 generic base vectors are deleted
(only `raw_fields` remains, for the unsurfaced S2R `imm8` / BAR `barname`
fields). Debug/ASan gates green 36/36. The migration continues in small,
gated-green increments; this doc records **where we are** and the exact next
operation.

---

## 1. Project context (backend)

- `semu/` implements the sm120 decoder + interpreter + profiler/debugger; root
  AGENTS.md = sm90 reverse-eng; `semu/AGENTS.md` = semu build/test standards.
- Build toolchain: **Clang 23** at `/opt/LLVM-23.0.0git-Linux-X64/` (g++ + its
  asan/tsan were too slow). All 4 trees (`build`, `build-asan`, `build-tsan`,
  `build-rel`) are configured with that clang.
- Python for gates: **conda env `blkw`** — run gates with
  `export PATH="/home/cicuvc/miniconda3/envs/blkw/bin:$PATH"` and
  `export L1TEX_ARCH_DIR=/home/cicuvc/cs/projects/arch/l1tex`.
- Main gate: `tools/run_semu_cpu_gate.sh <build_dir>` — **36 items**; must be all
  green on all three trees. (`g++`/`ctest` also exist but the gate script is the
  standard.)

---

## 2. The migration goal (from design discussions)

Currently every decoded instruction is one **generic** `semu::DecodedInstruction`
holding four `std::vector`s:
`operands (vector<Operand>)`, `modifiers (vector<string>)`,
`slot_values (vector<pair<string,uint64>>)`, `raw_fields`.

Goal: **type-specialized decoded IR** — shared info in a base
`DecodedInstruction`, per-instruction data as strongly-typed fields in derived
types, no generic vectors. User decisions locked in:

1. **Storage** = `vector<DecodedInstruction*>` (`PredecodedWord::inst` is a
   `std::unique_ptr<DecodedInstruction>`).
2. **Type layering**: first by **mnemonic**, then by **operand count**. e.g.
   `FFMA d,a,b,c` and `IADD3 d,a,b,c` are different types (different mnemonic);
   `FFMA Rd,Ra,URb,Rc` and `FFMA Rd,Ra,Rb,Rc` are the SAME type (same mnemonic,
   same operand count) — the operand-kind difference is runtime (`OperandKind`).
   → **425 derived types** `Decoded<Mnemonic><Ops>` (operand counts 0..9).
3. **Operands** = positional union `OperandValue ops[N]` (no slot-id; kind+flags
   in the element), positions = canonical role order per mnemonic. **16-bit
   immeds sign-extended to 32 bits.**
4. **Modifiers** = **reusable enums** (395) as typed members of the specialized
   derived type (NOT in the shared base, because they differ a lot between
   instructions). Human-readable, no slot/LUT indirection.

---

## 3. Completed history and current checkpoint

| Commit | Content |
|--------|---------|
| `44cc30b` | `DecodedInstruction`: mnemonic/variant_class/pipe → generated `isa::{Mnemonic,VariantClass,Pipe}` enums; `disasm`/`disasm_full` removed (rendered on demand via `Decoder::disassemble`); `kConds` legality conditions compiled into **one merged per-variant lambda** `(const Word128&, slots)->std::optional<CondResult>` at gen time (decoder never runtime-parses predicates); added `cond_compile_equiv` gate (emitted C++ vs `sass_cond` on random slot maps), gate 35→36 items; ABI v1→v2. |
| `05b70a2` | Switch builds to **Clang 23**; fix Clang-`-Werror`-only issues (unused-private-field in `l2_events.hpp` → `[[maybe_unused]]`; generated `isa_data.cpp` scoped `-Wno-constant-logical-operand`/`-Wno-overlength-strings` in `src/CMakeLists.txt`; remove dead `kParamKeys`/`kConstKeys`; `[[maybe_unused]]` on generated table helpers). Add `gen_isa.py --shapes` → `isa_shapes.hpp` (OperandValue union + 394 modifier enums + 425 `Decoded<Mnemonic><Ops>` types). |
| `2316f6c` | **Storage → vector-of-pointers**: `PredecodedWord::inst` = `std::unique_ptr<DecodedInstruction>` (deep-copyable + movable); `DecodedInstruction` gains `virtual ~` (polymorphic prep); update all `.inst` → `->` sites; ABI v2→**v3**. Also `--shapes` now emits per-variant **ShapeManifest** (`kShapeManifests`, indexed by `kVariants` index: slot→(pos, kind)); `gen_corpus.py --hpp` → `isa_corpus.hpp` (1414 canonical words). |
| `15acc1f` | **2a typed-fill**: `gen_isa --shapes` also emits `isa_shapes_fill.hpp` — per-variant fillers (`fill_by_variant(kVariants-index, FillIn, void*)`) that populate a typed `Decoded*` (ops[] + modifier members) from an opaque `FillIn` (decoded slot source). Added `include/semu/shape_in.hpp` (FillIn + `operand_set_value` kind→union setter). Representative equivalence test. |
| `553699d` | **2a complete**: whole-1414-corpus equivalence — `typed_fill_matches_across_corpus` decodes every `isa_corpus.hpp` word, fills a typed `Decoded*`, reads ops[0..n) via offset-0 overlay, and asserts value+kind+flags == live `slot_values`/`operands`. Caught + fixed a F-imm union read-width bug. |
| working tree (2026-08-20) | **2b checkpoint**: generated shapes now derive from `DecodedInstruction`; decoder allocates/fills the concrete shape through `make_by_variant` + `fill_by_variant`; `DecodeResult` and `PredecodedWord` preserve the dynamic type through `clone()`; ABI is v4. The interpreter bridge reads typed operands through `ShapeManifest` and typed modifiers through generated `slot_value_by_variant`. Generic vectors remain only as a temporary compatibility bridge. |
| `d206a4a` | **2b-3 step 1 (migration begin)**: add `include/semu/decoded_access.hpp` — `op_lookup`/`op_value`/`op_kind`/`op_flag` read an operand role straight out of the typed `Decoded*` ops[] via `ShapeManifest` (slot→position), and a `shape::slot_value` wrapper over generated `slot_value_by_variant`. These replace the `const Operand*`/generic-vector contract (no base `operand_cache`, no vector scan). Migrate the **uniform/ALU control family** (`do_mov`/`do_umov`/`do_uiadd3`/`do_ushf`/`do_iadd3`/`do_isetp`/`do_imad`) off `find_op`/`field_value`/`const Operand*` onto `read_reg_slot`/`read_ur_slot`/`read_pred_slot` + `shape::op_value`/`shape::op_flag`/`shape::slot_value`. Add `decoded_access.hpp` to the per-header compile list. Debug+ASan gates 36/36. |
| `3c2cb2e` | **2b-3 step 2**: migrate `do_tensor` (HMMA/QMMA/OMMA) to the typed accessors (`shape::op_value` bases + `op_lookup`/`read_reg_slot`/`read_ur_slot` for Re/Rh/URi). Debug gate 36/36. |
| `7ec42dd` | **2b-3 step 3**: migrate the entire `do_compute` (~40 operanded blocks) to typed accessors — every FP/convert/collective/integer block reads via `shape::op_value`/`op_kind`/`op_flag` + `bind_reg_slot`/`read_reg_slot`/`read_pred_slot`/`write_pred_slot`/`write_rd_slot`. Removed the last legacy `Operand*` readers (`bind_reg_index`, `read_pred`, `write_pred`, `write_rd`). Immediate slots (Sb/Sc/imm8) classified UImm/SImm exactly as before (a roster dump of per-mnemonic ShapeManifest role slots made this safe). Debug gate 36/36. |
| `2e0c2a9` | **2b-3 steps 4-6 (vector deletion)**: migrate `do_memory`/`resolve_mem_addr`/`do_ldgsts`/`do_syncs`/`do_arrives`/`do_tma` (deleted `find_op`, `read_reg_val`, `read_ur_val`, `read_ur_pair`, `read_addr_pair`). DELETE the generic `operands` / `modifiers` / `slot_values` vectors + the bounded `operand_cache` and the `Operand` struct from `DecodedInstruction`. `render_instruction` no longer builds them; modifier text is rendered on demand from the decode context (`render_modifiers`). CLI `decode-json` and `test_decoder`/`compile_api_test` migrated to the typed surface (whole-corpus typed-fill is now a typed-storage interception, not a generic-path duplicate). `raw_fields` stays on the base (see below). Debug **and ASan** gates 36/36. |

**2b-3 status: 3 of 4 vectors deleted; `raw_fields` is the remaining slice.**

**2b-3 migration lessons (folded in, do not reintroduce):**
- The RIR/RRI immediate's **canonical SLOT name is `Sb`** (the raw FIELD is named `Ra_offset`). `slot_value("Ra_offset")`/`op_value("Ra_offset")` return nullopt for those variants — read `Sb` instead.
- In `do_uiadd3`, **`URc==255` (UZ) is the encoder's "no third reg" pin** that must fall through to the `Sb` immediate; routing on operand *presence* instead of *value==255* silently drops the addend.
- The legacy `read_op` helper was fully removed once its last caller migrated; `bind_reg_slot` must be re-added when `do_compute` is migrated (kept out to stay -Werror-clean).

**2a conclusion (proven by test):** the generated typed `Decoded*` fill is
semantically equivalent to the current generic decoder **across the whole ISA**.

---

## 4. Generated artifacts (commit-owned; regen targets)

- `semu/generated/isa_data.{hpp,cpp}` — core decode tables + condition thunks
  (regenerate: `python3 semu/tools/gen_isa.py`). **isa_regen gate** checks byte
  determinism vs committed.
- `semu/generated/isa_shapes.hpp` (schema: OperandValue/modifier enums/425
  types/ShapeManifest), `isa_shapes_fill.hpp` (per-variant fillers, allocation,
  typed slot accessors),
  `isa_corpus.hpp` (1414 words) — regenerate with:
  `python3 semu/tools/gen_isa.py --shapes` and
  `python3 semu/tools/gen_corpus.py --hpp semu/generated/isa_corpus.hpp`.
  These are NOT checked by `isa_regen` (only isa_data is); they're design/2a
  artifacts, now used by decoder/interpreter code and `test_decoder.cpp`.
- Hand-written glue: `include/semu/decoded_base.hpp`, `include/semu/shape_in.hpp`,
  and **`include/semu/decoded_access.hpp`** (2b-3: `op_lookup`/`op_value`/
  `op_kind`/`op_flag` + `shape::slot_value` wrappers over the typed ops[] /
  `slot_value_by_variant`, the replacement for the former `const Operand*` contract).
  Also per-family typed slot readers live in `src/interpreter.cpp`
  (`read_reg_slot`/`read_ur_slot`/`read_pred_slot`).

---

## 5. NEXT TASK — Step 2b: make typed storage the main path

**Objective:** stop building the generic vectors; the decoder actually allocates
a derived `Decoded*`, fills it (reuse `isa_shapes_fill.hpp`), deletes the four
vectors from `DecodedInstruction`, and migrates the interpreter to read typed
fields positionally / via strong-typed modifier members.

### 2b sub-parts (suggested order, keep gates green each step)

**2b-1: Transition bridge — DONE in the current checkpoint.**
The bridge works over typed derived storage, so the existing interpreter call
sites keep compiling:
- `find_op` returns `const Operand*` today (122 sites dereference
  `.value/.negated/.absolute/.kind/.slot`). This contract does not map cleanly
  onto a union array, so **2b-1 = introduce value/flag-returning accessors**
  (`op_value(inst,"Rb")`, `op_flag(inst,"Rb",neg|abs|not)`, `op_kind(inst,"Rb")`,
  `slot_value(inst,"sz")`) backed by the typed storage + per-variant `ShapeManifest`,
  The existing 122 `find_op` and 71 `slot_value` call sites are kept compiling
  through the bridge. The current compatibility `Operand*` result is materialized in a bounded
  base-owned cache; normal decoded instructions no longer scan `inst.operands`.
- Modifier reads are served by generated `slot_value_by_variant`; this is the
  temporary table-driven bridge before direct per-family typed-member reads.

**2b-2: decoder storage swap — DONE in the current checkpoint.**
`render_instruction`/decode allocates the correct derived `Decoded<Mnemonic><N>`
(via `fill_by_variant` + a per-variant type-allocate dispatch) and sets it into
`PredecodedWord::inst` (already `unique_ptr<DecodedInstruction>`). The four
generic vectors are not deleted yet; that is the next cleanup slice.

**2b-3: cleanup + ABI — ABI DONE; vector cleanup PENDING.**
- `render`/`Decoder::disassemble(word)` already re-decodes from `isa_data` and
  does NOT read the vectors → unaffected.
- Bump `kDecodedIrVersion` 3→4 (breaking: typed dynamic storage became the main
  path; vector removal remains pending within v4).
- Update the two freeze-marker tests (`compile_api_test.cpp`,
  `test_mock_backend.cpp`) asserting the version.

### 2b-4: gate/verification
Full three-tree gate must stay 36/36. The existing whole-corpus typed-fill test
is the safety net: once the decoder produces the typed `Decoded*` as main
storage, that test effectively asserts main == expectations. Add:
- a check that the typed main-storage path is what the interpreter consumes
  (decode → execute unchanged behavior on the interp/fuzz/tensor gates);
- remove the generic-vector path in the pending cleanup slice after the typed
  bridge has been migrated off the compatibility cache.

**Open design notes for the next cleanup slice:**
- Remove `operands`, `modifiers`, `slot_values`, and `raw_fields` from the base;
  first grep all remaining consumers, especially debugger/mock-backend/render
  paths, then make typed accessors the only interpreter path.
- Replace the temporary `Operand*` cache/find-op compatibility layer with value,
  flag, and kind accessors. Group the mechanical rewrite by interpreter family:
  `do_compute`, `do_memory`, `do_tensor`, `do_s2ur`, and control flow.
- Replace generated name-based modifier lookup with direct typed-member access
  where practical; retain one generated typed fallback only for families whose
  modifier member names differ across variants.
- Update tests that currently use generic `FillIn`/vector equivalence so the
  whole-corpus assertion intercepts the actual typed main-storage object rather
  than maintaining a duplicate generic path.
- Keep 16-bit sign-extension rule in `operand_set_value`/typed op reads.

---

## 6. Gotchas / conventions (carry-over)

- 128-bit words: hi64 bytes at `[127:64]`, lo64 `[63:0]`; opcode = `{bit[91],bits[11:0]}`.
- `DecodedInstruction` is now polymorphic (`virtual ~`); `PredecodedWord::inst` is
  a deep-copyable `unique_ptr` whose copy path must call virtual `clone()`.
- `Array` `isa::kVariants` order == `build_variants(db)` order ==
  `shape::kShapeManifests` index order — keep them aligned when adding manifests.
- Generated files: don't hand-edit; regen + commit. `isa_data` is determinism-gated
  (isa_regen); shapes/corpus are not — keep them regenerated in the same commit.
- Clang `-Werror` is stricter than GCC: new generated code must be warning-clean
  (watch unused params/vars, constant-logical-operand, overlength-strings).
- Run gates with the `blkw` python + `L1TEX_ARCH_DIR` (see §1).

---

## 7. Current status / next operation

**2b is FINAL — done-good met.**  All interpreter families read the typed
`Decoded*` storage; ALL four generic vectors (`operands`/`modifiers`/
`slot_values`/`raw_fields`) plus the `Operand` struct and `operand_cache` are
deleted from `DecodedInstruction`; `render_instruction` builds no generic
vectors (modifiers render on demand from the decode context); the few
unsurfaced ENCODING fields (S2R `imm8`, BAR `barname`) are read straight from
the word via `field_value` (interpreter.cpp).  **Debug / ASan / TSan gates are
green 36/36.**  ABI remains v4; the freeze-marker tests were updated.

Committed: d206a4a, 3c2cb2e, 7ec42dd, 2e0c2a9, 20dac82 (+ docs 379e42d,
beb79c4).

Remaining (optional, NOT required for 2b):
1. Optional polish: the anonymous `slot_value` shim in interpreter.cpp is
   redundant with `shape::slot_value` — can be aliased/removed.
2. Pre-existing (untested) slot-name quirks preserved by the do_compute
   migration — fixing them is separate follow-up work: ISCADD still reads the
   shift from an absent "Ra_offset" role (shift stays 0); FRND still reads an
   absent "Ra" (source stays 0); FFMA/FSETP F32-bit immediates (kFImm32) are
   still excluded from the UImm/SImm immediate path.
3. A future slice could specialize hot interpreter paths further (direct
   typed-member modifier reads instead of the generated `slot_value_by_variant`
   string lookup) — the 2b design keeps the generated reader as the typed
   bridge.

## 8. Done-good definition for 2b
**MET (2026-08 session; Debug/ASan/TSan 36/36).**
- `DecodedInstruction` has no `operands/modifiers/slot_values/raw_fields` vectors.
- decode allocates/consumes the typed `Decoded*` via `PredecodedWord::inst`.
- interpreter reads operands positionally / modifier members typed (no per-opname
  scan; no `const Operand*`).
- ABI v4; freeze-marker tests updated.
- Three trees (Debug/ASan/TSan) pass the full 36-item gate; whole-corpus
  typed-fill interception no longer needed as a separate duplicate path
  (it now intercepts the actual typed main storage).

---

## 9. 2b-3 plan-b — eliminate ALL string lookups on the interpreter execution path

**Goal (user requirement, 2026 session):** interpreter reads operands and
modifiers purely as **direct typed members / positional `ops[]`** — no slot-name
string matching, no slot-id comparisons anywhere on the execution path.  This
supersedes the earlier `decoded_access.hpp` slot-name bridge for the
interpreter (the bridge stays for decode-only / tests).

**Generator support (committed):** `gen_isa.py --shapes` now emits a
`std::uint8_t subclass;` member on every `Decoded<Mnemonic><N>` type, filled at
decode time from the CLASS name (bit0 `_x`, bit1 `wide`, bit2 `hi`, bit3
`imm64`, bit4 `_fp`), and a typed `barname` member on the BAR types.  Used by
do_imad (wide/hi/x), do_umov (imm64), decode_atomic_op (_fp) — replaces the
variant-class `strstr`.  The dead `RED`/`BFE`/`BFREV` mnemonic `strcmp`s were
deleted (those mnemonics do not exist in sm120).  `SRa` role replaced the raw
S2R `imm8` field; `barname` replaced the raw BAR field; `field_value`/
`raw_field_bits` are now dead.

**Migrated so far (commits d98fc5a..a4de422; Debug gate 36/36):**
branch_target/special_reg/bssy/bsync/s2r/s2ur/bar, the ENTIRE do_compute,
do_mov/umov/uiadd3/ushf/iadd3/isetp/imad, do_tensor (HMMA/QMMA/OMMA),
mem_sz (by (m,nops) cast; LDG 5/7/8-op), decode_atomic_op (members +
subclass), resolve_mem_addr (positional Ra/off by (m,nops); LDC/LDCU keep
slot-name reads — its Sa_offset/URa layouts are form-specific), do_memory
(rd/rb/cas indices + atom sz/sem/sco by (m,nops)), do_ldgsts (its 4 layouts
distinguished by operand kind + 64-bit/uniform base), do_depbar/do_ldgdepbar.
The old `read_*_slot` / `op_value` / `slot_value` helpers are now used only by
the not-yet-migrated syncs/tma families (~60 remaining call sites).

**PENDING (next session, same mechanical pattern):**
1. do_syncs (8 opcode cases; layouts known), do_arrives, do_tma, MEMBAR `sco`
   member — replace the remaining ~60 slot-name reads.
2. Delete dead helpers: `read_reg_slot`/`read_ur_slot`/`read_pred_slot`/
   `write_pred_slot`/`read_addr_pair_slot`/`read_ur_pair_slot`/`write_rd_slot`,
   the anonymous `slot_value`, `offset_value`, `field_value`/`raw_field_bits`.
3. Re-run Debug + ASan + TSan gates (36/36 each); update this doc.

**DONE (2026-08 session, commits <pending>; Debug + ASan + TSan gates 36/36):**
- **do_syncs**: all 9 opcode cases read typed members + positional ops[] via
  per-case casts (`DecodedSYNCS0/3/4/5/6`).  The shared target is resolved
  uniformly: uniform forms (EXCH/CAS/LD) use `[URa,URa_offset]` at [2]/[3];
  non-uniform forms place the trio `[Ra,Ra_URc,Ra_offset]` at the tail
  (Rb-carrying arrives/phasechk leave ops[nops-1] = Rb).  ARRIVE vs TCNT is
  split by nops (5 vs 4); `Pu` (PHASECHK) reads ops[0] positionally.
- **do_arrives**: `DecodedARRIVES3` positional [Ra,Ra_URc,Ra_offset] + `barop`
  member.
- **do_tma**: `UTMACMDFLUSH` counts on `inst.schedule.dst_wr_sb` (the
  generated ScheduleWord field — the old `slot_value("dst_wr_sb")` never
  resolved (schedule slot, not FORMAT) and always counted 0); `UTMAREDG`
  reads the `RedOp` typed member `op` (the old `Pnz` name was never a slot —
  reduce op always faulted to ADD); URb/URa + descriptor pair read ops[1]/[2]
  positionally.
- **MEMBAR**: `sco` read from the `DecodedMEMBAR0` typed member, gated on
  `variant_class` (`membar_`/`membar_async_` only; the tma form has no sco
  field and keeps the default gpu scope).
- **loc** (LDGSTS cache policy in `record_coupled_l1_to_shared`): per-nops
  cast to `DecodedLDGSTS6/7/8`.
- **resolve_mem_addr LDC/LDCU**: fully positional by opcode (0xb82/0x13ac/
  0x15ac/0x17ac/0x19ac/0x1bac/0x1dac; 0x1582 LDC.UR has no bank/base/off
  roles, same as the old slot-name fallthrough).
- **deleted** all listed dead helpers + `field_value`/`raw_field_bits`
  (S2R `imm8` is the surfaced `SRa` role; BAR `barname` is a typed member);
  interpreter.cpp no longer includes `decoded_access.hpp` (the bridge remains
  for cli/main.cpp + tests/test_decoder.cpp decode paths).
- Latent-bug fixes folded in (behavior changes, gates-stable): the uniform
  SYNCS offset is `ops[ra_pos+1]` not `+2` (EXCH.64 was addressing 12 bytes
  past the barrier); `UTMACMDFLUSH`/`UTMAREDG` now use the real field values
  instead of the never-resolved slot names.
