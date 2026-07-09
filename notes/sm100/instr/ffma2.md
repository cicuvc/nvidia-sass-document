# FFMA2 / FADD2 / FMUL2 — packed FP32x2 FMA / Add / Mul  → PTX `fma.f32x2` / `add.f32x2` / `mul.f32x2`

**Opcode mnemonic:** `FFMA2` / `FADD2` / `FMUL2` — multiple opcodes per mnemonic
(RRR/RRU/RRI/RIR/RUR variant positions).
**Pipe:** `fmalighter_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

New on sm100 (Blackwell). The **packed FP32x2** instructions: each computes
`{hi,lo}` on a 64-bit register pair in one instruction. `FFMA2 Rd, Ra, Rb, Rc`
computes `Rd = (Ra·Rb + Rc)` treating the operands as packed pairs. `FADD2` and
`FMUL2` are the add-only and multiply-only variants. Each source operand
(Ra/Rb/Rc) carries an `ISWZA_fadd2` swizzle modifier specifying whether it is
a packed FP32x2, an FP32x2 half-swap, or a scalar F32. `IDEST_SIZE` is
conditionally 32+32=64 for packed operands, 32 otherwise.

The PF32x2 packed FMA instruction uses ISWZA_fadd2 per source, per-element
negate/abs, and a single rounding mode—everything gets packed into separate
bit fields rather than a single operation encoding. The source pair overloads
let the compiler choose between packed and scalar modes for each operand.

## Semantics
`FFMA2 Rd, Ra, Rb, Rc` computes `Rd = Ra * Rb + Rc` where each operand's
interpretation is governed by its ISWZA:
- **`F32x2` / `F32x2.HI_LO`** (= 0): packed pair in a 64-bit register — `{hi, lo}`.
- **`F32x2.LO_HI`** (= 1): packed pair with hi/lo swapped.
- **`F32`** (= 2): single 32-bit scalar (broadcast across both lanes).

For packed operands, each 32-bit lane independently has `[-]`/`[||]`
(negate/absolute) applied via the `NEGA` per-source modifier and the per-element
negate/abs bits `Ra@negate`[72] / `Ra@absolute`[73] (and similarly for Rb[62:63],
Rc[74:75]). The rounding mode is `rnd`[79:78] (`Round1`: RN=0, RP=1, RZ=2, RM=3);
flush-to-zero is `FTZ` for FADD2, `FMZ_hfma2` for FFMA2/FMUL2.

`FADD2 Rd, Ra, Rc` computes `Rd = Ra + Rc` (no Rb; same swizzle and per-element
control). `FMUL2 Rd, Ra, Rb` computes `Rd = Ra * Rb` (no Rc).

## Variant overview (example: FFMA2)
| Class | Opcode | Operand config | Distinguisher |
|-------|--------|---------------|---------------|
| `ffma2_rb_rc__RRR` | 0x249 | Rd, Ra, Rb, Rc | all register |
| `ffma2_rb_imm__RIR` | 0x849 | Rd, Ra, imm, Rc | immediate in A-slot (RIR) |
| `ffma2_rb_urc__RRU` | 0x1e49 | Rd, Ra, Rb, URc | uniform C |
| `ffma2_urb_rc__RUR` | 0x1c49 | Rd, URa, Rb, Rc | uniform B |
| `ffma2_rb_x__RRI` / etc. | 0x449 | Rd, Ra, Rb, imm | immediate in C-slot |

`FADD2` has 3 (RRR/RRU/RIR), `FMUL2` has 3 (RRR/RRU/RIR). All 11 variants share
`fmalighter_pipe` and `INST_TYPE_COUPLED_MATH` (paired instructions occupy two
issue slots).

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `rnd` | `Round1` | [79:78] | rounding mode: RN=0, RP=1, RZ=2, RM=3 |
| `fmz` / `ftz` | `FMZ_hfma2` / `FTZ` | [80]∥[76] | flush-to-zero |
| `iswzA/B/C` | `ISWZA_fadd2` | [82:81][88:87][85:84] | operand width/order: `F32x2`/`HI_LO`=0, `LO_HI`=1, `F32`=2 |
| `negA/C` | `NEGA` (PP=0, NP=1) | [83][86] | negate Ra / Rc |
| `Ra/Rb/Rc@negate` / `@absolute` | per-bit | [72]/[73], [63]/[62], [75]/[74] | per-element negate/abs |
| `reuse_src_a/b/c` | `REUSE` | opex packed | operand `.reuse` (Volta reuse model) |

## Encoding example (`ffma2_rb_rc__RRR`, opcode 0x249)
```
[91]∥[11:0]         opcode     = 0x249
[88:87]             iswzB      [86] negC  [85:84] iswzC  [83] negA  [82:81] iswzA
[80]∥[76]           fmz        [79:78] rnd
[75] negC_per_elem  [74] absC_per_elem  [73] absRa  [72] negRa
[71:64] Rc  [63] negRb  [62] absRb
[39:32] Rb  [31:24] Ra  [23:16] Rd
[15] Pg_not  [14:12] Pg
```

## Verified encoding (cuobjdump, `fma.rn.f32x2`, sm_100a)
```
FFMA2 R2, R2.F32, R2.F32, 1
  opcode=0x449 (RRI variant)  Rd=R2  Ra=R2(scalar F32)  Rb=0  Rc=R2(imm=1)
  iswzA=F32(2)  iswzB=F32(2)  iswzC=F32(2)
```

The operands printed as `R2.F32` (ISWZA=2, single scalar broadcast) — the
constant `1.0f` is loaded by the preceding `HFMA2` (which initialised the
register pair and got constant-folded), then `FFMA2 R2, R2.F32, R2.F32, 1`
computes the fma as a packed pair.

## Cross-references
- `notes/sm100/arch/control_codes.md` — control codes (opex, reuse, pm_pred) are
  the standard sm_90 layout unchanged.
- `notes/sm90/instr/*` — the f32/x32 scalar predecessors; FFMA2 is the packed
  sm100 successor.
- `notes/sm100/instr/utchmma.md` — unrelated but shares the `INST_TYPE_COUPLED_MATH`
  type (FFMA2 is the lighter fmalighter_pipe counterpart to the MMA's coupled
  math dispatch).

## Open questions
- `ISWZA_fadd2` F32x2=0 / F32x2.HI_LO=0 both map to 0 — how does the disassembler
  choose between the two display strings? (Likely assembler-only aliases, both
  encode the same packed pair.)
- Per-element negate/abs on each 32-bit lane — confirmed via spec bits [72:75],
  but not yet tested with a kernel that forces a per-lane negate on a packed
  source.
- The exact microarch benefit of FP32x2 on `fmalighter_pipe`: each 64-bit FMA
  occupies two coupled issue slots, suggesting the pipe's FMA unit is 32-bit wide
  but can pair two FFMA2s as one coupled dispatch.
