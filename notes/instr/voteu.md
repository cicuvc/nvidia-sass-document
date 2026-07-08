# VOTEU — Uniform warp vote / ballot

**Opcode mnemonic:** `VOTEU` = `0b100010000110` = **0x886** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency)

The uniform-datapath sibling of `VOTE` (see `vote.md`). Same warp reduction of a per-lane
source predicate `Pp`, but the results land in **uniform** storage: the ballot mask in a uniform
register `URd` and the vote boolean in a uniform predicate `UPu`. Emitted when the ballot/vote
result is warp-uniform and consumed by the uniform datapath — e.g. `__activemask()`.

## Semantics
Reduces `Pp` across active lanes per `voteop`, identical modes to `VOTE`:
| `voteop`[73:72] | SASS | reduction of `UPu` |
|-----------------|------|--------------------|
| `ALL`=0 | `VOTEU.ALL` | AND of lanes' `Pp` |
| `ANY`=1 | `VOTEU.ANY` | OR of lanes' `Pp` |
| `EQ`=2 | `VOTEU.EQ` | all lanes' `Pp` equal |
| 3 | INVALID3 | illegal (`ILLEGAL_INSTR_ENCODING_ERROR`) |

`URd` = 32-bit ballot mask (lane bits). `__activemask()` lowers to `VOTEU.ANY URd, UPT, PT`
(source `Pp`=PT so every active lane votes true → the active-lane mask), discarding the uniform
predicate (`UPu`=UPT). Membermask is dropped (as with VOTE). `Pp` may be negated.

## Variant overview
Single CLASS `voteu_` / opcode 0x886. Behaviour parameterized by `voteop`.

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x886 | 13-bit (VOTE 0x806 + bit7) |
| [14:12] / [15] | `Pg` / `Pg_not` | Pg guard | guard predicate (7=PT hidden) |
| [21:16] | `URd` | UniformRegister | ballot mask dest (default URZ, omitted in text) |
| [73:72] | `num` | `VoteOp` | 0=ALL, 1=ANY, 2=EQ, 3=INVALID3 |
| [83:81] | `Pu` | UniformPredicate `UPu` | vote-result dest predicate |
| [89:87] | `Pnz` | Pp | source (per-lane) predicate voted on |
| [90] | `input_reg_sz_32_dist` | Pp@not | negate bit for `Pp` |
| [124:122]∥[109:105] | `opex` | TABLES_opex_1(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | **pinned 0x7** | fixed-latency, no variable scoreboard |
| [103:102] | `pm_pred` | perfmon predicate | |

## Cross-comparison vs VOTE
| | **VOTE** (0x806) | **VOTEU** (0x886) |
|--|------------------|-------------------|
| pipe | int_pipe | udp_pipe (uniform) |
| ballot dest | GPR `Rd` [23:16] (8-bit) | uniform reg `URd` [21:16] (6-bit) |
| vote-bool dest | predicate `Pu` | uniform predicate `UPu` |
| source `Pp` | per-lane predicate | per-lane predicate (same) |
| opcode delta | — | +bit7 |

Field positions for `voteop`/`Pu`/`Pp`/`Pp_not` are identical to VOTE; only the destination
register field (`Rd`→`URd`, 8→6 bits) and predicate class (`Pu`→`UPu`) differ.

## Latency (from sm_90_latencies.txt)
`udp_pipe`, `OP_VOTEU = {VOTEU, VOTEUudp_pipe}`, fixed-latency `COUPLED_MATH`. Its uniform
predicate `UPu` is a `TABLE_TRUE/TABLE_OUTPUT(UPRED)` producer at **1** cycle (same row as
VOTE's UPu). The uniform-register `URd` is grouped in the `ULDC_VOTEU` connector set for
`TABLE_*(UGPR)` latency (URd-producer rows).

## Verified encodings
| Lo64 | Hi64 | Disassembly | source |
|------|------|-------------|--------|
| `0x0000000000047886` | `0x000fe400038e0100` | `VOTEU.ANY UR4, UPT, PT` | **real** (`__activemask()`) |
| `0x00000000003f7886` | `0x0000000000000100` | `VOTEU.ANY UP0, P0` | synthetic (round-trip) |
| `0x00000000003f7886` | `0x0000000000000000` | `VOTEU.ALL UP0, P0` | synthetic |
| `0x00000000003f7886` | `0x0000000000000200` | `VOTEU.EQ UP0, P0` | synthetic |
| `0x0000000000057886` | `0x00000000048e0100` | `VOTEU.ANY UR5, UPT, !P1` | synthetic |

Text drops `URd` when it is URZ. Decoder: `tools/decode_voteu.py` (real vector + round-trips
pass). Test: `tests/voteu_test.cu`.

### PTX→SASS mapping
- `__activemask()` → `VOTEU.ANY URd, UPT, PT`.
- Regular `__any/__all/__uni/__ballot_sync` with per-lane (non-uniform) result → plain `VOTE`;
  ptxas only chooses `VOTEU` when the result is uniform and used on the uniform datapath.

## Open questions
- Which other source patterns beyond `__activemask()` reliably steer ptxas to `VOTEU` — the
  ALL/EQ modes and a used `UPu` were not observed empirically (only constructed here).
