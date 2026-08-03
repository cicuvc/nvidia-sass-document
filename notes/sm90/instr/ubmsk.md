# UBMSK — Uniform Bitmask

**Opcode mnemonic:** UBMSK  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Creates a bitmask from position and size: `URd = ((1 << width) - 1) << pos`,
truncated to 32 bits. **`URa` = position, `URb` = width** (silicon-confirmed,
same as BMSK). The CWMode modifier selects clamp (C, default) or wrap (W)
behavior for overflow:
- **C** — operands as-is; the "clamp" is the natural 32-bit truncation
  (`pos=2, w=32` → `0xFFFFFFFC`, not a width-clamped `0x3FFFFFFC`).
- **W** — `pos & 31` and `width & 31` before the same formula.

Silicon-verified on SM120 (`tests/asm_construct/test_ubmsk.py`, RTX 5090):
17/17 cases — RIR (12) and RUR (5) forms, C and W, boundary positions/widths.
Uses the uniform-datapath recipe from `ubrev.md` (dummy first udp read, UMOV
settling before the GPR consumer, fresh module per launch).

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `ubmsk__URURUR_URUR` | `0x129b` | `UBMSK.C URd, URa, URb` |
| `ubmsk__URuIUR_URI` | `0x189b` | `UBMSK.C URd, URa, imm32` |

## Modifiers

| Modifier | Field | Bit | Values |
|----------|-------|-----|--------|
| cw | sz | [75] | 0=C(clamp), 1=W(wrap) |

## Bit layout (noimm — opcode 0x129b)

```
[75:75]         sz        <= cw
[37:32]         Ra_URb    <= URb
[29:24]         Sa        <= URa
[21:16]         URd       <= URd
[91:91],[11:0]  opcode    <= 0b1001010011011
```

## Latency

`UDP_subset` group: output 1–7 cycles, true-dependency 4–12 cycles.
