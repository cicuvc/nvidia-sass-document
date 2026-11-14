# SULD — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Surface/image load; descriptor selection is separate from the X/Y coordinate operand.

## Graphics-observed semantics

`imageLoad()` lowers to a surface load. A representative sm75 form is:

```text
SULD.P.2D.CTA.IGN R0, [R4], 0x1e, 0x0
```

- `Rd=R0`: destination quad.
- `Ra=R4`: integer X/Y coordinate pair.
- `0x1e, 0x0`: constant-bank location selecting the surface header.
- `.P`, `.2D`, `.CTA`, and `.IGN`: predicate, dimensionality,
  memory-scope/order controls in the emitted form.

The instruction does not contain a linear byte address. Bindless storage
images use a register descriptor instead:

```text
LDC R8, c[0x1e][R8]
SULD.P.2D.CTA.IGN R0, [R6], R8
```

The dynamic index is scaled and masked before `LDC`. In the tested image all
array entries referenced the same view, so all captured selectors were `9`.

sm120 loads the descriptor through `LDCU`, masks it to 20 bits, and can move it
to a uniform register with `R2UR`:

```text
LDCU UR4, c[0x1e][URZ]
SULD.P.2D.IGN R0, [R4], UR4
```

## Backing-address findings

CUDA external-memory interop proved that the backing allocation is ordinary
device memory. For a 64x64 RGBA8 optimal image, the CUDA-visible base plus a
recovered tiling bit permutation addressed every texel. The selector itself is
not a VA; conversion continues inside the hardware surface-header path.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `suld_d_r_urc_` | `0x1f9a` | `[/d] /BA("noba"):ba [/dim] /UAI("nouai"):uai /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] NonZeroRegister:Rc :URc :URe` |
| `suld_d_reg_` | `0x99a` | `[/d] /BA("noba"):ba [/dim] /UAI("nouai"):uai /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] NonZeroRegister:Rc :URe` |
| `suld_d_urc_` | `0x1f99` | `[/d] /BA("noba"):ba [/dim] /UAI("nouai"):uai /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] :URc :URe @:tid8` |
| `suld_p_r_urc_` | `0x1f98` | `[/p] [/dim] /UAI("nouai"):uai /COP("EN"):cop /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] NonZeroRegister:Rc :URc :URe` |
| `suld_p_reg_` | `0x998` | `[/p] [/dim] /UAI("nouai"):uai /COP("EN"):cop /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] NonZeroRegister:Rc :URe` |
| `suld_p_urc_` | `0x1f97` | `[/p] [/dim] /UAI("nouai"):uai /COP("EN"):cop /SEM("WEAK"):sem /SCO("nosco"):sco /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] :URc :URe @:tid8` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32 + (((rgba==`RGBA@RG))*32 + ((rgba==`RGBA@RGBA))*96)`, `32 + (((sz==`SZ_U8_S8_U16_S16_32_64_128@"64"))*32 + ((sz==`SZ_U8_S8_U16_S16_32_64_128@"128"))*96)` |
| `ILABEL_Ra_SIZE` | `32 + ((((uai==`UAI@nouai) || (uai==`UAI@UAI)) && ((dim==`Dim1@"2D")))*32 + (((uai==`UAI@nouai)) && ((dim==`Dim1@"1D_ARRAY")))*32 + (((uai==`UAI@UAI)) && ((dim==`Dim1@"2D_ARRAY")))*32 + (((uai==`UAI@nouai)) && ((dim==`Dim1@"2D_ARRAY")))*64 + (((uai==`UAI@nouai) || (uai==`UAI@UAI)) && ((dim==`Dim1@"3D")))*64)` |
| `ILABEL_Rc_SIZE` | `32` |
| `ILABEL_URc_SIZE` | `32` |
| `ILABEL_URe_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32 + ((((uai==`UAI@nouai) || (uai==`UAI@UAI)) && ((dim==`Dim1@"2D")))*32 + (((uai==`UAI@nouai)) && ((dim==`Dim1@"1D_ARRAY")))*32 + (((uai==`UAI@UAI)) && ((dim==`Dim1@"2D_ARRAY")))*32 + (((uai==`UAI@nouai)) && ((dim==`Dim1@"2D_ARRAY")))*64 + (((uai==`UAI@nouai) || (uai==`UAI@UAI)) && ((dim==`Dim1@"3D")))*64)` |
| `ISRC_C_SIZE` | `32` |
| `ISRC_E_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@SULD_D_R`, ``SIDL_NAMES@SULD_D_R_URc`, ``SIDL_NAMES@SULD_D_URb`, ``SIDL_NAMES@SULD_P_R`, ``SIDL_NAMES@SULD_P_R_URc`, … (+1) |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`suld_d_r_urc_`); other classes differ
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
| [83:81] | `Pu` | 3 | `Pu` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [71:64] | `Ra_URc` | 8 | `Rc` |
| [47:40] | `Re` | 8 | `URc` |
| [55:48] | `URe` | 8 | `URe` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [80:77] | `mem` | 4 | TABLES_mem_1(sem,sco,private) |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `suld_d_reg_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `suld_d_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_r_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_r_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_r_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `suld_p_reg_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `suld_p_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of sem, sco, private |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Illegal specification of sem, sco, private |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The surface-header table base and selector-to-header lookup remain unresolved.
