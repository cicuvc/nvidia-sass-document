# USGXT — Uniform Sign-Extend

**Opcode mnemonic:** USGXT  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Sign-extends a uniform-register value: `URd = sign_extend(URa, size_from_URb)`. The size to extend from is encoded in or derived from `URb`. The `cw` modifier selects clamp-to-word (C) or wrap (W) behavior.

**Silicon-verified on SM120 (`tests/asm_construct/test_usgxt.py`, RTX 5090):**
identical semantics to SGXT — `N = URb` (unmasked for clamp); `.U32`
zero-extends, default `.S32` sign-extends; N=0 → 0; clamp N≥32 → URa
unchanged; wrap N mod 32 (32→0, 33→1).  Verified 16 cases incl. the imm
form (opcodes 0x129a UUU / 0x189a imm; cw [75], fmt [73] — same bit
positions as SGXT).

## Variant overview

| Variant | Opcode | Format |
|---------|--------|--------|
| `usgxt__URURUR_UUU` | `0x129a` | `USGXT.C URd, URa, URb` |
| `usgxt__URuIUR_URIR` | `0x189a` | `USGXT.C URd, URa, imm32` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| cw | sz | [75] | 0=C (clamp), 1=W (wrap) |
| fmt | sz | [73] | S32=0 |

## Bit layout (noimm — opcode 0x129a)

```
[75:75]              sz    <= cw (CWMode)
[73:73]              sz    <= fmt (REDUX_SZ)
[37:32]              Ra_URb <= URb
[29:24]              Sa     <= URa
[21:16]              URd    <= URd
[91:91],[11:0]       opcode <= 0b1001010011010
```

Imm variant (0x189a) replaces URb with 32-bit immediate at [63:32].

## Latency

`UDP_subset` group: output 1–7 cycles, true-dependency 4–12 cycles.
