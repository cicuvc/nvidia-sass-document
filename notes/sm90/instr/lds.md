# LDS — Load from Shared Memory

**Opcode mnemonic:** `LDS`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` (decoupled read/write scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Loads data from shared memory at address `[Ra + stride×URb + offset]` into
destination register `Rd`. Shared memory is an on-chip, per-CTA scratchpad.

- **Plain (sImmOffset):** `Rd = smem[Ra + offset]` (Ra != RZ, signed 24-bit offset)
- **Plain (uImmOffset):** `Rd = smem[RZ + offset]` (Ra == RZ, unsigned 24-bit offset, no stride)
- **Uniform (lds_uniform_):** `Rd = smem[RZ + stride×URb + offset]` (uniform register index)

The 32-bit load is the default (no size suffix); `.64` and `.128` load wider
values into register pairs/quads with alignment constraints.

## Variant overview

LDS has **3 encoding variants** across **2 opcodes**:

| Class | Opcode | Ra | Stride | Notes |
|-------|--------|:---:|:---:|-------|
| `lds__sImmOffset` | `0b100110000100` (`0x984`) | Ra != RZ | Yes | Signed 24-bit offset |
| `lds__uImmOffset` | `0b100110000100` (`0x984`) | Ra == RZ (0xFF) | No | Unsigned 24-bit offset |
| `lds_uniform_` | `0b1100110000100` (`0x1984`) | Ra == RZ (default) | Yes | Uniform register URb index |

Key differences from LDC:
- Offset is 24-bit at [63:40] (not 16-bit)
- No `AdMode` — stride (`/STRIDE`) occupies bits [79:78] instead
- CS-only instruction (shader-type constraint)
- Uses `$VQ_AGU` virtual queue (Address Generation Unit)

## Shader constraint

LDS is **restricted to Compute Shaders (CS)**:
```
(%SHADER_TYPE == $ST_UNKNOWN) || ((%SHADER_TYPE == $ST_TRAP)||(%SHADER_TYPE == $ST_CS))
```
Graphics shaders (VS/GS/TS/PS) emit an `ILLEGAL_INSTR_ENCODING_ERROR`.

## Modifiers

### Size (`sz`) — bits [75:73]

| Value | Mnemonic | Load width |
|:-----:|----------|------------|
| 0     | `.U8`    | Unsigned 8-bit, zero-extend |
| 1     | `.S8`    | Signed 8-bit, sign-extend |
| 2     | `.U16`   | Unsigned 16-bit, zero-extend |
| 3     | `.S16`   | Signed 16-bit, sign-extend |
| 4     | (default) | 32-bit |
| 5     | `.64`    | 64-bit (register pair, Rd % 2 == 0) |
| 6     | `.128`   | 128-bit (register quad, Rd % 4 == 0) |

### Stride (`stride`) — bits [79:78]

Only applicable to `lds__sImmOffset` and `lds_uniform_` — absent from `lds__uImmOffset`.

| Value | Mnemonic | Stride multiplier |
|:-----:|----------|------------------|
| 0     | `.X1` (default, omitted) | 1× (byte stride) |
| 1     | `.X4`  | 4× |
| 2     | `.X8`  | 8× |
| 3     | `.X16` | 16× |

Stride multiplies the uniform register index in the uniform variant; for the
sImmOffset variant it applies a stride to the address computation.

**Empirical note:** `.X4`/`.X8`/`.X16` strides do not appear in `libcublas.so`.
Only `.X1` (default, omitted from disasm) is used in practice.

### ISRC_A_SIZE — 32 for all variants

Unlike LDC (which has 64-bit ISRC_A_SIZE for bindless), LDS always uses 32-bit
ISRC_A_SIZE. The address space is per-CTA shared memory, fully addressable in 32 bits.

## Bit layout (non-uniform, 128-bit)

```
Bit  127                                                                          0
      ...###.####...........####............##..###.........
      .........########################........................

Field (lds__sImmOffset):
  [124:122],[109:105]  8b  opex        <= TABLES_opex_0(batch_t, usched_info)
  [121:116]            6b  req_bit_set         
  [115:113]            3b  src_rel_sb   <= VarLatOperandEnc(src_rel_sb)
  [112:110]            3b  dst_wr_sb    <= VarLatOperandEnc(dst_wr_sb)
  [103:102]            2b  pm_pred             
  [91],[11:0]         13b  opcode       (0x984 for non-uniform)
  [79:78]              2b  stride       (absent in uImmOffset)
  [75:73]              3b  sz           (LDSSIZE: U8=0..128=6)
  [63:40]             24b  Ra_offset    (signed for sImmOffset, unsigned for uImmOffset)
  [31:24]              8b  Ra           (*Ra for RaRZ/uImmOffset)
  [23:16]              8b  Rd           
  [15]                 1b  Pg_not       
  [14:12]              3b  Pg           
