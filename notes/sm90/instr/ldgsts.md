# LDGSTS — asynchronous global→shared copy (cp.async)

**Opcode mnemonic:** LDGSTS  |  **Pipe:** mio_pipe (VQ_AGU_UNORDERED_WR)  |  **INSTRUCTION_TYPE:** INST_TYPE_DECOUPLED_RD_WR_SCBD

Asynchronously copies bytes from global memory into shared memory, per
thread.  This is the SASS encoding of PTX `cp.async.cg.shared.global`.
Verified SM120 (test_ldgsts.py) against nvcc-generated code.

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). A real sm_90 rerun of the full matrix is blocked by the LDCU-vs-ULDC
> scoreboard difference (`LDCU+req` legal on sm_120; ULDC is synchronous on
> sm_90 — see `assembler_sm90_port.md`). Kernels must switch to the
> stall/NOP pattern before results count as sm_90-verified.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

## The working sequence (mirrors nvcc)

```
LDGSTS.E.BYPASS.128 [Rshared], desc[UR4][Rsrc.64]   ; async 16B/lane
LDGDEPBAR[wr=SB0]     ; bind ALL prior LDGSTS completions to SB0
DEPBAR.LE SB0, 0x0    ; drain: every LDGSTS has landed in shared
BAR.SYNC 0            ; warp-wide visibility
LDS.128 ..., [Rshared]; read the copied data
```

* **dest `[Rb]`** is a SHARED-window byte offset (0x400 with a 16 KB
  `#pragma SHARED(0x4000)` window).  It is NOT an absolute address.
* **source `desc[UR4][Ra.64+off]`** is a 64-bit global address (the same
  `desc`/address form as LDG).
* **`.BYPASS` requires `.128`** (spec condition); `.128` copies 16 bytes per
  lane.  `.32`/`.64` copy 4/8 bytes (verified single-lane).

## Completion / scoreboard semantics

LDGSTS writes shared memory and has IDEST_SIZE = 0 — it sets **no result SB
itself**.  Completion is tracked via LDGDEPBAR:

* **LDGDEPBAR** (`0x79af`, also DECOUPLED_RD_WR_SCBD) binds the completion of
  **every prior LDGSTS** to the SB named by its `wr` (`&wr=0x0` → SB0).
* **DEPBAR.LE SB0, 0x0** then waits until the tally drains (all LDGSTS have
  landed in shared).
* LDGSTS's own `rd_sb` (nvcc uses `&rd=0x2` = SB2) is an anti-dependency on
  **all GPR address operands**, including both the global source pair and the
  shared destination address.  A later writer must not clobber any of them
  before LSU operand collection finishes.  This is shorter than memory
  completion, but it is not necessarily the SASS issue cycle.

In the verified hand-built pattern the LDGSTS carries no `req` on the
descriptor (`[7:2:{}:5:1]`); the LDCU.64 UR4/LDC.64 R6,R7 producers use SB3
and the in-place address bump `IADD3 R6, R6, R1` waits on SB3.  The
LDGDEPBAR `wr=SB0` + `DEPBAR.LE SB0,0x0` is what guarantees the shared data
is ready for LDS.

## Variants (sm120.json)

| variant | opcode | form |
|---------|--------|------|
| `ldgsts__RR32U` / `RR64U` | 0x1fae | dest [Rb(+URc+off)], src desc/Ra64 |
| `ldgsts__RUR` / `ldgsts__desc_RRU` / `memdesc_` | 0x1dae | uniform/desc forms |
| (2 more ALT) | | |

Modifiers: `e` (EONLY), `loc` (LOC: ACCESS/BYPASS), `cop` (COP), `sp2`,
`sz` (32/64/128), `fc` (FILLCTRL: nofillctrl/ZFILL), `sem`/`sco`/`private`
(TABLES_mem_3).  Encoding bits on the desc_RRU form: `cop`[86:84],
`sp2`[72:71], `sz`[75:73], `fc`[82], `loc`[81], `mem`[80:77]
(TABLES_mem_3), `Ra_URc`(desc UR)[71:64], `Ra`[31:24], `Rb`[23:16].

## Cross-comparison

* PTX `cp.async.cg.shared.global [smem], [gmem], 16` → `LDGSTS.E.BYPASS.128`.
* The `.BYPASS` loc (L2-bypass, 16B-aligned) is the standard bulk-copy form.
* `LDGDEPBAR` + `DEPBAR.LE SB0,0x0` + `BAR.SYNC` is the canonical wait;
  `cp.async.wait_all` lowers to the DEPBAR pair.
