# IPA — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Pixel-shader attribute interpolation read from rasterizer-produced attribute memory.

## Graphics-observed semantics

`IPA` is the fragment-stage attribute interpolator. The compiled shader names
an attribute through the scaled `a[...]` address and receives one interpolated
component in a normal 32-bit GPR.

Observed Vulkan GLSL lowerings:

| source construct | sm75 lowering |
|---|---|
| `smooth in vec4` | four `IPA.PASS` reads plus `IPA.PASS a[0x7c]` perspective factor |
| perspective correction | `MUFU.RCP` of `a[0x7c]`, then component multiplies |
| `noperspective in vec4` | four `IPA.PASS` reads, with no perspective factor |
| `flat in vec4` | four `IPA.CONSTANT` reads |
| `centroid in vec4` | `IPA.PASS.CENTROID` |
| `interpolateAtOffset/Sample` | `IPA.PASS.OFFSET` with an evaluation offset |

The perspective divisor is explicit in the instruction stream. It is not a
separate top-level `IPA` mode. A shared smooth varying needs only one
`a[0x7c]` factor read.

In the tested fragment shaders, `BATCH_START` appears on the first shader
instruction, often the first `IPA` or a preceding constant move. No tested
fragment shader emitted a paired `BATCH_END`.

sm120 keeps the same source semantics and resource handling through uniform
registers where applicable. The generated variants below come from each
architecture's own ISA dump.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `ipa_` | `0x326` | `[/ipaop] /MSI_CENTER_CENTROID("CENTER"):msi :Rd :Pu A:srcAttr[ *:attr ]` |
| `ipa_offset__IPA_Ib` | `0x926` | `[/ipaop] [/msi] :Rd :Pu A:srcAttr[ *:attr ] *:Sb` |
| `ipa_offset__IPA_Rb` | `0x326` | `[/ipaop] [/msi] :Rd :Pu A:srcAttr[ *:attr ] :Rb` |
| `ipa_ur_` | `0x1526` | `[/ipaop] /MSI_CENTER_CENTROID("CENTER"):msi :Rd :Pu A:srcAttr[ :URa + *:URa_offset ]` |
| `ipa_ur_offset__IPA_URa_Ib` | `0x1926` | `[/ipaop] [/msi] :Rd :Pu A:srcAttr[ :URa + *:URa_offset ] *:Sb` |
| `ipa_ur_offset__IPA_URa_Rb` | `0x1526` | `[/ipaop] [/msi] :Rd :Pu A:srcAttr[ :URa + *:URa_offset ] :Rb` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32` |
| `ILABEL_Rb_SIZE` | `32` |
| `ILABEL_URa_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32`, `8` |
| `ISRC_B_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@IPA_Imm`, ``SIDL_NAMES@IPA_Rb`, ``SIDL_NAMES@IPA_URa_Ib`, ``SIDL_NAMES@IPA_URa_Rb` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_PS)+0` |
| `VIRTUAL_QUEUE` | `$VQ_IPA` |

## Encoding

Bit map of the first layout (`ipa_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [79:78] | `stride` | 2 | `ipaop` |
| [77:76] | `op` | 2 | *msi |
| [23:16] | `Rd` | 8 | `Rd` |
| [83:81] | `Pu` | 3 | `Pu` |
| [71:64] | `Ra_URc` | 8 | `attr SCALE 4` |
| [39:32] | `Rb` | 8 | *255 |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `ipa_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `ipa_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ipaop field value |
| `ipa_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ipa_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ipa_offset__IPA_Ib` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `ipa_offset__IPA_Ib` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ipaop field value |
| `ipa_offset__IPA_Ib` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ipa_offset__IPA_Ib` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ipa_offset__IPA_Rb` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `ipa_offset__IPA_Rb` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ipaop field value |
| `ipa_offset__IPA_Rb` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ipa_offset__IPA_Rb` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ipa_offset__IPA_Rb` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ipa_ur_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `ipa_ur_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ipaop field value |
| `ipa_ur_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ipa_ur_` | `OOR_REG_ERROR` | Uniform register URa is out of range |
| `ipa_ur_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ipa_ur_offset__IPA_URa_Ib` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `ipa_ur_offset__IPA_URa_Ib` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ipaop field value |
| `ipa_ur_offset__IPA_URa_Ib` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ipa_ur_offset__IPA_URa_Ib` | `OOR_REG_ERROR` | Uniform register URa is out of range |
| `ipa_ur_offset__IPA_URa_Ib` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ipa_ur_offset__IPA_URa_Rb` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `ipa_ur_offset__IPA_URa_Rb` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ipaop field value |
| `ipa_ur_offset__IPA_URa_Rb` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ipa_ur_offset__IPA_URa_Rb` | `OOR_REG_ERROR` | Uniform register URa is out of range |
| `ipa_ur_offset__IPA_URa_Rb` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ipa_ur_offset__IPA_URa_Rb` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

No direct test isolated every `IPA.STATE` use. Barycentric helper behavior is documented separately through `LDTRAM`.
