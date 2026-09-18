# UTCCP — async shared-memory → TMEM copy  → PTX `tcgen05.cp`

**Opcode mnemonic:** `UTCCP` = `0b1100111100111` (0x19e7, 6631)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42) | **MEM_SCBD_TYPE:** `BARRIER_INST`

New on sm100 (Blackwell). The SASS realization of PTX **`tcgen05.cp`** — an
asynchronous copy of a matrix from **shared memory** (addressed by a 64-bit UMMA
matrix descriptor) into **Tensor Memory (TMEM)**, with optional on-the-fly
decompression of packed FP6/FP4 source formats to `b8x16`. It is the data-staging
path that feeds `UTC*MMA` operands into TMEM without going through registers.

## Semantics
`UTCCP.T.S[.mode][.srcfmt] tmem[URa + Sa_offset], gdesc[URb]`
- **`.T`** = destination is **T**ensor memory; **`.S`** = source is **S**hared
  memory. Both role tags are always printed by cuobjdump (the `OnlyT`/`SONLY`
  enums each have a single value — the direction is fixed shmem→TMEM).
- `gdesc[URb]` — a **64-bit** UMMA matrix descriptor (`UMMAB` operand,
  `ISRC_B_SIZE=64`) in a register pair starting at `URb`; describes the source
  matrix layout/base in shared memory (same descriptor format as wgmma/UTC MMA).
- `tmem[URa + Sa_offset]` — TMEM destination base (32-bit address in `URa`, plus
  a 32-bit signed immediate offset).

Async / decoupled: `INST_TYPE_DECOUPLED_RD_SCBD` + `src_rel_sb` active,
`dst_wr_sb` pinned `*7`.  It has **warp-scalar U-path issue granularity**: one
native instruction initiates one complete copy for the issuing warp, even when
all active lanes execute it. Like STTM it releases only a **read** scoreboard
(it has no register destination), but unlike STTM its operation completion is
tracked by `tcgen05.commit`/`UTCBAR`, not `tcgen05.wait::{ld,st}`.  A dependent
MMA is also an implicitly pipelined successor.

## Variant overview
| Class | Kind | Opcode | cluster |
|-------|------|--------|---------|
| `utccp__1CTA` | CLASS | 0x19e7 | `1CTA` (`$VQ_TC_1CTA`) |
| `utccp__2CTA` | CLASS | 0x19e7 | `2CTA` (`$VQ_TC_2CTA`) |
| `utccp_one__1CTA` | ALT | 0x19e7 | + `.ONE` |
| `utccp_one__2CTA` | ALT | 0x19e7 | + `.ONE` |

