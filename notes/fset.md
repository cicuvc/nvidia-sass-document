# FSET — FP32 Comparison to Register

**Opcode mnemonic:** `FSET`  
**Pipe:** `int_pipe` (integer pipe — not fmalighter_pipe!)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd = CMP(Ra, Rb)` — compare two FP32 values and write boolean result (0x00000000 or
0xFFFFFFFF) to a register. Optionally combines the result with a predicate input
using a **Boolean operator** (AND/OR/XOR), and outputs a predicate `Pp` capturing
the comparison result.

```
Rd = (Ra CMP Rb) BOP Pp_input
```

where `CMP` is one of 16 relational operators and `BOP` is AND/OR/XOR.

## Variant overview — 5 base + 5 `_simple` = 10 variants

| Variant | Opcode | Notes |
|---------|:------:|-------|
| `fset__RRR_RRR` | 0x20a | Full: with Bop + Pp output |
| `fset__RIR_RIR` | 0x80a | F32Imm Rb |
| `fset__RCR_RCR` | 0xa0a | Const bank Rb |
| `fset__RCxR_RCxR` | 0x1a0a | Const bank+UR Rb |
| `fset__RUR_RUR` | 0x1c0a | UniformRegister Rb |
| `fset_simple__RRR_RRR` | 0x20a | **ALTERNATE**: no Bop, no Pp output |
| + 4 more `_simple` | same | Same opcodes, different format interpretation |

The `_simple` variants share the same opcodes but lack the `Bop` modifier and
`Pp` predicate output slot. The decoder selects between them based on the
Bop field value.

## Modifiers

| Modifier | Field | Width | Values |
|----------|-------|:---:|--------|
| **fcomp** | [79:76] | 4 | 16 comparison types (see below) |
| **bop** | [75:74] | 2 | `AND`(0), `OR`(1), `XOR`(2), `INVALID3`(3) |
| **ftz** | [80] | 1 | `noftz`(0), `FTZ`(1) |
| **bf** (BFONLY) | — | — | Always `BF`(0), single-value enum |

## FCMP comparison types

| Value | Name | Semantics | Signed/Unsigned |
|:-----:|------|-----------|:---:|
| 0 | `F` | Always false | — |
| 1 | `LT` | Less than | signed |
| 2 | `EQ` | Equal | signed |
| 3 | `LE` | Less or equal | signed |
| 4 | `GT` | Greater than | signed |
| 5 | `NE` | Not equal | signed |
| 6 | `GE` | Greater or equal | signed |
| 7 | `NUM` | Not NaN | — |
| 8 | `NAN` | Is NaN | — |
| 9 | `LTU` | Less than | unsigned |
| 10 | `EQU` | Equal | unsigned |
| 11 | `LEU` | Less or equal | unsigned |
| 12 | `GTU` | Greater than | unsigned |
| 13 | `NEU` | Not equal | unsigned |
| 14 | `GEU` | Greater or equal | unsigned |
| 15 | `T` | Always true | — |

## Bit layout (RRR_RRR, 128-bit MSB-left)

```
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[91],[11:0]             opcode       (13b)
[90]                    Pp.not       (1b)
[89:87]                 Pp           (3b: output predicate, 7=PT=discard)
[86:81]                 -- gap --
[80]                    ftz          (1b)
[79:76]                 fcomp        (4b: comparison type)
[75:74]                 bop          (2b: AND/OR/XOR)
[73]                    Ra.absolute
[72]                    Ra.negate
[71:64]                 -- gap --
[63]                    Rb.negate
[62]                    Rb.absolute
[61:40]                 -- gap --
[39:32]                 Rb           (8b)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not
[14:12]                 Pg           (3b: predicate, 7=PT)
```

## Verified encodings (cuobjdump, sm_90)

14/14 matches, covering all 14 non-trivial comparison types (F=0 and T=15 not yet
triggered). Decoder: `tools/decode_fset.py`.

All share lo64 = `0x000000050405720a` (opcode 0x20a, R5=Rd, R4=Ra, R5=Rb, bop=AND, Pp=PT).

| hi64 | fcomp | Disassembly |
|------|:---:|-------------|
| `0x001fc60003801000` | 1 | FSET.BF.LT.AND R5, R4, R5, PT |
| `0x001fc60003802000` | 2 | FSET.BF.EQ.AND R5, R4, R5, PT |
| `0x001fc60003803000` | 3 | FSET.BF.LE.AND R5, R4, R5, PT |
| `0x001fc60003804000` | 4 | FSET.BF.GT.AND R5, R4, R5, PT |
| `0x001fc60003805000` | 5 | FSET.BF.NE.AND R5, R4, R5, PT |
| `0x001fc60003806000` | 6 | FSET.BF.GE.AND R5, R4, R5, PT |
| `0x001fc60003807000` | 7 | FSET.BF.NUM.AND R5, R4, R5, PT |
| `0x001fc60003808000` | 8 | FSET.BF.NAN.AND R5, R4, R5, PT |
| `0x001fc60003809000` | 9 | FSET.BF.LTU.AND R5, R4, R5, PT |
| `0x001fc6000380a000` | 10 | FSET.BF.EQU.AND R5, R4, R5, PT |
| `0x001fc6000380b000` | 11 | FSET.BF.LEU.AND R5, R4, R5, PT |
| `0x001fc6000380c000` | 12 | FSET.BF.GTU.AND R5, R4, R5, PT |
| `0x001fc6000380d000` | 13 | FSET.BF.NEU.AND R5, R4, R5, PT |
| `0x001fc6000380e000` | 14 | FSET.BF.GEU.AND R5, R4, R5, PT |

### PTX→SASS mapping

| PTX | SASS |
|-----|------|
| `set.{CMP}.f32.f32 d, a, b` | `FSET.BF.{CMP}.AND d, a, b, PT` |
| `set.{CMP}.{BOP}.f32.f32 d, a, b, c` | `FSET.BF.{CMP}.{BOP} d, a, b, c` |
| `set.{CMP}.ftz.f32.f32 d, a, b` | → FSETP (ptxas prefers FSETP over FSET for FTZ) |

Note: ptxas on sm_90 always emits the full variant (with `.AND` and `PT` output
predicate), even for simple comparisons without BoolOp. The `.BF` prefix is always
present (BFONLY single-value enum).

### FSET vs FSETP

| Aspect | FSET | FSETP |
|--------|------|-------|
| Output | Register (Rd) | Predicate (Pp) |
| BoolOp | AND/OR/XOR with predicate | AND/OR/XOR with predicate |
| Pipe | int_pipe | int_pipe |
| Opcode | 0x20a | 0x20b |

FSET outputs a register (for masking, selection, etc.), while FSETP outputs a
predicate (for branch/select/mux). ptxas may substitute one for the other based
on optimization heuristics (e.g., FTZ cases prefer FSETP).

## Latency

FSET is on `int_pipe`; TABLE_TRUE 6–8, TABLE_OUTPUT 1–2, TABLE_ANTI 1–2 (FXU_OPS).

## Open questions

- Bop=OR and Bop=XOR not yet triggered in any test
- `_simple` variant (no Bop, no Pp) not observed — ptxas always emits full variant
- F=0 (always false) and T=15 (always true) comparison types not yet triggered
- FTZ on FSET: does it exist in hardware or is it always lowered to FSETP?
