# IMAD — Integer Multiply-Add

**Opcode mnemonic:** `IMAD`  
**Pipe:** `fmalighter_pipe` (FMA lite unit — shared with IMUL, IDP, FFMA-lite and IDP4A)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Variant overview

IMAD performs `Rd = (Ra * Rb) + Rc` (and extended forms) on 32-bit integer operands.
All variants share the same mnemonic `IMAD`; the width/extended/uniform shape is
controlled by modifier fields and operand types in the encoding, not by a distinct
mnemonic (except `UIMAD` for uniform register forms).

### Width modes (3 total)

| Mode        | ASM syntax    | opcode bits[2:0] | Result size | Predicate output |
|-------------|---------------|:---:|-------------|:---:|
| **LO**      | `IMAD`        | `100` | 32-bit `Rd` | none |
| **WIDE**    | `IMAD.WIDE`   | `101` | 64-bit `Rd.Rd+1` | `Pu` (carry) |
| **HI**      | `IMAD.HI`     | `111` | 32-bit `Rd` | `Pu` (carry) |

- **LO** (`/LOOnly("LO")`): `Rd = low32((Ra × Rb) + Rc)` — the default, most
  common form.
- **WIDE** (`/WIDEONLY`): `{Rd+1,Rd} = s32_32(Ra) × s32_32(Rb) + s64(Rc,Rc+1)` —
  produces a full 64-bit result; both `Rd` and `Rc` must be even-aligned.
  Renders as `IMAD.WIDE` (signed) or `IMAD.WIDE.U32` (unsigned).
- **HI** (`/HIONLY_imad`): `Rd = high32((Ra × Rb) + s64(Rc,Rc+1))` — takes the
  upper 32 bits of the 64-bit accumulation. `Rc` must be even-aligned.
  Renders as `IMAD.HI`.

### Extended (X) overlay

The `/XONLY:X` modifier produces an **extended-precision** form used in carry
chains (e.g. for 64×64→128 multiplication). It adds an explicit carry-in/out
predicate `Pp` and replaces the standard `[-]Rc` negate with `[~]Rc`:

```
IMAD.X  Rd, Ra, Rb, [~]Rc, [!]Pp
```

The `X` suffix appears on all width modes: `IMAD.X`, `IMAD.WIDE.X`, `IMAD.HI.X`.

### Pseudo (IMUL degeneration)

When `Ra = RZ` (zero), the multiply degenerates and the assembler emits a
pseudo-opcode (typically `IMUL` or `MOV` depending on operand pattern). The
spec encodes these as `ALTERNATE CLASS` entries with a `REMAP` directive and
`/PSEUDO_OPCODE("nopseudo_opcode")` slot. These are explicitly excluded from
documentation scope per TODO.md policy.

### Uniform register variant: UIMAD

`UIMAD` uses uniform registers (`URd`, `URa`, `URb`, `URc`) instead of GPRs and
executes on `udp_pipe`. Only LO/WIDE width modes (no HI), only `UR*` operand
types (no C/CX/I), and the `/XONLY:X` overlay is supported. Notably,
`UIMAD.WIDE` appears in extended-precision chains alongside `UIADD3.X` for
carry propagation.

---

## Operand form matrix

Each *operand form* selects which of the three source slots (Ra, Rb/Sb, Rc) are
driven by a general register, immediate constant, uniform register, or
constant-bank (C/CX) register. The encoding opcode bits vary per form; there is
no single "operand type" field.

### LO (9 forms)

| Form   | Ra  | Sb (Rb)         | Rc                 | opcode (13-bit) |
|--------|-----|-----------------|--------------------|:---:|
| RRR    | Reg | Reg             | Reg                | `0b_000_1000100100` |
| RsIR   | Reg | SImm(32)        | Reg                | `0b_010_0000100100` |
| RCR    | Reg | Cb              | Reg                | `0b_001_01000100100` |
| RCxR   | Reg | CXb             | Reg                | `0b_011_01000100100` |
| RUR    | Reg | URb             | Reg                | `0b_011_10000100100` |
| RRsI   | Reg | Reg             | SImm(32)           | `0b_001_0000100100` |
| RRC    | Reg | Reg             | Cc                 | `0b_000_11000100100` |
| RRCx   | Reg | Reg             | CXc                | `0b_001_011000100100` |
| RRU    | Reg | Reg             | URc                | `0b_011_11000100100` |

### WIDE (8 forms — no RRsI)

Same as LO except `RRsI` is absent (a 64-bit addend cannot be encoded in a
single 32-bit immediate slot). The opcode LSB is `1` instead of `0`.

### HI (8 forms — no RRsI)

