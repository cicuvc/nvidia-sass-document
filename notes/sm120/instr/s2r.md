# S2R — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** vertex/fragment builtin probes in `experiments/graphics_batch_t`, `gpucomp_spy.c` SR-pair patch  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Reads special register state; several graphics builtins map directly or through packed bitfields.

## Graphics-observed semantics

Graphics builtins use three distinct sources: attribute loads, driver ABI
constants, and special registers. `S2R` covers the SR path.

Observed mappings:

| builtin / use | special register |
|---|---|
| `gl_SubgroupInvocationID` | `SR_LANEID` |
| subgroup equality masks | `SR_EQMASK` / `SR_GEMASK` / `SR_GTMASK` / `SR_LEMASK` / `SR_LTMASK` |
| `gl_WarpIDNV` | bitfield in `SR_VIRTID` |
| `gl_SMIDNV` | another bitfield in `SR_VIRTID` |
| `gl_SMCountNV` | bitfield in `SR_VIRTCFG` |
| `gl_HelperInvocation` | `SR_THREAD_KILL` |
| thread/block IDs | `SR_TID.*` / `SR_CTAID.*` |

Packed fields require shift/mask extraction:

```text
S2R R1, SR_VIRTID
SHF.R.U32.HI R6, RZ, 0x8, R1
SHF.R.U32.HI R7, RZ, 0x14, R1
SGXT.U32 R6, R6, 0x7
SGXT.U32 R7, R7, 0x9
```

The `SpecialRegisters` enum has no named surface-header-table or bindless
descriptor-table base. Candidate address-like registers were sampled in a
fragment S2R patch: direct-CBE address (21/22), circular-queue address (98/99),
and invocation/TTU metadata (29/133) all read zero. A positive control reading
`SR_LANEID`/`SR_TID.X` produced expected nonzero per-lane values.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `s2r_` | `0x919` | `:Rd SpecialRegister:SRa` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_UNORDERED` |

## Encoding

Bit map of the first layout (`s2r_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [23:16] | `Rd` | 8 | `Rd` |
| [79:72] | `imm8` | 8 | `SRa` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `s2r_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Special registers 84 and 85 should not be read in user mode |
| `s2r_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `s2r_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Unnamed SR indices and stage-specific populating of address-like registers remain untested.
