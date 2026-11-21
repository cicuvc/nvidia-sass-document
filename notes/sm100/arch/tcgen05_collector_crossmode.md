# B200 AS/WS collector interference

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

Evidence: B200 silicon, 2026-11-17. Probe:
`tests/asm_construct/probe_sm100_collector_crossmode.py`, runner:
`tools/modal_collector_crossmode.py`. Builds on the source-erasure retention
probe, preserving its original source and results.

## Conclusion

An inserted AS MMA makes all four previously filled WS B versions unavailable after shared-B erasure. An empty commit preserves them, and a WS b0 discard preserves b1..b3. This establishes cross-mode interference without identifying physical storage aliasing.

## Construction

M128 N256 K16 BF16. WS A is repeated I16 in TMEM; WS output exposes each
B element eight times. Shared A for inserted AS is all ones. B comprises
four independently populated random matrices from the earlier 512-value
finite BF16 alphabet (avoiding overflow in the AS column-sum control).
All destination writes overwrite D, rather than accumulate.

Interference sequence: fill WS b0..b3, commit/wait, execute the inserted
instruction, commit/wait, erase all shared B, fence, then load runtime query
ID and execute one WS B_REUSE, commit/wait, read all 32768 output values.
Each query ID is selected in a separate launch of identical SASS.
Empty-commit control inserts the same extra barrier phase without an MMA.
Unpoisoned and forced-discard query controls accompany every sequence.

Direct sequence: AS A_KEEP, commit/wait, erase shared B, then WS B_REUSE
on runtime-selected bN. No preceding WS fill exists in this diagnostic;
PTX's valid-B-fill precondition is not established. AS uses its own shared A,
while WS A remains I16 in TMEM.

## Results

| Prefix before B erasure and WS use | b0 | b1 | b2 | b3 |
|---|---|---|---|---|
| WS fills, no inserted instruction | old B | old B | old B | old B |
| WS fills, extra empty commit/wait | old B | old B | old B | old B |
| WS fills, WS b0 discard | zero | old B | old B | old B |
| WS fills, AS shared A discard | zero | zero | zero | zero |
| WS fills, AS shared A fill | zero | zero | zero | zero |
| WS fills, AS TMEM A discard | zero | zero | zero | zero |
| AS A fill only | zero | zero | zero | zero |

All unpoisoned queries return the expected B, and forced-discard queries
after erasure return zero. No AS-one patterns or partial remnants observed.
AS's own numerical control (A=ones, random B) produces correct column sums.
However, AS A-fill -> commit/wait -> erase shared A -> AS A-use returns zero,
just like discard. Thus direct AS-to-WS failure alone is NOT a clean physical
alias test: AS retention does not survive this tested sequence even without
switching to WS. Which operation or delay loses AS state remains unresolved.

## Interpretation

An intervening AS operation makes all four previously retained WS tiles
unavailable to B_REUSE in these sequences. The empty-commit control excludes
extra completion synchronization alone. AS TMEM-A discard shows the effect
does not require an explicit shared-A collector fill.

This is consistent with mode-associated collector invalidation/reconfiguration,
not evidence of physical corruption of four entire tiles. A WS b0-discard
control loses only b0 while retaining b1..b3, excluding arbitrary extra MMA
as a cause of global invalidation. It neither proves
nor excludes shared AS/WS physical storage. A negative direct-cross-mode result
cannot establish independent SRAM banks. No reverse WS-to-AS direct reuse or
no-completion-gap AS-to-WS retention experiment is claimed here.

## Evidence

- [Main scan](data/tcgen05_collector_crossmode_main_20261117.json.gz): 66 configurations,
  198 launches, including two unpoisoned AS controls.
- [Additional controls](data/tcgen05_collector_crossmode_controls_20261117.json.gz):
  36 configurations, 108 launches, including poisoned AS controls.

Both scans completed without numerical control failures or GPU faults, with
identical classifications across three repetitions. Full generator and base
source snapshots are in each JSON. Dependency checking remains enabled;
only the existing conservative sb_capacity advisory is accepted.

- [Final combined scan](data/tcgen05_collector_crossmode_final_20261117.json.gz):
  116 configurations, 348 launches, including WS b0-discard control.
  Modal app `ap-qCijpPo0g5zgHHYsfK99Dd`. All three scans total 654 launches.

## AS TMEM-A follow-up

[Shared/TMEM A retention controls](tcgen05_as_collector_retention.md) reproduce
the zero-after-erasure result for TMEM A as well (40 launches). This rules out
a shared-A-only explanation, without isolating the AS invalidating event.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
