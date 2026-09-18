# UTCSHIFT — async TMEM row-shift  → PTX `tcgen05.shift.down`

**Opcode mnemonic:** `UTCSHIFT` = `0b1100111100110` (0x19e6, 6630)
**Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42)

New on sm100 (Blackwell). `UTCSHIFT` = the SASS realization of PTX
**`tcgen05.shift.down`** — an asynchronous instruction that shifts a matrix's
rows down by one in Tensor Memory. It is the **standalone** version of the row
slide that `UTCHMMA.ASHIFT` performs fused into an MMA.

## Semantics
`UTCSHIFT.DOWN tmem[URa + Sa_offset]` shifts 32-byte elements down by one row
for the TMEM matrix based at `URa + Sa_offset`.  The `taddr` column must be
32-aligned. It has **warp-scalar U-path issue granularity**: one native
instruction initiates the whole `.cta_group::1` operation for its issuing warp,
even when all active lanes execute it. Completion is asynchronous and is
tracked by a later `tcgen05.commit`/`UTCBAR` from that warp's stream.

Dynamic B200 readback establishes that the operation is physically segmented
at the four warp/subcore TMEM chunks.  In each 32-row chunk it performs
`row[i] <- old row[i+1]` for `i=0..30`, while row 31 is retained.  The four
independent boundaries are therefore 31/32, 63/64, and 95/96: data does **not**
propagate across them. One warp-scalar issue still triggers all four chunks in
the CTA.

This wording is identical to `.ashift`'s in the MMA spec ("shifts the rows of
the A matrix down by one row, except for the last row"), strongly suggesting a
shared primitive.  The chunk segmentation is measured directly only for the
standalone form so far.

## Relationship to `UTCHMMA.ASHIFT` — fused vs standalone
The user's hypothesis "`.ashift` ≈ MMA then a `tcgen05.shift`" is **conceptually
right but not literally two instructions**:
- **`UTCHMMA.ASHIFT`** (opcode 0x19ea, bit [74]=1) is a **single fused
  instruction** — MMA + the row slide in one op. Verified: compiling
  `tcgen05.mma.…ashift` emits exactly one `UTCHMMA.ASHIFT` and **no** separate
  `UTCSHIFT` (`/tmp/ashift_probe`).
- **`UTCSHIFT.DOWN`** (opcode 0x19e6) is the **standalone** row slide — same
  down-by-one-row semantics, but as its own instruction, for when you need to
  advance the window **without** an accompanying MMA (or when the shift decouples
  from the MMA cadence).

Thus they are most likely two encodings of the same segmented row-shift
primitive: fused into the MMA (`.ASHIFT`) vs issued separately (`UTCSHIFT`). PTX
exposes the fused form as the `.ashift` MMA qualifier and the standalone form as
`tcgen05.shift.down`.

Note the asymmetry from the convolution analysis
(`notes/sm100/arch/tcgen05_microarch_speculation.md`): `.ashift` fuses into the
**AS** MMA (activation in A, slides as rows). `UTCSHIFT` is the general TMEM
row-shift you can point at any TMEM matrix. Both only make sense when the shifted
matrix is TMEM-resident.

## Variant overview
| Class | Kind | Opcode | cluster |
|-------|------|--------|---------|
| `utcshift__1CTA` | CLASS | 0x19e6 | `1CTA` (`$VQ_TC_1CTA`) |
| `utcshift__2CTA` | CLASS | 0x19e6 | `2CTA` (`$VQ_TC_2CTA`) |
| `utcshift_one__1CTA` / `_one__2CTA` | ALT | 0x19e6 | + `.ONE` (encoding-identical) |

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `cluster_sz` | `ONLY1CTA`/`ONLY2CTA` | [85] (`ignoreKill`) | `.2CTA` = PTX `.cta_group::2` |
| `mode` | `DOWNONLY` | [80] (`texunpack`) | `.DOWN` (only value =1; the "down" direction) |

`DOWNONLY` has a single value `DOWN`=1 — the only shift direction exposed.

