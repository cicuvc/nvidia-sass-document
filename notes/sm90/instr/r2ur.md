# R2UR — Register → Uniform Register

**Opcode mnemonic:** `R2UR` = `0b1011001010` = **0x2ca** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` | since sm_73 (crucible idx 164; sm_90 high-half variant `R2UR_H` idx 226)

Moves a per-lane general register `Ra` into a **uniform** register `URd` — the bridge from the
per-thread datapath to the uniform datapath. Unlike the fast decoupled uniform ops, R2UR is
**coupled** and slow (needs the warp to coordinate to produce a single uniform value).

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). A real sm_90 rerun is currently blocked because the accompanying test source
> uses sm_120 FORMAT shapes the sm_90 spec rejects at match time.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

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
  probed (uniform/divergent source, full/partial predicated mask, true branch divergence, no
  faults).

`Pu`[83:81] is a destination predicate (default PT, hidden in the noOR form). **RESOLVED on
sm_120 silicon: it is a per-lane (non-uniform) nonconformity mask — every *active* lane whose
`Ra` differs from the captured uniform value (first active lane's `Ra`) gets `Pu=1`; all other
lanes — the elected lane, equal-valued lanes, and inactive/predicated-off lanes — are
**preserved** (Pu is write-1-only, never clears 0).** Evidence:
- divergent source, full mask, P0 pre-set 0: `Pu = (0, 1×31)` — elected lane 0 (value == captured)
  untouched; the 31 differing lanes written 1.
- same with P0 pre-set 1: `Pu = (1×32)` — the elected lane *keeps* its 1 (never cleared); the
  differ lanes would be written 1 anyway. This rules out a full pred-file write.
- value `(laneid&8) ? 0xAA : 0x55`, full mask, P0 pre-set 0: `Pu = 0×8, 1×8, 0×8, 1×8` —
  lanes 0..7 and 16..23 carry the captured 0x55 → preserved 0; lanes 8..15/24..31 carry 0xAA →
  written 1. Exactly the "differs-from-captured" mask.
- predicated partial mask (lanes ≥8), divergent source, P0 pre-set 1: lanes 0..7 (inactive,
  preserved 1), lane 8 (elected, preserved 1), lanes 9..31 (written 1) — all 1.
- guard fully off (`@P1` with P1=0 for all lanes), P0 pre-set 1: nothing written, all lanes keep 1.
- true divergence (R2UR on a branch path, mask 0..15 while lanes 16..31 run a different PC):
  same behavior — lane 0 preserved, lanes 1..15 written 1, lanes outside the mask untouched.
- `.OR`, `.FILL`, `.BROADCAST` (and `.OR.FILL`) all produce identical Pu patterns.

The earlier "Pu always reads 0" observation (test_r2ur.py v1) is explained: a **uniform** readback
collapses the predicate to the *elected lane's* bit, which is never written — it stays at its
initial 0. Pu must be read **per-lane** (e.g. `P2R R3, PR, RZ, 0x1` then a per-lane store) to be
seen.

**Stall note**: R2UR has no write scoreboard (`dst_wr_sb` pinned 0x7) and is coupled, so any
consumer of its outputs must pad statically. Pu RAW latency measured by static-stall sweep
(divergent source, P0 pre-set 0, per-lane P2R readback):
- `WAIT1..3_END_GROUP` (usched 1..3, zero filler) → **stale** (reads the old P0 value, all 0);
- `WAIT4`/`WAIT5_END_GROUP` → correct with zero filler — Pu lands at ~4–5 static cycles;
- `usched=0` = `OFF_DECK_DRAIN` (warp stops issuing until the pipeline drains) → always
  correct, which is why an earlier "stall=0 always reads right" sweep was misleading;
- one dependent `IADD3` filler (~5+ cycles) after WAIT1..3 also suffices.
**The `yield` flavor (transn, usched 17..27 — the bracket's 5th field) does not change the
timing**: `trans1..3` are equally stale, `trans4..7` settle, at zero filler. It is only a
scheduling/convergence hint (0x10 bit in the 5-bit usched field; ptxas uses the trans forms at
block ends). `usched=16` (yield=0/stall=0) is a **gap** in `USCHED_INFO`/`TABLES_opex_*` — the
assembler rejects it with `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR`.
The URd result takes the full 13–15 cycle coupled latency (Latency section) — when consuming
both outputs, pad for URd. ptxas emits R2UR with the WAIT5 schedule (see verified encodings).
Sibling of the other GPR→uniform paths:
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
- Pu semantics are resolved for converged and branch-diverged execution (per-lane
  write-1-only nonconformity mask, see above). Remaining: is the write-1 set computed with
  full 32-bit equality on `Ra` (probed), and is there any scenario on sm_90 (untested here —
  all probes on sm_120/RTX 5090) where Pu differs? Also untested: sm_90 silicon itself,
  and whether the `.OR`/`.FILL`/`.BROADCAST` encodings diverge under mixed-PC warp states
  that cannot be produced with plain `BRA`/`BSSY` reconvergence (e.g. `BREAK`-peeled lanes).
