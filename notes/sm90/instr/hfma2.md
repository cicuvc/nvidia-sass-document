# HFMA2 / HFMA2.MMA — Packed FP16x2 Fused Multiply-Add

**Opcode mnemonic:** `HFMA2` / `HFMA2.MMA`
**Pipe:** `fp16_pipe` (= `FP16_OPS`) / `fma64lite_pipe` (= `HFMA2MMA_OP`)
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd = Ra * Rb + Rc` — per-lane FP16 fused multiply-add on two packed halfword
pairs. Three source operands (Ra multiplicand, Rb multiplier, Rc accumulator),
each with independent ISWZA/ISWZB lane swizzles and sign control (negate/absolute).

**HFMA2.MMA variant:** Identical computational semantics but runs on `fma64lite_pipe`
and strips the ISWZ lane swizzles. Uses `OFMT_F16_V2_BF16_V2` (F16_V2/BF16_V2 only)
and `FMZ_hfma2` (no `OOB` value). No `.F32` output format unlike HADD2.
Compiler universally emits HFMA2.MMA for all `fma.f16x2` and `add.f16x2` PTX
operations on sm_90.

**RELU variant:** Same opcodes, but `satrelu = RELU (2)` and adds a 4th predicate
operand (`@Pp`) controlling per-lane ReLU activation. The ReLU is applied to the
result of the FMA: `Rd = relu(Ra * Rb + Rc)`.

## Variant overview

9 base opcodes × 2 (regular + relu) = 18 HFMA2 + 18 HFMA2.MMA = 36 total variants.

| Variant | Opcode (13b) | B operand | C operand |
|---------|:-----------:|-----------|-----------|
| `__RRR` | 0x231 / 0x235 | Register | Register |
| `__RRI` | 0x431 / 0x435 | 2× F16Imm | Register |
| `__RIR` | 0x831 / 0x835 | Register | 2× F16Imm |
| `__RRC` | 0x631 / 0x635 | Register | Const bank |
| `__RCxR` | 0x1631 / 0x1635 | Const bank | Register |
| `__RCR` | 0xa31 / 0xa35 | Const bank | Register |
| `__RRCx` | 0x1a31 / 0x1a35 | Register | Const bank + UR |
| `__RRU` | 0x1e31 / 0x1e35 | Register | UniformRegister |
| `__RUR` | 0x1c31 / 0x1c35 | UniformRegister | Register |

Opcodes listed as `non-MMA / MMA`.

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **ofmt** (output format) | [85],[78] | F16_V2(0), F32(1/=INVALID), E8M7_V2/BF16_V2(2), E6M9_V2(3) |
| **fmz** (flush mode zero) | [80],[76] | nofmz(0), FMZ(1), FTZ(2), OOB(3) |
| **satrelu** | [79],[77] | nosat(0), SAT(1), RELU(2) |
| **iswzA** (on Ra) | [75:74] | H1_H0(0), H0_H0(2), H1_H1(3) |
| **iswzB** (on Rb) | [86],[61:60] | H1_H0(0), F32(1), H0_H0(2), H1_H1(3), H0_NH1(4) |
| **iswzC** (on Rc) | [82:81] | H1_H0(0), H0_H0(2), H1_H1(3) |

MMA variant: OFMT limited to F16_V2(0)/BF16_V2(2), FMZ limited to nofmz(0)/FMZ(1)/FTZ(2),
no ISWZ fields. The `fmz` field for MMA uses `FMZ_hfma2` enum (no `OOB`).

Conditions enforce: BF16_V2/E8M7_V2/E6M9_V2 disallow FMZ/FTZ/SAT; ISWZA cannot
be INVALID1; ISWZB cannot be INVALID5/6/7; `.F32` output format is always illegal
on HFMA2 (unlike HADD2 which supports `.F32` widening).

## Bit layout (HFMA2 RRR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 91],[11:0]            opcode       (13b)
[86],[61:60]            iswzB        (3b)
[85],[78]               ofmt         (2b)
[84]                    Rc@negate    (1b: OR)
[83]                    Rc@absolute  (1b: clear)
[82:81]                 iswzC        (2b)
[80],[76]               fmz          (2b)
[79],[77]               satrelu      (2b)
[75:74]                 iswzA        (2b: bop)
[73]                    Ra@absolute  (1b: sz)
[72]                    Ra@negate    (1b: e)
[71:64]                 Rc           (8b)
[63]                    Rb@negate    (1b: Sb_invert)
[62]                    Rb@absolute  (1b: Sc_absolute)
[39:32]                 Rb           (8b)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not       (1b)
[14:12]                 Pg           (3b, 7=PT)
```

### HFMA2.MMA RRR differences

No ISWZ fields at [86],[61:60], [82:81], [75:74]. Bits [86:78] are arranged
differently (iswzB gap filled, iswzA slot unused). Key fields same positions:
Ra [31:24], Rb [39:32], Rc [71:64], Rd [23:16], negate/abs bits same.

