# B200 AS collector: commit boundaries versus issue gaps

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

B200 silicon, 2026-11-17. Probe `tests/asm_construct/probe_sm100_as_commit.py`,
runner `tools/modal_as_commit.py`, analyzer `tools/analyze_tcgen05_as_commit.py`.
[Raw data and exact generator/base/matcher sources](data/tcgen05_as_commit_20261117.json.gz).
Modal app `ap-XkSLvTD3wtonEvAxUlKemM`.

## Conclusion

Continuous AS A reuse retains its throughput and shared-interference benefit with a UTCBAR after every MMA, provided no intermediate wait occurs. Long issue gaps remove the observable benefit even without intermediate commits. The measured effect constrains reuse eligibility, not a physical buffer lifetime.

## Evidence

## Question and construction

Does AS reuse end at a commit boundary, or disappear when the issue stream
has a long gap? This experiment never modifies A or B during the MMA sequence.

M128 N64 K16 BF16, shared A and B all ones. D initially zero, each MMA
accumulates 16; all 128x64 output values and remaining 192 zero guard columns
are validated. Reuse is A_KEEP first, A_REUSE.A_KEEP on every later MMA;
discard never requests reuse. Counts 64/256 produce two-point steady slopes.

Four issue sequences: continuous; UTCBAR after every MMA without waiting;
32 NOPs (stall 8 each) between MMAs without intermediate commit; both UTCBAR
and the NOP gap. The last MMA has no trailing gap and uses the common final
commit/wait. For per-MMA commit, mbarrier expected arrival count is set to the
MMA count; all commits arrive at one phase, waited only at the end. Thus no
premature phase recycling or intermediate completion wait is introduced.

With/without three independent LDS.128 meter warps, 2048 iterations each,
using the previously validated 12-load meter and scratch area. Their checksums
and output values are checked. Minimum simultaneous three-warp coverage of
the MMA interval is 96.196%; meter extends past every MMA sequence. Its span
is an interference indicator, not a byte counter.

## Results

Slopes use `(T256-T64)/192`. Gap column is scheduled NOP count, not a direct
measurement of collector lifetime. MMA slopes below are without LDS meter;
LDS slopes are the fixed-work meter-span extension per additional MMA.

| Intermediate commit | Gap NOPs | MMA discard | MMA reuse | LDS discard | LDS reuse |
|---|---:|---:|---:|---:|---:|
| no | 0 | 48 | 32 | 47.828125 | 15.244792 |
| every MMA, no wait | 0 | 48 | 32 | 47.828125 | 15.250000 |
| no | 32 | 258 | 258 | 47.432292 | 47.427083 |
| every MMA, no wait | 32 | 270 | 270 | 46.671875 | 46.671875 |

All units cycles/MMA. With LDS pressure, continuous discard MMA slope is
49.864583, reuse stays 32, identically with/without intermediate commits.
Gap cases have the same MMA slopes with/without the meter. Do not infer loss
of reuse solely from gap-dominated MMA throughput; the independent LDS result
is what distinguishes preserved bandwidth savings from their disappearance.

32 configurations, one warmup plus five retained samples = **192 launches**,
zero numerical/checksum/guard errors. Dependency checking is enabled and only
existing sb_capacity advisories are accepted. Full local build passes.

## Interpretation

Inserting a commit after every MMA preserves throughput and shared-interference benefits, provided no intermediate wait occurs.

A long issue gap alone, without intermediate commit, removes the observable
shared-traffic advantage. This favors short-lived pipeline reuse/retention
that is released or no longer eligible once the issuing stream has a gap,
rather than an architectural commit-group lifetime. The continuous control exhibits a large, reproducible benefit with the same operands and output.

This does not locate a physical buffer or identify whether release is caused
by completion/drain, a timeout, queue-state transitions, or matching logic.
The test does not establish an exact gap threshold. LDS interference is not
an exact traffic counter; describe disappearance of observable reuse benefit,
not a measured count of A reload bytes. The prior wait-and-source-erasure
results are consistent with this short-lived-state model.

Reproduction:

```
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_as_commit.py --output /tmp/as-commit
python tools/analyze_tcgen05_as_commit.py /tmp/as-commit/result.json
```

The dedicated probe internally runs five retained repetitions plus a warmup.

## Residency-isolation follow-up

[Maximal-shared residency control](tcgen05_as_collector_isolation.md) reproduces
the same continuous reuse benefit and gap-associated loss after exhausting
the SM shared residency budget. Ordinary same-SM concurrent kernel residency
is therefore not required for the observed phenomenon.

[Gap/yield sweep](tcgen05_as_collector_gap.md) further finds indistinguishable
NOP yield0/1 results. Fine sampling preserves nearly full LDS savings at
MMA slope50, finds partial savings at58–90, and none at98 and above.
UTCHMMA yield changes sparse pacing by one cycle without changing the
tested qualitative reuse regimes. A fixed physical lifetime has not been
established. The alternate NOP count/stall control matches8×stall8 and
16×stall4 at66 cycles/MMA and the same LDS advantage, rejecting a simple
NOP-count-only explanation at those points.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
