# M12a implementation gap review

Initial review: 2026-09-06
Fix re-review: 2026-09-07

## Current verdict after re-review

The first repair closes a substantial part of the original review, but M12a is
**not fully closed yet**.  The 52 checked-in CPU tests pass; additional
order-independent and fail-closed counterexamples expose six remaining
correctness gaps.  The plan's current statement that every GAP item is closed
should not be used as the M12b readiness gate.

### Confirmed closed

- Native text relocations are associated through `sh_info`, not section-name
  concatenation.
- REL and RELA records take separate structural parse paths and are no longer
  duplicated.
- Destination indices subtract the destination island base.
- Basic immediate/register/uniform CALL and RET variants use opcode-specific
  layouts and preserve the GPR/UR distinction.
- Isolated functions appear in SCCs; duplicate function names no longer
  overwrite a unique name lookup.
- `just_my_code`, out-of-module target finalization, module-scope capsule
  relocations, and file-handle cleanup are implemented.

### Remaining blocker A: function construction is order-dependent and zero-size repair is incomplete

`from_cubin()` builds and analyzes each function before all functions in the
island are known (`modulecode.py:647-663`).  `_analyze_return_abi()` therefore
only excludes nested functions that happened to appear earlier in `.symtab`.
The real `call_test.cubin` lists child functions before the kernel and passes;
a semantically equivalent symbol table with the outer function first makes the
outer function inherit its child's `RET.REL R20` again.

Zero-size extents have the same phase-order bug.  `_build_function()` computes
`relocations`, analyzes RETs, and slices `words` while size is still zero
(`modulecode.py:687-700`); `_fix_zero_size_extents()` later updates only `size`
and `n_insts`.  A reproduced zero-size function inferred to one instruction
has `n_insts == 1` but `len(words) == 0`, and it retains relocations from later
functions.

Build this model in phases: create every symbol object, infer all extents,
establish ownership, then derive relocations/word slices/RET ABI.  Results must
not depend on symbol-table order.

### Remaining blocker B: multi-RET agreement omits displacement and depth

`_analyze_return_abi()` compares only `(ReturnABI, RegSpec)` and discards the
RET depth bit (`modulecode.py:711-727`).  Consequently it accepts:

- two byte-identical `RET.REL R20, 0` words at different PCs, even though their
  `pc + 0x10 + sImm*4` base terms differ; and
- one `RET.REL.NODEC R20` plus one `RET.REL.DEC R20`.

It then stores the last RET's `return_rel_base`, making the result iteration
dependent.  The current `test_consistent_returns_kept` accidentally codifies
the first invalid case.  A return protocol must compare at least address mode,
register file/pair, resolved REL base term, and depth behavior across every
owned RET.

### Remaining blocker C: return-token high-half proof is still unsound

The new backward scan is safer for the low half, but the high-half paths do not
reject predicated zeroing (`modulecode.py:842-868`).  Both of these reproduced
cases currently produce a non-None `return_token`:

- caller uses `@P0 MOV32I R21, 0`; or
- callee uses `@P0 MOV32I R21, 0` before RET.

`_writer_reg()` also reports only the base `Rd` and ignores destination width.
For example, `IMAD.WIDE {R20,R21}, ...` is seen only as a write to R20.  The
sequence `MOV R21,0; IMAD.WIDE {R20,R21},...; MOV R20,token; CALL` incorrectly
reuses the stale R21 zero definition and accepts the token.

The proof needs predicate-aware definitions and the ISA destination width (all
written registers), and callee-side zeroing must hold on every path to every
compatible RET.  Otherwise it must remain unknown.

### Remaining blocker D: relocations are recorded but not used to resolve call edges

`TextIsland.native_relocs` is now populated, but `_decode_edges()` /
`_resolve_target()` never consult it (`modulecode.py:739-812`).  A relocation on
a CALL can name one symbol while the unrelocated immediate happens to point at
another in-range function; the model currently follows the raw immediate and
labels that edge `INTERNAL_DIRECT`.  Loader-resolved/out-of-section calls can
likewise be misclassified merely because placeholder bits numerically overlap
a local function.

Call edges need relocation-aware target resolution.  Unknown relocation types,
ambiguous symbol bindings, or a relocated call without a supported relocation
rule must fail closed rather than fall back to the raw word.