```

### Uniform variant additions

```
  [37:32]  6b  Ra_URb       (uniform register index)
```

## LDS vs LDC comparison

| Property | LDS | LDC |
|----------|-----|-----|
| Memory space | Shared memory (on-chip) | Constant memory (cache-optimized) |
| Opcode | `0x984` / `0x1984` | `0xb82` / `0x1582` |
| Offset width | 24-bit [63:40] | 16-bit [53:38] (or 21-bit with bank) |
| Address modifier | Stride (2-bit) | AdMode (2-bit) |
| Uniform variant | URb index into shared mem | URa for bindless bank |
| VQ | `$VQ_AGU` | `$VQ_UNORDERED` |
| Shader constraint | CS only | All shaders |
| ISRC_A_SIZE | 32 | 32 (plain) / 64 (bindless) |
| MIO subset | MIO_SLOW_OPS | MIO_FAST_OPS |

## Latency

MIO pipe, MIO_SLOW_OPS subset, decoupled scoreboard ($VQ_AGU).

### TABLE_TRUE (GPR) — LDS as consumer

LDS reads `Ra` as an address register, creating a true dependency. As a MIO_SLOW_OPS
consumer, the latency from common compute producers is 8 cycles:
```
MIO_SLOW_OPS:{Ra @RaRange, Rb @RbRange, Rc @RcRange, Re @ReRange}
FXU → MIO_SLOW: 8
FMAI → MIO_SLOW: 8
```

### TABLE_OUTPUT (GPR) — LDS as producer

LDS writes `Rd`, and its output latency to consumers is managed through the
decoupled scoreboard (VarLatOperandEnc on `dst_wr_sb`). There is no explicit
MIO_OPS producer row in TABLE_OUTPUT — the decoupled scoreboard mechanism
handles output dependency latency separately.

### Decoupled scoreboard

- `src_rel_sb` [115:113]: source release scoreboard (3-bit, default 7)
- `dst_wr_sb` [112:110]: destination write scoreboard (3-bit, default 7)
- `req_bit_set` [121:116]: request bit mask (6-bit)

## Verified encodings

All verified against `cuobjdump -arch sm_90 -sass` from `libcublas.so`:

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x000000001d100984` | `0x000e640000000800` | `@P0 LDS R16, [R29]` |
| `0x000100001d1b1984` | `0x000e280000000800` | `@P1 LDS R27, [R29+0x100]` |
| `0x000080001d190984` | `0x000e620000000800` | `@P0 LDS R25, [R29+0x80]` |
| `0xffdf80001b065984` | `0x000e260000000800` | `@P5 LDS R6, [R27+-0x2080]` |
| `0x0000000014120984` | `0x000eb00000000a00` | `@P0 LDS.64 R18, [R20]` |
| `0x0001000014120984` | `0x000e240000000a00` | `@P0 LDS.64 R18, [R20+0x100]` |
| `0xffdf800000140984` | `0x000e280000000a00` | `@P0 LDS.64 R20, [R0+-0x2080]` |
| `0x0000000017100984` | `0x000ea20000000c00` | `@P0 LDS.128 R16, [R23]` |
| `0x00010000170c1984` | `0x000e620000000c00` | `@P1 LDS.128 R12, [R23+0x100]` |
| `0xffdf000000100984` | `0x000e620000000c00` | `@P0 LDS.128 R16, [R0+-0x2100]` |
| `0xffe1000000047984` | `0x000e300000000c00` | `LDS.128 R4, [R0+-0x1f00]` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `ld.shared.u32 %r, [%ra]` | `LDS Rd, [Ra]` |
| `ld.shared.u64 %rd, [%ra]` | `LDS.64 Rd, [Ra]` |
| `ld.shared.u32 %r, [%ra+imm]` | `LDS Rd, [Ra+imm]` |
| `ld.shared.v4.u32 %r, [%ra]` | `LDS.128 Rd, [Ra]` |
| `__shared__` C++ array access | `LDS` with computed register address |

## Open questions

- **Stride variants `.X4`/`.X8`/`.X16`**: What PTX construct or optimization
  triggers them? Not present in cublas.
- **`lds_uniform_` (URb variant)**: What triggers the uniform register index
  form in SASS? Likely related to warp-wide uniform shared-memory access patterns.
- **Graphics shader restriction**: The `$ST_CS` constraint suggests separate LDS
  encodings or entirely different shared-memory instructions exist for graphics
  pipelines (VS/GS/TS/PS).
