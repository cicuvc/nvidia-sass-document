# DSETP — FP64 Compare-Set-Predicate

**Opcode:** `0x22a` (RRR), `0x42a` (RRsI), `0x62a` (RRC), `0x162a` (RRCx), `0x1e2a` (RRU)  
**Pipe:** `fma64lite_pipe`, `$VQ_REDIRECTABLE`  
**TYPE:** `INST_TYPE_COUPLED_EMULATABLE`  
**Scoreboard:** `IDEST_SIZE=0` — no register output, predicate-only result

## Semantics

Compares two FP64 values (`Ra` and `Rc/URc`) and writes the boolean result to
predicate registers `Pu` and `Pv`. The `Pp` accumulator predicate allows
chaining with previous comparison results.

`Pu, Pv = Ra DSETP_FCMP Rc, chained via Pp`

Pairs with FSETP (F32) and HSET2 (F16) as the FP64 member of the compare-
set-predicate family.

## Format

```
@Pg DSETP{.test}{.bop} Pu, Pv, [-]|[||]Ra{.reuse}, [-]|[||]Rc/URc{.reuse}, [!]Pp
```

## Modifiers

### DSETP_FCMP (test) — 4-bit

| Value | Mnemonic | Description |
|:---:|----------|------|
| 0 | `.MIN` | Minimum (always false?) |
| 1 | `.LT` | Less than |
| 2 | `.EQ` | Equal |
| 3 | `.LE` | Less or equal |
| 4 | `.GT` | Greater than |
| 5 | `.NE` | Not equal |
| 6 | `.GE` | Greater or equal |
| 7 | `.NUM` | Is numeric (not NaN) |
| 8 | `.NAN` | Is NaN |
| 9 | `.LTU` | Less than (unordered) |
| 10 | `.EQU` | Equal (unordered) |
| 11 | `.LEU` | Less or equal (unordered) |
| 12 | `.GTU` | Greater than (unordered) |
| 13 | `.NEU` | Not equal (unordered) |
| 14 | `.GEU` | Greater or equal (unordered) |
| 15 | `.MAX` | Maximum (always true?) |

### Bop — 2-bit

| Value | Mnemonic |
|:---:|----------|
| 0 | `.AND` (default) |
| 1 | `.OR` |
| 2 | `.XOR` |
| 3 | INVALID |

### Operand negation/absolute

Ra supports `[-]` and `[||]`; Rc supports `[-]` and `[||]`. Negate flips
the comparison sense via sign bit inversion.

### Pp — accumulator predicate

The `Pp` predicate allows chaining: `result = (Ra op Rc) bop Pp`. Default
`Pp = PT` (always true for first comparison in chain).

### Encoding detail

The test field [79:76] per the spec CLASS encoding does not match the
actual ptxas-generated encoding — the test value is instead encoded in
the `opex` (operation extension) field along with scoreboard configuration.
This is consistent across DFMA/DMUL/DADD/DSETP, suggesting ptxas uses a
different micro-architectural encoding from what the CLASS dump captures.

## Verified encodings

| Disassembly | PTX |
|-------------|-----|
| `DSETP.LEU.AND P0, PT, R6, UR4, PT` | `setp.leu.f64` (RRU_RU variant) |
| `DSETP.LT.AND P0, PT, R4, UR4, PT` | `setp.lt.f64` |
| `DSETP.NEU.AND P2, PT, R4, UR4, PT` | `setp.neu.f64` |

All observed instances use the RRU_RU variant (URc promoted to uniform register).

## PTX to SASS

| PTX | SASS |
|-----|------|
| `setp.lt.f64 %p, %ra, %rb` | `DSETP.LT.AND Pu, PT, Ra, UR4, PT` |
| `setp.leu.f64` | `DSETP.LEU.AND` |
| `setp.neu.f64` | `DSETP.NEU.AND` |
