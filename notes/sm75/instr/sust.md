# SUST — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

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
| `sust_d_imm_` | `0xb9d` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb *:bank5 *:tsPtrIdx` |
| `sust_d_imm_weakonly_` *(ALT)* | `0xb9d` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb *:bank5 *:tsPtrIdx` |
| `sust_d_reg_` | `0x99e` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb NonZeroRegister:Rc` |
| `sust_d_reg_weakonly_` *(ALT)* | `0x99e` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb NonZeroRegister:Rc` |
| `sust_d_tid_` | `0x79d` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb *:bank5 *:hdrtblbase6 *:tid8` |
| `sust_d_tid_weakonly_` *(ALT)* | `0x79d` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb *:bank5 *:hdrtblbase6 *:tid8` |
| `sust_d_urc_` | `0x1f9d` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb :URc *:tid8` |
| `sust_d_urc_weakonly_` *(ALT)* | `0x1f9d` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb :URc *:tid8` |
| `sust_p_imm_` | `0xb9b` | `[/p] [/dim] /COP("EN"):cop /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb *:bank5 *:tsPtrIdx` |
| `sust_p_imm_weakonly_` *(ALT)* | `0xb9b` | `[/p] [/dim] /COP("EN"):cop /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb *:bank5 *:tsPtrIdx` |
| `sust_p_reg_` | `0x99c` | `[/p] [/dim] /COP("EN"):cop /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb NonZeroRegister:Rc` |
| `sust_p_reg_weakonly_` *(ALT)* | `0x99c` | `[/p] [/dim] /COP("EN"):cop /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb NonZeroRegister:Rc` |
| `sust_p_tid_` | `0x79b` | `[/p] [/dim] /COP("EN"):cop /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb *:bank5 *:hdrtblbase6 *:tid8` |
| `sust_p_tid_weakonly_` *(ALT)* | `0x79b` | `[/p] [/dim] /COP("EN"):cop /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb *:bank5 *:hdrtblbase6 *:tid8` |
| `sust_p_urc_` | `0x1f9b` | `[/p] [/dim] /COP("EN"):cop /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb :URc *:tid8` |
| `sust_p_urc_weakonly_` *(ALT)* | `0x1f9b` | `[/p] [/dim] /COP("EN"):cop /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp [ NonZeroRegister:Ra ] :Rb :URc *:tid8` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST2_SIZE` | `0` |
| `IDEST_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST_SIZE` | `0` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_MISALIGNED_ADDR)+(1<<IERROR_MISALIGNED_REG)+(1<<IERROR_OOR_ADDR)+(1<<IERROR_OOR_REG)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<INDEX(Ra))` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_SURFACE_COORDINATES)` |
| `ISRC_A_SIZE` | `((dim<2) + ((dim==2)*2) + ((dim==3)*2) + ((dim>3)*3))*32` |
| `ISRC_B_OPERAND_MAP` | `(1<<INDEX(Rb))` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_GENERIC)` |
| `ISRC_B_SIZE` | `(( sz <= 4 ) ? 1 : ( ( sz == 5 ) ? 2 : 4 ))*32`, `((((rgba==`RGBA@R))*1+ ((rgba==`RGBA@RG))*2+ ((rgba==`RGBA@RGBA))*4))*32` |
| `ISRC_C_OPERAND_MAP` | `(1<<INDEX(Rc))`, `(1<<INDEX(URc))`, `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)`, `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_C_SIZE` | `0`, `32` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@SUST_D_I`, ``SIDL_NAMES@SUST_D_R`, ``SIDL_NAMES@SUST_D_TID`, ``SIDL_NAMES@SUST_D_URb`, ``SIDL_NAMES@SUST_P_I`, … (+3) |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_SUST` |

## Encoding

Bit map of the first layout (`sust_d_imm_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [72:72] | `e` | 1 | `ba` |
| [63:61] | `dim` | 3 | `dim` |
| [86:84] | `cop` | 3 | `cop` |
| [75:73] | `sz` | 3 | `sz` |
| [80:79] | `sem` | 2 | `sem` |
| [78:77] | `sco` | 2 | `sco` |
| [76:76] | `private` | 1 | `private` |
| [60:59] | `clamp` | 2 | `clamp` |
| [31:24] | `Ra` | 8 | *Ra |
| [39:32] | `Rb` | 8 | `Rb` |
| [58:54] | `Sb_bank` | 5 | `bank5` |
| [53:40] | `Sb_addr` | 14 | `tsPtrIdx MULTIPLY 4 SCALE 4` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | 7 |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed specification: UR in surface instructions should have 64-bit alignment |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_d_urc_weakonly_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_d_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed specification: UR in surface instructions should have 64-bit alignment |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed specification: UR in surface instructions should have 64-bit alignment |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `sust_p_urc_weakonly_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `sust_p_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `sust_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed specification: UR in surface instructions should have 64-bit alignment |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Selector-to-backing-allocation lookup remains driver/hardware-internal.
