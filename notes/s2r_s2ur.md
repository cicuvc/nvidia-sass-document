# S2R / S2UR — Read Special Register (→ GPR / uniform register)

**Opcode mnemonics:** `S2R` = `0b100100011001` = **0x919** (`mio_pipe`, MIO_SLOW) | `S2UR` = `0b100111000011` = **0x9c3** (`udp_pipe`) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` | S2R sm_70 / S2UR sm_73

Copy a hardware **special register** `SRa` into a general register (`S2R Rd`) or a uniform
register (`S2UR URd`). The canonical way to read `threadIdx`/`blockIdx`/`laneid`/lanemasks/
cluster IDs etc. `S2UR` is the uniform-datapath sibling, chosen when the SR value is
warp-uniform (e.g. `blockIdx`, `SR_CgaCtaId`) and consumed on the uniform datapath.

## Semantics
`Rd`/`URd` (32-bit) = value of special register `SRa` (`SRa`[79:72], 8-bit index). Both are
decoupled (S2R `VQ_UNORDERED`, S2UR `VQ_SR2UR`=29) — consumers wait via the write scoreboard.
`SRa` 84/85 (`SR_ESR_PC`/`_HI`) are trap-mode only (`ILLEGAL_INSTR_ENCODING` in user mode).

Not all SR reads use S2R: **`clock()`/`clock64()`** use the coupled **`CS2R`** (0x805) for the
`SR_CLOCKLO/HI` counters, and `blockDim`/`gridDim` usually come from the constant bank, not S2R.

## Fields (128-bit)
| bits | field | S2R | S2UR |
|------|-------|-----|------|
| [91]∥[11:0] | `opcode` | 0x919 | 0x9c3 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard (uniform pred) |
| [23:16] | `Rd` | dest GPR | — |
| [21:16] | `URd` | — | dest uniform reg (6-bit) |
| [79:72] | `SRa` | special-register index (8-bit) | same |
| [112:110] | `dst_wr_sb` | write scoreboard | write scoreboard |
| [124:122]∥[109:105] | `opex` | scheduling | scheduling |

`Rd` ≠ R254, ≤MAX_REG-1; `URd` ≤MAX_UREG-1.

## SpecialRegister index map (from sm_90_instructions.txt)
| # | name | # | name |
|---|------|---|------|
| 0 | SR_LANEID | 48–51 | SR_SWINLO/SWINSZ/SMEMSZ/SMEMBANKS |
| 1 | SR_CLOCK | 52–55 | SR_LWINLO/LWINSZ/LMEMLOSZ/LMEMHIOFF |
| 2 | SR_VIRTCFG | 56–60 | SR_EQMASK/LTMASK/LEMASK/GTMASK/GEMASK (lanemasks) |
| 3 | SR_VIRTID | 61–62 | SR_REGALLOC/BARRIERALLOC |
| 15 | SR_ORDERING_TICKET | 64–66 | SR_GLOBAL/CGA/WARP ERRORSTATUS |
| 16–20 | SR_PRIM_TYPE…SM_SHADER_TYPE | 67–68 | SR_VIRTUALSMID / SR_VIRTUALENGINEID |
| 24–27 | SR_MACHINE_ID_0..3 | 80–83 | SR_CLOCKLO/HI, SR_GLOBALTIMERLO/HI |
| 28–31 | SR_AFFINITY…WSCALEFACTOR_Z | 84–85 | SR_ESR_PC/_HI (**trap only**) |
| 32 | SR_TID | 96–99 | SR_HWTASKID, SR_CIRCULARQUEUE* |
| **33/34/35** | **SR_TID.X/Y/Z** | 100–115 | SR_PM0..SR_PM_HI7 |
| **37/38/39** | **SR_CTAID.X/Y/Z** | 116–131 | SR_SNAP_PM0..SR_SNAP_PM_HI7 |
| 40 | SR_NTID | 132–135 | SR_VARIABLE_RATE, TTU_TICKET_INFO, WARPGROUP_INFO, WARPGROUPID |
| 44 | SR_SM_SPA_VERSION | **136** | **SR_CgaCtaId** |
| 46/47 | SR_LWINHI/SWINHI | 137/138 | SR_GpcLocalCgaId / SR_CgaLinearMemorySlot |
| — | — | 139 / 255 | SR_CTARegPoolSz / SRZ |

(Note the gap at 36 between `SR_TID.Z`=35 and `SR_CTAID.X`=37. `SR_UGPU_ID`/`SR_SW_SCRATCH`
alias 24.)

## Latency (from sm_90_latencies.txt)
- **S2R**: `mio_pipe`, in `MIO_SLOW_OPS`; decoupled, consumers wait on write scoreboard.
- **S2UR**: `udp_pipe`, in `R2UR_S2UR`/`OP_R2UR` group; URd producer latency **1** cycle
  (`TABLE_*(UGPR)`), `VQ_SR2UR`.
- `OP_S2UR_S2R = {S2R, S2UR}` participate in `GMMA_SCOREBOARD_READERS` (they can read a
  warpgroup-MMA scoreboard SR).

## Verified encodings (sm_90, CUDA 13.1)
S2R (`tests/s2r_test.cu`):
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000000057919` | `0x000e2e0000000000` | `S2R R5, SR_LANEID` (0) |
| `0x0000000000057919` | `0x000e2e0000002100` | `S2R R5, SR_TID.X` (0x21=33) |
| `0x0000000000057919` | `0x000e2e0000002500` | `S2R R5, SR_CTAID.X` (0x25=37) |
| `0x0000000000057919` | `0x000e2e0000003800` | `S2R R5, SR_EQMASK` (0x38=56) |
| `0x0000000000077919` | `0x000e620000003900` | `S2R R7, SR_LTMASK` (0x39=57) |
| `0x0000000000077919` | `0x000e640000000300` | `S2R R7, SR_VIRTID` (3) |

S2UR (`libcublasLt.so`):
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000000679c3` | `0x000e620000002600` | `S2UR UR6, SR_CTAID.Y` (0x26=38) |
| `0x00000000001079c3` | `0x000f220000002500` | `S2UR UR16, SR_CTAID.X` (0x25=37) |
| `0x00000000000579c3` | `0x000e220000008800` | `S2UR UR5, SR_CgaCtaId` (0x88=136) |

Decoder: `tools/decode_s2r_s2ur.py` (all 9 vectors pass). Tests: `tests/s2r_test.cu`,
`tests/s2ur_test.cu`.

### PTX→SASS mapping
- `threadIdx.{x,y,z}` → `S2R Rd, SR_TID.{X,Y,Z}` (33/34/35)
- `blockIdx.{x,y,z}` → `S2R Rd, SR_CTAID.{X,Y,Z}` (37/38/39), or **`S2UR URd, SR_CTAID.*`** when uniform
- `%laneid` → `S2R Rd, SR_LANEID` (0); `%lanemask_{eq,lt,le,gt,ge}` → `SR_EQ/LT/LE/GT/GEMASK` (56–60)
- `%smid` → `S2R Rd, SR_VIRTUALSMID` (67); `clock()/clock64()` → `CS2R … SR_CLOCKLO` (not S2R)
- cluster: `SR_CgaCtaId` (136) etc. via `S2UR` on sm_90 cluster kernels.

## Open questions
- Exact trigger heuristic for S2R vs S2UR (only observed S2UR in warp-specialized/cluster
  cublasLt kernels; simple kernels keep S2R even for uniform `blockIdx`).
