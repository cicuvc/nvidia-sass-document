# ATOMS — Atomic Operation on Shared Memory

**Opcode mnemonic:** `ATOMS`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`  
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Performs an atomic read-modify-write operation on shared memory. The operation
is specified by the `AtomsOp` field, applied to `[Ra + stride×URc + offset]`
with source operand `Rb` (and `Rc` for CAS). Result is returned in `Rd`.

- **Basic:** `Rd, *smem[addr] = atomic_op(*smem[addr], Rb)` (ADD/MIN/MAX/INC/DEC/AND/OR/XOR/EXCH)
- **CAS:** `Rd, *smem[addr] = (*smem[addr] == Rb ? Rc : *smem[addr])`
- **CAST:** CAS with spinlock (`.SPIN` suffix)
- **ARRIVE:** Barrier arrive atomic, 64-bit result
- **POPC.INC:** Population-count increment atomic

CS shader only (same constraint as LDS/STS).

## Variant overview

9 encoding variants across 4 opcodes:

| Opcode | Variants | Operation | Operands |
|--------|----------|-----------|:---:|
| `0x38c` | RaNonRZ, RaRZ | AtomsOp (8 ops) | Rd, Ra, Rb |
| `0x38d` | RaNonRZ_CAS, RaNonRZ_CAST, RaRZ_CAS, RaRZ_CAST | CAS/CAST | Rd, Ra, Rb, Rc |
| `0x1f8c` | ARRIVE, POPC.INC | Arrive/PopcInc | Rd, Ra(RZ)+URc |
| `0x198c` | uniform | AtomsOp | Rd, Ra(RZ)+URc, Rb |

## Modifiers

### AtomsOp — bits [90:87] (4-bit)

| Value | Mnemonic | Allowed sizes |
|:-----:|----------|---------------|
| 0 | `.ADD` | U32/S32/U64 |
| 1 | `.MIN` | U32/S32 |
| 2 | `.MAX` | U32/S32 |
| 3 | `.INC` | U32 |
| 4 | `.DEC` | U32 |
| 5 | `.AND` | U32 |
| 6 | `.OR` | U32 |
| 7 | `.XOR` | U32 |
| 8 | `.EXCH` | U32/S32/U64 |
| 9–15 | — | INVALID |

### ATOMCASSZ — size

| Value | Mnemonic | Notes |
|:-----:|----------|-------|
| 0 | `.U32` (default) | |
| 1 | `.S32` | Signed 32-bit |
| 2 | `.U64` / `.64` | 64-bit |
| 4 | `.128` | 128-bit |
| 3,5,6,7 | — | INVALID |

### Stride — bits [79:78]

Only on RaNonRZ variants (not RaRZ uImmOffset). X1(0,default), X4(1), X8(2), X16(3).

### CAS (0x38d): /CAS — bit role

CAS mode: `Rd = atomicCAS(addr, Rb, Rc)` — if `*addr == Rb`, write `Rc` to `*addr`, return old value. Uses `Rc` as operand at a separate encoding position from `Rb`.

### CAST: /CASTONLY + /AtomsSPIN

CAST mode adds a spinlock (`ATOMSSPIN`): same CAS semantics but with hardware spin. `.SPIN` suffix.

### ARRIVE (0x1f8c): /ARRIVEONLY

Barrier arrive atomic on shared memory. 64-bit only. No Rb/Rc operands. URc provides offset.

### POPC.INC (0x1f8c): /POPC.INCONLY

Population-count increment. 32-bit only. URc uniform offset.

## Bit layout (basic 0x38c, 128-bit)

```
  [90:87]   4b  op (AtomsOp)
  [79:78]   2b  stride        (absent in RaRZ)
  [63:40]  24b  Ra_offset
  [39:32]   8b  Rb             (source operand)
  [31:24]   8b  Ra             (*Ra for RaRZ)
  [23:16]   8b  Rd             (destination/old value)
  [91],[11:0] 13b  opcode     (0x38c)
```

CAS (0x38d) adds Rc at a different encoding position.

## Open questions

- **ATOMS usage in practice:** No ATOMS found in cublas. Shared-memory atomics
  on sm_90 may be rare — the compiler likely uses global atomics (ATOMG) or
  warp-level reductions instead.
- **ARRIVE/POPC.INC vs explicit barriers:** These may be compiler-internal
  for CTA-level synchronisation patterns.
