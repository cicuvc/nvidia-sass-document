# QGMMA — FP8 (Quarter-precision) Group MMA

**Pipe:** `mio_pipe` (MIO_SLOW_OPS) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` | **VIRTUAL_QUEUE:** `$VQ_UMMA`

Warpgroup-level async tensor core operation for 8-bit floating point types (e4m3/e5m2). Uses the same GMMA architecture as HGMMA — see `../arch/wgmma.md` and `hgmma.md` for sync model, accumulator collector, and GMMA scoreboard details.

## Opcode
6 variants (3 modes × dense/sparse):

| Mode | Opcode |
|------|:------:|
| qgmma_Ra_URb_Rc_ | 0x1df3 |
| qgmma_sparse_Ra_URb_Rc_ | 0x1df3 |
| qgmma_URa_Rb_Rc_ | 0x15f3 |
| qgmma_sparse_URa_Rb_Rc_ | 0x15f3 |
| qgmma_URa_Rc_ | 0x19f3 |
| qgmma_sparse_URa_Rc_ | 0x19f3 |

## Semantics
Standard FP matrix multiply-accumulate with 8-bit floating point inputs (e4m3 = 4-bit exponent + 3-bit mantissa, e5m2 = 5-bit exponent + 2-bit mantissa). Same structure as HGMMA but for FP8 types. K=32 dense / K=64 sparse.

### Accumulator precision
When `.F32` destination format is used, the internal Kulisch accumulator only has **14 mantissa bits** — well short of true FP32's 23-bit mantissa. The `.F32` output format refers to the **storage width** (32-bit registers), not the arithmetic precision. For full FP32 accumulation, use HGMMA with f16/BF16 inputs instead.

## Modifiers
| Modifier | Dense | Sparse |
|---|---|---|
| `size` | 64xNx32, N=8..256 (32 values) | 64xNx64, N=8..256 (32 values) |
| `srcfmt` | F16(0), BF16/E8M7(1), TF32/E8M10(2), E6M9(3) | same |
| `dstfmt` | F16(0), F32(1) | F16(0), F32(1) |
| negA/negB | Yes | Yes |
| tnspA/tnspB | Yes (not TF32) | Yes (not TF32) |
| SAT | Yes | Yes |

## Register sizes
- ISRC_A_SIZE = 128 (4 regs of b32, each holds 4×e4m3/e5m2 elements)
- ISRC_B_SIZE = 128 (from descriptor)
- IDEST_SIZE/ISRC_C_SIZE: 64 + N/8×dstep (f16 dst) or 128 + N/8×dstep (f32 dst)

## Syntax
```
@P0 QGMMA.64x128x32.F16 R24, R4, gdesc[UR8], R24, UPT
@P0 QGMMA.64x64x32.F32 R24, gdesc[UR6], -R8, R24, UPT, gsb0
```

## PTX→SASS
| PTX | SASS |
|-----|------|
| `wgmma.mma_async.sync.aligned.m64n64k32.s32.e4m3.e4m3` | `QGMMA.64x64x32.F16` |
| `wgmma.mma_async.sync.aligned.m64n128k32.s32.e4m3.e4m3` | `QGMMA.64x128x32.F16` |

## Bit layout (128-bit, Ra_URb_Rc_ variant 0x1df3)

Same GMMA layout as HGMMA (`hgmma.md`), with QGMMA-specific opcode:

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [124:122],[109:105] | opex | 8 | `TABLES_opex_0(batch_t,usched_info)` | scheduling |
| [121:116] | req_bit_set | 6 | — | scoreboard wait mask |
| [115:113] | src_rel_sb | 3 | `*7` | fixed (no source scoreboard) |
| [112:110] | dst_wr_sb | 3 | `*7` | fixed |
| [103:102] | pm_pred | 2 | — | perfmon predicate |
| [91],[11:0] | opcode | 13 | 0x1df3 | |
| [90:87] | op | 4 | UPp | uniform predicate |
| [86:84] | cop | 3 | gsb | GMMA scoreboard group |
| [77:76] | srcfmt | 2 | SRCFMT | F16=0,BF16=1,TF32=2,E6M9=3 |
| [75] | dstfmt | 1 | FloatNo64 | F16=0,F32=1 |
| [74] | sh | 1 | `*0` | |
| [73] | sz | 1 | `*0` | |
| [72] | Ra@negate | 1 | negA | `-Ra` / `-A` |
| [71:64] | Rc | 8 | Register | accumulator C |
| [63] | negB | 1 | — | `-B` |
| [62] | tnspB | 1 | — | transpose B |
| [59:53] | size | 7 | MMA_SIZE | 64xNx32/64, N ∈ {8..256} |
| [37:32] | URb | 6 | UniformRegister | B descriptor |
| [31:24] | Ra | 8 | Register | A registers |
| [23:16] | Rd | 8 | Register | accumulator D |
| [15] | Pg_not | 1 | Pg@not | predicate negate |
| [14:12] | Pg | 3 | Predicate | guard predicate |

Sparse variants add `sp`/`spformat` fields; URa_Rb_Rc_ (0x15f3) swaps Ra/URb; URa_Rc_ (0x19f3) has no Rb.

Sparse variants add `sp`/`spformat` fields; URa_Rb_Rc_ (0x15f3) swaps Ra/URb; URa_Rc_ (0x19f3) has no Rb.

## Latency
`mio_pipe`, async GMMA scoreboard. See `../arch/wgmma.md` for GMMA completion model.
