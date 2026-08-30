# SASS debugger warp-private mutable code plan

Status: implementation plan, 2026-08-30.  This plan supersedes runtime
patching of the module's single shared text image.  M9/M10 remain the working
fallback until all migration gates below pass.

## 1. Decision

Each launched warp gets one full, fixed-address, mutable copy of the target
function's SASS in executable device memory.  All execution groups of that
warp execute the same copy.  Different warps, including warps in different
CTAs, never execute the same mutable instruction word.

When an execution group stops, the handler can run in two explicit modes.  A
tight, non-yielding `FROZEN` mode quiesces the rest of its warp and is the only
mode in which code may be changed.  A `PARKED_COOPERATIVE` mode retains
`NANOSLEEP` so a divergence-aware stepper can collect sibling groups at their
own successor sites; code is immutable in that mode.  Before committing or
leaving a frozen mutation boundary, the target warp executes one
`CCTL.I.IVALL`; no explicit NOP padding and no second IVALL are used on this
frozen-warp path.

The immutable source of truth is a canonical host-side instruction image.
Removing a breakpoint restores its word from that image.  There is no tree of
immutable code fragments and no physical version sharing between live warps
in the first implementation.

This gives the following isolation boundary:

```
module entry (immutable trampoline)
             |
             v
shared heap dispatcher (immutable; computes global warp id)
       +-----+-------------------+
       |                         |
       v                         v
warp 0 mutable text          warp N mutable text
  | all execution groups       | all execution groups
  | of warp 0                  | of warp N
  +--> shared/per-warp stubs    +--> shared/per-warp stubs
             |                              |
             +------> per-warp handler <----+
                         tight park
```

## 2. Goals and non-goals

### 2.1 Goals

- Breakpoint changes for one warp or CTA cannot affect any other warp or CTA.
- All execution groups of a warp keep one code identity, preserving
  reconvergence behavior at BSYNC/WARPSYNC and ordinary CFG joins.
- A stopped warp can gain or lose breakpoints without patching shared module
  text and without racing another execution group's fetch.
- Default breakpoints are per-warp.  Optional lane masks allow the handler to
  transparently pass an execution group for which no lane is selected.
- Source kernels and real cubins use the same code-instance, breakpoint,
  handler, command, and stepper machinery.
- The existing zero-register-reservation contract is retained: the breakpoint
  path borrows registers only after spilling them to per-lane frames.
- Persistent breakpoints, group stepping, BAR/BSYNC/WARPSYNC assistance,
  dump/set/exec, relaunch, and CLI behavior remain available.
- The device patcher kernel is removed from the steady-state breakpoint path;
  heap text is writable with ordinary host-to-device copies.

### 2.2 Initial non-goals

- Sharing one physical text version between several running warps.
- Basic-block or breakpoint-delimited immutable fragment graphs.
- Arbitrary asynchronous patching of a RUNNING warp.
- Debugging a grid that cannot keep all potentially parked CTAs resident.
- Copying an arbitrary inter-function call graph in the first milestone.
- Silently relocating code whose PC-sensitive semantics are not understood.

These are explicit scope limits rather than implicit correctness gaps.

## 3. Safety invariants

Implementation and review should treat these as assertions, not comments.

1. Module text is immutable after `cuModuleLoadData`.  The only module-text
   change is the real-cubin entry trampoline applied to the byte image before
   module load.
2. Every live warp has exactly one `CodeInstance`, with a 16-byte-aligned base
   and a stride aligned beyond the instruction-fetch line (initially 0x100).
3. Every execution group of a warp enters and resumes in that warp's instance.
   A running warp's code-base table entry is never changed.
4. Host code writes are legal only in `GATED` or `FROZEN` state.  A request
   against a `RUNNING` warp fails or is queued; it never writes optimistically.
5. A breakpoint word is written only to the requested warp instances.
6. A code mutation transaction publishes code and metadata first and its
   commit generation last.  Mode change or release is published only after the
   handler acknowledges that commit.
