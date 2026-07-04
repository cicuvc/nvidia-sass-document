# LEA — Load Effective Address (Shift-Add)

**Opcode mnemonic:** `LEA`  
**Pipe:** `int_pipe` (integer execution pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

Related: `ULEA` (uniform register variant, `udp_pipe`, 14 variants).

---

## Variant overview

LEA computes `Rd = (Ra << N) + Rb (+ Rc)` where `N` is a 5-bit unsigned
immediate scale (0..31). It has two width modes and an X-overlay, plus an SX32
sign-extension mode.

| Mode       | ASM format | Rc | Semantics |
|------------|-----------|:---:|-----------|
| **LO**     | `LEA Rd, Pu, [-]Ra, [-]Rb, N` | fixed `RZ` | `Rd = low32((Ra << N) + Rb)` |
| **HI**     | `LEA.HI Rd, Pu, [-]Ra, [-]Rb, Rc, N` | register | `Rd = high32((Ra << N) + Rb + Rc)` |
| **HI.X**   | `LEA.HI.X Rd, Pu, [~]Ra, [~]Rb, N, [!]Pp` | fixed `RZ` | extended-precision HI with carry-in |
| **HI.X.SX32** | `LEA.HI.X.SX32 Rd, Pu, [~]Ra, [~]Rb, N, [!]Pp` | fixed `RZ` | sign-extended HI.X |

- **LO** (`/LOOnly`): 2-source operation. The shift produces `Ra << N`, then adds
  `Rb`. Rc is hardwired to 0. The intermediate result is 64-bit but only the low
  32 bits are written to `Rd`. `ISRC_C_SIZE = 0`.
- **HI** (`/HIONLY`): 3-source operation. Same as LO but adds `Rc` (32-bit
  register) and writes the *high* 32 bits to `Rd`. `ISRC_C_SIZE = 32`.
- **X** (`/XONLY`): extended precision. Sources use `[~]` (invert) instead of
  `[-]` (negate). `Pp` provides carry-in/out. Rc is fixed to `RZ`.
- **SX32** (`/SX32ONLY`): sign-extends the intermediate 64-bit result
  (used for signed 32→64 widening shift-add).

### Pu: carry output predicate

Like IADD3, LEA uses `Pu` as a predicate output slot typed `Predicate("PT")` with
default PT=7 (discard). When non-default, it captures the carry bit from the
addition `(Ra << N) + Rb`. In LO mode, this is the overflow from the 64-bit
intermediate.

---

## Operand forms

| Form   | Ra  | Sb               | Rc   | opcode (13-bit) |
|--------|-----|------------------|------|:---:|
| RRR    | Reg | Reg              | Reg (HI) / RZ (LO) | `0b0001000010001` (0x211) |
| RuIR   | Reg | UImm(32)         | Reg (HI) / RZ (LO) | `0b0100000010001` (0x811) |
| RRuI   | Reg | Reg              | UImm(32) | `0b0001000010001` (0x411) |
| RCR    | Reg | Cb               | Reg (HI) / RZ (LO) | `0b0010100010001` (0xa11) |
| RCxR   | Reg | CXb              | Reg (HI) / RZ (LO) | `0b0110100010001` (0x1a11) |
| RUR    | Reg | URb              | Reg (HI) / RZ (LO) | `0b0111000010001` (0x1c11) |

LO and HI share opcodes; the `/LOOnly` vs `/HIONLY` modifier at bit [80] distinguishes them.

---

## ENCODING layout (128-bit, MSB-left)

Shown for `lea_lo_noimm__RRR_RRR` (LO); HI differs in Rc and opex.

| Bits                | Width | Field            | Source | Notes |
|---------------------|:-----:|------------------|--------|-------|
| [124:122],[109:105] | 8     | `opex`           | `TABLES_opex_5(L)` / `_4(H)` | LO has 2 src |
| [121:116]           | 6     | `req_bit_set`    | `req_bit_set` | |
| [115:113]           | 3     | `src_rel_sb`     | `*7` | |
| [112:110]           | 3     | `dst_wr_sb`      | `*7` | |
| [103:102]           | 2     | `pm_pred`        | `pm_pred` | |
| **[91],[11:0]**     | **13**| **`opcode`**     | **Opcode** | |
| [90]                | 1     | `Pp_not`         | `*1` (plain) / `Pp@not` (X) | |
| [89:87]             | 3     | `Pnz`            | `*7` (plain) / `Pp` (X) | carry-in pred (X) |
| [83:81]             | 3     | `Pu`             | `Pu` | **carry output** |
| [80]                | 1     | `hilo`           | `*hilo` | **0=LO, 1=HI** |
| **[79:75]**         | **5** | **`scaleU5`**    | **scaleU5** | **shift amount (0–31)** |
| [74]                | 1     | `sh`             | `0` | |
| [73]                | 1     | `sz`             | `0` | |
| [72]                | 1     | `e`              | `Ra@negate` (plain) / `Ra@invert` (X) | |
| [71:64]             | 8     | `Rc`             | `*255` (LO) / `Rc` (HI) | RZ=0xFF in LO |
| [63]                | 1     | `Sb_invert`      | `Rb@negate` (plain) / `Rb@invert` (X) | |
| [39:32]             | 8     | `Rb`             | `Rb` | |
| [31:24]             | 8     | `Ra`             | `Ra` | |
| [23:16]             | 8     | `Rd`             | `Rd` | |
| [15]                | 1     | `Pg_not`         | `Pg@not` | |
| [14:12]             | 3     | `Pg`             | `Pg` | guard predicate |

The `*255` encoding for Rc in LO mode corresponds to register 0xFF (RZ).

---

## Key differences from IMAD/IADD3

| Feature | LEA | IMAD | IADD3 |
|---------|-----|------|-------|
| Operation | `(Ra<<N) + Rb (+ Rc)` | `(Ra×Rb) + Rc` | `Ra + Rb + Rc` |
| Scale/shift | 5-bit immediate (0–31) | N/A | N/A |
| LO mode | 2-source, Rc=RZ | 32-bit result | N/A |
| HI mode | 3-source, high half | high half of multiply | N/A |
| SX32 | Sign-extend 32→64 | N/A | N/A |
| Pu | carry from `(Ra<<N)+Rb` | carry from multiply (HI/WIDE) | 2-bit carry from triple add |
| HI has Rc | Yes (3-source) | Yes (3-source) | N/A |

---

## Conditions

- Standard register-range checks
- `(Ra@negate) → ¬(Rb@negate)` — no simultaneous negate
- `TABLES_opex_5` for LO (2 sources + scale), `TABLES_opex_4` for HI (3 sources)

---

## Pipe and latency

| Property | Value |
|----------|-------|
| Pipe | `int_pipe` |
| OPERATION SET | `{LEA, LEAint_pipe}` |
| INST_TYPE | `INST_TYPE_COUPLED_MATH` |

Shares the FXU latency matrix with IADD3/LOP3.

---

## Empirical confirmation (sm_90, CUDA 13.1)

### Basic LEA (compiler-generated)

The `lea_3src` test (`(a[idx]*16) + b[idx] + c[idx]`) produced:
```
LEA R0, R2, R5, 0x4      ; R0 = (R2 << 4) + R5 (= a*16 + b)
IADD3 R11, R0, R7, RZ    ; R11 = R0 + R7 (= result + c)
```

The compiler uses LEA for the `(a << 4) + b` part, then chains IADD3 for the
third addend. LEA is NOT used for pure address index multiplication (the
compiler prefers `SHF.L.U32` + `IMAD.WIDE.U32` for `idx * stride` patterns).

### LEA.HI.X.SX32 with IADD3 carry generator

The `lea_hi_ext` kernel triggered a sophisticated pattern for computing
`high32((a << 3) + b + c)`:
```
SHF.R.S32.HI R7, RZ, 0x1f, R6       ; R7 = sign_extend(R6)  (>>31)
IMAD.WIDE R6, R3, 0x8, R6            ; R6 = R3*8 + R6_lo
IADD3 RZ, P0, R6, R9, RZ             ; discard result, capture carry→P0
LEA.HI.X.SX32 R7, R9, R7, 0x1, P0    ; R7 = high32_sx((R9<<1) + R7) + P0
```

This is a remarkable chain:
1. `SHF.R.S32.HI` sign-extends an input (right-shift by 31)
2. `IMAD.WIDE` computes `a*8 + c_lo`
3. `IADD3 RZ, P0, R6, R9, RZ` — **pure carry generation**. The result goes to
   RZ (discarded), but the overflow is captured in P0. This confirms both:
   - IADD3's Pu as a carry output
   - Rd=RZ as a valid "discard result, keep carry" encoding
4. `LEA.HI.X.SX32` uses P0 as carry-in, computing the high 32 bits of the
   signed shift-add with sign extension.

### Common vs rare

LEA is **relatively rare** in typical compiler output — the compiler strongly
prefers `SHF` + `IMAD.WIDE` + `IADD3` chains over LEA for most indexing
patterns. LEA.HI.X.SX32 appears only in specialized big-int arithmetic.
This may be because LEA has only a 5-bit shift immediate (0–31), and for
many address-calc patterns the compiler can fuse shift+add into IMAD.WIDE.U32
with a 32-bit stride immediate.

---

## ULEA: uniform register variant

ULEA operates on `UniformRegister` with `udp_pipe`. 14 variants covering
LO/HI/imm/x/sx32 modes. Same opcode space pattern (e.g., `0x1491`, `0x1891`).
ULEA.HI.X.SX32 is structurally identical to its LEA counterpart but with UR
operands.
