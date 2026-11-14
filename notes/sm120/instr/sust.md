# SUST — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Surface/image store with the same descriptor-selection model as SULD.

## Graphics-observed semantics

`imageStore()` lowers to `SUST`, using the same coordinate and descriptor
inputs as the matching `SULD`:

```text
SUST.P.2D.CTA.IGN [R4], R8, 0x1e, 0x0
```

- `Ra=R4`: integer X/Y coordinate pair.
- `Rb=R8`: source component quad.
- immediate `0x1e, 0x0`: surface-header selector.

The bindless form replaces the immediate with a register selector:

```text
LDC R8, c[0x1e][R8]
SUST.P.2D.CTA.IGN [R6], R0, R8
```

sm120 likewise uses `LDCU`/`ULOP3` and an optional `R2UR` path for nonuniform
descriptor selection.

There is no generic `STG` in the shader. The texture/surface unit resolves the
selector, format, tiling and address calculation. CUDA interop confirmed that
the eventual backing allocation is device memory addressable through a CUDA
device pointer, with tiling applied by the surface path.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `sust_d_r_urc_` | `0x1f9e` | `[/d] /BA("noba"):ba [/dim] /UAI("nouai"):uai /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb NonZeroRegister:Rc :URc :URe` |
| `sust_d_reg_` | `0x99e` | `[/d] /BA("noba"):ba [/dim] /UAI("nouai"):uai /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb NonZeroRegister:Rc :URe` |
| `sust_d_urc_` | `0x1f9d` | `[/d] /BA("noba"):ba [/dim] /UAI("nouai"):uai /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb :URc :URe @:tid8` |
| `sust_p_r_urc_` | `0x1f9c` | `[/p] [/dim] /UAI("nouai"):uai /COP("EN"):cop /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb NonZeroRegister:Rc :URc :URe` |
| `sust_p_reg_` | `0x99c` | `[/p] [/dim] /UAI("nouai"):uai /COP("EN"):cop /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb NonZeroRegister:Rc :URe` |
| `sust_p_urc_` | `0x1f9b` | `[/p] [/dim] /UAI("nouai"):uai /COP("EN"):cop /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb :URc :URe @:tid8` |

## Properties

| property | value(s) |
|---|---|
| `ILABEL_Ra_SIZE` | `32 + ((((uai==`UAI@nouai) || (uai==`UAI@UAI)) && ((dim==`Dim1@"2D")))*32 + (((uai==`UAI@nouai)) && ((dim==`Dim1@"1D_ARRAY")))*32 + (((uai==`UAI@UAI)) && ((dim==`Dim1@"2D_ARRAY")))*32 + (((uai==`UAI@nouai)) && ((dim==`Dim1@"2D_ARRAY")))*64 + (((uai==`UAI@nouai) || (uai==`UAI@UAI)) && ((dim==`Dim1@"3D")))*64)` |
| `ILABEL_Rb_SIZE` | `32 + (((rgba==`RGBA@RG))*32 + ((rgba==`RGBA@RGBA))*96)`, `32 + (((sz==`SZ_U8_S8_U16_S16_32_64_128@"64"))*32 + ((sz==`SZ_U8_S8_U16_S16_32_64_128@"128"))*96)` |
| `ILABEL_Rc_SIZE` | `32` |
| `ILABEL_URc_SIZE` | `32` |
| `ILABEL_URe_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_SCBD` |
| `ISRC_A_SIZE` | `32 + ((((uai==`UAI@nouai) || (uai==`UAI@UAI)) && ((dim==`Dim1@"2D")))*32 + (((uai==`UAI@nouai)) && ((dim==`Dim1@"1D_ARRAY")))*32 + (((uai==`UAI@UAI)) && ((dim==`Dim1@"2D_ARRAY")))*32 + (((uai==`UAI@nouai)) && ((dim==`Dim1@"2D_ARRAY")))*64 + (((uai==`UAI@nouai) || (uai==`UAI@UAI)) && ((dim==`Dim1@"3D")))*64)` |
| `ISRC_B_SIZE` | `32 + (((rgba==`RGBA@RG))*32 + ((rgba==`RGBA@RGBA))*96)`, `32 + (((sz==`SZ_U8_S8_U16_S16_32_64_128@"64"))*32 + ((sz==`SZ_U8_S8_U16_S16_32_64_128@"128"))*96)` |
| `ISRC_C_SIZE` | `32` |
| `ISRC_E_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@SUST_D_R`, ``SIDL_NAMES@SUST_D_R_URc`, ``SIDL_NAMES@SUST_D_URb`, ``SIDL_NAMES@SUST_P_R`, ``SIDL_NAMES@SUST_P_R_URc`, … (+1) |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_SUST` |

## Encoding

Bit map of the first layout (`sust_d_r_urc_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [72:72] | `e` | 1 | `ba` |
| [63:61] | `paramA` | 3 | `dim` |
| [58:58] | `uai` | 1 | `uai` |
| [86:84] | `cop` | 3 | `cop` |
| [75:73] | `sz` | 3 | `sz` |
| [60:59] | `clamp` | 2 | `clamp` |
| [31:24] | `Ra` | 8 | `Ra` |
| [39:32] | `Rb` | 8 | `Rb` |
| [71:64] | `Ra_URc` | 8 | `Rc` |
| [47:40] | `Re` | 8 | `URc` |
| [55:48] | `URe` | 8 | `URe` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | 7 |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [80:77] | `mem` | 4 | TABLES_mem_0(sem,sco,private) |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `sust_d_reg_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `sust_d_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `sust_p_reg_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `sust_p_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `sust_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Selector-to-backing-allocation lookup remains driver/hardware-internal.