* Related: LDS/STS (shared window), LDG (global reads), LDGSTS.32/.64 for
  smaller async copies (e.g. strided gather into shared).

## Verified encodings (test_ldgsts.py, SM120)

* Warp round-trip: 32 lanes × 16 B = 512 B copied global→shared→global,
  every word matches.
* Single-lane `.128`, `.32`, `.64`.
* Encoding data bits (sz/cop/loc/mem, bits 64..104 and lo 0..15) match
  nvcc `-arch=sm_120` byte-for-byte.

## Operand capture and LSU admission (SM120)

`probe_ldgsts_operand_latch.py` deliberately omits LDGSTS's read scoreboard.
It places older LSU requests ahead of a target copy, issues the target, and
then overwrites either its global-address low register, its shared-address
register, or both.  The old/new global locations contain distinct sentinels
and two disjoint shared slots reveal both the sampled source and destination.

With an empty path, even a gap-zero overwrite is too late.  Older
`STG.E.128` requests make both addresses mutable for roughly 16--18 scheduled
one-stall instructions.  Therefore LDGSTS retains the GPR identities and
reads both addresses later during local LSU dispatch/packetization; neither
address is captured completely at SASS issue.

Separating the two overwrites by eight NOPs produces three stable regions.
Global-first gives `new->new`, `new->old`, `old->old`; shared-first gives the
mirror `new->new`, `old->new`, `old->old`.  Thus both address reads belong to
one short late-collection episode.  The experiment does not prove they are
read on the same physical clock, and phase effects near the boundary prevent
assigning a reliable order to the three constituent GPR reads.

Fair prefix controls distinguish RF collection from downstream queuing:

* `STG.32` and `LDGSTS.32` prefixes give the same complete overwrite-boundary
  table.  Both demand three late GPR values (a 64-bit global address plus one
  data/shared-address GPR) and share the local LSU collector/admission path.
* `STG.E.128` holds the target much longer because it contributes four store
  data registers in addition to its address pair.  Its large delay is mainly
  operand-collector work, not one fixed queue slot per instruction.
* Up to eight 32-way bank-conflicted LDS requests do not extend the target's
  mutable-address window.  Once LDS has collected its address and entered the
  shared-memory downstream queue, replay wavefronts do not immediately
  backpressure this local collection boundary.
* `SHFL ... RZ` likewise has no effect, while scalar LDG has only a narrow
  boundary effect.  Removing physical GPR inputs is essential when using
  this probe to infer queue occupancy.

For equal-cost `STG.32`/`LDGSTS.32` prefixes, delay grows through the first
roughly 4--6 requests and then stays near a six-instruction window for
prefixes 6--12.  This is consistent with the independently measured
approximately four effective local LSU backlog credits, but instruction
packing creates non-monotonic one-cycle phase effects, so this latch test
alone is not an exact FIFO-depth measurement.

### Read-scoreboard release is operand collection, not copy completion

`probe_ldgsts_read_scoreboard.py` gives the target LDGSTS `rd=SB2`, then makes
an address-overwriting IADD3 request SB2 and timestamps both SB2 release and
the later `LDGDEPBAR`/`DEPBAR.LE` completion.  Global-source and shared-dest
overwrites produce the same result:

| older STG.128 prefix | SB2 release | copy complete |
|---:|---:|---:|
| 0 | 7 | 357--359 |
| 1 | 19 | 371--372 |
| 2 | 30 | 384--386 |
| 3 | 40 | 395--397 |
| 4 | 50 | 404--405 |
| 6--16 | 53 | 406--410 |

All copied values use the old global and shared addresses.  The read
scoreboard therefore covers the whole late-collection lifetime of both
address operands and releases hundreds of clocks before the memory operation
completes.  Its saturation with queue backlog also matches the unprotected
WAR/latch boundary.

Changing only the copy size gives the same SB2 releases for `.32`, `.64`, and
`.128`: 7 clocks with no prefix, 50 behind four STG.128s, and 53 behind eight.
The `.128` completion is nevertheless about 20 clocks later than `.32/.64`.
Thus size-dependent formation of 1/2/4 128-byte lane groups is downstream of
source release; it does not extend the lifetime of the three address GPRs.

## Commit-group ordering (SM120)

