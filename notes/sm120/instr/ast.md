# AST — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Graphics attribute-space store used for clip position, varyings, and stage outputs.

## Graphics-observed semantics

`AST` writes graphics attribute storage used to carry stage outputs to the
next fixed-function stage.

Observed vertex output slots:

| output | sm75 SASS |
|---|---|
| `gl_Position` | `AST.128 a[0x70], R0` |
| varying `location=0` | `AST.128 a[0x80], R4` |
| `gl_Layer` | `AST a[0x64], R...` |
| `gl_ViewportIndex` | `AST a[0x68], R...` |
| `gl_PointSize` | `AST a[0x6c], R...` |

The compiler selects `AST.128` when four contiguous source registers are
available and scalar `AST` when components are produced separately. Vertex,
geometry and tessellation paths use the same logical attribute-store family.

`AST` does not write ordinary global memory. It supplies graphics-stage
records consumed by clipping, primitive assembly, rasterization, or
subsequent shader stages.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `ast_PHYS_` | `0x322` | `[/p] /ONLY32("32"):sz A:srcAttr[ NonZeroRegister:Ra ] :Rb :Rc` |
| `ast_UR__LOGICAL_URa` | `0x1522` | `/AInteger("32"):sz A:srcAttr[ :URa + *:URa_offset ] :Rb :Rc` |
| `ast_UR__PATCH_RaRZ_URa` | `0x1522` | `[/p] /AInteger("32"):sz A:srcAttr[ :URa + *:URa_offset ] :Rb :Rc` |
| `ast__LOGICAL_RaRZ` | `0x322` | `/AInteger("32"):sz A:srcAttr[ ZeroRegister("RZ"):Ra + *:Ra_offset ] :Rb :Rc` |
| `ast__PATCH_RaNonRZOffset` | `0x322` | `[/p] /AInteger("32"):sz A:srcAttr[ NonZeroRegister:Ra + *:Ra_offset ] :Rb ZeroRegister("RZ"):Rc` |
| `ast__PATCH_RaRZ` | `0x322` | `[/p] /AInteger("32"):sz A:srcAttr[ ZeroRegister("RZ"):Ra + *:Ra_offset ] :Rb :Rc` |

## Properties

