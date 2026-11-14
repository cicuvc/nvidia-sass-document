# FOOTPRINT — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe_fragment_footprint*.frag`, `vulkan_graphics.c`, `extract_pipeline_binary.py`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

## Conclusion

Hardware texture-footprint query for implicit or explicit derivatives.

## Graphics-observed semantics

`FOOTPRINT` computes the texel-group footprint of an equivalent filtered
texture access without returning sampled colors.

Primary modes:

| mode | meaning |
|---|---|
| `FOOTPRINT.TEX` | implicit screen-space derivatives |
| `FOOTPRINT.TXD` | explicit X/Y gradients |

LOD controls include `LB`, `LC`, `LL`, `LB.LC`, `LC.FDV`, and `LZ`.
`COARSE` requests coarse mip granularity; the default is fine.

Representative sm75 forms:

```text
FOOTPRINT.SCR.TEX.NODEP P0, R6, R4, R6, R4, 0x1e, 0x0, 2D
FOOTPRINT.SCR.TEX.LL.NODEP P0, R4, R6, R6, R4, 0x1e, 0x0, 2D
FOOTPRINT.TXD.NODEP P0, R8, R0, R4, R8, 0x1e, 0x0, 2D
```

The operation returns packed footprint data in two 64-bit destination pairs
and validity in `Pu`. The GLSL result exposes anchor, offset, a 64-bit mask of
8x8 texel groups, LOD, and granularity.

sm120 unpacks the descriptor into `UR4` and adds `.DXY` to implicit forms.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `footprint_` | `0xb72` | `[/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx PARAMA_2D_3D:paramA` |
| `footprint_b_` | `0xb72` | `[/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:tsPtrIdx PARAMA_2D_3D:paramA` |
| `footprint_b_noConst_` | `0x373` | `[/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb PARAMA_2D_3D:paramA` |
| `footprint_b_tid_` | `0xb74` | `[/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:hdrtblbase6 *:tid8 PARAMA_2D_3D:paramA` |
| `footprint_scr_` | `0xb72` | `[/scr] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx PARAMA_2D_3D:paramA` |
| `footprint_scr_b_` | `0xb72` | `[/scr] [/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:tsPtrIdx PARAMA_2D_3D:paramA` |
| `footprint_scr_b_noConst_` | `0x373` | `[/scr] [/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb PARAMA_2D_3D:paramA` |
| `footprint_scr_b_tid_` | `0xb74` | `[/scr] [/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:hdrtblbase6 *:tid8 PARAMA_2D_3D:paramA` |
| `footprint_scr_uniform_` | `0x1f74` | `[/scr] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra :Rb NonZeroUniformRegister:URc *:tid8 PARAMA_2D_3D:paramA` |
| `footprint_uniform_` | `0x1f74` | `[/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra :Rb NonZeroUniformRegister:URc *:tid8 PARAMA_2D_3D:paramA` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_OPERAND_MAP` | `(1<<INDEX(Rd2))` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_FLOAT)` |
| `IDEST2_SIZE` | `64` |
| `IDEST_OPERAND_MAP` | `(1<<INDEX(Rd))` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_FLOAT)` |
| `IDEST_SIZE` | `64` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_MISALIGNED_REG)+(1<<IERROR_OOR_REG)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<INDEX(Ra))` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_A_SIZE` | `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) - (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*(((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1))) + (((lodlc==`LODLC@nolodlc)*1 + (lodlc==`LODLC@LZ)*1 + (lodlc==`LODLC@LB)*2 + (lodlc==`LODLC@LL)*2 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2)) + 1) > 2) ? 64 : 32`, `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) - (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*(((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1))) + (((lodlc==`LODLC@nolodlc)*1 + (lodlc==`LODLC@LZ)*1 + (lodlc==`LODLC@LB)*2 + (lodlc==`LODLC@LL)*2 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2))) > 2) ? 64 : 32`, `(((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) + 1 + (mode==`MODE_FOOTPRINT@TXD))*32`, `(((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) + 1)*32` |
| `ISRC_B_OPERAND_MAP` | `(1<<INDEX(Rb))` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_B_SIZE` | `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) - (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*(((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1))) + (((lodlc==`LODLC@nolodlc)*1 + (lodlc==`LODLC@LZ)*1 + (lodlc==`LODLC@LB)*2 + (lodlc==`LODLC@LL)*2 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2)) + 1)==4) ? 64 : 32`, `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) - (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*(((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1))) + (((lodlc==`LODLC@nolodlc)*1 + (lodlc==`LODLC@LZ)*1 + (lodlc==`LODLC@LB)*2 + (lodlc==`LODLC@LL)*2 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2)))==4) ? 64 : 32`, `((mode==`MODE_FOOTPRINT@TXD) ? (128) : ((((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1))*32))`, `((mode==`MODE_FOOTPRINT@TXD) ? (128) : (32 + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1))*32))` |
| `ISRC_C_OPERAND_MAP` | `(1<<INDEX(URc))`, `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)`, `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_C_SIZE` | `0`, `64` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@FOOTPRINT`, ``SIDL_NAMES@FOOTPRINT_B`, ``SIDL_NAMES@FOOTPRINT_B_noConst`, ``SIDL_NAMES@FOOTPRINT_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_FTPRNT` |

## Encoding

Bit map of the first layout (`footprint_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [60:60] | `scr` | 1 | 0 |
| [59:59] | `b` | 1 | 0 |
| [78:78] | `ofmt` | 1 | `mode` |
| [76:76] | `private` | 1 | `lodctrl` |
| [89:87] | `Pp` | 3 | `lodlc` |
| [77:77] | `ntz` | 1 | `ndv` |
| [90:90] | `input_reg_sz_32_dist` | 1 | `nodep` |
| [83:81] | `Pu` | 3 | `Pu` |
| [71:64] | `Rc` | 8 | `Rd2` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [39:32] | `Rb` | 8 | `Rb` |
| [58:54] | `Sb_bank` | 5 | `bank5` |
| [53:40] | `Sb_addr` | 14 | `tsPtrIdx MULTIPLY 4 SCALE 4` |
| [63:61] | `dim` | 3 | *paramA |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: TXD_paramA) |
| `footprint_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_in_tex_mode_only) |
| `footprint_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_in_tex_mode_only) |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_b_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_b_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_b_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_b_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_b_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: TXD_paramA) |
| `footprint_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_in_tex_mode_only) |
| `footprint_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_in_tex_mode_only) |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: TXD_paramA) |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_in_tex_mode_only) |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_in_tex_mode_only) |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_b_tid_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_b_tid_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_b_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_b_tid_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_b_tid_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: TXD_paramA) |
| `footprint_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_in_tex_mode_only) |
| `footprint_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_in_tex_mode_only) |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_scr_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_scr_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_scr_b_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_scr_b_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_scr_b_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_scr_b_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_scr_b_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_scr_b_tid_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_scr_b_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed uniform register URc |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_uniform_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed uniform register URc |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: TXD_paramA) |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_in_tex_mode_only) |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_in_tex_mode_only) |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The full granularity-code table is supplied by the NV extension specification and was not independently enumerated.
