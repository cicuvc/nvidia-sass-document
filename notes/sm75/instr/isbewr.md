# ISBEWR — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe.mesh`, `vulkan_graphics.c`, `extract_pipeline_binary.py`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

## Conclusion

Write to indexed shader-buffer entries; observed directly in sm120 mesh output.

## Graphics-observed semantics

`ISBEWR` writes `Rb` to raw indexed shader-buffer entry `[Ra]` and uses `.O`
for the output direction. The ISA permits VS, TS, and TI, but not GS.

An `EXT_mesh_shader` probe on sm120 emits:

```text
ISBEWR.O.32 [0x3], R0
ISBEWR.O.ATTR.SKEW.32 [RZ],  R1
ISBEWR.O.ATTR.SKEW.32 [0x80], R1
ISBEWR.O [0x4], RZ
ISBEWR.O [0x5], R4
ISBEWR.O [0x6], R5
```

`.ATTR` writes per-vertex output attributes such as `gl_Position` and user
varyings. Plain `.O` writes carry primitive/topology metadata. `SKEW` exposes
the packed/skewed entry layout.

The instruction has no normal destination register and does not write global
memory. It updates graphics-front-end indexed shader-buffer entries.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `isbewr_` | `0x927` | `[/io] /ISBEWR_BASE("MAP"):base /SKEW("noskew"):skew /ISBERD_SZ("U8"):sz [ :Ra ] :Rb` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST2_SIZE` | `0` |
| `IDEST_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST_SIZE` | `0` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_MISALIGNED_ADDR)+(1<<IERROR_OOR_ADDR)+(1<<IERROR_OOR_REG)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<INDEX(Ra))` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_RAW_ISBE_ACCESS)` |
| `ISRC_A_SIZE` | `32` |
| `ISRC_B_OPERAND_MAP` | `(1<<INDEX(Rb))` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_GENERIC)` |
| `ISRC_B_SIZE` | `32` |
| `ISRC_C_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_C_SIZE` | `0` |
| `MIN_WAIT_NEEDED` | `1` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_TI)+(1<<ISHADER_TS)+(1<<ISHADER_VS)+0` |
| `VIRTUAL_QUEUE` | `$VQ_AGU` |

## Encoding

Bit map of the first layout (`isbewr_`); other classes differ
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
| [31:24] | `Ra` | 8 | `Ra` |
| [39:32] | `Rb` | 8 | `Rb` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | 7 |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `isbewr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, TS, TI |
| `isbewr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid base field value |
| `isbewr_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid sz field value |
| `isbewr_` | `OOR_REG_ERROR` | Register Ra is out of range |
| `isbewr_` | `OOR_REG_ERROR` | Register Rb is out of range |
| `isbewr_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The sm75 mesh path is not available in local Vulkan; sm75 evidence covers the ISA/stage legality, not a mesh caller.
