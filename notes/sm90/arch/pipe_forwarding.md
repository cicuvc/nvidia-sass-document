# Pipe-forwarding latency: udp_pipe → int_pipe (SM120, GB202 / RTX 5090)

**Full survey of every pipe-pipe edge (excluding fma64): `pipe_forward_survey.md`.**
This note is the per-edge method/verification detail behind the survey.

**Question:** a `udp_pipe` producer writes a uniform register and an
`int_pipe` consumer reads it (`MOV R,UR`, `IADD3 …,UR`).  The sm120 UGPR
`TABLE_TRUE` says `L_table = 12` cycles (`UDP_subset → MOV_OP/MATH_OPS`).
How much stall is *actually* required on silicon?

**Answer (measured):** `minG = 3` cycles of stall for `UIADD3 → MOV` and
`UIADD3 → IADD3.RUR` (real issue gap ≈ 3.4 cyc).  The spec's `L_table=12`
is ~4× conservative — the uniform datapath forwards to the int pipe's UR
operand collector, but the transfer is **not free**: a read issued within
~2 cycles of the producer reads stale (poison) data.  The hazard `L_table`
warns about genuinely exists at tiny gaps; the tabulated value is just a
loose upper bound (overlap `L−minG = 9`).

Companion: `tests/asm_construct/test_udp_int_forward.py` reproduces the
calibration.  This note resolves the *udp forwarding undetermined* open
question in `usched_latency.md`.

## Method — value-based stale/fresh boundary sweep

Per instance in one kernel (mirrors the `ISETP;P2R;STG.E` poison technique
of `usched_latency.md`):

```
LDCU UR10, #param(poison)          ; wr=SB0, UR10 = poison (0xAAAAAAAA)
UIADD3 UR10, UPT, UPT, UR11, UR12, URZ ;[7:7:{0}:1:1]   req={0} settles poison, stall=1
< S-1 NOPs, stall=1 each >          ; total stall S between producer and consumer
MOV R20, UR10                       ; int_pipe reads UR10
< 8× NOP pad > STG R20              ; capture (store-data confound guard)
```

- The consumer is protected **only** by the gap S.  At small S it reads the
  poison (stale); once the producer's write has landed it reads TRUE
  (`0x12345678`).  `minG` = first stall with a fresh read that stays fresh.
- Each kernel carries instances at every `S ∈ {0, 1..16, 30}` (0 =
  poison-only control, 30 = huge-gap control); 3 launches per config.

## Results (deterministic across ≥3 launches)

| producer (udp_pipe) | consumer (int_pipe) | spec L_table | minG stall | real gap | overlap L−minG |
|---|---|---|--:|--:|--:|
| `UIADD3` (UDP_subset) | `MOV R,UR` | 12 | **3** | ~3.4 cyc | 9 |
| `UIADD3` (UDP_subset) | `IADD3 …,UR` (RUR) | 12 | **3** | ~3.4 cyc | 9 |
| `UIADD3` → `UIADD3` (same-pipe) | | 4 | **2** | ~2.4 cyc | 2 |
| `UMOV` (UMOV_ULEPC) | `MOV R,UR` | 5 | **1** | ~1.4 cyc | 4 |

Sweep patterns (stalls 1..16): `UIADD3→int`: `SSFFFFFFFFFFFFFF`
(`S` at stall 1–2, `F` from 3); same-pipe: `SFFFFFFFFFFFFFFF` (`F` from 2);
`UMOV→MOV`: `FFFFFFFFFFFFFFFF` (`F` from 1).  All deterministic.

### Interpretation

- **The udp datapath forwards to the int pipe.**  `L−minG = 9` cycles of the
  tabulated 12 are "free" — the value is usable ~3 cycles after the producer
  issues, not 12.
- **The transfer is producer-dependent, not just pipe-pipe dependent.**
  `UIADD3` (uniform ALU) `minG=3`; `UMOV` (uniform copy) `minG=1`; the slow
  producers are far worse: `R2UR` (cross-lane broadcast/reduce) needs ~40
  cycles of settle (the 8× `UMOV` pads in `test_r2ur.py`), and `LDCU`
  (const-bank load) is scoreboard-governed, not stall-governed.
