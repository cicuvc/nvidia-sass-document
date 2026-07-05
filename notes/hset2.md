# HSET2 / HSETP2 — Packed FP16x2 Compare and Set

**Opcode mnemonic:** `HSET2` / `HSETP2`
**Pipe:** `fp16_pipe` (= `FP16_OPS`)
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

Per-lane FP16 comparison of two packed halfword pairs with boolean reduction.

**HSET2** — writes a 32-bit register destination:
```
Rd.h0 = (Ra.h0 cmp Rc.h0) ? true_val : false_val
Rd.h1 = (Ra.h1 cmp Rc.h1) ? true_val : false_val
```
If `Bop = AND/OR/XOR`, the two per-lane bools are combined before storing.
`BVal` controls true/false representations:
- `BM` (=0, bool-mask): true = `0x00010001`, false = `0x00000000`
- `BF` (=1, bool-float): true = `0xFFFFFFFF`, false = `0x00000000`

**HSETP2** — writes two predicate registers (Pv, Pv+1) without a register destination:
```
Pv  = (Ra.h0 cmp Rc.h0)
Pv+1 = (Ra.h1 cmp Rc.h1)
```
If `H_AND`, the two per-lane bools are AND-reduced to Pv (Pv+1 unused).
`IDEST_SIZE = 0` — no register write, only predicate output.

Both instructions have a 3rd predicate output `Pp` for uniform-scale compare result.

## Variant overview — 10 each (5 base + 5 ALT "noBop")

| Variant | HSET2 opcode | HSETP2 opcode | C operand |
|---------|:-----------:|:------------:|-----------|
| `__RR` | 0x233 | 0x234 | Register |
| `__RI` | 0x433 | 0x434 | 2× F16Imm |
| `__RC` | 0x633 | 0x634 | Const bank |
| `__RCx` | 0x1633 | 0x1634 | Const bank + UR |
| `__RU` | 0x1e33 | 0x1e34 | UniformRegister |

"noBop" ALTERNATE CLASSes share the same opcodes but omit the `Bop` field
([70:69]) — the boolean reduction lane-combine is always AND.

## Modifiers (HSET2)

| Modifier | Field | Values |
|----------|-------|--------|
| **ofmt** | [65:64] | F16_V2(0), BF16_V2(2) |
| **cmp** (FCMP) | [79:76] | F(0), LT(1), EQ(2), LE(3), GT(4), NE(5), GE(6), NUM(7), NAN(8), LTU(9), EQU(10), LEU(11), GTU(12), NEU(13), GEU(14), T(15) |
| **bval** (BoolVal) | [71] | BM(0)=0x00010001 mask, BF(1)=0xFFFFFFFF float |
| **bop** (BoolOp) | [70:69] | AND(0), OR(1), XOR(2) |
| **ftz** | [80] | noftz(0), FTZ(1) |
| **iswzA** | [75:74] | H1_H0(0), H0_H0(2), H1_H1(3) |
| **iswzB** | [61:60] | H1_H0(0), H0_H0(2), H1_H1(3) |

### HSETP2 differences

- No `BVal` — predicate output instead of register
- `H_AND` at [71] (replaces `bval`): noh_and(0), H_AND(1)
- Dest predicates: `Pu` at [83:81] and `Pv`/`Pv+1` at [86:84]
- No `Rd` register field (gap at [23:16]); `IDEST_SIZE = 0`
- Output format is `Pu|Pv` (two predicates from per-lane compare)

Both `ofmt` and `cmp` are at the same bit positions. Both use `ofmt` at
[65:64] (different from HFMA2/HADD2 which use [85],[78]).

