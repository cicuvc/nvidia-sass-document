# PLOP3 — Predicate Three-Input Logic

**Opcode mnemonic:** PLOP3  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Regular-predicate three-input logic operation. Produces one (Pu) or two (Pu, Pv) predicate outputs from an 8-bit LUT applied to three source predicates or three register sign bits. Equivalent to `LOP3` for predicates.

The input sources can be:
- **Predicates only** (`Pp`, `Pq`, `Pr` with optional `!` negation) — 0-register form
- **Register sign bits** (SIGNONLY extracts bit 31) — 1, 2, or 3-register forms
- **Constant bank** / **uniform register** — RCR, RCxR, RUR variants

Each register source has a `.reuse` flag for pipeline optimization.

Empirically confirmed: the 0-register, 2-output LUT form appears in ptxas-generated code with complex conditional branches (`plop3_test.cu`). Only the 0-reg form observed; 1/2/3-reg forms not yet seen in practice.

## Variant overview (30 total)

Matrix: {0-reg, 1-reg, 2-reg, 3-reg} × {1-out, 2-out} × {RRR, RCR, RCxR, RUR, uniform}

| Regs | 1-out RRR | 2-out RRR | 1-out RCR | 2-out RUR | ... |
|------|-----------|-----------|-----------|-----------|-----|
| 0 | `0x81c` (ALT) | `0x81c` | — | — | also LOP & uniform |
| 1 | `0x21d` (ALT) | `0x21d` | `0xa1d` | `0x1c1d` | |
| 2 | `0x21e` (ALT) | `0x21e` | `0xa1e` | `0x1c1e` | |
| 3 | `0x21f` (ALT) | `0x21f` | `0xa1f` | `0x1c1f` | |

Additional modes:
- `plop3_1out_` (ALT): LOP mode using PLOP_OP_NOREG (AND=32768, XOR=38400, SEL=51712, OR=65024)
- `plop3_*_uniform_` (ALT): Uses uniform predicates (UPp, UPq, UPr) as inputs instead of regular predicates

## Modifiers

| Modifier | Field | Bits | Description |
|----------|-------|------|-------------|
| SIGNONLY | — | — | Extracts sign bit (bit 31) from register input |
| Pp@not | input_reg_sz | [90] | Invert predicate input P |
| Pq@not | UPq_not | [80] | Invert predicate input Q |
| Pr@not | memdesc | [71] | Invert predicate input R |
| uimm8 | SRa ([79:72]) | [79:72] | 8-bit LUT for Pu output |
| vimm8 | Rd ([23:16]) | [23:16] | 8-bit LUT for Pv output (2-out only) |

## Bit layout (0-reg, 2-out — opcode 0x81c)

```
[90:90]              input_reg_sz_32_dist <= Pp@not
[89:87]              Pnz                  <= Pp
[86:84]              cop                  <= Pv
[83:81]              Pu                   <= Pu
[80:80]              UPq_not              <= Pq@not
[79:77]              UPq                  <= Pq
[76:72],[66:64]      uimm8                <= uimm8 (8-bit LUT for Pu)
[71:71]              memdesc              <= Pr@not
[70:68]              UPr                  <= Pr
[23:16]              Rd                   <= vimm8 (8-bit LUT for Pv)
[15:15]              Pg_not               <= Pg@not
[14:12]              Pg                   <= Pg
[91:91],[11:0]       opcode               <= 0b100000011100
```

## Bit layout (3-reg, 2-out RRR — opcode 0x21f)

```
[86:84]              cop       <= Pv
[83:81]              Pu        <= Pu
[79:72]              SRa       <= uimm8
[71:64]              Rc        <= Rc (8-bit register)
[39:32]              Rb        <= Rb
[31:24]              Ra        <= Ra
[23:16]              Rd        <= vimm8
[15:15]              Pg_not    <= Pg@not
[14:12]              Pg        <= Pg
[91:91],[11:0]       opcode    <= 0b1000011111
```

RCR variant (0xa1f): Ra/c[bank] replaces Rc, same structure.
RCxR variant (0x1a1f): Ra/c[URb] replaces Rc.
RUR variant (0x1c1f): Ra/URb replaces Rc.

## Cross-comparison

| Property | PLOP3 | UPLOP3 | ULOP3 |
|----------|-------|--------|-------|
| Pipe | `int_pipe` | `udp_pipe` | `udp_pipe` |
| Output | Regular predicate | Uniform predicate | Uniform register |
| Input predicates | Pp, Pq, Pr (regular) | UPp, UPq, UPr | — (uses registers) |
| Input registers | Ra, Rb, Rc | URa, URb, URc | URa, URb, URc |
| Source variants | RRR,RCR,RCxR,RUR | URURUR | URURUR, URIUR |
| LUT width | 8-bit (×2 for 2-out) | 8-bit (×2) | 8-bit |

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. `FXU_OPS` group in GPR tables, `MATH_PRED_NO_FP16_FP64_OPS` in PRED tables.

## Verified encodings

From `plop3_test.cu` (sm_90, CUDA 13.1):

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x000000000000781c` | `0x000fda0000f25570` | `PLOP3.LUT P1, PT, P1, P2, PT, 0xa8, 0x0` |

LUT=0xa8 = 0b10101000: with inputs (Pp,Pq,Pr)=(P1,P2,PT), this produces output only for combinations 7 (111), 5 (101), and 3 (011). This corresponds to a specific Boolean function of the three predicate inputs, with vimm8=0x0 (Pv output forced to false).
