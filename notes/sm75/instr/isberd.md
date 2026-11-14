# ISBERD — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe_dynamic.geom`, `probe.tesc`, `probe.tese`, `vulkan_graphics.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

## Conclusion

Read of raw indexed shader-buffer entry values in geometry/tessellation stages.

## Graphics-observed semantics

`ISBERD` reads a raw indexed shader-buffer entry from `[Ra]`. It is legal in
VS, GS, TS, and TI stages.

Geometry and tessellation prologues use the result as a dynamic offset for
attribute operations:

```text
ISBERD R3, [R1]
ALD.128 R4, a[0x70], R3
ALD.128 R8, a[0x80], R3
AST.128 a[0x70], R4
AST.128 a[0x80], R8
```

The same pattern selects input vertices and patch entries in TCS/TES.
`ISBERD` supplies the raw entry value; `ALD/AST` consume it as an attribute
address component. It is not a global-memory load.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `isberd_` | `0x923` | `/AIO("I"):io /BASE("MAP"):base /SKEW("noskew"):skew /ISBERD_SZ("U8"):sz :Rd [ :Ra ]` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST2_SIZE` | `0` |
| `IDEST_OPERAND_MAP` | `(1<<INDEX(Rd))` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_GENERIC)` |
| `IDEST_SIZE` | `32` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_MISALIGNED_ADDR)+(1<<IERROR_OOR_ADDR)+(1<<IERROR_OOR_REG)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<INDEX(Ra))` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_RAW_ISBE_ACCESS)` |
| `ISRC_A_SIZE` | `32` |
| `ISRC_B_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_B_SIZE` | `0` |
| `ISRC_C_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_C_SIZE` | `0` |
| `MIN_WAIT_NEEDED` | `1` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_GS)+(1<<ISHADER_TI)+(1<<ISHADER_TS)+(1<<ISHADER_VS)+0` |
| `VIRTUAL_QUEUE` | `$VQ_AGU` |

## Encoding

Bit map of the first layout (`isberd_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [79:79] | `op` | 1 | `io` |
| [77:76] | `msi` | 2 | `base` |
| [78:78] | `ofmt` | 1 | `skew` |
| [75:74] | `iswzA` | 2 | `sz` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `isberd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `isberd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `isberd_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `isberd_` | `OOR_REG_ERROR` | Register Ra is out of range |
| `isberd_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `isberd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |
| `isberd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The complete hardware layout of all ISBE bases (`MAP/PRIM/ATTR/PATCH`) is not decoded.