There is also a narrower `SHT_REL` semantic issue in `cubin.py:201-220`:
reading an unconditional 64-bit little-endian word is not generally the
implicit addend.  Relocation type 1 is `R_CUDA_32`, for example, whose field is
32 bits, while the added test expects the full 64-bit target word.  NVIDIA's
relocator table contains 16/20/24/32/47/55/64-bit and split bitfields.  Either
extract the addend according to the relocation type/field map or retain the raw
target bits and mark the semantic addend unresolved.

### Remaining blocker E: target resolution applies REL locality to ABS and accepts invalid alignment

`_resolve_target()` always prefers the source island, although its own rationale
only applies to CALL.REL.  With two overlapping `sh_addr == 0` islands, a
`CALL.ABS` target covered by both is currently assigned to the source function
instead of being ambiguous/fail-closed.  Absolute targets require global
uniqueness or relocation/symbol identity; source-island preference is not
evidence.

The resolver also accepts a target that is only 4-byte aligned and floors it to
an instruction index.  A reproduced CALL target of `0x14` becomes instruction
1.  Native SASS targets must be validated against the 16-byte instruction
boundary before constructing a `CodeLoc`.

### Remaining blocker F: `CallEdge` still does not contain or validate the complete call/return protocol

`CallDecode` does not retain CALL depth, and `_finalize_edge()` simply copies
the callee's RET classification onto the edge.  It never checks CALL family
against RET address mode, `INC` against `DEC`, or whether a relative token is
appropriate for that call form.  Thus an incompatible CALL/RET pair can be
presented as a known edge ABI.

M12b replay needs an explicit edge protocol containing CALL address family,
target kind, call-depth action, RET address family, return register pair,
return-depth action, and proven token/base relation.  Unsupported combinations
must be `UNKNOWN` before placement or replay decisions.

### Secondary issues

- `probe_retrel.part2()` now wraps the whole GPU probe in `except Exception`.
  This fixes no-device skipping, but also converts assembler bugs, assertions,
  CUDA execution faults, and readback regressions into exit code 2 (`GPU
  SKIPPED`).  Catch only the expected device-unavailable initialization errors;
  test failures must return 1 or propagate.
- `FunctionTemplate.sym_index` is always left at its default zero even though
  the field is presented as native symbol identity.  Either populate it from
  the symbol-table entry or remove it in favor of the actual stable ID.
- The synthetic tests create persistent `mkdtemp()` directories.  This is not
  a model correctness issue, but the fixture should use managed temporary
  files/directories.

### Tests still required

Add regressions for:

1. outer-before-child and child-before-outer symbol ordering;
2. zero-size function `words`, relocations, and RET ABI after extent inference;
3. multi-RET disagreement in REL base term and depth;
4. predicated caller/callee high-half zeroing and wide/vector clobbers;
5. relocation-directed CALL resolution and unsupported relocation fail-close;
6. ambiguous ABS targets and non-16-byte-aligned targets;
7. compatible and incompatible CALL-depth/address-family versus RET protocols;
8. a deliberately broken GPU probe path that must report failure, not skip.

### Re-review evidence

- Checked-in CPU suites: `test_modulecode + test_warpcode` = 102 passed, 1
  skipped because nvcc is unavailable inside the environment.
- `probe_retrel.py` on the current GPU: PASS at both heap bases and for the
  token `+0x10` differential.
- M10 real-cubin GPU E2E: all T0-T5 checks pass.
- M11g real-cubin/private-default GPU E2E: all T0-T6 checks pass.
- `py_compile` and `git diff --check`: pass.
- Separate in-memory synthetic ELF counterexamples reproduced every blocker
  A-E above; blocker F follows directly from the absent call-depth/protocol
  fields and was checked by source inspection.

## First repair mapping (2026-09-06)

The first repair attempted every original item and added
`tests/asm_construct/test_modulecode.py` (52 tests, CPU-only) plus the GPU
`probe_retrel.py`:

- #1 relocation association now uses the relocation section's `sh_info`
  (`Relocation.target_section`); `TextIsland.native_relocs` filters by it.
- #2 `SHT_REL` and `SHT_RELA` parse on separate paths, one record per entry;
  `SHT_REL` recovers the implicit addend from the target word
  (`addend_implicit=True`; type-specific addend semantics remain open).
