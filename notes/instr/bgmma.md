# BGMMA — Binary (b1) Group MMA

**Pipe:** `mio_pipe` (MIO_SLOW_OPS) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` | **VIRTUAL_QUEUE:** `$VQ_UMMA`

Warpgroup-level async tensor core operation for binary data. Uses the same GMMA architecture as HGMMA — see `../arch/wgmma.md` and `hgmma.md` for sync model, accumulator collector, and GMMA scoreboard details.

## Opcode
3 variants (no sparse — 2:4 sparsity makes no sense for single-bit data):

| Mode | Opcode |
|------|:------:|
| Ra_URb_Rc_ | 0x1df2 |
| URa_Rb_Rc_ | 0x15f2 |
| URa_Rc_ | 0x19f2 |

## Semantics
```
D = POPC(A AND B) + D
```
Matrix multiplication for binary data: each bit pair is AND-ed (b1 multiply = AND), then the 1-bits are counted (POPC) and added to the accumulator.

## Modifiers
| Modifier | Enum | Values |
|---|---|---|
| `size` | MMA_SIZE | 64xNx256, N ∈ {8,16,24,32,48,64,80,96,112,128,144,160,176,192,208,224,240,256} |
| `op` | ANDONLY | AND=2 (always) |
| `accum` | POPCONLY | POPC=1 (always) |
| `gsb` | OPTIONAL_GSB | gsb0=0, nooptional_gsb=7 |
| `sat` | SAT? | (check — may be present) |

K=256 for all sizes. Accumulator is always s32 (4 regs minimum).

## Register sizes
- ISRC_A_SIZE = 128 (4 regs), aligned to 4
- ISRC_B_SIZE = 128 (4 regs from descriptor)
- IDEST_SIZE/ISRC_C_SIZE: 128 + N_stepping×128 (e.g., N=64 → 896 bits = 28 regs)
- Alignment: Rd/Rc aligned to 4

## Syntax
```
@P0 BGMMA.64x128x256.AND.POPC R24, R4, gdesc[UR8], R24, UPT
@P0 BGMMA.64x64x256.AND.POPC R24, gdesc[UR6], R24, UPT, gsb0
```

## PTX→SASS
| PTX | SASS |
|-----|------|
| `wgmma.mma_async.sync.aligned.m64n64k256.s32.b1.b1.and` | `BGMMA.64x64x256.AND.POPC` |
| `wgmma.mma_async.sync.aligned.m64n128k256.s32.b1.b1.and` | `BGMMA.64x128x256.AND.POPC` |

## Bit layout (128-bit, Ra_URb_Rc_ variant 0x1df2)

Same GMMA layout as HGMMA (`hgmma.md`), with opcode and size/type fields adapted for binary data:

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [124:122],[109:105] | opex | 8 | `TABLES_opex_0(batch_t,usched_info)` | scheduling |
| [121:116] | req_bit_set | 6 | — | scoreboard wait mask |
| [115:113] | src_rel_sb | 3 | `*7` | fixed (no source scoreboard) |
| [112:110] | dst_wr_sb | 3 | `*7` | fixed |
| [103:102] | pm_pred | 2 | — | perfmon predicate |
| [91],[11:0] | opcode | 13 | 0x1df2 | |
| [90:87] | op | 4 | UPp | uniform predicate |
| [86:84] | cop | 3 | gsb | GMMA scoreboard group |
| [77:76] | srcfmt | 2 | `*0` | binary (no format selection) |
| [75] | dstfmt | 1 | `*0` | s32 only |
| [74] | sh | 1 | `*0` | |
| [73] | sz | 1 | `*0` | |
| [71:64] | Rc | 8 | Register | accumulator C |
| [59:53] | size | 7 | MMA_SIZE | 64xNx256, N ∈ {8..256} |
| [37:32] | URb | 6 | UniformRegister | B descriptor |
| [31:24] | Ra | 8 | Register | A registers |
| [23:16] | Rd | 8 | Register | accumulator D |
| [15] | Pg_not | 1 | Pg@not | predicate negate |
| [14:12] | Pg | 3 | Predicate | guard predicate |

URa_Rb_Rc_ (0x15f2) swaps Ra/URb roles; URa_Rc_ (0x19f2) has no Rb field.

## Latency
`mio_pipe`, async GMMA scoreboard. See `../arch/wgmma.md` for GMMA completion model.
