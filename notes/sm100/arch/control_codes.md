# Control codes — per-instruction scheduling word (sm100 vs sm_90)

**Question:** did the "control codes" (wait mask, read/write scoreboards,
PM predicate, micro-scheduler `usched_info`, `batch_t`, operand **reuse** flags)
change between Hopper (sm_90) and Blackwell (sm100)?
**Status:** resolved from the spec dumps. **The control word is unchanged.**
(Empirical Blackwell-SASS corroboration is still TODO — no cuobjdump vectors
mined yet.)

See the sm_90 note `notes/sm90/arch/control_codes.md` for the full derivation of
each field; this note only records the sm100 delta.

## TL;DR — byte-for-byte identical control word

Every control/scheduling field keeps the **exact same bit positions, widths,
encoders, and enum value-maps** on sm100 as on sm_90:

| Field | Bits | Width | Encoder | sm_90 → sm100 |
|-------|------|------:|---------|:-------------:|
| `req_bit_set` (wait barrier mask) | [121:116] | 6 | `BITSET(6/0x0000)` | **same** |
| `src_rel_sb` (read barrier) | [115:113] | 3 | `VarLatOperandEnc` | **same** |
| `dst_wr_sb` (write barrier) | [112:110] | 3 | `VarLatOperandEnc` | **same** |
| `pm_pred` (perf-monitor pred) | [103:102] | 2 | `PM_PRED` | **same** |
| `opex` (usched/batch/reuse) | [124:122] ∥ [109:105] | 8 | `TABLES_opex_N(...)` | **same** |

Verified programmatically against `sm90.json` / `sm100.json`:
- Control-field bit positions for `opex`, `req_bit_set`, `src_rel_sb`,
  `dst_wr_sb`, `pm_pred`: **all identical** across every CLASS.
- `FUNIT uC` control-word view: all **565 named control fields** unchanged
  (0 added / 0 removed / 0 moved), incl. `Pred`[18:16], `PredNot`[19],
  `OEReuseA/B/C`[81/82/83], `Sync`[63], `NODEP`[49].
- Scheduling enums byte-identical: `USCHED_INFO` (0=DRAIN, 1..15=WnEG,
  17..27=trans/Wn), `BATCH_T` (NOP/BATCH_START/BATCH_START_TILE/BATCH_END(4)/
  BARRIER_EXEMPT(5), value 3 still unnamed), `PM_PRED` (PMN/PM1..3),
  `REUSE` (noreuse/reuse), `Scoreboard` (SB0..SB5 + INVALID6/7).
- **`opex` tables `TABLES_opex_0..9` are content-identical** (row-for-row): 157,
  87, 113, 135, 179, 135, 1, 113, 113, 135 rows respectively — same on both
  arches. The reuse-bit overload on [124:122] and the reuse⊕`?DRAIN`/`?WnEG`
  mutual exclusion are unchanged.

Every one of the 1380 sm100 CLASS variants carries the full control block
(`req_bit_set` + `src_rel_sb` + `dst_wr_sb` + `pm_pred` + `opex` present in all).

### opex-table usage across sm100 classes
Distribution of which opex packer each class selects (informational — the tables
themselves are unchanged from sm_90):

| table | inputs | classes |
|-------|--------|--------:|
| `opex_0` | (batch_t, usched) — no reuse | 674 |
| `opex_1` | same, batch_t≠3 — special ctrl ops | 188 |
| `opex_2` | + reuse_a | 139 |
| `opex_3` | + reuse_a, reuse_c | 136 |
| `opex_5` | + reuse_a, reuse_b | 116 |
| `opex_4` | + reuse_a, reuse_b, reuse_c | 66 |
| `opex_7` | + reuse_b | 29 |
| `opex_8` | + reuse_c | 20 |
| `opex_9` | 4-input | 10 |
| `opex_6` | 1-row | 2 |

(Note sm100 uses `opex_7`/`opex_8` — standalone reuse_b / reuse_c tables — which
sm_90 did not populate; this only reflects that some new Blackwell classes expose
a reusable source in the B or C slot only, exactly like Turing sm_75 did. The
reuse *bit positions* [124:122] and table *contents* are unchanged.)

## The one real difference: tensor-core sync no longer uses a private scoreboard

This is a control-flow/synchronization change rather than a control-*word*
change, but it belongs here because it alters how completion is tracked.

- **sm_90 wgmma** (`HGMMA/IGMMA/BGMMA/QGMMA`) tracked async-MMA completion via a
  **dedicated GMMA scoreboard**, encoded through the `OPTIONAL_GSB` operand
  (`cop` field [86:84]) and modeled by `TABLE_TRUE(GMMA_SCOREBOARD)` /
  `TABLE_TRUE(GMMA_GROUP_SCOREBOARD)` in `sm_90_latencies.txt`.
- **sm100 tcgen05** (`UTCHMMA/UTCIMMA/UTCQMMA/UTCMXQMMA/UTCOMMA`) drops that
  entirely: `OPTIONAL_GSB` usage 43× (sm_90) → **0×** (sm100), and both
  `GMMA_SCOREBOARD` latency tables are **gone** (6 refs → 0). The `UTC*` classes
  instead carry the **standard** control block — ordinary `req_bit_set` wait mask
  + `src_rel_sb` read barrier + `dst_wr_sb` — so tensor-core dependency tracking
  folds back into the normal 6-entry scoreboard model (plus `UTCBAR`, a new
  explicit tensor-core barrier op, for cross-op ordering).

So from a scheduler/decoder standpoint the `UTC*` family looks like a regular
long-latency `udp_pipe` instruction with normal scoreboard release, not a
special GMMA-scoreboard citizen.

## What this means for the decoders
- All existing sm_90 control-word decode logic (wait mask, scoreboards,
  `usched`/`batch_t`/`reuse` extraction, `pm_pred`) **ports to sm100 verbatim** —
  no bit-position or enum edits required.
- The only decoder-relevant change is that tensor-core (`UTC*`) instructions now
  decode their scoreboard fields the ordinary way, whereas the old `HGMMA` path
  had to special-case `OPTIONAL_GSB`/`cop`.

## Open questions
- Empirical confirmation on real Blackwell SASS: mine cuobjdump `-arch sm_100`
  (CUDA ≥12.8) for reuse-bit / wait-mask / `usched` samples, mirroring the sm_90
  cublas survey, to confirm the fields decode as predicted.
- Does ptxas ever emit non-zero `batch_t` on Blackwell (still only
  `BARRIER_EXEMPT` on `DEPBAR`, or does tcgen05 use `BATCH_*` grouping)?
- How is `UTCBAR` ordered relative to the standard scoreboard release on `UTC*`
  ops (is the wait mask sufficient, or is `UTCBAR` mandatory between dependent
  MMAs)? — track in `arch/tcgen05.md`.