- #3 CALL resolution is source-island-first; an out-of-island target is only
  accepted when it falls in exactly one island with a distinct base, else
  finalized `EXTERNAL_RUNTIME`.  Destination instruction index is computed
  island-relative (`(target - island.link_base) // 16`; ABS/relocation/alignment
  cases remain open).
- #4 CALL/RET decode selects opcode-specific layouts from the ISA DB
  (`decode_call`/`decode_return`); GPR vs uniform operands are explicit
  `RegSpec("R"/"UR", n)`; unsupported forms return None (no edge).
- #5 RET ABI analysis scans only instructions owned by the innermost
  function's exclusive range; a container kernel with no owned RET is
  `UNKNOWN`, and conflicting multi-return protocols resolve to `UNKNOWN`
  (subject to the ordering and protocol-comparison gaps above).
- #6 return-token discovery uses a reaching-definition backward scan bounded
  by the caller's own instructions, stopping at control-flow barriers; both
  halves of the pair must be proven (low = unconditional MOV32I/MOV-imm,
  high = zero in caller or callee) or the token fails closed (predicate and
  wide-destination handling remain open).
- #7 `sccs(edges, nodes)` accepts the complete node set; every function
  (including isolated ones) belongs to exactly one component.
- #8 `just_my_code` is implemented: `True` filters internal functions through
  include/exclude; `False` disables the filter (external stays opaque).
- #9 zero-sized FUNC extents are inferred from the next compatible symbol
  (extent only; derived fields remain stale as described above).
- #10 functions carry island-qualified `fid`s; name lookup is ambiguous-safe;
  `CodeLoc`/SCC use fids.
- #11 immediate targets outside the module are finalized
  `EXTERNAL_RUNTIME`, never left `INTERNAL_DIRECT`.
- #12 capsule relocations live at module scope (`ModuleTemplate.capsule_relocs`),
  not copied onto islands.
- #13 probe_retrel wraps the entire GPU section; a no-device machine returns
  the documented exit code 2 (the exception scope is currently too broad).
- #14 file handles are closed (no `ResourceWarning`).

The first-repair fixtures build synthetic ELF cubins via
`tests/asm_construct/elf_fixture.py` (relocations through `sh_info`, SHT_REL,
multi-island/overlapping `sh_addr`, ABS/REL/GPR/UR CALL/RET variants,
multi-return functions, token hazards, SCC isolation, duplicate
names, zero-size symbols, and observable just-my-code behavior).

## Original 2026-09-06 verdict (historical)

The RET.REL heap-copy experiment is sound on the tested RTX 5090, and the
native/Mercury address-space split is directionally correct.  The current
host-side module model is nevertheless **not ready to be the correctness
foundation for M12b**.  In particular, native text relocations are not attached
to text islands, several legal ELF/control-flow forms are decoded incorrectly,
and the call graph is not well-defined for the common multi-text-section case.

The existing 28 M12a tests all pass, but the fixture has one text island at
`sh_addr == 0`, an empty native `.rela.text.*`, non-zero FUNC sizes, and one
GPR RET shape.  Those properties hide most of the blocking defects below.

(Original review text follows for history; the first-repair mapping and the
2026-09-07 re-review above are authoritative.)

## Original blocking correctness gaps

### 1. Native text relocations never attach to an island

`ModuleTemplate.from_cubin()` matches relocation section names with
`f".rela.{sec.name}"` / `f".rel.{sec.name}"` (`modulecode.py:455-457`).  For a
section named `.text.foo` these expressions produce `.rela..text.foo` and
`.rel..text.foo`; the ELF names are `.rela.text.foo` and `.rel.text.foo`.

Consequences:

- `TextIsland.native_relocs` is empty even when native text relocations exist.
- Function relocation sets are consequently empty.
- M12b could copy or rewrite a word that actually requires loader relocation.

The association should use the relocation section's `sh_info` target section
index, not name concatenation.  `Relocation` should retain that target section
identity.  The current `call_test.cubin` has an empty `.rela.text._Z1kPKiPii`,
so its test cannot expose this bug.

### 2. ELF `SHT_REL` parsing is invalid and duplicates records