7. A handler that commits a mutated warp performs one target-side
   `CCTL.I.IVALL` before acknowledging commit and before fetching a changed
   thunk or warp-private target word.
8. Breakpoint sites remain patched while armed.  The displaced instruction is
   replayed in a per-warp thunk; no running group races a temporary restore.
9. Execution groups of one warp that replay a synchronization instruction use
   the same cached thunk VA for the same logical site and replay plan.
10. Canonical words never change.  Disarm and relaunch derive device text from
    the canonical image plus an explicit breakpoint overlay.
11. A text image is rejected before launch if relocation/PC-sensitive analysis
    cannot prove it safe to copy.
12. Existing late-read anti-dependency rules for LDG/STG/CALL/RET remain in
    force across all new dispatcher, stub, handler, and thunk code.

## 4. Host-side model

### 4.1 `CodeTemplate`

One immutable object per target function:

```
CodeTemplate
  words: tuple[(lo64, hi64)]
  source_lines: optional tuple[str]
  size: instruction_count * 16
  relocations: analyzed text relocation records
  replay_plans: one ReplayPlan per instruction
  pc_sensitive: classified instruction indices
```

For source input, `words` comes from assembling the original, uninjected
function.  For a real cubin, it comes from the selected function's ELF text
after validation.  The template is never patched in place.

### 4.2 `CodeInstance`

One per global warp id:

```
CodeInstance
  warp: global warp id
  base: executable device VA
  stride: aligned allocation size
  state: UNLAUNCHED | GATED | RUNNING | PARKED_COOPERATIVE
         | FREEZING | FROZEN | RESUMING | DONE
  code_epoch: host mutation generation
  applied: {orig_index: breakpoint_id}
  dirty: whether exit from the handler requires IVALL
  parked_groups: reported group identities/masks
```

The device allocation is contiguous where practical, but callers use
`code_base[warp]` rather than deriving addresses.  This keeps the design open
to future copy-on-write or relocation without changing dispatcher/stub APIs.

### 4.3 Breakpoint objects

A logical breakpoint describes a source/cubin instruction index.  Its binding
is per warp:

```
Breakpoint
  id, orig_index, canonical_word, stub_slot
  bindings[warp]: {armed, stop_mask, patch_word, epoch}
```

`stop_mask` is a lane mask.  The default is `0xffffffff`, meaning every
execution group of the selected warp stops.  A zero mask removes the patch
from that warp.  The public API should make scope explicit:

```
arm(index, warps=None, lane_masks=None)
disarm(bp, warps=None)
set_break_mask(bp, warp, mask)
```

Before the entry gate opens, omitted `warps` means all launch warps.  Once any
warp is running, omitted scope is rejected unless every launch warp is at a
safe boundary.  The stepper always uses explicit warp and lane masks.

### 4.4 Address mapping

Replace the single-address assumptions with explicit mappings:

```
site_va(warp, orig_index) = code_base[warp] + orig_index * 16
orig_index(warp, site_va) = (site_va - code_base[warp]) / 16
```

Hit decoding validates alignment and bounds before looking up the logical
breakpoint.  `base()` remains the module entry base for diagnostics;
`code_base(warp)` is the executable PC used by the target warp.

## 5. Device layout

Refactor `Layout` so executable and communication regions are explicit:

```
arena
  ctrl                 module base, gate, launch dimensions
  code_base_table      max_warps x u64
  code_epoch           max_warps x u32 host generation
  park_mode/request    max_warps x requested/observed mode generations
  freeze_ack/go        max_warps x cache-line-separated control
  bp_masks             max_warps x max_bps x u32
  stubs                max_bps x STUB_SZ (shared, position-independent)
  handlers             max_warps x HANDLER_STRIDE
  thunks               max_warps x per-warp thunk arena
  hslots/cmd/results    group and command communication
  frames               max_warps x 32 x FRAME
  dispatcher           immutable heap entry dispatcher
  code                 max_warps x aligned code stride
```

