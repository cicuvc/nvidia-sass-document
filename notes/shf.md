# SHF — Funnel Shift

**Opcode mnemonic:** `SHF`  
**Pipe:** `int_pipe` (integer execution pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

Related: `USHF` (uniform register variant, `udp_pipe`, 3 variants).

---

## Variant overview

SHF performs a **funnel shift** (also called double-precision shift): concatenates
two 32-bit registers into a 64-bit pair, shifts the pair by N positions (left or
right), and extracts either the low or high 32-bit half of the result.

`Rd = bits(hilo)( ({Ra, Rc} as 64-bit) shifted by Sb )`

Four modifier axes produce the full set of operations:

| Modifier | Field | Values | Effect |
|----------|-------|--------|--------|
| **Direction** | `SDIR` | `.L`=0, `.R`=1 | left or right shift |
| **Format** | `FMT` | `.U32`=3, `.S32`=2, `.U64`=1, `.S64`=0 | unsigned/logical vs signed/arithmetic |
| **Half-select** | `HILO` | plain=LO=0, `.HI`=1 | which 32-bit half of the 64-bit result |
| **Shift-source** | `CWMode` | `.C`=0 | shift amount from literal/register (constant mode) |

The `.CWMode` is always `C` in observed compiler output. The `W` mode (=1) may
enable wrap/rotate semantics but is not confirmed.

### Common SHF idioms

| SASS | Semantics |
|------|-----------|
| `SHF.L.U32 Rd, Ra, N, RZ` | `Rd = Ra << N` (logical left shift by N) |
| `SHF.L.U32 Rd, Ra, N, Rc` | funnel: `{Ra, Rc} << N`, take low 32 bits |
| `SHF.R.U32 Rd, Ra, N, RZ` | `Rd = Ra >> N` (logical right shift by N) |
| `SHF.R.S32.HI Rd, RZ, N, Rc` | `Rd = (int64_t)Rc >> N` (signed/arithmetic right shift) |
| `SHF.R.S32.HI Rd, RZ, 31, Rc` | `Rd = sign_mask(Rc)` (all 0s or all 1s) |

### Funnel shift semantics (detailed)

The 64-bit input is formed as `{Ra[31:0], Rc[31:0]}` where Ra is the high half
and Rc is the low half.

- **Left shift** (`.L`): `result_64 = {Ra, Rc} << Sb`. Take `Rd = result_64[31:0]` (LO)
  or `Rd = result_64[63:32]` (HI).
- **Right shift** (`.R`): `result_64 = {Ra, Rc} >> Sb`. With `.S32`/`.S64` format,
  the shift is **arithmetic** (fills with sign bit); `.U32`/`.U64` is **logical**
  (fills with zero).

For 2-input simple shifts (e.g. `R9 << 2`), the compiler sets the unused half
to RZ: `SHF.L.U32 R7, R9, 2, RZ` — the zero in Rc means the shifted-in bits are 0.

For sign extension (e.g. computing `sign(R6)`), the compiler uses:
`SHF.R.S32.HI R7, RZ, 31, R6` — funnel `{0, R6}` right 31 with arithmetic shift;
the HI 32 bits become the sign mask.

---

## Operand forms

| Form   | Ra  | Sb (shift amount) | Rc   | opcode (13-bit) |
|--------|-----|:---:|------|:---:|
| RRR    | Reg | Reg (low bits) | Reg | `0b0001000011001` (0x219) |
| RuIR   | Reg | UImm(32) | Reg | `0b0100000011001` (0x819) |
| RRuI   | Reg | Reg | UImm(32) | `0b0010000011001` (0x419) |
| RCR    | Reg | Cb | Reg | `0b0010100011001` (0xa19) |
| RCxR   | Reg | CXb | Reg | `0b0110100011001` (0x1a19) |
| RRC    | Reg | Reg | Cc | `0b0001100011001` (0x619) |
| RRCx   | Reg | Reg | CXc | `0b00101100011001` (0x1619) |
| RRU    | Reg | Reg | URc | `0b0111100011001` (0x1e19) |
| RUR    | Reg | URb | Reg | `0b0111000011001` (0x1c19) |

---

## ENCODING layout (128-bit, MSB-left)

Shown for `shf__RRR_RRR` (register shift amount).

| Bits                | Width | Field            | Source | Notes |
|---------------------|:-----:|------------------|--------|-------|
| [124:122],[109:105] | 8     | `opex`           | `TABLES_opex_4(...)` | |
| [121:116]           | 6     | `req_bit_set`    | `req_bit_set` | |
| [115:113]           | 3     | `src_rel_sb`     | `*7` | |
| [112:110]           | 3     | `dst_wr_sb`      | `*7` | |
| [103:102]           | 2     | `pm_pred`        | `pm_pred` | |
| **[91],[11:0]**     | **13**| **`opcode`**     | **Opcode** | |
| [80]                | 1     | `hilo`           | `hilo` (HILO) | 0=LO, 1=HI |
| **[76]**            | **1** | **`dir`**        | **`dir` (SDIR)** | **0=L, 1=R** |
| [75]                | 1     | `cw`             | `cw` (CWMode) | 0=C |
| **[74:73]**         | **2** | **`fmt`**        | **`fmt` (FMT)** | **0=S64,1=U64,2=S32,3=U32** |
| [71:64]             | 8     | `Rc`             | `Rc` | in high word ([7:0]) |
| [39:32]             | 8     | `Rb`             | `Rb` | shift amount (or Sb in IMM form) |
| [31:24]             | 8     | `Ra`             | `Ra` | |
| [23:16]             | 8     | `Rd`             | `Rd` | |
| [15]                | 1     | `Pg_not`         | `Pg@not` | |
| [14:12]             | 3     | `Pg`             | `Pg` | |

IMM form (0x819): `Rb` at [39:32] is replaced by the 32-bit immediate `Sb` at
[63:32]. `TABLES_opex_3` instead of `_4`.

Note: `Rc` is encoded in the **high word** ([71:64] at positions [7:0]), not
the low word — unlike IMAD/IADD3 where Rc is in the low word at [71:64].

---

## Key differences from LEA

SHF and LEA both perform shift operations, but:
- **SHF** is a funnel shift: `{Ra, Rc} << N` or `>> N`, then extract LO or HI half.
  Two source registers form the 64-bit input.
- **LEA** is a shift-add: `(Ra << N) + Rb (+ Rc)`. One register shifted, then added.
  Purposely designed for address calculation.
- SHF has `.HI` and `.U32`/`.S32` modifiers; LEA has `.HI`/`.X`/`.SX32`.
- The compiler uses SHF for pure shift operations and LEA for shift+add.

---

## Conditions

- Standard register-range checks
- No negate/invert bits (SHF has none)
- `TABLES_opex_4` (RRR) or `_3` (IMM)

---

## Pipe and latency

| Property | Value |
|----------|-------|
| Pipe | `int_pipe` |
| OPERATION SET | `{SHF, SHFint_pipe}` |
| INST_TYPE | `INST_TYPE_COUPLED_MATH` |

Shares the FXU latency matrix.

---

## Empirical confirmation (sm_90, CUDA 13.1)

All observed SHF patterns used `CWMode=C` and the IMM form (opcode 0x819).

| SASS | Semantics | dir | fmt | hilo |
|------|-----------|:---:|:---:|:---:|
| `SHF.L.U32 R7, R9, 0x2, RZ` | `R7 = R9 << 2` | L | U32 | LO |
| `SHF.L.U32 R7, R9, 0x3, RZ` | `R7 = R9 << 3` | L | U32 | LO |
| `SHF.R.S32.HI R7, RZ, 0x1f, R6` | `R7 = sign_extend(R6 >> 31)` | R | S32 | HI |

### Compiler pattern: simple power-of-2 multiplication

The compiler prefers `SHF.L.U32` over `IMAD` for pure shifts:
```
SHF.L.U32 R7, R9, 3, RZ       ; R7 = R9 << 3  (= R9 * 8)
IMAD.WIDE.U32 R2, R7, 4, R4   ; R2 = R7*4 + R4 (address calc)
```

### Compiler pattern: sign mask extraction

```
SHF.R.S32.HI R7, RZ, 0x1f, R6   ; R7 = all 1s if R6 < 0, else all 0s
```

This is used in the `lea_hi_ext` test as part of a 64-bit signed shift-add
chain. The sign mask is then consumed by `LEA.HI.X.SX32` as a carry/bias input.

---

## USHF: uniform register variant

USHF operates on `UniformRegister` with `udp_pipe`. 3 variants: URURUR, URURuI,
URuIUR. Same modifier axes (SDIR, CWMode, FMT, HILO). Opcodes: `0x1299`, `0x1499`,
`0x1899`.
