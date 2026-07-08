# HSETP2 — Packed FP16x2 Compare-Set-Predicate

**Opcode mnemonic:** `HSETP2` | **Pipe:** `fp16_pipe` (= `FP16_OPS`) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

Per-lane FP16 comparison of two packed halfword pairs with predicate output. Writes two predicate registers `Pv, Pv+1` without a register destination.

## Semantics
```
Pv  = (Ra.h0 cmp Rc.h0)
Pv+1 = (Ra.h1 cmp Rc.h1)
```
If `H_AND`, the two per-lane bools are AND-reduced to Pv (Pv+1 unused). `IDEST_SIZE = 0` — no register write, only predicate output. A 3rd predicate output `Pp` provides uniform-scale compare result.

## Variant overview — 10 (5 base + 5 ALT "noBop")
| Variant | Opcode | C operand |
|---------|:------:|-----------|
| `__RR` | 0x234 | Register |
| `__RI` | 0x434 | 2× F16Imm |
| `__RC` | 0x634 | Const bank |
| `__RCx` | 0x1634 | Const bank + UR |
| `__RU` | 0x1e34 | UniformRegister |

"noBop" ALTERNATE CLASSes share the same opcodes but omit the `Bop` field — the boolean reduction lane-combine is always AND.

## Modifiers (HSETP2 vs HSET2 differences)
| Modifier | Field | Values |
|----------|-------|--------|
| **ofmt** | [65:64] | F16_V2(0), BF16_V2(2) |
| **cmp** (FCMP) | [79:76] | F(0), LT(1), EQ(2), LE(3), GT(4), NE(5), GE(6), NUM(7), NAN(8), LTU(9), EQU(10), LEU(11), GTU(12), NEU(13), GEU(14), T(15) |
| **bop** | [70:69] | AND(0), OR(1), XOR(2) |
| **ftz** | [80] | noftz(0), FTZ(1) |
| **iswzA** | [75:74] | H1_H0(0), H0_H0(2), H1_H1(3) |
| **iswzB** | [61:60] | H1_H0(0), H0_H0(2), H1_H1(3) |
| **H_AND** | [71] | noh_and(0), H_AND(1) |

HSETP2 has no `BVal` (predicate output instead of register), `H_AND` at [71] replaces `bval`. Dest predicates: `Pu` at [83:81] and `Pv`/`Pv+1` at [86:84]. No `Rd` register field (gap at [23:16]).

## Bit layout (RR, 128-bit MSB-left)
- Bits [90:87], [86:84], [83:81]: triple-predicate encoding area
  - [90:90] Pp.not
  - [89:87] Pp (3b)
  - [86:84] Pv (3b: second per-lane pred, auto-increment to Pv+1)
  - [83:81] Pu (3b: first per-lane pred)
- [71]: `H_AND` instead of `bval`
- [23:16]: gap (no Rd)

## Latency (from sm_90_latencies.txt)
Same `FP16_OPS` latency class as all other fp16_pipe ops.

## Open questions
- HSETP2 encodings not yet verified (compiler prefers HSET2 + LOP3 pattern for predicate extraction).
- "noBop" ALT classes — when would Bop AND not be specified?
- Uniform register, const-bank, RCx, and immediate variants not yet verified.
- FCMP values NUM(7), NAN(8), LTU(9), EQU(10), LEU(11), GTU(12), NEU(13), GEU(14), T(15), F(0) not yet verified.