## Bit layout (128-bit)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = *7 (pinned)
[112:110]           dst_wr_sb    = *7 (pinned)
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x19e6
[85]                ignoreKill   = cluster_sz (2CTA)
[80]                texunpack    = mode (DOWN)
[79:72]∥[63:40]     Sb_offset    = Sa_offset (32-bit signed TMEM offset, split)
[31:24]             Ra           = URa (TMEM base address)
[15]                Pg_not ; [14:12] Pg = @UPg (UniformPredicate)
```

`INSTRUCTION_TYPE = INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` — note the **BRU**
(branch/convergence-barrier unit) + **DEPBAR** typing, the same class family as
Hopper's `WARPGROUP.*` ops (`notes/sm90/arch/wgmma.md`). The shift is a
barrier-class async op that participates in the depbar/scoreboard ordering, not a
plain MIO memory op — consistent with it reshaping the tensor-core's TMEM feed
state that MMAs depend on.

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/tcgen05_shift_test.cu` → `tests/tcgen05_shift_test.cubin`.
Decoder: `tools/decode_utcshift.py` — all round-trip (**ALL PASS**).

| Disassembly | Lo64 / Hi64 | 2CTA | URa |
|-------------|-------------|:----:|:---:|
| `UTCSHIFT.DOWN tmem[UR6]` | `…79e6` / `08010000` | 0 | UR6 |
| `UTCSHIFT.2CTA.DOWN tmem[UR4]` | `…79e6` / `08210000` | 1 | UR4 |
| `UTCSHIFT.DOWN tmem[UR4]` | `…79e6` / `08010000` | 0 | UR4 |

Confirmed: `tcgen05.shift.down.cta_group::1/2 [taddr]` → `UTCSHIFT[.2CTA].DOWN
tmem[URa]`; `.DOWN` (bit[80]) always present; `.2CTA` = bit[85] (needs a cluster
launch). Also confirmed `UTCHMMA.ASHIFT` is one fused op, not MMA+UTCSHIFT.

## Dynamic B200 validation (2026-09-17)

`tests/tcgen05_cp_shift_runtime.cu` writes eight tagged columns with STTM,
executes one lane-0 `tcgen05.shift`, commits it to an mbarrier, and reads the
matrix back with LDTM.  For one warp the first value in each row changes from
`0,1,...,31` to:

```
1,2,...,30,31,31
```

A four-warp version writes globally unique row tags 0..127 and issues the shift
from thread 32.  Its four output ranges are independently:

```
1..31,31 | 33..63,63 | 65..95,95 | 97..127,127
```

Thus the earlier all-lanes result that produced row 31 everywhere cannot be
explained as 32 independent U-path issues: native UTCSHIFT is warp-scalar. It
must be reinterpreted as a probe construction/order artifact. The corrected
sequence issues both `shift` and the tracking `commit` from the same warp. With
one UTCBAR event and an mbarrier initialized to count 1, the first completion is
waited with phase parity 0.

### Admission cadence and parallel tiles

`tests/tcgen05_shift_bandwidth.cu` unrolls 1--128 shifts of the same aligned
32-column TMEM tile and waits for the final commit.  B200 timing is exact and
noise-free:

| shifts | cycles |
|---:|---:|
| 1 | 152 |
| 2 | 196 |
| 4 | 284 |
| 8 | 460 |
| 16 | 812 |
| 32 | 1516 |
| 64 | 2924 |
| 128 | 5740 |

Therefore the native PTX lowering follows **`cycles = 108 + 44*N`**, or one
same-tile shift every 44 cycles.  This is not yet a direct measurement of the
raw TMEM-array byte bandwidth.  Lifting the cubin reveals that ptxas emits a
six-instruction convergence/election envelope for every logical shift:

```text
PLOP3(13) -> ELECT(1) -> UTCSHIFT(12) -> PLOP3(2)
            -> PLOP3(11) -> BRA.U.ANY(5)
```

The scheduled stalls sum to exactly 44.  Patching only UTCSHIFT from stall 12
to 11 or 1 while retaining the surrounding envelope makes even a one-shift
kernel fail to leave the retry protocol.  Thus 12 is a forwarding/state-
visibility floor from UTCSHIFT to the following PLOP sequence, not arbitrary
ptxas padding.  The bare-instruction experiment below shows that it is **not**
an unconditional front-end admission restriction on UTCSHIFT itself.

#### Bare SASS stream

The nvcc cubin was patched a second way: each six-instruction envelope was
replaced in place by consecutive raw
`UTCSHIFT.DOWN tmem[UR6];[7:7:{}:stall:1]` instructions and one branch over the
now-unused padding.  All allocator, commit/mbarrier, capmerc and exit metadata
remain those of the original nvcc cubin.