Code, handler, command, and thunk starts are at least 16-byte aligned.  Warp
code strides and per-warp thunk arenas are at least 0x100-aligned so host
writes for adjacent warps never share an instruction-fetch line.

Memory use is reported at construction.  The initial implementation keeps the
existing co-residency limit and refuses an allocation or launch whose declared
`max_warps * code_stride` exceeds a configurable budget.

## 6. Entry and launch path

### 6.1 Source kernels

The source path still appends `dbgctrl<8>`, but its injected entry code becomes
an immutable dispatcher rather than a prelude followed by shared target text.
The original function is separately assembled into `CodeTemplate` and copied
once per launch warp.

### 6.2 Real cubins

The cubin's first two words are statically replaced before module load with:

```
LEPC {R8,R9}
JMP dispatcher_va
```

The dispatcher reports the module entry, waits at the gate, computes

```
global_warp = CTAID.X * warps_per_cta + (TID.X >> 5)
```

loads `code_base_table[global_warp]`, restores the architectural entry
predicate baseline, and jumps to original instruction 0 in the private copy.
The old M10 displaced-instruction replay slots disappear because the private
copy contains instructions 0 and 1 unchanged.

Arena allocation must precede target module load so the trampoline can contain
the dispatcher VA.  Replace `Patcher` as the allocation owner with a minimal
`ArenaOwner`/driver-context helper; no runtime patch kernel is needed.

### 6.3 Gate behavior

All copies and initial breakpoint overlays are written before launch or while
warps are parked in the dispatcher gate.  These are fresh, never-fetched VAs,
so the dispatcher does not need the old hardened IVALL sequence.  Opening the
gate is the final publish operation.

## 7. Copyability and relocation

Copying a full function preserves offsets for internal PC-relative BRA, BSSY,
and similar control flow because every instruction moves by the same delta.
It does not automatically preserve every possible text image.

Add a `CodeImageAnalyzer` with three outcomes per instruction/relocation:

- `POSITION_INDEPENDENT`: copy verbatim.
- `REWRITE`: known internal absolute target; encode the corresponding
  warp-private target.
- `UNSUPPORTED`: reject before launch with instruction index and reason.

The first implementation accepts relocation-free, single-function kernels
whose internal relative control flow is understood.  It rejects:

- any ELF relocation that writes the copied text;
- external or unresolved CALL targets;
- absolute JMP/JMX targets that cannot be mapped into the copy;
- LEPC/RPC-based code-address constructions whose required semantic address
  cannot be reproduced;
- self-modifying target code.

Later work may copy the transitive call closure and apply ELF relocations per
warp.  This is a separate milestone; it must not weaken the v1 preflight gate.

## 8. Breakpoint entry, filtering, and parking

### 8.1 Patch word and shared stub

Each selected warp's site word becomes an absolute `JMP` to a logical
breakpoint stub.  The stub remains shared across warps.  It computes the
global warp/frame index, spills R0-R7 and PR as M9 does, and derives the actual
site VA from `code_base_table[warp] + orig_index*16`; it no longer bakes one
shared module-text VA.

The host writes heap code directly with `device_write`.  `Patcher.patch()` is
not called for warp-private sites.

### 8.2 Lane-mask filter

Before reporting a stop, the handler reads `bp_masks[warp][slot]` and splits
the current active mask:

- if `MACTIVE & stop_mask == 0`, restore state and take a prebuilt transparent
  replay thunk without reporting a hit;
- selected lanes enter the parked path;
- if an active group contains both selected and unselected lanes, hardware
  divergence forms subgroups.  The selected subgroup's tight park freezes the
  warp; the unselected subgroup continues only after that stop is released.

This preserves per-warp code identity while allowing the stepper to arm the
union of successor sites without stopping an unrelated execution group.

### 8.3 Dual-mode park and freeze protocol

The handler has two poll loops:

- `PARKED_COOPERATIVE`: contains `NANOSLEEP 0x100`, allowing sibling groups
  to execute and report additional hits.  The host may inspect already-spilled
  groups, but must not write any executable word.
