# UTCSHIFT — async TMEM row-shift  → PTX `tcgen05.shift.down`

**Opcode mnemonic:** `UTCSHIFT` = `0b1100111100110` (0x19e6, 6630)
**Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42)

New on sm100 (Blackwell). `UTCSHIFT` = the SASS realization of PTX
**`tcgen05.shift.down`** — an asynchronous instruction that shifts a matrix's
rows down by one in Tensor Memory. It is the **standalone** version of the row
slide that `UTCHMMA.ASHIFT` performs fused into an MMA.

## Semantics
`UTCSHIFT.DOWN tmem[URa + Sa_offset]` shifts the **32-byte elements downwards
across all rows except the last, by one row**, for the TMEM matrix based at
`URa + Sa_offset`. The `taddr` lane must be 32-aligned. Async / decoupled
(`src_rel_sb` pinned `*7`; ordered via the BRU/depbar path — see INSTRUCTION_TYPE
below).

**The shift spans the full M-plane globally — it crosses 32-row subcore
boundaries.** The spec says "shifting … downwards across **all** the rows, except
the **last**, by one row" and for `.cta_group::2` "performed in the Tensor
Memory of **both** the current and the peer CTAs." This is a single
M-wide down-shift with only the global bottom row fixed, not four independent
per-32-row-segment shifts:
- The "32" in the lane-alignment requirement ("lane of `taddr` must be aligned to
  32") refers to TMEM **column/allocation-unit** alignment (TMEM is allocated in
  units of 32 columns), not M-direction segmentation — the row shift propagates
  across the entire stacked 128/256-row plane.
- **`.ashift` confirms this**: `.ashift` is only legal at M=128 or M=256 — it
  requires the full M-stack to be occupied so that a single shift can slide the
  activation window across all subcore rows as one coherent receptive-field
  advance (see `tcgen05_microarch_speculation.md`). A per-32-row shift would be
  legal at M=32/64; the M=128/256 gate is strong evidence against segmentation.
- **`cta_group::2` proves it**: with `.cta_group::2` the shift crosses the CTA
  boundary (256 rows) as one operation — it must obviously cross the internal
  32-row subcore boundaries within each CTA as well.

This wording is **identical** to `.ashift`'s in the MMA spec ("shifts the rows of
the A matrix down by one row, except for the last row"), which is what ties the
two together (see cross-comparison).

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

So they are two encodings of the *same primitive*: fused into the MMA
(`.ASHIFT`) vs issued separately (`UTCSHIFT`). PTX exposes the fused form as the
`.ashift` MMA qualifier and the standalone form as `tcgen05.shift.down`.

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
- Latency/ordering: the BRU+DEPBAR typing suggests it rendezvouses with dependent
  MMAs like a barrier — precise semantics vs the MMA's own scoreboard TBD.
