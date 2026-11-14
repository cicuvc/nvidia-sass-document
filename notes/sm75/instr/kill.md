# KILL — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe_discard.frag`, `vulkan_graphics.c`, `extract_pipeline_binary.py`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

## Conclusion

Fragment discard control; suppresses the eventual fixed-function update.

## Graphics-observed semantics

GLSL `discard` lowers to a predicated `KILL` before the final `EXIT`:

```text
@!P0 KILL
...
EXIT
```

`KILL` is separate from output writeback. The shader may still have staged
color/depth values, but a killed fragment is suppressed before the normal
fixed-function commit. Unlike color output, discard is explicit in SASS.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `kill_` | `0x95b` | `[!]:Pp` |

## Properties

| property | value(s) |
|---|---|
| `BRANCH_TYPE` | `BRT_BRANCHOUT` |
| `IDEST2_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST2_SIZE` | `0` |
| `IDEST_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST_SIZE` | `0` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_A_SIZE` | `0` |
| `ISRC_B_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_B_SIZE` | `0` |
| `ISRC_C_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_C_SIZE` | `0` |
| `MIN_WAIT_NEEDED` | `1` |
| `PRED_INDEX` | `INDEX(Pp)` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_PS)+0` |
| `VIRTUAL_QUEUE` | `$VQ_CBU` |

## Encoding

Bit map of the first layout (`kill_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [11:0] | `opcode` | 12 | Opcode |
| [89:87] | `Pp` | 3 | `Pp` |
| [90:90] | `input_reg_sz_32_dist` | 1 | Pp@not |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | 7 |
| [112:110] | `dst_wr_sb` | 3 | 7 |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `kill_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `kill_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |

## Pipe

Pipe suffix(es) in this dump: `cbu_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Early versus late discard timing across all depth/stencil state combinations was not exhaustively measured.
