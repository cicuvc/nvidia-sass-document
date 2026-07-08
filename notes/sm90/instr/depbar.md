# DEPBAR — dependency barrier (counted scoreboard wait)

**Opcode mnemonic:** `DEPBAR`  |  **Pipe:** `fe_pipe`  |
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`  |  **opcode:** `0x91a`
(uniform-count form `0x1d1a`)

Explicit barrier that waits on the **outstanding-operation count** of a
scoreboard. Where the per-instruction `req_bit_set` wait-mask can only express
"wait until scoreboard == 0" (binary), `DEPBAR.LE SBn, cnt` waits until SBn's
pending count is **≤ cnt** — a *partial* drain. This is what software-pipelined
async pipelines (`cp.async` / LDGSTS multi-buffering, wgmma groups) need to keep
N stages in flight while waiting for the older ones.

## Semantics
`DEPBAR.LE SBn, m {, S}` blocks issue until:
- scoreboard `SBn`'s outstanding count `≤ m`, **and**
- every scoreboard in the bitset `S` (scoreboard_list) is drained to 0.
CONDITION: `SBn` may not itself appear in `S`.

The non-LE form `DEPBAR S` just drains the listed scoreboards to 0 (a
multi-scoreboard barrier); `DEPBAR.ALL` drains all.

## Variant overview
| class | form | opcode | note |
|---|---|--:|---|
| `depbar__LE`   | `DEPBAR.LE SBn, cnt, {S}` | `0x91a` | counted wait (≤cnt) |
| `depbar__noLE` | `DEPBAR {S}` | `0x91a` | drain scoreboard set to 0 |
| `depbar_all_`  | `DEPBAR.ALL` (ALT) | `0x91a` | drain all |
| `depbar_ur_`   | `DEPBAR.LE SBn, URb, {S}` | `0x1d1a` | **dynamic** count from a uniform reg |
| — `LDGDEPBAR`  | (`mio_pipe`, `0x9af`) | — | `cp.async.commit_group` group marker |
| — `WARPGROUP.DEPBAR.LE GSB, cnt` | (`mio_pipe`, `0x9c5`) | — | wgmma group-scoreboard wait (`MODE_DEPBAR`) |

## Fields (register form `depbar__LE`)
| field | bits | meaning |
|---|---|---|
| le | [47] | LE mode (counted) vs set-drain |
| sbidx | [46:44] | scoreboard SB0–SB5 (6,7 = INVALID) |
| cnt | [43:38] | 6-bit threshold count (0–63) |
| scoreboard_list `S` | [37:32] | 6-bit bitset of scoreboards to drain to 0 |

Control word as usual: `req_bit_set`[121:116], `opex`[124:122]∥[109:105]
(`TABLES_opex_1` — so `batch_t=3` is illegal here), `pm_pred`[103:102];
`src_rel_sb`/`dst_wr_sb` are pinned to 7 (DEPBAR reads scoreboards, doesn't own
one).

## The cp.async / LDGSTS pipeline (verified, `tests/depbar_test.cu`)
```
LDGSTS.E [smem], [gmem]          wr_sb=7        # async copy; does NOT set a normal SB
LDGSTS.E [smem+..], [gmem+..]    wr_sb=7
LDGDEPBAR                        wr_sb=0        # commit_group -> counts a group on SB0
LDGSTS.E ...                     wr_sb=7        # next group
LDGSTS.E ...
LDGDEPBAR                        wr_sb=0        # commit_group #2
DEPBAR.LE SB0, 0x1   [le=1 sbidx=SB0 cnt=1]     # cp.async.wait_group 1  (keep ≤1 in flight)
LDS R0, [smem]                                  # safe to read the drained group
DEPBAR.LE SB0, 0x0   [le=1 sbidx=SB0 cnt=0]     # cp.async.wait_group 0 / wait_all
```
Mechanism (the 1:1 lowering):
- `cp.async` → **LDGSTS** — async copy; takes **no** ordinary write scoreboard
  (`wr_sb=7`). It feeds a hidden async-completion tracker.
- `cp.async.commit_group` → **LDGDEPBAR** — `wr_sb=k`: **increments the group
  counter on scoreboard `SBk` by 1**, binding the just-issued batch of LDGSTS as
  one group. When every copy in that group completes, `SBk` decrements by 1.
- `cp.async.wait_group N` → **DEPBAR.LE SBk, N** — wait until the group counter
  `≤ N`. `cp.async.wait_all` → `DEPBAR.LE SBk, 0x0`.

**The counter counts GROUPS, not individual copies** — verified with asymmetric
groups of 4 / 1 / 2 copies: `wait_group 2/1/0` emitted `DEPBAR.LE SB0, 0x2/0x1/0x0`
(one `LDGDEPBAR` per commit, all bound to the same `SB0`), i.e. `cnt` equals the
`wait_group` argument regardless of ops-per-group. So one scoreboard holds the
warp's whole cp.async group count; `cnt=1` keeps one group in flight
(double-buffering), `cnt=0` drains all.

## Latency relationship (`sm_90_latencies.txt`)
- `DEPBAR ∈ fe_pipe`; `DEPBAR_OP` is subtracted out of the math-vs-uniform
  overlap set (`MATH_OPS_WITHOUT_RPCMOV_DEPBAR`) and is a member of
  `CoupledDispOverlapWithMathOps`.
- `TABLE_TRUE(SCOREBOARD)` lists `DEPBAR`{sbidx}` as a **reader** of the
  scoreboard resource (it consumes, never produces). The wait itself is
  `ORDERED_ZERO` (runtime-variable), not a fixed cycle count.
- `WARPGROUP.DEPBAR` reads `GMMA_GROUP_SCOREBOARD` under `MODE_DEPBAR (mode==2)`
  (see `TABLE_TRUE(GMMA_GROUP_SCOREBOARD)` = 3).

## Cross-notes
- `../arch/control_codes.md`: the only non-zero `batch_t` ptxas ever emits
  (`BARRIER_EXEMPT=5`) appears **exclusively on DEPBAR** in cuBLAS/cuBLASLt —
  marking the drain exempt from the batch/issue barrier accounting.
- Contrasts with the `req_bit_set` mask (binary, per-instruction) documented in
  `../arch/control_codes.md`: DEPBAR is the *counted* superset used when partial
  draining is required.

## Open questions
- Exact width/semantics of the async-copy counter behind `SB0` (how many
  outstanding LDGSTS groups a scoreboard can track).
- `depbar_ur_` dynamic-count use: which PTX (`cp.async.wait_group` with a runtime
  operand?) emits the uniform-register count form `0x1d1a`.
