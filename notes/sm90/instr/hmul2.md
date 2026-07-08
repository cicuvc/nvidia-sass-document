# HMUL2 — Packed FP16x2 Multiply

**Opcode mnemonic:** `HMUL2`
**Pipe:** `fp16_pipe` (= `FP16_OPS`)
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd = Ra * Rb` — per-lane FP16 multiply on two packed halfword pairs. Two source
operands with independent ISWZA lane swizzles and sign control (negate/absolute).
No accumulator operand (`ISRC_C_SIZE = 0`).

## Variant overview — 5 encoding variants

| Variant | Opcode (13b) | Hex | B operand |
|---------|:-----------:|:---:|-----------|
| `hmul2__RR` | `0b1000110010` | 0x232 | Register |
| `hmul2__RI` | `0b100000110010` | 0x832 | 2× F16Imm |
| `hmul2__RC` | `0b101000110010` | 0xa32 | Const bank |
| `hmul2__RCx` | `0b1101000110010` | 0x1a32 | Const bank + UR |
| `hmul2__RU` | `0b1110000110010` | 0x1c32 | UniformRegister |

No MMA variant, no RELU variant. Clean 2-source multiply; unlike HADD2 and HFMA2
the compiler emits the non-MMA instruction directly (no lowering-through-FMA).

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **ofmt** (output format) | [85],[78] | F16_V2(0), INVALID1, BF16_V2(2), INVALID3 |
| **fmz** (flush mode) | [80],[76] | nofmz_hfma2(0), FMZ(1), FTZ(2) |
| **sat** (saturation) | [77] | nosat(0), SAT(1) |
| **iswzA** (on Ra) | [75:74] | H1_H0(0), H0_H0(2), H1_H1(3) |
| **iswzB** (on Rb) | [61:60] | H1_H0(0), H0_H0(2), H1_H1(3) |
| **Ra absolute** | [73] | off(0), \|Ra\|(1) |
| **Ra negate** | [72] | off(0), -Ra(1) |
| **Rb absolute** | [62] | off(0), \|Rb\|(1) |
| **Rb negate** | [63] | off(0), -Rb(1) |

Both operands use `ISWZA` (2-bit), not `ISWZB`. No `F32` or `H0_NH1` swizzle
modes — only the standard halfword broadcast controls.

BF16_V2 output format disallows `.FMZ`, `.FTZ`, and `.SAT` (enforced by CONDITIONS).

## Bit layout (hmul2__RR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b)  TABLES_opex_5(batch_t,usched_info,reuse_src_a,reuse_src_b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 91],[11:0]            opcode       (13b)
[85],[78]               ofmt         (2b)
[80],[76]               fmz          (2b)
[77]                    sat          (1b: ntz)
[75:74]                 iswzA        (2b: bop)
[73]                    Ra.absolute  (1b: sz)
[72]                    Ra.negate    (1b: e)
[63]                    Rb.negate    (1b: Sb_invert)
[62]                    Rb.absolute  (1b: Sc_absolute)
[61:60]                 iswzB        (2b: hsel, ISWZA on Rb)
[39:32]                 Rb           (8b)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not       (1b)
[14:12]                 Pg           (3b, 7=PT)
```

### vs HFMA2 RRR — field position comparison

HMUL2 is a stripped-down HFMA2 with only 2 operands. All that was removed:
- Rc register at [71:64] → gap
- iswzC at [82:81] → gap
- OR (Rc@negate) at [84] → gap
- clear (Rc@absolute) at [83] → gap
- sat field reduced from 2-bit ([79],[77]) to 1-bit ([77])

Ra, Rb, and Rd positions are identical to HFMA2. The ISWZB on HFMA2's Rb
(3-bit at [86],[61:60]) is replaced by a simple 2-bit ISWZA at [61:60].
This makes the two-operand encoding a clean subset of the three-operand
HFMA2 layout.

## Compiler behavior (ptxas, sm_90, CUDA 13.1)

**HMUL2 IS emitted by ptxas** for standalone FP16 multiplies:

| PTX | SASS |
|-----|------|
| `mul.f16x2 d, a, b` | `HMUL2 Rd, Ra, Rb` |
| `a * b` (`__half2`) | `HMUL2 Rd, Ra, Rb` |

This is a key difference from HADD2: `add.f16x2` gets lowered to
`HFMA2.MMA ..., 1, 1, ...`, but `mul.f16x2` stays as `HMUL2`.

The compiler emits ISWZA swizzles directly: `.H0_H0` and `.H1_H1` suffixes
appear in cublas-disassembled code for lane-broadcast operations.

## Latency (from sm_90_latencies.txt)

Same as HADD2/HFMA2 in `FP16_OPS`:

| Dependency | Pipe group × operand role | Cycles |
|-----------|--------------------------|:------:|
| TABLE_TRUE(GPR) | `FP16_OPS`{Rd} | 5–8 |
| TABLE_OUTPUT(GPR) | `FP16_OPS`{Rd} | 1–2 |
| TABLE_ANTI(GPR) | `FP16_OPS`{Ra,Rc} | 1–2 |

## Verified encodings (cuobjdump, sm_90)

6/6 test vectors pass via `tools/decode_hmul2.py`.

| Source | Lo64 / Hi64 | Disassembly |
|--------|------------|-------------|
| cublas | `0x2000000704047232` / `0x004fc80000000800` | HMUL2 R4, R4.H0_H0, R7.H0_H0 |
| cublas | `0x200000090e097232` / `0x004fc80000000800` | HMUL2 R9, R14.H0_H0, R9.H0_H0 |
| cublas | `0x2000000a050a7232` / `0x004fc80000000800` | HMUL2 R10, R5.H0_H0, R10.H0_H0 |
| cublas | `0x2000000805008232` / `0x000fe40000000800` | @!P0 HMUL2 R0, R5.H0_H0, R8.H0_H0 |
| cublas | `0x2000001211008232` / `0x000fe20000000800` | @!P0 HMUL2 R0, R17.H0_H0, R18.H0_H0 |
| cublas | `0x2000001407008232` / `0x000fe20000000800` | @!P0 HMUL2 R0, R7.H0_H0, R20.H0_H0 |

### PTX→SASS mapping

PTX `mul.f16x2 d, a, b` → `HMUL2 Rd, Ra, Rb` (not lowered to HFMA2.MMA).

## Open questions

- RI (immediate), RC (const bank), RCx (extended const), and RU (uniform reg)
  variants not yet verified
- No MMA variant exists — why does the compiler choose HFMA2.MMA for add but
  HMUL2 for multiply? (Likely because add-as-FMA uses Rc as accumulator
  whereas standalone multiply has no natural FMA form)
