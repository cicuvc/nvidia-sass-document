# BGMMA / QGMMA — Binary and FP8 Group MMA

**Pipe:** `mio_pipe` (MIO_SLOW_OPS)
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`
**VIRTUAL_QUEUE:** `$VQ_UMMA`

Same warpgroup-level async tensor core architecture as HGMMA — see
`notes/wgmma.md` and `notes/hgmma.md` for sync model, accumulator collector,
and GMMA scoreboard details.

---

## GMMA opcode family

All four GMMA types share the same 3 addressing modes, differentiated by
the lower 2 opcode bits:

| Bits [1:0] | Mnemonic | Data type | Dense K | Sparse K | Notes |
|:---:|----------|-----------|:---:|:---:|---|
| 00 | **HGMMA** | f16/bf16/tf32/e6m9 | 16 (f16) / 8 (tf32) | 32 (f16) / 16 (tf32) | 32 N sizes |
| 01 | **IGMMA** | u8/s8 | 32 | 64 | 18 N sizes |
| 10 | **BGMMA** | b1 | 256 | — (no sparse) | 18 N sizes |
| 11 | **QGMMA** | e4m3/e5m2 (FP8) | 32 | 64 | 32 N sizes |

3 opcodes per type × 4 types = 12 base opcodes, ×2 for sparse on H/I/Q = 18 total CLASS blocks.

| Mode | HGMMA | IGMMA | BGMMA | QGMMA |
|------|:---:|:---:|:---:|:---:|
| Ra_URb_Rc_ | 0x1df0 | 0x1df1 | 0x1df2 | 0x1df3 |
| URa_Rb_Rc_ | 0x15f0 | 0x15f1 | 0x15f2 | 0x15f3 |
| URa_Rc_ | 0x19f0 | 0x19f1 | 0x19f2 | 0x19f3 |

---

## BGMMA — Binary (b1) GMMA

Implements PTX `wgmma.mma_async` for `.b1` (single-bit) type with `.and` operation.

### Semantics

```
D = POPC(A AND B) + D
```

Matrix multiplication for binary data: instead of multiply-accumulate,
each bit pair is AND-ed (b1 multiply = AND), then the 1-bits are counted
(population count = POPC) and added to the accumulator.

### Variants

**3 variants** only (no sparse — 2:4 sparsity makes no sense for single-bit data):

| Class | Opcode |
|-------|--------|
| `bgmma_Ra_URb_Rc_` | 0x1df2 |
| `bgmma_URa_Rb_Rc_` | 0x15f2 |
| `bgmma_URa_Rc_` | 0x19f2 |

### Modifiers

| Modifier | Enum | Values |
|---|---|---|
| `size` | MMA_SIZE | 64xNx256, N ∈ {8,16,24,32,48,64,80,96,112,128,144,160,176,192,208,224,240,256} |
| `op` | ANDONLY | AND=2 (always) |
| `accum` | POPCONLY | POPC=1 (always) |
| `gsb` | OPTIONAL_GSB | gsb0=0, nooptional_gsb=7 |
| `sat` | SAT? | (check — may be present) |

K=256 for all sizes. Accumulator is always s32 (4 regs minimum).

### Register sizes

- ISRC_A_SIZE = 128 (4 regs), aligned to 4
- ISRC_B_SIZE = 128 (4 regs from descriptor)
- IDEST_SIZE/ISRC_C_SIZE: 128 + N_stepping×128 (e.g., N=64 → 896 bits = 28 regs)
- Alignment: Rd/Rc aligned to 4

### Syntax

```
@P0 BGMMA.64x128x256.AND.POPC R24, R4, gdesc[UR8], R24, UPT
@P0 BGMMA.64x64x256.AND.POPC R24, gdesc[UR6], R24, UPT, gsb0
```

### PTX→SASS

| PTX | SASS |
|-----|------|
| `wgmma.mma_async.sync.aligned.m64n64k256.s32.b1.b1.and` | `BGMMA.64x64x256.AND.POPC` |
| `wgmma.mma_async.sync.aligned.m64n128k256.s32.b1.b1.and` | `BGMMA.64x128x256.AND.POPC` |

---

## QGMMA — FP8 (Quarter-precision) GMMA

Implements PTX `wgmma.mma_async` for `.e4m3`/`.e5m2` (8-bit floating point) types.

### Semantics

Standard FP matrix multiply-accumulate with 8-bit floating point inputs
(e4m3 = 4-bit exponent + 3-bit mantissa, e5m2 = 5-bit exponent + 2-bit mantissa).
Same structure as HGMMA but for FP8 types.

### Variants

**6 variants** (3 modes × dense/sparse):

| Class | Opcode |
|-------|--------|
| `qgmma_Ra_URb_Rc_` | 0x1df3 |
| `qgmma_sparse_Ra_URb_Rc_` | 0x1df3 |
| `qgmma_URa_Rb_Rc_` | 0x15f3 |
| `qgmma_sparse_URa_Rb_Rc_` | 0x15f3 |
| `qgmma_URa_Rc_` | 0x19f3 |
| `qgmma_sparse_URa_Rc_` | 0x19f3 |

### Modifiers

| Modifier | Dense | Sparse |
|---|---|---|
| `size` | 64xNx32, N=8..256 (32 values) | 64xNx64, N=8..256 (32 values) |
| `srcfmt` | F16(0), BF16/E8M7(1), TF32/E8M10(2), E6M9(3) | same |
| `dstfmt` | F16(0), F32(1) | F16(0), F32(1) |
| negA/negB | Yes | Yes |
| tnspA/tnspB | Yes (not TF32) | Yes (not TF32) |
| SAT | Yes | Yes |

Wait — the srcfmt uses the same SRCFMT enum as HGMMA (F16/BF16/TF32/E6M9). This suggests the QGMMA instruction can also handle f16/bf16/tf32, OR the encoding overlaps with HGMMA and the type selection is via the lower opcode bits. Given the PTX spec lists e4m3/e5m2 separately for wgmma at K=32/64, QGMMA likely handles all these FP8 formats.

Actually, looking more carefully: the PTX spec says e4m3/e5m2 at K=32 (dense) and K=64 (sparse), with dstfmt f16/f32. QGMMA has K=32 dense / K=64 sparse, same as IGMMA but with FloatNo64 dstfmt. So QGMMA = FP8 GMMA.

### Register sizes

Similar to IGMMA:
- ISRC_A_SIZE = 128 (4 regs of b32, each holds 4×e4m3/e5m2 elements)
- ISRC_B_SIZE = 128 (from descriptor)
- IDEST_SIZE/ISRC_C_SIZE: 64 + N/8×dstep (f16 dst) or 128 + N/8×dstep (f32 dst)

### Syntax

```
@P0 QGMMA.64x128x32.F16 R24, R4, gdesc[UR8], R24, UPT
@P0 QGMMA.64x64x32.F32 R24, gdesc[UR6], -R8, R24, UPT, gsb0
```

---

## GMMA family comparison

| Property | HGMMA | IGMMA | BGMMA | QGMMA |
|---|---|---|---|---|
| Data type | f16/bf16/tf32/e6m9 | u8/s8 | b1 | e4m3/e5m2 (FP8) |
| Accumulator | f16/f32 | s32 | s32 | f16/f32 |
| Dense K | 16 (f16) / 8 (tf32) | 32 | 256 | 32 |
| Sparse K | 32 (f16) / 16 (tf32) | 64 | — | 64 |
| N sizes (dense) | 32 | 18 | 18 | 32 |
| N sizes (sparse) | 32 | 18 | — | 32 |
| Negation | Yes | No | No | Yes |
| Transpose | Yes | No | No | Yes |
| Saturation | No | Yes | No (POPC implicit) | No |
| Sparse | Yes | Yes | No | Yes |
| Variants | 6 | 6 | 3 | 6 |
| Pipe | mio | mio | mio | mio |
| Uniform reg alignment | 4 | 4 | 4 | 4 |
| Rd alignment | 2 | 4 | 4 | 2 |
| Rc alignment | 2 (varies with N) | 4 | 4 | 2 (varies with N) |
