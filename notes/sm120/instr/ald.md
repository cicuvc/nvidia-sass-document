# ALD — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Graphics attribute-space load used for vertex inputs and draw builtins.

## Graphics-observed semantics

`ALD` loads from the graphics front-end attribute address space. Static
attributes use immediate `a[imm]`; dynamic arrays use a base plus register
offset.

Observed vertex mappings:

| source value | sm75 address |
|---|---|
| input `location=0` (`vec4`) | `a[0x80]` |
| input `location=1` (`vec4`) | `a[0x90]` |
| `gl_VertexIndex` | `a[0x2fc]` |
| raw instance ID | `a[0x2f8]` |

Representative lowering:

```text
ALD.128 R0, a[0x80]
ALD R4, a[0x90]
ALD R5, a[0x94]
ALD R6, a[0x98]
ALD R7, a[0x9c]
```

`ALD.128` consumes a naturally aligned four-register destination. Scalar
loads can gather individual components. Geometry/tessellation prologues can
feed an `ISBERD` result into the dynamic address form, for example
`ALD.128 ..., a[base], Roffset`.

This is not the CUDA parameter path (`LDC`) or the global-memory path (`LDG`).
It addresses the graphics stage's logical attribute storage.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `ald_PHYS_` | `0x321` | `/AIO("I"):io [/p] /ONLY32("32"):sz :Rd A:srcAttr[ NonZeroRegister:Ra ] :Rb` |
| `ald_UR__LOGICAL_URa_default` | `0x1521` | `/AIO("I"):io /AInteger("32"):sz :Rd A:srcAttr[ :URa + *:URa_offset ] :Rb` |
| `ald_UR__PATCH_URa_P_RbRZ` | `0x1521` | `/AIO("I"):io [/p] /AInteger("32"):sz :Rd A:srcAttr[ :URa + *:URa_offset ] ZeroRegister("RZ"):Rb` |
| `ald__LOGICAL_RaRZ_default` | `0x321` | `/AIO("I"):io /AInteger("32"):sz :Rd A:srcAttr[ ZeroRegister("RZ"):Ra + *:Ra_offset ] :Rb` |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `0x321` | `/AIO("I"):io [/p] /AInteger("32"):sz :Rd A:srcAttr[ NonZeroRegister:Ra + *:Ra_offset ] ZeroRegister("RZ"):Rb` |
| `ald__PATCH_RaRZ_P_RbRZ` | `0x321` | `/AIO("I"):io [/p] /AInteger("32"):sz :Rd A:srcAttr[ ZeroRegister("RZ"):Ra + *:Ra_offset ] ZeroRegister("RZ"):Rb` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32`, `32 + (((sz==`AInteger@"64"))*32 + ((sz==`AInteger@"96"))*64 + ((sz==`AInteger@"128"))*96)` |
| `ILABEL_Ra_SIZE` | `32` |
| `ILABEL_Rb_SIZE` | `32` |
| `ILABEL_URa_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32` |
| `ISRC_B_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@ALD`, ``SIDL_NAMES@ALD_URb` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_GS)+(1<<ISHADER_TI)+(1<<ISHADER_TS)+(1<<ISHADER_VS)+0` |
| `VIRTUAL_QUEUE` | `$VQ_AGU` |

## Encoding

Bit map of the first layout (`ald_PHYS_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [79:79] | `op` | 1 | `io` |
| [77:76] | `op` | 2 | *p |
| [75:74] | `iswzA` | 2 | `sz` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | *Ra |
| [39:32] | `Rb` | 8 | `Rb` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `ald_PHYS_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ald_PHYS_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ald_PHYS_` | `OOR_REG_ERROR` | Register Ra is out of range |
| `ald_PHYS_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `ald_PHYS_` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ald_PHYS_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ald_PHYS_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald_PHYS_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald_UR__LOGICAL_URa_default` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ald_UR__LOGICAL_URa_default` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ald_UR__LOGICAL_URa_default` | `OOR_REG_ERROR` | Uniform register URa is out of range |
| `ald_UR__LOGICAL_URa_default` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ald_UR__LOGICAL_URa_default` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ald_UR__LOGICAL_URa_default` | `OOR_REG_ERROR` | Register is out of range |
| `ald_UR__LOGICAL_URa_default` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald_UR__LOGICAL_URa_default` | `OOR_REG_ERROR` | Register is out of range |
| `ald_UR__LOGICAL_URa_default` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald_UR__LOGICAL_URa_default` | `OOR_REG_ERROR` | Register is out of range |
| `ald_UR__LOGICAL_URa_default` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald_UR__LOGICAL_URa_default` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald_UR__LOGICAL_URa_default` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald_UR__PATCH_URa_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ald_UR__PATCH_URa_P_RbRZ` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ald_UR__PATCH_URa_P_RbRZ` | `OOR_REG_ERROR` | Uniform register URa is out of range |
| `ald_UR__PATCH_URa_P_RbRZ` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ald_UR__PATCH_URa_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rb |
| `ald_UR__PATCH_URa_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ald_UR__PATCH_URa_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald_UR__PATCH_URa_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald_UR__PATCH_URa_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald_UR__PATCH_URa_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald_UR__PATCH_URa_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald_UR__PATCH_URa_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald_UR__PATCH_URa_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald_UR__PATCH_URa_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald_UR__PATCH_URa_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald_UR__PATCH_URa_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__LOGICAL_RaRZ_default` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ald__LOGICAL_RaRZ_default` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ald__LOGICAL_RaRZ_default` | `OOR_REG_ERROR` | Register Ra is out of range |
| `ald__LOGICAL_RaRZ_default` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `ald__LOGICAL_RaRZ_default` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ald__LOGICAL_RaRZ_default` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ald__LOGICAL_RaRZ_default` | `OOR_REG_ERROR` | Register is out of range |
| `ald__LOGICAL_RaRZ_default` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__LOGICAL_RaRZ_default` | `OOR_REG_ERROR` | Register is out of range |
| `ald__LOGICAL_RaRZ_default` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__LOGICAL_RaRZ_default` | `OOR_REG_ERROR` | Register is out of range |
| `ald__LOGICAL_RaRZ_default` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__LOGICAL_RaRZ_default` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__LOGICAL_RaRZ_default` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `OOR_REG_ERROR` | Register Ra is out of range |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rb |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__PATCH_RaNonRZOffset_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__PATCH_RaRZ_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `ald__PATCH_RaRZ_P_RbRZ` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ald__PATCH_RaRZ_P_RbRZ` | `OOR_REG_ERROR` | Register Ra is out of range |
| `ald__PATCH_RaRZ_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `ald__PATCH_RaRZ_P_RbRZ` | `OOR_REG_ERROR` | Register Rb is out of range |
| `ald__PATCH_RaRZ_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Rb |
| `ald__PATCH_RaRZ_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ald__PATCH_RaRZ_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald__PATCH_RaRZ_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__PATCH_RaRZ_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald__PATCH_RaRZ_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__PATCH_RaRZ_P_RbRZ` | `OOR_REG_ERROR` | Register is out of range |
| `ald__PATCH_RaRZ_P_RbRZ` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `ald__PATCH_RaRZ_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__PATCH_RaRZ_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__PATCH_RaRZ_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `ald__PATCH_RaRZ_P_RbRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The physical layout behind the logical `a[...]` address is not exposed as a raw pointer.
