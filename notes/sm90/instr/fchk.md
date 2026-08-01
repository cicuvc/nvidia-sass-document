# FCHK — FP Check

**Opcode mnemonic:** FCHK  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

> **Status: semantics verified on SM120 with a clean hand-built ELF (2026-08).**
> FCHK.DIVIDE is a fast-divide safety pre-check: `Pu = 1` when the
> `MUFU.RCP`+Newton path can't be correctly rounded (see "Verified fire
> conditions").  Encoding verified against the CLASS spec and a real ptxas
> vector; decoder round-trip in `tools/decode_fchk.py`.

## Semantics

Checks whether the fast Newton-Raphson reciprocal-based division path (the
`MUFU.RCP` + FFMA refinement sequence ptxas emits for `a/b`) can produce a
correctly-rounded quotient; if not, it sets `Pu = 1` so the `@!P0 BRA` skips
to the software slow path.  It is a **fast-path-safety pre-check**, not a
general NaN/inf/denorm classifier.

The result is written to a **regular predicate** (`Pu`), not a register.
Inputs support `[-]` negate and `[||]` absolute value modifiers (which fold
into the magnitude check and don't change the decision).

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

## Verified fire conditions (SM120, clean hand-built ELF, 2026-08)

`Pu = 1` iff **any** of these holds (magnitude-based; signs irrelevant):

| # | Condition | e.g. fires | boundary (P0=0) |
|---|-----------|-----------|-----------------|
| 1 | Ra or Rb is NaN, ±Inf, ±0, denormal | `a=NaN`, `b=0`, `a=denorm` | — |
| 2 | `\|Ra\| < 2^-102` | `a=2^-103` | `\|Ra\| ≥ 2^-102` (biased exp field ≥ 25) |
| 3 | `\|Rb\| < 2^-125` | `b=2^-126` | `\|Rb\| ≥ 2^-125` (biased exp field ≥ 2) |
| 4 | `\|Rb\| ≥ 2^125` | `b=2^125` | `\|Rb\| < 2^125` (biased exp field ≤ 251) |
| 5 | quotient `Ra/Rb < 2^-125` | `a=2^-60,b=2^65` | quotient ≥ 2^-125 |
| 6 | quotient `Ra/Rb ≥ 2^127` | `a=2^127,b=1` | quotient < 2^127 |

So the fast path is trusted only when **both operands are "normal enough"
AND the quotient stays within `[2^-125, 2^127)`** — i.e. where the
`MUFU.RCP` + Newton refinement is exactly rounded.  Note the quotient bounds
are asymmetric (`2^-125` low vs `2^127` high), matching the RCP accuracy
window.  Verified in `tests/asm_construct/test_fchk.py` (41 checks: boundary
mantissas, all specials, sign/negate/abs invariance, and the 2D
(exponent-a × exponent-b) fire map).

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
| Purpose | Float conditional move | Float fast-divide safety check |
| Scoreboard | Coupled | Decoupled (RD+WR) |
| Queue | — | VQ_MUFU |

### PTX→SASS mapping

ptxas emits `FCHK P0, Ra, Rb` in the FP32 division sequence (sm_90, verified
against cuobjdump):

```
MUFU.RCP R0, R7            ; ~1/b
FCHK  P0, R6, R7           ; safety check (Ra=dividend, Rb=divisor)
FFMA  R3, R0, -R7, 1       ; \ 5× Newton refinement (not 3×):
FFMA  R3, R0, R3, R0       ; |  rcp' = rcp + rcp·(1 − b·rcp)
FFMA  R5, R3, R6, RZ       ; |  q ≈ a·rcp'
FFMA  R0, R5, -R7, R6      ; |  residual a − q·b
FFMA  R5, R3, R0, R5       ; /  q += rcp'·residual
@!P0  BRA  fast_done       ; P0==0 → skip slow path
      MOV  R4, 0xd0        ; arg for the fixup
      CALL.REL.NOINC 0x130 ; software slow path (reloads a,b from cbank)
```

**Slow path (`0x130`) re-derives the exponent of both operands from the
fast-path result** (`SHF.R.U32.HI` + `LOP3.LUT …0xff` extract the biased
exponent, `VIADD −1`), and:

- `ISETP.GT.U32 0xfd` — if either exponent field > 0xfd (huge/Inf class),
  normalizes via the generic path (BRA 0x370).
- `FSETP.GTU |R2|, +INF` — if either operand is Inf (incl. NaN payloads),
  jumps to the Inf/NaN handler (0x750).
- `LOP3 0xc8 (R7&0x7fffffff, R6)` — if signs don't match a normal divide
  (BRA 0x730) handle −0/denormal/underflow; otherwise
  `FSETP.NEU |R2|, +INF` re-check for the final Inf case.
- Ends with the sign merge (`LOP3 …0xc8` xor of the two sign bits) and
  round-to-nearest result.

The slow path is the *fully general* divide (handles the cases FCHK
rejected); the fast path is the RCP-based Newton sequence trusted only for
the verified window.  See `notes/sm90/arch/div.md`.

## Verified encodings (SM120)

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000706007302` | `0x0000000000000000` | `FCHK P0, R6, R7` |
| `0x0000000706007302` | `0x0000000000020000` | `FCHK P1, R6, R7` |
| `0x0000000706007302` | `0x0000000000000200` | `FCHK P0, \|R6\|, R7` |
| `0x0000000706007302` | `0x0000000000000100` | `FCHK P0, -R6, R7` |
| `0x8000000706007302` | `0x0000000000000000` | `FCHK P0, R6, -R7` |
| `0x0000000706007302` | `0x000ea20000000000` | `FCHK P0, R6, R7` (ptxas real vector) |

Decoder round-trip + the real ptxas vector: `tools/decode_fchk.py`.
