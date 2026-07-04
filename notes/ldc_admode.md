# LDC `AdMode` — constant-memory addressing modes

**Question:** what do the `AdMode` values `IA / IL / IS / ISL` mean?
**Status:** resolved (spec-grounded + external reference; empirically corroborated).

## Where it lives in the spec
- Enum: `AdMode "IA"=0 , "IL"=1 , "IS"=2 , "ISL"=3;` (a 2-bit field).
- Used **only by `LDC`** — the four classes `ldc__RaNonRZ`, `ldc__RaRZ`,
  `ldc_ur__URRzI`, `ldc_ur__URnonRzI`. FORMAT modifier `/AdMode("IA"):ad`.
- Encodes to **bits [79:78]** (the ENCODING field is literally named `stride`:
  `BITS_2_79_78_stride=ad`).
- Operand shape (non-bindless): `Register:Rd , C:Sa[UImm(5):Sa_bank][NonZeroRegister:Ra + SImm(17):Ra_offset]`
  i.e. `c[bank][Ra + off]`.

## The 2 bits are orthogonal (structural key)
| val | mode | bit1 "S" (indexed) | bit0 "L" (literal) |
|----:|------|:--:|:--:|
| 0 | IA  | . | . |
| 1 | IL  | . | X |
| 2 | IS  | X | . |
| 3 | ISL | X | X |

- bit0 (=1) = **L = literal / unified constant space**
- bit1 (=2) = **S = indexed: bank/offset supplied from a register**
- `ISL == IL | IS` (both); `IA` = neither.

## Meanings
| val | mode | meaning |
|----:|------|---------|
| 0 | IA  | immediate/absolute `c[bank][imm]` — the common case |
| 1 | IL  | immediate-literal in the unified constant space |
| 2 | IS  | indexed — bank/offset taken from a register |
| 3 | ISL | indexed literal (both indexed + literal) |

(Meanings from an external RE reference; every claim below is cross-checked
against the spec's own `CONDITIONS`.)

## Spec corroboration — bank legality tightens as you leave IA
From the `INVALID_CONST_ADDR_LDC` conditions in `ldc__RaNonRZ`/`ldc__RaRZ`:
- **IA** (base, no `ad` guard): banks **0–17 and 24–31** are legal
  (18–23 always forbidden). The 24–31 range is the RTV / driver "run-time value"
  banks → matches "absolute, common case, can reach driver constants".
- **IL / IS / ISL**: restricted to banks **0–17** (`ad in {IL,IS,ISL} -> bank<=0x11`).
- **ISL**: further restricted to banks **0–14** (`ad==ISL -> bank<=0xe`).
- Orthogonal shader rule: `CS` shaders limited to banks **0–7**.

## The 5th mode `IB` (bindless) is NOT an AdMode value on sm_90
An external reference lists a 5th mode `IB` (bindless: bank "header" in a
register, no fixed bank bit). On sm_90 the `AdMode` field has only 4 values;
bindless is a **separate encoding class**, not an `ad` value:
- `ldc_ur__URRzI` / `ldc_ur__URnonRzI`, operand `CX:Sa[UniformRegister:URa][Rb + off]`
  — the constant **bank comes from a uniform register `URa`** (a `CX` bindless-const
  operand), no fixed bank bit.
- These classes **pin `ad = IA`** (condition message:
  "LDC with bindless requires .IA").
- The reference's "OR `(1<<bank)` into a per-program constant-bank reference mask,
  bindless excluded" is a program-header/driver concern outside these two dump
  files, but is consistent: a bindless ref has no static bank to add to the mask.

## Empirical note
Dumped **5.6M lines** of `sm_90` SASS from `libcublas.so.13`
(`cuobjdump -arch sm_90 -sass`): **every** `LDC` is the default IA immediate form
(`LDC[.64/.U8/...] Rd, c[0x0][imm]`). No `.IL/.IS/.ISL` suffix, no register-indexed
address, no bindless `c[UR..]` appeared. So these modes are rare, compiler/driver
-internal (RTV/bindless/driver-constant access) and are not emitted by ordinary
math-library kernels — hence not minable from stock libraries. nvdisasm omits the
default `.IA`; the non-default suffixes would only surface in driver/runtime code.

## Open sub-questions (not yet pinned)
- Exact runtime datapath difference between IA and IS when `Ra` is present in
  both (the spec defines encoding + legality, not micro-semantics). Hypothesis:
  in IS the register selects/indexes the bank slot, whereas in IA `Ra` is a byte
  offset within a fixed bank — unverified.
- What "unified constant space" (the `L` bit) remaps to physically.
