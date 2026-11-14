# PIXLD — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe_fragment_sample*.frag`, `probe_fragment_fullycovered.frag`, `vulkan_graphics.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Pixel-shader load of sample and coverage state.

## Graphics-observed semantics

`PIXLD` has no source operands and writes one 32-bit result plus optional
predicate.

Observed Vulkan GLSL mappings:

| source | SASS |
|---|---|
| `gl_SampleID` | `PIXLD.MY_INDEX R0` |
| `gl_SampleMaskIn[0]` | `PIXLD.MY_INDEX`, then `PIXLD.COVMASK` |
| `gl_FragFullyCoveredNV` | `PIXLD.INNER_COVERAGE R0` |

`gl_SamplePosition` also reads `MY_INDEX`, then performs `LDC.U8` from the
sample-position table in `c[0x0][0x32d0]`.

`gl_HelperInvocation` is not PIXLD; it lowers to `S2R SR_THREAD_KILL`.
`interpolateAtCentroid` uses `IPA.PASS.CENTROID`, and
`interpolateAtSample` combines `PIXLD.MY_INDEX` with `IPA.PASS.OFFSET`.

The same three observed PIXLD modes occur on sm75 and sm120. No tested
standard Vulkan GLSL construct emitted `MSCOUNT` or `CENTROID_OFFSET`.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `pixld_` | `0x925` | `/PIXLD_MODE("MSCOUNT"):mode :Rd :Pu` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_PS)+0` |
| `VIRTUAL_QUEUE` | `$VQ_AGU` |

## Encoding

Bit map of the first layout (`pixld_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [80:78] | `mode` | 3 | `mode` |
| [23:16] | `Rd` | 8 | `Rd` |
| [83:81] | `Pu` | 3 | `Pu` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `pixld_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `pixld_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `pixld_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

`MSCOUNT` and `CENTROID_OFFSET` callers remain unidentified.
