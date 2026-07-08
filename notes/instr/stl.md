# STL — Store to Local Memory (per-thread stack)

**Opcode mnemonic:** `STL`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` (decoupled read-only scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Stores source register `Rb` into per-thread local memory (stack or register
spill area). Address = `Ra + URb + offset`.

STL is the store counterpart to LDL — identical structure, no E bit, no mem
qualifiers, no Pu/Pnz/SP2. 4 variants across 2 opcodes (same pattern as
LDL/STS/LDS).

## LDL/STL vs LDG/STG comparison

| Feature | LDG/STG (global) | LDL/STL (local) |
|---------|------------------|-----------------|
| Address space | Global device memory | Per-thread stack / spill |
| E (64-bit addr) | Yes | No |
| SEM/SCO/PRIVATE | Yes | No |
| Pu/Pnz/SP2 | LDG only | No |
| memdesc usage | All active (0x1981/0x1986) | Plain only (0x983/0x1983/0x387/0x1987) |
| Base register | Global pointer (UR desc) | R1 (stack frame) |
| COP | EF/EN/EL/LU/EU/NA | same |

## Bit layout (stl__sImmOffset, 128-bit)

Same structure as LDL, with Rb at [39:32] instead of Rd at [23:16], and
dst_wr_sb hardwired to 7 (no destination register).

```
  [86:84]  3b  cop (COP)
  [76]     1b  memdesc      (*0)
  [75:73]  3b  sz
  [63:40] 24b  Ra_offset
  [39:32]  8b  Rb           (source data)
  [31:24]  8b  Ra           (address base, typically R1)
  [23:16]  8b  Rd           (unused/layout padding)
  [91],[11:0] 13b  opcode   (0x387)
```

## Verified encodings

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000201007387` | — | `STL.64 [R1], R2` |
| `0x0000080401007387` | — | `STL.64 [R1+0x8], R4` |
| `0x0000100601007387` | — | `STL.64 [R1+0x10], R6` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `st.local.u32 [%ra], %rb` | `STL [Ra], Rb` |
| `st.local.u64 [%ra+off], %rb` | `STL.64 [Ra+off], Rb` |
| Register spill (compiler-generated) | `STL.64 [R1+off], Rb` |
