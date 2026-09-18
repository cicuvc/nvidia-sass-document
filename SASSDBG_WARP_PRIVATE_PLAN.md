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

### M11a — freeze protocol and minimum-IVALL production probe  (DONE: sm_120 + Hopper sm_90)

- Extend `probe_warp_mutable.py` with immediate-after-ack patching, configurable
  settling iterations, multiple warps, and multiple CTAs.
- Add a command-buffer/self-modified-retline case, not only a body-word case.
- Separate setup/handoff failures from visibility failures in the runner.
- Local gate: no sibling progress after freeze ack and no stale fetch in at
  least 10,000 valid shortest-sequence iterations.
- Hopper gate: repeat the selected protocol when SM90 hardware is available.

Status (RTX 5090, sm_120): every bullet above is implemented and green.
Full F0/F1/P1-P5/C1 matrix passes at warps=1..4 (per-warp 0x100-stride
control slots, per-warp freeze/ack/release/deltas), ctas=2x2, 4x1 and
2x4 (8 total warps) all PASS, staggered release (warp 0 runs while the
others must stay frozen) PASSes at warps=3, and the yield handoff works
at warps=2.  The 10k shortest-sequence gate (1x IVALL + 0 NOPs) PASSED
at warps=1 and at warps=3 (10,000/10,000 valid, zero freeze failures,
zero stale fetches; `--gate-min 10000`).

Root cause found while extending past 2 warps (>= 3 warps faulted 715
before any heap store): the wrapper cubin's declared REGCOUNT is
auto-computed from the wrapper's own registers only (16 from R4/R5),
while the heap program executes R14-R30.  Out-of-window register access
is undefined rather than always-faulting: at <= 2 warps the overrun
lands in unallocated RF space (harmless); at >= 3 warps the CTA's RF
allocation geometry changes and it faults 715.  Fix: the wrapper now
declares `#pragma MAXREG_COUNT` computed over every word the GPU can
execute from the heap via `CubinBuilder._compute_regcount`.  This rule
applies to any wrapper-JMP-to-heap scheme (M9's stub only borrowed
R0-R7, which is why it never tripped).

Hopper deferral resolved (2026-08-31, H20 sm_90, driver 580.65.06,
``ASSEMBLER_ARCH=sm90``, ``--handoff nanosleep``): the full matrix
passes x3 at warps=1; multi-warp P3+C1 pass at warps=2/3/4; ctas=2x2
and ctas=4x1 pass; staggered warps=3 (P3+P4 x2) passes — the first
multi-warp sm_90 runs, also validating the REGCOUNT fix on Hopper.
The 10k shortest-sequence gate PASSED at warps=1 (10,541 valid /
159 SETUP / 0 visibility / 0 freeze) and at warps=3 (10,306 valid /
394 SETUP / 0 visibility / 0 freeze; the skip rate grows with warp
count, consistent with the known one-shot NANOSLEEP handoff flakiness
being per-warp).

### M11b — `CodeTemplate`, analyzer, layout, and CPU-only tests  (DONE)

- Add immutable template and per-warp instance classes.
- Refactor address mapping and `Layout(code_size=...)`.
- Implement copyability classification and fail-closed diagnostics.
- Unit-test mapping, alignment, overlays, epochs, masks, replay-plan cache keys,
  memory budgeting, and relocation rejection without a GPU.

