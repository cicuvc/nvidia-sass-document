# MUFU — Multi-Function Unit

**Opcode mnemonic:** `MUFU`  
**Pipe:** `mio_pipe` (memory/IO pipe — **not** the math pipe!)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`  
**VIRTUAL_QUEUE:** `$VQ_MUFU`

---

## Semantics

`Rd = Op(Rb)` — single-operand transcendental/special-function unit.
Takes one 32-bit source operand (Rb) and produces a 32-bit result (Rd).
No source A operand (`ISRC_A_SIZE = 0`).

Uses **variable-latency scoreboard** (`VarLatOperandEnc` — latency depends on
the specific operation and operand value).

## Variant overview — 5 base + 5 fp16 = 10 variants

### Base variants (FP32 operations)

| Variant | Opcode | Source B |
|---------|:------:|----------|
| `mufu__RRR_RR` | 0x308 | Register |
| `mufu__RIR_RI` | 0x908 | F64Imm |
| `mufu__RCR_RC` | 0xb08 | Const bank |
| `mufu__RCxR_RCx` | 0x1b08 | Const bank + UR |
| `mufu__RUR_RU` | 0x1d08 | UniformRegister |

### fp16 variants (same opcodes, different format interpretation)

Same 5 opcodes but with `FMT_F16_BF16` enum to select F16/BF16 format and
`MUFUOP_COS_SIN_EX2_LG2_RCP_RSQ_SQRT_TANH` enum (no RCP64H/RSQ64H).

## Operations (MUFU_OP enum)

| Value | Name | Description | PTX |
|:-----:|------|-------------|-----|
| 0 | `COS` | Cosine (approx) | `cos.approx.ftz.f32` |
| 1 | `SIN` | Sine (approx) | `sin.approx.ftz.f32` |
| 2 | `EX2` | 2^x (approx) | `ex2.approx.ftz.f32` |
| 3 | `LG2` | log2(x) (approx) | `lg2.approx.ftz.f32` |
| 4 | `RCP` | 1/x (approx) | `rcp.approx.ftz.f32` |
| 5 | `RSQ` | 1/sqrt(x) (approx) | `rsqrt.approx.ftz.f32` |
| 6 | `RCP64H` | Double-precision reciprocal helper | `rcp64h.approx.f64` |
| 7 | `RSQ64H` | Double-precision rsqrt helper | `rsqrt64h.approx.f64` |
| 8 | `SQRT` | sqrt(x) (approx) | `sqrt.approx.ftz.f32` |
| 9 | `TANH` | tanh(x) (approx) | `tanh.approx.f32` |
| 10–15 | `INVALID*` | Illegal encoding | — |

Note: RCP64H and RSQ64H are used as building blocks for full double-precision
reciprocal/sqrt (typically paired with a Newton-Raphson iteration).

## Modifiers

MUFU has no ftz/sat/rnd modifiers in the encoding. The `ftz` in PTX is handled
at the PTX-to-SASS lowering level.

| Modifier | Field | Width |
|----------|-------|:---:|
| **mufuop** | [77:74] | 4 (operation selector) |
| Rb negate | [63] | 1 |
| Rb absolute | [62] | 1 |

## Bit layout (RRR_RR, 128-bit MSB-left)

```
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   VarLatOperandEnc (variable latency!)
[112:110]               dst_wr_sb    VarLatOperandEnc
[103:102]               pm_pred      (2b)
[ 92: 78]               -- gap --
[77:74]                 mufuop       (4b: operation type)
[73:72]                 — 0 —        (const)
[71:64]                 -- gap --
[63]                    Rb.negate
[62]                    Rb.absolute
[61:40]                 -- gap --
[39:32]                 Rb           (8b)
[31:24]                 -- gap --      ← no Ra field!
[23:16]                 Rd           (8b)
[15]                    Pg.not
[14:12]                 Pg           (3b: predicate, 7=PT)
```

### Variant differences

- **RUR**: URb at [37:32] (6-bit); Rb negate/abs still at [63:62]
- **RIR**: F64Imm at [63:32]; note: F64Imm, not F32Imm!
- **fp16 variants**: Same bit layout, different MUFUOP enum (no RCP64H/RSQ64H)
  + FMT_F16_BF16 discriminator

## Key characteristics

### On `mio_pipe` — not math pipe

MUFU is the only transcendental unit covered so far that runs on `mio_pipe`.
All other FP operations (FADD, FFMA, FMUL, FMNMX, FSET, etc.) are on
`fmalighter_pipe` or `int_pipe`.

### Single source operand

No Ra operand — only Rb. This is fundamentally a unary operation: `Rd = f(Rb)`.

### Variable latency scoreboard

The `src_rel_sb` and `dst_wr_sb` fields use `VarLatOperandEnc()` instead of
the usual `*7` (fixed latency). This means the scoreboard delay depends on both
which `MUFU_OP` is used and potentially the operand value (e.g., denormals,
special values).

### Decoupled RD/WR scoreboard

`INST_TYPE_DECOUPLED_RD_WR_SCBD` — read and write scoreboards are managed
separately, unlike the coupled-math instructions which share a unified
scoreboard.

## Verified encodings (cuobjdump, sm_90)

11/11 matches, covering 10 of 10 valid FP32 operations. Decoder: `tools/decode_mufu.py`.

| Source | Lo64 / Hi64 | Disassembly |
|--------|------------|-------------|
| kernel | `0x0000000500057308` / `0x000e240000000000` | MUFU.COS R5, R5 |
| kernel | `0x0000000500057308` / `0x000e240000000400` | MUFU.SIN R5, R5 |
| kernel | `0x0000000000057308` / `0x000e240000000800` | MUFU.EX2 R5, R0 |
| kernel | `0x0000000600057d08` / `0x000e240008000800` | MUFU.EX2 R5, UR6 (RUR) |
| kernel | `0x0000000600057d08` / `0x000e240008000c00` | MUFU.LG2 R5, UR6 (RUR) |
| kernel | `0x0000000600057d08` / `0x000e240008001000` | MUFU.RCP R5, UR6 (RUR) |
| kernel | `0x0000000600057d08` / `0x000e240008001400` | MUFU.RSQ R5, UR6 (RUR) |
| kernel | `0x0000000600057d08` / `0x000e240008002000` | MUFU.SQRT R5, UR6 (RUR) |
| kernel | `0x0000000600057d08` / `0x000e240008002400` | MUFU.TANH R5, UR6 (RUR) |
| cublas | `0x0000000300057308` / `0x001e240000001800` | MUFU.RCP64H R5, R3 |
| cublas | `0x0000000f00097308` / `0x000e620000001c00` | MUFU.RSQ64H R9, R15 |

### PTX→SASS mapping

| PTX | SASS |
|-----|------|
| `cos.approx.f32 d, a` | `MUFU.COS d, a` |
| `sin.approx.f32 d, a` | `MUFU.SIN d, a` |
| `ex2.approx.f32 d, a` | `MUFU.EX2 d, a` |
| `lg2.approx.f32 d, a` | `MUFU.LG2 d, a` |
| `rcp.approx.f32 d, a` | `MUFU.RCP d, a` |
| `sqrt.approx.f32 d, a` | `MUFU.SQRT d, a` |
| `rsqrt.approx.f32 d, a` | `MUFU.RSQ d, a` |
| `tanh.approx.f32 d, a` | `MUFU.TANH d, a` |
| `rcp64h.approx.f64 d, a` | `MUFU.RCP64H d, a` |
| `rsq64h.approx.f64 d, a` | `MUFU.RSQ64H d, a` |

Compiler behavior: ptxas prefers to load operands into uniform registers and emit
the RUR variant when the operand comes from a kernel parameter (same pattern as
FADD/FMUL on sm_90).

## Open questions

- fp16 variants (`mufu_fp16__*`) not yet tested
- What operations trigger the F64Imm variant (RIR)?
- Variable latency mechanism — how does `VarLatOperandEnc` work exactly?
