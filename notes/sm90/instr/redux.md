# REDUX — Warp-wide reduction (uniform result)

**Opcode mnemonic:** `REDUX` = `0b1111000100` = **0x3c4** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VIRTUAL_QUEUE=$VQ_REDUX` (=28) | since sm_80 (crucible idx 192)

SASS lowering of PTX `redux.sync` (`__reduce_{add,min,max,and,or,xor}_sync`). Reduces a per-lane
32-bit register `Ra` across the warp's active lanes in a single instruction and writes the
warp-uniform result to a **uniform** register `URd`.

## Semantics (verified PTX→SASS)
| intrinsic / PTX | SASS | `op`[80:78] |
|-----------------|------|-------------|
| `__reduce_and_sync` / `redux.sync.and` | `REDUX URd, Ra` (AND, default) | 0 |
| `__reduce_or_sync`  / `redux.sync.or`  | `REDUX.OR`  | 1 |
| `__reduce_xor_sync` / `redux.sync.xor` | `REDUX.XOR` | 2 |
| `__reduce_add_sync` / `redux.sync.add` | `REDUX.SUM` | 3 |
| `__reduce_min_sync` / `redux.sync.min` | `REDUX.MIN[.S32]` | 4 |
| `__reduce_max_sync` / `redux.sync.max` | `REDUX.MAX[.S32]` | 5 |

`sz`[73]: **U32=0** (default, hidden), **S32=1** — only meaningful for MIN/MAX (signed vs
unsigned compare); the compiler picks it from the operand type. AND is `op`=0 so a bare `REDUX`
means AND. **Membermask is dropped** (as with VOTE/MATCH/SHFL) — REDUX has no mask operand and
reduces over the hardware active-lane mask.

## Variant overview
Single CLASS `redux_` / opcode 0x3c4, parameterized by `op` and `sz`. `op` 6,7 illegal
(`INVALID6/7` → `ILLEGAL_INSTR_ENCODING`).

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x3c4 | 13-bit |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard predicate (7=PT hidden) |
| [21:16] | `URd` | UniformRegister | uniform result (6-bit) |
| [31:24] | `Ra` | Register | per-lane source (≠R254) |
| [80:78] | `cache`=`op` | `REDUX_OP` | AND0 OR1 XOR2 SUM3 MIN4 MAX5 |
| [73] | `sz` | `REDUX_SZ` | U32=0 / S32=1 |
| [112:110] | `dst_wr_sb` | write scoreboard | |
| [124:122]∥[109:105] | `opex` | scheduling | |

## Cross-comparison (GPR→uniform family)
| op | reduction | latency (URd) |
|----|-----------|---------------|
| **REDUX** | full-warp int reduce (and/or/xor/sum/min/max) | **1** cyc (decoupled) |
| **R2UR** | move/OR to uniform | 13–15 cyc (coupled) |
| **S2UR** | special reg → uniform | 1 cyc |
| **FSWZADD** | FP32 quad swizzle-add | FMA-pipe |

REDUX / S2UR share the fast decoupled `R2UR_S2UR` latency group; R2UR is the slow coupled one.

## Latency (from sm_90_latencies.txt)
`udp_pipe`, `OP_R2UR = {R2UR, REDUX, S2UR}`; REDUX is in `R2UR_S2UR` with URd-producer latency
**1** cycle (`TABLE_*(UGPR)`). Decoupled (`VQ_REDUX`) — consumers wait via the write scoreboard.

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000020673c4` | `0x004e240000000000` | `REDUX UR6, R2` (AND) |
| `0x00000000020673c4` | `0x004e240000004000` | `REDUX.OR UR6, R2` |
| `0x00000000020673c4` | `0x004e240000008000` | `REDUX.XOR UR6, R2` |
| `0x00000000020673c4` | `0x004e24000000c000` | `REDUX.SUM UR6, R2` |
| `0x00000000020673c4` | `0x004e240000010000` | `REDUX.MIN UR6, R2` |
| `0x00000000020673c4` | `0x004e240000014000` | `REDUX.MAX UR6, R2` |
| `0x00000000020673c4` | `0x004e240000010200` | `REDUX.MIN.S32 UR6, R2` |
| `0x00000000020673c4` | `0x004e240000014200` | `REDUX.MAX.S32 UR6, R2` |

(Lo64 identical: `URd`=UR6, `Ra`=R2, opcode. op/sz differ only in Hi64: `op`[80:78]=bits[16:14],
`sz`[73]=bit9.) Decoder: `tools/decode_redux.py` (all 8 pass). Test: `tests/redux_test.cu`.

### PTX→SASS mapping
- `__reduce_add_sync(mask, x)` → `REDUX.SUM URd, Ra` (mask dropped)
- `__reduce_min_sync`/`max` on `int` → `.MIN.S32`/`.MAX.S32`; on `unsigned` → `.MIN`/`.MAX`
- `__reduce_and/or/xor_sync` → `REDUX`(AND)/`.OR`/`.XOR`.

## Open questions
- None significant — fully verified for all six ops and both signedness modes.