- `FROZEN`: contains no NANOSLEEP/YIELD.  One parked handler subgroup owns
  issue, quiescing running siblings and other parked handler subgroups.  Only
  this state authorizes mutation.

The default user-breakpoint stop requests `FROZEN`.  The group stepper may
request cooperative collection after all code/mask changes have been committed
and invalidated.  Before its next mutation it performs an explicit
`PARKED_COOPERATIVE -> FREEZING -> FROZEN` handshake; merely having one or more
reported hit slots is not a safe patch boundary.

On a freeze request, the winning handler subgroup enters a bounded no-yield
settling loop and publishes a freeze acknowledgement.  It then remains in a
tight release/command/mode poll.  The host waits for both the hit state and the
matching freeze epoch before declaring the warp `FROZEN`.

This is an empirical hardware contract, so implementation begins with a probe
that removes the current 350 ms host delay and sweeps the settling-loop length.
The chosen constant must pass immediate host patching with zero stale fetches
under local stress; Hopper repeats are a release gate when hardware is next
available.

Only a `FROZEN` warp may be patched mid-run.  Sibling execution groups can be
in the original body, stub, or handler; none may make forward issue progress
while the tight poll owns the warp.  Transitioning back to cooperative mode or
releasing a group is a separate, host-published action after mutation commit.

## 9. Mutation and resume transaction

For a frozen warp, all arm/disarm/step changes are committed as one batch:

1. Compute the desired overlay from canonical words and breakpoint bindings.
2. Write changed stub/mask/thunk metadata.
3. Write all changed instruction words in the warp-private copy.
4. Increment and write the warp's `code_epoch`.
5. Write per-lane replay target and release generations.
6. Publish a commit generation last.
7. The tight handler observes the commit, waits required memory scoreboards,
   performs any required device-side executable write (such as composing its
   RET line), executes one `CCTL.I.IVALL`, and acknowledges commit.
8. Only after the acknowledgement, publish either a mode change back to
   cooperative collection or a per-warp GO/release generation.
9. On release, restore PR and registers and enter the per-warp thunk.

The same single IVALL covers host-written warp code, command code, thunk reuse,
and the handler's self-written RET line, provided their stores are complete
before CCTL.  The existing STG/LDG late-read barrier discipline is retained.

If no executable word changed, a later optimization may skip IVALL.  The first
correct implementation executes one on every handler release.

## 10. Replay and reconvergence

Thunks remain necessary: an armed site stays patched, so the original
instruction executes out of line.  Make replay support explicit with a
`ReplayPlan` rather than ad-hoc string handling:

- ordinary position-independent instruction: verbatim word/text;
- predicated/unpredicated BRA: absolute JMP sequence with predicate preserved;
- BSSY: verified thunk-local representation;
- BSYNC/WARPSYNC/BAR: shared per-warp thunk VA and existing barrier assist;
- terminal instruction: explicit terminal plan;
- LEPC, CALL, RET, BRX/JMX and other PC-sensitive cases: dedicated lowering or
  a clear unsupported error.

Thunk cache keys include `(warp, orig_index, replay_plan, target_index,
breakpoint_epoch)`.  Different warps require different thunks because their
fall-through VAs differ.  Execution groups of the same warp intentionally
reuse the same key and VA.

## 11. Commands and inspection

The dual-mode handler changes the command model.  A state-changing command
first acquires `FROZEN`; read-only inspection of already-spilled frames may be
served while cooperative.  Normally only the tight handler subgroup can issue
while siblings are frozen.  Commands therefore gain an explicit
`(warp, lane_mask)` scope instead of relying only on a per-warp generation.

- Frame-backed dump/set keeps the stopped group's architectural R0-R7/PR view.
- Non-frame registers are read only for lanes in the stopped group unless an
  API explicitly requests otherwise.
- Command generations and acknowledgements become per lane or carry a command
  mask, preventing a second handler subgroup from executing a stale command
  after the first group resumes.
- Host-written command code is followed by the same single-IVALL dispatch
  protocol.
