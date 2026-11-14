# FOOTPRINT — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe_fragment_footprint*.frag`, `vulkan_graphics.c`, `extract_pipeline_binary.py`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

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
| `footprint_b_noConst_` | `0x1d73` | `[/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb PARAMA_2D_3D:paramA` |
| `footprint_b_urc_` | `0x1f73` | `[/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb :URc PARAMA_2D_3D:paramA` |
| `footprint_scr_b_noConst_` | `0x1d73` | `[/scr] [/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb PARAMA_2D_3D:paramA` |
| `footprint_scr_b_urc_` | `0x1f73` | `[/scr] [/b] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra NonZeroRegister:Rb :URc PARAMA_2D_3D:paramA` |
| `footprint_scr_uniform_` | `0x1f74` | `[/scr] [/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra :Rb :URc @:tid8 PARAMA_2D_3D:paramA` |
| `footprint_uniform_` | `0x1f74` | `[/mode] /LODCTRL("FINE"):lodctrl /LODLC("nolodlc"):lodlc /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu NonZeroRegister:Rd2 NonZeroRegister:Rd NonZeroRegister:Ra :Rb :URc @:tid8 PARAMA_2D_3D:paramA` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_SIZE` | `64` |
| `IDEST_SIZE` | `64` |
| `ILABEL_Ra_SIZE` | `64`, `96 + ((((mode==`MODE_FOOTPRINT@TXD)) && ((paramA==`PARAMA_2D_3D@"2D")))*32 + ((paramA==`PARAMA_2D_3D@"3D"))*32)`, `96 + ((paramA==`PARAMA_2D_3D@"3D"))*32` |
| `ILABEL_Rb_SIZE` | `32 + ((((mode==`MODE_FOOTPRINT@TEX)) && ((lodlc==`LODLC@LB) || (lodlc==`LODLC@LL) || (lodlc==`LODLC@LB.LC)))*32 + ((mode==`MODE_FOOTPRINT@TXD))*96)`, `32 + ((((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@nolodlc)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LZ)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LC)))*32)`, `32 + ((((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"3D")) && ((lodlc==`LODLC@nolodlc)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"3D")) && ((lodlc==`LODLC@LZ)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LB)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LL)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"3D")) && ((lodlc==`LODLC@LC)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LB.LC)))*32)` |
| `ILABEL_URc_SIZE` | `64` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `64`, `96 + ((((mode==`MODE_FOOTPRINT@TXD)) && ((paramA==`PARAMA_2D_3D@"2D")))*32 + ((paramA==`PARAMA_2D_3D@"3D"))*32)`, `96 + ((paramA==`PARAMA_2D_3D@"3D"))*32` |
| `ISRC_B_SIZE` | `32 + ((((mode==`MODE_FOOTPRINT@TEX)) && ((lodlc==`LODLC@LB) || (lodlc==`LODLC@LL) || (lodlc==`LODLC@LB.LC)))*32 + ((mode==`MODE_FOOTPRINT@TXD))*96)`, `32 + ((((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@nolodlc)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LZ)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LC)))*32)`, `32 + ((((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"3D")) && ((lodlc==`LODLC@nolodlc)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"3D")) && ((lodlc==`LODLC@LZ)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LB)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LL)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"3D")) && ((lodlc==`LODLC@LC)))*32 + (((mode==`TEXONLY@TEX)) && ((paramA==`PARAMA_2D_3D@"2D")) && ((lodlc==`LODLC@LB.LC)))*32)` |
| `ISRC_C_SIZE` | `64` |
| `ISRC_E_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@FOOTPRINT_B_URc`, ``SIDL_NAMES@FOOTPRINT_B_noConst`, ``SIDL_NAMES@FOOTPRINT_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_FTPRNT` |

## Encoding

Bit map of the first layout (`footprint_b_noConst_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [60:60] | `scr` | 1 | 0 |
| [78:78] | `mode` | 1 | `mode` |
| [57:57] | `lodctrl` | 1 | `lodctrl` |
| [89:87] | `Pp` | 3 | `lodlc` |
| [77:76] | `op` | 2 | `div` |
| [90:90] | `memdesc` | 1 | `nodep` |
| [83:81] | `Pu` | 3 | `Pu` |
| [71:64] | `Ra_URc` | 8 | `Rd2` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [39:32] | `Rb` | 8 | `Rb` |
| [55:48] | `URe` | 8 | *255 |
| [63:61] | `paramA` | 3 | `paramA` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
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
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TXD_paramA) |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: When TXD is specified divergence cannot be specified) |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_TEX_Ra) |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_TXD_Ra) |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_Ra) |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: no_LOD) |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD) |
| `footprint_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TXD_Rb) |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_b_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_b_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `footprint_b_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TXD_paramA) |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: When TXD is specified divergence cannot be specified) |
| `footprint_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_TEX_Ra) |
| `footprint_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_TXD_Ra) |
| `footprint_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_Ra) |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: no_LOD) |
| `footprint_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD) |
| `footprint_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TXD_Rb) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
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
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Rb can't be RZ) |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .TXD may not be specified with .SCR) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LZ) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_2D_LB) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LB) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_2D_LL) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LL) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LC) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_2D_LBLC) |
| `footprint_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LBLC) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register Rd2 is misaligned |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd2 |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register Rd is misaligned |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rd |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register Ra is misaligned |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Rb can't be RZ) |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .TXD may not be specified with .SCR) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LZ) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_2D_LB) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LB) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_2D_LL) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LL) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LC) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_2D_LBLC) |
| `footprint_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LBLC) |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
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
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Rb can't be RZ) |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_scr_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .TXD may not be specified with .SCR) |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LB) |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LL) |
| `footprint_scr_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_3D_LBLC) |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
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
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TXD_paramA) |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: When TXD is specified divergence cannot be specified) |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_TEX_Ra) |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_TXD_Ra) |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_Ra) |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TEX_Rb) |
| `footprint_uniform_` | `OOR_REG_ERROR` | Register is out of range |
| `footprint_uniform_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `footprint_uniform_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: TXD_Rb) |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The full granularity-code table is supplied by the NV extension specification and was not independently enumerated.
