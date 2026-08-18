# FFMA — FP32 Fused Multiply-Add

**Opcode mnemonic:** `FFMA`  
**Pipe:** `fmalighter_pipe` (= `FMAI_OPS`)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd = Ra * Rb + Rc` — three-operand fused multiply-add on 32-bit floats.

Each source operand supports optional **negate** (`-`) and **absolute** (`||`) modifiers via
the sign-control bits in the encoding (see Bit layout below). RZ (register 0xFF) reads as 0.0;
writing RZ discards the result.

## Variant overview — 9 encoding variants

| Variant | Opcode (13b) | Operand C | Operand B | C size |
|---------|:-----------:|-----------|-----------|:------:|
| `ffma__RRR_RRR` | 0x223 | Register | Register | 32 |
| `ffma__RRI_RRI` | 0x423 | F32Imm | Register | 32 |
| `ffma__RRC_RRC` | 0x623 | Const bank | Register | 32 |
| `ffma__RRCx_RRCx` | 0x1623 | Const bank + UR | Register | 64 |
| `ffma__RIR_RIR` | 0x823 | Register | F32Imm | 32 |
| `ffma__RCR_RCR` | 0xa23 | Register | Const bank | 32 |
| `ffma__RCxR_RCxR` | 0x1a23 | Register | Const bank + UR | 32 |
| `ffma__RUR_RUR` | 0x1c23 | Register | UniformRegister | 32 |
| `ffma__RRU_RRU` | 0x1e23 | UniformRegister | Register | 32 |

Variant naming: each letter denotes the CBA operand type (`R`=Register, `I`=F32Imm,
`C`=Const bank, `Cx`=Const+UR, `U`=UniformRegister). Opcode = 13 bits ([91]∥[11:0]).

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **fmz** | [80],[76] | `nofmz_hfma2`(0), `FMZ`(1), `FTZ`(2), `INVALID3`(3) |
| **rnd** (rounding) | [79:78] | `RN`(0), `RM`(1), `RP`(2), `RZ`(3) |
| **sat** (saturation) | [77] | `nosat`(0), `SAT`(1) |

- `.RM`, `.RP`, `.RZ`, `.SAT`, `.FTZ` appear as suffixes in disassembly.
- `fmz=INVALID3` triggers `ILLEGAL_INSTR_ENCODING_ERROR`.
- `.reuse` is encoded via `TABLES_opex_*` in the `opex[8]` field; disallowed with
  `?DRAIN` / `?WAITn_END_GROUP`.

## Bit layout (RRR_RRR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b: batch_t, usched_info, reuse)
[121:116]               req_bit_set  (6b: REQ barrier)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 92: 90],[89:81]       -- gap --
[91],[11:0]             opcode       (13b)
[80],[76]               fmz          (2b)
[79:78]                 stride       (2b: rounding)
[77]                    ntz          (1b: sat)
[75]                    Rc.negate
[74]                    Rc.absolute
[73]                    Ra.absolute
[72]                    Ra.negate
[71:64]                 Rc           (8b)
[63]                    Rb.negate
[62]                    Rb.absolute
[61:40]                 -- gap --
[39:32]                 Rb           (8b)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not
[14:12]                 Pg           (3b: predicate, 7=PT)
[10:4]                  -- gap --
[3:0]                   -- gap --
```

### Variant differences

- **RRI** (imm Sc): Rb→[71:64], no Rc; Sc F32Imm in [63:32]
- **RIR** (imm Sb): Rc→[71:64], no Rb; Sb F32Imm in [63:32]
- **RRU** (URc): Rb→[71:64]; URc in [37:32] (6-bit uniform reg); URc negate/abs in [63:62]
- **RUR** (URb): Rc→[71:64]; URb in [37:32]; URb negate/abs in [63:62] (opcode differs)

## Latency (from sm_90_latencies.txt)

FFMA belongs to `FMAI_OPS` (= `fmalighter_pipe`, excl. IMAD). FFMA itself is in
`FMAI_WITHOUT_IMAD`:

| Dependency | Pipe group × operand role | Cycles |
|-----------|--------------------------|:------:|
| TABLE_TRUE | `FMAI_WITHOUT_IMAD`{Rd} | 4–8 |
| TABLE_OUTPUT | `FMAI_OPS`{Rd} | 1–2 |
| TABLE_ANTI | `FMAI_OPS`{Ra,Rb,Rc} | 1–2 |

