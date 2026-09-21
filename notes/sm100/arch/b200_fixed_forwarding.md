# B200 fixed-pipeline result forwarding

Silicon: Modal B200 (sm_100a), 2026-09-21. Cubins are assembled directly by
the repository assembler. Primary probes are the shared
`tests/asm_construct/probe_*_latency.py` suite plus:

- `probe_sm100_fp32x2_latency.py` for FADD2/FMUL2/FFMA2;
- `probe_sm100_latency_phase.py` for raw values at phase-sensitive gaps.

The producer destination is first poisoned, then the producer is issued and a
consumer reads it after a controlled issue gap. `fine` uses stall-1 NOPs;
`coarse` uses fewer large-stall NOPs. The permanent poison-to-fresh boundary is
reported. A `fine/coarse` pair therefore describes earliest observed and
conservative phase placement; it is not an instruction control-code stall
value by itself.

## High-level result

The forwarding results are consistent with three established subcore-local
fixed-pipeline domains and a packed Heavy+Lite mode. Dedicated cross-subcore
probes now favor four local FP64 slices, although physical placement is not
proved:

```text
per subcore:  ALU  |  FMA Heavy  |  FMA Lite
                           \         /
                            PACKED_LOCK (HFMA2 and FP32x2)

likely:       4 x 0.5 inst/cycle FP64 slices, one per subcore
alternative: a sufficiently buffered/multiported central implementation
                               |
                  result return/bypass ingress
```

The latency probes contain only one producing warp and establish result-path
visibility, not replication of the execution array. The additional
cross-subcore probes below provide the locality evidence; the uniform FP64
boundary by itself only locates result return into the subcore-facing bypass
network.

Backend identity alone is also insufficient to predict every forwarding
boundary. B200 has opcode-specific fast and late result stages. Many results
reach FMA Heavy/Lite, FP16, or ALU Heavy in two cycles, while ALU Lite is often
one crossbar hop later. At deliberately unsafe gaps, a late-result producer
can expose its **source A**, not merely the old destination value.

## Common backend matrix

The following table describes the common representatives; exceptions are in
the next sections.

| producer -> consumer | fine | coarse |
|---|---:|---:|
| ALU -> ALU Heavy/Lite | 2 | 2 |
| fast ALU-result opcode -> FMA Heavy/Lite/FP16 | 2 | 2 |
| late ALU-result opcode -> FMA Heavy/Lite/FP16 | 3 | 4 |
| scalar FMA Lite -> FMA Heavy/Lite/FP16 | 2 | 2 |
| scalar FMA Lite -> ALU Lite | 3 | 4 |
| scalar FMA Lite -> ALU Heavy | normally 2 | 2 |
| FMA Heavy -> FMA Heavy/Lite/FP16 | 2 | 2 |
| FMA Heavy -> ALU Lite | 3 | 4 |
| FMA Heavy -> ALU Heavy | opcode-dependent 2 or 3/4 | |
| ordinary packed FP16 -> FMA Heavy/Lite/FP16/ALU Heavy | 2 | 2 |
| ordinary packed FP16 -> ALU Lite | 3 | 4 |

Thus B200 differs sharply from H100. On H100, ordinary HFMA2 has a two-cycle
same-FP16 bypass but takes 3/4 to either FMA leaf. On B200, ordinary packed
FP16, FMA Heavy, and FMA Lite all exchange results at two cycles. This fits a
much tighter Heavy+Lite `PACKED_LOCK` arrangement.

## Opcode-specific ALU result paths

Every tested ALU producer reaches ALU Heavy and ALU Lite consumers at two
cycles. The distinction appears when the consumer is FMA Heavy/Lite or FP16.

Two-cycle fast-result group:

- nominal ALU Lite: FMNMX, FSEL, FSET, IMNMX, SEL;
- nominal ALU Heavy: IADD3, LOP, LOP3, PRMT, SHL, SGXT, HMNMX2, HSET2.

Late group, permanently fresh at fine 3/coarse 4:

- IADD/IADD32I, MOV;
- ISCADD/ISCADD32I, LEA, LOP32I, SHF, SHR, IABS, BMSK;
- F2FP, F2IP, I2FP, I2I, I2IP, P2R.

Several late arithmetic/conversion instructions expose source A at the middle
gap rather than keeping the poisoned destination. Others remain cleanly stale
until fresh. Both classes have the same permanent 3/4 boundary.

This opcode split is stronger than the static ALU-Heavy/ALU-Lite labels. It
likely reflects which internal result stage or bypass mux an opcode selects.

## FMA Heavy and Lite

Scalar FADD/FFMA/FMUL results reach FMA Heavy, FMA Lite, FP16, and normally
ALU Heavy at two cycles, but ALU Lite at 3/4. Scalar FHADD/FHFMA variants use
the late ALU-Heavy path: gap 2 exposes Ra and permanent fresh begins at 3/4.

FMA-Heavy FSWZADD reaches ALU Heavy at two cycles. IDP.2A/4A, IMAD, IMUL, and
IMUL32I instead expose Ra at gap 2 and become permanently fresh at fine
3/coarse 4. All tested Heavy results reach FMA Heavy, FMA Lite, and FP16 at
two cycles, and ALU Lite at 3/4.

The Heavy/Lite reciprocal two-cycle paths support distinct execution leaves
with a close shared result network. They do not imply one admission queue:
the admission/service experiments still distinguish scalar Lite from Heavy.

## Packed FP16 and FP32x2

Ordinary HADD2/HMUL2/HFMA2, including HFMA2.MMA on B200, have:

