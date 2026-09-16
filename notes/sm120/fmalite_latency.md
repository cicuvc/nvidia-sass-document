# GB202 FMA-Lite pipeline latency

Silicon: RTX 5090 (GB202, sm_120), 2026-09-16.  Reproducer:
[`probe_fmalite_latency.py`](../../tests/asm_construct/probe_fmalite_latency.py).

```bash
python3 tests/asm_construct/probe_fmalite_latency.py --reps 3
python3 tests/asm_construct/probe_fmalite_latency.py --isolated \
    --gaps 1,2,3,4,5,6 --reps 3
```

## Scope

The dynamically measured FMA-Lite set is:

```text
FADD FADD32I FFMA FFMA32I FMUL FMUL32I FHADD FHFMA
```

Both `.F16` and `.BF16` modes of `FHADD/FHFMA` were tested.  Consumers select
four execution leaves:

| consumer | selected leaf | detector operation |
|---|---|---|
| `MOV` | ALU Lite | bit-preserving copy |
| `IADD3` | ALU Heavy | bit-preserving add-zero |
| `FADD` | FMA Lite | FP32 add-zero |
| `IMAD` | FMA Heavy | integer multiply-by-one |

Every producer writes `0x3f800000` as its architecturally completed result;
the settled poison is `0x40000000`.  Scalar `FHADD/FHFMA` read FP16/BF16
source halves but expand their scalar result to FP32, which makes the same
detector valid for all four consumers.

## FP32 FMA-Lite operations

`FADD`, `FADD32I`, `FFMA`, `FFMA32I`, `FMUL`, and `FMUL32I` have exactly the
same matrix:

| producer -> consumer leaf | fine | coarse | isolated result |
|---|---:|---:|---:|
| FMA Lite -> ALU Lite | 2 | 2 | **2** |
| FMA Lite -> ALU Heavy | 2 | 2 | **2** |
| FMA Lite -> FMA Lite | 2 | 2 | **2** |
| FMA Lite -> FMA Heavy | 2 | 2 | **2** |

Gap 1 sees the old destination; every gap from 2 onward sees the completed
FP32 value.  No distinction is visible between add, multiply, fused multiply-
add, and immediate forms at the result-ready boundary.

This is substantially earlier than the static `TABLE_TRUE(GPR)` values:
ordinary FMAI producers have table latency 5 to FXU consumers and 4 to FMAI
or IMAD consumers.  Those values remain conservative scheduling metadata, not
the silicon bypass point.

The isolated result also corrects the older combined-layout survey: both
`IADD3 -> FADD` and `FADD -> IADD3` reach the consumer at gap 2 when each gap
has a fixed instruction position.  The apparent combined-kernel gap 3 is an
issue-group/PC phase effect.

## Scalar FP16/BF16 result has two observable representations

`FHADD` and `FHFMA` behave differently only for the ALU-Heavy consumer:

| consumer leaf | permanent boundary | value at the intermediate gap |
|---|---:|---|
| ALU Lite | **2** | final FP32 |
| ALU Heavy | 3 fine / **4 coarse** | raw FP16/BF16 payload |
| FMA Lite | **2** | final FP32 |
| FMA Heavy | **2** | final FP32 |

The raw values are deterministic:

| mode | architectural result | `IADD3` observation at gap 2 |
|---|---:|---:|
| `.F16` | `0x3f800000` | `0x00003c00` |
| `.BF16` | `0x3f800000` | `0x00003f80` |

With fine fillers the ALU-Heavy consumer sees the final FP32 result from gap 3.
With one coarse filler it continues to see the raw 16-bit payload at gap 3 and
becomes final at gap 4.  This is stronger than a stale/fresh boundary: an
underscheduled consumer observes a real intermediate representation from the
format-conversion pipeline.

The surprising asymmetry is physical evidence about bypass selection.  ALU
Lite, FMA Lite, and FMA Heavy receive the formatted FP32 result at gap 2, while
the ALU-Heavy integer input can attach to an earlier narrow-result node.  FMA
Heavy does **not** share that early integer-input tap even though it resides in
the same Shared FMA Heavy macro as ALU Lite.

## Initial simulator model

```text
FP32 FMA-Lite operation
    `-- common scalar-result bypass ---------------- all four leaves ready t+2

scalar FHADD/FHFMA
    +-- raw FP16/BF16 result node ------------------ visible to ALU Heavy t+2
    +-- FP32 expansion / formatting
    |       +-- ALU Lite --------------------------- ready t+2
    |       +-- FMA Lite --------------------------- ready t+2
    |       +-- FMA Heavy -------------------------- ready t+2
    |       `-- ALU Heavy final value -------------- t+3 fine / t+4 coarse
    `-- final RF commit ---------------------------- not yet located
```

The simultaneous “formatted t+2” and “raw t+2” observations should be modeled
as consumer-selected bypass payloads, not as one globally changing result
register.  Correctly scheduled code uses the final-value ready time; malformed
SASS can expose the raw payload and is useful for pipeline validation.