With `stall=12`, the steady timing becomes exactly:

```text
cycles = 119 + 12*N
```

Representative results are 215, 311, 503, 887 and 1655 cycles for 8, 16, 32,
64 and 128 shifts.  This cleanly decomposes the native 44-cycle cadence into a
12-cycle raw stream plus 32 cycles of PTX execution-group enumeration overhead.

More importantly, a raw stream with `stall=1` also executes correctly.  A
separate readback kernel initializes row `r` with `0x51000000|r`, issues
1/2/4/8/16 naked shifts, waits through `tcgen05.commit`, then reloads TMEM.
Every result is exactly:

```text
row[r] = old_row[min(r + N, 31)]
```

so aggressive issue neither merges nor drops shifts.  Short bursts can
therefore enter faster than one per 12 cycles.  Once the stream is long enough,
hardware throttle/backend service dominates: in one stable warmed state,
stall-1 streams of 8, 16 and 32 shifts take 244, 340 and 532 cycles, whose two
successive slopes are both exactly **12 cycles/shift**.  Longer stall-1/2/4/8
streams likewise converge to approximately this slope.

Absolute intercepts change after several Modal launches, most likely because
the SM and tensor/TMEM domains change clock state; static ptxas scheduling does
not show this transition, while backend-dominated naked streams do.  Queue
depth should therefore be measured from instruction-level admission markers,
not inferred directly from these cross-launch intercepts.  The robust result
is: **raw admission accepts a burst at one instruction per cycle, while the
sustained same-tile service rate is about one shift per 12 SM cycles in a
fixed clock state.**

Independent tiles can overlap.  `tests/tcgen05_shift_parallel.cu` allocates
128 columns and lets the lane-0 thread of one, two, or four warps shift separate
32-column tiles.  Each issuer commits to and waits on its own mbarrier.  The
maximum per-issuer intervals are:

| shifts/issuer | 1 issuer | 2 issuers | 4 issuers |
|---:|---:|---:|---:|
| 1 | 152 | 184 | 194 |
| 8 | 460 | 498 | 508 |
| 32 | 1516 | 1602 | 1747 |

At batch 32, aggregate operation throughput rises from **0.0211** to
**0.0399** to **0.0733 shifts/cycle** for one, two, and four issuers.  Four
independent tiles thus reach 3.47x the finite-batch aggregate throughput of one
issuer (about 3.4x after removing the single-stream 108-cycle intercept), not a
single global 1/44 shift/cycle bottleneck.  The four individual batch-32
intervals are 1747, 1731, 1735, and 1743 cycles, showing balanced service.

These figures are intentionally reported in shifts/cycle, not bytes/cycle:
the standalone operation updates four independently segmented row ranges, and
the physical implementation may rotate/rename rows rather than read and write
the full logical matrix through a conventional datapath.  Calling the logical
matrix footprint “physical TMEM traffic” would overstate what this probe has
established.

Schedule patcher: `tools/patch_tcgen05_shift_schedule.py`.
Bare semantic check: `tests/tcgen05_shift_bare_correctness.cu`.

## Cross-references
- `notes/sm100/instr/utchmma.md` — `.ASHIFT` (bit[74]) is the fused MMA+shift;
  this is the standalone form.
- `notes/sm100/arch/tcgen05_microarch_speculation.md` — the convolution dataflow:
  `.ashift`/shift = receptive-field row slide over a TMEM-resident activation
  window (AS conv); the mirror WS conv uses the zero-column mask on B instead.
- `notes/sm100/instr/ldtm.md`/`sttm.md`/`utccp.md` — other TMEM ops; UTCSHIFT
  mutates TMEM contents in place.

## Open questions
- Only `.DOWN` exists (no up/left/right) — is up-shift unnecessary because the
  window only ever advances one way in a conv sweep?
- Exact interaction with the collector: does a standalone `UTCSHIFT` invalidate/
  update the A collector buffer, or only the TMEM backing store?
- The exact outstanding-queue depth needs an in-kernel admission timestamp
  probe; cross-launch timing is contaminated by clock-domain state changes.
- The maximum number of simultaneously outstanding shifts, especially across
  more CTAs, remains to be measured.
