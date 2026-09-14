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
  one group. When every copy in that group completes, it becomes eligible for
  retirement from the ordered group tracker.
- `cp.async.wait_group N` → **DEPBAR.LE SBk, N** — wait until the group counter
  `≤ N`. `cp.async.wait_all` → `DEPBAR.LE SBk, 0x0`.

**The counter counts GROUPS, not individual copies** — verified with asymmetric
groups of 4 / 1 / 2 copies: `wait_group 2/1/0` emitted `DEPBAR.LE SB0, 0x2/0x1/0x0`
(one `LDGDEPBAR` per commit, all bound to the same `SB0`), i.e. `cnt` equals the
`wait_group` argument regardless of ops-per-group. So one scoreboard holds the
warp's whole cp.async group count; `cnt=1` keeps one group in flight
(double-buffering), `cnt=0` drains all.

### Partial waits retire committed groups in order (SM120 silicon)

`probe_ldgsts_group_order.py` commits three one-copy groups and makes exactly
one group slow by scattering its 32 lanes over 32 independent 128-byte lines;
the other groups are coalesced and explicitly preheated.

| wait | slow group(s) that extend the wait | groups allowed to remain |
|---|---|---|
| `LE SB0,2` | position 0 only | 1 and 2 |
| `LE SB0,1` | position 0 or 1 | 2 |
| `LE SB0,0` | any position | none |

For `wait_group 2`, all-fast and slow-at-1/2 take about 374--379 clocks,
while slow-at-0 takes about 417.  For `wait_group 1`, slow-at-0/1 takes about
422--429 while slow-at-2 remains about 374.  A threshold of 3 returns in 10
clocks and observes stale shared data, providing the no-wait control.  Every
group that the partial wait promises to drain contains the correct data.

Thus this is not merely an unordered count of completed groups.  The hidden
tracker preserves commit order: `wait_group N` drains the oldest groups and
permits only the N youngest groups to remain, even if a younger group reaches
physical completion first.  A FIFO of group-closure records is a sufficient
implementation; the experiment does not determine its physical depth.

### Effective committed-group capacity: 54 (SM120, one warp)

`probe_ldgsts_group_depth.py` compares identical copy traffic with one commit
at the end against one `LDGDEPBAR` after every copy.  A stronger variant keeps
group 0 incomplete with 8--24 scattered copies, then rapidly appends
coalesced one-copy groups.  Ordered retirement prevents any younger group
record from escaping around the long head.

With 54 committed groups, issue remains on the exact linear marker-cost line.
Attempting group 55 stalls until group 0 closes: for 16 head copies, issue
jumps from 560 clocks at 54 groups to about 963 at 55; for 8/12/20/24 head
copies the knee remains exactly 54->55.  Moving the knee neither with copy
count nor with head latency rules out a shared copy-token limit.

The observed capacity is therefore **54 simultaneously committed, incomplete
cp.async groups per warp** on GB202.  `probe_ldgsts_group_sharing.py` makes
warp 0+4 share a subcore or places warp 0+1 on different subcores.  With 28
groups each, a partial wait confirms both head groups are still incomplete,
yet all 56 records coexist without a knee.  With a 12-copy long head, both
warps independently stall their 55th commit until their own group 0 closes;
placement does not change the boundary.  This excludes one 54-credit pool per
subcore or per SM.

This is an effective credit count; it does not establish whether the storage
is a literal 54-entry FIFO or includes an active head/commit slot under a
different physical accounting scheme.

#### Scoreboard-index partitioning

The same long-head construction routed alternately to SB0 and SB1 continues
linearly through 108 total groups, exactly 54 per scoreboard.  Group 109 is
assigned to SB0 and stalls until SB0's long head closes.  In contrast, 55
groups all assigned to SB0 already stall.  Thus SB0 and SB1 have independently
accounted 54-credit domains; there is no single 54-credit total shared by all
scoreboard indices in a warp.

A three-scoreboard run did not expose a useful 162->163 boundary because the
long heads completed before all three domains could be filled at the available
issue rate.  The present evidence therefore does not prove six fully separate
54-entry physical arrays, nor exclude an additional warp-wide ceiling at 108
or above.

#### Divergence / pipeline-sequence entanglement

`probe_ldgsts_divergent_commit.py` shows that the counter is updated per
dynamic converged execution group, not per static `LDGDEPBAR` PC.  Two halves
of a BSSY region that funnel through the same LDGSTS and LDGDEPBAR instructions
before their matching BSYNC leave two incomplete groups (`LE 1` waits, `LE 2`
passes).  Moving the same instructions after BSYNC leaves only one.  Repeating
the construction gives exact 2/4/6 versus 1/2/3 threshold sequences.

