# LDSM — Load from Shared Memory to Matrix Register

**Opcode mnemonic:** `LDSM`
**Pipe:** `mio_pipe` (MIO_SLOW_OPS subset)
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` (decoupled read/write scoreboard)
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Loads data from shared memory into registers with a **matrix-aware layout**
(stride + element-size conversion). Part of the tensor-core data-movement pair:
LDSM loads from shared memory into GPRs, STSM stores from GPRs to shared memory.
The loaded data is typically fed into HMMA/IMMA tensor-core compute instructions.

- **Plain (sImmOffset):** `Rd = LDSM.sz.mode.num [Ra + offset]`
- **Uniform (UR_sI_R):** `Rd = LDSM.sz.mode.num [Ra + URb + offset]` (uniform register index)

Unlike standard LDS, LDSM supports **element-size conversion** during load:
`.U4TO8`/`.S4TO8` (4→8 bit upcast) and `.U2TO4`/`.S2TO4` (2→4 bit upcast),
paired with matrix layout modes M88/MT88/M816/M832. This is essential for
feeding sub-16-bit quantized data into tensor cores.

Each `num` value loads a different number of destination registers:
- `.1`: 1 register (32 bits)
- `.2`: 2 registers (64 bits, Rd aligned to 2)
- `.4`: 4 registers (128 bits, Rd aligned to 4)

IDEST_SIZE = 32 / 64 / 128 accordingly.

## Variant overview

LDSM has **2 encoding variants** across **2 opcodes** (plus 2 ALTERNATE CLASS pseudo ops):

| Class | Opcode | Address mode |
|-------|--------|-------------|
| `ldsm__UR_sI_R` | `0b1100000111011` (`0x183b`) | Ra + URb + signed 24-bit offset |
| `ldsm__sImmOffset` | `0b100000111011` (`0x83b`) | Ra + signed 24-bit offset |

Bit [91] distinguishes UR (1) vs sImm (0). Lower 12 bits are identical (`0x83b`).

## Shader constraint

LDSM is **restricted to Compute Shaders (CS)**:
```
(%SHADER_TYPE == $ST_UNKNOWN) || ((%SHADER_TYPE == $ST_TRAP)||(%SHADER_TYPE == $ST_CS))
```

## Modifiers

### Element size and conversion (`sz`) — bits [77:75], enum `LDSM_SZ`

| Value | Mnemonic | Description |
|:-----:|----------|-------------|
| 0     | `.16`    | 16-bit elements (no conversion) |
| 1     | `.U4TO8` | Unsigned 4→8 bit upcast |
| 2     | `.S4TO8` | Signed 4→8 bit upcast |
| 3     | `.U2TO4` | Unsigned 2→4 bit upcast |
| 4     | `.S2TO4` | Signed 2→4 bit upcast |
| 5–7   | INVALID  | Illegal encoding error |

### Matrix layout mode (`mode`) — bits [79:78], enum `LDSM_MODE`

| Value | Mnemonic | Description |
|:-----:|----------|-------------|
| 0     | `M88`    | 8×8 matrix tile |
| 1     | `MT88`   | Transposed 8×8 matrix tile |
| 2     | `M816`   | 8×16 matrix tile |
| 3     | `M832`   | 8×32 matrix tile |

**Legal combos enforced by CONDITIONS:**
- M88 / MT88 → require sz = `.16`
- M816 → requires sz = `.U4TO8` or `.S4TO8`
- M832 → requires sz = `.U2TO4` or `.S2TO4`

### Number of registers (`num`) — bits [73:72], enum `LDSM_NUM`

| Value | Mnemonic | Registers loaded | Alignment |
|:-----:|----------|:---------------:|:---------:|
| 0     | `.1` (default) | 1 | None |
| 1     | `.2`         | 2 | Rd % 2 == 0 |
| 2     | `.4`         | 4 | Rd % 4 == 0 |
| 3     | INVALID      | — | Illegal encoding error |

## Bit layout (128-bit)

```
Bit  127                                                                          0
      ...#####.####.####...........###.#..###...........######................########
      ###############.####........####################################################
