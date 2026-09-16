# GB202 packed-FP16 / coupled-FMA latency

Silicon: RTX 5090 (GB202, sm_120), 2026-09-16.  Reproducer:
[`probe_fp16_latency.py`](../../tests/asm_construct/probe_fp16_latency.py).

```bash
python3 tests/asm_construct/probe_fp16_latency.py --reps 3
python3 tests/asm_construct/probe_fp16_latency.py \
    --producer HADD2 --producer HFMA2 --producer HMUL2_32I \
    --producer HFMA2_32I --producer HADD2.F32 \
    --consumer aluheavy --isolated --gaps 1,2,3,4 --reps 2
```

Ordinary packed operations occupy FMA Heavy and FMA Lite together.  The
measured set is `HADD2`, `HMUL2`, `HFMA2`, their `_32I` forms, and
`HFMA2.MMA`.  `HADD2.F32` is also included because it selects FMA Heavy alone.

## Ordinary register forms

`HADD2`, `HMUL2`, `HFMA2`, and `HFMA2.MMA` have one uniform matrix:

| consumer leaf | final packed result ready |
|---|---:|
| ALU Lite | **2** |
| ALU Heavy | **2** |
| FMA Lite | **2** |
| FMA Heavy | **2** |

Gap 1 sees the settled old destination; gap 2 and every later gap see the
architectural packed result.  Coupled occupancy of both FMA leaves therefore
does not imply two serial result stages.  The result is broadcast to all four
tested scalar consumer leaves at t+2.

`HADD2_32I` also follows this uniform t+2 matrix.  Two immediate multiply
forms have an extra malformed-schedule observation only on ALU Heavy:

| producer | ALU Lite/FMA Lite/FMA Heavy | ALU Heavy |
|---|---:|---:|
| `HMUL2_32I` | **2** | final 3 fine / **4 coarse** |
| `HFMA2_32I` | **2** | final 3 fine / **4 coarse** |

At gap 2 the ALU-Heavy consumer reads `Ra` exactly (`0x3f803c00` in the
probe), not an arithmetic intermediate.  This is the same early-input node
seen for `IMAD/IMUL/IDP`, but it is operand-form-sensitive: the ordinary
register packed forms and immediate `HADD2_32I` do not expose it.

## Widening `HADD2.F32`

`HADD2.F32` selects only FMA Heavy dynamically and produces a scalar FP32
result.  Its matrix is:

| consumer leaf | boundary |
|---|---:|
| ALU Lite | **2** |
| ALU Heavy | 3 fine / **4 coarse** |
| FMA Lite | **2** |
| FMA Heavy | **2** |

Unlike the `_32I` cases, the ALU-Heavy destination remains stale at gap 2;
there is no exposed narrow payload or `Ra` value.  This is a delayed crossing,
not an intermediate-representation event.

## Simulator rule

Use t+2 for ordinary coupled packed-FP results to every leaf.  Add a
producer-form tag for `HMUL2_32I/HFMA2_32I` and a mode tag for `HADD2.F32`:
their final ALU-Heavy input is safe at t+4 under arbitrary packing.  The
coupled execution initiation interval (approximately one instruction per two
clocks) remains independent of this RAW bypass latency.
