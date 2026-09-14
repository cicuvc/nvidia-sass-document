# Volta register-bank read bandwidth (V100S, 2026-09)

## Result

The controlled SASS experiment reproduces the Volta microbenchmarking
paper's register-bank result: Volta has two parity-selected RF banks, and one
bank can supply **two distinct 32-bit warp operands in one operand-collection
clock**.  A third source from that bank costs one additional clock.

This is stronger than the old Hopper single-warp result.  Hopper's native
two-clock FFMA cadence hid whether its two same-bank operands were collected
together or in consecutive clocks.  On V100, the following FFMA comparison
isolates the extra bank-read clock above the same two-clock execution floor.

## Experiment

Hardware: Tesla V100S-PCIE-32GB (sm_70).  The kernel is assembled from the
native `sm_70_instructions.txt` database and runs one 32-thread warp.  Each
timed region contains 512 straight-line independent-destination operations,
uses scheduling `stall=1, yield=0`, and is bracketed by `CS2R SR_CLOCKLO`.
The reported value is the minimum of 15 warm repetitions.

`E` and `O` mean even- and odd-numbered source registers.  All sources are
distinct; destination selection and instruction schedule are identical
between parity cases.

| stream | source demand | cycles | cycles/instruction |
|---|---:|---:|---:|
| NOP | none | 520 | 1.016 |
| FADD | 2E | 1031 | 2.014 |
| FADD | 1E + 1O | 1031 | 2.014 |
| FADD | 2O | 1031 | 2.014 |
| FFMA | 3E | 1541 | **3.010** |
| FFMA | 3O | 1541 | **3.010** |
| FFMA | 2E + 1O, any operand ordering | 1031 | **2.014** |
| FFMA 3E + `.reuse` on any one source | effective 2E | 1031 | **2.014** |

The same ratios appear with a 128-instruction region: NOP 1.063,
FADD/FFMA-2+1/reused-3E 2.055, and FFMA-3E 3.039 cycles/instruction.  A
1024-instruction fully unrolled body crosses a separate instruction-fetch
capacity cliff (even NOP rises to about 3.53 cycles/instruction), so that size
is excluded from the RF inference.

## Interpretation

A compact empirical service law for these streams is:

```text
cycles/instruction = max(Volta FP32 execution floor,
                         even-bank source count,
                         odd-bank source count)

Volta FP32 execution floor = 2 clocks for FADD/FFMA in this one-warp stream
```

Thus `FFMA 2E+1O` fits under the two-clock FP32 floor, whereas `FFMA 3E`
requires three clocks.  `.reuse` removes one physical RF request and removes
exactly the added clock.  FADD alone cannot reveal the two-read capacity
because both tested layouts remain hidden under the two-clock backend floor.

This agrees with Jia et al., *Dissecting the NVIDIA Volta GPU Architecture
via Microbenchmarking* (arXiv:1804.06826), which describes two 64-bit-wide
register banks and a conflict only when all three FFMA sources map to one
bank: <https://arxiv.org/pdf/1804.06826>.

The result should not be projected unchanged onto Hopper or Blackwell.
Same-subcore two-warp aggregate measurements on both H800 and H20, and the
one-clock-floor discriminator on GB202, expose only one independently
addressed full-warp operand per parity bank per clock.  Therefore the V100
result is a genuine generational difference, not evidence that the modern
measurements were merely suffering from an FFMA-latency artifact.

## Reproduction files

- `tests/asm_construct/probe_v100_rf_banks.py` — emits the controlled sm_70
  cubins.
- `tests/asm_construct/v100_cubin_runner.c` — CUDA Driver API timing runner
  for hosts without Python.
- `tests/asm_construct/v100_fixture.cu` — nvcc fixture used to recover and
  verify the sm_70 ELF ABI and parameter constant-bank offset.