- CLI output distinguishes `stopped group` from `frozen sibling lanes`.

## 12. Stepper changes

The CFG remains indexed by canonical instruction index.  Replace global
successor arming with a per-warp mask transaction:

1. For every parked group, compute its successor indices.
2. Union sites per warp, but build a lane stop mask at each site from only the
   groups for which that site is a successor.
3. While the warp is frozen, apply the site-word and mask overlay in one batch.
4. Commit, execute the single IVALL, then either release the current group or
   switch parked handlers to cooperative collection.
5. In cooperative collection, sibling groups may reach and report their own
   successor sites without any executable-memory mutation.
6. A group that reaches a patched but mask-disabled site transparently replays
   it and does not appear as an unexpected hit.
7. Preserve the existing merge/split accounting and barrier assist, now keyed
   by `(warp, mask, code_base)`.
8. At the next explicitly acquired frozen boundary, remove successor patches
   whose masks reached zero and restore their canonical words.

This removes the current possibility that one divergent group hits a union
successor intended only for another group.

Predicated EXIT and dynamic-target stepping remain separate CFG tasks, but the
new replay analyzer must report them precisely rather than falling through to
an unsafe generic thunk.

## 13. Lifecycle and relaunch

At each launch:

1. Validate one-dimensional launch and co-residency limits.
2. Set `warps_per_cta` and active global warp count.
3. Reset communication/frame generations.
4. Bulk-write the canonical template into every active warp instance.
5. Reapply persistent breakpoint bindings and masks while copies are fresh.
6. Restore handler/command/thunk mutable lines.
7. Launch into the gate, verify every expected warp registered, then open it.

Breakpoint configuration may persist across launches, but device code state is
reconstructed rather than trusted.  Changing block size is safe because stubs
and the dispatcher read launch metadata instead of baking `ctawarps` into a
live patch.

## 14. Implementation milestones

### M11a — freeze protocol and minimum-IVALL production probe

- Extend `probe_warp_mutable.py` with immediate-after-ack patching, configurable
  settling iterations, multiple warps, and multiple CTAs.
- Add a command-buffer/self-modified-retline case, not only a body-word case.
- Separate setup/handoff failures from visibility failures in the runner.
- Local gate: no sibling progress after freeze ack and no stale fetch in at
  least 10,000 valid shortest-sequence iterations.
- Hopper gate: repeat the selected protocol when SM90 hardware is available.

### M11b — `CodeTemplate`, analyzer, layout, and CPU-only tests

- Add immutable template and per-warp instance classes.
- Refactor address mapping and `Layout(code_size=...)`.
- Implement copyability classification and fail-closed diagnostics.
- Unit-test mapping, alignment, overlays, epochs, masks, replay-plan cache keys,
  memory budgeting, and relocation rejection without a GPU.

### M11c — private-code bootstrap, no breakpoints

- Implement source dispatcher and real-cubin static trampoline/dispatcher.
- Write canonical copies and execute each warp from its reported private base.
- Remove M10's displaced instruction replay from the new backend.
- E2E: one/two/many warps, two CTAs, tight loops, divergence and relaunch all
  produce baseline-identical results; record PCs prove different warps use
  different code bases.

### M11d — per-warp breakpoint mutation

- Make the stub position-independent with respect to warp site VA.
- Implement direct heap writes, per-warp bindings, mutation batching and code
  epochs.
- Convert the handler to tight freeze and single IVALL.
- E2E: arm warp 0 only while warp 1 runs; per-CTA isolation; independent
  arm/disarm sets; tight-loop persistent hit; restore canonical word; relaunch.
- Verify the original module text is never runtime-written.

### M11e — lane masks and group-aware stepping

- Implement stop-mask filtering and transparent replay.
- Implement cooperative-collection and tight-freeze mode handshakes.
- Migrate `Stepper.step_groups()` to per-warp successor masks.
- Re-run and adapt M8 split/merge, BSYNC, WARPSYNC and BAR tests.  Expected
  scheduling changes are explicit: one stopped group freezes its warp, so two
  sibling groups need not be simultaneously reported.
