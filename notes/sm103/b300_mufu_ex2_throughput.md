# B300 (sm_103) XU/MUFU throughput: EX2 doubled, everything else unchanged

Silicon: Modal B300 SXM6 (sm_103, 148 SMs) vs B200 (sm_100, 148 SMs),
2026-09-21; H100/GB202 as references.  Probe:
`tests/asm_construct/probe_sm80_admission_depth.py --mode xu*`, post-knee
steady slope of a single-warp burst (equals per-subcore XU service rate;
runners: `tools/modal_b200_probe.py --gpu B200|B300|H100`, local 5090).

| MUFU op | H100 sm_90 | GB202 sm_120 | B200 sm_100 | B300 sm_103 |
|---|---:|---:|---:|---:|
| RCP | 8 | 8 | 8 | 8 |
| RSQ | 8 | 8 | 8 | 8 |
| LG2 | 8 | 8 | 8 | 8 |
| SIN | 8 | 8 | 8 | 8 |
| TANH | 8 | 8 | 8 | 8 |
| **EX2** | 8 | 8 | 8 | **4** |

- **MUFU.EX2 is 2x faster per subcore on B300** (8 -> 4 cycles/op, exact
  steady slope).  The B300 knee also shifts slightly later (~3-4 fast
  admissions vs 2-3 elsewhere), so the XU admission queue may have picked
  up one entry alongside the faster EX2 drain.
- The speedup is a faster EX2 datapath, not more units: with two warps on
  the same subcore (`--actors same2`) the two streams timeshare one
  4-cycle service (+8 cyc/op per warp = 0.25/cyc aggregate), exactly
  halving per-warp rate like every other MUFU op.
- RCP/RSQ/LG2/SIN/TANH are unchanged at 8 cycles/op on B300; same2
  aggregate 0.125/cyc on both B200 and B300.
- XU remains fully disjoint from the fixed ALU/FMA domains on all four
  architectures (no interaction with the fixed-pipeline domain map).
