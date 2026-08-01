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

> **COS/SIN take the argument in turns (2π units), not radians** — see
> "Resolved" below.  A compiler must pre-scale by `1/2π`.

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

## Resolved: semantics + quantitative error (SM120, clean hand-built ELF, 2026-08)

Probed with a clean kernel (`S2R` lane-id → per-lane `LDG` → `MUFU.op` →
`STG`), sweeping thousands of random normal-range FP32 inputs plus specials,
compared against double-precision references.  `tests/asm_construct/test_mufu.py`.

### Exact semantics

| Op | Function | Notes |
|----|----------|-------|
| RCP  | `1/x` | correctly rounded for normal inputs (max 1 ulp) |
| RSQ  | `1/√x` | correctly rounded (1–2 ulp) |
| SQRT | `√x`   | correctly rounded (1 ulp) |
| EX2  | `2^x`  | ~1 ulp mean, worst ~31 ulp at large |x| |
| LG2  | `log2(x)` | ~0.65 ulp mean; worst ~87 ulp near x=1 |
| TANH | `tanh(x)` | mean 5.6 ulp; worst ~117 ulp near x=±1 |
| COS  | **`cos(2π·x)`** | argument in **turns, not radians**! |
| SIN  | **`sin(2π·x)`** | argument in **turns, not radians**! |
| RCP64H | `hi32(1/x)` | reads hi 32 bits of a double → hi 32 bits of result |
| RSQ64H | `hi32(1/√x)` | same convention |

### COS/SIN turn convention (major finding)

`MUFU.COS(x)` computes `cos(2π·x)`, `MUFU.SIN(x)` computes `sin(2π·x)` —
the operand is in **half-turns / cycles**, not radians.  Verified:
`COS(0.5) = cos(π) = −1`, `COS(1.0) = cos(2π) = 1`, `SIN(0.25) = sin(π/2) = 1`.
This is why a compiler must scale a radian argument by `1/2π` (or fold the
scale into its range reduction) before issuing MUFU.COS/SIN.  The hardware
does exact range reduction: absolute error stays ~1e-7 even for |x| up to 32
turns.  (PTX `cos.approx`/`sin.approx` hide this by requiring the source to
be pre-reduced.)

### Quantitative error (random normal-range FP32, vs double reference)

Relative error percentiles:

| Op | p50 | p99 | max |
|----|-----|-----|-----|
| RCP  | 2.7e-08 | 9.1e-08 | 1.2e-07 |
| RSQ  | 2.6e-08 | 9.2e-08 | 1.3e-07 |
| SQRT | 2.3e-08 | 8.6e-08 | 1.1e-07 |
| EX2  | 1.5e-08 | 4.6e-07 | 2.7e-06 |
| LG2  | 4.1e-08 | 3.3e-07 | 3.6e-06 |
| TANH | 1.5e-08 | 6.7e-06 | 9.5e-06 |

COS/SIN (absolute error, output ∈ [−1,1]): p50 ≈ 6–9e-08, max ≈ 3.6e-07.
RCP64H/RSQ64H: p50 ≈ 2e-07, max ≈ 1e-06 (approximations, not correctly
rounded — they are Newton-Raphson seeds for full FP64 div/sqrt).

So: **RCP/RSQ/SQRT are correctly rounded; EX2/LG2/TANH are ~1e-6–1e-5
relative (the "approx" ops); COS/SIN are exact-range-reduced but need turn
inputs; RCP64H/RSQ64H are ~1e-6 FP64 helpers.**

### Special values (verified)

| Input | RCP | RSQ | SQRT | EX2 | LG2 | TANH | COS/SIN |
|-------|-----|-----|------|-----|-----|------|---------|
| ±0   | ±inf | ±inf | ±0 | 1 | −inf | ±0 | cos=1/sin=±0 |
| denormal | inf | inf | 0 | 1 | −inf | **passthrough (bit-exact)** | 1/±0 |
| ±inf | ±0 | ±0/NaN | inf | inf/−0 | inf/NaN | ±1 | NaN |
| NaN  | NaN | NaN | NaN | NaN | NaN | NaN | NaN |

Note `TANH` passes denormals through **unchanged** (returns the denormal
itself, e.g. 0x1 → 0x1, 0x7fffff → 0x7fffff) — it does not flush them.

## Latency (SM120 empirical, 2026-08)

Measured with a **dependent scoreboard chain**: each MUFU sets `wr=SB1`, the
next MUFU `req={1}` waits for that writeback; `CS2R SR_CLOCKLO/HI` (64-bit
cycle counter) read around the chain, `latency = Δt / N`.
`tests/asm_construct/test_mufu_latency.py`.

**Result: every MUFU op measures 18.02 cycles** (±0.02, stable across N and
repeats) — a single shared SFU/MUFU writeback latency:

| op | RCP | RSQ | SQRT | EX2 | LG2 | TANH | COS | SIN | RCP64H | RSQ64H |
|----|-----|-----|------|-----|-----|------|-----|-----|--------|--------|
| cyc | 18.02 | 18.02 | 18.02 | 18.02 | 18.02 | 18.02 | 18.02 | 18.02 | 18.02 | 18.02 |

**Harness calibration** (same chain): IADD3 / FFMA / MOV ≈ 5.44 cyc — the
harness cleanly separates the ~5-cycle ALU ops from the ~18-cycle SFU op, so
the 18.0 is genuine, not a measurement floor.

**Interpretation**: the spec's `VarLatOperandEnc` ("variable latency, depends
on op/operand") does not produce per-op *writeback* differences on the tested
hardware — all 10 ops dispatch through the same MUFU/SFU unit with one
writeback depth (~18 cyc).  The "variable" part likely refers to the *issue /
pipe occupancy* behavior (e.g. throughput of independent ops ≈ 8 cyc/op on
this core) rather than the data-dependency writeback latency.  Cross-pipe:
a MUFU result consumed by a coupled FFMA (MUFU→FFMA dependency) measures
≈ 23 cyc/iteration.

Note: this is the SM120 measurement; the sm_90 latency tables (mio_pipe /
MIO_SLOW_OPS) would predict the GPR-release latency (MIO→MIO = 2 in
TABLE_TRUE), which is a *different* number than the SFU execution+writeback
latency measured here — the scoreboard `req` wait exposes the latter.
