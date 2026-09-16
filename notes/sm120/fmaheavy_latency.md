# GB202 FMA-Heavy pipeline latency

Silicon: RTX 5090 (GB202, sm_120), 2026-09-16.  Reproducers:
[`probe_fmaheavy_latency.py`](../../tests/asm_construct/probe_fmaheavy_latency.py)
and
[`probe_fmaheavy_wide_latency.py`](../../tests/asm_construct/probe_fmaheavy_wide_latency.py).

```bash
python3 tests/asm_construct/probe_fmaheavy_latency.py --isolated \
    --gaps 1,2,3,4,5,6 --reps 3
python3 tests/asm_construct/probe_fmaheavy_wide_latency.py --reps 3
```

The first probe covers the 32-bit-result operations dynamically assigned to
the FMA-Heavy leaf:

```text
FSWZADD IDP.2A IDP.4A IMAD.LO IMUL IMUL32I.LO
```

The second separates low and high outputs of `IMAD.WIDE` and
`IMUL32I.WIDE`, the result of `IMAD.HI`, and their `Pu` predicate.  All gaps
below are nominal producer-to-consumer issue distances.  Fine fillers are
stall-1 NOPs; coarse fillers put the same delay into fewer instructions.

## Ordinary 32-bit result

| consumer leaf | `FSWZADD` | `IDP/IMAD/IMUL/IMUL32I` final value |
|---|---:|---:|
| ALU Lite (`MOV`) | **2** | **2** |
| ALU Heavy (`IADD3`) | **2** | 3 fine / **4 coarse** |
| FMA Lite (`FADD`) | **2** | **2** |
| FMA Heavy (`IMAD`) | **2** | **2** |

The delayed ALU-Heavy path exposes a deterministic non-architectural payload
at gap 2.  Inputs were deliberately selected so that `Ra`, the multiply/dot
result, addend, and final result were all distinguishable:

| producer | `Ra` | arithmetic intermediate | final | ALU-Heavy observation at gap 2 |
|---|---:|---:|---:|---:|
| `IDP.4A` | `0x01010101` | dot = 4 | `0x3f800000` | **`0x01010101`** |
| `IDP.2A` | `0x00010001` | dot = 2 | `0x3f800000` | **`0x00010001`** |
| `IMAD` | 2 | product = 6 | `0x3f800000` | **2** |
| `IMUL` | 2 | final product | `0x3f800000` | **2** |
| `IMUL32I` | `0x1fc00000` | final product | `0x3f800000` | **`0x1fc00000`** |

Thus this is an **early `Ra` payload**, not a multiplier/dot-product
intermediate.  It must not be modeled as a globally changing destination
register: the other three consumer leaves see the final result at the same
gap where ALU Heavy sees `Ra`.  The observation instead identifies a
consumer-selected input/bypass node inside the physical Shared-FMA-Heavy
macro.  `FSWZADD` does not expose that node.

## HI/WIDE GPR outputs

| output | ALU Lite | ALU Heavy | FMA Lite | FMA Heavy |
|---|---:|---:|---:|---:|
| `IMAD.WIDE` low 32 | **1** | final at **2**; `Ra` at 1 | **1** | **1** |
| `IMUL32I.WIDE` low 32 | **1** | final at **2**; `Ra` at 1 | **1** | **1** |
| `IMAD.WIDE` high 32 | **2** | 3 fine / **4 coarse** | **2** | **2** |
| `IMUL32I.WIDE` high 32 | **2** | 3 fine / **4 coarse** | **2** | **2** |
| `IMAD.HI` result | **2** | 3 fine / **4 coarse**; `Ra` at 2 | **2** | **2** |

The WIDE low-half t+1 result was repeated with independent launches and two
different operations.  It is earlier than the ordinary LO result.  The
architectural low product/add is therefore formed on an early path even
though a WIDE instruction occupies the FMA-Heavy execution service longer
than LO.  Result readiness and initiation interval are separate parameters.

The ALU-Heavy anomalous observations again equal `Ra` exactly.  For the WIDE
high half, ALU Heavy remains stale until the final high value arrives; it does
not receive the low result as an intermediate.

## `Pu` predicate output

`IMAD.WIDE`, `IMAD.HI`, and `IMUL32I.WIDE` give the same predicate matrix:

| consumer | fine boundary | safe coarse boundary |
|---|---:|---:|
| ALU-Lite selector (`SEL`) | 3 | **4** |
| ALU-Heavy predicate read (`P2R`) | 3 | **4** |
| effective instruction guard | 7 | **12** |
| CBU branch | 7 | **12** |

The probes initialize `P0` to the inverse of the long-gap architectural value,
so the boundary is observed even for operations whose tested carry output is
false.  Unlike ordinary ALU-Heavy arithmetic predicate producers, which can
loop into `P2R` at t+2, the multiply-wide `Pu` becomes readable only at the
same 3/4 boundary as the selector path.  Effective predication and CBU
distribution retain the common much later 7/12 behavior.

## Initial simulator model

```text
FMA-Heavy issue / operand collection
        |
        +-- early Ra/input node
        |       `-- ALU-Heavy malformed-schedule tap
        |
        +-- low-product/add formation
        |       `-- WIDE low -> Lite/FMA consumers -------- t+1
        |
        +-- ordinary/final result formation
        |       +-- LO -> all normal consumers ------------ t+2
        |       +-- HI/WIDE-high -> Lite/FMA consumers ---- t+2
        |       `-- final -> ALU Heavy -------------------- t+3 fine / t+4 safe
        |
        +-- WIDE/HI Pu -> selector/P2R -------------------- t+3 fine / t+4 safe
        `-- effective predicate / CBU distribution -------- t+7 fine / t+12 safe
```

For valid code generation, use the final-value boundaries, and use the coarse
number where a scheduling guarantee must be independent of instruction
packing/issue phase.  Keep the already measured FMA-Heavy service rate
(approximately one LO per two clocks and one HI/WIDE per four clocks) separate
from these RAW bypass times.