- **The practical rule for the user's premise is confirmed but small:**
  a udp→int fixed-latency transfer *does* hazard at stall < 2–3, so leave
  ≥3 cycles (or one filler instruction); ptxas's conservative stalls are
  justified, just not at the spec's magnitude.

## GPR-domain: int_pipe / fmalighter_pipe (same method)

Same stale/fresh boundary sweep in the GPR domain (`test_int_fma_forward.py`),
producer writes R10, consumer reads it.  Producer/consumer ops: `IADD3`
(int_pipe), `FADD` (fmalighter_pipe); TRUE = 1.0f bits, poison = 2.0f bits
(both normal fp32 so the FADD pass-through preserves them exactly).

| pair | spec L (TABLE_TRUE GPR) | minG stall | real gap | overlap L−minG |
|---|---|--:|--:|--:|
| int→int (`IADD3`→`IADD3`, FXU→FXU) | 6 | **2** | ~2.4 cyc | 4 |
| fmal→fmal (`FADD`→`FADD`, FMAI→FMAI) | 4 | **2** | ~2.4 cyc | 2 |
| int→fmal (`IADD3`→`FADD`) | 6 | **3** | ~3.4 cyc | 3 |
| fmal→int (`FADD`→`IADD3`) | 5 | **3** | ~3.4 cyc | 2 |

All four are deterministic and hazards are real at stall 1 (reads poison).
Verdicts:
- **int→int** needs only `minG=2` on sm120 (the spec's 6 is ~3× conservative;
  sm90 cuBLAS's observed `minG=4` in `usched_latency.md` is a *compiler* floor,
  not a hardware one).
- **fmal→fmal** `minG=2` vs spec 4 — the fmalighter pipe also forwards here;
  the sm90 "no bypass" conclusion for fp pipes does not hold at this granularity
  on sm120 (the value is usable in ~2 cycles; the tabulated 4 is what the
  scoreboard/issue model still pads to).
- **Cross-pipe** int↔fmal needs `minG=3` — the extra cycle is the cross-pipe
  operand-collect (matching the udp→int `minG=3`).
- Forwarding taxonomy so far on sm120: every fixed-latency datapath (int,
  fmalighter, udp) delivers its value to any consumer within ~2–3 cycles of
  issue; the spec `TABLE_TRUE` values are conservative upper bounds used by
  ptxas, and the real hazard only exists below ~2 cycles.

## cbu_pipe: int→cbu via NANOSLEEP (same method, timing-observed)

The cbu consumer is `NANOSLEEP R10` (sleeps for its register operand).
poison = 100000 → ~89k cycles of sleep; the int producer `IADD3 R10,RZ,RZ,RZ`
writes 0 → ~85 cycles.  A CS2R delta around the NANOSLEEP is the detector.
One kernel **per** stall value — several NANOSLEEPs in one kernel corrupt the
CS2R clock reads (long sleeps leave garbage clock values, later instances
store zeros), so `test_int_cbu_forward.py` launches once per S.

| pair | spec L (TABLE_TRUE GPR) | minG stall | real gap | overlap L−minG |
|---|---|--:|--:|--:|
| int→cbu (`IADD3`→`NANOSLEEP`, FXU→BRU) | 6 | **1** | ~1.4 cyc | 5 |

`S=0` (poison-only) reads stale; every `S≥1` reads fresh.  **int→cbu
forwards at the minimum schedulable gap** — the cbu pipe reads its register
operand *late* (store-like), so the int write has even more time to land than
for an int→int consumer (`minG=2`).  The spec's 6 is ~6× conservative.
(Hazard note: the delay isn't absent, just absorbed by the consumer's late
operand-collect — a *different* cbu op that reads its operand at issue, e.g.
a register-indirect branch, would show the true issue-time latency.)

