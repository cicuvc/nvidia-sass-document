# R2UR — Register → Uniform Register

**Opcode mnemonic:** `R2UR` = `0b1011001010` = **0x2ca** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` | since sm_73 (crucible idx 164; sm_90 high-half variant `R2UR_H` idx 226)

Moves a per-lane general register `Ra` into a **uniform** register `URd` — the bridge from the
per-thread datapath to the uniform datapath. Unlike the fast decoupled uniform ops, R2UR is
**coupled** and slow (needs the warp to coordinate to produce a single uniform value).

## Semantics
- **`R2UR URd, Ra`** (noOR) — capture `Ra` into `URd` as a warp-uniform value. ptxas emits it
  when it knows `Ra` is uniform across the warp (or captures a representative/elected lane's
  value), often predicated (`@P0 R2UR …`) to take the value under a leader/uniform-branch guard.
- **`R2UR.OR Pu, URd, Ra`** (OR form, `/ORONLY`) — OR-reduce `Ra` across the active lanes into
  `URd` (a cross-lane OR reduction), with predicate `Pu`. (Not captured empirically.)

`Pu`[83:81] is a destination predicate (default PT, hidden in the noOR form). Sibling of the
other GPR→uniform paths: `REDUX` (full ADD/MIN/MAX/AND/OR/XOR reductions), `S2UR` (special
reg → uniform), `UP2UR` (predicate → uniform).

## Variant overview (2 CLASS, same opcode 0x2ca)
| CLASS | `OR`[84] | form |
|-------|----------|------|
| `r2ur__noOR` | 0 | `R2UR [Pu,] URd, Ra` |
| `r2ur__OR`   | 1 | `R2UR.OR Pu, URd, Ra` (`ORONLY`="OR"=1) |

`R2UR_H` (idx 226, sm_90) — the high-32b half of a 64-bit register→uniform move; collapses into
this R2UR encoding (TODO maps it `-> R2UR`). ptxas emits two R2UR for a 64-bit uniform pair.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x2ca |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [21:16] | `URd` | dest uniform reg (6-bit) |
| [31:24] | `Ra` | source GPR (≠R254) |
| [83:81] | `Pu` | dest predicate (default PT) |
| [84] | `OR` | 0=move, 1=`.OR` cross-lane OR-reduce |
| [112:110] | `dst_wr_sb` | pinned 0x7 |
| [124:122]∥[109:105] | `opex` | scheduling (+`.reuse` on Ra) |

`URd` ≤MAX_UREG-1; `Ra` ≠R254, ≤MAX_REG-1. IDEST/ISRC_A = 32.

## Latency (from sm_90_latencies.txt)
`udp_pipe`, but **coupled** and slow: `OP_R2UR_COUPLED = {R2UR}` has URd-producer latency
**13–15** cycles (`TABLE_*(UGPR)`), vs **1** cycle for `R2UR_S2UR = {REDUX, S2UR}`. The `Ra`
read connector is 1–2 cycles. It is carved out of `UDP_subset` (special-cased in the latency
model) precisely because of the cross-lane coupling cost. Part of `OP_R2UR = {R2UR, REDUX, S2UR}`.

## Verified encodings (sm_90, CUDA 13.1 — libcublasLt.so)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000040d02ca` | `0x008fe400000e0000` | `@P0 R2UR UR13, R4` |
| `0x00000000020c02ca` | `0x004fd600000e0000` | `@P0 R2UR UR12, R2` |
| `0x00000000000e72ca` | `0x002fda00000e0000` | `R2UR UR14, R0` |
| `0x00000000000772ca` | `0x002fda00000e0000` | `R2UR UR7, R0` |

Decoder: `tools/decode_r2ur.py` (real vectors + `.OR` round-trips pass).

### PTX→SASS mapping
- No direct PTX; ptxas-internal. Emitted when a per-lane value is moved to the uniform datapath
  (uniform address/loop bookkeeping in warp-specialized kernels), frequently under a leader
  predicate `@P0`.

## Open questions
- Exact noOR source semantics (assumes uniformity vs elects a lane) and the meaning of the `Pu`
  destination predicate; no `.OR` form was observed empirically (only constructed).
- Whether `R2UR_H` renders a distinct mnemonic/suffix or just a second R2UR on the high word.