`cubin._relocations()` accepts both `SHT_RELA` and `SHT_REL`, but unconditionally
unpacks every entry as `<QQq>` (`cubin.py:174-190`).  A legal ELF64 REL entry is
only `<QQ>` and has no explicit addend.  `native_relocations()` then has a
second REL loop (`cubin.py:208-215`), which would append the records again if
the first loop did not fail.

Minimal reproduction with one 16-byte REL entry currently raises:

```text
struct.error: unpack_from requires a buffer of at least 24 bytes
```

RELA and REL need separate parsing paths, exactly one emitted record per input
entry, and an explicit policy for recovering or retaining an implicit addend.

### 3. Direct-call resolution is wrong for multiple text islands and non-zero bases

`_function_by_link()` searches all islands by numerical VA and returns the
first match (`modulecode.py:553-558`).  CUDA text sections commonly have
`sh_addr == 0`, so several `.text.*` sections overlap in this provisional
address space.  A local `CALL.REL` in a later island can therefore resolve to a
function in the first island.  CALL.REL should first resolve in its source
island; an actual cross-section reference must be identified through its
relocation/symbol.

There is a second independent arithmetic error at `modulecode.py:527-529`:
the destination instruction index uses `(target - dst_fn.offset) // 16` without
subtracting the destination island's `link_base`.  Moving the existing fixture
to link base `0x100000` changes valid destination indices 69/20 into
65605/65556.

Until the model has island-qualified identities and relocation-aware
cross-island resolution, its call closure is unsafe for multi-kernel/modules
with more than one text section.

### 4. CALL/RET decoding uses one arbitrary ISA encoding for distinct opcodes

`_call_enc()` and `_ret_enc()` each request one generic mnemonic encoding, then
use it for every CALL/RET opcode (`modulecode.py:318-377`).  The variants do not
share all operand fields.

- Decoding the legal immediate `CALL.ABS` opcode `0x943` currently raises
  `WarpCodeError: field 'Sb' not in encoding`.
- Uniform RET opcode `0x1950` carries `URa[29:24]`, but `decode_return()` reads
  `Ra[31:24]` and reports an ordinary integer GPR.  For example a RET through
  `UR4` is returned as register `4`; later token discovery then searches for a
  `MOV32I R4`, which is the wrong register file.

Decode must select the opcode/class-specific layout and represent GPR versus UR
operands explicitly.  Unsupported ABI forms must remain `UNKNOWN` rather than
being silently converted to a GPR ABI.

### 5. Function RET ABI is inferred from instructions owned by nested functions

`_build_function()` scans the entire ELF symbol range and stops at the first
RET (`modulecode.py:472-495`).  In `call_test.cubin` the kernel FUNC covers the
whole text section and overlaps the two `$kernel$device_function` FUNC ranges.
The kernel itself exits, but the builder finds `fib`'s RET and labels the
kernel `REL_REG/R20`.  `test_return_abi_decoded` explicitly expects this false
metadata.

RET analysis must operate on instructions owned by the innermost function (or
on a recovered function CFG), collect all reachable returns, and validate that
their protocols agree.  A container/kernel symbol with no owned RET should be
`UNKNOWN`/not-applicable.  Stopping at the first RET also misses real
multi-return ABI conflicts.

### 6. Return-token discovery is not safe enough to authorize rewriting

`_attach_return_token()` chooses any matching `MOV32I` in the preceding eight
linear instructions (`modulecode.py:568-585`).  It does not check control flow,
predication, intervening writes, reachability, the high half of the 64-bit
pair, or alternative materialization sequences.  A stale unrelated MOV can
therefore be recorded as proven ABI metadata.

The model must use reaching-definition/CFG analysis for both halves of the
return pair, or fail closed with an unknown token.  The current probe establishes
three concrete ptxas sequences and the RET.REL base equation; it does not make
the eight-instruction heuristic generally valid.

### 7. SCC placement drops functions with no call edges

`sccs()` builds its node set only from edges, and `ModuleTemplate.scc()` passes
only `self.edges` (`modulecode.py:189-241,435-436`).  A single no-call function,
or any isolated function in a larger module, is absent from all SCCs.  For
example, `sccs([])` returns `[]` rather than one singleton when the module has
one function.