## Predicate path: int ISETP P0 → cbu @P0 BRA (the exception)

The `TABLE_TRUE(PRED)` path is the one place the spec is **essentially
exact** — predicates do NOT forward like GPRs (`test_int_cbu_pred_forward.py`).

Poison P0=false (`ISETP.F`, fixed pad), producer `ISETP.EQ P0,RZ,RZ` (P0=true),
consumer `@P0 BRA` falls through to a stale marker or branches to a true
marker.  Two filler structures:

| fillers | sweep pattern | reliable minG | overlap L−minG |
|---|---|--:|--:|
| fine (many stall-1 NOPs) | `S S F S S S S F F…` | **7** | 6 |
| coarse (few big-stall NOPs) | `S S F S S S S S S S S S F F…` | **12–13** | 0–1 |

- **coarse mode lands at L=13 = the spec** — with few instructions between
  the ISETP and the BRA, the predicate writeback genuinely takes ~13 cycles
  (this is why `test_break.py`'s ISETP→`@P0 BRA` needs stall=13).
- **fine mode opens a deterministic but fragile bypass**: at exactly `S=3`
  (2 intervening stall-1 NOPs) the BRA reads the fresh predicate, yet `S=4..6`
  read stale again — an issue-alignment window, not a reliable forwarding
  path.  The reliable tail is `S≥7`.
- **Predicates ≠ GPRs**: every GPR datapath (int/fmal/udp/cbu-late-read)
  forwards in 2–3 cycles; the predicate file has no such bypass — schedule
  `ISETP → @P0 BRA` with stall ≥13 (coarse) to be safe.

## Updated sm120 forwarding taxonomy

| producer → consumer (register class) | spec L | reliable minG |
|---|---|--:|
| udp → int (`UIADD3`→`MOV`/`IADD3.RUR`, UR) | 12 | 3 |
| udp → fmalighter (`UIADD3`→`FFMA.RRU` reads UR, UR) | 12 | 3 |
| int → int (`IADD3`→`IADD3`, GPR) | 6 | 2 |
| fmal → fmal (`FADD`→`FADD`, GPR) | 4 | 2 |
| int ↔ fmal (GPR) | 5–6 | 3 |
| int → cbu late-read (`IADD3`→`NANOSLEEP`, GPR) | 6 | 1 |
| int → mio address (`MOV.64`→`LDG` addr/AGU, GPR) | 6 | 1 |
| fmal → mio address (`FFMA`×2→`LDG` addr/AGU, GPR) | 6 | 1 |
| fp16 → int / fmal (`HADD2`→`IADD3`/`FADD`, GPR) | 5 | 2 |
| udp → fe (`UMOV`→`DEPBAR.LE` UR count, UR) | 10 | 2 |
| **mio → int / fmal (`MUFU.RCP`→`IADD3`/`FADD`, GPR)** | **2** | **8** |
| **int → cbu predicate (`ISETP P0`→`@P0 BRA`)** | **13** | **7 fine / 12–13 coarse** |

`udp→fmalighter` (`test_udp_fma_forward.py`) is identical to `udp→int`
(`minG=3`): the uniform datapath forwards to **any** consumer reading the UR
(int `MOV`/`IADD3.RUR` or fmalighter `FFMA.RRU`) in ~3 cycles.  `int→mio` /
`fmal→mio` (`test_int_mio_forward.py`, `test_fmal_mio_forward.py`, LDG whose
address pair a fixed-latency op produced) are `minG=1` — the AGU address read
sees the write at the minimum gap (late-ish operand-collect, like the cbu
`NANOSLEEP` case).  `fp16→int/fmal` (`test_fp16_int_fma_forward.py`, packed
`HADD2` producer) is `minG=2`, same as int→int / fmal→fmal.  `udp→fe`
(`test_udp_fe_forward.py`) uses a `DEPBAR.LE SB0, UR3` count read (armed with
one cold LDG so counter=1): `UR3=0` waits, `UR3=1` proceeds early — the
DEPBAR sees the UDP `UMOV` write at `minG=2` (spec 10).  **The exception
is the reverse: `mio→int/fmal`
(`test_mio_int_fma_forward.py`, MUFU producer, consumer reads without a
scoreboard req) needs `minG=8`** — the mio/SFU result is NOT fast-forwarded
to the fixed-latency pipes (the spec's catch-all `MIO_CBU_OPS→ALL_OPS=2` is
too optimistic), and in real code the scoreboard (not a stall gap) is the
correct mechanism for variable-latency mio results.  GPR datapaths forward in
1–3 cycles (specs 2–6× conservative for the fast directions); the predicate
path is slow like mio (spec 13 exact, no fast bypass).

## Measurement apparatus — the three gotchas that shaped the method

1. **`stall=0` is DRAIN, not "zero gap".**  A dependent chain with `stall=0`
   runs at **~34 cyc/op** (CS2R-timed, N=256) — the DRAIN/end-group encoding
   forces a full pipeline drain and yield.  The producer therefore always
   carries `stall=1` and all extra gap comes from NOP fillers.  (Same
   `usched_info` story as `usched_latency.md` §stall model, but the DRAIN
   magnitude is new.)
2. **The single-warp issue floor is ~2.5–3 cyc/op.**  Independent and fully
   dependent chains (`IADD3`/`UIADD3`/`FADD`/`FFMA`/`HADD2`) all run at
   ~2.5–3.0 cyc/op at `stall=1` — so `minG` is only resolvable down to
   ~2.4 cyc (stall=2), and the *true* forwarding latency is bounded above by
   the floor, not pinned exactly.
3. **Scoreboard writeback ≠ bypass delivery.**  The same dependent ops,
   when each one sets `wr=SBn` and the next `req`s it, run at **~5.4–5.8
   cyc/op** (matching the `test_mufu_latency.py` ALU calibration).  The
   stall-gap measurement (~3 cyc) and the scoreboard measurement (~5.4 cyc)
   disagree because the stall-based issue reads the value through the pipe's
   **operand-forwarding/bypass network** (correct early), while the
   scoreboard waits for the **register-file writeback** to commit.  On this
   view, `minG≈3` is the bypass-delivery latency; `L_table≈12` is nearer
   the worst-case commit path ptxas models.  So on sm120 the *value* is
   usable at ~3 cyc, but ptxas still pads to 4–6 because not every consumer
   path (memory pipes, scoreboard-tracked ops) can use the bypass.

## Cross-checks and controls (all pass)

- **poison-only** (no producer, dummy+req read): reads poison → capture path
  valid.
- **huge-gap** (stall 30): always fresh.
- **variable-latency producers without a scoreboard wait** read stale or
  garbage at small gaps (`S2R`/`MUFU`/`LDCU`), i.e. the harness detects
  non-freshness — the fresh-at-floor results for fixed producers are real.
- **Same-pipe/other fixed pipes** (`int→int`, `fp32→fp32`, `fp16→fp16`)
  also deliver correct values at the issue floor at `stall=1` — forwarding
  is pipe-wide for the fixed-latency datapaths, consistent with the int
  bypass seen in sm90 cuBLAS, and extending it to udp.

## Yield bit (usched bit4) — identical gap, wider transN hazard window

Bracket `yield` flips `usched` bit4: `yield=1 → usched=stall` (WnEG),
`yield=0 → usched=16+stall` (transN); `eff_stall = usched & 0xF` is identical
either way.  Two independent measurements:

- **Issue gap is identical.**  CS2R-timed dependent `UIADD3` chains run at the
  same rate for both encodings (stall=5 → 5.42 cyc/op both; stall=3 → 3.80
  both).  This confirms `usched_latency.md`'s "bit4 never moves a measured
  stall boundary" — for the *issue interval*.
- **The stale/fresh hazard pattern differs.**  Re-running the udp→int
  boundary sweep per (producer-yield, filler-yield):

  | P yield | F yield | minG stall |
  |--:|--:|--:|
  | 1 (WnEG) | 1 (WnEG) | **3** |
  | 0 (transN) | 0 (transN) | **6** |
  | 1 (WnEG) | 0 (transN) | 4–5 |
  | 0 (transN) | 1 (WnEG) | 3–4 |

  The all-transN form needs ~2× the stall for a reliably fresh read; mixed
  forms sit between.  The 3–6 region is **alignment-sensitive** (exact values
  shift ±1–2 with kernel layout — the committed test's controls change the
  mixed-form numbers run to run), but the extremes are stable across probe
  runs: all-WnEG `minG=3`, all-transN `minG=6`.

**Mechanism guess:** transN ("transition, no group-end") keeps the warp
issuing back-to-back; a WnEG ("wait, end-group") on the producer/fillers lets
the consumer's operand-collect land clear of the UR writeback commit.  On the
other side of the ledger, ptxas emits WnEG precisely for dependency stalls —
so the tight `minG=3` (WnEG) is the realistic rule for hand-written SASS.
(Verified at the scheduler level in `subcore_scheduler.md`: WnEG hands the
issue slot to another warp, transN hogs it — so WnEG fillers insert dead
cycles into a single-warp stream, giving the UDP writeback more commit time.)

**Practical rule:** for a udp→int dependency, use `yield=1` (WnEG) on the
producer and gap-fillers; `yield=0` (transN) buys nothing on gap and widens
the hazard window.

## LDCU-specific artifacts (why LDCU is not a clean stall probe)

- A `LDCU`-loaded UR's **first read returns the old value** (often 0), even
  long after the load; a dummy read settles the datapath
  (`test_ldcu.py` caveat).
- The `LDCU` writeback only **commits once a consumer `req`s its scoreboard**
  (`wr=SBn`); a req-less read can see 0x0.  This is why the sweep's poison
  uses `LDCU` + producer `req={0}` (scoreboard-settled, no WAW race) and why
  `LDCU` as the *measured producer* is excluded from the clean numbers.
- With the req missing, a `LDCU` producer shows non-monotonic stale/fresh
  (`0x0` at gap 0, stale at gap 6, fresh ≥ 8 in one run) — pure variable
  latency, not a stall-controlled forwarding edge.

## Reproduce

```
python3 tests/asm_construct/test_udp_int_forward.py
```

prints the main sweep (4 producer/consumer pairs), the poison-only / huge-gap
controls, and the yield-bit probe (4 yield configurations of UIADD3→MOV).
Probe scripts used during development (not committed): `/tmp/opencode/probe_*.py`.

## Open questions

- **Yield-bit mechanism**: why does all-transN widen the stale window while
  leaving the issue gap identical?  The WnEG group-end may flush the operand
  collector / align the read clear of the UR writeback commit; not verified
  at the microarchitectural level.

- **Exact bypass geometry**: is `minG≈3` the UDP ALU→UR-file write port,
  a UR-file→int-operand-collect bypass, or both?  A UR read via a *memory*
  consumer (LDG address) would isolate the AGU path.
- **Boundary alignment sensitivity**: at `S ∈ [2,5]` a fillergranularity
  change (one big-stall NOP vs several stall-1 NOPs) can flip an instance
  fresh↔stale; the boundary has an alignment-zone of ±2 cycles, not a single
  clean edge.  Stable-fresh requires producer stall ≥6 *or* ≥2 intervening
  instructions.  The 8-identical-instance runs show a deterministic
  per-instance pattern (`SFSSSSSS`) whose period is not yet explained.
- **Reverse direction** (int→udp): the only GPR→UR mover `R2UR` is a
  cross-lane op with ~40-cyc settle — there is no fast int→udp path to
  measure with this harness.
- **Other cross-pipe pairs** (udp→fma64, udp→fp16, int→fma64) would extend
  the table; the existing `usched_latency.md` sm90 corpus suggests fma64
  carries no bypass (overlap 0).
