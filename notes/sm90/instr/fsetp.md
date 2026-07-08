# FSETP — FP32 Comparison to Predicates

**Opcode mnemonic:** `FSETP`  
**Pipe:** `int_pipe`  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Pu, Pv = CMP(Ra, Rb)` — compare two FP32 values and write boolean results to
**two predicate registers**: `Pu` holds the comparison result, `Pv` holds its
complement. Optionally combines the result with a predicate input `Pp` using
a Boolean operator (AND/OR/XOR).

```
Pu  = (Ra CMP Rb) BOP Pc
Pv  = ¬((Ra CMP Rb) BOP Pc)
```

`Pp` is the Bop input predicate (`[!]Pp`). `Pu` and `Pv` are always complementary.

No register destination (`IDEST_SIZE = 0`).

## Variant overview — 5 base + 5 `_simple` = 10 variants

| Variant | Opcode |
|---------|:------:|
| `fsetp__RRR_RRR` | 0x20b |
| `fsetp__RIR_RIR` | 0x80b |
| `fsetp__RCR_RCR` | 0xa0b |
| `fsetp__RCxR_RCxR` | 0x1a0b |
| `fsetp__RUR_RUR` | 0x1c0b |
| + 5 `_simple` (ALT) | same opcodes, no Bop |

## Modifiers

| Modifier | Field | Width | Values |
|----------|-------|:---:|--------|
| **fcomp** | [79:76] | 4 | 16 comparison types (same FCMP enum as FSET) |
| **bop** | [75:74] | 2 | `AND`(0), `OR`(1), `XOR`(2), `INVALID3`(3) |
| **ftz** | [80] | 1 | `noftz`(0), `FTZ`(1) |

## Bit layout (RRR_RRR, 128-bit MSB-left)

```
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[91],[11:0]             opcode       (13b) = 0x20b
[90]                    Pp.not       (1b)
[89:87]                 Pp           (3b: Bop input predicate)
[86:84]                 Pv           (3b: complement output)
[83:81]                 Pu           (3b: primary output)
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
[15]                    Pg.not
[14:12]                 Pg           (3b: guard predicate, 7=PT)
[23:16]                 -- unused --   ← no Rd!
```

## FSET vs FSETP (side-by-side)

| Aspect | FSET (0x20a) | FSETP (0x20b) |
|--------|:-----------:|:------------:|
| Primary output | Register Rd | Predicate Pu (and Pv) |
| Output count | 1 register + 1 pred | 2 predicates + Bop input |
| IDEST_SIZE | 32 | 0 |
| Rd field | [23:16] | — unused — |
| Pu field | — | [83:81] |
| Pv field | — | [86:84] |
| Pp field | [89:87] | [89:87] (Bop input!) |
| Bop | AND/OR/XOR on Pp | AND/OR/XOR on Pp |
| BF suffix | `.BF` (always) | No `.BF` |
| FTZ pattern in asm | CMP.FTZ? | CMP.FTZ.BOP |
| ptxas preference | For set.f32 | For setp.f32 and some FTZ cases |

## Verified encodings (cuobjdump, sm_90)

5/5 matches. Decoder: `tools/decode_fsetp.py`.

All share lo64 = `0x000000050400720b` (opcode 0x20b, Ra=R4, Rb=R5, Pu=P0, Pv=PT).

| hi64 | fcomp | Disassembly |
|------|:---:|-------------|
| `0x001fc80003f11000` | 1 | FSETP.LT.FTZ.AND P0, PT, R4, R5, PT |
| `0x001fc80000701000` | 1 | FSETP.LT.AND P0, PT, R4, R5, P0 |
| `0x001fc80003f04000` | 4 | FSETP.GT.AND P0, PT, R4, R5, PT |
| `0x001fc80003f0d000` | 13 | FSETP.NEU.AND P0, PT, R4, R5, PT |
| `0x001fc80003f0e000` | 14 | FSETP.GEU.AND P0, PT, R4, R5, PT |

### PTX→SASS mapping

| PTX | SASS |
|-----|------|
| `setp.{CMP}.f32 Pu, Pv, a, b` | `FSETP.{CMP}.AND Pu, Pv, a, b, PT` |
| `setp.{CMP}.ftz.f32 Pu, Pv, a, b` | `FSETP.{CMP}.FTZ.AND Pu, Pv, a, b, PT` |
| `setp.{CMP}.{BOP}.f32 Pu, Pv, a, b, c` | `FSETP.{CMP}.{BOP} Pu, Pv, a, b, c` |
| `if (a < b)` (C++) | `FSETP.LT.AND P0, PT, a, b, PT` |

For simple C++ bool comparisons (e.g., `return a < b`), ptxas emits FSETP (not
FSET) because the result feeds a predicate/conditional, not a register.

## Latency

Same as FSET: TABLE_TRUE 6–8, TABLE_OUTPUT 1–2, TABLE_ANTI 1–2 (int_pipe/FXU_OPS).

## Open questions

- Bop=OR and Bop=XOR not yet verified
- `_simple` variant (no Bop) not yet observed
- Relationship with ISETP (integer setp) — same opcode pattern?
