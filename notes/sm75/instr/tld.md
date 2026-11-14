# TLD — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

## Conclusion

Direct LOD texel fetch; subpassLoad lowers to a zero-LOD array-texture fetch.

## Graphics-observed semantics

`subpassLoad(input_color)` lowers to `TLD`, not `TEX`, `SULD`, or `LDG`:

```text
TLD.SCR.LZ.NODEP R2, R0, R6, R5, 0x1e, 0x0, ARRAY_2D
```

The input attachment is represented as an `ARRAY_2D` texture:

- `a[0x64]` supplies the attachment layer.
- `a[0x70]/a[0x74]` supply fragment X/Y.
- `.LZ` selects LOD zero.
- the result is written to `R0..R3`.

sm120 uses the same array fetch after descriptor unpacking:

```text
LDCU.HDRUNPACK UR4, c[0x1e][URZ]
TLD.SCR.LZ.NODEP R2, R0, R6, R5, UR4, ARRAY_2D
```

This path bypasses the sampler filtering used by `TEX`.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `tld_` | `0xb66` | `/F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_b_` | `0xb66` | `[/b] /F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:tsPtrIdx PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_b_noConst_` | `0x367` | `[/b] /F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_b_tid_` | `0xb68` | `[/b] /F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:hdrtblbase6 *:tid8 PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_scr_` | `0xb66` | `[/scr] /F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_scr_b_` | `0xb66` | `[/scr] [/b] /F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:tsPtrIdx PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_scr_b_noConst_` | `0x367` | `[/scr] [/b] /F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_scr_b_tid_` | `0xb68` | `[/scr] [/b] /F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb *:bank5 *:hdrtblbase6 *:tid8 PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_scr_urc_` | `0x1f66` | `[/scr] /F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb NonZeroUniformRegister:URc *:tid8 PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |
| `tld_urc_` | `0x1f66` | `/F16RM("nof16rm"):f16rm [/lodlc] /AOFFI("noaoffi"):aoffi /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb NonZeroUniformRegister:URc *:tid8 PARAMA_ARRAY_2D_ARRAY_1D_2D_1D_3D:paramA *:wmsk` |

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
| `ISRC_A_SIZE` | `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3))) + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)) + (aoffi==`AOFFI@AOFFI) + (ms==`MS@MS) + 1)>2) ? 64 : 32`, `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3))) + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)) + (aoffi==`AOFFI@AOFFI) + (ms==`MS@MS))>2) ? 64 : 32`, `((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3)))*32` |
| `ISRC_B_OPERAND_MAP` | `(1<<INDEX(Rb))` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_B_SIZE` | `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3))) + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)) + (aoffi==`AOFFI@AOFFI) + (ms==`MS@MS) + 1)==4) ? 64 : 32`, `((((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@"3D")*3) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3))) + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1)) + (aoffi==`AOFFI@AOFFI) + (ms==`MS@MS))==4) ? 64 : 32`, `((aoffi==`AOFFI@AOFFI)*32 + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1))*32 + (ms==`MS@MS)*32)`, `(32 + (aoffi==`AOFFI@AOFFI)*32 + (((lodlc==`LODLC@LB)*1 + (lodlc==`LODLC@LL)*1 + (lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*2) - ((lodlc==`LODLC@LC)*1 + (lodlc==`LODLC@"LC.FDV")*1 + (lodlc==`LODLC@"LB.LC")*1))*32 + (ms==`MS@MS)*32)` |
| `ISRC_C_OPERAND_MAP` | `(1<<INDEX(URc))`, `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)`, `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_C_SIZE` | `0`, `64` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@TLD`, ``SIDL_NAMES@TLD_B`, ``SIDL_NAMES@TLD_B_noConst`, ``SIDL_NAMES@TLD_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`tld_`); other classes differ
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
| [86:84] | `cop` | 3 | `cop` |
| [78:78] | `ofmt` | 1 | `ms` |
| [77:77] | `ntz` | 1 | `cl` |
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
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_b_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_b_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_b_tid_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_b_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_scr_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_scr_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value"ILLEGAL_INSTR_ENCODING_ERROR |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | More than 4 coordinates are not allowed for .SCR |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed uniform register URc |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed uniform register URc |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination ( rule name: MS) |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Other TLD modes such as shadow/compare variants were not isolated in this Vulkan probe.
