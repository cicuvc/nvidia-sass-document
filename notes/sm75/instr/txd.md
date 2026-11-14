# TXD — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

## Conclusion

Gradient texture fetch consuming an explicit 2D X/Y gradient pair.

## Graphics-observed semantics

`textureGrad()` lowers to `TXD`:

```text
TXD.NODEP R2, R0, R4, R8, 0x1e, 0x0, 2D
```

`Ra=R4` supplies coordinates and `Rb=R8..R11` supplies the 128-bit gradient
pair `{dX.xy, dY.xy}`. The shader first constructs this pair using the same
`SHFL.BFLY` + `FSWZADD` derivative sequence used by `dFdx/dFdy`.

Unlike `TEX`, `TXD` does not derive LOD from implicit screen derivatives.
sm120 uses the same gradient operand and adds `.DXY` to the derivative
combine instructions:

```text
TXD.NODEP R2, R0, R4, R8, UR4, 2D
```

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `txd_` | `0xb6c` | `/F16RM("nof16rm"):f16rm /LC("nolc"):lc /AOFFI("noaoffi"):aoffi /COP("EN"):cop /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx PARAMA_ARRAY_2D_ARRAY_1D_2D_1D:paramA *:wmsk` |
| `txd_b_` | `0xb6c` | `[/b] /F16RM("nof16rm"):f16rm /LC("nolc"):lc /AOFFI("noaoffi"):aoffi /COP("EN"):cop /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb *:bank5 *:tsPtrIdx PARAMA_ARRAY_2D_ARRAY_1D_2D_1D:paramA *:wmsk` |
| `txd_b_noConst_` | `0x36d` | `[/b] /F16RM("nof16rm"):f16rm /LC("nolc"):lc /AOFFI("noaoffi"):aoffi /COP("EN"):cop /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb PARAMA_ARRAY_2D_ARRAY_1D_2D_1D:paramA *:wmsk` |
| `txd_b_tid_` | `0xb6e` | `[/b] /F16RM("nof16rm"):f16rm /LC("nolc"):lc /AOFFI("noaoffi"):aoffi /COP("EN"):cop /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb *:bank5 *:hdrtblbase6 *:tid8 PARAMA_ARRAY_2D_ARRAY_1D_2D_1D:paramA *:wmsk` |
| `txd_urc_` | `0x1f6c` | `/F16RM("nof16rm"):f16rm /LC("nolc"):lc /AOFFI("noaoffi"):aoffi /COP("EN"):cop /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb NonZeroUniformRegister:URc *:tid8 PARAMA_ARRAY_2D_ARRAY_1D_2D_1D:paramA *:wmsk` |

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
| `ISRC_A_SIZE` | `((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3)))*32 + (((lc==`LC@LC)||(aoffi==`AOFFI@AOFFI)) - (((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1)))*32*((lc==`LC@LC)||(aoffi==`AOFFI@AOFFI))`, `32 + ((((paramA==`TEXPARAMA@"1D")*1) + ((paramA==`TEXPARAMA@"2D")*2) + ((paramA==`TEXPARAMA@ARRAY_1D)*2) + ((paramA==`TEXPARAMA@ARRAY_2D)*3)))*32 + (((lc==`LC@LC)||(aoffi==`AOFFI@AOFFI)) - (((paramA==`TEXPARAMA@ARRAY_1D)*1) + ((paramA==`TEXPARAMA@ARRAY_2D)*1) + ((paramA==`TEXPARAMA@ARRAY_CUBE)*1)))*32*((lc==`LC@LC)||(aoffi==`AOFFI@AOFFI))` |
| `ISRC_B_OPERAND_MAP` | `(1<<INDEX(Rb))` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_B_SIZE` | `64 + ((paramA==`TEXPARAMA@"2D")||(paramA==`TEXPARAMA@"ARRAY_2D"))*64` |
| `ISRC_C_OPERAND_MAP` | `(1<<INDEX(URc))`, `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)`, `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_C_SIZE` | `0`, `64` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@TXD`, ``SIDL_NAMES@TXD_B`, ``SIDL_NAMES@TXD_B_noConst`, ``SIDL_NAMES@TXD_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`txd_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [59:59] | `b` | 1 | 0 |
| [80:79] | `sem` | 2 | `f16rm` |
| [87:87] | `cas` | 1 | `lc` |
| [76:76] | `private` | 1 | `aoffi` |
| [86:84] | `cop` | 3 | `cop` |
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
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `txd_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `txd_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `txd_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `txd_b_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `txd_b_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_tid_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid f16rm field value |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `txd_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `txd_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `txd_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed uniform register URc |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

No instruction-specific open item from the local graphics probes.