### RRI (register × 2 imm): Rb at [71:64], Sc imm at [63:48], Sb imm at [47:32], no register at [39:32].
### RIR (2 imm × register): Ra at [31:24], Sc/Sb imm at [63:48]/[47:32], Rc at [71:64].
### RB negate/abs: `OR` [84]/`clear` [83] are `Rb@negate`/`Rb@absolute` in RRI;
   `Rc@negate`/`Rc@absolute` in RRR and RIR.

## HADD2→HFMA2.MMA lowering

Compiler (ptxas, sm_90, CUDA 13.1) always lowers `add.f16x2` → `HFMA2.MMA`:

| PTX | SASS |
|-----|------|
| `add.f16x2 d, a, b` | `HFMA2.MMA Rd, Ra, 1, 1, Rc` |
| `fma.f16x2 d, a, b, c` | `HFMA2.MMA Rd, Ra, Rb, Rc` |
| `a + b` (`__half2`) | `HFMA2.MMA Rd, Ra, 1, 1, Rc` |
| `a - b` | `HFMA2.MMA Rd, Ra, 1, 1, -Rc` |
| `a * b + c` | `HFMA2.MMA Rd, Ra, Rb, Rc` |

The `1, 1` immediates (FP16 0x3C00) are identity multipliers. Negation on Ra/Rc
is achieved via hardware negate bits; negation on Rb would require negative
immediates. ISWZ lane swizzles are not used by the compiler — it selects lanes
via shuffle/permute instructions instead.

The `.MMA` suffix selects the `fma64lite_pipe` scheduling — the hardware can
co-issue MMA loads and MMA math for tensor-core-adjacent throughput.

## Latency (from sm_90_latencies.txt)

HFMA2: `FP16_OPS` group, same latency class as HADD2/HSET2/HMUL2.
HFMA2.MMA: `HFMA2MMA_OP` group (= `fma64lite_pipe`).

| Dependency | Pipe group × operand role | HFMA2 | HFMA2.MMA |
|-----------|--------------------------|:-----:|:---------:|
| TABLE_TRUE(GPR) | `*`{Rd} | 5–8 | 10–11 |
| TABLE_OUTPUT(GPR) | `*`{Rd} | 1–2 | 3 |
| TABLE_ANTI(GPR) | `*`{Ra,Rc} | 1–2 | 1–2 |

Note that HFMA2.MMA has significantly higher true dependency latency (10–11
cycles) than regular HFMA2 (5–8 cycles). The compiler's choice of MMA for
addition is an instruction-issue throughput trade-off, not a latency win.

## Verified encodings (cuobjdump, sm_90)

16/16 test vectors pass via `tools/decode_hfma2.py`.

| Source | Lo64 / Hi64 | Disassembly |
|--------|------------|-------------|
| cublas | `0x00000000ff207435` / `0x000fe200000001ff` | HFMA2.MMA R32, -RZ, RZ, 0, 0 |
| kernel | `0x3c003c0004057835` / `0x001fce0000000005` | HFMA2.MMA R5, R4, 1, 1, R5 |
| kernel | `0x3c003c0004057835` / `0x001fce0000002005` | HFMA2.MMA.SAT R5, R4, 1, 1, R5 |
| kernel | `0x3c003c0004057835` / `0x001fce0000010005` | HFMA2.MMA.FTZ R5, R4, 1, 1, R5 |
| kernel | `0x3c003c0004057835` / `0x001fce0000012005` | HFMA2.MMA.FTZ.SAT R5, R4, 1, 1, R5 |
| kernel | `0x3c003c0004057835` / `0x001fce0000000105` | HFMA2.MMA R5, -R4, 1, 1, R5 |
| kernel | `0x3c003c0004057835` / `0x001fce0000100005` | HFMA2.MMA R5, R4, 1, 1, -R5 |
| kernel | `0x3c003c0004057835` / `0x001fce0000100105` | HFMA2.MMA R5, -R4, 1, 1, -R5 |

### PTX→SASS mapping

PTX `fma.f16x2` → `HFMA2.MMA` (not non-MMA HFMA2).
PTX `add.f16x2` → `HFMA2.MMA Rd, Ra, 1, 1, Rc` (via compiler lowering).

## Open questions

- Non-MMA HFMA2 (with ISWZ lane swizzles) encodings not yet verified — compiler
  never emits them for sm_90
- ISWZB.F32 and H0_NH1 modes: defined in enum but rejected by CONDITIONS for
  both HFMA2 and HFMA2.MMA. Where are these used? (Likely on other FP16 ops
  like HMMA or future extensions)
- RELU variant (`satrelu=2`): encoding format has an extra predicate `Pp` for
  per-lane RELU activation. Not yet seen in generated code
- E8M7_V2/E6M9_V2 output formats: enum-defined but not verified in generated SASS
- Const-bank (`RC`, `RCR`, `RCxR`, `RRCx`) and uniform (`RRU`, `RUR`) variants
  not yet verified
