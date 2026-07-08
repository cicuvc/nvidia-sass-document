# S2UR — Read Special Register (→ Uniform register)

**Opcode mnemonic:** `S2UR` = `0b100111000011` = **0x9c3** | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` | since sm_73

Copy a hardware **special register** `SRa` into a uniform register `URd`. The uniform-datapath sibling of `S2R`, chosen when the SR value is warp-uniform (e.g. `blockIdx`, `SR_CgaCtaId`) and consumed on the uniform datapath.

## Semantics
`URd` (32-bit) = value of special register `SRa` (`SRa`[79:72], 8-bit index). Decoupled (`VQ_SR2UR`=29) — consumers wait via the write scoreboard. `SRa` 84/85 (`SR_ESR_PC`/`_HI`) are trap-mode only.

Not all SR reads use S2UR: `clock()`/`clock64()` use **`CS2R`** for the `SR_CLOCKLO/HI` counters; `blockDim`/`gridDim` usually come from the constant bank.

## Fields (128-bit)
| bits | field | S2UR |
|------|-------|------|
| [91]∥[11:0] | `opcode` | 0x9c3 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard (uniform pred) |
| [21:16] | `URd` | dest uniform reg (6-bit) |
| [79:72] | `SRa` | special-register index (8-bit) |
| [112:110] | `dst_wr_sb` | write scoreboard |
| [124:122]∥[109:105] | `opex` | scheduling |

`URd` ≤MAX_UREG-1.

## Latency (from sm_90_latencies.txt)
`udp_pipe`, in `R2UR_S2UR`/`OP_R2UR` group; URd producer latency **1** cycle (`TABLE_*(UGPR)`), `VQ_SR2UR`. `OP_S2UR_S2R = {S2R, S2UR}` participate in `GMMA_SCOREBOARD_READERS`.

## Verified encodings (sm_90, libcublasLt.so)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000000679c3` | `0x000e620000002600` | `S2UR UR6, SR_CTAID.Y` (0x26=38) |
| `0x00000000001079c3` | `0x000f220000002500` | `S2UR UR16, SR_CTAID.X` (0x25=37) |
| `0x00000000000579c3` | `0x000e220000008800` | `S2UR UR5, SR_CgaCtaId` (0x88=136) |

Decoder: `tools/decode_s2r_s2ur.py` (all 9 vectors pass). Tests: `tests/s2ur_test.cu`.

### PTX→SASS mapping
- `blockIdx.{x,y,z}` → `S2UR URd, SR_CTAID.{X,Y,Z}` when uniform
- `SR_CgaCtaId` (136) → `S2UR` on sm_90 cluster kernels

## Open questions
- Exact trigger heuristic for S2R vs S2UR (only observed S2UR in warp-specialized/cluster cublasLt kernels; simple kernels keep S2R even for uniform `blockIdx`).
