# TMML — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Texture mip/lod query that returns LOD data without sampling a texel.

## Graphics-observed semantics

`textureQueryLod()` lowers to two `TMML.LOD` operations:

```text
TMML.LOD.NODEP RZ, R6, R4, 0x1e, 0x0, 2D, 0x2
TMML.LOD.NODEP RZ, R7, R4, 0x1e, 0x0, 2D, 0x1
```

The trailing immediate selects which LOD result is produced. The compiler
converts the returned values to float and scales by `1/256` to match GLSL.
No texel fetch occurs.

sm120 uses the same two `TMML.LOD.DXY` operations with a uniform descriptor:

```text
TMML.LOD.DXY.NODEP RZ, R6, R4, UR4, 2D, 0x1
TMML.LOD.DXY.NODEP RZ, R0, R4, UR4, 2D, 0x2
```

Scheduling can reverse the two result-producing instructions; the trailing
selector identifies them.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `tmml_b_noConst_` | `0x36a` | `[/b] [/lod] /DIV("nodiv"):div /NODEP("nonodep"):nodep :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb TEXPARAMA:paramA *:wmsk` |
| `tmml_b_urc_` | `0x1f6a` | `[/b] [/lod] /DIV("nodiv"):div /NODEP("nonodep"):nodep :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URc TEXPARAMA:paramA *:wmsk` |
| `tmml_urc_` | `0x1f69` | `[/lod] /DIV("nodiv"):div /NODEP("nonodep"):nodep :Rd2 :Rd NonZeroRegister:Ra :Rb :URc @:tid8 TEXPARAMA:paramA *:wmsk` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_SIZE` | `((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))>2) ? (32 + (((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))==4)*32)) : 0` |
| `IDEST_SIZE` | `((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))>=2) ? 64 : 32` |
| `ILABEL_Ra_SIZE` | `32 + (((paramA==`TEXPARAMA@ARRAY_1D) || (paramA==`TEXPARAMA@"2D"))*32 + ((paramA==`TEXPARAMA@ARRAY_2D) || (paramA==`TEXPARAMA@CUBE) || (paramA==`TEXPARAMA@"3D"))*64 + ((paramA==`TEXPARAMA@ARRAY_CUBE))*96)` |
| `ILABEL_Rb_SIZE` | `32` |
| `ILABEL_URc_SIZE` | `64` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32 + (((paramA==`TEXPARAMA@ARRAY_1D) || (paramA==`TEXPARAMA@"2D"))*32 + ((paramA==`TEXPARAMA@ARRAY_2D) || (paramA==`TEXPARAMA@CUBE) || (paramA==`TEXPARAMA@"3D"))*64 + ((paramA==`TEXPARAMA@ARRAY_CUBE))*96)` |
| `ISRC_B_SIZE` | `32` |
| `ISRC_C_SIZE` | `64` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@TMML_B_URc`, ``SIDL_NAMES@TMML_B_noConst`, ``SIDL_NAMES@TMML_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`tmml_b_noConst_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [77:76] | `op` | 2 | `div` |
| [90:90] | `memdesc` | 1 | `nodep` |
| [71:64] | `Ra_URc` | 8 | `Rd2` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [39:32] | `Rb` | 8 | `Rb` |
| [63:61] | `paramA` | 3 | `paramA` |
| [75:72] | `wmsk` | 4 | `wmsk` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tmml_b_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tmml_b_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tmml_b_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tmml_b_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tmml_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tmml_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tmml_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tmml_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The exact fixed-point scaling of every TMML result mode was not exhaustively enumerated.
