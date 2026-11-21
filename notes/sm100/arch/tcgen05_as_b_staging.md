# AS M128 B staging versus output visibility

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-19
**Probe:** `tests/asm_construct/probe_sm100_as_b_stage.py` on Modal NVIDIA B200
**Open items:** 2
**Audit:** 23040 launches; complete D, shared-byte readbacks, clocks, controls, and joint snapshots including in-flight LDS confirmation validated

## Conclusion

The measurements support **B input-version fixation before output becomes
visible**, with an N8 grouping on the input side and a two-column/cycle
observable progression on the output side. They do not identify a physical
K16×N8 buffer, its capacity, or the internal partition compute operation.

The completed experiments establish these constraints:

| observable | result |
|---|---|
| N grouping | sparse writes to each of eight columns share an N8 input-version cutoff within the tested K8 half |
| K halves | the separately tested K8 halves have cutoff curves displaced by one cycle |
| staging before output | 318 same-launch witnesses confirm new shared bytes with LDS while LDTM still sees D sentinels and final D uses old B |
| region agreement | all eight I16 replicas, including all four 32-row regions, select the same B version |
| input/output progress | input sensitivity advances roughly N8 per two cycles; output visibility roughly two columns per cycle |

An input/output rate difference does not locate storage. A sequence of input
staging registers, operand collectors, partial products, and pending output
writes can produce the same observations. In particular, these probes cannot
show that the original B values remain in a 256-byte temporary until the
last output pair becomes visible.

The [WS shape follow-up](tcgen05_ws_b_versions.md) applies final B-version
comparison to M32/M64/M128. M128 still agrees across all four regions, while
M32 and cross-N M64 pairs can differ under a reversed writer lane mapping.
Those completed-output measurements remove in-flight LDTM ambiguity but
retain shared-store timing as a confounder for distinct B addresses.

## Evidence

### Sparse perturbations: N8 input grouping with distinct K-half cutoffs

The [cutoff run](data/tcgen05_as_b_stage_cutoff_20261119/result.json.gz)
contains **13824 launches**: 1296 controls and 12528 races. Every complete
D matrix, modified shared-memory patch, counter, and timestamp is rechecked
offline. There are no outside-patch changes, unexpected D values, control
failures, or disagreements between the eight repeated identity matrices.

A consists of eight copies of I16 in TMEM. Initially B=1, so final
`D[m,n]=B[m%16,n]`. The writer changes B to 2 in either K0..7, K8..15, or
both halves. N8 starts are 0, 8, 16, 24, 64, 128, 192, and 240. Within each
block, the writer selects one of its eight columns or all eight. Both forward
and reversed lane-to-address assignments are tested.

The single-column update touches only 16 bytes in a K8 half, or 32 bytes
across K16. It is predicated by physical address, so reversing the lane map
preserves the exact modified elements. This removes the need to modify an
entire 128-byte tile just to test one column's input sensitivity. The selected
column, the lane map, and the N8 block are runtime parameters of the same
binary for a given width/K-half/control mode.

For the 8352 racing single-half samples, the following empirical rules have
**zero mismatches**, including both lane maps and all column selections:

```text
s = pre-STS timestamp - first post-MMA timestamp
n = aligned N8 start

K0..7:  new B affects D iff s <= n/4 - 9
K8..15: new B affects D iff s <= n/4 - 8
```

These are **store-issue sensitivity rules**, not exact shared-memory fetch
clocks. STS service and shared-to-async visibility contribute an unknown
constant offset. The same store form and bank layout make the relative
N/K progression useful, but do not remove that offset.

| N8 start | K0..7 latest new / earliest old | K8..15 latest new / earliest old |
|---:|---:|---:|
| 0 | −11 / −8 | −8 / −5 |
| 8 | −8 / −5 | −8 / −5 |
| 16 | −5 / −4 | −4 / −3 |
| 24 | −3 / 0 | −3 / 0 |
| 64 | +7 / +11 | +7 / +11 |
| 128 | +22 / +27 | +22 / +27 |
| 192 | +39 / +44 | +39 / +44 |
| 240 | +49 / +52 | +52 / +53 |

Every row applies to each of the eight individually modified columns and the
whole-N8 control, with either lane map. The normalized empirical K0 and K8
curves are separated by one cycle. N0 at phase −8 and N16 at phase −4 provide
same-phase independent-launch examples: K0 is already insensitive while K8
is still sensitive. The two kernel variants differ in the shared address
immediate; they do not simultaneously modify both halves.

