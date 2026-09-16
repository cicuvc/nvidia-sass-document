# GA100 scalar-math pipes and ALU/FMA sharing

Hardware: NVIDIA A100-SXM4-40GB, compute capability 8.0.  Measurements were
made in September 2026 with native sm_80 cubins from this repository and
Nsight Compute 2023.1 running with performance-counter permission.

## NCU-visible pipe partition

GA100 exposes only the older top-level instruction counters
`smsp__inst_executed_pipe_{alu,fma,fp16,fp64}`.  It does not expose the
`fmaheavy_subpipe_{alulite,fmaheavy}` leaf counters available on GB202.  A
minimal kernel containing 128 copies of each target instruction gives the
following exact partition.  The six initializer MOVs account for the ALU
counter floor of six in non-ALU kernels.

| NCU pipe | Mnemonics measured (+128 target instructions) |
|---|---|
| ALU | `BMSK F2FP FMNMX FSEL FSET FSETP I2I I2IP IABS IADD IADD3 IADD32I IMNMX ISCADD ISCADD32I ISETP LEA LOP LOP3 LOP32I MOV MOV32I P2R PLOP3 PRMT PSETP R2P SEL SGXT SHF SHL SHR` |
| FMA | `FADD FADD32I FFMA FFMA32I FMUL FMUL32I FSWZADD IDP.2A IDP.4A IMAD IMUL IMUL32I` |
| FP16 | `HADD2 HADD2_32I HFMA2 HFMA2_32I HMNMX2 HMUL2 HMUL2_32I HSET2 HSETP2` |
| FP64 | `CLMAD DADD DFMA DMUL DSETP` |

Seven scalar mnemonics present in the sm_120 catalog do not have encodable
mnemonics in the current sm_80 database: `F2IP`, `I2FP`, `MOV64IUR`,
`VIMNMX`, `FHADD`, `FHFMA`, and `VIADD`.

The important generational difference is that GA100 counts FP32 FADD/FFMA
and integer IMAD/IMUL/dot product on the same FMA pipe.  In a same-subcore
two-warp test, a four-times-long FFMA contender serializes an IMAD victim (and
vice versa): the victim slope grows from 2 to 10 clocks/instruction.  Thus the
GA100 counter is not merely a logical aggregate of the independently
accepting GB202 FMA-Heavy and FMA-Lite leaves; these tested operations expose
one common execution service on A100.

## Hidden ALU admission classes

Although NCU reports all 32 operations above as `pipe_alu`, an all-source-
reuse structural-conflict scan separates two admission behaviours.  Each
instruction alone takes exactly 2 clocks per warp instruction on one GA100
subcore.

With a four-times-long FMA contender on the same subcore:

| inferred ALU admission class | Mnemonics | victim slope |
|---|---|---:|
| heavy | `IADD3 LOP3 PRMT SHF` | 4.000000 clocks/instruction |
| light | all other measured ALU mnemonics in the table above | 2.585938 clocks/instruction |

The different-subcore control remains 2.000000.  All source slots were marked
reusable, so this split is not RF read bandwidth.  Repeating representative
tests with both results discarded to `RZ` gives the same values:

| pair (same subcore) | normal destination | `Rd=RZ` |
|---|---:|---:|
| `IADD + IMAD` | 2.585938 | 2.585938 |
| `MOV + IMAD` | 2.585938 | 2.585938 |
| `IADD3 + IMAD` | 4.000000 | 4.000000 |
| `IADD + FFMA` | 2.585938 | 2.585938 |
| `FFMA + IMAD` (same FMA pipe) | 10.000000 | 10.000000 |

It is therefore also not scalar-RF writeback arbitration.  Calling the two
sets *ALU Heavy* and *ALU Lite* is a microarchitectural inference from their
admission behaviour; GA100's public counters do not expose those leaf names.

## What ALU Lite and FMA share on GA100

The best-fit model is not a shared arithmetic body:

```text
                  one subcore warp scheduler
                           |
                 common issue/admission control
                     /             \
       inferred ALU-Lite body      FMA body
       (gap-using admission)       (2-cycle warp service)
                     \             /
                  common scalar RF domain
```

A same-pipe victim with a 4x contender has slope 10, whereas an ALU-Lite/FMA
pair has slope only 2.585938.  Most of their execution occupancy therefore
overlaps.  The residual penalty survives both operand reuse and `Rd=RZ`,
placing the shared resource before execution/writeback: most likely the
single warp scheduler's issue selection, dispatch wiring, or a common
admission-credit boundary.

The inferred heavy ALU class paired with FMA has slope four.  This still does
not imply a common arithmetic unit: separate exposed FP16 and FMA pipes also
produce slope four, while same-pipe FP16/FP16 produces slope ten.  Rather,
two heavy-class warp instructions cannot exploit the admission gaps that a
light ALU instruction can use.

Consequently, the GB202 phrase **Shared FMA Heavy = ALU Lite + FMA Heavy**
must not be projected literally onto GA100.  On A100, NCU exposes ALU and FMA
as separate physical pipe domains, and the directly visible sharing is a
subcore-front-end admission effect.  Any deeper common physical placement,
clocking, or wiring cannot be isolated by these counters.

## Reproduction

The NCU catalog uses
`tests/asm_construct/probe_scalar_pipe_catalog.py` with
`ASSEMBLER_ARCH=sm80`.  The single-warp floor can be checked with the first
probe below; structural sharing is measured by the second:

```bash
python3 tests/asm_construct/probe_sm80_scalar_overlap.py

python3 tests/asm_construct/probe_sm80_scalar_conflict.py \
  --pair iadd_rz,imad_rz --pair iadd3_rz,imad_rz \
  --pair ffma_rz,imad_rz --counts 128,256 \
  --placements solo,same,different --factor 4
```

The two-warp test uses warp 0 as victim, warp 4 as the same-subcore contender,
and warp 1 as the different-subcore control.
