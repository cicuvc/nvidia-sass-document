# LOP3 — Three-Input Arbitrary Logic (LUT)

**Opcode mnemonic:** `LOP3`  
**Pipe:** `int_pipe` (integer execution pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

Related: `LOP32I` (pipe-only alias, same opcode 0x812), `PLOP3` (predicate-only variant), `ULOP3` (uniform variant).

---

## Variant overview

LOP3 computes an **arbitrary 3-input boolean function** via an 8-bit look-up table
(LUT). The LUT encodes the truth table for `f(A, B, C)` — each of the 8 input
combinations (ABC from 000 to 111) maps to a bit in the imm8 byte.

| Mode     | Mnemonic | Format |
|----------|----------|--------|
| **LUT**  | `LOP3.LUT` | `Rd, Pu, Ra, Rb, Rc, imm8, [!]Pp` |
| **Named**| `LOP3.AND`, `.OR`, `.XOR`, `.PASS_B` | symbolic shortcuts → LUT |
| **IMM**  | `LOP3.LUT` (imm) | `Rd, Pu, Ra, Sb_imm, Rc, imm8, [!]Pp` |

The named-op forms (`AND`, `OR`, `XOR`, `PASS_B`) are **ALTERNATE CLASS**es that
remap the `/LOP:lop` field to the equivalent 8-bit LUT value. The disassembler
renders the symbolic name when possible; otherwise the raw `0xNN` LUT value.

---

## LUT truth-table encoding

The 8-bit `imm8` byte encodes `f(A, B, C)` where `{A, B, C}` = `{Ra, Rb, Rc}`.
Bit `i` corresponds to input `(i & 4)? Ra : 0`, `(i & 2)? Rb : 0`, `(i & 1)? Rc : 0`.

```
Index:  7    6    5    4    3    2    1    0
Ra:     1    1    1    1    0    0    0    0
Rb:     1    1    0    0    1    1    0    0
Rc:     1    0    1    0    1    0    1    0
```

### Common LUT values

| LUT | Binary    | Boolean function | Notes |
|:---:|-----------|------------------|-------|
| `0x80` | `10000000` | **AND** `A & B & C` | 3-input AND |
| `0xFE` | `11111110` | **OR** `A \| B \| C` | 3-input OR |
| `0x96` | `10010110` | **XOR** `A ^ B ^ C` | 3-input XOR |
| `0xC0` | `11000000` | `A & B` | 2-input AND (C=RZ) |
| `0xFC` | `11111100` | `A \| B` | 2-input OR (C=RZ) |
| `0xE0` | `11100000` | `A` | pass-through A (B=RZ, C=RZ) |
| `0xAA` | `10101010` | `C` | pass-through C (A=RZ, B=RZ) |
| `0x0C` | `00001100` | `A & ~B` | AND-NOT |
| `0x33` | `00110011` | `~B` (NOT) | negate B (A=RZ, C=RZ) |
| `0x55` | `01010101` | `~A` (NOT) | negate A (B=RZ, C=RZ) |
| `0xF8` | `11111000` | `A \| (B & C)` | merge: `lo \| (hi & 0xFF)` |
| `0xB8` | `10111000` | `(A & m) \| (B & ~m)` | SELECT/bitwise mux |
| `0xCA` | `11001010` | `(A & B) \| (C & ~(A & B))` | majority |
| `0xE8` | `11101000` | `A \| (B & ~C)` | AND-NOT-OR |
| `0xE2` | `11100010` | `(A & ~B) \| C` | |
| `0x1A` | `00011010` | `A ^ B ^ C` (alt LUT) | 3-input XOR variant |

---

## Pu: predicate output accumulator

Like IADD3, LOP3 has `Pu` as a predicate output slot typed `Predicate("PT")`.
But unlike IADD3 (carry), LOP3's `Pu` accumulates the LUT result into a predicate
for downstream conditional use. The `/LOP_POP` modifier controls the accumulation:

| LOP_POP | Value | Operation |
|---------|:---:|-----------|
| `POR`   | 0 | **OR-accumulate**: `Pu_new = Pu_old \| LUT_result` |
| `PAND`  | 1 | **AND-accumulate**: `Pu_new = Pu_old & LUT_result` |

The `!PT` at the end of the disassembly is `Pp` (not `Pu`): when non-default,
`Pp` captures the LUT result as a one-bit predicate output. The `@not` modifier
inverts the output (`!PT` = predicate-true inverted = always write 0 → discard).

In typical register-to-register usage, `Pu` defaults to PT (discard) and the
data result goes to `Rd`. The `Pp` output similarly defaults to `!PT` (discard).

---

## Operand forms

| Form   | Ra  | Sb               | Rc  | opcode (13-bit) |
|--------|-----|------------------|-----|:---:|
| RRR    | Reg | Reg              | Reg | `0b0001000010010` (0x212) |
| RuIR   | Reg | UImm(32)         | Reg | `0b0100000010010` (0x812) |
| RCR    | Reg | Cb               | Reg | `0b0010100010010` (0xa12) |
| RCxR   | Reg | CXb              | Reg | `0b0110100010010` (0x1a12) |
| RUR    | Reg | URb (6-bit)      | Reg | `0b0111000010010` (0x1c12) |

Named-op and optional-Pp forms are ALTERNATE CLASSes sharing the same opcodes.

---

## ENCODING layout (128-bit, MSB-left)

Shown for `lop3_lut__RRR_RRR` (primary non-ALT).

| Bits                | Width | Field            | Source | Notes |
|---------------------|:-----:|------------------|--------|-------|
| [124:122],[109:105] | 8     | `opex`           | `TABLES_opex_4(...)` | |
| [121:116]           | 6     | `req_bit_set`    | `req_bit_set` | |
| [115:113]           | 3     | `src_rel_sb`     | `*7` | |
| [112:110]           | 3     | `dst_wr_sb`      | `*7` | |
| [103:102]           | 2     | `pm_pred`        | `pm_pred` | |
| **[91],[11:0]**     | **13**| **`opcode`**     | **Opcode** | |
| [90]                | 1     | `Pp_not`         | `Pp@not` | |
| [89:87]             | 3     | `Pnz`            | `Pp` | **predicate output** |
| [83:81]             | 3     | `Pu`             | `Pu` | **predicate accumulator** |
| [80]                | 1     | `pop`            | `pop` (LOP_POP) | 0=POR, 1=PAND |
| **[79:72]**         | **8** | **`imm8`**       | **imm8 (LUT)** | **truth table** |
| [71:64]             | 8     | `Rc`             | `Rc` | |
| [39:32]             | 8     | `Rb`             | `Rb` | |
| [31:24]             | 8     | `Ra`             | `Ra` | |
| [23:16]             | 8     | `Rd`             | `Rd` | |
| [15]                | 1     | `Pg_not`         | `Pg@not` | |
| [14:12]             | 3     | `Pg`             | `Pg` | guard predicate |

### RUR variant differences
- `URb` at [37:32] (6-bit) instead of `Rb` at [39:32] (8-bit)
- `URa` at [29:24] (6-bit) instead of `Ra` at [31:24] (8-bit)

### IMM variant differences
- `Sb` at [63:32] (32-bit immediate) instead of `Rb` at [39:32]
- `TABLES_opex_3` (no reuse_src_b)

---

## Conditions

- Standard register-range checks and opex legality
- No negate/invert constraints (LOP3 has none — pure boolean)

---

## PLOP3: predicate-only variant

PLOP3 applies the same 8-bit LUT to **predicate** registers, producing a
predicate output — no GPR destination. 30 variants covering:
- 0/1/2 GPR inputs (none, 1-reg, 2-reg) plus predicate sources
- LUT mode and named-op mode (AND, OR, XOR, PASS_B)
- Uniform predicate path

The opcode space is related but distinct: PLOP3 RRR opcode = `0b1000011101` (0x21d).

---

## ULOP3: uniform register variant

ULOP3 operates on `UniformRegister`/`UniformPredicate` and executes on `udp_pipe`.
8 variants covering URURUR, URuIUR, LUT and named-op modes. Same LUT encoding,
same Pu/Pp predicate structure with uniform predicates (`UPu`, `UPp`).

---

## Pipe and latency

| Property | Value |
|----------|-------|
| Pipe | `int_pipe` |
| OPERATION SET | `{LOP3, LOP3int_pipe, LOP, LOPint_pipe, LOP32I, LOP32Iint_pipe}` |
| INST_TYPE | `INST_TYPE_COUPLED_MATH` |

Shares the FXU latency matrix (same as IADD3).

---

## Empirical confirmation (sm_90, CUDA 13.1)

### Confirmed LUT patterns

| Operation | SASS | LUT |
|-----------|------|:---:|
| `a & b & c` | `LOP3.LUT R5, R0, R5, R4, 0x80, !PT` | `0x80` |
| `a \| b \| c` | `LOP3.LUT R5, R0, R5, R4, 0xFE, !PT` | `0xFE` |
| `a ^ b ^ c` | `LOP3.LUT R5, R0, R5, R4, 0x96, !PT` | `0x96` |
| `a & b` | `LOP3.LUT R5, R5, R4, RZ, 0xC0, !PT` | `0xC0` |
| `a & ~b` | `LOP3.LUT R5, R5, R4, RZ, 0x0C, !PT` | `0x0C` |
| `~a` (NOT) | `LOP3.LUT R5, RZ, UR4, RZ, 0x33, !PT` | `0x33` |
| `(a&m)\|(b&~m)` | `LOP3.LUT R5, R5, UR4, R4, 0xB8, !PT` | `0xB8` |
| byte merge | `LOP3.LUT R5, R5, 0xFF, R4, 0xF8, !PT` | `0xF8` |

### Key observations

- **RZ defaults**: unused source ports are set to RZ (0xFF encoding), which the
  LUT truth table accounts for — e.g. `a & b` uses `0xC0` with Rc=RZ.
- **UR operands**: the `RUR` form allows UniformRegister as the middle operand
  (used for uniform-path boolean ops like `~a`).
- **32-bit immediate**: `LOP3.LUT Rd, Ra, 0xNNNNNNNN, Rc, LUT, !PT` uses the
  `RuIR` form — 32-bit literal operand at bits [63:32].
- **Dual LOP3 for byte merge**: `(a & 0xFF00) | (b & 0xFF)` maps to two
  LOP3.LUT instructions chained as AND + MERGE.
- **IADD3 alignment check**: `LOP3.LUT R9, R11, 0x1, RZ, 0xC0, !PT` (previously
  seen in the IADD3 carry test) is `R9 = R11 & 1` — bit extraction after
  carry combination.
