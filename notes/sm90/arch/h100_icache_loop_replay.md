# H100 instruction-fetch replay and runtime patch visibility

Silicon: Modal H100 (sm_90), 2026-09-21.  The probes use repository-assembled
SASS and do not depend on ptxas.  Modal does not expose usable NCU counters, so
this note distinguishes the directly tested IVALL behavior from the still
unknown target/trace-buffer capacity.

## Result

> H100 does **not** have an IVALL-resistant tight-loop replay behavior under
> the tested construction.  A single target-side `CCTL.I.IVALL`, with no NOP
> padding after it, makes a replacement instruction visible to a previously
> hot tight loop.

This agrees with corrected GB202 and B200 measurements.  The old claim that a
tight loop defeats IVALL came from a 4096-iteration asynchronous-patcher test
that could finish before the patcher was admitted.

## Long-running asynchronous patch test

`sassdbg/probe_patch.py exp4` executes a 128-byte loop for 262144 iterations,
performs a device-side 128-bit replacement store while it is running, and
executes `CCTL.I.IVALL` on the target SM every iteration.

- gate-time replacement plus target IVALL was visible from iteration zero;
- without target-side IVALL, the running loop remained stale;
- the first long exp4 run changed at iteration 133637 (host observed patch ack
  at 133731);
- six additional runs all changed exactly once, at iterations
  132287--136691.  Their host-observed ack points were 132389--136795;
- the roughly 100-iteration ordering difference is host polling latency: the
  target can execute the replacement before the host reads the patcher's ack.

Thus all seven long-loop samples in which the patcher ran were fresh after
IVALL.

## Frozen-warp control

`sassdbg/probe_warp_mutable.py` removes asynchronous kernel-admission timing.
One divergent group heats the tight loop; its sibling freezes the warp,
the host replaces the hot instruction, and the sibling optionally performs
the invalidate before releasing the loop group.

| Case | Invalidate sequence | Valid outcome |
|---|---|---:|
| P2 | none | 29/29 stale |
| P3 | one `CCTL.I.IVALL`, zero padding | 30/30 fresh |

One additional P2 attempt failed before establishing the freeze handshake and
was classified as SETUP, not as a visibility sample.  There were zero
visibility, freeze, timeout, or abort failures among the 59 valid samples.

This frozen result is the decisive one: the IVALL instruction itself, rather
than target preemption or a large-loop refetch, makes the hot replacement
visible.

The probe also had a latent control bug: `Case.ivall="none"` was descriptive
but ignored, so a combined P2/P3 invocation could apply the global
`--ivall-count` to P2 as well.  The probe now forces P2 to zero invalidates and
classifies its expected stale result as PASS.

## Target/trace buffer remains unknown

The GB202 target/trace structure is almost invisible in execution time and
was identified with `sm__icc_requests`: slot-0 rings cross a counter boundary
at 12--13 targets, while slot-7 rings cross at 9--10.  H100 timing-only sweeps
show no corresponding boundaries:

| construction | below/above proposed boundary | cycles/visit |
|---|---:|---:|
| slot-0 JMP | 12 / 13 targets | 30.762 / 30.782 |
| slot-7 JMP | 9 / 10 targets | 5.970 / 5.933 |

The slot-0 ring remains nearly flat through 16 targets and rises at 17
(30.825 to 33.557 cycles/visit), consistent with an ICC associativity
conflict for this 4-KiB spacing.  It is not evidence for a 16-entry target
buffer: the same timing method also hides GB202's counter-proven 12-entry
structure.

Therefore the H100 conclusions are:

- no IVALL-resistant loop replay;
- ordinary instruction fetch is non-coherent without an invalidate;
- existence and depth of a smaller IVALL-flushable target/trace buffer remain
  unknown without performance counters.

## Reproduction

```bash
/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --gpu H100 --script sassdbg/probe_patch.py \
  --args 'exp1 exp2 exp4 exp6'

/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --gpu H100 --script sassdbg/probe_warp_mutable.py \
  --args '--cases P2 P3 --ivall-count 1 --ivall-nops 0 --settle 0 --repeat 30'
```

