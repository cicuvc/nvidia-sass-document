# PMTRIG — Performance Monitor Trigger

**Opcode mnemonic:** `PMTRIG`  |  **Pipe:** `fe_pipe` (front-end pipe)  |
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Fires a programmatic performance-monitor event. The 16-bit immediate is an
event **bitmask**: each bit corresponds to one of the 16 programmatic events
and the event fires on the SM's performance-monitor hardware. The event is
combined with hardware events (via host-programmed Boolean functions) to
increment one of the four PM counters — see "Capturing the events" below.

`PMTRIG [!]Pp, <16-bit mask>`

The `Pp` predicate gates the trigger: when `!Pp` is false the event is
suppressed. Default `Pp = PT` (always trigger), omitted from disassembly.
`Pg` is the ordinary guard (`@!Px PMTRIG ...`).

## Variant overview

| Variant | Opcode | Notes |
|---------|--------|-------|
| `pmtrig_` | `0x801` | single class; `Pp`/`Pg` slots + 16-bit `imm` |

## PTX mapping (`pmevent`)

```
pmevent 0      → PMTRIG 0x1       (1 << 0)
pmevent 1      → PMTRIG 0x2       (1 << 1)
pmevent 4      → PMTRIG 0x10      (1 << 4)
pmevent 15     → PMTRIG 0x8000    (1 << 15)
pmevent.mask 0x5   → PMTRIG 0x5   (mask passed through)
pmevent.mask 0xffff → PMTRIG 0xffff
```

`pmevent` without `.mask` takes an event index `0..15` and ptxas lowers it to
`1 << N`; `pmevent.mask` passes the 16-bit mask through unchanged. Verified
identically on sm_90 and sm_120 (CUDA 12.8).

**Predicated `pmevent`:** ptxas does *not* use the `Pp` slot. `@p pmevent 3`
becomes a branch (`@!P0 EXIT` + unconditional `PMTRIG 0x8` in the taken path),
so the `Pp` gating field is only reachable via hand-written SASS. The same
pattern is used by profilers when they inject PMTRIG into a stream.

## Modifiers

| Field | Bits | Enum | Default | Meaning |
|-------|------|------|---------|---------|
| `pm_pred` | [103:102] | `PM_PRED`: `PMN`=0, `PM1`=1, `PM2`=2, `PM3`=3 | `PMN` | selects which PM counter the trigger feeds (spec-level; never emitted by ptxas/cuobjdump) |
| `usched_info`/`batch_t` | opex [124:122]∥[109:105] | `TABLES_opex_1` | DRAIN/NOP | schedule annotation; ptxas prints `?trans1` |

`PM_PRED` is a *shared* optional slot across many classes (memory + async
instructions too, e.g. ALD/AST/ARRIVES/ACQBULK), not PMTRIG-specific; with
default `PMN=0` it contributes nothing to the observable encoding.

## Bit layout (128-bit)

```
 127       112 111       96
 | opex     | req | sb7 | sb7 | ... pm_pred ...
   [124:122]∥[109:105]  [121:116]  [115:113]  [112:110]  [103:102]
  95        80 79        64
 | ...      |            |
  63        48 47        32 31        16 15 14    12 11         0
 |          | imm[15:0]  |            | !P| Pg | opcode[11:0]  |
    (hi64)     [47:32]                   [15] [14:12]
   opcode[12] = bit[91] (hi64)  → 13-bit opcode 0x801
   Pp = [89:87], Pp_not = [90] (hi64)
```

## Cross-comparison

- fe_pipe sibling instructions: `NOP`, `DEPBAR`, `STP`, `CSMTEST` — all
  `INST_TYPE_COUPLED_MATH`, issued from the front end without a math pipe.
- `CoupledDispOverlapWithMathOps` (sm_90_latencies line 235) groups PMTRIG
  with NOP/CS2R/LEPC/RPCMOV/DEPBAR/IDE for scheduler-overlap accounting.
- No register operands (`ISRC_B_SIZE=16` immediate only, `IDEST_SIZE=0`), so
  no `TABLE_TRUE`/`TABLE_OUTPUT`/`TABLE_ANTI` row applies — nothing to wait on.
- See also `notes/sm90/instr/ide.md` (front-end discussion), `depbar.md`/`nop.md`.

## Latency

`fe_pipe`, zero-issue-impact (no dependencies). No latency-matrix row: it
neither writes nor reads registers.

## Verified encodings (sm_90 == sm_120, CUDA 12.8)