Status: `sassdbg/warpcode.py` ships CodeTemplate (from_source/
from_cubin via sassdbg.cubin), CodeInstance, Breakpoint bindings with
lane masks, AddressMap hit decoding, Layout(max_bps, max_warps,
code_size) with the plan section 5 regions, OverlayBatch (words first,
every warp's code_epoch bump last) and the PrivateCodeSet arm/disarm/
set_break_mask scope rules.  CodeImageAnalyzer classifies every word
POSITION_INDEPENDENT / REWRITE / UNSUPPORTED (relocations writing the
copied text, PC-sensitive LEPC/RPCMOV/CALL/RET/JMX/BRX/CCTL, and
out-of-function BRA/BSSY targets reject fail-closed with instruction
index + reason; internal absolute JMPs become REWRITE with the
in-function index).  Field decode (crossing the lo/hi 64-bit
boundary, SCALE 4, sign) verified against assemble_flat round-trips:
BRA target = pc+16+sImm*4, BSSY Sa likewise, JMP imm absolute.
43 CPU-only tests in tests/asm_construct/test_warpcode.py cover all
M11b bullets; full runner 135/136 (only the known test_uimad
self-bug), M10/M2 regression green.  cubin.py gained sh_addr
(link_addr) + all-text reloc offsets for the analyzer.

### M11c — private-code bootstrap, no breakpoints  (DONE: sm_120)

- Implement source dispatcher and real-cubin static trampoline/dispatcher.
- Write canonical copies and execute each warp from its reported private base.
- Remove M10's displaced instruction replay from the new backend.
- E2E: one/two/many warps, two CTAs, tight loops, divergence and relaunch all
  produce baseline-identical results; record PCs prove different warps use
  different code bases.

Status (2026-08-31, RTX 5090 sm_120): `sassdbg/private.py` implements the
source wrapper and real-cubin two-word trampoline, immutable heap dispatcher,
per-warp canonical materialization (including internal absolute-JMP rewrite),
entry gate, global-warp mapping, canonical relaunch, and state transitions.
The source wrapper appends `dbgctrl<8>` without moving the original parameter
offsets; the real-cubin path changes only the entry 32 bytes before module
load.  `test_warpcode.py` has 48 CPU/static checks green under both sm_120 and
sm_90.  `test_sassdbg_m11c.py` passes the one/four-warp, 2-CTA, divergent
tight-loop, relaunch, and real-cubin E2E matrix four consecutive times.  M10
real-cubin attach and M2 lift/instrument regressions also pass.  The sm_90
dispatcher assembles and passes static dependency checks; an sm_90 hardware
run is desirable but is not a gate for the sm_120 M11c milestone.  Full runner:
134/137; all sassdbg tests pass, with only the pre-existing `test_uimad`
self-bug and two FP16 scripts whose optional NumPy dependency is absent.

### M11d — per-warp breakpoint mutation  (DONE: sm_120)

- Make the stub position-independent with respect to warp site VA.
- Implement direct heap writes, per-warp bindings, mutation batching and code
  epochs.
- Convert the handler to tight freeze and single IVALL.
- E2E: arm warp 0 only while warp 1 runs; per-CTA isolation; independent
  arm/disarm sets; tight-loop persistent hit; restore canonical word; relaunch.
- Verify the original module text is never runtime-written.

Status (2026-08-31, RTX 5090 sm_120): implemented in `sassdbg/private.py`.
The shared 24-instruction logical stub spills R0-R7/PR, uses the host-seeded
per-lane `F_CODEBASE` cache to derive `code_base[warp] + orig_index*16`, and
dispatches to a 38-instruction per-warp handler.  The handler publishes the
private site/mask, enters a tight poll with no NANOSLEEP/YIELD, and handles an
independent COMMIT generation by executing exactly one `CCTL.I.IVALL` and
publishing ACK before the host may publish RELEASE.  Stubs, thunks, handler
return JMPs, and private words are written directly through a fail-closed
arena-only executable-write API; the Patcher/module-text path is never used.

`PrivateKernel.arm/disarm/wait_hit/resume_hit` apply per-warp `OverlayBatch`
transactions and code epochs, keep armed sites persistent, replay displaced
instructions in per-warp thunks, and restore from the materialized immutable
template.  Relaunch clears APPLIED state, reconstructs canonical images,
reapplies persistent bindings, and performs one target-side launch IVALL for
breakpoint-capable instances so reused heap VAs and wpc-dependent stubs cannot
execute stale lines.

`test_sassdbg_m11d.py` passes five consecutive runs and covers: arming a new
warp-0 site while warp 1 demonstrably advances; per-CTA independent sites;
tight-loop persistent re-hit; canonical restore; code-epoch isolation;
relaunch with 1x64 -> 2x32 shape change; real-cubin FFMA replay; and an
executable-write journal proving every runtime target stays inside the heap
arena and outside module text.  M11c/M10 regressions pass.  Static stub/handler
assembly + depcheck passes under sm_120 and sm_90 (50 CPU/static tests).  Full
runner: 136/138, with only two unrelated FP16 scripts failing at their optional
`import numpy` because NumPy is absent.  Partial lane masks/cooperative group
collection remain deliberately rejected until M11e.

### M11e — lane masks and group-aware stepping  (DONE: sm_120)

- Implement stop-mask filtering and transparent replay.
- Implement cooperative-collection and tight-freeze mode handshakes.
- Migrate `Stepper.step_groups()` to per-warp successor masks.
- Re-run and adapt M8 split/merge, BSYNC, WARPSYNC and BAR tests.  Expected
  scheduling changes are explicit: one stopped group freezes its warp, so two
  sibling groups need not be simultaneously reported.
- Add the adversarial union-successor test that currently can stop the wrong
  group.

Status (2026-08-31, RTX 5090 sm_120): implemented.  The stub intersects each
binding's per-warp stop mask with MACTIVE.  A disjoint execution group takes a
transparent restore/replay epilogue without publishing a hit; selected groups
publish independent leader-lane hit slots.  The host explicitly switches a
parked warp between cooperative NANOSLEEP collection and tight freeze, and
`PARKED_COOPERATIVE` is no longer a legal executable-write boundary.  The
cooperative-to-freeze commit uses IVALL/NOPx32/IVALL so an immediately prior
sibling fetch cannot survive the acknowledgement.

Replay and restore code is immutable per `(warp, orig_index)` rather than per
recyclable stub slot.  BSSY Sa is relocated from the heap thunk to the
warp-private reconvergence target.  The private `Stepper.step_groups()` path
builds a complete `warp -> {successor: lane_mask}` overlay transaction at each
boundary, so a group outside the source mask transparently crosses a globally
shared successor.  Barrier assist records groups already blocked inside a
replay barrier: BSYNC/WARPSYNC use the common per-warp/site thunk VA, while BAR
matches arrivals across private warps without requiring equal PCs.

`test_sassdbg_m11e.py` covers nonmatching transparent replay, cooperative
split collection and freeze reacquisition, the adversarial successor-mask
case, BSYNC, WARPSYNC, and two-warp CTA BAR.  M11d, legacy M8/M5w and the
50-test CPU/static suite pass; full `blkw` runner: 139/139.

### M11f — command, dump/set/exec, CLI

**DONE.** Command dispatch is per warp, selection is per lane, and completion
is acknowledged in each lane's spill frame.  Rewriting the command buffer
cannot make a late-arriving group replay a stale image: the handler compares
the warp command generation with its frame-local baseline before calling it.
The selected mask is intersected with MACTIVE before the group-uniform CALL;
P6 predicates the requested lanes inside the command.

`exec_cmd`, `cmd_read`, `dump_regs`, and `set_reg` preserve the handler's frame
pointer and rebuild its R4/R5 control pointer on command return.  R0-R7 and PR
inspection uses the saved architectural frame, while higher GPRs are accessed
live.  Generated memory commands claim/read-wait their address barrier before
the return sequence reuses R2/R3.  Straight-line validation rejects control
flow and writes to the live R0/R1 frame pointer.

The CLI accepts `--backend warp_private` and scoped breakpoints
`b N [warp W] [mask M]`; `info b` reports per-warp masks.  Its hit drain
temporarily enters cooperative mode to collect divergent siblings, then
reacquires tight freeze before inspection.  `test_sassdbg_m11f.py` covers two
warps with two parked groups each, disjoint lane commands, stale-image
prevention, frame/live registers, validation, resumed output, and scripted CLI
scope/dump/set.  M11d, M11e, M6/M7 and the 50-test static suite pass.

### M11g — real-cubin default path

**DONE.** `CubinDebugger(...)` now constructs a `PrivateKernel` unless the
caller explicitly requests `backend="shared"`; an unsupported private image
never silently retries the shared runtime patcher.  The CLI follows the same
default for `--cubin` while source kernels remain shared-by-default until
M11h.

`CodeTemplate.from_cubin()` validates the complete ELF function slice before
module load.  Any text relocation in that slice or unsupported PC-sensitive
instruction raises an actionable error naming the function, instruction and
explicit compatibility option.  Lifted replay plans now cover BRA/BSSY rather
than treating every cubin word as verbatim.  cuobjdump's section-alignment NOPs
are trimmed to the exact ELF `symbol.size`, including symbols with nonzero text
entry offsets.

`test_sassdbg_m11g.py` covers bare output, entry instruction zero, two-warp
FFMA inspection/mutation, persistent relaunch, lifted-CFG stepping, first-two-
instruction outputs, nonzero symbol entry, two CTAs, fail-closed diagnostics,
explicit shared fallback, and the CLI cubin default.  The old M10 suite now
requests `backend="shared"` and passes unchanged, preserving the rollback
gate.  The migration regression also exposed and fixed an M11e barrier-assist
ordering bug: only groups covered by the current hit may advance from the
barrier site to its successor set; moving an in-flight sibling early made it
execute WARPSYNC at the private PC while the first group waited at the thunk
PC.  Five adversarial M11e repeats and the complete serial suite pass; `blkw`
full runner: **141/141**.

### M11h — cleanup and source-default switch

**DONE.** `Debugger(source)`, `Stepper(source)`, and every CLI input mode
(`--sass`, direct `--cubin`, and lifted `--cubin/--sass --trace`) now default to
`backend="warp_private"`.  `SharedDebugger` and `SharedCubinDebugger` retain the
M9/M10 implementation only behind explicit `backend="shared"`.  Copyability
failure is fail-closed and never retries shared text.

The public factories build `PrivateKernel` directly.  No `Patcher` object is
constructed and no patcher module is launched on the default path; the old
device patcher exists only inside the two shared fallback constructors.
M3–M10 tests and the old CLI regression explicitly select shared so the
rollback implementation continues to receive coverage.  `Stepper` accepts an
explicit `backend=` for the same purpose.

`test_sassdbg_m11h.py` proves factory selection without a GPU, then verifies
the default Stepper, divergent WARPSYNC replay, fail-closed PC-sensitive source,
source CLI scope, and wtrace reverse composition on the private backend.  Its
release stress mode executes 168 divergent loop iterations and **1015 actual
private step transitions**, including one WARPSYNC per iteration.  M3–M11
mixed batches pass 3/3 and the `blkw` serial full runner passes **142/142**.

### M12 — call closure and advanced relocation (follow-up)

M12 extends the private backend from a single copied kernel image to mixed
user/device/runtime call graphs.  **Reachability, placement, and stepping are
separate decisions:** a reachable function is not automatically copied, and a
copied function is not automatically Just My Code.

The default remains fail-closed.  M12 must never absorb driver/runtime code,
patch shared module text, or silently let a supposedly private path return to
the original kernel image.

#### M12 preflight findings (2026-09-06, RTX 5090/sm_120)

`tests/call_test.cu` was rebuilt with CUDA 13.1.  Its kernel, recursive `fib`,
and `leaf` are three FUNC symbols in one 0x580-byte `.text` section.  The
linked image has no ordinary `.rela.text` entries: direct edges are already
`CALL.REL.NOINC`, and returns are `RET.REL.NODEC Rxx`.  CUDA 13 also emits
three retained `.nv.merc.rela.text` records, but those records belong to the
capmerc capsule's **separate Mercury address space**, not native SASS text.
They must be segregated from native relocations rather than projected onto
native instruction indices.

Three process-local analyzer-bypass probes established:

1. Copying the complete linked text image byte-for-byte to a warp-private heap
   image executes `leaf` plus recursive `fib` correctly.
2. A breakpoint inside private `leaf`, scoped only to warp 0, hits while warp
   1 completes and the final 64-thread result remains correct.  Existing M11
   handlers already work inside a device function.
3. Redirecting the private caller's leaf CALL to the original module leaf,
   without converting its return token, completes through original text and
   does **not** hit the private continuation.  Moving leaf from section offset
   0x450 to 0x600 while changing only CALL also faults 700.  Therefore
   `CALL.REL` target relocation alone is insufficient: program-base-relative
   return materialization/RET semantics and the linked text layout are part of
   the ABI.

These probes make preservation of the linked text layout the first safe path.
Function-granular packing and private/shared boundaries require an explicit
return-ABI transform and may not infer correctness from final output alone.

#### Ownership and stepping policy

Each resolved function/target receives two independent classifications:

```text
placement: PRIVATE_EAGER | PRIVATE_LAZY | SHARED_OPAQUE | INDIRECT_UNKNOWN
stepping:  STEP_INTO     | STEP_OVER
```

- The selected kernel is always `PRIVATE_EAGER`.
- User compilation units and explicit include patterns are eligible for
  `PRIVATE_LAZY`.
- Undefined symbols, driver runtime address ranges, and explicit excludes are
  `SHARED_OPAQUE` and default to step-over.
- An unresolved indirect target is `INDIRECT_UNKNOWN`; continue-only behavior
  must be explicit, otherwise reject before launch.
- Symbol names are hints, not ownership proof.  `DEVICE_PRINT.md` shows that
  undefined `vprintf` resolves to `syscall_trampoline_vprintf`, not to the
  same-named implementation entry.  Static symbol/relocation evidence must be
  combined with runtime module address ranges.

CLI/API policy surface:

```text
set just-my-code on|off
set step-filter include <regex>
set step-filter exclude <regex>
info functions
materialize <function>
```

`step` steps over opaque calls; an explicit instruction/assembly step may try
to enter only when the target can be safely materialized.  Breakpoint reports
must say when a shared caller path cannot reach a private function instance.

#### Module, function, and address model

Replace the single flat template assumption with:

```text
ModuleTemplate
  TextIsland[]                  # one linked text/program-base domain
    FunctionTemplate[]         # symbol range + CFG + relocation records
    CallEdge[]                 # target class + return ABI

CodeLoc(module, island, function, instruction)

WarpProgram
  island_base[island]          # fixed for the launch
  FunctionInstance[]           # state/base/overlays/incoming edges
```

`FunctionInstance.state` is `UNMATERIALIZED`, `MATERIALIZING`, `PRIVATE`, or
`OPAQUE`.  Once a private VA becomes observable during a launch it is never
moved or freed until that launch ends.

The initial local-call implementation copies a complete `TextIsland` while
preserving every original section-relative offset.  This retains linked
CALL/return conventions and provides a correctness oracle.  Function-level
placement is enabled only after its return ABI is decoded and tested.

The ELF reader must retain full **native** relocations, not only offsets:

```python
Relocation(section, offset, type, symbol, addend, mercury)
```

In practice this should become separate `NativeRelocation` and
`CapsuleRelocation` types: `.nv.merc.symtab` and `.nv.merc.rela.*` use standard
ELF64 record layouts, but their symbol values, offsets and addends name
Mercury/MPE positions.  They are not applied to finalized `.text`.  The
current `cubin.py` inclusion of `.nv.merc.rela.text.*` in native
`text_reloc_offsets()` is deliberately conservative but wrong for M12 and
causes false instruction-index rejection.

Build the native direct call graph from decoded finalized CALL targets,
primary symbols and ordinary relocations; use `.nv.callgraph` as a
cross-check.  The retained capsule may be inspected independently, but without
a verified Mercury-to-SASS map/finalizer it cannot supply native addresses.
Recursion and mutually recursive functions are one SCC placement unit.
Supported native relocations use a strict whitelist and preserve opcode,
guard, divergence predicate, scheduling, and call-depth fields.

Runtime materialization remains two-phase: the entry gate reports the loaded
module base, then the host applies private/module address mappings, writes only
heap executable ranges, commits, target-invalidates, and finally opens the
gate.

#### Call-boundary rules

M12 records a return protocol on every direct call edge.

- **Private local relative ABI:** linked `CALL.REL.NOINC` plus
  `RET.REL.NODEC` stays inside the same private text island with original
  offsets for the first implementation.
- **Opaque absolute-return ABI:** `LEPC` constructs an absolute private
  continuation and `CALL.ABS.NOINC` calls a loader-resolved target.  This is
  the expected `printf` fast path, pending its dedicated probe.
- **Opaque relative-return ABI:** a raw private-to-module CALL is forbidden.
  A bridge must replace the caller's relative return token with one that the
  original callee's `RET.REL` resolves to the private continuation.  A
  site-specific bridge can write the known return register pair without
  scratch registers, execute the original guarded CALL, and let the callee
  return directly to private code.
- **Unknown return ABI / shared-to-private callback:** reject or report an
  explicitly incomplete breakpoint scope.  No shared module site is patched.

An opaque boundary must also be checked for re-entry.  A PRIVATE -> OPAQUE
edge is safe only when the opaque subgraph does not silently call a function
that is expected to be private on that path.  SCCs are indivisible; static
OPAQUE -> PRIVATE back-edges either promote the boundary or receive a precise
diagnostic.

#### Just My Code and demand copying

Implement demand copying in two steps:

1. **Mixed eager placement:** at the entry gate, materialize only the root
   text island and explicitly selected user islands; route verified opaque
   edges to their original runtime targets and step over them.  This delivers
   Just My Code before adding a transparent resolver.
2. **First-use resolver:** unresolved `PRIVATE_LAZY` call sites target a
   debugger-owned resolver.  It reports `(warp, group, callee)`, freezes the
   warp, materializes the whole callee SCC, applies relocations, commits and
   invalidates, then replays the call.  Subsequent calls may be patched to the
   direct private target.  The permanent-resolver form is the simpler initial
   correctness path; direct-call promotion is the later fast path.

Setting a breakpoint in an unmaterialized function queues/promotes the
necessary SCC and its private incoming edges.  An invocation already running
in shared code is never migrated mid-function.  Removing all breakpoints
restores canonical words but does not change that function's VA or reclaim it
until the next launch.

For very large same-section images, copying on first use only reduces transfer
cost unless storage is sparse.  The preferred physical-memory experiment is
CUDA VMM: reserve a stable per-warp virtual text layout, map executable pages
on demand, and use page COW for mutation while preserving all architectural
PCs.  It is gated on executable-fetch, alias-icache, remap/TLB, and IVALL
experiments; regular `cuMemAlloc` remains the fallback.

#### LEPC and dynamic control flow

Debugger-visible locations are logical `CodeLoc`s; hardware control flow uses
private physical VAs.  Arbitrary LEPC-as-data is not bit-identical after
copying and remains rejected in strict mode.  Recognized control-flow uses may
return the private address and are translated back to `CodeLoc` for display.

Replay encoding becomes placement-aware rather than a tuple of source lines:

```python
ReplayPlan.encode(logical_site, site_va, thunk_va, address_map)
```

- LEPC immediate replay adjusts by `site_next - thunk_next`; bare LEPC can use
  the immediate form to reproduce the private site address.
- BRX replay adjusts its relative immediate by the same delta.
- JMX is absolute and can replay unchanged when its register already contains
  a private target.
- CALL/RET replay uses the edge's recorded return protocol, never generic
  verbatim replay.

At a stopped JMX/BRX, M11f command injection reads predicate and target
registers per active lane.  The host computes and validates targets, maps them
to `CodeLoc`, partitions lane masks by successor, and arms scoped private
breakpoints.  Targets outside owned address maps are step-over/continue-only
or fail closed; external text is never patched.

#### Milestones and mandatory probes

- **M12a — ELF/call ABI foundation:** parse complete native symbols and
  relocations, separate retained Mercury capsule records so they can never be
  mistaken for native text offsets, and add `ModuleTemplate`, `TextIsland`,
  `FunctionTemplate`, `CodeLoc`, `CallEdge`, SCC and ownership-policy unit
  tests.  Probe the exact `RET.REL` program base and each observed return-token
  materialization.

Status (2026-09-06, RTX 5090 sm_120): `sassdbg/cubin.py` now exposes
`native_symbols`/`capsule_symbols`, `NativeRelocation`/`CapsuleRelocation`
(`native_relocations`/`capsule_relocations`), and native-only
`text_reloc_offsets` (mercury is opt-in and never feeds native checks).  The
retained `.nv.merc.rela.text.*` records live in the capsule's separate
Mercury address space — one offset (0xcc) is not even a native 16-byte
instruction boundary.  Relocations carry their `sh_info` target-section
identity so text islands associate them without name concatenation; `SHT_REL`
parses on its own path with the implicit addend recovered from the target
word.  `sassdbg/modulecode.py` ships `ModuleTemplate`, `TextIsland`,
`FunctionTemplate`, `CodeLoc`, `CallEdge` (target class + return ABI +
placement/stepping policy), Tarjan `sccs`/`recursive_scc`, and
`OwnershipPolicy` (just-my-code, include/exclude, root=eager).  Functions
carry island-qualified `fid`s; resolution is source-island-first with
fail-closed cross-island/out-of-module targets.  CALL/RET decode is
per-opcode (GPR vs uniform `RegSpec`); a container kernel with no owned RET
and conflicting multi-return protocols are `UNKNOWN`; return-token discovery
proves both halves of the pair (reaching-def backward scan + zero high in
caller or callee) or fails closed.  The native call graph is built from
decoded finalized CALL targets; the `.nv.callgraph` section in the sampled
CUDA 13.1 cubins is a fixed 32-byte placeholder (identical across a
1-function and a 3-function cubin) and cannot be a cross-check.

`tests/asm_construct/test_modulecode.py` (52 CPU-only tests) covers all M12a
bullets including the call_test edges (k→leaf token R6=0xb0, k→fib token
R20=0xf0, fib→fib token R20=0x310), REL_REG ABI, SCC recursion + isolated
functions, ownership policy, the innermost-function lookup that keeps the
wide kernel symbol from masking nested `$kernel$fn` sub-functions, and
synthetic-ELF acceptance fixtures (relocations via `sh_info`, SHT_REL,
multi-island/overlapping `sh_addr`, ABS/REL/GPR/UR CALL/RET variants,
multi-return conflicts, token hazards, duplicate names, zero-size symbols,
just-my-code).  The `sassdbg/GAP_M12a.md` review items are all closed.

`sassdbg/probe_retrel.py` pins the return ABI empirically (3/3 repeat runs):
- ptxas encodes every `RET.REL.NODEC Rxx` so `pc_link+0x10+sImm*4 == 0`;
  at a runtime PC the term equals the image's placement delta (its program
  base), so `return target = Rxx + base`.
