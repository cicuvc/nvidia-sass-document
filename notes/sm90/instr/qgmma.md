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

## H800 throughput and operand-service model (2026-09)

Hand-SASS timing shows that dense E4M3 QGMMA has the same wall-clock shape
as BF16 HGMMA, while performing twice as many MACs because K is 32 instead
of 16.  For F32 accumulation:

| shape | SS issue / drain | RS issue / drain |
|---|---:|---:|
| m64n8k32 | 17.359 / 19.438 | 12.000 / 13.516 |
| m64n16k32 | 19.234 / 21.562 | 12.016 / 13.578 |
| m64n64k32 | 30.422 / 34.250 | 28.922 / 32.656 |

An overlapping STS stream measures the shared operand service directly:

| shape | predicted SS wavefronts | measured SS block | predicted RS wavefronts | measured RS block |
|---|---:|---:|---:|---:|
| n8 | 18 | 18.12 | 2 | 2.016 |
| n16 | 20 | 20.12 | 4 | 4.016 |
| n64 | 32 | 32.12 | 16 | 16.016 |

The byte accounting is identical to dense BF16 HGMMA:

```text
A = 64x32 FP8 = 2048 B = 16 wavefronts
B per n8 = 32x8 FP8 = 256 B = 2 wavefronts
SS = 16 + 2*(N/8); RS = 2*(N/8)
```

Thus the FP8 RHS unit tile is **32x8**, not 16x8.  It takes two cycles on
the one-128-B-wavefront/cycle shared path and is broadcast to all four
subcore Tensor Cores.  Halving element width is exactly cancelled by
doubling K.

The F32 output/RMW backend is also identical to HGMMA.  A marker race sees
the same three states (`marker+delta`, `base+delta`, `marker`) at exactly
the same accumulator-pair boundaries: an approximately 12-clock
read-to-write aperture and one 32-lane `{even,odd}` register pair every
approximately two clocks.  A real-GPR `MOV32I` storm slows n64 QGMMA from
64.641 to 80.328 cycles/MMA relative to its `RZ` control, the exact HGMMA
write-port signature.

An E5M2 n64 spot check is indistinguishable: 30.422/34.250 issue/drain,
31.984 STS-blocked cycles (expected 32), and exactly the same six-slot
RMW aperture.  The model therefore belongs to the common FP8 QGMMA path,
not specifically to E4M3.

One register pair contains 64 F32 outputs, i.e. one m8n8 tile per subcore.
For QGMMA that tile performs `8*8*32 = 2048` MACs every two clocks:

```text
per subcore: 1024 MAC/clock = 2048 FLOP/clock
per SM:      4096 MAC/clock = 8192 FLOP/clock
```

At 132 SMs and the 1.83-GHz low-precision Tensor clock this gives 1.979
PFLOP/s dense FP8, exactly the published H100 SXM value (3.958 PFLOP/s
with 2:4 sparsity).  Consequently m64n8/n16/n64 have MAC lower bounds of
4/8/32 clocks, the same cycle counts as BF16 despite twice the MAC count.

Probe sources: `tests/asm_construct/probe_hgmma_mio_interaction.py`
(`--mma qgmma`) and `tests/asm_construct/probe_hgmma_rmw_window.py`
(`--mma qgmma`).
