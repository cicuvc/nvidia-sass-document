# SULD — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

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
| `suld_d_imm_` | `0xb99` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] *:bank5 *:tsPtrIdx` |
| `suld_d_imm_weakonly_` *(ALT)* | `0xb99` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] *:bank5 *:tsPtrIdx` |
| `suld_d_reg_` | `0x99a` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] NonZeroRegister:Rc` |
| `suld_d_reg_weakonly_` *(ALT)* | `0x99a` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] NonZeroRegister:Rc` |
| `suld_d_tid_` | `0x799` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] *:bank5 *:hdrtblbase6 *:tid8` |
| `suld_d_tid_weakonly_` *(ALT)* | `0x799` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] *:bank5 *:hdrtblbase6 *:tid8` |
| `suld_d_urc_` | `0x1f99` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] :URc *:tid8` |
| `suld_d_urc_weakonly_` *(ALT)* | `0x1f99` | `[/d] /BA("noba"):ba [/dim] /COP("EN"):cop /SZ_U8_S8_U16_S16_32_64_128("32"):sz /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] :URc *:tid8` |
| `suld_p_imm_` | `0xb97` | `[/p] [/dim] /COP("EN"):cop /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] *:bank5 *:tsPtrIdx` |
| `suld_p_imm_weakonly_` *(ALT)* | `0xb97` | `[/p] [/dim] /COP("EN"):cop /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] *:bank5 *:tsPtrIdx` |
| `suld_p_reg_` | `0x998` | `[/p] [/dim] /COP("EN"):cop /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] NonZeroRegister:Rc` |
| `suld_p_reg_weakonly_` *(ALT)* | `0x998` | `[/p] [/dim] /COP("EN"):cop /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] NonZeroRegister:Rc` |
| `suld_p_tid_` | `0x797` | `[/p] [/dim] /COP("EN"):cop /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] *:bank5 *:hdrtblbase6 *:tid8` |
| `suld_p_tid_weakonly_` *(ALT)* | `0x797` | `[/p] [/dim] /COP("EN"):cop /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] *:bank5 *:hdrtblbase6 *:tid8` |
| `suld_p_urc_` | `0x1f97` | `[/p] [/dim] /COP("EN"):cop /SEM_WEAK_STRONG_MMIO("WEAK"):sem [/sco] /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] :URc *:tid8` |
| `suld_p_urc_weakonly_` *(ALT)* | `0x1f97` | `[/p] [/dim] /COP("EN"):cop /WEAKONLY("WEAK"):sem /PRIVATE("noprivate"):private /RGBA("RGBA"):rgba /Clamp1("NEAR"):clamp :Pu :Rd [ NonZeroRegister:Ra ] :URc *:tid8` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST2_SIZE` | `0` |
| `IDEST_OPERAND_MAP` | `(1<<INDEX(Rd))` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_GENERIC)` |
| `IDEST_SIZE` | `(( sz <= 4 ) ? 1 : ( ( sz == 5 ) ? 2 : 4 ))*32`, `((((rgba==`RGBA@R))*1+ ((rgba==`RGBA@RG))*2+ ((rgba==`RGBA@RGBA))*4))*32` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_MISALIGNED_ADDR)+(1<<IERROR_MISALIGNED_REG)+(1<<IERROR_OOR_ADDR)+(1<<IERROR_OOR_REG)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<INDEX(Ra))` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_SURFACE_COORDINATES)` |
| `ISRC_A_SIZE` | `((dim<2) + ((dim==2)*2) + ((dim==3)*2) + ((dim>3)*3))*32` |
| `ISRC_B_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_B_SIZE` | `0` |
| `ISRC_C_OPERAND_MAP` | `(1<<INDEX(Rc))`, `(1<<INDEX(URc))`, `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)`, `(1<<IOPERAND_TYPE_TEX)` |
| `ISRC_C_SIZE` | `0`, `32` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@SULD_D_I`, ``SIDL_NAMES@SULD_D_R`, ``SIDL_NAMES@SULD_D_TID`, ``SIDL_NAMES@SULD_D_URb`, ``SIDL_NAMES@SULD_P_I`, … (+3) |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`suld_d_imm_`); other classes differ
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
| [83:81] | `Pu` | 3 | `Pu` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | *Ra |
| [58:54] | `Sb_bank` | 5 | `bank5` |
| [53:40] | `Sb_addr` | 14 | `tsPtrIdx MULTIPLY 4 SCALE 4` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_imm_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_imm_weakonly_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_reg_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_reg_weakonly_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_tid_weakonly_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed specification: UR in surface instructions should have 64-bit alignment |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_d_urc_weakonly_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_d_urc_weakonly_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_d_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_d_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed specification: UR in surface instructions should have 64-bit alignment |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_imm_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_imm_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_imm_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_imm_weakonly_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_imm_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_imm_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_reg_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_reg_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_reg_weakonly_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rc is out of range |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rc |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_reg_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_reg_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_tid_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_tid_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_tid_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_tid_weakonly_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_tid_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_tid_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sem field value |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed specification: UR in surface instructions should have 64-bit alignment |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid dim field value |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rgba field value |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid clamp field value |
| `suld_p_urc_weakonly_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `suld_p_urc_weakonly_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register is out of range |
| `suld_p_urc_weakonly_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `suld_p_urc_weakonly_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed specification: UR in surface instructions should have 64-bit alignment |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The surface-header table base and selector-to-header lookup remain unresolved.