- The caller materializes the continuation *offset* in the return GPR pair
  with an immediate MOV; the pair's high half must be zero (ptxas zeroes it
  in the caller or callee before the matching RET — a stale high half lands
  `token + garbage<<32` and faults 718).
- A byte-identical caller/callee copy in devmem executes correctly at TWO
  different heap bases (0xe both), proving the return is
  program-base-relative; perturbing the token by +0x10 lands the return
  exactly one instruction later (0x9), proving token and base add
  independently.  The assembler's `RET.REL ..., 0x0` is *raw* sImm (not the
  ptxas pre-resolved form) — M12b replay must re-encode the displacement.
- **M12b — local call closure:** execute preserved-layout text islands with
  nested/recursive/divergent calls; support breakpoints in callees and
  placement-aware CALL/RET replay.  Prove every return remains private by
  continuation breakpoints, not only output comparison.
- **M12c — Just My Code / opaque calls:** verify heap-resident `LDC c[4]`
  observes loader relocation, then run private `LEPC + CALL.ABS` through the
  full printf syscall chain and back to a private continuation.  Add default
  step-over and relative-return bridge tests.
- **M12d — lazy materialization:** resolver, per-warp/SCC state machine,
  breakpoint-triggered promotion, relaunch cleanup, and multi-warp isolation.
