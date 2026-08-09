# SM subcore mapping (warp i → subcore i%4) and the yield-hint scheduler switch (SM120)

**Question:** does each SM partition its warps onto 4 subcores as `warp i →
subcore i%4`, and does the SASS "yield" hint (bracket `yield=1` → `usched`
bit4=0, `WnEG`) really make the subcore scheduler switch to another warp on
the next cycle?

**Answer (verified on sm_120 / GB202, RTX 5090):** yes to both.
`tests/asm_construct/test_subcore_yield.py` reproduces it. The i%4 pairs
`{0,4},{1,5},{2,6},{3,7}` interact on a shared subcore; every other pair
does not. On a shared subcore, a `WnEG` (yield=1) warp **yields its issue
slots** to a co-resident `transN` (yield=0) warp, doubling that warp's
finish time while the transN warp runs at ~solo speed.

## Method — per-warp yield asymmetry

Two active warps out of a 256-thread block (the rest `EXIT`), each on its own
branch with a **different yield bit** over `N` independent `NOP`s, and its own
`CS2R SR_CLOCKLO` start/end stored to `out[warp*16]`:

```
warp A (selected by ISETP.EQ warp==wA + @P0 BRA):  N× NOP [7:7:{}:1:1]  ; yield=1 WnEG
warp B (selected the same, different target):      N× NOP [7:7:{}:1:0]  ; yield=0 transN
```

If A,B share a subcore, the transN warp keeps issuing ("keep this warp", per
`usched_latency.md`) while the WnEG warp repeatedly signals "group end / may
switch" → the scheduler hands the slot to B.  A is starved: `A.delta ≈ 2×
B.delta`.  If they are on different subcores, each runs at its own rate with
no interaction.

## Results (5 reps, best-of, deterministic)

| warps | subcores (i%4) | A=WnEG | B=transN | asym A/B |
|---|---|--:|--:|--:|
| `{0,1}` | 0,1 diff | 1100 | 1042 | 1.06 (none) |
| **`{0,4}`** | **0,0 same** | 1415 | 732 | **1.93** |
| **`{1,5}`** | **1,1 same** | 1374 | 685 | **2.01** |
| **`{2,6}`** | **2,2 same** | 1415 | 732 | **1.93** |
| **`{3,7}`** | **3,3 same** | 1374 | 685 | **2.01** |
| `{0,5}` | 0,1 diff | 1100 | 1042 | 1.06 |
| `{0,7}` | 0,3 diff | 1100 | 1042 | 1.06 |
| `{0,3}` | 0,3 diff | 1100 | 1042 | 1.06 |

Controls on `{0,4}`:
- **flip** (A=transN, B=WnEG): asym `0.61` — the asymmetry reverses.
- **both WnEG**: asym `0.99`; **both transN**: asym `0.95` — symmetric.

Only the i%4 pairs interact, and the interaction is exactly the yield bit.
That is a clean verification of **both** claims.

## Interpretation

- **i%4 mapping.**  A CTA's warps are assigned to the SM's 4 subcore
  schedulers round-robin.  This is the same "SMSP" partition the
  `register_bandwidth.md` note already assumed (per-SMSP aggregate rates);
  here it is measured directly as a scheduling interaction, not inferred
  from bandwidth.
- **Yield = "switch next cycle".**  The bracket `yield` bit is the `usched`
  bit4 selector (see `control_codes.md`, `usched_latency.md`):
  * `yield=1` → `WnEG` (bit4=0): group-end / "the next instruction may go to
    another warp" — the scheduler is free to switch.  A co-resident ready
    warp takes the slot.
  * `yield=0` → `transN` (bit4=1): "independent successor, keep issuing this
    warp" — the warp hogs the slot.
  On a shared subcore this is a ~2× issue-slot bias toward the transN warp.
- **Solo-warp corollary** (same datapath, `probe_issue`): a single warp's
  `NOP` stream runs at 1.53 cyc/op (`transN`) vs 2.50 cyc/op (`WnEG`) —
  with nothing else to switch to, the WnEG "yield" simply wastes the slot.
  This is the mechanism behind the `pipe_forwarding.md` finding that
  all-`WnEG` gap fillers give a *tighter* stale/fresh boundary than
  all-`transN` fillers: WnEG fillers inject extra dead cycles into the
  single-warp stream, giving the UDP writeback more time to commit.
- **Why the dependent-chain throughput test fails to see the mapping.**  With
  dependent work the scheduler fills each warp's latency stall with the other
  warp **regardless of the yield bit** (opportunistic scoreboard-style
  switching), so `{0,4}` and `{0,1}` both complete in ~1× single-warp time.
  The mapping only becomes visible when both warps are *ready every cycle* and
  the yield bit arbitrates the single issue port.

## SASS recipes / gotchas used

- The `ISETP` feeding a guarded `@P0 BRA` needs **stall=13** (predicate
  writeback must settle before the BRA reads it) — same recipe as
  `tests/asm_construct/test_break.py`.
- Warp id = `SHR(SR_TID.X, 5)`; per-warp branch via `ISETP.EQ.AND P0, PT, R3,
  imm, PT` + `@P0 BRA #label(...)`; non-target warps fall through to `EXIT`.
- Host-side warp stride is 16 **bytes** = 4 **words** (classic stride bug).

## Reproduce

```
python3 tests/asm_construct/test_subcore_yield.py
```

Probe scripts used during development (not committed): `/tmp/opencode/probe_subcore.py`,
`/tmp/opencode/probe_yield_asym.py`, `/tmp/opencode/probe_issue.py`.

## Open questions

- The exact issue-port arbitration: is the transN/WnEG bias ~2:1 always, or
  does it depend on warp count per subcore / instruction mix?  A 3-warp
  shared-subcore probe (`{0,4,8}`, block=288) would pin the arbitration rule.
- Whether the mapping is strictly `i%4` across **blocks** sharing an SM (a
  second co-resident CTA's warps: do they continue the round-robin or restart
  at subcore 0?).
- Whether `DRAIN` (`stall=0`) behaves as a stronger "yield to any warp" than
  `WnEG` (its 34-cycle solo penalty suggests a full pipe drain, not just an
  issue-slot handoff).
