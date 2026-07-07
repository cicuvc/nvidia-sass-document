# UFLO — Uniform Find Leading One

**Opcode mnemonic:** UFLO  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Finds the position of the leading one (or zero, via `[~]` inversion) in a uniform register: `URd = find_leading_one(URb)`. Result is the 0-based bit position (0–31 for 32-bit). The `sh` modifier optionally shifts the result.

No empirical examples found in libcublas or ptxas output on sm_90, CUDA 13.1.

## Variant overview

| Variant | Opcode | Format |
|---------|--------|--------|
| `uflo__URURUR_URURUR` | `0x12bd` | `UFLO URd, UPu, [~]URb` |
| `uflo__URuIUR_URuIR` | `0x18bd` | `UFLO URd, UPu, imm32` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| fmt | sz | [73] | S32=0 |
| sh | sh | [74] | 0=nosh, 1=SH |
| invert | Sb_invert | [63] | 0=normal, 1=`[~]` (find leading zero) |

## Bit layout (noimm — opcode 0x12bd)

```
[83:81]              Pu     <= UPu
[74:74]              sh     <= sh
[73:73]              sz     <= fmt (REDUX_SZ)
[63:63]              Sb_invert <= URb@invert
[37:32]              Ra_URb <= URb
[21:16]              URd    <= URd
[91:91],[11:0]       opcode <= 0b1001010111101
```

Imm variant (0x18bd) replaces URb with 32-bit immediate at [63:32].

## Latency

`UDP_subset` group: output 1–7 cycles, true-dependency 4–12 cycles.

## Open questions

- `UPu` is always UPT in the FORMAT — what is its semantic role? Overflow flag? Result-zero flag?
- Does `UFLO` with `[~]` invert before counting (count leading zeros = CLZ)?
- The `SH` modifier: what shift is applied? Position-based shift?
