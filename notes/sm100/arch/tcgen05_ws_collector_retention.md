# B200 WS collector retention after source erasure

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

Evidence: B200 silicon, 2026-11-17. Probe:
`tests/asm_construct/probe_sm100_ws_retention.py`; runner:
`tools/modal_ws_retention.py`.

## Conclusion

All four WS B IDs independently preserve complete old B tiles after shared-source erasure and a completion boundary. Runtime-selected reuse returns the original nonuniform data, while discard returns zeros. This establishes effective retention across the tested sequence, not a physical SRAM layout.

## Evidence

## Construction

M128 N256 K16 BF16, A in TMEM. Each 16-row group of A is I16,
so D repeats the complete B eight times, rather than checking only K sums.
Fill one or four distinct B IDs with B_KEEP; commit and wait for completion.
Warp zero overwrites the entire 32 KiB shared B source region with zero,
then FENCE.VIEW.ASYNC.S and WARPSYNC. After 32 padded NOPs, load the
query ID from a runtime scalar kernel parameter, explicitly wait, and branch
to one B_REUSE MMA. All four queries use identical SASS. Both fill and query
MMAs overwrite D (!UPT); the final query cannot obtain the old answer merely
by accumulating into the previous D. A second commit/wait uses barrier phase 1.
Read every D element with the existing scalar LDTM observer.

The query is selected separately per launch, not four successive destructive
lastuses in one launch. The common fill/erase prefix and late runtime selection
make each retained ID independently observable without an earlier query MMA
being queued before source erasure. No claim of a host-selected-after-fill
interactive challenge is made.

## Results

Each run: 20 configurations, three repetitions, 60 launches. For one ID and
for each query 0..3 after filling all four IDs:

| Source erased | Query | Result |
|---|---|---|
| no | discard | complete original B |
| no | reuse | complete original B |
| yes | discard | all zero |
| yes | reuse | complete original B |

Every launch validates 32768 FP32 output values, representing eight exact
copies of all 4096 BF16 B elements. No mixed/other values in accepted runs.
The final run also reports and verifies the runtime selector through readback.

Initial fixed-query run used the earlier 512-value B generator. Second
fixed-query and final runtime-query runs use independent pseudorandom draws
from all 65024 normal finite BF16 encodings (sign, exponent 1..254, mantissa),
seed 20261118. This is almost 16 bits of alphabet information per element,
far stronger against compression than the earlier 9-bit alphabet, but does
not mathematically prove incompressibility or an exact SRAM byte count.

Raw evidence and exact source snapshots:
- [Initial narrow distribution](data/tcgen05_ws_retention_narrow_20261117.json.gz)
- [Wide distribution, fixed query](data/tcgen05_ws_retention_wide_20261117.json.gz)
- [Wide distribution, late runtime query](data/tcgen05_ws_retention_late_20261117.json.gz)

The final run is Modal app ap-iAvVSWnL7L4IfcCLYkSVBS. All three accepted
runs total 180 launches. Dependency checking remains enabled; only the
existing conservative sb_capacity advisory is tolerated.

## Interpretation and limits

The ordinary model of a small shared collector store, time-multiplexed across
four IDs and refilled from shared memory as needed, cannot explain preservation
of every original B after the source is erased. Together with the late query,
this strongly supports simultaneous retention of four complete logical tiles
somewhere in the operand path. Pure cross-instruction N-strip scheduling with
shared refetch is also inadequate for this construction.

This does NOT locate the state: distributed PE storage, another operand cache,
or a 1 KiB frontend plus a larger downstream store remain possible. It does
not prove four physically separate 8 KiB SRAMs, nor formally exclude a store
slightly below 32 KiB using compression. Source mutation with reuse is a
hardware diagnostic, not a portable PTX correctness guarantee; reuse is
opportunistic. A negative result could reflect invalidation rather than size.

## Cross-mode follow-up

[AS/WS interference](tcgen05_collector_crossmode.md): an inserted AS MMA
makes all four WS retained tiles unavailable, whereas an empty commit preserves
all four and WS b0 discard preserves b1..b3. Physical AS/WS storage aliasing
remains unresolved.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