```

### ldsm__UR_sI_R (opcode 0x183b)

| Bits | Width | Field | Source |
|------|:---:|-------|--------|
| [124:122],[109:105] | 8 | opex | TABLES_opex_0(batch_t, usched_info) |
| [121:116] | 6 | req_bit_set | req_bit_set |
| [115:113] | 3 | src_rel_sb | VarLatOperandEnc(src_rel_sb) |
| [112:110] | 3 | dst_wr_sb | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | 2 | pm_pred | pm_pred |
| [91][11:0] | 13 | opcode | 0x183b |
| [79:78] | 2 | stride/mode | mode |
| [77:75] | 3 | sz | sz |
| [73:72] | 2 | num | num |
| [63:40] | 24 | Ra_offset | Ra_offset (signed) |
| [37:32] | 6 | Ra_URb | Ra_URb (uniform register) |
| [31:24] | 8 | Ra | Ra |
| [23:16] | 8 | Rd | Rd |
| [15] | 1 | Pg_not | Pg@not |
| [14:12] | 3 | Pg | Pg |

### ldsm__sImmOffset (opcode 0x83b)

Same as above except:
- Bit [91] = 0 (opcode 0x83b)
- No `Ra_URb` field (bits [37:32] unused/default)

## LDSM vs LDS comparison

| Property | LDSM | LDS |
|----------|------|-----|
| Purpose | Tensor-core matrix load | General shared memory load |
| Opcode | `0x183b` / `0x83b` | `0x1984` / `0x984` |
| Size modifiers | `.16`/`.U4TO8`/`.S4TO8`/`.U2TO4`/`.S2TO4` | `.U8`/`.S8`/`.U16`/`.S16`/32/`.64`/`.128` |
| Layout modes | M88/MT88/M816/M832 | (none) |
| Register count | num (1/2/4 regs) | implicit from sz |
| UR variant | Ra_URb at [37:32] | Ra_URb at [37:32] |
| Uniform reg name | Ra_URb | Ra_URb |
| VQ | `$VQ_AGU` | `$VQ_AGU` |
| MIO subset | MIO_SLOW_OPS | MIO_SLOW_OPS |
| Shader constraint | CS only | CS only |

## Latency

MIO pipe, MIO_SLOW_OPS subset, decoupled scoreboard ($VQ_AGU).

### TABLE_TRUE (GPR) — LDSM as consumer

LDSM reads `Ra` as an address register. As MIO_SLOW_OPS, true dependency
latency from common compute producers is **8 cycles** (8th column in TABLE_TRUE).

### TABLE_OUTPUT (GPR) — LDSM as producer

LDSM writes `Rd` via decoupled scoreboard (VarLatOperandEnc). Output latency
from MIO_OPS producers to various consumers is **1 cycle** for most pipes
(column 6 = MIO_OPS in TABLE_OUTPUT).

### Decoupled scoreboard

- `src_rel_sb` [115:113]: source release scoreboard (3-bit, default 7)
- `dst_wr_sb` [112:110]: destination write scoreboard (3-bit, default 7)
- `req_bit_set` [121:116]: request bit mask (6-bit)

## Cross-comparison with STSM

| Property | LDSM (load) | STSM (store) |
|----------|-------------|--------------|
| Data direction | shared mem → GPR | GPR → shared mem |
| Dest/src reg | Rd | Rb |
| Scoreboard type | RD_WR | RD only |
| Size modifiers | 5 values (16/U4TO8/S4TO8/U2TO4/S2TO4) | ONLY16 |
| Mode modifiers | 4 values (M88/MT88/M816/M832) | 2 values (M88/MT88) |
| UR field | Ra_URb at [37:32] | Ra_URc at [69:64] |

## PTX→SASS mapping

LDSM implements `ldmatrix` on sm_90. Detailed mapping in `ptx2sass-ldmatrix-stmatrix.md`.

On sm_90, only `.m8n8` shape + `.b16` type is reachable via PTX. The M816/M832 modes
and sub-16-bit sz values exist in the encoding but require Blackwell+ (sm_100a+)
architectures which expose `.m16n16` and `.m8n16` shapes.

| PTX | SASS |
|-----|------|
| `ldmatrix.sync.aligned.m8n8.x1.b16` | `LDSM.16.M88.1 Rd, [Ra+offset]` |
| `ldmatrix.sync.aligned.m8n8.x1.trans.b16` | `LDSM.16.MT88.1 Rd, [Ra+offset]` |
| `ldmatrix.sync.aligned.m8n8.x{2,4}.b16` | `LDSM.16.M88.{2,4} Rd, [Ra+offset]` |

## Open questions

- **Element-size conversion semantics**: How exactly does `.U4TO8` map 4-bit
  values to 8-bit register lanes? Needs microbenchmark verification.
- **Matrix layout details**: The memory layout implied by M88/MT88/M816/M832
  modes — are these standard row-major/column-major matrices with the given
  dimensions, or something specific to tensor-core data ordering?
- **Relationship to HMMA/IMMA**: What is the exact data-layout contract between
  LDSM-loaded registers and HMMA/IMMA input operands?
- **pseudo_ops ALTERNATE CLASS**: The two `ldsm_pseudo_ops_*` variants have the
  same opcodes but with a `PSEUDO_OP` discriminator. What triggers these?
