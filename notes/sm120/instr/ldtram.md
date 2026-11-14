# LDTRAM — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `probe_fragment_barycentric.frag`, `vulkan_graphics.c`, `extract_pipeline_binary.py`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Per-vertex/barycentric attribute load from triangle attribute storage.

## Graphics-observed semantics

`LDTRAM` appears in fragment shaders using per-vertex barycentric input
attributes:

```glsl
layout(location = 0) pervertexEXT in vec4 colors[3];
```

Observed sm75 lowering:

```text
LDTRAM.AB R12, a[0x80]
LDTRAM.AB R14, a[0x84]
LDTRAM.AB R16, a[0x88]
LDTRAM.AB R18, a[0x8c]
LDTRAM.C  R1,  a[0x80]
LDTRAM.C  R5,  a[0x84]
LDTRAM.C  R7,  a[0x88]
LDTRAM.C  R8,  a[0x8c]
```

The modes match triangle vertex storage:

| mode | result |
|---|---|
| `AB` | 64-bit pair containing A and B vertex values |
| `C` | 32-bit C vertex value |

This differs from ordinary interpolation: `LDTRAM` exposes each triangle
vertex's attribute separately so the shader can combine them with explicit
barycentric weights.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `ldtram_` | `0x13ad` | `[/mode] :Rd A:srcAttr[ :URa + *:URa_offset ]` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32 + ((mode==`MODE_ldtram@AB))*32` |
| `ILABEL_URa_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@LDTRAM` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_PS)+0` |
| `VIRTUAL_QUEUE` | `$VQ_AGU` |

## Encoding

Bit map of the first layout (`ldtram_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [72:72] | `e` | 1 | `mode` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `URa` |
| [71:64] | `Ra_URc` | 8 | `URa_offset SCALE 4` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `ldtram_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with PS |
| `ldtram_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `ldtram_` | `OOR_REG_ERROR` | Uniform register URa is out of range |
| `ldtram_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `ldtram_` | `OOR_REG_ERROR` | Register is out of range |
| `ldtram_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

No non-barycentric caller of LDTRAM was found in the tested Vulkan paths.
