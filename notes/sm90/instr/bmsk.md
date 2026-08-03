# BMSK — Bitmask

**Opcode mnemonic:** BMSK  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Generates a bitmask from a position and width: `Rd = bitmask(Ra, Rb)`.
**`Ra` = start position, `Rb` = width** (silicon-confirmed: pos=4, w=3 → `0x70`).
`Rd = ((1 << width) - 1) << pos`, truncated to 32 bits. The `cw` modifier
selects clamp (C, default) or wrap (W) behavior when the range exceeds 32 bits:
- **C (clamp)** — operands used as-is; the "clamp" is the natural 32-bit
  truncation of the shifted mask, **not** width-clamping (`pos=2, w=32` →
  `0xFFFFFFFC`, not `0x3FFFFFFC`). `pos ≥ 32` → 0; `width ≥ 32` → all bits
  below the position (`pos=0, w=32` → `0xFFFFFFFF`).
- **W (wrap)** — `pos & 31` and `width & 31` before the same formula
  (`pos=33` → pos 1; `width=33` → width 1; `width=32` → 0). Bits shifted past
  bit 31 are dropped, not wrapped to the low end.

Equivalent to the PTX `bfi` (bit-field insert) pattern `(1 << width) - 1` shifted by position.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `bmsk__RRR_RRR` | `0x21b` | `BMSK.C Rd, Ra, Rb` |
| `bmsk__RIR` | `0x81b` | `BMSK.C Rd, Ra, imm32` |
| `bmsk__RCR` | `0xa1b` | `BMSK.C Rd, Ra, c[bank][offset]` |
| `bmsk__RCxR` | `0x1a1b` | `BMSK.C Rd, Ra, c[URb][offset]` |
| `bmsk__RUR` | `0x1c1b` | `BMSK.C Rd, Ra, URb` |

## Modifiers

| Modifier | Field | Bit | Values |
|----------|-------|-----|--------|
| cw | sz | [75] | 0=C (clamp), 1=W (wrap) |

## Bit layout (RRR — opcode 0x21b)

```
[75:75]              sz   <= cw (CWMode)
[39:32]              Rb   <= Rb (width/position)
[31:24]              Ra   <= Ra (start position)
[23:16]              Rd   <= Rd
[91:91],[11:0]       opcode <= 0b1000011011
```

## Cross-comparison

| Property | BMSK | UBMSK |
|----------|------|-------|
| Pipe | `int_pipe` | `udp_pipe` |
| Registers | Regular (Rd,Ra,Rb) | Uniform (URd,URa,URb) |
| Opcode | `0x21b` | `0x129b` |
| Same modifiers | CWMode (C/W) | CWMode (C/W) |

## Latency

`int_pipe`, `FXU_OPS` group. Standard integer-pipe latency (1 cycle output typical).

## SM120 verification (`tests/asm_construct/test_bmsk.py`, RTX 5090)

sm_120 keeps 3 variants (RRR `0x21b`, RIR `0x81b`, RUR `0x1c1b`; RCR/RCxR
dropped). Silicon-verified 14-case battery + RUR (3 concurrent blocks): the
formula above, C-vs-W divergence at `width ≥ 32` (C keeps all bits, W uses
`width & 31`) and `pos ≥ 32` (C → 0, W wraps to `pos & 31`). ptxas does not
emit BMSK from plain C on sm_120 (`(1u << n) - 1` lowers to SHF.L + LOP3);
the op is exercised directly via the assembler.
