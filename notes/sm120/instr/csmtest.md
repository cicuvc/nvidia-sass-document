# CSMTEST — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe_vertex_attr.vert`, `probe_vertex_ssbo.vert`, `vulkan_graphics.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Combines clip/guard-band predicates for a vertex-stage early-exit decision.

## Graphics-observed semantics

A passthrough vertex shader uses `CSMTEST` after six clip-bound comparisons:

```text
FSETP...                         ; X/Y/Z against positive and negative bounds
FMUL.FTZ R5, R3, UR5             ; scale clip-space W
CSMTEST.RA.F.AND ...
CSMTEST.A.FCSM_TR.AND P0, ...
@P0 EXIT
```

`SR_WSCALEFACTOR_XY/Z` supplies viewport scale factors used before the bound
comparisons. The two `CSMTEST` operations combine the six predicates into the
final predicate consumed by the early `EXIT`.

The test is interleaved with setup stores but depends only on previously
generated predicates; it does not itself load a GLSL builtin. sm75 and sm120
use the same structural sequence with generation-specific scheduling controls.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `csmtest_` *(ALT)* | `0x80d` | `[/vtgmode] *:Sa` |
| `csmtest_bop_` | `0x80d` | `[/vtgmode] [/ccmp] [/bop] :Pu :Pv *:Sa [!]:Pp` |
| `csmtest_cmp_` *(ALT)* | `0x80d` | `[/vtgmode] [/ccmp] :Pu *:Sa` |

## Properties

| property | value(s) |
|---|---|
| `INSTRUCTION_TYPE` | `INST_TYPE_COUPLED_MATH` |
| `ISRC_A_SIZE` | `28` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `0` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_GS)+(1<<ISHADER_TI)+(1<<ISHADER_TS)+(1<<ISHADER_VS)+0` |

## Encoding

Bit map of the first layout (`csmtest_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [63:62] | `query` | 2 | `vtgmode` |
| [78:76] | `dstfmt` | 3 | *0 |
| [75:74] | `iswzA` | 2 | *0 |
| [83:81] | `Pu` | 3 | *7 |
| [86:84] | `cop` | 3 | *7 |
| [59:32] | `Sa` | 28 | `Sa` |
| [89:87] | `Pp` | 3 | * 7 |
| [90:90] | `memdesc` | 1 | *0 |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | *7 |
| [112:110] | `dst_wr_sb` | 3 | *7 |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_1(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `csmtest_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `csmtest_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid vtgmode field value |
| `csmtest_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `csmtest_bop_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `csmtest_bop_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid vtgmode field value |
| `csmtest_bop_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid bop field value |
| `csmtest_bop_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `csmtest_cmp_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `csmtest_cmp_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid vtgmode field value |
| `csmtest_cmp_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |

## Pipe

Pipe suffix(es) in this dump: `fe_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Individual `RA`/`FCSM_TR` modifier semantics were not isolated beyond the combined clip-rejection sequence.
