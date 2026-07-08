# ATOM — Atomic Operation (generic address space)

**Opcode mnemonic:** `ATOM`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`  
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Performs an atomic read-modify-write on **any address space** (shared, global,
or local). ATOM is the generic-pointer version — the compiler emits this when
the address space cannot be determined at compile time (e.g. function pointer
arguments of generic address).

`Rd = atomic_op(*addr, val)`

## Status on sm_90

**ATOM is effectively unused.** The compiler always resolves the address space
statically in practice (via PTX `.global`/`.shared`/`.local` annotations) and
emits the specialized instruction:

| PTX | SASS | Reason |
|-----|------|--------|
| `atom.shared.*` | **ATOMS** | Shared memory known at compile time |
| `atom.global.*` | **ATOMG** | Global memory known at compile time |
| `atom.*` (generic ptr) | **ATOM** → not observed | Compiler resolves space statically |

No ATOM instructions appear in `libcublas.so` or any user-compiled kernels. The
22 encoding variants exist as a spec-completeness fallback for generic pointer
scenarios.

## ATOM = ATOMS ∪ ATOMG ∪ atom_arrive

ATOM is the union of all atomic operations across all address spaces:

| Sub-group | Variants | Opcodes | Counterpart |
|-----------|:---:|---------|-------------|
| atom_arrive | 6 | `0x1f8a` | ATOMS.ARRIVE / ATOMS.POPC.INC |
| atom_cas | 4 | `0x38b` | ATOMS.CAS / ATOMG.CAS |
| atom_fp | 2 | `0x3a2` | ATOMS fp / ATOMG fp |
| atom_fp_uniform | 4 | `0x19a2` | ATOMS/ATOMG fp uniform |
| atom_int | 2 | `0x38a` | ATOMS/ATOMG int |
| atom_int_uniform | 4 | `0x198a` | ATOMS/ATOMG int uniform |

ATOM uses `ATOMICINTSIZES` (which adds S64) vs ATOMS's `ATOMCASSZ`.

### Opcode layout — consistent offset from ATOMS/ATOMG

| Operation | ATOMS | ATOMG | ATOM (generic) |
|-----------|:---:|:---:|:---:|
| int plain | `0x38c` | `0x3a8` | `0x38a` |
| int uniform | `0x198c` | `0x19a8` | `0x198a` |
| CAS | `0x38d` | `0x3a9` | `0x38b` |
| fp plain | — | `0x3a3` | `0x3a2` |
| fp uniform | — | `0x19a3` | `0x19a2` |
| arrive | `0x1f8c` | — | `0x1f8a` |

The opcodes form a regular pattern — ATOM = ATOMS - 2, ATOMG - 1 (mostly).

## Bit layout (basic int 0x38a, RaNonRZ, 128-bit)

| bits | field | source |
|------|-------|--------|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(src_rel_sb)` |
| [112:110] | dst_wr_sb | `VarLatOperandEnc(dst_wr_sb)` |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | varies by group |
| [90:87] | op | AtomsOp / ATOMICFPOPS / ARRIVEONLY / POPC.INCONLY / CAS |
| [86:84] | cop | COP (`.E`/`.EN`) |
| [83:81] | Pu | write predicate |
| [80:77] | mem | sem/sco/private (via `TABLES_mem_0`) |
| [75:73] | sz | data size (ATOMICINTSIZES / ATOMCASSZ) |
| [72] | e | 1=64-bit address (`Ra.64`) |
| [63:40] | Ra_offset | 24-bit signed offset |
| [39:32] | Rb | source operand |
| [31:24] | Ra | address register (*Ra for RaRZ) |
| [23:16] | Rd | destination (old value) |
| [15] | Pg_not | predicate negate |
| [14:12] | Pg | guard predicate |

CAS (`atom_cas_*`) adds `Rc` at [71:64]; ARRIVE/POPC.INC variants use `URc` at [69:64] for uniform offset instead of `Rb`.
