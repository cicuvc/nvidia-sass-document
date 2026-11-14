# EXIT — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe_const.frag`, `probe_atexit.frag`, `vulkan_graphics.c`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Operand-less shader termination with graphics output export performed by fixed-function state.

## Graphics-observed semantics

Fragment color outputs are staged in GPRs and committed by an operand-less
`EXIT`:

```text
IMAD.MOV.U32 R0, RZ, RZ, 1.0
MOV           R1, 2.0
MOV           R2, 3.0
MOV           R3, 4.0
EXIT
```

There is no per-attachment store operand. Pipeline state selects attachment
indices, formats, blend equations, masks, and ROP behavior.

### Fragment epilogue search

Static pipeline-binary scans and live `/proc/<pid>/mem` scans found no SASS
epilogue after `EXIT`; the following slots were padding (`BRA 0x0; NOP`).
Replacing the normal EXIT control with `EXIT.NO_ATEXIT` did not change pixels,
and patching the post-EXIT slots to execute a store still did not affect the
result. `ATEXIT_PC` and `TRAP_RETURN_PC` both read zero in ordinary fragment
invocations.

This supports an implicit fixed-function export at `EXIT`, not a hidden SASS
continuation. If a continuation exists, it is not exposed through the tested
CBU registers and is not reached by fall-through.

### `gl_FragDepth`

A constant `gl_FragDepth` value can be folded into pipeline metadata with no
shader instruction. A dynamic value is computed into a compiler-selected GPR
and consumed by the late depth path after `EXIT`. One color output placed the
value in `R5`; two color outputs placed it in `R9`. Patching the producing
instruction from `R5` to `R4` left the old `R5` value to be exported, proving
the fixed-function path consumed that register.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `exit_` | `0x94d` | `/EXIT_MODE("noexit_mode"):mode /NO_ATEXIT("nono_atexit"):no_atexit [!]:Pp` |

## Properties

| property | value(s) |
|---|---|
| `BRANCH_TYPE` | `BRT_BRANCHOUT` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` |
| `MEM_SCBD` | `NON_BARRIER_INT_INST` |
| `MEM_SCBD_TYPE` | `BB_ENDING_INST` |
| `MIN_WAIT_NEEDED` | `5` |
| `PRED_INDEX` | `INDEX(Pp)` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_CBU` |

## Encoding

Bit map of the first layout (`exit_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [85:84] | `mode` | 2 | `mode` |
| [86:86] | `depth` | 1 | `no_atexit` |
| [89:87] | `Pp` | 3 | `Pp` |
| [90:90] | `memdesc` | 1 | Pp@not |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | 7 |
| [112:110] | `dst_wr_sb` | 3 | 7 |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `exit_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid mode field value |
| `exit_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `exit_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed combination for shader |

## Pipe

Pipe suffix(es) in this dump: `cbu_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

The fixed-function continuation or state machine behind color/depth export is not represented as shader SASS.
