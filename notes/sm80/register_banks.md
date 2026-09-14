# Ampere register-bank read bandwidth (A100, 2026-09)

## Result

The A100 measurement is cycle-for-cycle identical to the V100 result in
`notes/sm70/register_banks.md`.  Ampere retains two parity-selected RF banks,
with each bank able to supply **two independently addressed 32-bit warp
operands per operand-collection clock**.  Three sources on one bank require
an additional clock.

This experiment establishes the externally visible read service rate.  It
does not measure or establish the RF write-port count.

## Experiment

Hardware: NVIDIA A100-SXM4-40GB, compute capability 8.0.  Cubins are assembled
from the native `sm_80_instructions.txt` database.  One 32-thread warp executes
512 straight-line independent-destination instructions with `stall=1,
yield=0`; `CS2R SR_CLOCKLO` brackets the region.  Results below are minima of
15 warm repetitions on one GPU.

| stream | source demand | cycles | cycles/instruction |
|---|---:|---:|---:|
| NOP | none | 520 | 1.016 |
| FADD | 2E | 1031 | 2.014 |
| FADD | 1E + 1O | 1031 | 2.014 |
| FADD | 2O | 1031 | 2.014 |
| FFMA | 3E | 1541 | **3.010** |
| FFMA | 3O | 1541 | **3.010** |
| FFMA | 2E + 1O, all operand orderings | 1031 | **2.014** |
| FFMA 3E + `.reuse` on A or B | effective 2E | 1031 | **2.014** |
| FFMA 3E + `.reuse` on A+B or A+B+C | at most 1E | 1031 | **2.014** |

The 128-instruction cross-check also exactly matches V100 within the timer
overhead: NOP 1.063, FADD/FFMA-2+1/reused-3E 2.055, and FFMA-3E 3.039
cycles/instruction.  Operand order does not matter, so this is parity-bank
pressure rather than a limitation attached to one FFMA source slot.

## Model and cross-generation comparison

For this one-warp FP32 stream:

```text
cycles/instruction = max(2, even-source-count, odd-source-count)
```

The leading `2` is the Ampere FP32 instruction floor exposed by this schedule.
Two same-bank reads fit below it; the third same-bank read raises the result to
three clocks.  Reuse removes a request before bank service.

The resulting generational picture is:

| architecture | directly exposed same-bank read service |
|---|---|
| Volta V100 | 2 distinct 32-bit warp operands/bank/clock |
| Ampere A100 | 2 distinct 32-bit warp operands/bank/clock |
| Hopper H800/H20 | 1 distinct full-warp operand/bank/clock |
| Blackwell GB202 | 1 distinct full-warp operand/bank/clock |

Thus the Volta paper's 64-bit-bank behavior survived into Ampere, then changed
at Hopper: the H800/H20 same-subcore aggregate discriminator and GB202's
one-clock-floor discriminator both expose one operand/bank/clock.

## Encoding and reproduction

The sm_80 nvcc fixture gives ELF flags `0x00500550`, OSABI `0x33`, ABI version
7, parameter base `c[0][0x160]`, and default global descriptor slot
`c[0][0x118]`.  Like Volta, composite constant-address fields encode a dword
index while assembly syntax uses byte offsets.

Run the common probe with:

```bash
python3 tools/parse_sm90.py --instructions sm_80_instructions.txt \
  --latencies '' -o sm80.json
python3 tests/asm_construct/probe_v100_rf_banks.py \
  --arch sm80 --count 512 --out /tmp/a100_rf
```