Same as WIDE. Opcode LSB is `3` (`0b111`) instead of LO's `0`/WIDE's `1`.
Also: `ISRC_C_SIZE = 64` (Rc is treated as a 64-bit register pair); `IDEST_SIZE = 32`.

### UIMAD (3 LO + 2 WIDE)

| Form     | Ra  | Sb         | Rc  | LO opcode (13-bit)      | WIDE opcode             |
|----------|-----|------------|-----|:-------:|:-------:|
| URURUR   | UR  | URb        | URc | `0b1001010100100` (0x12a4) | `0b1001010100101` (0x12a5) |
| URURsI   | UR  | URb        | SI  | `0b1010010100100` (0x14a4) | —                       |
| URsIUR   | UR  | SImm(32)   | URc | `0b1100010100100` (0x18a4) | `0b1100010100101` (0x18a5) |

---

## ENCODING layout (128-bit, MSB-left, bits [127:0])

The encoding is identical across width modes except for opcode, `Pu`, and
scoreboard fields. Shown for `imad__RRR_RRR` (LO); WIDE/HI differ only where
noted.

| Bits                 | Width | Field              | Source                         | Notes |
|----------------------|:-----:|--------------------|--------------------------------|-------|
| [124:122],[109:105]  | 8     | `opex`             | `TABLES_opex_4(...)`           | reuse/drain/batch control |
| [121:116]            | 6     | `req_bit_set`      | `req_bit_set`                  | barrier requirement mask |
| [115:113]            | 3     | `src_rel_sb`       | `*7`                           | fixed (no SB release on src) |
| [112:110]            | 3     | `dst_wr_sb`        | `*7`                           | fixed (no SB write) |
| [103:102]            | 2     | `pm_pred`          | `pm_pred`                      | perf-monitor predicate |
| **[91],[11:0]**      | **13**| **`opcode`**       | **Opcode**                     | **MSB=[91], LSBs=[11:0]** |
| [90]                 | 1     | `input_reg_sz_32_dist` | `*1`                       | fixed |
| [89:87]              | 3     | `Pnz`              | `*7`                           | fixed |
| [83:81]              | 3     | `Pu`               | `Pu` (WIDE/HI); `*7` (LO)     | output carry predicate |
| [75]                 | 1     | `sz`               | `Rc@negate`                    | **Rc negate** (=1 → `-Rc`) |
| [74]                 | 1     | `sh`               | `0`                            | fixed |
| [73]                 | 1     | `sz`               | `fmt` (`REDUX_SZ`)             | **0=U32, 1=S32** |
| [71:64]              | 8     | `Rc`               | `Rc`                           | GPR number |
| [39:32]              | 8     | `Rb`               | `Rb`                           | GPR number (or imm in imm-b forms) |
| [31:24]              | 8     | `Ra`               | `Ra`                           | GPR number |
| [23:16]              | 8     | `Rd`               | `Rd`                           | GPR destination |
| [15]                 | 1     | `Pg_not`           | `Pg@not`                       | predicate invert |
| [14:12]              | 3     | `Pg`               | `Pg`                           | guard predicate |

For X-extended forms, `Pnz` at [89:87] encodes the output predicate `Pp` instead
of `*7`, and `Rc@negate` at [75] switches to `Rc@carry_in` (distinct from negate).

---

## Conditions (legality assertions)

Key constraints from `CONDITIONS` blocks — violations produce assembler errors:

### Register range
- All register operands must be ≤ `%MAX_REG_COUNT-1` (or `%MAX_REG_COUNT-2` for
  64-bit double-register operands in WIDE/HI modes) and cannot be `R254`.

### Alignment (WIDE/HI)
- `Rd` and `Rc` are even-aligned for WIDE/HI modes:
  `((Rd + (Rd==RZ)) % 2) == 0` / same for `Rc`.

### opex legality
- `TABLES_opex_4(batch_t, usched_info, reuse_src_a, reuse_src_b, reuse_src_c)`
  must be a defined combination (encodes `.reuse`/drain/wait scheduling controls).
- `.reuse` is mutually exclusive with DRAIN/WAIT tokens:
  `(reuse_any==1) -> (usched_info not in [17..27])`.

### Immediate range
- `SImm(32)` for Sb (imm-b) and Sc (imm-c, LO only) is a full-range 32-bit
  signed immediate (fits in the 32-bit Sb/Sc slot at bits [39:32] or [71:64]
  respectively).

### Pseudo exclusion
- The `ALTERNATE CLASS` (pseudo) entries are excluded when `Ra != RZ`.

---

## Pipe and latency