SCC construction must accept the complete function node set in addition to
edges.  Every function must belong to exactly one placement unit.

### 8. `just_my_code` is a no-op

`OwnershipPolicy.__init__()` stores `just_my_code`, but no decision reads it
(`modulecode.py:271-300`).  `OwnershipPolicy(just_my_code=False)` and `True`
classify every target identically.  The public API and plan currently claim a
feature that is not implemented.

The intended difference should be specified and tested before M12c.  If M12a
only provides policy data structures, the flag should either affect
classification now or be removed/deferred explicitly rather than silently
ignored.

## Other model gaps

### 9. Zero-sized FUNC symbols consume the remainder of their section

`size = sym.size or (island.size - start)` makes every zero-sized function
overlap all following symbols.  Infer the end from the next compatible symbol
in the same section (or retain an explicitly unknown extent) before falling
back to section end.

### 10. Function identity is not unique across islands

`ModuleTemplate._function_index` is keyed only by symbol name, and `CodeLoc`
also carries the name rather than a stable symbol/island-qualified ID.  Local
symbols with duplicate names overwrite one another.  SCC nodes keyed by name
have the same collision.  Use an island-qualified function identity while
keeping the display name separately.

### 11. Immediate targets outside the module keep `INTERNAL_DIRECT`

`decode_call_target()` labels every immediate target internal before module
range resolution.  If `_decode_edges()` cannot find the target it changes the
placement to opaque but leaves `CallEdge.target_class == INTERNAL_DIRECT`.
This contradictory edge state can mislead later bridge/stepping logic.  Target
class must be finalized after range and relocation resolution.

### 12. Capsule relocations are copied wholesale onto every text island

Every island receives the entire tuple returned by `capsule_relocations()`
(`modulecode.py:458`).  They remain segregated from native relocations, which
is good, but their island association is false and becomes ambiguous in a
multi-island module.  Either keep capsule records only at module scope or
associate them using their own `sh_info`/capsule section identity.

### 13. Probe skip behavior does not match its documented exit contract

`probe_retrel.py` catches import errors only.  CUDA context/module creation and
allocation occur after the `try` (`probe_retrel.py:181-200`), so a machine with
the Python package but no usable CUDA device raises instead of returning the
documented GPU-skipped exit code 2.

### 14. Tests leak file handles

`test_modulecode.py:51` and `:151` use `open(...).read()` without closing the
files.  The suite passes but emits two `ResourceWarning`s.

## Missing acceptance tests

Before marking M12a complete, add synthetic or real fixtures covering at
least:

1. non-empty native `.rela.text.*` association through `sh_info`;
2. one- and multi-entry `SHT_REL` sections;
3. two text islands with overlapping zero `sh_addr`, plus non-zero link bases;
4. immediate ABS/REL, GPR and UR CALL/RET variants, with unsupported forms
   failing closed;
5. an outer kernel/container symbol overlapping device-function symbols;
6. multiple returns and conflicting return protocols;
7. stale, predicated, branched, clobbered, and split low/high return-token
   materializations;
8. isolated functions in SCC output and duplicate local symbol names;
9. zero-sized FUNC symbols;
10. observable `just_my_code=True/False` policy behavior.

The `.nv.callgraph` placeholder conclusion is currently based on only two CUDA
13.1 cubins.  It is acceptable not to trust that section, but the claim that it
is generally fixed should remain toolkit/fixture-qualified until a broader
inventory is collected.

## Review evidence

Commands run in the `blkw` environment/current GPU:

- `python -m unittest -v tests.asm_construct.test_modulecode` — 28/28 pass,
  with two `ResourceWarning`s.
- `python -m unittest -v tests.asm_construct.test_modulecode tests.asm_construct.test_warpcode`
  — 78 pass, 1 skipped (`nvcc` unavailable inside the environment).
- `python sassdbg/probe_retrel.py` — static checks pass; both heap bases return
  `0xe`; token `+0x10` returns `0x9`; overall PASS.
- M10 real-cubin GPU E2E — all T0-T5 checks pass.
- M11g real-cubin/private-default GPU E2E — all T0-T6 checks pass.
- `py_compile` for the changed/new M12a Python files — pass.

These passing results validate the narrow current fixture and the core
RET.REL experiment; they do not cover the module-model gaps above.
