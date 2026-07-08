# STS — Store to Shared Memory

**Opcode mnemonic:** `STS`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` (decoupled read-only scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Stores source register `Rb` into shared memory at address `[Ra + stride×URc + offset]`.

- **Plain (sImmOffset):** `smem[Ra + offset] = Rb` (Ra != RZ, signed 24-bit offset)
- **Plain (uImmOffset):** `smem[RZ + offset] = Rb` (Ra == RZ, unsigned 24-bit offset, no stride)
- **Uniform (sts_uniform_):** `smem[RZ + stride×URc + offset] = Rb` (uniform register index)

Compare with LDS which loads *from* shared memory; STS stores *to* shared memory.
The formats are symmetric: LDS reads `Rd`, STS writes `Rb`; LDS has `dst_wr_sb`,
STS has `dst_wr_sb=7` (hardwired, no variable-latency write scoreboard since
there's no destination register).

## Variant overview

3 encoding variants across 2 opcodes:

| Class | Opcode | Ra | Stride | Notes |
|-------|--------|:---:|:---:|-------|
| `sts__sImmOffset` | `0b1110001000` (`0x388`) | Ra != RZ | Yes | Signed 24-bit offset |
| `sts__uImmOffset` | `0b1110001000` (`0x388`) | Ra == RZ (0xFF) | No | Unsigned 24-bit offset |
| `sts_uniform_` | `0b1100110001000` (`0x1988`) | Ra == RZ | Yes | URc uniform register index |

## STS vs LDS — encoding comparison

| Field | LDS | STS |
|-------|-----|-----|
| Semantics | `Rd = smem[...]` | `smem[...] = Rb` |
| Opcode | `0x984` / `0x1984` | `0x388` / `0x1988` |
| Data register | `Rd` @ [23:16] | `Rb` @ [39:32] |
| IDEST_SIZE | 32/64/128 | 0 (no dest) |
| ISRC_B_SIZE | 0 | 32/64/128 |
| dst_wr_sb | VarLatOperandEnc | Hardwired 7 |
| Scoreboard | `INST_TYPE_DECOUPLED_RD_WR_SCBD` | `INST_TYPE_DECOUPLED_RD_SCBD` |
| Uniform reg | URb @ [37:32] | URc @ [69:64] |

## Modifiers

### Size (`sz`) — bits [75:73]

| Value | Mnemonic | Store width | Rb alignment |
|:-----:|----------|-------------|--------------|
| 0     | `.U8`    | 8-bit | — |
| 1     | `.S8`    | 8-bit | — |
| 2     | `.U16`   | 16-bit | — |
| 3     | `.S16`   | 16-bit | — |
| 4     | (default) | 32-bit | — |
| 5     | `.64`    | 64-bit | Rb % 2 == 0 |
| 6     | `.128`   | 128-bit | Rb % 4 == 0 |
| 7     | —        | `ILLEGAL_INSTR_ENCODING_ERROR` |

### Stride (`stride`) — bits [79:78]

Same as LDS: X1=0 (default), X4=1, X8=2, X16=3. Absent from uImmOffset variant.

## Shader constraint

CS shader only (same as LDS):
```
(%SHADER_TYPE == $ST_UNKNOWN) || ((%SHADER_TYPE == $ST_TRAP)||(%SHADER_TYPE == $ST_CS))
```

## Bit layout (non-uniform, 128-bit)

```
Bit  127                                                                          0
      ...###.####...........####.###......##..###.........
      ........#########################.......................

Field (sts__sImmOffset):
  [124:122],[109:105]  8b  opex        <= TABLES_opex_0(batch_t, usched_info)
  [121:116]            6b  req_bit_set         
  [115:113]            3b  src_rel_sb   <= VarLatOperandEnc(src_rel_sb)
  [112:110]            3b  dst_wr_sb    <= 7 (hardwired)
  [103:102]            2b  pm_pred             
  [91],[11:0]         13b  opcode       (0x388 for non-uniform)
  [79:78]              2b  stride       (absent in uImmOffset)
  [75:73]              3b  sz           (U8=0..128=6, INVALID7)
  [63:40]             24b  Ra_offset    (signed/unsigned 24-bit)
  [39:32]              8b  Rb           (source data register)
  [31:24]              8b  Ra           (*Ra for RaRZ/uImmOffset)
  [15]                 1b  Pg_not       
  [14:12]              3b  Pg           
```

### Uniform variant additions

```
  [69:64]  6b  Ra_URc       (uniform register index, different bits from LDS URb)
```

## Latency

MIO pipe, MIO_SLOW_OPS subset, decoupled read-only scoreboard.

- `INST_TYPE_DECOUPLED_RD_SCBD`: only read scoreboard active; write side is
  hardwired (no output register to track).
- `ISRC_A_SIZE = 32` (address register), `ISRC_B_SIZE = 32/64/128` (data register)
- `IDEST_SIZE = 0` — no destination, no write dependency created
- As consumer: same MIO_SLOW_OPS latency (8 cycles from compute producers)
- No output dependency latency — STS doesn't produce a register value

## Verified encodings

All verified against `cuobjdump -arch sm_90 -sass` from `libcublas.so`:

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x002080061a00c388` | — | `@!P4 STS [R26+0x2080], R6` |
| `0x000000151a009388` | — | `@!P1 STS [R26], R21` |
| `0x0020a0081400a388` | — | `@!P2 STS [R20+0x20a0], R8` |
| `0x0000401718008388` | — | `@!P0 STS [R24+0x40], R23` |
| `0x0021200d16007388` | — | `STS [R22+0x2120], R13` |
| `0x000080081b00b388` | — | `@!P3 STS.64 [R27+0x80], R8` |
| `0x000000121b009388` | — | `@!P1 STS.64 [R27], R18` |
| `0x0000000c07007388` | — | `STS.64 [R7], R12` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `st.shared.u32 [%ra], %rb` | `STS [Ra], Rb` |
| `st.shared.u64 [%ra], %rd` | `STS.64 [Ra], Rb` |
| `st.shared.v4.u32 [%ra], %rb` | `STS.128 [Ra], Rb` |
| `__shared__` C++ store | `STS` with computed register address |

## Open questions

- **Stride variants `.X4`/`.X8`/`.X16`**: Not present in cublas.
- **`sts_uniform_` (URc variant)**: What triggers the uniform register form?
- **Why URc at [69:64] vs LDS's URb at [37:32]?** The bit position difference
  is notable — possibly reflects a different micro-architectural pipeline slot.