- **M12e — LEPC/JMX/BRX:** supported PC semantics, dynamic lane-target
  partitioning, indirect internal calls, and precise unsupported diagnostics.
- **M12f — physical sharing experiment:** only after fixed-VA demand copies
  pass.  Try VMM sparse mapping/page COW first; do not switch a live warp to a
  different virtual code base because return registers and reconvergence
  state may retain old physical PCs.

Required gates include nested and mutually recursive calls, a breakpoint on
callee entry/body/RET, simultaneous warps with different callee breakpoints,
divergent calls, opaque-call step-over, printf return to private code, lazy SCC
first-use races, relaunch, and fail-closed unknown relocation/indirect target.
The full M2-M12 serial regression and Hopper cross-check remain release gates.

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
Debugger / CubinDebugger / Stepper / CLI
                  |
                  +-- default: WarpPrivateBackend (PrivateKernel)
                  |             |
                  |             +-- immutable template
                  |             +-- mutable code copy per global warp
                  |             +-- arena-only executable writes
                  |             `-- no Patcher / no runtime module-text write
                  |
                  `-- explicit backend="shared"
                                |
                                `-- SharedTextBackend (M9/M10 + Patcher)
```

`Debugger`, `CubinDebugger`, `Stepper`, and CLI depend on the backend's
logical operations (`site_va`, `arm_scope`, `commit_mutations`, `release`,
`replay_plan`) rather than direct dictionaries or `Patcher.patch()`.

Tests run against both backends where semantics overlap.  Since M11h the
private backend is the default for source and real cubin inputs.  A failure in
private copyability analysis may offer the legacy backend only when the user
explicitly selects it; it must not silently fall back to unsafe shared runtime
patching.  Keep the legacy implementation for one release cycle, then reassess
removal separately from M12 call-closure work.

## 17. First implementation slice

The first code change should be deliberately narrow:

1. Add the M11a immediate-ack probe and settle on a freeze acknowledgement.
2. Add `CodeTemplate`, `CodeInstance`, and address-mapping unit tests.
3. Build a source-kernel dispatcher that runs an unmodified private copy with
   no breakpoints.
4. Prove two warps report distinct heap PCs and compute identical output.

Only after that slice passes should `arm()` or the handler be changed.  This
keeps bootstrap/copy errors separate from breakpoint state-machine errors.
