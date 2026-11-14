# TEX — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

## Conclusion

Filtered sampled-texture fetch with implicit derivatives and sampler state.

## Graphics-observed semantics

`texture(sampler2D, uv)` lowers to `TEX`. Representative sm75 SASS:

```text
TEX.SCR.NODEP R2, R0, R4, R5, 0x1e, 0x0, 2D
```

`R4/R5` supply coordinates, `R0..R3` receive RGBA, `.SCR` indicates
screen-space sampling, and `.NODEP` controls the client dependency bit. The
immediate pair selects the texture/sampler descriptor.

Bindless sampled textures use the `.B` form:

```text
LDC R6, c[0x1e][R6]
TEX.SCR.B.NODEP R2, R0, R4, R6, 2D
```

Here `Rb=R6` is the dynamically loaded texture/sampler pointer. There is no
separate bindless mnemonic.

On sm120, the compiler first unpacks the descriptor:

```text
LDCU.TEXUNPACK UR4, c[0x1e][URZ]
TEX.SCR.DXY.NODEP R2, R0, R4, R5, UR4, 2D
```

`.DXY` marks the sm120 derivative model; `.B` remains the register-pointer
bindless form.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `tex_` | `0xb60` | `/F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx TEXPARAMA:paramA *:wmsk` |
| `tex_b_` | `0xb60` | `[/b] /F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:tsPtrIdx TEXPARAMA:paramA *:wmsk` |
| `tex_b_noConst_` | `0x361` | `[/b] /F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb TEXPARAMA:paramA *:wmsk` |
| `tex_b_tid_` | `0xb62` | `[/b] /F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:hdrtblbase6 *:tid8 TEXPARAMA:paramA *:wmsk` |
| `tex_scr_` | `0xb60` | `[/scr] /F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx TEXPARAMA:paramA *:wmsk` |
| `tex_scr_b_` | `0xb60` | `[/scr] [/b] /F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:tsPtrIdx TEXPARAMA:paramA *:wmsk` |
| `tex_scr_b_noConst_` | `0x361` | `[/scr] [/b] /F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb TEXPARAMA:paramA *:wmsk` |
| `tex_scr_b_tid_` | `0xb62` | `[/scr] [/b] /F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:hdrtblbase6 *:tid8 TEXPARAMA:paramA *:wmsk` |
| `tex_scr_urc_` | `0x1f60` | `[/scr] /F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb NonZeroUniformRegister:URc *:tid8 TEXPARAMA:paramA *:wmsk` |
| `tex_urc_` | `0x1f60` | `/F16RM("nof16rm"):f16rm /LODLC("nolodlc"):lodlc /AOFFI("noaoffi"):aoffi /DC("nodc"):dc /COP("EN"):cop /NDV("nondv"):ndv /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb NonZeroUniformRegister:URc *:tid8 TEXPARAMA:paramA *:wmsk` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_OPERAND_MAP` | `(1<<INDEX(Rd2))` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_FLOAT)` |
| `IDEST2_SIZE` | `((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))>2) ? (32 + (((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))==4)*(f16rm==0)*32)) : 0` |
| `IDEST_OPERAND_MAP` | `(1<<INDEX(Rd))` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_FLOAT)` |
| `IDEST_SIZE` | `((((wmsk)&0x1) + ((wmsk>>1)&0x1) + ((wmsk>>2)&0x1) + ((wmsk>>3)&0x1))>=2) ? (32 + ((f16rm==0)*32)) : 32` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_MISALIGNED_REG)+(1<<IERROR_OOR_REG)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<INDEX(Ra))` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_A_SIZE` | `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) - (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*((((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1)))) + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2)) + (aoffi==`AOFFI@AOFFI) + (dc==`DC@DC) + 1)>2) ? 64 : 32`, `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) - (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*((((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1)))) + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2)) + (aoffi==`AOFFI@AOFFI) + (dc==`DC@DC))>2) ? 64 : 32`, `(((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) + (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*((((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1))!=1)))*32` |
| `ISRC_B_OPERAND_MAP` | `(1<<INDEX(Rb))` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_B_SIZE` | `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) - (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*((((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1)))) + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2)) + (aoffi==`AOFFI@AOFFI) + (dc==`DC@DC) + 1)==4) ? 64 : 32`, `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@CUBE)*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*4))) - (((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)*((((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1)))) + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2)) + (aoffi==`AOFFI@AOFFI) + (dc==`DC@DC))==4) ? 64 : 32`, `((aoffi==`AOFFI@AOFFI)*32 + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1))*32 + (dc==`DC@DC)*32)`, `(32 + (aoffi==`AOFFI@AOFFI)*32 + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1))*32 + (dc==`DC@DC)*32)` |
| `ISRC_C_OPERAND_MAP` | `(1<<INDEX(URc))`, `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)`, `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_C_SIZE` | `0`, `64` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@TEX`, ``SIDL_NAMES@TEX_B`, ``SIDL_NAMES@TEX_B_noConst`, ``SIDL_NAMES@TEX_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`tex_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [60:60] | `scr` | 1 | 0 |
| [59:59] | `b` | 1 | 0 |
| [80:79] | `sem` | 2 | `f16rm` |
| [89:87] | `Pp` | 3 | `lodlc` |
| [76:76] | `private` | 1 | `aoffi` |
| [78:78] | `ofmt` | 1 | `dc` |
| [86:84] | `cop` | 3 | `cop` |
| [77:77] | `ntz` | 1 | `ndv` |
| [90:90] | `input_reg_sz_32_dist` | 1 | `nodep` |
| [83:81] | `Pu` | 3 | `Pu` |
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
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_b_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_b_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_scr_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_scr_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | None |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed uniform register URc |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed uniform register URc |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: CUBE) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: 3D) |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: ndv_only) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: fdv_only) |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Descriptor contents beyond the operand behavior are not decoded here.
