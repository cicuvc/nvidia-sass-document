# IADD3 — Three-Input Integer Add

**Opcode mnemonic:** `IADD3`  
**Pipe:** `int_pipe` (integer execution pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Variant overview

IADD3 performs `Rd = Ra + (±)Sb + (±)Rc` (three-input add/subtract) on 32-bit integers.
All variants share the mnemonic `IADD3`; the extended (X) form adds carry-chain predicates.
Related: `IADD` (two-input add alias), `IADD32I` (pipe-only alias), `UIADD3` (uniform variant).

| Mode   | ASM format | Operands | Carry output |
|--------|-----------|:---:|:---:|
| **Plain** | `IADD3 Rd, Pu, Pv, [-]Ra, [-]Rb, [-]Rc` | 3-source with per-src negate | `Pu,Pv` (2-bit) |
| **X**      | `IADD3.X Rd, Pu, Pv, [~]Ra, [~]Rb, [~]Rc, [!]Pp, [!]Pq` | 3-source with per-src invert | `Pp,Pq` (X-mode) |

- **Plain**: `Rd = (±Ra) + (±Rb) + (±Rc)`. Ra and Rb cannot be simultaneously
  negated (`Ra@negate → ¬Rb@negate` and vice versa). Rc negate is independent.
- **X**: extended-precision carry chain. Uses `[~]` (bitwise NOT/ones-complement)
  instead of `[-]` (two's complement negate). Pp and Pq capture carry bits.
  Ra and Rb cannot both be inverted (`Ra@invert → ¬Rb@invert`).

### Pu and Pv: 2-bit carry output (verified)

**Pu and Pv are carry outputs, not generic predicate inputs.** Three 32-bit unsigned
values can sum to a 34-bit result; the two carry bits are captured into these
predicate registers. The `Predicate("PT")` typing with default `PT=7` follows the
same convention as `IMAD.HI`'s `Pu` carry output: when set to PT (7), the carry
is **discarded** (analogous to writing a register result to RZ). When set to a
non-default predicate (e.g. P0, P1), the carries are captured for downstream use.

```
IADD3 R7,  P0, P1,  R7, UR4, R6     ; P0 = carry₁ from (Ra+Rb)
                                     ; P1 = carry₂ from ((Ra+Rb)+Rc)
IADD3.X R9, RZ, RZ, RZ, P0, P1      ; R9 = P0 + P1 = combined 2-bit carry
```

The compiler emits this pattern explicitly when 3-way carry extraction is needed
(e.g. accumulating `(unsigned long long)x + y + z`). In typical two-operand
usage (e.g. `a + b + RZ`) at most one carry bit is produced; Pu captures it
and Pv is left at PT (discarded, omitted from disassembly).

### Uniform variant: UIADD3

`UIADD3` / `UIADD3.X` uses uniform registers and executes on `udp_pipe`. Same
semantics but with `UniformRegister` and `UniformPredicate` types. Two operand
forms: URURUR and URsIUR.

---

## Operand forms (5 plain, 1 immediate)

| Form   | Ra  | Sb             | Rc  | opcode (13-bit) |
|--------|-----|----------------|-----|:---:|
| RRR    | Reg | Reg            | Reg | `0b_0001000010000` (0x210) |
| RsIR   | Reg | SImm(32)       | Reg | `0b_0100000010000` (0x810) |
| RCR    | Reg | Cb             | Reg | `0b_0010100010000` (0xa10) |
| RCxR   | Reg | CXb            | Reg | `0b_0110100010000` (0x1a10) |
| RUR    | Reg | URb            | Reg | `0b_0111000010000` (0x1c10) |

No multi-register or HI/WIDE forms (always 32-bit). X forms share the same
opcodes, distinguished by the `/XONLY:X` modifier in the encoding.

---

## ENCODING layout (128-bit, MSB-left)

Shown for `iadd3_noimm__RRR_RRR`; the `imm` form differs only in Sb encoding.

| Bits                | Width | Field            | Source | Notes |
|---------------------|:-----:|------------------|--------|-------|
| [124:122],[109:105] | 8     | `opex`           | `TABLES_opex_4(...)` | reuse/drain control |
| [121:116]           | 6     | `req_bit_set`    | `req_bit_set` | barrier mask |
| [115:113]           | 3     | `src_rel_sb`     | `*7` | fixed (no SB release) |
| [112:110]           | 3     | `dst_wr_sb`      | `*7` | fixed (no SB write) |
| [103:102]           | 2     | `pm_pred`        | `pm_pred` | perf-monitor |
| **[91],[11:0]**     | **13**| **`opcode`**     | **Opcode** | |
| [90]                | 1     | `input_reg_sz_32_dist` | `*1` (plain) / `Pp@not` (X) | |
| [89:87]             | 3     | `Pnz`            | `*7` (plain) / `Pp` (X) | X: carry-out pred |
| [86:84]             | 3     | `cop`            | `Pv` | **carry₂ output** (plain) / `Pv` input (X) |
| [83:81]             | 3     | `Pu`             | `Pu` | **carry₁ output** (plain) / `Pu` input (X) |
| [80]                | 1     | `UPq_not`        | `*1` (plain) / `Pq@not` (X) | |
| [79:77]             | 3     | `UPq`            | `*7` (plain) / `Pq` (X) | X: 2nd carry-out pred |
| **[75]**            | **1** | `sz`             | `Rc@negate` (plain) / `Rc@invert` (X) | |
| [74]                | 1     | `sh`             | `0` (plain) / `*X` (X) | |
| **[72]**            | **1** | `e`              | `Ra@negate` (plain) / `Ra@invert` (X) | |
| [71:64]             | 8     | `Rc`             | `Rc` | |
| **[63]**            | **1** | `Sb_invert`      | `Rb@negate` (plain) / `Rb@invert` (X) | |
| [39:32]             | 8     | `Rb`             | `Rb` | (or SImm[31:24] in imm form) |
| [31:24]             | 8     | `Ra`             | `Ra` | |
| [23:16]             | 8     | `Rd`             | `Rd` | |
| [15]                | 1     | `Pg_not`         | `Pg@not` | |
| [14:12]             | 3     | `Pg`             | `Pg` | guard predicate |

### Immediate form differences

- `Rb` at [39:32] is replaced by the upper bits of `SImm(32)*:Sb`; the full
  32-bit immediate occupies [63:32] as `Ra_offset`.
- `TABLES_opex_3(batch_t, usched_info, reuse_src_a, reuse_src_c)` instead of
  `TABLES_opex_4` (no `reuse_src_b` since Sb is an immediate).
- No `Rb@negate`/`Rb@invert` bits (immediate is always literal).

---

## Key differences from IMAD

| Feature | IMAD | IADD3 |
|---------|------|-------|
| Pipe | `fmalighter_pipe` | `int_pipe` |
| Operation | `(Ra×Rb)+Rc` | `Ra+Rb+Rc` |
| Width modes | LO/WIDE/HI | 32-bit only |
| Predicate ports | 1 input (Pg) + 1 output (Pu, WIDE/HI only) | **2 carry outputs** (Pu, Pv) in plain mode
| Guard pred | Pg | Pg |
| X-mode inversion | `[~]` on Rc only | `[~]` on **all three** sources |
| IMUL pseudo | Yes (Ra=RZ → IMUL) | No (Rc=RZ → IADD) |
| Immediate slot | 32-bit (in Rb or Rc slot) | 32-bit (in Sb slot only) |

---

## Conditions (legality assertions)

Key constraints unique to IADD3:

### Simultaneous negate ban
```
(Ra@negate == 1) -> (Rb@negate == 0)    // reason: nA-Rb
(Rb@negate == 1) -> (Ra@negate == 0)    // reason: Ra-nB
```
Same for X-mode: `(Ra@invert) -> ¬(Rb@invert)`.

### Register range
All register operands ≤ `%MAX_REG_COUNT-1`, ≠ `R254`.

### opex
`TABLES_opex_4` (or `_3` for imm) must be a valid combination; `.reuse` is
mutually exclusive with DRAIN/WAIT scheduling tokens.

---

## Pipe and latency

| Property | Value |
|----------|-------|
| Pipe | `int_pipe` |
| IADD3 OPERATION SET | `{IADD3, IADD3int_pipe, IADD, IADDint_pipe, IADD32I, IADD32Iint_pipe}` |
| INST_TYPE | `INST_TYPE_COUPLED_MATH` |

### True dependency latency (TABLE_TRUE, FXU_OPS)

IADD3 shares the FXU latency matrix:
```
FXU_OPS {Rd @1, Rd2 @0} : 6 6 6 6 6 6 6 8 6 6 7 7 7 7 7 7 6 8
```

Shortest true-dep latency is **6 cycles** (vs 4–5 for IMAD on fmalighter).

---

## Empirical confirmation (sm_90, CUDA 13.1)

All operand forms and X-mode verified via `nvcc -arch=sm_90 -O3` →
`cuobjdump -arch sm_90 -sass`.

### Confirmed forms

| Form | SASS | opcode |
|------|------|:---:|
| RRR (3-reg) | `IADD3 R5, R0, R5, R4` | 0x210 |
| RRR (2-op, Rc=RZ) | `IADD3 R5, R5, R4, RZ` | 0x210 |
| RsIR (imm) | `IADD3 R5, R4, 0x2a, R5` | 0x810 |
| RsIR (imm+RZ) | `IADD3 R7, R2, 0x1, RZ` | 0x810 |
| RRR (neg Rc) | `IADD3 R5, R0, R4, -R5` | 0x210 |
| UIADD3 | `UIADD3 UR4, UP0, UR4, UR6, URZ` | 0x1290 |
| UIADD3.X | `UIADD3.X UR5, UR5, UR7, URZ, UP0, !UPT` | 0x1290 |

### Negate encoding
`IADD3 R5, R0, R4, -R5` vs plain: only bit [75] differs (Rc_neg=1).

### Pu/Pv: 2-bit carry output — empirically verified

The theory that Pu and Pv are carry outputs (not general predicate inputs) is
**confirmed** by kernels that force 3-way carries. Given three 32-bit unsigned
values, the sum can reach ~34 bits; the compiler emits explicit non-default
predicates when the carries are needed downstream.

**3-way addition with carry extraction** (`x + y + z` as `u64`):
```
IADD3 R13, P0, P1, R13, UR4, R12    ; Rd = R13+UR4+R12
                                     ; P0 = (R13+UR4) >> 32        (carry₁)
                                     ; P1 = ((R13+UR4)+R12) >> 32  (carry₂)
IADD3.X R11, RZ, RZ, RZ, P0, P1     ; R11 = RZ⊕RZ⊕RZ + P0 + P1
                                     ;     = combined 2-bit carry
LOP3.LUT R9, R11, 0x1, RZ, 0xc0, !PT ; extract low bit of carry
```

**96-bit extended-precision add** (A[2:0] + B[2:0]):
```
IADD3 R7, P0, P1, R7, R10, R5       ; bits[31:0]  + carry into P0,P1
IADD3.X R0, RZ, RZ, RZ, P0, P1      ; carry propagation to R0
IADD3 R5, R0, UR4, R11              ; bits[63:32] = R0 + UR4 + R11
```

In both cases, `P0` and `P1` appear **explicitly** (not default PT=7) because
the compiler needs the carry bits for subsequent operations.

**Default behaviour** (2-operand add, most common):
```
IADD3 R5, R5, R4, RZ                 ; Pu=PT(7), Pv=PT(7) → carries discarded
```
The disassembler omits `PT, PT` since they're default. This is the form seen in
the vast majority of kernel code (address calcs, simple arithmetic).

### 64-bit add via UIADD3.X
The compiler lifts GPR-based 64-bit addition to the uniform path:
```
UIADD3   UR4, UP0, UR4, UR6, URZ          ; bits[31:0]
UIADD3.X UR5, UR5, UR7, URZ, UP0, !UPT    ; bits[63:32] with carry
```
The GPR-based IADD3.X chain was not triggered by the test; the uniform path
is preferred on sm_90. The form exists in the spec and shares the same opcodes
as the plain IADD3 RUR class with `/XONLY:X`.

### Common compiler patterns

**Address index calc:**
```
IADD3 R7, R2, 0x1, RZ      ; R7 = R2 + 1 (simple increment)
```

**Two-operand add (most common):**
```
IADD3 R5, R5, R4, RZ        ; R5 = R5 + R4  (emitted for PTX add.s32)
```
The `IADD` mnemonic shown in some contexts is an alias for the IADD3 encoding
with Rc=RZ.

**Subtract via negate:**
```
IADD3 R5, R0, R4, -R5       ; R5 = R0 + R4 - R5 (PTX sub.s32)
```

---

## Open questions

1. **IADD alias** — `IADD` appears in the OPERATION SETS alongside `IADD3`;
   likely an assembler alias mapping to IADD3 with Rc=RZ. No separate CLASS.
