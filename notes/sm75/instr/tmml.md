# TMML — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

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
| `tmml_` | `0xb69` | `[/lod] /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Rd2 :Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx TEXPARAMA:paramA *:wmsk` |
| `tmml_b_` | `0xb69` | `[/b] [/lod] /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:tsPtrIdx TEXPARAMA:paramA *:wmsk` |
| `tmml_b_noConst_` | `0x36a` | `[/b] [/lod] /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb TEXPARAMA:paramA *:wmsk` |
| `tmml_b_tid_` | `0xb6b` | `[/b] [/lod] /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:hdrtblbase6 *:tid8 TEXPARAMA:paramA *:wmsk` |
| `tmml_urc_` | `0x1f69` | `[/lod] /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Rd2 :Rd NonZeroRegister:Ra :Rb NonZeroUniformRegister:URc *:tid8 TEXPARAMA:paramA *:wmsk` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_OPERAND_MAP` | `(1<<INDEX(Rd2))` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_FLOAT)` |
| `IDEST2_SIZE` | `((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))>2) ? (32 + (((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))==4)*32)) : 0` |
| `IDEST_OPERAND_MAP` | `(1<<INDEX(Rd))` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_FLOAT)` |
| `IDEST_SIZE` | `((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))>=2) ? 64 : 32` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_MISALIGNED_REG)+(1<<IERROR_OOR_REG)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<INDEX(Ra))` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_A_SIZE` | `((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4)))*32` |
| `ISRC_B_OPERAND_MAP` | `(1<<INDEX(Rb))` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_B_SIZE` | `32` |
| `ISRC_C_OPERAND_MAP` | `(1<<INDEX(URc))`, `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)`, `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_C_SIZE` | `0`, `64` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@TMML`, ``SIDL_NAMES@TMML_B`, ``SIDL_NAMES@TMML_B_noConst`, ``SIDL_NAMES@TMML_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`tmml_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [59:59] | `b` | 1 | 0 |
| [77:77] | `ntz` | 1 | `ndv` |
| [90:90] | `input_reg_sz_32_dist` | 1 | `nodep` |
| [71:64] | `Rc` | 8 | `Rd2` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [39:32] | `Rb` | 8 | `Rb` |
| [58:54] | `Sb_bank` | 5 | `bank5` |
| [53:40] | `Sb_addr` | 14 | `tsPtrIdx MULTIPLY 4 SCALE 4` |
| [63:61] | `dim` | 3 | `paramA` |
| [75:72] | `PixMaskU04` | 4 | `wmsk` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `tmml_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tmml_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tmml_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tmml_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tmml_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tmml_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tmml_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tmml_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tmml_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tmml_b_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tmml_b_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tmml_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
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
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tmml_b_tid_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tmml_b_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tmml_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tmml_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tmml_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tmml_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed uniform register URc |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tmml_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tmml_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The exact fixed-point scaling of every TMML result mode was not exhaustively enumerated.