Three-group slow/fast experiments in `probe_ldgsts_group_order.py` show that
`DEPBAR.LE SB0,N` retires committed groups in program order.  `N=2` waits only
for group 0, `N=1` waits for groups 0--1, and `N=0` waits for all three.  A
slow younger group does not delay a partial wait that permits it to remain;
a slow oldest group cannot be bypassed by two faster younger groups.  The
completion machinery therefore includes ordered per-group closure state even
though ordinary LDG requests can complete out of order.

A long-head capacity variant finds 54 effective committed-group credits per
warp.  Groups 1--53 may complete physically but cannot retire around the
incomplete group 0; commit 54 (the 55th outstanding group) then blocks until
the head closes.  The 54->55 knee is invariant when group 0 contains
8/12/16/20/24 slow copies, separating group-record pressure from copy-token
pressure.  This is far above the commonly used shallow software pipeline and
is not the same as the larger SM-wide return/backlog crossover measured by
the L1TEX collector-capacity probe.

Two-warp tests establish ownership.  Warp 0+4 (same subcore) and warp 0+1
(different subcores) can each hold 28 ordered records behind an incomplete
head simultaneously, exceeding 54 combined without interference.  Extending
the head makes each warp independently hit its own 54->55 knee.  The credits
are therefore warp-private, not a shared subcore or SM pool.

The credit accounting is also scoreboard-indexed.  Sending every group to
SB0 stalls at 54->55, whereas alternating SB0/SB1 remains linear through 108
total groups and stalls when group 109 becomes SB0's 55th.  This proves at
least two independently accounted 54-credit domains in one warp.  It does
not yet prove that all six usable SB indices each have a physically separate
array or that no additional total cap exists above 108.

## Divergent commit expands the warp sequence (SM120)

`probe_ldgsts_divergent_commit.py` directly scans the `DEPBAR.LE SB0,N`
threshold while the submitted copies are still incomplete.  The first
threshold that passes immediately gives the number of live committed groups:

| construction | source rounds | immediate-pass threshold | groups/round |
|---|---:|---:|---:|
| converged copy + commit | 1 / 2 / 3 | 1 / 2 / 3 | 1 |
| two half-warp predicated copy+commit PCs | 1 / 2 / 3 | 2 / 4 / 6 | 2 |
| divergent halves, separate commit PCs | 1 / 2 / 3 | 2 / 4 / 6 | 2 |
| divergent halves, **same static copy+commit PC before BSYNC** | 1 / 2 / 3 | 2 / 4 / 6 | 2 |
| BSYNC first, then common copy+commit | 1 / 2 / 3 | 1 / 2 / 3 | 1 |

Thus a static `LDGDEPBAR` is not deduplicated by PC or by the enclosing BSSY
participant mask.  Every dynamic converged execution group that executes it
appends one group to the warp's scoreboard-indexed async sequence.  Explicit
reconvergence before the instruction collapses the operation back to one
warp group.  Active-lane count itself is not the count: one half-warp commit
adds one record, not sixteen.

Register-indirect fan-out gives the same result beyond two paths.  Four
execution groups funneled to one static LDGSTS/LDGDEPBAR PC require `LE 4` to
pass immediately.  With eight groups, an older 32-copy converged FIFO head
prevents early retirement; the total passes at `LE 9` (one head plus eight
subgroups), proving all eight dynamic commits were recorded.  Without the
long head, the oldest groups can finish during dispatch and only the five or
six youngest remain visible, so incomplete-count measurements must not be
mistaken for submitted sequence length.

The expanded groups consume the same physical credits.  Behind one long head,
25 and 26 rounds of two predicated half-warp commits (51 and 53 total groups)
remain on the linear issue line.  Round 27 attempts groups 54 and 55 and the
issue interval jumps from about 1642 to 2283 clocks, reproducing the ordinary
54->55 capacity knee.

This behavior closely matches NVIDIA patent US12118382B2, *Asynchronous data
movement pipeline*, which describes warp submissions as aggregated batches,
an incomplete-batch count incremented per converged-thread subset, and a
possible sequence increment between 1 and 32 under divergence.  The patent is
behavioral rather than a physical block diagram; it supports the sequence and
FIFO interpretation but says nothing about the measured queue placement or
54-credit implementation:
https://patents.google.com/patent/US12118382B2/en

## Open questions

* FILLCTRL.ZFILL (zero-fill on fault) not exercised.
* Whether all six usable SB indices scale beyond the verified SB0/SB1 pair,
  and whether there is an additional warp-wide cap at 108 or above.