| property | value(s) |
|---|---|
| `ILABEL_Ra_SIZE` | `32` |
| `ILABEL_Rb_SIZE` | `32`, `32 + (((sz==`AInteger@"64"))*32 + ((sz==`AInteger@"96"))*64 + ((sz==`AInteger@"128"))*96)` |
| `ILABEL_Rc_SIZE` | `32` |
| `ILABEL_URa_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_SCBD` |
| `ISRC_A_SIZE` | `32` |
| `ISRC_B_SIZE` | `32`, `32 + (((sz==`AInteger@"64"))*32 + ((sz==`AInteger@"96"))*64 + ((sz==`AInteger@"128"))*96)` |
| `ISRC_C_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@AST`, ``SIDL_NAMES@AST_URb` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_GS)+(1<<ISHADER_TI)+(1<<ISHADER_TS)+(1<<ISHADER_VS)+0`, `(1<<ISHADER_TRAP)+(1<<ISHADER_TI)+0` |
| `VIRTUAL_QUEUE` | `$VQ_AGU` |

## Encoding

Bit map of the first layout (`ast_PHYS_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [77:76] | `op` | 2 | *p |
| [75:74] | `iswzA` | 2 | `sz` |
| [31:24] | `Ra` | 8 | *Ra |
| [39:32] | `Rb` | 8 | `Rb` |
| [71:64] | `Ra_URc` | 8 | `Rc` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | 7 |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `ast_PHYS_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ast_PHYS_` | `OOR_REG_ERROR` | Register Ra is out of range |
| `ast_PHYS_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `ast_PHYS_` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ast_PHYS_` | `OOR_REG_ERROR` | Register Rc is out of range |
| `ast_PHYS_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ast_PHYS_` | `UNPREDICTABLE_BEHAVIOR_WARNING` | Combination leads to unpredictable behavior |
| `ast_UR__LOGICAL_URa` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ast_UR__LOGICAL_URa` | `OOR_REG_ERROR` | Uniform register URa is out of range |
| `ast_UR__LOGICAL_URa` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ast_UR__LOGICAL_URa` | `OOR_REG_ERROR` | Register Rc is out of range |
| `ast_UR__LOGICAL_URa` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ast_UR__LOGICAL_URa` | `OOR_REG_ERROR` | Register is out of range |
| `ast_UR__LOGICAL_URa` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast_UR__LOGICAL_URa` | `OOR_REG_ERROR` | Register is out of range |
| `ast_UR__LOGICAL_URa` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast_UR__LOGICAL_URa` | `OOR_REG_ERROR` | Register is out of range |
| `ast_UR__LOGICAL_URa` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast_UR__LOGICAL_URa` | `UNPREDICTABLE_BEHAVIOR_WARNING` | Combination leads to unpredictable behavior |
| `ast_UR__PATCH_RaRZ_URa` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with TI |
| `ast_UR__PATCH_RaRZ_URa` | `OOR_REG_ERROR` | Uniform register URa is out of range |
| `ast_UR__PATCH_RaRZ_URa` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ast_UR__PATCH_RaRZ_URa` | `OOR_REG_ERROR` | Register Rc is out of range |
| `ast_UR__PATCH_RaRZ_URa` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ast_UR__PATCH_RaRZ_URa` | `OOR_REG_ERROR` | Register is out of range |
| `ast_UR__PATCH_RaRZ_URa` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast_UR__PATCH_RaRZ_URa` | `OOR_REG_ERROR` | Register is out of range |
| `ast_UR__PATCH_RaRZ_URa` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast_UR__PATCH_RaRZ_URa` | `OOR_REG_ERROR` | Register is out of range |
| `ast_UR__PATCH_RaRZ_URa` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast_UR__PATCH_RaRZ_URa` | `UNPREDICTABLE_BEHAVIOR_WARNING` | Combination leads to unpredictable behavior |
| `ast__LOGICAL_RaRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ast__LOGICAL_RaRZ` | `OOR_REG_ERROR` | Register Ra is out of range |
| `ast__LOGICAL_RaRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `ast__LOGICAL_RaRZ` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ast__LOGICAL_RaRZ` | `OOR_REG_ERROR` | Register Rc is out of range |
| `ast__LOGICAL_RaRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ast__LOGICAL_RaRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ast__LOGICAL_RaRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__LOGICAL_RaRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ast__LOGICAL_RaRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__LOGICAL_RaRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ast__LOGICAL_RaRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__LOGICAL_RaRZ` | `UNPREDICTABLE_BEHAVIOR_WARNING` | Combination leads to unpredictable behavior |
| `ast__PATCH_RaNonRZOffset` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with TI |
| `ast__PATCH_RaNonRZOffset` | `OOR_REG_ERROR` | Register Ra is out of range |
| `ast__PATCH_RaNonRZOffset` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `ast__PATCH_RaNonRZOffset` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ast__PATCH_RaNonRZOffset` | `OOR_REG_ERROR` | Register Rc is out of range |
| `ast__PATCH_RaNonRZOffset` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rc |
| `ast__PATCH_RaNonRZOffset` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ast__PATCH_RaNonRZOffset` | `OOR_REG_ERROR` | Register is out of range |
| `ast__PATCH_RaNonRZOffset` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__PATCH_RaNonRZOffset` | `OOR_REG_ERROR` | Register is out of range |
| `ast__PATCH_RaNonRZOffset` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__PATCH_RaNonRZOffset` | `OOR_REG_ERROR` | Register is out of range |
| `ast__PATCH_RaNonRZOffset` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__PATCH_RaNonRZOffset` | `UNPREDICTABLE_BEHAVIOR_WARNING` | Combination leads to unpredictable behavior |
| `ast__PATCH_RaRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with TI |
| `ast__PATCH_RaRZ` | `OOR_REG_ERROR` | Register Ra is out of range |
| `ast__PATCH_RaRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `ast__PATCH_RaRZ` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ast__PATCH_RaRZ` | `OOR_REG_ERROR` | Register Rc is out of range |
| `ast__PATCH_RaRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ast__PATCH_RaRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ast__PATCH_RaRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__PATCH_RaRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ast__PATCH_RaRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__PATCH_RaRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ast__PATCH_RaRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ast__PATCH_RaRZ` | `UNPREDICTABLE_BEHAVIOR_WARNING` | Combination leads to unpredictable behavior |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The post-shader transport between logical attributes and rasterizer physical slots remains opaque.
