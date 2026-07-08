# STSM — Store to Shared Memory, Matrix Layout

**Opcode mnemonic:** `STSM`
**Pipe:** `mio_pipe` (MIO_SLOW_OPS subset)
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` (decoupled read scoreboard — no writeback)
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Stores data from registers into shared memory with a **matrix-aware layout**.
The store analogue of LDSM: STSM writes GPR data to shared memory in the tile
format expected by tensor-core consumers (LDSM loads, HMMA/IMMA compute).

- **Plain (sImmOffset):** `smem[Ra + offset] = Rb`
- **Uniform (UR_sI_R):** `smem[Ra + URc + offset] = Rb` (uniform register index)

Unlike LDSM, STSM is **simpler**: only 16-bit element size, only M88/MT88
matrix modes, no on-the-fly element-size conversion.

Each `num` value stores a different number of source registers:
- `.1`: 1 register (32 bits)
- `.2`: 2 registers (64 bits, Rb aligned to 2)
- `.4`: 4 registers (128 bits, Rb aligned to 4)

ISRC_B_SIZE = 32 / 64 / 128 accordingly. IDEST_SIZE = 0 (store has no dest register).

## Variant overview

STSM has **2 encoding variants** across **2 opcodes**:

| Class | Opcode | Address mode |
|-------|--------|-------------|
| `stsm__UR_sI_R` | `0b1100001000100` (`0x1844`) | Ra + URc + signed 24-bit offset |
| `stsm__sImmOffset` | `0b100001000100` (`0x844`) | Ra + signed 24-bit offset |

Bit [91] distinguishes UR (1) vs sImm (0). Lower 12 bits are identical (`0x844`).

## Shader constraint

STSM is **restricted to Compute Shaders (CS)**:
```
(%SHADER_TYPE == $ST_UNKNOWN) || ((%SHADER_TYPE == $ST_TRAP)||(%SHADER_TYPE == $ST_CS))
```

## Modifiers

### Element size (`sz`) — bit [75], enum `ONLY16`

| Value | Mnemonic | Description |
|:-----:|----------|-------------|
| 0     | `.16`    | 16-bit elements (only option) |

STSM only supports 16-bit elements — no `.U4TO8`/`.U2TO4` conversion modes.

### Matrix layout mode (`mode`) — bit [78], enum `STSM_MODE`

| Value | Mnemonic | Description |
|:-----:|----------|-------------|
| 0     | `M88`    | 8×8 matrix tile |
| 1     | `MT88`   | Transposed 8×8 matrix tile |

Only M88 and MT88 — no M816 or M832 (those are LDSM-only, for element-size
conversion during load).

### Number of registers (`num`) — bits [73:72], enum `LDSM_NUM` (shared with LDSM)

| Value | Mnemonic | Registers stored | Alignment |
|:-----:|----------|:---------------:|:---------:|
| 0     | `.1` (default) | 1 | None |
| 1     | `.2`         | 2 | Rb % 2 == 0 |
| 2     | `.4`         | 4 | Rb % 4 == 0 |
| 3     | INVALID      | — | Illegal encoding error |

## Bit layout (128-bit)

```
Bit  127                                                                          0
      ...#####.####.####.......###.#..#.........#......################........####
      ###################.####........##############################################