- Add the adversarial union-successor test that currently can stop the wrong
  group.

### M11f — command, dump/set/exec, CLI

- Add command masks/per-lane generations and prevent stale command replay.
- Update CLI states and breakpoint scope syntax (`b N [warp W] [mask M]`).
- Re-run M6/M7 inspection tests with divergent groups and multiple warps.

### M11g — real-cubin default path

- Move `CubinDebugger` to the private backend.
- Reject whole-function text relocations and unsupported PC-sensitive code,
  with actionable messages.
- Re-run M10 entry-output, nonzero symbol entry, multi-warp, persistence and
  stepper tests; add multi-CTA real-cubin E2E.
- Keep `backend="shared"` as an explicit fallback during this milestone.

### M11h — cleanup and default switch

- Make `backend="warp_private"` the default after all gates pass.
- Remove `Patcher` construction from the new path; retain legacy code only
  behind the fallback until one full release cycle.
- Update `DBG_HANDOFF.md`, `AGENTS.md`, CLI help and architecture diagrams.
- Run serial full regression and repeated M3–M11 stress batches.

### M12 — call closure and advanced relocation (follow-up)

- Copy reachable device functions per warp.
- Apply supported text relocations and rewrite internal absolute targets.
- Define LEPC/code-address semantics and dynamic JMX/BRX stepping.
- Revisit physical version sharing only after fixed per-warp copies are stable.

## 15. Test matrix and release gates

The new backend is not complete merely because a breakpoint hits.

| Area | Required gate |
|---|---|
| Freeze | sibling progress remains constant from ack through mutation |
| Visibility | single IVALL, zero stale first execution under stress |
| Isolation | patch warp/CTA A; B's code word, PC path and output unchanged |
| Divergence | selected and transparent groups split/merge correctly |
| Reconvergence | BSYNC/WARPSYNC same-PC and BAR assistance pass |
| Registers | R0-R7, high GPRs, PR and pending scoreboard writes preserved |
| Commands | dump/set/exec affect only requested stopped lanes |
| Lifecycle | persistent bps and canonical restoration survive relaunch |
| Real cubin | entry 0/1, nonzero symbol entry and multi-CTA pass |
| Failure mode | running-warp patch and unsupported relocation fail closed |
| Regression | M2–M11 serial suite at baseline or better |

Before making the backend default, run at least:

- 10,000 local valid freeze/patch/resume iterations for the minimum sequence;
- 1,000 repeated divergent step transitions including barriers;
- repeated multi-warp/multi-CTA isolation runs;
- one complete serial repository regression;
- the freeze/visibility and multi-CTA isolation gates on Hopper hardware.

## 16. Migration and rollback strategy

Do not rewrite M9 in place at the start.  Introduce a backend boundary:

```
SharedTextBackend       # current M9/M10 implementation
WarpPrivateBackend      # M11 implementation
```

`Debugger`, `CubinDebugger`, `Stepper`, and CLI depend on the backend's
logical operations (`site_va`, `arm_scope`, `commit_mutations`, `release`,
`replay_plan`) rather than direct dictionaries or `Patcher.patch()`.

During migration, tests run against both backends where semantics overlap.
The private backend becomes default only after M11g gates pass.  A failure in
private copyability analysis may offer the legacy backend only when the user
explicitly selects it; it must not silently fall back to unsafe shared
runtime patching.

## 17. First implementation slice

The first code change should be deliberately narrow:

1. Add the M11a immediate-ack probe and settle on a freeze acknowledgement.
2. Add `CodeTemplate`, `CodeInstance`, and address-mapping unit tests.
3. Build a source-kernel dispatcher that runs an unmodified private copy with
   no breakpoints.
4. Prove two warps report distinct heap PCs and compute identical output.

Only after that slice passes should `arm()` or the handler be changed.  This
keeps bootstrap/copy errors separate from breakpoint state-machine errors.
