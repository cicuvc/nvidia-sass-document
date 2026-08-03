# R2UR — Register → Uniform Register

**Opcode mnemonic:** `R2UR` = `0b1011001010` = **0x2ca** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` | since sm_73 (crucible idx 164; sm_90 high-half variant `R2UR_H` idx 226)

Moves a per-lane general register `Ra` into a **uniform** register `URd` — the bridge from the
per-thread datapath to the uniform datapath. Unlike the fast decoupled uniform ops, R2UR is
**coupled** and slow (needs the warp to coordinate to produce a single uniform value).

## Semantics
- **`R2UR URd, Ra`** (noOR) — `URd = Ra` of the **first active lane** (lowest active laneid
  under the guard predicate). Verified on sm_120 silicon (RTX 5090):
  full warp → lane 0's value; `@P0` with lanes 8..31 active → lane 8's value (9); `@!P0`
  (lanes 0..7) → lane 0's value. A warp-uniform source yields the exact value.
- **`R2UR.OR Pu, URd, Ra`** (`/ORONLY`[84]) — **NOT a cross-lane OR-reduce on sm_120**:
  observed identical to the noOR form (first-active-lane capture) with uniform and divergent
  sources, full and partial active masks. The real cross-lane reduction is `REDUX.OR`
  (control probe: OR(1..32) = 0x3F). The earlier note's OR-reduce interpretation was
  speculation from the `ORONLY` name and is not supported by silicon behavior.
- **`R2UR.FILL/BROADCAST`** (sm_120 nonconformity variants, `NONCONFORMITY_FILL_BROADCAST`
  [87:86]: FILL=1, BROADCAST=2) — behave identically to the plain form in every configuration
  probed (uniform/divergent source, full/partial mask, no faults).

`Pu`[83:81] is a destination predicate (default PT, hidden in the noOR form). It read back **0**
via deterministic `P2R` readback in all probed cases (uniform/divergent source, full/partial
mask) — its role is unresolved (possibly a nonconformity/divergence status that only fires in
non-converged execution, or a no-op on this silicon). Sibling of the other GPR→uniform paths:
`REDUX` (full ADD/MIN/MAX/AND/OR/XOR reductions), `S2UR` (special reg → uniform), `UP2UR`
(predicate → uniform).

## Variant overview (sm_90: 2 CLASS; sm_120: 4 CLASS, same opcode 0x2ca)
| CLASS | `OR`[84] | nonconf[87:86] | form |
|-------|----------|----------------|------|
| `r2ur__noOR` | 0 | 0 | `R2UR [Pu,] URd, Ra` |
| `r2ur__OR`   | 1 | 0 | `R2UR.OR Pu, URd, Ra` (`ORONLY`="OR"=1) |
| `r2ur_nonconformity__noOR` (sm_120) | 0 | FILL/BROADCAST | `R2UR.FILL/BROADCAST [Pu,] URd, Ra` |
| `r2ur_nonconformity__OR` (sm_120) | 1 | FILL/BROADCAST | `R2UR.OR.FILL/BROADCAST Pu, URd, Ra` |

`R2UR_H` (idx 226, sm_90) — the high-32b half of a 64-bit register→uniform move; collapses into
this R2UR encoding (TODO maps it `-> R2UR`). sm_120 has **no separate `R2UR_H` mnemonic/class**;
ptxas emits two R2UR for a 64-bit uniform pair — verified on silicon (R2 → UR16 low word,
R3 → UR17 high word round-trips exactly).

## Fields (128-bit)
| bits | field | notes |
|------|-------|------|
| [91]∥[11:0] | `opcode` | 0x2ca |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [23:16] | `URd` | dest uniform reg — **sm_120: 8-bit**; sm_90: 6-bit at [21:16] |
| [31:24] | `Ra` | source GPR (≠R254) |
| [83:81] | `Pu` | dest predicate (default PT) |
| [84] | `OR` (sm_120: `clear`) | 0=move, 1=`.OR` (observed = same capture, not a reduce) |
| [87:86] | `nonconformity` | sm_120 only: 0 / FILL=1 / BROADCAST=2 |
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

### sm_120 encodings (assembler-verified, RTX 5090)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000021072ca` | `0x000fca00000e0000` | `R2UR UR16, R2` |
| `0x00000000021072ca` | `0x000fca0000100000` | `R2UR.OR P0, UR16, R2` |
| `0x00000000021072ca` | `0x000fca0000400000` | `R2UR.FILL P0, UR16, R2` |
| `0x00000000021072ca` | `0x000fca0000800000` | `R2UR.BROADCAST P0, UR16, R2` |
| `0x00000000021072ca` | `0x000fca00004e0000` | `R2UR.FILL UR16, R2` (Pu=PT default → 0b111) |

### PTX→SASS mapping
- No direct PTX; ptxas-internal. Emitted when a per-lane value is moved to the uniform datapath
  (uniform address/loop bookkeeping in warp-specialized kernels), frequently under a leader
  predicate `@P0`.

## Open questions
- `Pu` destination predicate: consistently 0 in every probed case — does it ever set?
  (Speculative: a nonconformity/divergence status for non-converged execution.)
- `.OR`/`.FILL`/`.BROADCAST` all behave identically under converged execution; whether the
  variants differ under true thread divergence (different PCs, not just predicate masks)
  is untested — constructing that needs a branch/reconvergence setup.
