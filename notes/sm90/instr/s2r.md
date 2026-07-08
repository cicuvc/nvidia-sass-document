# S2R — Read Special Register (→ GPR)

**Opcode mnemonic:** `S2R` = `0b100100011001` = **0x919** | **Pipe:** `mio_pipe` (MIO_SLOW) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` | since sm_70

Copy a hardware **special register** `SRa` into a general register `Rd`. The canonical way to read `threadIdx`/`blockIdx`/`laneid`/lanemasks/cluster IDs etc.

## Semantics
`Rd` (32-bit) = value of special register `SRa` (`SRa`[79:72], 8-bit index). Decoupled (`VQ_UNORDERED`) — consumers wait via the write scoreboard. `SRa` 84/85 (`SR_ESR_PC`/`_HI`) are trap-mode only (`ILLEGAL_INSTR_ENCODING` in user mode).

Not all SR reads use S2R: **`clock()`/`clock64()`** use the coupled **`CS2R`** (0x805) for the `SR_CLOCKLO/HI` counters.

## Fields (128-bit)
| bits | field | S2R |
|------|-------|-----|
| [91]∥[11:0] | `opcode` | 0x919 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [23:16] | `Rd` | dest GPR |
| [79:72] | `SRa` | special-register index (8-bit) |
| [112:110] | `dst_wr_sb` | write scoreboard |
| [124:122]∥[109:105] | `opex` | scheduling |

`Rd` ≠ R254, ≤MAX_REG-1.

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

(Note the gap at 36 between `SR_TID.Z`=35 and `SR_CTAID.X`=37.)

## Latency (from sm_90_latencies.txt)
`mio_pipe`, in `MIO_SLOW_OPS`; decoupled, consumers wait on write scoreboard. `OP_S2UR_S2R = {S2R, S2UR}` participate in `GMMA_SCOREBOARD_READERS` (they can read a warpgroup-MMA scoreboard SR).

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000000057919` | `0x000e2e0000000000` | `S2R R5, SR_LANEID` (0) |
| `0x0000000000057919` | `0x000e2e0000002100` | `S2R R5, SR_TID.X` (0x21=33) |
| `0x0000000000057919` | `0x000e2e0000002500` | `S2R R5, SR_CTAID.X` (0x25=37) |
| `0x0000000000057919` | `0x000e2e0000003800` | `S2R R5, SR_EQMASK` (0x38=56) |
| `0x0000000000077919` | `0x000e620000003900` | `S2R R7, SR_LTMASK` (0x39=57) |
| `0x0000000000077919` | `0x000e640000000300` | `S2R R7, SR_VIRTID` (3) |

Decoder: `tools/decode_s2r_s2ur.py` (all 9 vectors pass). Tests: `tests/s2r_test.cu`.

### PTX→SASS mapping
- `threadIdx.{x,y,z}` → `S2R Rd, SR_TID.{X,Y,Z}` (33/34/35)
- `blockIdx.{x,y,z}` → `S2R Rd, SR_CTAID.{X,Y,Z}` (37/38/39)
- `%laneid` → `S2R Rd, SR_LANEID` (0); `%lanemask_{eq,lt,le,gt,ge}` → `SR_EQ/LT/LE/GT/GEMASK` (56–60)
- `%smid` → `S2R Rd, SR_VIRTUALSMID` (67); `clock()/clock64()` → `CS2R … SR_CLOCKLO` (not S2R)

## Open questions
- None significant.
