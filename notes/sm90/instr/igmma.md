# IGMMA — Integer Group Matrix Multiply-Accumulate

**Opcode mnemonic:** `IGMMA`
**Pipe:** `mio_pipe` (MIO_SLOW_OPS, same as HGMMA)
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`
**VIRTUAL_QUEUE:** `$VQ_UMMA`

## Semantics

Warpgroup-level integer tensor core matrix multiply-accumulate — the integer
counterpart of HGMMA. Implements PTX `wgmma.mma_async` for u8/s8 types.

```
D = A × B + D
```

M=64 fixed, N=8..256, K=32 (dense) or K=64 (sparse). Accumulator is always s32.
All sync mechanisms (GMMA scoreboard, accumulator collector, WARPGROUP fence/wait)
are identical to HGMMA — see `../arch/wgmma.md` and `hgmma.md`.

## Variant overview

IGMMA has **6 encoding variants** — same 3 addressing modes × dense/sparse as HGMMA:

| Class | Opcode | A source | B source |
|-------|--------|----------|----------|
| `igmma_Ra_URb_Rc_` | `0x1df1` | GPR Ra | SMEM via URb desc |
| `igmma_URa_Rb_Rc_` | `0x15f1` | SMEM via URa desc | GPR Rb |
| `igmma_URa_Rc_` | `0x19f1` | SMEM via URa desc | SMEM via URa desc |

Sparse variants share the same opcodes. Opcodes are HGMMA + 1 (bit 0 = 1).

## Key differences from HGMMA

| Property | IGMMA | HGMMA |
|---|---|---|
| Opcodes | 0x1df1 / 0x15f1 / 0x19f1 | 0x1df0 / 0x15f0 / 0x19f0 |
| Data type | u8 / s8 | f16 / bf16 / tf32 / e6m9 |
| Accumulator | s32 (always) | f16 / f32 |
| Dense K | 32 | 16 (f16) / 8 (tf32) |
| Sparse K | 64 | 32 (f16) / 16 (tf32) |
| Src fmt fields | 2 independent (srcfmtA, srcfmtB) | 1 shared (srcfmt) |
| Negation (scale-a/b) | No | Yes (negA, negB) |
| Transpose | No | Yes (tnspA, tnspB) |
| Saturation (SAT) | Yes | No |
| Register alignment | Rd/Ra/Rc aligned to 4 | Rd/Rc aligned to 2 |

## Modifiers

### Matrix size (`size`) — 7-bit at [59:53]

Dense `SIZE_64x8x32_..._64x256x32`: 18 valid values, K=32
Sparse `SIZE_64x8x64_..._64x256x64`: 18 valid values, K=64

Valid N values (dense, sparse both use same N subset):
8, 16, 24, 32, 48, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 256

Note the gaps: 40, 56, 72, 88, 104, 120, 136, 152, 168, 184, 200, 216, 232, 248
are all INVALID for IGMMA (valid for HGMMA). 18 sizes vs HGMMA's 32 sizes.

### Source formats (`srcfmtA`, `srcfmtB`) — 2-bit each

Uses `DSTFMT_U8_S8` (note: oddly named, but it's the source format):
0 = U8, 1 = S8, 2 = INVALID2, 3 = INVALID3

Same type for both A and B: `both .u8 or both .s8` (PTX requirement).

### Saturation (`sat`) — 1-bit

SAT flag: 0 = nosat (wrap on overflow), 1 = SAT (saturate to s32 range).
Maps to PTX `.satfinite` qualifier.

### Accumulator register sizes

Accumulator s32: N/2 registers per thread, aligned to 4.

| N | Regs/thread (Rd/Rc) | MAX_REG_COUNT limit |
|:---:|:---:|:---:|
| 8 | 4 | -4 |
| 16 | 8 | -8 |
| 24 | 12 | -12 |
| 32 | 16 | -16 |
| 48 | 24 | -24 |
| 64 | 32 | -32 |
| 80 | 40 | -40 |
| 96 | 48 | -48 |
| 112 | 56 | -56 |
| 128 | 64 | -64 |
| 144 | 72 | -72 |
| 160 | 80 | -80 |
| 176 | 88 | -88 |
| 192 | 96 | -96 |
| 208 | 104 | -104 |
| 224 | 112 | -112 |
| 240 | 120 | -120 |
| 256 | 128 | -128 |

A in registers (Ra): always 4 regs (128-bit), aligned to 4.
B in registers (Rb, only URa_Rb_Rc_ variant): varies with size.
GMMA descriptor (URa/URb): always 4 uniform regs, aligned to 4.

## Bit layout

Same bit positions as HGMMA, with these field substitutions:

| Bits | HGMMA field | IGMMA field | Notes |
|------|-------------|-------------|-------|
| [77:76] | srcfmt (2b) | srcfmtB (2b) | IGMMA has independent A/B format |
| [75] | dstfmt (1b) | srcfmtA bit? | IGMMA: no dstfmt, srcfmtA elsewhere |
| [74] | sh (*0) | srcfmtA bit? | repurposed |
| [73] | sz (0) | 0 | |
| [72] | Ra@negate / negA | 0 | No negation in IGMMA |
| [63] | negB / Rb@negate | 0 | No negation |
| [62] | tnspB | 0 | No transpose |
| [61] | tnspA | 0 | No transpose |

Saturation bit (SAT) occupies a slot repurposed from HGMMA's layout.

## PTX→SASS mapping

IGMMA implements PTX `wgmma.mma_async` for integer types.

| PTX | SASS |
|-----|------|
| `wgmma.mma_async.sync.aligned.m64n64k32.s32.u8.u8` | `IGMMA.64x64x32.U8.U8` |
| `wgmma.mma_async.sync.aligned.m64n128k32.s32.u8.u8` | `IGMMA.64x128x32.U8.U8` |
| `wgmma.mma_async.sync.aligned.m64n256k32.s32.s8.s8` | `IGMMA.64x256x32.S8.S8` |
| `... .satfinite ...` | `IGMMA.64xNx32.U8.U8.SAT` |

### PTX operand mapping

| PTX | IGMMA field | Notes |
|-----|-------------|-------|
| `scale-d` (pred) | Rc == RZ? | false = A×B only (RZ), true = accumulate (same reg) |
| `imm-scale-a` (±1) | **(none)** | Integer: no negation |
| `imm-scale-b` (±1) | **(none)** | Integer: no negation |
| `imm-trans-a` | **(none)** | Integer: no transpose support |
| `imm-trans-b` | **(none)** | Integer: no transpose support |
| `.satfinite` | SAT flag | Saturation on overflow |

### Sync skeleton (same as HGMMA)

```
WARPGROUP.ARRIVE                              # wgmma.fence
IGMMA.64x64x32.U8.U8 R24, gdesc[UR4], RZ, !UPT
IGMMA.64x64x32.U8.U8 R24, gdesc[UR4], R24, gsb0
WARPGROUP.DEPBAR.LE gsb0, 0x0                 # wgmma.wait_group
```

## IGMMA vs IMMA comparison

| Property | IGMMA | IMMA |
|---|---|---|
| Scope | Warpgroup (4 warps) | Warp (1 warp) |
| Pipe | mio_pipe | int_pipe |
| Matrix data | Shared mem (gdesc) or regs | Registers only |
| Matrix size | M=64, N=8..256, K=32/64 | M=8/16, N=8, K=16/32/64 |
| Acc reg count | 4..128 (varies with N) | 2–8 (varies with size) |
| Sync | GMMA scoreboard (gsb) | Variable scoreboard |
| SrcFmt fields | srcfmtA + srcfmtB (both U8/S8) | srcFmtA + srcFmtB (same) |
| ROW/COL qualifiers | No (gdesc handles layout) | Yes |
| SAT | Yes | Yes |