A four-way fan-out through one common commit PC creates four groups.  An
eight-way test held retirement behind an extra long FIFO head and observed a
pass boundary of nine: one head record plus eight divergent-subgroup records.
Those records also reproduce the 54->55 allocation knee, so this is physical
group-credit consumption rather than only a conservative per-thread software
sequence number.

This is the SASS-level manifestation of the converged-subset accounting
described in NVIDIA US12118382B2.  Structured divergence makes the result
deterministic in these probes, although the patent permits an increment from
1 through 32 when the runtime convergence partition is not fixed.

An ordering probe commits an older scattered group to SB0 and younger hot
groups to SB1.  Waiting only for SB1 is delayed by the older SB0 group (about
426 versus 348 clocks for all-hot).  This is compatible with a global commit
order above the per-SB accounting, but is not decisive: ordered service in the
LDGSTS/shared completion datapath can create the same timing without a global
retirement FIFO.

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

## Resolved: silicon-verified LE partial-drain semantics (SM120)

`tests/asm_construct/test_depbar.py` verifies the counted wait WITHOUT
LDGSTS/LDGDEPBAR, by bookkeeping a scoreboard with ordinary `wr=SBn` ops:
2 MUFU (~18 cyc) + 1 cold LDG (~500-1000 cyc), all `wr=SB0` -> counter 3.

| barrier | wait (cyc) | LDG result |
|---------|-----------|------------|
| `DEPBAR.LE SB0, 3` | ~10 | stale garbage (load in flight) |
| `DEPBAR.LE SB0, 1` | ~10 | stale garbage (load STILL in flight) |
| `DEPBAR.LE SB0, 0` | ~500-1000 | valid |
| `req={0}` consumer | ~500-1000 | valid |

Conclusive: **`DEPBAR.LE SBn, cnt` proceeds as soon as SBn's counter is
`<= cnt`** — with cnt>=1 it lets dependent code run while ops are still in
flight (their registers are stale), while `cnt=0` is the same force-to-zero as
a `req` wait.  The S-list `{S}` forces those scoreboards to 0 even when the LE
part is already satisfied (`DEPBAR.LE SB0, 63, {1}` waited for a SB1 load);
`DEPBAR {S}` is a pure force-0 drain; `DEPBAR.ALL` drains all.  `depbar_ur_`
(dynamic count from a uniform reg, opcode 0x1d1a, URb at [39:32], S-list at
[53:48]) verified with UR=0 (drains) vs UR=1 (proceeds early).

Hand-assembler gotchas:
- A uniform-register count needs the LDCU loaded with a sufficient stall
  (`LDCU UR3, #param(cnt);[3:7:{}:2:0]` — stall=2, yield=0) AND the DEPBAR
  must `req` that scoreboard (`DEPBAR.LE SB0, UR3;[7:7:{3}:5:1]`), else it
  reads a stale 0.
- Encoding: le[47], sbidx[46:44], cnt[43:38], S-list[37:32] (reg form) /
  [53:48] (UR form).  The assembler rejects `sbidx ∈ S` (matches the spec
  condition, which required adding `&`/`<<` to the condition evaluator).

## DEPBAR.LE immediate sweep: threshold == number of in-flight LDGs

`/tmp/scan_depbar.py`: burst of `m` MUFU (~18 cyc) + `n` cold LDG
(~330-370 cyc) all `wr=SB0`, CS2R t0 after the burst, `DEPBAR.LE SB0, imm`,
CS2R t1.  Measured wait (cyc, min of 3 runs):

| m | n | imm < n | imm = n | imm > n |
|---|----|---------|---------|---------|
| 2 | 1 | 0 -> 345 | 1 -> 10 | 10 |
| 3 | 2 | 0 -> 332, 1 -> 330 | 2 -> 10 | 10 |
| 4 | 3 | 0 -> 330, 1 -> 328, 2 -> 369 | 3 -> 10 | 10 |
| 2 | 3 | 0 -> 328, 1 -> 334, 2 -> 372 | 3 -> 10 | 10 |

Step function: **wait is ~10 cyc (DEPBAR+CS2R overhead) whenever `imm >= n`
and ~330-370 cyc whenever `imm < n`.**  The MUFU contributions have already
drained by the time DEPBAR observes the counter (each ~18 cyc, issued before
t0), so the counter at the DEPBAR is exactly `n` (the LDGs still in flight).
`DEPBAR.LE SB0, n` therefore proceeds while all n loads are in flight — the
pipelining sweet spot; `imm = n-1` waits one load-batch, `imm = 0` waits all.
The co-issued LDGs drain as a batch, so `imm` in [0, n-1] all land on ~one
batch latency rather than `(n-imm)` distinct steps.
