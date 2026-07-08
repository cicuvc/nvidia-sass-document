# FCHK — FP Check

**Opcode mnemonic:** FCHK  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

## Semantics

Checks floating-point operands for special values (NaN, infinite, denormal) and sets a predicate bit: `Pu = fcheck(Ra, Rb)`. Used for pre-divide validation (ChkMode=DIVIDE) to detect exceptional inputs that would cause a divide-by-zero or invalid-result.

The result is written to a **regular predicate** (`Pu`), not a register. Inputs support `[-]` negate and `[||]` absolute value modifiers.

## Variant overview

| Variant | Opcode | Format |
|---------|--------|--------|
| `fchk__RRR_RR` | `0x302` | `FCHK Pu, [-] [\|\|] Ra, [-] [\|\|] Rb` |
| `fchk__RIR_RI` | `0x902` | `FCHK Pu, [-] [\|\|] Ra, F32Imm` |
| `fchk__RCR_RC` | `0xb02` | `FCHK Pu, [-] [\|\|] Ra, c[bank][offset]` |
| `fchk__RCxR_RCx` | `0x1b02` | `FCHK Pu, [-] [\|\|] Ra, c[UR][offset]` |
| `fchk__RUR_RU` | `0x1d02` | `FCHK Pu, [-] [\|\|] Ra, [-] [\|\|] URb` |

## Modifiers

| Modifier | Field | Bit | Values |
|----------|-------|-----|--------|
| Ra absolute | sz | [73] | 1=`[\|\|]` |
| Ra negate | e | [72] | 1=`[-]` |
| Rb negate | Sb_invert | [63] | 1=`[-]` |
| Rb absolute | Sc_absolute | [62] | 1=`[\|\|]` |

ChkMode: always DIVIDE(0) on sm_90 — no other check modes defined.

## Bit layout (RR — opcode 0x302)

```
[83:81]              Pu         <= Pu (output predicate)
[73:73]              sz         <= Ra@absolute
[72:72]              e          <= Ra@negate
[63:63]              Sb_invert  <= Rb@negate
[62:62]              Sc_absolute <= Rb@absolute
[39:32]              Rb         <= Rb
[31:24]              Ra         <= Ra
[15:15]              Pg_not     <= Pg@not
[14:12]              Pg         <= Pg
[91:91],[11:0]       opcode     <= 0b1100000010
```

## Key features

- **Decoupled scoreboard**: `INST_TYPE_DECOUPLED_RD_WR_SCBD` — separate read (RD) and write (WR) release scoreboards. The `src_rel_sb` and `dst_wr_sb` fields use variable-latency encoding (`VarLatOperandEnc()`), unlike the fixed `*7` of coupled-pipe instructions.
- **VIRTUAL_QUEUE=$VQ_MUFU**: Dispatched to the multi-function unit (MUFU) queue, which also handles transcendental ops (MUFU, RRO, etc.).
- **mio_pipe**: Memory I/O pipeline, same as LDG/STG, not the integer pipe.

## Latency

`mio_pipe`, decoupled scoreboard. FCHK falls under `MIO_CBU_OPS_WITHOUT_ELECT` in the latency tables. Latency higher than int_pipe ops due to MUFU dispatch.

## Cross-comparison

| Property | FSEL | FCHK |
|----------|------|------|
| Pipe | `int_pipe` | `mio_pipe` |
| Output | `Rd` (register) | `Pu` (predicate) |
| Purpose | Float conditional move | Float exception check |
| Scoreboard | Coupled | Decoupled (RD+WR) |
| Queue | — | VQ_MUFU |
