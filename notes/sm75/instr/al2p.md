# AL2P — sm75 (Turing) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** spec  
**Tier confidence:** low  
**Last verified:** 2026-11-14  
**Probe:** `AL2P` ISA operand types plus negative tests across local VS/GS/TCS/TES/mesh probes  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm75.json`

## Conclusion

Logical-to-physical attribute-address conversion; not observed in tested GLSL.

## ISA-derived semantics

`AL2P` converts a logical attribute address to a physical attribute address:

```text
source:      LOGICAL_ATTR_ADDRESS
destination: PHYSICAL_ATTR_ADDRESS
```

Conceptually:

```text
Rphysical = translate_logical_attribute_address(
                Rlogical + offset)
```

The destination can feed a later dynamic `ALD`, `AST`, `IPA`, or related
attribute operation.

The ISA restricts `AL2P` to the geometry front-end stages:

```text
VS, GS, TS, TI
```

It is not legal in pixel shaders.

No real `AL2P` appeared in the tested static/dynamic VS, GS, TCS/TES, mesh, or
fragment probes. Ordinary static accesses use immediate `a[...]`; dynamic
arrays commonly use `ISBERD` plus `ALD/AST` with a register offset.

Likely callers are compiler-generated logical-to-physical remaps for dynamic,
aliased, packed, widened, or transformed attribute layouts.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `al2p__RaNonRZ` | `0x920` | `/AIO("I"):io /AInteger("32"):sz :Rd NonZeroRegister:Ra *:Ra_offset` |
| `al2p__RaRZ` | `0x920` | `/AIO("I"):io /AInteger("32"):sz :Rd ZeroRegister("RZ"):Ra *:Ra_offset` |

## Properties

| property | value(s) |
|---|---|
| `IDEST2_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `IDEST2_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `IDEST2_SIZE` | `0` |
| `IDEST_OPERAND_MAP` | `(1<<INDEX(Rd))` |
| `IDEST_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_PHYSICAL_ATTR_ADDRESS)` |
| `IDEST_SIZE` | `32` |
| `IERRORS` | `(1<<IERROR_ILLEGAL_INSTR_DECODING)+(1<<IERROR_OOR_REG)+(1<<IERROR_PC_WRAP)+0` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_OPERAND_MAP` | `(1<<INDEX(Ra)) + (1<<INDEX(Ra_offset))` |
| `ISRC_A_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_LOGICAL_ATTR_ADDRESS)` |
| `ISRC_A_SIZE` | `32` |
| `ISRC_B_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_B_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_B_SIZE` | `0` |
| `ISRC_C_OPERAND_MAP` | `(1<<IOPERAND_MAP_NON_EXISTENT_OPERAND)` |
| `ISRC_C_OPERAND_TYPE` | `(1<<IOPERAND_TYPE_NON_EXISTENT_OPERAND)` |
| `ISRC_C_SIZE` | `0` |
| `MIN_WAIT_NEEDED` | `1` |
| `VALID_IN_SHADERS` | `(1<<ISHADER_TRAP)+(1<<ISHADER_GS)+(1<<ISHADER_TI)+(1<<ISHADER_TS)+(1<<ISHADER_VS)+0` |
| `VIRTUAL_QUEUE` | `$VQ_ADU`, `$VQ_UNORDERED` |

## Encoding

Bit map of the first layout (`al2p__RaNonRZ`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [11:0] | `opcode` | 12 | Opcode |
| [79:79] | `op` | 1 | `io` |
| [75:74] | `iswzA` | 2 | `sz` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | *Ra |
| [50:40] | `Ra_offset` | 11 | `Ra_offset` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `al2p__RaNonRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `al2p__RaNonRZ` | `OOR_REG_ERROR` | Register Rd is out of range |
| `al2p__RaNonRZ` | `OOR_REG_ERROR` | Register Ra is out of range |
| `al2p__RaNonRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `al2p__RaNonRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `al2p__RaRZ` | `ILLEGAL_INSTR_ENCODING_ERROR` | Can only be used with VS, GS, TS, TI |
| `al2p__RaRZ` | `OOR_REG_ERROR` | Register Rd is out of range |
| `al2p__RaRZ` | `OOR_REG_ERROR` | Register Ra is out of range |
| `al2p__RaRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Disallowed register Ra |
| `al2p__RaRZ` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Need a concrete GLSL/SPIR-V layout that forces AL2P before promoting this note above spec evidence.