## Bit layout (HSET2 RR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 91],[11:0]            opcode       (13b)
[90]                    Pp.not       (1b)
[89:87]                 Pp           (3b: uniform result predicate)
[80]                    ftz          (1b: UPq_not)
[79:76]                 cmp          (4b: FCMP condition code)
[75:74]                 iswzA        (2b)
[73]                    Ra.absolute  (1b)
[72]                    Ra.negate    (1b)
[71]                    bval         (1b: 0=BM, 1=BF)
[70:69]                 bop          (2b: AND=0/OR=1/XOR=2)
[65:64]                 ofmt         (2b)
[63]                    Rc.negate    (1b)
[62]                    Rc.absolute  (1b)
[61:60]                 iswzB        (2b)
[39:32]                 Rc           (8b: Rb slot)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not       (1b)
[14:12]                 Pg           (3b, 7=PT)
```

### HSETP2 RR differences

- Bits [90:87], [86:84], [83:81]: triple-predicate encoding area
  - [90:90] Pp.not
  - [89:87] Pp (3b)
  - [86:84] Pv (3b: second per-lane pred, auto-increment to Pv+1)
  - [83:81] Pu (3b: first per-lane pred)
- [71]: `H_AND` instead of `bval`
- [23:16]: gap (no Rd)
- Rd register absent; dest is predicate-only

## Compiler behavior (ptxas, sm_90, CUDA 13.1)

| C++ intrinsic | PTX | SASS |
|---------------|-----|------|
| `__hlt2(a,b)` | `setp.lt.f16x2` | `HSET2.BF.LT.AND Rd, Ra, Rc, PT` |
| `__heq2(a,b)` | `setp.eq.f16x2` | `HSET2.BF.EQ.AND Rd, Ra, Rc, PT` |
| `__hle2(a,b)` | `setp.le.f16x2` | `HSET2.BF.LE.AND Rd, Ra, Rc, PT` |
| `__hgt2(a,b)` | `setp.gt.f16x2` | `HSET2.BF.GT.AND Rd, Ra, Rc, PT` |
| `__hne2(a,b)` | `setp.ne.f16x2` | `HSET2.BF.NE.AND Rd, Ra, Rc, PT` |
| `__hge2(a,b)` | `setp.ge.f16x2` | `HSET2.BF.GE.AND Rd, Ra, Rc, PT` |

All compiler-generated HSET2 uses:
- `Bop = AND` (both lanes must be true for the boolean result)
- `BVal = BF` (0xFFFFFFFF / 0x00000000 representation)
- `Pp = PT` (always-true — unconditional write of the per-lane comparison)

HSETP2 is used for `if (__hlt2(a,b).x)` pattern but lowered to the same
HSET2 + LOP3.SETP for extracting individual lane predicates.

## Latency (from sm_90_latencies.txt)

Same `FP16_OPS` latency class as all other fp16_pipe ops:

| Dependency | Pipe group × operand role | Cycles |
|-----------|--------------------------|:------:|
| TABLE_TRUE(GPR) | `FP16_OPS`{Rd} | 5–8 |
| TABLE_OUTPUT(GPR) | `FP16_OPS`{Rd} | 1–2 |
| TABLE_ANTI(GPR) | `FP16_OPS`{Ra,Rc} | 1–2 |

## Verified encodings (cuobjdump, sm_90)

7/7 HSET2 test vectors pass via `tools/decode_hset2.py`.

| Source | Lo64 / Hi64 | Disassembly |
|--------|------------|-------------|
| kernel | `0x0000000504057233` / `0x001fca0003801080` | HSET2.BF.LT.AND R5, R4, R5, PT |
| kernel | `0x0000000504057233` / `0x001fca0003802080` | HSET2.BF.EQ.AND R5, R4, R5, PT |
| kernel | `0x0000000504057233` / `0x001fca0003803080` | HSET2.BF.LE.AND R5, R4, R5, PT |
| kernel | `0x0000000504057233` / `0x001fca0003804080` | HSET2.BF.GT.AND R5, R4, R5, PT |
| kernel | `0x0000000504057233` / `0x001fca0003805080` | HSET2.BF.NE.AND R5, R4, R5, PT |
| kernel | `0x0000000504057233` / `0x001fca0003806080` | HSET2.BF.GE.AND R5, R4, R5, PT |

### PTX→SASS mapping

PTX `setp.{cmp}.f16x2` → `HSET2.BF.{CMP}.AND Rd, Ra, Rc, PT`.
HSETP2 not yet verified in generated code — compiler uses HSET2 + LOP3 for
predicate extraction.

## Open questions

- HSETP2 encodings not yet verified (compiler prefers HSET2 + LOP3 pattern)
- "noBop" ALT classes — when would Bop AND not be specified? (Maybe hand-coded
  SASS or future compiler optimization)
- `BM` (bool-mask with 0x00010001) vs `BF` (bool-float with 0xFFFFFFFF) —
  compiler always uses BF; when is BM used?
- Uniform register, const-bank, RCx, and immediate variants not yet verified
- FCMP values NUM(7), NAN(8), LTU(9), EQU(10), LEU(11), GTU(12), NEU(13),
  GEU(14), T(15), F(0) — unordered variants and identity comparisons not yet
  verified in generated code
