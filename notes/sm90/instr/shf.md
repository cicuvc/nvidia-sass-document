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

`Rd = bits(hilo)( ({Rc, Ra} as 64-bit) shifted by Sb )`

The funnel is `{Rc, Ra}`: **Rc is the high 32 bits, Ra is the low 32 bits**
(PTX `shf` operand order: SASS `Ra` == PTX `a`, SASS `Rc` == PTX `b`). This is
the opposite of the older "Ra high / Rc low" prose — corrected below using
ptxas-generated code (verified sm_90 + sm_120, CUDA 12.8).

Four modifier axes produce the full set of operations:

| Modifier | Field | Values | Effect |
|----------|-------|--------|--------|
| **Direction** | `SDIR` | `.L`=0, `.R`=1 | left or right shift |
| **Format** | `FMT` | `.U32`=3, `.S32`=2, `.U64`=1, `.S64`=0 | U=logical vs S=arithmetic; **32-formats clamp the amount at 32, 64-formats use 0–63** (see below) |
| **Half-select** | `HILO` | plain=LO=0, `.HI`=1 | which 32-bit half of the 64-bit result |
| **Shift-source** | `CWMode` | `.C`=0, `.W`=1 | amount semantics: `.C` = 0–63 (64-formats) or clamped at 32 (32-formats); `.W` = wrap at 32 (`amount & 0x1f`) |

`.C` (default) uses the amount as-is — **but the effective range depends on the
format** (verified on SM120, RTX 5090):
- `U64`/`S64`: full 6-bit amount, 0–63 (64-bit shift).
- `U32`/`S32`: amount **clamped at 32**, i.e. `min(amount, 32)` (32-bit shift;
  the funnel is still the full 64-bit `{Rc, Ra}`).

`.W` wraps the amount at 32 (`amount & 0x1f`). ptxas emits `.C` + `U64`/`S64`
for 64-bit shifts (`v >> k` with k up to 63) and `.W` for rotate idioms (where
the raw, unmasked amount must wrap mod 32).

### Common SHF idioms

| SASS | Semantics |
|------|-----------|
| `SHF.L.U32 Rd, Ra, N, RZ` | `Rd = Ra << N` (logical left shift by N) |
| `SHF.L.U32 Rd, Ra, N, Rc` | funnel: `{Rc, Ra} << N`, take low 32 bits |
| `SHF.R.U32 Rd, Ra, N, RZ` | `Rd = Ra >> N` (logical right shift by N) |
| `SHF.R.U32.HI Rd, RZ, N, Rc` | `Rd = Rc >> N` (compiler form for unsigned right shift; value in Rc) |
| `SHF.R.S32.HI Rd, RZ, N, Rc` | `Rd = (int32_t)Rc >> N` (arithmetic; sign-fills from Rc[31]) |
| `SHF.R.S32.HI Rd, RZ, 31, Rc` | `Rd = sign_mask(Rc)` (all 0s or all 1s) |

### Funnel shift semantics (detailed)

The 64-bit input is formed as `{Rc[31:0], Ra[31:0]}` where **Rc is the high
half and Ra is the low half**.

- **Left shift** (`.L`): `result_64 = {Rc, Ra} << Sb`. Take `Rd = result_64[31:0]` (LO)
  or `Rd = result_64[63:32]` (HI).
- **Right shift** (`.R`): `result_64 = {Rc, Ra} >> Sb`. With `.S32`/`.S64` format,
  the shift is **arithmetic** (fills with sign bit); `.U32`/`.U64` is **logical**
  (fills with zero).

For 2-input simple shifts the compiler puts the value in the funnel half that
matters and RZ in the other:
- `R9 << 2` → `SHF.L.U32 R7, R9, 2, RZ` — value in Ra (low half), Rc=RZ.
- `R9 >> 2` (unsigned) → `SHF.R.U32.HI R7, RZ, 2, R9` — value in Rc (high
  half), Ra=RZ, take HI.
- `R9 >> 2` (signed) → `SHF.R.S32.HI R7, RZ, 2, R9` — same shape, arithmetic.

The two halves of a real 64-bit shift are then two SHFs with the same funnel
`{hi, lo}`: e.g. `v >> k` for `v = (hi<<32)|lo` lowers to
`SHF.R.U64 Rd, lo, k, hi` (low word) plus `SHF.R.U32.HI Rd, RZ, k, hi` (high
word) combined with the carry-in bits — this is also the direct proof that
`Rc` is the high half.