Across all **1392** width × K-half × N8 × lane-map × pad groups, the normalized
new-value fraction is identical for all nine column selections. Thus the N8
grouping survives reducing the writer from a full tile to one column.
The phase grid is finite: this is not a claim that untested subcycle or
intra-column differences cannot exist.

The slope is one K16×N8 block per approximately **two cycles**. The prior
[TMEM scalar sweep](tcgen05_as_tmem_snapshot.md) has approximately one N8
output interval per **four cycles**, with paired-column tail deviations.
Over N0→N240, these two observables shift by about 60 and 120 cycles,
respectively. Their absolute intercept difference is not a buffer residence
latency: the writer and reader have different service delays and the kernels
are different.

[Full analysis](data/tcgen05_as_b_stage_cutoff_20261119/analysis.txt) ·
[cutoff plot](data/tcgen05_as_b_stage_cutoff_20261119/cutoffs.svg).

### A two-half writer still exposes its own service order

There are 153 mixed results from the width-256 writer. This includes sparse
single-column updates, so shrinking the modified footprint does **not** by
itself make a warp store temporally atomic. Forward lanes produce K0-new /
K8-old in 45 cases; reversed lanes produce K0-old / K8-new in 108 cases.
For example, at N192 and phase +37, reversing the lane assignment reverses
which K8 half is new, for both sparse columns and whole-N8 writes.

This reproduces the warning from the earlier
[B-fetch tomography](tcgen05_as_b_fetch_tomography.md): a mixed 256-byte
update is not proof that the tensor unit atomically acquires one half before
the other. The separately modified half-tile curves are the cleaner evidence
for their distinct input-version sensitivities. Even those curves cannot
exclude an address-dependent difference in writer visibility.

### Same launch: B fixed while D is still unreadable as a result

The [joint run](data/tcgen05_as_b_stage_joint_20261119/result.json.gz)
contains **4608 launches**: 432 controls and 4176 races. It uses the two-half
writer for columns 0, 3, and 7 within each of the eight N8 blocks, both lane
maps, and three repeats. D is initialized to `-(n+1)` before the single MMA.

After the writer executes STS and `FENCE.VIEW.ASYNC.S`, the **same warp** reads
its selected D column with scalar LDTM and explicitly waits for the result.
It saves all 32 lane values. No global stores occur in this interval;
all diagnostics are exported after the final CTA rendezvous. The final
shared readback proves B=2 at every selected K value. There are no further B
stores, and all 32768 final D elements are checked.

**600 samples** have all three properties:

1. The selected K16 column in shared memory was changed from 1 to 2 and fenced.
2. All 32 observer lanes still read the initialized negative D sentinel.
3. The final corresponding D values are all 1, using the old B version;
   all four 32-row regions agree.

The counts by N8 start are 27, 30, 33, 36, 108, 132, 162, and 72 for
0, 8, 16, 24, 64, 128, 192, and 240. One N240/column240 example is:

| event | cycles relative to first post-MMA stamp | observation |
|---|---:|---|
| pre-STS clock | +51 | start changing all K values of B column 240 |
| clock after store dependency/fence | +74 | shared write/fence sequence finished |
| pre-LDTM clock | +79 | read D column 240 |
| first post-LDTM instruction | +85 | |
| LDTM scoreboard wait finished | +103 | all 32 lanes returned −241 |
| producer completion-wait stamp | +223 | |
| final shared readback | after rendezvous | B column 240 is all 2 |
| final D readback | after rendezvous | D column 240 is all 1 |

This establishes a mutation-insensitive result before the corresponding
output is visible to the sampled LDTM. It is consistent with prior B fetch
into a temporary, but also with computation already completed into a
non-TMEM result stage. The read returns a sample acquired during its service
window; the +103 completion stamp does not mean D remained sentinel until
exactly +103. The producer +223 stamp includes the completion-wait scaffold.

Every early control orders the store **and snapshot completion** before MMA;
the snapshot must be sentinel and final selected D must be 2. Every late
control orders MMA completion before the store/read; snapshot and final D
must remain 1 despite shared B becoming 2. The no-mutation control leaves B
at 1. Full payload validation finds no snapshot-other values, control errors,
final outside-region errors, or M-replica disagreements.

[Full analysis](data/tcgen05_as_b_stage_joint_20261119/analysis.txt) ·
[same-launch timeline](data/tcgen05_as_b_stage_joint_20261119/cutoffs_witness.svg).

### Stronger witness: LDS confirms the new shared bytes before LDTM