| consumer | fine | coarse |
|---|---:|---:|
| FMA Heavy/Lite, FP16, ALU Heavy | 2 | 2 |
| ALU Lite | 3 | 4 |

HMUL2_32I and HFMA2_32I expose Ra to ALU Heavy at gap 2 and become fresh at
3/4; HADD2_32I keeps the ordinary two-cycle path. `HADD2.F32` reaches FMA
Heavy/Lite and FP16 at 2, but both ALU consumers at 3/4.

The new sm_100 FP32x2 operations were measured on both destination halves:

| producer | ALU Lite | all other tested ALU/FMA/FP16 consumers |
|---|---:|---:|
| FADD2 | 3/4 | 2 |
| FMUL2 | 2 | 2 |
| FFMA2 | 2 | 2 |

Lo and hi halves are identical. FFMA2 therefore has an unusually broad
two-cycle packed-result bypass. This agrees with the throughput/admission
evidence that FFMA2 and HFMA2 occupy one effective packed state, while also
showing that their final result stages are not bit-for-bit identical.

Unlike H100, B200 `HFMA2.MMA` does **not** show the FP64-like 4/7 boundary; it
has the same 2 or 3/4 topology as ordinary packed FP16. The `.MMA` suffix is
therefore not evidence of an FP64 backend on B200.

## IMAD.WIDE and IMAD.HI

| result -> consumer | boundary |
|---|---:|
| IMAD.WIDE low -> FMA Heavy/Lite/FP16 | 1 |
| IMAD.WIDE low -> ALU Heavy | 2 (Ra is visible at gap 1) |
| IMAD.WIDE low -> ALU Lite | phase-sensitive gap 1; fine-safe 2 |
| IMAD.WIDE high -> FMA Heavy/Lite/FP16 | 2 |
| IMAD.WIDE high -> ALU Heavy/Lite | fine 3 / coarse 4 |
| IMAD.HI -> FMA Heavy/Lite/FP16 | 2 |
| IMAD.HI -> ALU Heavy/Lite | fine 3 / coarse 4 |

As on H100, the wide low half has the fastest path on the chip, reaching the
FMA/FP16 result network at gap 1. B200 additionally shows explicit Ra exposure
when an ALU consumer reads that path too early.

## FP64 and CLMAD

Lo and hi halves are identical, and every tested ALU Heavy/Lite, FMA
Heavy/Lite, FP16, and FP64 consumer sees the same result-return boundary:

| producer | fine | coarse |
|---|---:|---:|
| DADD/DMUL/DFMA | 4 | 7 |
| CLMAD.LO | 5 | 9 |

These match H100 despite the throughput differences. This measurement alone
locates only the return/bypass path after execution.

`probe_mio_queue_depth.py` and
`probe_sm100_fp64_cross_subcore.py` provide three locality checks:

1. Short sustained streams are exactly `5+2N` clocks for one warp and
   `6+2N` for two or four different-subcore warps over `N=0..40`. The one
   clock difference already exists at `N=0`; DADD adds exactly two clocks in
   every placement, with no knee or growing cross-subcore penalty.
2. After a counted rendezvous, the local `CS2R; DADD/DFMA; CS2R` interval is
   identical to NOP and predicated-off-DADD controls. For the contiguous
   one/two/three/four-subcore placements it is exactly three clocks in every
   one of 101 repetitions. In the three-subcore case all three starting
   timestamps are equal, so this is a genuinely simultaneous admission test.
3. A synchronized unsafe RAW probe reproduces the solo DADD boundary: gaps
   1--3 read poison and gap 4 reads the completed value. Every warp in
   `diff3`, `diff4`, `(0,2)`, and `(0,3)` has the same boundary in every
   repetition; no contender pushes any completion to gap 5.

This rejects the simple model of a two-warp-instruction/cycle SM-wide service
that serializes simultaneous subcore requests visibly at admission or
completion. Together with the aggregate rate of four instructions per two
clocks, the best working model is **one 0.5 instruction/clock FP64 slice per
subcore**. It is still not a physical-layout proof: a centralized service
with enough input buffering and completion bandwidth could deliberately
produce the same externally visible behavior.

## Predicate forwarding

| producer -> consumer | fine | coarse |
|---|---:|---:|
| ordinary arithmetic predicate -> selector/P2R | 2 | 2 |
| R2P-produced predicate -> selector/P2R | 3 | 4 |
| IMAD.WIDE/HI Pu -> selector/P2R | 3 | 4 |
| any tested predicate -> instruction guard | 7 | 12 |
| any tested predicate -> BRA guard | 7 | 12 |

The guard/CBU path is unchanged from H100 and agrees with the conservative
stall-13/yield-1 scheduling rule used by sassdbg.

## Source-A exposure at unsafe gaps

Twelve-repeat raw dumps are deterministic:

| dependency at unsafe gap | observed | meaning |
|---|---:|---|
| IADD -> FADD, gap 2 | `0x3f7fffff` | IADD Ra |
| ISCADD -> FADD, gap 2 | `0x00000000` | ISCADD Ra |
| IMAD -> IADD3, gap 2 | `0x00000002` | IMAD Ra |
| HFMA2_32I -> IADD3, gap 2 | `0x3f803c00` | HFMA2 Ra |
| IMAD.WIDE.low -> IADD3, gap 1 | `0x00000002` | IMAD Ra |

The following gap returns the correct final value in every case. This is not a
torn destination write and not stochastic launch residue. The best working
interpretation is that the dependency selects the producer's bypass entry
before its arithmetic result replaces the source-A/collector token. Correct
compiler scheduling never exposes this state; it is nevertheless useful
evidence for the placement of operand collection relative to result bypass.
