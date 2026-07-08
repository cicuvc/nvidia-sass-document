# LDL — Load from Local Memory (per-thread stack)

**Opcode mnemonic:** `LDL`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` (decoupled read/write scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_AGU_UNORDERED_WR`

## Semantics

Loads from per-thread local memory (stack or register spill area) into
destination register `Rd`. The address is formed from a base register `Ra`
(typically R1 — the stack frame pointer) plus a signed 24-bit offset.

`Rd = *(local_memory_base + Ra + URb + offset)`

LDL is the simplest global-address-space load instruction in the MIO family:
no E bit (addresses are always 32-bit within local memory), no memory
qualifiers (SEM/SCO/PRIVATE not applicable to per-thread storage), no
Pu/Pnz/SP2. Only COP and size modifiers.

## Variant overview

4 encoding variants across 2 opcodes:

| Class | Opcode | memdesc | Ra | Address |
|-------|--------|:---:|:---:|---------|
| `ldl__sImmOffset` | `0x983` | 0 | Ra≠RZ | `[Ra + offset]` |
| `ldl__uImmOffset` | `0x983` | 0 | Ra=RZ | `[RZ + offset]` |
| `ldl_uniform_` | `0x1983` | 0 | Ra=RZ | `[RZ + URb + offset]` |
| `ldl_memdesc_` | `0x1983` | 1 | (register) | `desc[URb][Ra + offset]` |

**Empirical note:** All observed LDL instructions use the plain 0x983 form
(`LDL Rd, [Ra+off]`). The memdesc and uniform forms are not seen in cublas or
user kernels. Local memory uses per-CTA shared base + stack frame, so the
descriptor indirection is unnecessary — the address is always relative to
the warp's local-memory window.

## LDL vs LDG — simplification

| Feature | LDG | LDL |
|---------|-----|-----|
| E (64-bit addr) | Yes (bit 72) | No (always 32-bit) |
| SEM/SCO/PRIVATE | Yes (bits 80:77) | No |
| Pu/Pnz/SP2 | Yes | No |
| Address width | 32 or 64-bit | 32-bit only |
| COP | Yes | Yes |
| Opcodes | 0x381/0x1981 | 0x983/0x1983 |

## Modifiers

### COP — Cache operator — bits [86:84]
Same as LDG: EF(0), EN(1,default), EL(2), LU(3,last-use), EU(4), NA(5).

### Size — bits [75:73]
U8=0, S8=1, U16=2, S16=3, 32=4(default), 64=5, 128=6, INVAL=7.

## Bit layout (ldl__sImmOffset, 128-bit)

```
Bit  127                                                                          0
      ...###.####..............###............##..###.........
      ........########################.................................

Field:
  [124:122],[109:105]  8b  opex        <= TABLES_opex_0
  [121:116]            6b  req_bit_set
  [115:113]            3b  src_rel_sb   <= VarLatOperandEnc
  [112:110]            3b  dst_wr_sb    <= VarLatOperandEnc
  [103:102]            2b  pm_pred
  [91],[11:0]         13b  opcode       (0x983)
  [86:84]              3b  cop (COP)
  [76]                 1b  memdesc      (*0 hardwired for plain form)
  [75:73]              3b  sz
  [63:40]             24b  Ra_offset
  [31:24]              8b  Ra           (*Ra, RZ=0xFF for uImmOffset)
  [23:16]              8b  Rd
  [15]                 1b  Pg_not
  [14:12]              3b  Pg
```

Memdesc form adds URb at [37:32] and sets memdesc=1 at bit 76.

## Verified encodings

All verified against `cuobjdump -arch sm_90 -sass` from `libcublas.so`:

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000006007983` | `0x000ea80000100800` | `LDL R0, [R6]` |
| `0x0000040006037983` | `0x000ea80000100800` | `LDL R3, [R6+0x4]` |
| `0x0000000001367983` | `0x000ea20000300a00` | `LDL.LU.64 R54, [R1]` |
| `0x0000000001527983` | `0x000ea80000100a00` | `LDL.64 R82, [R1]` |
| `0x0000080001507983` | `0x000ee80000100a00` | `LDL.64 R80, [R1+0x8]` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `ld.local.u32 %r, [%ra]` | `LDL Rd, [Ra]` |
| `ld.local.u64 %r, [%ra+off]` | `LDL.64 Rd, [Ra+off]` |
| Register spill (compiler-generated) | `LDL Rd, [R1+off]` |
| `ld.local.lu.u32 %r, [%ra]` | `LDL.LU Rd, [Ra]` |