For sign extension (e.g. computing `sign(R6)`), the compiler uses:
`SHF.R.S32.HI R7, RZ, 31, R6` — funnel `{R6, 0}` arithmetic right 31; the HI
32 bits become the sign mask of R6.

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
the low word — unlike IMAD/IADD3 where Rc is in the low word at [71:64]. This
matches the funnel role: Rc (high half) sits in the word with the opcode
extension bits.

---

## Key differences from LEA

SHF and LEA both perform shift operations, but:
- **SHF** is a funnel shift: `{Rc, Ra} << N` or `>> N`, then extract LO or HI half.
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

All observed compiler patterns use the uniform-amount form (`SHF.* Rd, Ra, URn, Rc`)
or the immediate form (opcode 0x819); CWMode is `.C` for 64-bit shifts and `.W`
for rotate/wrap idioms.

| SASS | Semantics | dir | fmt | hilo |
|------|-----------|:---:|:---:|:---:|
| `SHF.L.U32 R7, R9, 0x2, RZ` | `R7 = R9 << 2` | L | U32 | LO |
| `SHF.L.U32 R7, R9, 0x3, RZ` | `R7 = R9 << 3` | L | U32 | LO |
| `SHF.R.S32.HI R7, RZ, 0x1f, R6` | `R7 = sign_extend(R6 >> 31)` | R | S32 | HI |

Additional ptxas vectors (CUDA 12.8, `nvdisasm -hex`; sm_90 and sm_120 emit
identical instruction fields):

| SASS | Proven computation |
|------|--------------------|
| `SHF.R.U64 R8, R2, k, R3` | `low32(v >> k)` for `v = (R3<<32)|R2` → Rc=R3 is the high half |
| `SHF.L.U32 R4, R2, k, RZ` | `low32(v << k)` low word = `R2 << k` |
| `SHF.L.U64.HI R5, R2, k, R3` | `high32(v << k)` → Rc=R3 high, Ra=R2 low |
| `SHF.R.S64 R10, R2, k, R3` | `low32(sv >> k)` arithmetic (sv = (R3<<32)|R2 signed) |
| `SHF.R.S32.HI R11, RZ, k, R3` | `high32(sv >> k)` arithmetic |
| `SHF.L.W.U32.HI R7, R0, n, R3` | rotate/wrap; `.W` = amount `& 0x1f` (raw n) |

### Format-boundary confirmation (SM120, `tests/asm_construct/test_shf.py`)

49-case GPU battery (RTX 5090, all OK) pins the 32-vs-64 format difference at
the amount boundary — the funnel and HI/LO selection are identical, only the
amount semantics differ:

| Probe | Result | Reading |
|-------|--------|---------|
| `SHF.R.U32 Rd, A, 0x28, B` vs `SHF.R.U64 Rd, A, 0x28, B` | `B` vs `B >> 8` | U32 clamps k=40 → 32; U64 shifts 40 |
| `SHF.R.S32 Rd, A, 0x28, B` vs `SHF.R.S64 Rd, A, 0x28, B` (neg funnel) | identical (`0xffffffff`) | both arithmetic; same funnel |
| `SHF.R.S32 Rd, A, 0x10, B` (A≠RZ) vs `SHF.R.S64` | identical | S32 arithmetic applies to the full 64-bit funnel, not a sign-extended 32-bit one |
| `SHF.L.W.*` at k=0x20/0x23 | equals k=0 / k=3 | `.W` = amount `& 0x1f` |
| `SHF.*.U64` at k=0,1,31,32,40,63 (both halves/directions) | match full-64 model | `.C` + 64-format = 0–63 |

So `.U32`/`.S32` are NOT aliases of `.U64`/`.S64`: the 32-bit formats restrict
the shift to a 32-bit window (clamp at 32), which is why ptxas uses the 64-bit
formats whenever the amount may exceed 31 (e.g. the low word of `v >> k`).

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

## Open questions

Resolved on SM120 (RTX 5090) via `tests/asm_construct/test_shf.py` (49 cases,
all pass):

- **U32 vs U64 / S32 vs S64 are not aliases.** The 32-formats clamp the amount
  at 32 (`min(k,32)`); the 64-formats use the full 6-bit amount (0–63). The
  funnel `{Rc,Ra}`, HI/LO selection, and U/S (logical/arithmetic) behavior are
  identical between the pairs.
- **`.S32` with a non-RZ `Ra`** behaves exactly like `.S64`: arithmetic shift
  of the full 64-bit funnel (sign = `Rc[31]`), verified with both funnel halves
  nonzero at k=16 and k=40.
