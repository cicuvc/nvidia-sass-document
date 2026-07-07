# VOTE — Warp-wide vote / ballot

**Opcode mnemonic:** `VOTE` = `0b100000000110` = **0x806** | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70

SASS lowering of PTX `vote.sync` (`__ballot_sync` / `__any_sync` / `__all_sync` / `__uni_sync`).
Reduces a per-lane source predicate `Pp` across the warp's active lanes and produces **both** a
32-bit ballot mask in `Rd` (bit `i` = lane `i`'s `Pp`) **and** a boolean vote result in
predicate `Pu`. Either destination may be a sink (`Rd`=RZ / `Pu`=PT) when unused.

## Semantics (verified PTX→SASS)
| intrinsic / PTX | SASS | what is used |
|-----------------|------|--------------|
| `__ballot_sync` / `vote.ballot` | `VOTE.ANY Rd, PT, Pp` | `Rd` = per-lane mask (Pu=PT sink) |
| `__any_sync` / `vote.any` | `VOTE.ANY Pu, Pp` | `Pu` = OR of lanes (Rd=RZ sink) |
| `__all_sync` / `vote.all` | `VOTE.ALL Pu, Pp` | `Pu` = AND of lanes |
| `__uni_sync` / `vote.uni` | `VOTE.EQ Pu, Pp` | `Pu` = all lanes' `Pp` equal |

The three modes select the reduction of `Pu`; `Rd` is always the ballot mask regardless of
mode. `__ballot_sync` is just `VOTE.ANY` keeping `Rd` and discarding the predicate.

**Membermask is dropped** (as with `MATCH`): PTX `vote.sync` takes a `membermask`, but SASS
`VOTE` has no mask operand — it votes over the hardware active-lane mask. `Pp` may be negated
(`!Pp`) — the intrinsic's inverted-condition case folds the NOT into the source predicate.

## Variant overview
Single CLASS `vote_` / opcode 0x806. Behaviour parameterized by `voteop` [73:72].

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x806 | 13-bit |
| [14:12] / [15] | `Pg` / `Pg_not` | Pg guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | ballot mask dest (default RZ, omitted in text) |
| [73:72] | `num` | `VoteOp` | **0=ALL, 1=ANY, 2=EQ**, 3=INVALID3 (illegal) |
| [83:81] | `Pu` | Predicate | vote-result dest predicate |
| [89:87] | `Pnz` | Pp | source predicate voted on |
| [90] | `input_reg_sz_32_dist` | Pp@not | negate bit for source `Pp` |
| [124:122]∥[109:105] | `opex` | TABLES_opex_1(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | **pinned 0x7** | fixed-latency: no variable scoreboard |
| [103:102] | `pm_pred` | perfmon predicate | |

**`VoteOp`**: `ALL=0, ANY=1, EQ=2, INVALID3=3`. `voteop==INVALID3` → `ILLEGAL_INSTR_ENCODING_ERROR`.
Note the odd field names: `Pnz`[89:87] is the *input* predicate and `input_reg_sz_32_dist`[90]
is its negate bit (reused generic field slots).

## Cross-comparison
| | **VOTE** | **VOTEU** (idx 154) | **MATCH** |
|--|----------|---------------------|-----------|
| pipe | int_pipe (COUPLED_MATH) | udp_pipe (uniform) | mio_pipe (decoupled) |
| dest | GPR mask + predicate | uniform reg + uniform pred | GPR mask (+pred for ALL) |
| input | per-lane predicate | per-lane predicate | per-lane register value |
| latency | fixed | fixed | scoreboard (decoupled) |

`VOTEU` is the uniform-datapath sibling that writes a uniform register/predicate (used when the
ballot result is warp-uniform); documented separately.

## Latency (from sm_90_latencies.txt)
`int_pipe` member, fixed-latency `COUPLED_MATH` (scoreboards pinned to 0x7). `OP_VOTE =
{VOTE, VOTEint_pipe}` is explicitly carved out of `MATH_PRED_OPS` (`MATH_PRED_OPS = MATH_OPS -
OP_VOTE`) because it reads predicates warp-wide; its predicate connectors are
`{Pr,Pq,Pp,Pa,Pb,Pc,Ps,Plg,Pnz}`.

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000000077806` | `0x000fca00040e0100` | `VOTE.ANY R7, PT, !P0` (`__ballot_sync(!p)`) |
| `0x0000000000077806` | `0x000fca00000e0100` | `VOTE.ANY R7, PT, P0` (`__ballot_sync(p)`) |
| `0x0000000000ff7806` | `0x000fc80000000100` | `VOTE.ANY P0, P0` (`__any_sync`) |
| `0x0000000000ff7806` | `0x000fc80000000000` | `VOTE.ALL P0, P0` (`__all_sync`) |
| `0x0000000000ff7806` | `0x000fc80000000200` | `VOTE.EQ P0, P0` (`__uni_sync`) |

Text form drops `Rd` when it is RZ (`VOTE.EQ P0, P0` = `Pu, Pp`); shows it otherwise
(`VOTE.ANY R7, PT, P0` = `Rd, Pu, Pp`). Decoder: `tools/decode_vote.py` (all 5 vectors pass).
Test: `tests/vote_test.cu`.

### PTX→SASS mapping
- `__ballot_sync(mask, p)` → `VOTE.ANY Rd, PT, p` (mask dropped)
- `__any_sync(mask, p)` → `VOTE.ANY Pu, p`
- `__all_sync(mask, p)` → `VOTE.ALL Pu, p`
- `__uni_sync(mask, p)` → `VOTE.EQ Pu, p`
- inverted condition → source predicate negated (`!Pp`).

## Open questions
- Whether ptxas ever emits VOTE with both `Rd` and a real `Pu` simultaneously (e.g. a fused
  ballot + any); all observed cases use exactly one destination.
