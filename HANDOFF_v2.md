# HANDOFF_v2.md — typed-IR migration status & next tasks

Status snapshot for anyone resuming the **decoded-IR migration** in `semu/` (SM120
SASS simulator, CUDA-agnostic C++20). The current 2b checkpoint is implemented in
the working tree (not yet committed); Debug/ASan/TSan gates are green at 36/36.
The migration continues in small, gated-green increments; this doc records
**where we are** and the exact next operation.

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
- Hand-written glue: `include/semu/decoded_base.hpp` and
  `include/semu/shape_in.hpp`.

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

The current tree is **2b checkpoint complete but not 2b final**:

- DONE: typed decoder main storage, dynamic cloning, interpreter typed bridge,
  ABI v4, dynamic-shape smoke coverage, and all three 36-item gates.
- PENDING: delete the four generic base vectors and the temporary `Operand` cache;
  rewrite interpreter reads to typed value/flag/kind accessors and direct typed
  modifiers; remove the now-duplicate generic equivalence path.

Next session should begin with:

1. `rg -n "operands|modifiers|slot_values|raw_fields|find_op|slot_value" semu/src semu/include semu/tests` and classify every remaining consumer.
2. Add typed value/flag/kind accessors beside generated `slot_value_by_variant`.
3. Mechanically migrate one interpreter family at a time, running the Debug
   decoder/interpreter tests after each family.
4. Delete the vectors/cache, regenerate artifacts, then run Debug/ASan/TSan
   `tools/run_semu_cpu_gate.sh` (36/36 each).

## 8. Done-good definition for 2b
- `DecodedInstruction` has no `operands/modifiers/slot_values/raw_fields` vectors.
- decode allocates/consumes the typed `Decoded*` via `PredecodedWord::inst`.
- interpreter reads operands positionally / modifier members typed (no per-opname
  scan; no `const Operand*`).
- ABI v4; freeze-marker tests updated.
- Three trees (Debug/ASan/TSan) pass the full 36-item gate; whole-corpus
  typed-fill interception no longer needed as a separate duplicate path.
