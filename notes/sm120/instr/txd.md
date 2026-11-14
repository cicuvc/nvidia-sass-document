# TXD — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

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
| `txd_b_noConst_` | `0x1d6d` | `[/b] /RM16("norm16"):rm16 /LC("nolc"):lc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb :URe PARAMA_ARRAY_2D_ARRAY_1D_2D_1D:paramA *:wmsk` |
| `txd_b_urc_` | `0x1f6d` | `[/b] /RM16("norm16"):rm16 /LC("nolc"):lc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb :URc :URe PARAMA_ARRAY_2D_ARRAY_1D_2D_1D:paramA *:wmsk` |
| `txd_urc_` | `0x1f6c` | `/RM16("norm16"):rm16 /LC("nolc"):lc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb :URc :URe @:tid8 PARAMA_ARRAY_2D_ARRAY_1D_2D_1D:paramA *:wmsk` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32 + (((rm16==`RM16@norm16)) && ((wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"3") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"5") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"6") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"7") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"9") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"10") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"11") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"12") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"13") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"14") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"15")))*32` |
| `ILABEL_Ra_SIZE` | `32 + ((((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*32)`, `64 + ((((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*32)` |
| `ILABEL_Rb_SIZE` | `64 + ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D) || (paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D"))*64` |
| `ILABEL_URc_SIZE` | `64` |
| `ILABEL_URe_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32 + ((((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*32)`, `64 + ((((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"1D")))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D")))*64 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_1D)))*32 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@LC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((lc==`LC@nolc) || (lc==`LC@ULC)) && ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D)))*32)` |
| `ISRC_B_SIZE` | `64 + ((paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@ARRAY_2D) || (paramA==`PARAMA_ARRAY_2D_ARRAY_1D_2D_1D@"2D"))*64` |
| `ISRC_C_SIZE` | `64` |
| `ISRC_E_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@TXD_B_URc`, ``SIDL_NAMES@TXD_B_noConst`, ``SIDL_NAMES@TXD_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`txd_b_noConst_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [80:79] | `rm16` | 2 | `rm16` |
| [88:87] | `lodlc` | 2 | `lc` |
| [57:56] | `aoffi` | 2 | `aoffi` |
| [58:58] | `uai` | 1 | `uai` |
| [86:84] | `cop` | 3 | `cop` |
| [90:90] | `memdesc` | 1 | `nodep` |
| [83:81] | `Pu` | 3 | `Pu` |
| [71:64] | `Ra_URc` | 8 | `Rd2` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [39:32] | `Rb` | 8 | `Rb` |
| [55:48] | `URe` | 8 | `URe` |
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
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lc field value |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_AOFFI) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_AOFFI) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_AOFFI) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lc field value |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `txd_b_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `txd_b_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_AOFFI) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_AOFFI) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_AOFFI) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lc field value |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
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
| `txd_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_AOFFI) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_AOFFI) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_AOFFI) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_1D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY_2D) |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `txd_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI, ULC and UAOFFI cannot be specified together) |
| `txd_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

No instruction-specific open item from the local graphics probes.
