# VIADD — Vector Integer Add

**Opcode mnemonic:** VIADD  |  **Pipe:** `fmalighter_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). A real sm_90 rerun is currently blocked because the accompanying test source
> uses sm_120 FORMAT shapes the sm_90 spec rejects at match time.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

## Semantics

Vector integer addition dispatched through the floating-point pipeline. Supports two formats:
- **32**: Single 32-bit add — `Rd = Ra + Rb` (or `Ra - Rb` with `[-]` on Rb)
- **16x2**: Dual 16-bit SIMD add — packed 2×16-bit addition in one instruction

The `[-]` modifier on Rb negates the second operand, effectively turning this into a subtract instruction.

## Why fmalighter_pipe?

Issued on the FP pipeline (not the integer pipe) for scheduling balance — allows parallel execution of integer ops alongside FXU-bound arithmetic, improving throughput in mixed integer+float code. This is a key Hopper (sm_90) optimization.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `viadd__RRR_RRR` | `0x236` | `VIADD Rd, Ra, [-]Rb` |
| `viadd__RIR` | `0x836` | `VIADD Rd, Ra, imm32` |
| `viadd__RCR` | `0xa36` | `VIADD Rd, Ra, [-]c[bank][offset]` |
| `viadd__RCxR` | `0x1a36` | `VIADD Rd, Ra, [-]c[URb][offset]` |
| `viadd__RUR` | `0x1c36` | `VIADD Rd, Ra, [-]URb` |

## Modifiers

| Modifier | Field | Bit | Values |
|----------|-------|-----|--------|
| fmt | sz | [73] | 0=32, 1=16x2 |
| Rb negate | Sb_invert | [63] | 1=`[-]` |

## Bit layout (RRR — opcode 0x236)

```
[73:73]              sz        <= fmt
[63:63]              Sb_invert <= Rb@negate
[39:32]              Rb        <= Rb
[31:24]              Ra        <= Ra
[23:16]              Rd        <= Rd
[91:91],[11:0]       opcode    <= 0b1000110110
```

## Cross-comparison

| Property | IADD3 | VIADD |
|----------|-------|-------|
| Pipe | `int_pipe` | `fmalighter_pipe` |
| Three inputs? | Yes (Ra+Rb+Rc) | No (Ra+Rb only) |
| Packed ops | No (single 32-bit) | Yes (16x2) |
| Negate | No | Yes (`[-]` on Rb) |
| Immediate | Via IADD32I | Yes (RIR variant) |

## Latency

`fmalighter_pipe`, `INST_TYPE_COUPLED_MATH`. Dispatched to the lighter FP pipeline for scheduling balance.

## SM120 verification (`tests/asm_construct/test_viadd.py`, RTX 5090)

sm_120 drops the const-bank variants (RCR/RCxR absent) and adds the `[-]Ra`
negate and `.ISAT` saturation:

| Variant | Opcode | Format |
|---------|--------|--------|
| `viadd__RRR_RRR` | `0x236` | `VIADD[.fmt][.ISAT] Rd, [-]Ra, [-]Rb` |
| `viadd__RuIR_RIR` | `0x836` | `VIADD[.fmt][.ISAT] Rd, [-]Ra, imm32` |
| `viadd__RUR_RUR` | `0x1c36` | `VIADD[.fmt][.ISAT] Rd, [-]Ra, URb` |

Field map: `fmt` → [75:73] (`FMT_viadd`: 0=U32, 1=U16x2, 2=S32, 3=S16x2,
4=U8x4, 5=S8x4), `Ra@negate` → [72], `Rb@negate` → [63], `isat` → [80].
Negating **both** operands is an illegal combination (CONDITIONS `nA-Rb` /
`Ra-nB` — assembler rejects it).

Silicon-verified semantics (14-case battery + byte checks, all pass):
- `Rd = Ra + Rb`; `[-]Rb` → `Ra - Rb`; `[-]Ra` → `-Ra + Rb` (one negate max).
- `.ISAT` saturates per-lane: S32 at ±2^31, U32 at 0xFFFFFFFF, S16x2 per
  half-word (e.g. `{0x7FFF,0x8000}+{1,1}` → `{0x7FFF,0x8001}`: hi lane
  saturates at +max, lo lane `0x8000+1` is not an overflow).
- Packed wraps without `.ISAT` (U16x2/S16x2/U8x4 lane-wise add).
- RIR immediate and RUR uniform-register forms verified on GPU.

Note: ptxas on sm_120 does **not** emit VIADD for plain integer adds (it uses
IADD3); VIADD is only a scheduling-balance op, exercised here directly.