```

### stsm__UR_sI_R (opcode 0x1844)

| Bits | Width | Field | Source |
|------|:---:|-------|--------|
| [124:122],[109:105] | 8 | opex | TABLES_opex_0(batch_t, usched_info) |
| [121:116] | 6 | req_bit_set | req_bit_set |
| [115:113] | 3 | src_rel_sb | VarLatOperandEnc(src_rel_sb) |
| [112:110] | 3 | dst_wr_sb | fixed `7` (no dest writeback) |
| [103:102] | 2 | pm_pred | pm_pred |
| [91][11:0] | 13 | opcode | 0x1844 |
| [78] | 1 | mode | mode |
| [75] | 1 | sz | sz |
| [73:72] | 2 | num | num |
| [69:64] | 6 | Ra_URc | Ra_URc (uniform register) |
| [63:40] | 24 | Ra_offset | Ra_offset (signed) |
| [39:32] | 8 | Rb | Rb (source data) |
| [31:24] | 8 | Ra | Ra (base address) |
| [15] | 1 | Pg_not | Pg@not |
| [14:12] | 3 | Pg | Pg |

### stsm__sImmOffset (opcode 0x844)

Same as above except:
- Bit [91] = 0 (opcode 0x844)
- No `Ra_URc` field (bits [69:64] unused/default)

## Key differences from LDSM

| Property | STSM | LDSM |
|----------|------|------|
| Direction | GPR → shared mem | shared mem → GPR |
| Scoreboard type | RD only | RD_WR |
| dest writeback | dst_wr_sb = 7 (constant) | VarLatOperandEnc(dst_wr_sb) |
| IDEST_SIZE | 0 | 32/64/128 |
| Data reg field | Rb at [39:32] | Rd at [23:16] |
| Size enum | ONLY16 (1-bit [75]) | LDSM_SZ (3-bit [77:75]) |
| Mode enum | STSM_MODE (1-bit [78]) | LDSM_MODE (2-bit [79:78]) |
| Mode values | M88, MT88 | M88, MT88, M816, M832 |
| Uniform reg | Ra_URc at [69:64] | Ra_URb at [37:32] |
| sz is src/dest size | ISRC_B_SIZE (source data size) | IDEST_SIZE (dest data size) |

## Latency

MIO pipe, MIO_SLOW_OPS subset, decoupled read scoreboard ($VQ_AGU).

### TABLE_TRUE (GPR) — STSM as consumer

STSM reads `Ra` (address) and `Rb` (source data). As MIO_SLOW_OPS, true
dependency latency from common compute producers is **8 cycles**.

### TABLE_OUTPUT (GPR) — STSM as producer

IDEST_SIZE = 0 — STSM has no destination register, so it does not appear as a
producer in TABLE_OUTPUT. It only generates write traffic to shared memory.

### Decoupled scoreboard

- `src_rel_sb` [115:113]: source release scoreboard (3-bit, default 7)
- `dst_wr_sb` [112:110]: hardwired to `7` (no writeback needed for store)
- `req_bit_set` [121:116]: request bit mask (6-bit)

## Relation to tensor-core compute

STSM and LDSM form the shared-memory data-movement pair for tensor-core
instructions (HMMA/IMMA/GMMA). A typical tensor-core kernel uses:

1. **LDSM** to load weight/activation tiles from shared memory into GPRs
2. **HMMA**/IMMA to compute matrix multiply-accumulate using those GPRs
3. **STSM** to store accumulated results back to shared memory

The matrix layout modes (M88/MT88) match the tile dimensions expected by
HMMA/IMMA instructions.

## PTX→SASS mapping

STSM implements `stmatrix` on sm_90. Detailed mapping in `ptx2sass-ldmatrix-stmatrix.md`.

On sm_90, only `.m8n8` shape + `.b16` type is reachable via PTX. The PTX spec
indicates `stmatrix` requires `sm_90` or higher, but `.m16n8` shape requires Blackwell+.

| PTX | SASS |
|-----|------|
| `stmatrix.sync.aligned.m8n8.x1.b16` | `STSM.16.M88.1 [Ra+offset], Rb` |
| `stmatrix.sync.aligned.m8n8.x1.trans.b16` | `STSM.16.MT88.1 [Ra+offset], Rb` |
| `stmatrix.sync.aligned.m8n8.x{2,4}.b16` | `STSM.16.M88.{2,4} [Ra+offset], Rb` |

## Open questions

- **STSM_MODE MT88**: Does the transposed layout map directly to HMMA's operand
  transposition, or is additional data shuffling needed?
- **Ra_URc vs Ra_URb**: Why does STSM use a different uniform register slot
  name (URc vs URb) compared to LDSM? The URc naming suggests it occupies the
  "C" operand position of the address generation pipeline, but the functional
  role (stride index) appears identical to LDSM's URb.
- **Size asymmetry**: Why does STSM only support 16-bit elements while LDSM
  supports 4-to-8 and 2-to-4 upcasts? Possibly because stores don't need
  conversion (data is already in the tensor-core's native format after compute).