The `_one_` alternates are encoding-identical (`.ONE` display-only). 2CTA maps
PTX `.cta_group::2` (copies into both peer CTAs' TMEM); it selects a different
virtual queue and sets bit[85].

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `mode` | `MODE_128dp256bit_…` | [88]∥[84:83] | shape + multicast, **fused** (see below) |
| `cluster_sz` | `ONLY1CTA`/`ONLY2CTA` | [85] (`ignoreKill`) | 1CTA / 2CTA |
| `src_fmt` | `SRC_FMT` | [81:80] (`selB`) | decompress source format |
| `dst` / `src` | `OnlyT` / `SONLY` | [86] / [87] | direction role tags (fixed) |

### The `mode` field fuses PTX `.shape` **and** `.multicast`
This is the key PTX→SASS insight: PTX spells shape and multicast separately, but
SASS packs both into one 3-bit `mode`:

| PTX `.shape`(`.multicast`) | SASS `mode` | val |
|----------------------------|-------------|----:|
| `.128x256b` | `128dp256bit` | 0 |
| `.4x256b` | `4dp256bit` | 2 |
| `.128x128b` | `128dp128bit` | 3 |
| `.64x128b.warpx2::02_13` | `2x64dp128bit_lw02_lw13` | 4 |
| `.64x128b.warpx2::01_23` | `2x64dp128bit_lw01_lw23` | 5 |
| `.32x128b.warpx4` | `4x32dp128bit` | 6 |
| — (illegal) | INVALID1 / INVALID7 | 1,7 |

The `2x64…` / `4x32…` names encode the multicast fan-out directly: `2x64` = two
warp-halves (warpx2), `lw02_lw13`/`lw01_lw23` = the warp-pair grouping, `4x32` =
warpx4 (all four warps). `dp` = datapath (lane group), matching the `NNdpMMbit`
convention from LDTM/STTM.

`SRC_FMT`: `nosrc_fmt`=0, `U4x16P64`=1 (PTX `.b4x16_p64`), `U6x16P32`=2 (PTX
`.b6x16_p32`), INVALID3. When set, dst is implicitly `.b8x16` (decompression).

## Bit layout (128-bit)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = read-scoreboard release
[112:110]           dst_wr_sb    = *7 (pinned: no write scoreboard)
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x19e7
[88]∥[84:83]        mode         = shape+multicast (3b, MSB at 88)
[87]                cas          = src  (SONLY role tag)
[86]                depth        = dst  (OnlyT role tag)
[85]                ignoreKill   = cluster_sz (2CTA)
[81:80]             selB         = src_fmt (decompress)
[79:72]∥[63:40]     Sb_offset    = Sa_offset (32-bit signed TMEM offset, split)
[39:32]             Rb           = URb (matrix descriptor, 64-bit pair)
[31:24]             Ra           = URa (TMEM base address)
[15]                Pg_not ; [14:12] Pg = @UPg (UniformPredicate)
```
Operand-placement note: unlike LDTM/STTM (which use `Rb`[39:32] for the TMEM
address), UTCCP puts the **descriptor** in `Rb`[39:32] and the **TMEM address**
in `Ra`[31:24] — the descriptor is the primary "source" operand.

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/utccp_test.cu` → `tests/utccp_test.cubin`. Decoder:
`tools/decode_utccp.py` — all 8 round-trip (**ALL PASS**).

| Disassembly | Hi64 | mode | src_fmt |
|-------------|------|:----:|:-------:|
| `UTCCP.T.S tmem[UR6], gdesc[UR8]` | `…08000000` | 0 `128dp256bit` | – |
| `UTCCP.T.S.128dp128bit …` | `…08180000` | 3 | – |
| `UTCCP.T.S.4dp256bit …` | `…08100000` | 2 | – |
| `UTCCP.T.S.2x64dp128bit_lw02_lw13 …` | `…09000000` | 4 | – |
| `UTCCP.T.S.2x64dp128bit_lw01_lw23 …` | `…09080000` | 5 | – |
| `UTCCP.T.S.4x32dp128bit …` | `…09100000` | 6 | – |
| `UTCCP.T.S.128dp128bit.U6x16P32 …` | `…081a0000` | 3 | 2 `.b6x16_p32` |
| `UTCCP.T.S.128dp128bit.U4x16P64 …` | `…08190000` | 3 | 1 `.b4x16_p64` |

(All lo64 = `0x00000008060079e7`: URa=UR6, URb=UR8, role bits src/dst set.)

Confirmed facts:
- `.128x256b`/`.x1` defaults elide to bare `UTCCP.T.S`.
- Multicast is **not** a separate SASS token — it is baked into `mode`
  (`.64x128b.warpx2::02_13` → `.2x64dp128bit_lw02_lw13`, `.32x128b.warpx4` →
  `.4x32dp128bit`). ptxas rejects `.64x128b`/`.32x128b` without the required
  multicast (matches the spec's shape↔multicast requirement).
- Decompression: `.b8x16.b6x16_p32` → `.U6x16P32`, `.b8x16.b4x16_p64` →
  `.U4x16P64` (bits [81:80]).

## Dynamic B200 validation (2026-09-17)

`tests/tcgen05_cp_shift_runtime.cu` executes the full runtime chain:

```
generic shared stores
  -> fence.proxy.async.shared::cta
  -> tcgen05.cp.cta_group::1.128x256b
  -> tcgen05.commit ... mbarrier::arrive::one
  -> mbarrier.try_wait.parity 0
  -> LDTM.x8 + tcgen05.wait::ld
```

One warp issues both `cp` and its tracking `commit`; the four warps then
read all 128 TMEM lanes.  Shared word `i` contains `0xc0000000|i`.  With the
no-swizzle descriptor `LBO=16 B, SBO=128 B`, lane `r` reads eight words starting
at source word `4*r`, so the first words observed across lanes 0..127 are
`src[0], src[4], ..., src[508]`.  This matches the descriptor's 16-byte row
step exactly and proves that one warp-scalar `UTCCP` populates all four
32-lane TMEM chunks.

The producer-side `fence.proxy.async.shared::cta` is necessary because UTCCP's
shared reads occur through the async proxy. The tracking commit belongs to the
same warp's preceding tcgen05 stream. Executing one U-path UTCBAR with all lanes
active still contributes one mbarrier arrival; only multiple UTCBAR issues (for
example from multiple warps) require a correspondingly larger init count.

### Interaction with the STTM write path

A sustained B200 probe places independent UTCCP producers in warps 0--3 and a
collective `STTM.x8` producer in warp 4.  Every UTCCP copies one 128x256-bit
tile (4096 bytes total, 1024 bytes into each TMEM chunk).  STTM writes either
the same columns 0--7 or disjoint columns 8--15 of chunk 0.  Both streams take
their own completion wait: UTCCP uses per-producer `UTCBAR`+mbarrier chains;
STTM uses `FENCE.VIEW.ASYNC.T`.

The streams were duration-matched: each UTCCP producer issues 512 copies, and
STTM issues 16384 x8 stores.  Steady-state clocks are:

| workload | UTCCP cycles | STTM cycles |
|---|---:|---:|
| four UTCCP producers only | 131277 | -- |
| STTM only | -- | 66580 |
| mixed, overlapping columns | 131299 | 66605 |
| mixed, disjoint columns | 131299 | 66605 |

Thus STTM changes by only 25 cycles (0.038%), and UTCCP by 22 cycles.  The
overlap/disjoint result is bit-for-bit identical.  This is not a weak workload:
STTM sustains 251.99 B/cycle in chunk 0, while the four-producer UTCCP stream
adds 63.90 B/cycle over the CTA, or 15.98 B/cycle to each of four chunks.  A
single shared 256 B/cycle chunk write port would therefore see about 267.97
B/cycle during overlap and should impose a readily visible delay; none occurs.

The best current model is that UTCCP reaches TMEM through an ingress/write path
separate from the ordinary 256 B/cycle STTM port (or, equivalently at this
resolution, through independently buffered array ports able to accept both in
parallel).  Concurrent writes to the same columns are accepted without an
address-lock serialization; their final data value is naturally a race and was
not used as the timing criterion.

Raw SASS clarified the producer-side limit. An entire naked UTCCP burst can be
issued directly on the warp-scalar U path; ELECT/PLOP is only the PTX
compatibility envelope. Burst lengths 4/8/16/32 take
641/1153/2177/4225 cycles, an exact steady slope of 128 cycles per copy, or 32
B/cycle per producer.  Two and four independent producers raise aggregate
throughput only to about 64 B/cycle, so the shared-memory/source side remains
the UTCCP limiter.  This is consistent with 128 B/cycle shared-array service in
active grant cycles plus visible inactive/arbitration cycles; it is not a TMEM
256 B/cycle write-port limit.

The raw probe also exposes an ordering hazard hidden by ordinary PTX lowering.
One execution group can interleave 16 UTCCP and 128 STTM.x8 operations per
batch.  At 32 batches, disjoint STTM columns (8--15) complete in 45249 cycles,
but overlapping columns (0--7) do not complete when `FENCE.VIEW.ASYNC.T` is
placed before the UTCCP `UTCBAR`/mbarrier completion sequence.  The overlapping
case completes in exactly 45249 cycles when those two completion actions are
reversed.  Smaller overlapping streams complete up through 16 batches (23393
cycles), so this is a deep-outstanding completion-order cycle rather than an
illegal instruction pairing.  The current interpretation is a same-execution-
group, same-address ordering dependency: either use disjoint columns or commit
and retire the UTCCP stream before waiting on the STTM fence.  This constraint
is separate from the physical-port result above, which used independent warps
and showed simultaneous backend progress.

### Multicast as a TMEM-ingress amplifier

The multicast modes allow source traffic and destination traffic to be varied
independently:

| PTX mode | shared bytes/op | total TMEM bytes/op | fanout |
|---|---:|---:|---:|
| `.128x256b` | 4096 | 4096 | 1x |
| `.64x128b.warpx2::01_23` / `::02_13` | 1024 | 2048 | 2x |
| `.32x128b.warpx4` | 512 | 2048 | 4x |

The raw-SASS probe accepts these as `--cp-shape`.  For an equal 512-operation
stream, the measured intervals are 33921 cycles for the base form, exactly
10399 cycles for either warpx2 mapping, and 9376 cycles for warpx4.  The exact
warpx2 equality confirms that `01_23` vs `02_13` changes the logical-warp
pairing but not the aggregate service cost.

For the proper equal-source-volume comparison, four producers collectively
read 8 MiB from shared memory in every row below.  Multicast changes only the
number of TMEM bytes generated from that source volume:

| form | ops/producer | cycles | shared B/cycle | TMEM B/cycle, CTA-wide | TMEM B/cycle/chunk |
|---|---:|---:|---:|---:|---:|
| base | 512 | 131277 | 63.90 | 63.90 | 15.98 |
| warpx2 | 2048 | 137367 | 61.07 | 122.13 | 30.53 |
| warpx4 | 4096 | 274583 | 30.55 | 122.20 | 30.55 |

Thus multicast successfully doubles the observable UTCCP TMEM pressure, but
warpx4 cannot double it again: both warpx2 and warpx4 converge on about 122
B/cycle CTA-wide, very close to a **128 B/cycle UTCCP ingress limit**, or 32
B/cycle for each of the four TMEM chunks.  In warpx4, this destination limit
feeds back and halves the attainable shared-source rate.  The limiter is
therefore no longer the shared array once multicast amplification reaches it.

#### Clean builtin-allocator rebaseline

A later direct-SASS probe removed the legacy allocator/control envelope and
gave every producer warp exactly one active issuing lane.  With no concurrent
STTM, four `.warpx4` producer warps issuing 512 operations each take about
17012 cycles; doubling to 1024 operations takes about 33388 cycles.  Since
each operation writes 512 bytes into every chunk, the length-difference slope
is **64.03 B/cycle/chunk** (about 256 B/cycle of logical destination traffic
CTA-wide).  Serial SB0 reuse, no explicit instruction scoreboard, and
three-scoreboard rotation all give the same interval.

Eight producer warps do not raise this ceiling: 1024 operations per warp take
about 66677 cycles, almost exactly twice the four-warp interval, for 62.9
B/cycle/chunk directly observed.  Thus standalone UTCCP `.warpx4` reaches only
about **64 B/cycle/chunk**, not the nominal 128 B/cycle/chunk suggested by its
fanout and active-cycle source width.  Additional producer occupancy cannot
fill the missing half.

This newer control supersedes the older 30.5 B/cycle/chunk standalone peak
estimate above.  It also means that the old mixed UTCCP+STTM result must be
repeated with the clean harness before interpreting non-slowdown as proof of
two physical TMEM array write ports: a shared array port with STTM priority
could instead preserve STTM throughput while throttling UTCCP.  Probe:
`tests/asm_construct/probe_sm100_utccp_warpx4_peak.py` (B200, 2026-09-18).

That clean mixed repeat uses UTCCP producer warps 0--3 and two `STTM.x8`
warps 4 and 8, which map to the same TMEM chunk.  Both streams contain their
own completion closure and timer.  Standalone and mixed results are:

| stream | standalone cycles | mixed cycles | payload rate in mixed |
|---|---:|---:|---:|
| UTCCP `.warpx4` (4x1024 ops) | 33415--33433 | 32925--32929 | 63.7 B/cycle/chunk |
| STTM.x8 (2x4096 ops) | 33515 CTA span | 34124 CTA span | 245.8 B/cycle/chunk |

Columns 0--7 (overlapping UTCCP) and columns 8--15 (disjoint) produce exactly
the same mixed per-warp intervals.  Consequently the old result was not an
STTM-priority artifact: UTCCP is not throttled and the two logical streams
sustain about **309.5 B/cycle/chunk** together.

This still does **not** require two complete SRAM write ports.  The narrower
and safer model is two independently limited ingress paths (about 256
B/cycle/chunk for STTM and 64 B/cycle/chunk for UTCCP) feeding a common banked
array sink whose tested acceptance is at least 310 B/cycle/chunk, plausibly a
rounder 512 B/cycle/chunk.  STTM's 256 B/cycle ceiling is therefore an ingress
limit, not a demonstrated TMEM-array write limit.  Probe:
`tests/asm_construct/probe_sm100_utccp_sttm_clean.py` (B200, 2026-09-18).

An all-chunk repeat assigns STTM warps 4--11 as two producers per chunk.
STTM-only reaches about 1001 B/cycle SM-wide; with the four UTCCP producers it
retains about 981 B/cycle while UTCCP retains about 255 B/cycle SM-wide.  The
combined logical rate is therefore about **1235 B/cycle per SM**, or 309
B/cycle/chunk on average.  There is no additional approximately-1-KiB/cycle
SM-wide merge bottleneck: the independently accepting paths extend at least
through the four chunk-local array entrances.

This stronger stream was repeated concurrently with a 251.99 B/cycle
`STTM.x8` stream in chunk 0.  STTM took 67296 cycles versus 66580 alone, and
overlapping versus disjoint columns were identical.  Three UTCCP producers on
other schedulers retain their standalone intervals; only producer warp 0,
which shares a scheduler with STTM warp 4, gains about 5.7k issue cycles.  That
fixed scheduler penalty is the same for warpx2 and warpx4 and is not a backend
bandwidth effect.  Most importantly, roughly 30.5 B/cycle/chunk of UTCCP
traffic coexists with roughly 250 B/cycle/chunk of STTM traffic.  This is
stronger evidence that the approximately 128 B/cycle multicast/copy ingress is
physically separate from STTM's approximately 256 B/cycle register-store port.

Probes: `tests/tcgen05_utccp_sttm_interaction.cu` and
`tests/asm_construct/probe_tcgen05_utccp_sttm_raw.py`.

## Cross-references
- `notes/sm100/instr/ldtm.md`, `sttm.md` — register↔TMEM moves; UTCCP is the
  shmem→TMEM staging path (no register round-trip).
- `notes/sm100/instr/utcatomsws.md` — TMEM allocator; UTCCP writes into the TMEM
  region it hands out.
- `UMMAB`/`gdesc` matrix descriptor — shared with the `UTC*MMA` ops (same 64-bit
  descriptor format).
- `$VQ_TC_1CTA`/`$VQ_TC_2CTA` — the tensor-core copy virtual queues, distinct
  from `$VQ_TMEM` (load/store) and `$VQ_SW_STATE` (allocator).

## Latency (sm100_latencies.txt)
`UTCCP` = part of `OP_TMA_TC` (line 214, with the UTMA* and other UTC* ops);
subtracted from `UDP_subset` and handled as a scoreboard-gated async op.
The read scoreboard protects source/descriptor lifetime; completion of the
actual shared→TMEM copy is tracked through `UTCBAR` or an implicitly pipelined
dependent MMA, not a fixed latency-table entry.

## Open questions
- Backend completion latency, issue throughput, and outstanding-copy capacity.
- Runtime meaning of the `.ONE` alternate (encoding-identical here).
- Whether `depth`/`cas` field names ([86]/[87]) carry any meaning beyond the
  fixed `.T`/`.S` role tags (they are pinned by the single-value `OnlyT`/`SONLY`
  enums).