| Lo64 | Disassembly | Source |
|------|-------------|--------|
| `0x0000000100007801` | `PMTRIG 0x1` | `pmevent 0` |
| `0x0000000200007801` | `PMTRIG 0x2` | `pmevent 1` |
| `0x0000000400007801` | `PMTRIG 0x4` | `pmevent 2` |
| `0x0000000800007801` | `PMTRIG 0x8` | `pmevent 3` |
| `0x0000001000007801` | `PMTRIG 0x10` | `pmevent 4` |
| `0x0000800000007801` | `PMTRIG 0x8000` | `pmevent 15` |
| `0x0000000500007801` | `PMTRIG 0x5` | `pmevent.mask 0x5` |
| `0x0000ffff00007801` | `PMTRIG 0xffff` | `pmevent.mask 0xffff` |
| `0x0000000800007801` / hi64 `0x000fe20001000000` | `PMTRIG P1, 0x8` | hand-built (decoder) |
| `0x0000000800007801` / hi64 `0x000fe20004800000` | `PMTRIG !P1, 0x8` | hand-built (decoder) |
| `0x0000001000008801` | `@!P0 PMTRIG 0x10` | hand-built (decoder) |

Assembler round-trip (`assembler/`, sm_120) reproduces the lo64 exactly for
all of the above; the hi64 control word is scheduler-written and differs from
ptxas's (`0x001fca0003800000` vs `0x000fe20003800000`), like other
hand-assembled instructions. A kernel with six PMTRIG variants runs on the
RTX 5090 without fault (`tests/asm_construct/test_pmtrig.py`).

## Capturing the events (why this is the observable limit)

PMTRIG only *fires* a signal; nothing in SASS reads the counters back. The
capture side was historically the host: CUPTI's Event API
(`cuptiEventGroupCreate`/`cuptiEventEnable`/`cuptiEventGroupReadEvent`)
programmed the counter/Boolean mapping and read deltas around `pmevent`
markers. That API is **unsupported on compute capability 7.5 and higher**
(header `cupti_events.h`; nvprof confirms on sm_75/sm_120), deprecated in
CUDA 12.8 and slated for removal — so neither the RTX 2080 Ti (sm_75) nor the
RTX 5090 (sm_120) can use it.

The replacement (CUPTI Profiler API / Range Profiler, i.e. what `ncu` uses)
works on both GPUs, but the 16 programmatic events are **not exposed** in its
counter/metric database: `ncu --query-metrics` on the 5090 lists 5189
profiling metrics and 824 pm-sampling metrics with zero `pm0..pm15`/`pmevent`/
`PMTRIG` entries. Practically, on modern archs the pmevent mechanism is
reserved for NVIDIA profiling tools, not user-reachable counters.

What *can* be captured: PMTRIG executes as a real fe_pipe warp instruction.
`ncu --metrics sm__inst_executed.sum` on the RTX 5090 counts 12 instructions
for a kernel with four `pmevent`s vs 8 for the identical kernel without them
(delta = 4 PMTRIGs), and no per-opcode PMTRIG counter exists
(`sm__inst_executed_op_*` covers memory ops only).

## PM counter registers (`SR_PM*`) and the `pm_pred` tag

The sm_90+ spec defines eight 64-bit PM counters readable from SASS via
`CS2R`: `SR_PM0..7` (= 100..115, `SR_PMx:SR_PM_HIx` pairs) plus eight snapshot
registers `SR_SNAP_PM0..7` (= 116..131). Empirically on the RTX 5090:

- Reads are legal (`CS2R {R0,R1}, SR_PM0` runs without fault) but return 0
  when no profiling session is active.
- Under `ncu` (root, RTX 5090) the registers mirror the *live* hardware
  counters the profiler programmed: with `smsp__inst_executed.sum` +
  `smsp__cycles_active.sum` requested, `SR_PM0` counts per-SMSP instructions
  (CS2R reads themselves excluded: final value == total inst - #reads) and
  `SR_PM1` counts cycles; requesting only `sm__*` metrics leaves `SR_PM1` at
  0. `SR_SNAP_PM*` stayed 0 in every session tested.
- So `pmevent`/`PMTRIG` alone does *not* make anything visible: the counters
  are armed and their event expression programmed by the profiling host.

`pm_pred` (bits [103:102], enum `PMN`/`PM1`/`PM2`/`PM3`, default `PMN`) is a
**per-instruction tag present on every sm_90+/sm100/sm120 class** (1168+421
variants sm_90; zero on sm_80/sm_75). cuobjdump prints it as `?PM1`/`?PM2`/
`?PM3` (verified by patching the encoding; `PMN` is hidden). Hand-tagging
PMTRIGs with `?PM1`/`?PM2`/`?PM3` changed no readable counter under ncu —
the tags are inert without a host-programmed tag-matching event expression.
Consistent with the PTX note ("programmatic events may be combined with other
hardware events using Boolean functions to increment one of the four
performance counters ... programmed via API calls from the host"), the
working model is: pm_pred selects a per-instruction PM lane the host can use
to filter which instructions contribute to a counter; the public CUPTI
profiler/metric DB on CC>=7.5 exposes no such counters, so the field is only
reachable by NVIDIA-internal profiling tooling.

## Open questions

- How the host programs a tag-matching event expression for `?PM1/2/3`
  (driver-internal; not exposed by CUPTI on sm_75+).
- What `SR_SNAP_PM*` snapshots and what arms them (never non-zero under ncu).