Occupancy: `FMAI_Occupancy [2]`.

### Empirical latency & throughput (SM120, 2026-08)

Same harness as the MUFU measurements (`test_mufu_latency.py` /
`test_mufu_throughput.py`; `tests/asm_construct/test_ffma_throughput.py`):

- **Dependent-chain latency**: FFMA ≈ 5.44 cyc (writeback via scoreboard
  wait), consistent with TABLE_TRUE's 4–8.
- **Independent-chain throughput**: FFMA / FMUL / FADD / neg / imm variants
  all measure **6.18 cyc/op — identical to the NOP baseline** (delta ≈ 0).
  The ~6.2-cyc baseline is the single-warp instruction-issue floor; FFMA
  rides it with **zero marginal cost**.  This contrasts with MUFU, which
  adds **+2.01 cyc/op** over the same baseline (the mio/SFU pipe is the
  throughput bottleneck; the fmalighter/FMA pipe is not — it accepts far
  more than 1 op/cycle, so a single warp's issue rate saturates it).

## Verified encodings (cuobjdump, sm_90)

All 12 test vectors decoded correctly against cuobjdump disassembly.
Test kernel: `tests/ffma_test.cu`; decoder: `tools/decode_ffma.py`.

| Source | Hex (lo64 / hi64) | Disassembly |
|--------|-------------------|-------------|
| kernel | `0x4000000005057823` / `0x001fe20000000000` | FFMA R5, R5, 2, R0 (RIR) |
| kernel | `0x4040000004057423` / `0x001fc60000000005` | FFMA R5, R4, R5, 3 (RRI) |
| kernel | `0x8000000604057e23` / `0x001fe20008000005` | FFMA R5, R4, R5, -UR6 (RRU) |
| kernel | `0x0000000604057e23` / `0x001fc60008000105` | FFMA R5, -R4, R5, UR6 (RRU) |
| kernel | `0x0000000604057e23` / `0x001fe20008004005` | FFMA.RM R5, R4, R5, UR6 |
| kernel | `0x0000000604057e23` / `0x001fe20008008005` | FFMA.RP R5, R4, R5, UR6 |
| kernel | `0x0000000604057e23` / `0x001fe2000800c005` | FFMA.RZ R5, R4, R5, UR6 |
| kernel | `0x0000000604057e23` / `0x001fe20008000005` | FFMA R5, R4, R5, UR6 (plain) |
| kernel | `0x0000000604057e23` / `0x001fe20008002005` | FFMA.SAT R5, R4, R5, UR6 |
| kernel | `0x0000000604057e23` / `0x001fe20008010005` | FFMA.FTZ R5, R4, R5, UR6 |
| kernel | `0x0000000302057223` / `0x001fe200000000ff` | FFMA R5, R2, R3, RZ (RRR) |
| cublas | `0x0000000912130223` / `0x040fe2000000081a` | @P0 FFMA R19, R18, R9, -R26 (RRR) |

Key observations from compiler output:
- Compiler prefers **RRU** over RRR when operands are loaded via `ULDC` (uniform reg)
- `__fmul_rn(a,b)+c` splits into **FMUL+FADD** — no FFMA fusion there
- `a*b+0.0f` → FFMA with RZ (FFMA R5, R2, R3, RZ), still RRR
- PTX `fma.rz.f32` / `fma.rm.f32` / `fma.rp.f32` / `fma.ftz.f32` map directly to FFMA
  with the corresponding suffix via the `rnd`/`fmz` modifier bits

## Open questions

- `.reuse` flag not yet tested (requires paired consumer instructions)
- Const-bank variants (RRC, RRCx, RCR, RCxR) not yet verified with test kernel
- `FFMA32I` (pipe-only alias) relationship to FFMA not fully explored

## Resolved (SM120 bit-level verification, 2026-08)

`tests/asm_construct/test_ffma.py` + `fma_ref.py` (big-integer exact-sum FMA)
verified the full rounding model against real hardware; **160/160 cases OK**
(120 random vectors × RN/RM/RP/RZ/FTZ + 40 structured). Cross-validated
against an independent Fraction-based rounder (20k vectors/mode).

### Rounding modes — bit-level (`stride` [79:78] = RN:0 RM:1 RP:2 RZ:3)

The exact sum `Ra*Rb+Rc` (48-bit product, exact add) is rounded **once** to
the binary32 grid, matching IEEE 754-2019 §4.3.3 exactly:

| case | exact sum (ULP units) | RN | RM | RP | RZ |
|------|-----------------------|----|----|----|----|
| tie-even | 1.5 (tie) | up **to even** | down | up | down |
| subhalf | 1.25 | down | down | up | down |
| abvhalf | 1.75 | up | down | up | down |

- **Ties** resolve to the *even* mantissa (RN); a `tie-even` upper candidate
  stays down (0x3f800003) when the lower one is already even.
- **Overflow** (`|sum| ≥ 2^128`): RN/RP → ±inf; RM/RZ → clamp to ±max-finite
  (0x7f7fffff / 0xff7fffff). The exact `maxfinite + 1 ULP = 2^128` edge
  rounds to inf under RN, max-finite under RM/RZ.
- **Zero-sum sign** (§5.4.2): exact cancellation `a*b == -c` → +0, except
  **-0 under RM**; `+0 + -0` → +0 (RN/RZ/RP), -0 (RM). Verified bit-exact.
- **Underflow** below the denormal grid (e.g. `2^-149 * 2^-149`) → +0 even
  without FTZ (round-to-nearest of 2^-298).

### Fusion is real (single rounding)

The 48-bit exact product participates in the final round. `a=b=2^23+1`,
`c=2^22` (half-ULP): exact sum = `2^46 + 2.5 ULP + 1` → RN rounds **up**
(0x56800003). A separate FMUL then FADD rounds the product first
(`2^46+2^24`), then the +c lands exactly on the tie → stays at
0x56800002. **1 ULP apart** — direct proof FFMA is not FMUL+FADD.
(64 such vectors found; see `test_ffma.py` `fusion`/`fusion2`.)

### Denormals + flush modifiers (`fmz` bits [80],[76]: nofmz:0 FMZ:1 FTZ:2)

- **Plain FFMA preserves denormal inputs AND denormal results** on SM120
  (e.g. `2^-149` propagates; `2^-63 * 2^-86 = 2^-149` stays denormal).
- **`.FTZ` flushes** all three denormal inputs (multiplier + addend)
  sign-preserving and the subnormal result sign-preserving; exact +/-0
  results keep the IEEE zero-sum sign (verified matrix on sm120: a negative
  subnormal result flushes to -0 under every rounding mode, e.g.
  `-2^-126 * +2^-126` → 0x80000000).
- **`.FMZ` is NOT behaviourally identical to `.FTZ` on SM120** (corrected
  during the 2026-08-17 GPU differential rerun; verified by a 288-combo
  modifier sweep + directed probes):
  - The denormal **multiply inputs** (a, b) flush to **positive zero** — the
    multiply path's zero is sign-neutral (e.g. `FFMA.FMZ(-1.0, +den, +0)`
    under RM is +0, whereas a genuine data product `-1.0 * +0` would be -0).
  - The denormal **addend** (c) flushes sign-preserving (discriminator:
    `2^-63*2^-63 + 3*2^-149` → plain 0x00800003, FTZ/FMZ 0x00800000).
  - A **subnormal product is kept uncollapsed** in the fused sum (only the
    addend and result are flushed): `2^-126 * 2^-126 + (-2^-149)` flushes to
    +0, not -0.
  - A subnormal **result** flushes sign-preserving (`-2^-150` → -0 in every
    mode).
  - An **exact zero-product + zero-addend sum** takes the addend's sign
    under RM and +0 otherwise (the product zero's sign is dropped).
  `.FMZ` has no PTX equivalent and appears only in SASS.

### NaN canonicalization

All NaN-producing FFMA inputs (payload/sign NaN, `inf*0`, `inf + -inf`)
produce the canonical **0x7fffffff** (positive, all-ones mantissa) on SM120 —
not 0x7fc00000. PTX ISA says single-precision NaN is unspecified; empirically
it is always 0x7fffffff for FFMA.

### Assembler note

The SASS `.RZ` rounding modifier required a parser fix (the lexer reads `RZ`
as a register token, so `.RZ` failed; `sass_parser.py` now accepts a `REG`
token text "RZ" as a mnemonic modifier). `FFMA.RZ`, `FFMA.RZ.FTZ`, and the
`0fXXXXXXXX` F32-imm RRI form all assemble correctly.