The first joint suite verifies shared contents after completion; its fence
timestamp alone is not a direct measurement of when the new bytes are
readable. The [checked run](data/tcgen05_as_b_stage_checked_20261119/result.json.gz)
adds **LDS.64 plus an explicit scoreboard wait** between the store/fence and
LDTM. All 32 lanes read the entire 256-byte K16×N8 patch; their results are
saved in physical-address order and independently checked, including the
unchanged columns. A timestamp after this LDS wait precedes the pre-LDTM
timestamp. Both operations reuse SB2 only after draining its previous claim.

All **4608 launches** pass (432 controls, 4176 races). The early/late controls
now order the shared readback and D snapshot together. There are **318**
strong witnesses where the in-flight LDS reads the new selected B values,
then LDTM still returns D sentinels, and final D uses old B in all 128 rows.
Counts by N8 start are: N8=6, N64=33, N128=108, N192=135, N240=36.
None is captured at N0/N16/N24 with the extra LDS delay; this narrower timing
window does not invalidate the weaker earlier witnesses.

One N240/column240 example has this ordering, within a single launch:

| event | phase | returned/verified value |
|---|---:|---|
| pre-store clock | +53 | change B column 240 from 1 to 2 |
| store/fence sequence finished | +76 | |
| LDS scoreboard wait finished | +90 | all selected K values observed as 2 |
| pre-LDTM clock | +95 | |
| LDTM scoreboard wait finished | +119 | all 32 lanes returned −241 |
| producer completion-wait stamp | +223 | |
| final D | after rendezvous | all 128 rows of column 240 equal 1 |

The independently checked shared read completes before LDTM is issued.
This strengthens the input-fixation observation beyond merely timing a
store. It still does not locate the retained operand/result state, or imply
that a concurrent tensor read has portable synchronization semantics.
The measured LDS-check interval is 14 cycles after the fence stamp in all
4176 races. Some LDTM reads stall substantially; only their returned values
and explicit ordering, not an assumed fixed read latency, enter the witness.

[Full analysis](data/tcgen05_as_b_stage_checked_20261119/analysis.txt) ·
[LDS-confirmed timeline](data/tcgen05_as_b_stage_checked_20261119/cutoffs_witness.svg).

## Construction and interpretation limits

The source extends the validated B-fetch generator, preserving the identity
mapping and future-epoch clock waits. The no-swizzle physical B offset is
`2*((n//8)*128 + (k//8)*64 + (n%8)*8 + k%8)`. Thus a K8×N8 tile is 128 bytes,
and the two K halves of K16×N8 occupy adjacent 128-byte regions. This is the
address layout used by the experiment, not proof of a hardware transaction.

The sparse writer uses a single predicated STS or STS.64. Its per-lane address
is still a forward/reversed contiguous chunk assignment, and its predicate
selects the desired N column from that physical chunk index. Runtime
`select_col=8` enables the whole N8 patch. Each final shared readback includes
both modified and unmodified bytes, detecting a wrong column/half mask.

The cutoff suite has nine kernel variants. Each joint suite has three. All
pass full sm100a assembly with strict dependency checking; only the existing
`sb_capacity` conservative CFG advisory is accepted. The original cutoff
sources are unchanged when the joint variant is added. Python syntax checks,
static mask checks for both lane maps, and the complete hardware control
matrices pass.

All three runs use three control modes before any races. The cutoff suite has
432 writer configurations and one repeat; each joint suite has 48 configurations and
three repeats. Races use the 29 existing pads, with nominal
`delta=16*floor(N8_start/64)-64`; measured phases, not nominal pads, determine
the analysis. The joint initialization and observer change the binary and
may perturb scheduling. Its raw cutoff values should not be silently merged
with the separate cutoff suite into one exact threshold.

All four 32-row output regions are checked after completion. In-flight
snapshots in this joint test observe warp 1's region only; the earlier
scalar LDTM tests cover warps 1, 2, and 3 separately. Neither test directly
observes an internal tensor-core partition, and four row regions agreeing
does not prove a broadcast from one shared physical buffer.

Runner: `tools/modal_as_b_stage.py`, using durable Modal FunctionCall IDs and
frozen source/hash metadata. Analyzer:
`tools/analyze_tcgen05_as_b_stage.py RESULT --plot STEM`.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Where is the state retained after shared B loses influence: raw K16×N8
  operands, multiple queued tiles, partition-local operands, partial products,
  or pending D writes? What is its capacity and sharing topology?
  <!-- open-question: open blocked-by "needs independent pressure or retention perturbation that distinguishes operand storage from computed-result staging" -->
- Does the two-column D visibility progression equal physical writeback
  atomicity and four-cycle 32×N8 partition output service? LDTM itself has a
  matching two-column service pattern, and row-atomic extent is unknown.
  <!-- open-question: open blocked-by "needs a read-side observable that separates LDTM service and row mapping from internal writeback" -->