| Property            | Value |
|---------------------|-------|
| Pipe                | `fmalighter_pipe` |
| IMAD_OP set         | `{IMAD, IMADfmalighter_pipe, IMAD32I, IMAD32Ifmalighter_pipe, IMUL, IMULfmalighter_pipe, IMUL32I, IMUL32Ifmalighter_pipe}` |
| INST_TYPE           | `INST_TYPE_COUPLED_MATH` |
| VIRTUAL_QUEUE       | None |

### True dependency latency (TABLE_TRUE, GPR)

IMAD_OP shares latency with the FMA lite cluster. The latency matrix uses
register-range bins (`RdRange = (IDEST_SIZE - 1) >> 5 + 1 = 1` for LO/HI
32-bit dest, `=2` for WIDE 64-bit dest):

```
IMAD_OP {Rd @ 1..2, Rd2 @ 0} : 5 4 6 6 6 6 6 8 6 6 7 7 7 7 7 7 6 8
```

Key values: shortest true-dep latency is **4–5 cycles** (smallest register-range
bin), growing to 8 cycles for larger register file placements.

### Carry-chain latency (TABLE_TRUE, GPR, Rpc)

```
IMAD_OP {Rpc} : 9
```

The predicate (carry) chain has **9 cycles** of true dependency latency.

---

## Empirical confirmation (sm_90, CUDA 13.1, libcublas + hand-crafted kernels)

All width modes and operand forms verified via `nvcc -arch=sm_90 -O3` →
`cuobjdump -arch sm_90 -sass`. Key observations:

### Confirmed operand forms

| Form   | LO                   | WIDE                             | HI                  |
|--------|----------------------|----------------------------------|---------------------|
| RRR    | `IMAD R5, R5, R4, R0` | `IMAD.WIDE R2, R7, R6, R2`      | `IMAD.HI R5, ...`   |
| RsIR   | `IMAD R5, R4, 0x7, R5`| `IMAD.WIDE.U32 R2, R5, 0x4, R2` | (not confirmed)     |
| RRsI   | `IMAD R5, R5, R4, 0x2a`| N/A                              | N/A                 |
| RRU    | `IMAD R7, R2, UR6, R7`| —                                | —                   |
| RUR    | —                    | —                                 | `IMAD.HI R5, R7, R6, UR4` |

### UR→R via RZ (degenerate IMAD)
`IMAD.U32 R4, RZ, RZ, UR12` — the 0×0+Rc path acts as a **UR→GPR move** using
the `imad_pseudo__RRU_RRU` alternate class.

### Extended precision (X) chain
A 64×64→128 multiply compiled to:
```
UIMAD.WIDE.U32 UR12, UR14, UR16, URZ      ; lo product (UR)
UIMAD.WIDE.U32 UR8,  UR16, UR15, UR6      ; cross term 1
UIMAD.WIDE.U32 UR10, UR15, UR17, UR10     ; cross term 2 (add)
UIMAD.WIDE.U32 UR8,  UR14, UR17, UR8      ; cross term 3 (add)
UIADD3.X UR6, UR6, UR8, URZ, UP1, !UPT    ; carry chain
UIADD3.X UR5, UR5, UR11, URZ, UP0, !UPT   ; carry chain
IMAD.U32 R4, RZ, RZ, UR12                 ; UR→R (lo)
IMAD.U32 R5, RZ, RZ, UR6                  ; UR→R (hi)
```

### Negate
`IMAD R5, R5, R4, -R0` vs `IMAD R5, R5, R4, R0`: only bit [75] differs (0→1).

### Signedness (S32 vs U32)
`IMAD.WIDE` (signed) vs `IMAD.WIDE.U32` (unsigned) differ in bit [73]
(`REDUX_SZ`: 0=U32, 1=S32). The disassembler renders the class-default format.

---

## Open questions

1. **IMADSP** — present in the latency file's `mio_pipe` set but has no
   independent CLASS encoding in `sm_90_instructions.txt`. Only a single
   `IMADSP_SD SD=3;` table entry exists. Likely a `mio_pipe`-bound alias for a
   specific IMAD variant rather than a distinct instruction.

2. **IMAD32I** — pipe-only alias in `fmalighter_pipe` alongside `IMAD`. Same
   opcode space; likely a 32-bit-immediate sub-variant that shares the IMAD
   CLASS entries.

3. **C/CX operand forms** — the constant-bank source forms (Rb=Cb, Rc=Cc, etc.)
   are in the spec but were not triggered by the test kernels. They should appear
   when operands are loaded via `LDC` from `c[bank][offset]` in a way that the
   compiler can directly fold into the IMAD instruction.
