# SM120 local-memory address → device backing VA

**Hardware:** RTX 5090 (GB202, sm_120)
**Status:** silicon-verified for aligned 32-bit `STL`/`LDL` words on sm120;
core transform independently reproduced on H20/sm90
**Probe:** `tests/asm_construct/probe_lmem_transform.py`

## Result

There are three different address values involved in a local-memory access:

1. `local_addr`: the 32-bit address consumed by `STL`/`LDL`.
2. `generic_local`: the generic-space address consumed by `LD`/`ST`, formed by
   adding the local generic-window base.
3. `backing_va`: the device-only global VA through which the same backing word
   can be accessed with `LDG`/`STG`.

For an aligned 32-bit local word in lane `l` of a warp:

```text
generic_local = SR_LWINLO + local_addr

backing_va = GETLMEMBASE(warp)
           + (local_addr - SR_LMEMHIOFF) * 32
           + lane_id * 4
```

Equivalently, when starting from a generic-local address:

```text
local_addr = generic_local - SR_LWINLO

backing_va = GETLMEMBASE(warp)
           + (generic_local - SR_LWINLO - SR_LMEMHIOFF) * 32
           + lane_id * 4
```

`GETLMEMBASE` is **warp-uniform**, but not CTA-uniform or SM-uniform. Each warp
must use its own returned value unless the hardware resident-warp-slot mapping
is also known.

## Concrete values from the probe

The tested hand-assembled kernel reported:

| Value | Result | Meaning |
|---|---:|---|
| `c[0x0][0x37c]` | `0x00fffdc0` | current stack-frame/local address |
| `c[0x0][0x2f8]` | `0x03000000` | `SR_LWINLO`, generic-local window base |
| `SR_LWINLO` | `0x03000000` | agrees with `c[0x0][0x2f8]` |
| `SR_LWINSZ` | `0x01000000` | local-window size / high-local end |
| `SR_LMEMLOSZ` | `0x00000000` | no low-local segment in this launch |
| `SR_LMEMHIOFF` | `0x00fff9c0` | high-local segment lower bound |

Thus:

```text
generic_local = 0x03000000 + 0x00fffdc0
              = 0x03fffdc0

frame_delta = 0x00fffdc0 - 0x00fff9c0
            = 0x400

backing offset before lane selection = 0x400 * 32
                                     = 0x8000
```

For a warp whose `GETLMEMBASE` is `0x00003fffe6c00000`:

```text
lane 0 backing VA  = 0x00003fffe6c08000
lane 1 backing VA  = 0x00003fffe6c08004
...
lane 31 backing VA = 0x00003fffe6c0807c
```

The probe performs `STL [frame], magic(lane)`, local-cache writeback, then an
`LDG` from these derived addresses. All 32 lanes match. A second kernel reading
the same derived addresses after writer completion also matches 32/32.

## Why the multiplier is 32

Local words are warp-interleaved in the backing aperture:

```text
local_addr + 0x0 → one 128-byte segment containing lanes 0..31
local_addr + 0x4 → the next 128-byte segment
```

Therefore:

```text
local word stride = 4 bytes * 32 lanes = 0x80 backing bytes
lane stride       = 4 bytes
```

The scanner wrote 144 local words per lane at offsets `0x0..0x23c`. For one
warp, the first and last matching segments were:

```text
first = GET + 0x08000
last  = GET + 0x0c780

last - first = 0x4780 = 143 * 0x80
```

This independently confirms the 128-byte backing stride for successive local
words.

The verified formula is for aligned U32 words. The natural byte-level
generalization is likely:

```text
GET + ((local_addr - HIOFF) & ~3) * 32
    + lane_id * 4
    + ((local_addr - HIOFF) & 3)
```

but U8/U16 and unaligned accesses have not yet been directly probed.

## Multiple warps in one CTA

Test: one CTA, 256 threads (8 warps). The formula matched **256/256** threads.

Define the active high-local span per thread:

```text
thread_local_span = SR_LWINSZ - SR_LMEMHIOFF
                  = 0x01000000 - 0x00fff9c0
                  = 0x640 bytes
```

The observed `GETLMEMBASE` stride between adjacent warps was:

```text
warp_stride = thread_local_span * 32
            = 0x640 * 32
            = 0xc800
```

Example:

| CTA warp | `GETLMEMBASE` | lane-0 VA for `local_addr=frame` |
|---:|---:|---:|
| 0 | `0x3fffe6c00000` | `0x3fffe6c08000` |
| 1 | `0x3fffe6c0c800` | `0x3fffe6c14800` |
| 2 | `0x3fffe6c19000` | `0x3fffe6c21000` |
| 3 | `0x3fffe6c25800` | `0x3fffe6c2d800` |
| 4 | `0x3fffe6c32000` | `0x3fffe6c3a000` |
| 5 | `0x3fffe6c3e800` | `0x3fffe6c46800` |
| 6 | `0x3fffe6c4b000` | `0x3fffe6c53000` |
| 7 | `0x3fffe6c57800` | `0x3fffe6c5f800` |

Within this CTA, if only warp 0's base is retained, the equivalent formula is:

```text
backing_va = GETLMEMBASE(warp0)
           + warp_id * thread_local_span * 32
           + (local_addr - SR_LMEMHIOFF) * 32
           + lane_id * 4
```

This contiguous logical-warp assignment was observed for this launch, but the
safer form remains the per-warp `GETLMEMBASE` formula.

## Multiple CTAs and SM-local allocation

Two tests were run:

- 16 CTAs × 256 threads: **4096/4096** derived-VA loads matched.
- 400 CTAs × 256 threads: **102400/102400** matched, covering all 170 virtual
  SM IDs reported by `SR_VIRTUALSMID`.

The per-SM local aperture stride was:

```text
SM thread-slot capacity = 1536

sm_stride = 1536 * thread_local_span
          = 1536 * 0x640
          = 0x258000
```

For the first CTA placed on each SM:

```text
GETLMEMBASE(warp0, virtual_smid=s)
    = 0x3fffe6c00000 + s * 0x258000
```

The first few measured values were:

| `SR_VIRTUALSMID` | warp-0 `GETLMEMBASE` |
|---:|---:|
| 0 | `0x3fffe6c00000` |
| 1 | `0x3fffe6e58000` |
| 2 | `0x3fffe70b0000` |
| 3 | `0x3fffe7308000` |
| 15 | `0x3fffe8f28000` |

The 400-CTA run placed three observed CTAs on many SMs. For a 256-thread CTA,
their warp-0 bases within one SM occurred at:

```text
CTA resident slot 0: sm_base + 0x00000
CTA resident slot 1: sm_base + 0x70800 = sm_base +  9 * 0xc800
CTA resident slot 2: sm_base + 0xe1000 = sm_base + 18 * 0xc800
```

A 256-thread CTA contains 8 program warps, but adjacent resident CTA bases were
9 warp strides apart. This suggests one extra local-memory warp slot is reserved
between these CTA allocations. The reason for that extra slot is not yet known.

### Practical rule

The data are consistent with:

```text
GETLMEMBASE(warp)
    ≈ launch_aperture_base
    + virtual_smid * sm_stride
    + resident_warp_slot * warp_stride
```

The `virtual_smid` term and the measured strides are verified; the complete
resident-slot allocation policy is not. Resident slots are scheduling state,
not a simple function of `CTAID.X`. Do not reconstruct a warp's base from CTAID.
Execute `GETLMEMBASE` in each warp instead.

## H20 / sm90 replication

The same hand-assembled probes were run independently on an NVIDIA H20
(compute capability 9.0, driver 580.65.06) with `ASSEMBLER_ARCH=sm90`. The
Hopper launch ABI uses `c[0x0][0x28]` for the stack/local address and
`c[0x0][0x20]` for the generic local-window base; their measured values and
the special-register values happened to equal the sm120 launch above:

```text
local_addr    = 0x00fffdc0
SR_LWINLO     = 0x03000000
SR_LWINSZ     = 0x01000000
SR_LMEMHIOFF  = 0x00fff9c0
span/thread   = 0x640
```

The same transform matched 32/32 lanes in one warp, 256/256 threads in an
eight-warp CTA, and 4096/4096 threads across 16 CTAs. Adjacent warp bases were
again `0xc800` apart.

H20's virtual-SM aperture stride was larger because it represents 2048 rather
than 1536 thread slots:

```text
H20 sm_stride  = 2048 * 0x640 = 0x320000
GB202 sm_stride = 1536 * 0x640 = 0x258000
```

A 400-CTA run covered all 78 H20 virtual SM IDs. The four initially resident
256-thread CTA allocations on an SM started at 0, 9, 18 and 27 warp strides,
the same one-extra-warp spacing seen on GB202.

There is an important Hopper cache caveat. Once those four slots were reused,
an `LDG` through the global backing alias could see an old L1 line from the
previous occupant: without invalidation only 80000/102400 lane checks matched.
Adding `CCTL.IVALL` after local writeback/barrier and before the verifying
`LDG` yielded 102400/102400. The transform itself did not change.

H20 also faulted with error 700 when a second kernel tried to dereference a
default `GETLMEMBASE` saved by the completed first kernel. Treat a default
backing base as current launch/resident-slot state, not a persistent pointer.
The earlier sm120 second-kernel read happened to succeed and should not be
relied upon as a portable lifetime guarantee.

## SETLMEMBASE changes LDL/STL backing selection

`SETLMEMBASE` is not merely a software-visible value that round-trips through
`GETLMEMBASE`; it directly changes the backing base used by subsequent
`LDL`/`STL` operations in the executing warp.

The single-warp probe allocated an ordinary 1 MiB device buffer `B` and ran the
following sequence:

```text
A = GETLMEMBASE()                         // driver-selected original base
STL [frame], old_magic
CCTLL.WB [frame]; MEMBAR.ALL.SYS

SETLMEMBASE(B)
B_check = GETLMEMBASE()                   // exactly B
STL [frame], new_magic
CCTLL.WB [frame]; MEMBAR.ALL.SYS

LDG [B + (frame-HIOFF)*32 + lane*4]       // new_magic
LDG [A + (frame-HIOFF)*32 + lane*4]       // old_magic
LDL [frame]                               // new_magic

SETLMEMBASE(A)
LDL [frame]                               // old_magic

SETLMEMBASE(B)
LDL [frame]                               // new_magic

SETLMEMBASE(A)                            // restore before EXIT
```

All checks matched **32/32** lanes:

| Check | Result |
|---|---:|
| GET immediately after SET returns `B` | 32/32 |
| STL under `B` is visible through the derived `B` backing VA | 32/32 |
| original `A` backing retains `old_magic` | 32/32 |
| LDL while `B` is selected reads `new_magic` | 32/32 |
| host read of the ordinary allocation at `B+0x8000` sees `new_magic` | 32/32 |
| restoring `A` makes LDL read `old_magic` again | 32/32 |
| reselecting `B` makes LDL read `new_magic` again | 32/32 |

For the tested frame, `(frame-HIOFF)*32 = 0x8000`, so redirecting to an
ordinary allocation made the warp's lane segment directly host-visible at
`B+0x8000..B+0x807f` after `CCTLL.WB` and the system memory barrier.

This establishes that `SETLMEMBASE` switches a warp-local backing-aperture base
while leaving the local address (`frame`), `LMEMHIOFF`, and lane-interleave
transform unchanged. The supplied allocation must cover every derived backing
offset the warp may access. Restoring the original base before returning is the
safe practice.

### Lane-varying SET operand: lowest active lane wins

`tests/asm_construct/probe_setlmembase_lanes.py` supplied a different valid
1 MiB-spaced base in every lane of one warp. The result is not per-lane state:
SET selects the operand belonging to the lowest-numbered lane in its current
execution mask and installs that one value warp-wide.

With all lanes active, forward lane→slot mapping selected lane 0's slot 0;
reversing the mapping selected lane 0's slot 31. Predicating SET to lanes
`k..31` for `k = 1, 7, 16, 31` selected physical lane `k` in every case. Both
GET readbacks were uniform, exactly one candidate arena slot received the
complete 32-lane backing segment, and LDL matched 32/32. Repeats and 0–64
stall-8 NOPs between GET readbacks did not change the election.

In compact form:

```text
leader = ffs(active_mask)
GETLMEMBASE(after SET) = SET_source[leader]    // uniform across the warp
```

This experiment had two GETs between SET and the first local access, so it
does not remove the separate settling-latency requirement for an LDL/STL
placed immediately after SET.

## Cubin EIATTRs controlling a ptxas spill frame

Test source: `tests/spill_eiattr_probe.cu`. It keeps 96 FP32 values live across
a runtime loop, then uses `--maxrregcount` to turn register pressure into real
ptxas-generated `LDL`/`STL` spills. It does not declare an explicit local array.

Compilation matrix:

```bash
for r in 255 128 96 64 48 32; do
    /usr/local/cuda/bin/nvcc -arch=sm_120 -O3 \
        --maxrregcount=$r -Xptxas=-v -cubin \
        tests/spill_eiattr_probe.cu -o /tmp/spill-r$r.cubin
done
```

Results:

| maxrregcount | used regs | ptxas frame | spill stores | spill loads | `EIATTR_FRAME_SIZE` | `EIATTR_MIN_STACK_SIZE` | runtime `localSizeBytes` |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 255 | 196 | 0 | 0 | 0 | `0x0` | `0x0` | 0 |
| 128 | 128 | 0 | 0 | 0 | `0x0` | `0x0` | 0 |
| 96 | 96 | 56 | 76 | 80 | `0x38` | `0x38` | 56 |
| 64 | 64 | 408 | 632 | 636 | `0x198` | `0x198` | 408 |
| 48 | 48 | 432 | 824 | 828 | `0x1b0` | `0x1b0` | 432 |
| 32 | 32 | 472 | 1116 | 1120 | `0x1d8` | `0x1d8` | 472 |

Three independent views agree exactly:

1. ptxas's `N bytes stack frame` report;
2. `cuobjdump --dump-resource-usage` field `STACK:N`;
3. `cudaFuncGetAttributes(...).localSizeBytes == N`.

`cuobjdump` reports `LOCAL:0` for every row, including spilling kernels. In this
output, ptxas-generated register spill storage is accounted under `STACK`, not
the `LOCAL` resource column.

### Raw `.nv.info` records

For maxrregcount=64 / frame size `0x198`:

```text
04 2f 08 00  08 00 00 00  40 00 00 00  // EIATTR_REGCOUNT: sym=8, 64
04 11 08 00  08 00 00 00  98 01 00 00  // EIATTR_FRAME_SIZE: sym=8, 0x198
04 12 08 00  08 00 00 00  98 01 00 00  // EIATTR_MIN_STACK_SIZE: sym=8, 0x198
```

The records use an 8-byte SVAL payload `{function_symbol, value}`:

| Attribute | ID | Observed role |
|---|---:|---|
| `EIATTR_REGCOUNT` | `0x2f` | registers assigned to the function |
| `EIATTR_FRAME_SIZE` | `0x11` | exact per-thread frame addressed by R1-relative LDL/STL |
| `EIATTR_MIN_STACK_SIZE` | `0x12` | minimum per-thread stack reservation; equals frame for this leaf kernel |
| `EIATTR_MAX_STACK_SIZE` | `0x23` | not emitted by ptxas for these simple leaf entry kernels |

The repository assembler currently emits FRAME/MIN/MAX records with zero values;
ptxas's leaf cubin emits only REGCOUNT, FRAME and MIN in device-wide `.nv.info`.

### SASS cross-check

The frame value directly controls the R1 prologue adjustment:

```text
maxrreg=96: IADD R1, R1, -0x38
maxrreg=64: IADD R1, R1, -0x198
maxrreg=48: IADD R1, R1, -0x1b0
maxrreg=32: IADD R1, R1, -0x1d8
```

For every spilling cubin:

```text
largest LDL/STL offset + access width <= frame_size
```

| maxrregcount | frame | maximum spill offset | used end | tail padding |
|---:|---:|---:|---:|---:|
| 96 | `0x38` | `0x30` | `0x34` | 4 B |
| 64 | `0x198` | `0x194` | `0x198` | 0 B |
| 48 | `0x1b0` | `0x1ac` | `0x1b0` | 0 B |
| 32 | `0x1d8` | `0x1d0` | `0x1d4` | 4 B |

All highest-address accesses in this matrix are 32-bit. The 96- and
32-register frames include four bytes of tail padding, consistent with the
8-byte-aligned frame sizes.

Summing the operand width of every static LDL or STL instruction also exactly
reproduces ptxas's `spill loads` and `spill stores` byte counts. These traffic
counts are not allocation sizes: repeated accesses to the same frame slot count
multiple times, while the EIATTR frame is the unique R1-relative address range.

For this leaf-kernel experiment, `EIATTR_FRAME_SIZE` together with
`EIATTR_MIN_STACK_SIZE` is therefore the cubin metadata that tells the loader
how much per-thread local stack/spill storage the function requires. How this
requested size is rounded and combined with ABI reserve space to program
`SR_LMEMHIOFF` remains to be measured directly.

## The misleading `(generic_local << 20)` candidate

The initially observed values looked suggestive:

```text
generic_local << 20 = 0x00003fffdc000000
GETLMEMBASE          = 0x00003fffe6c00000
```

They differ by only `0x0ac00000`, but the shifted address itself faults with
`CUDA_ERROR_ILLEGAL_ADDRESS`. It is not the backing VA transform.

Device-side probing found that `GETLMEMBASE` is the beginning of a readable
device-only aperture for the current allocation. `GET-0x10000` faults, while
`GET` is readable. Host `cuMemcpyDtoH` from the GET address returns
`CUDA_ERROR_INVALID_VALUE`; access must go through device instructions.

## Failed candidates that motivated the scan

The following addresses were valid or probeable but did not alias the STL word:

```text
GET + local_addr
GET + generic_local
GET + (0x1000000 - frame) * 32 + lane*4
GET + (0x1000000 - frame) * 1536 + lane*4
(generic_local << 20) + lane*4       // faults
```

The missing quantity was `SR_LMEMHIOFF`: GET is the backing base corresponding
to the current warp's `LMEMHIOFF`, not to local address zero or the top of the
local window.

## Reproduction

```bash
python3 tests/asm_construct/probe_lmem_transform.py
```

Important subprobes in the script:

- `build()` — direct single-warp formula and generic-local cross-check.
- `build_eviction_probe()` — scans the first 16 MiB of the GET aperture and
  derives the word/lane layout.
- `build_multiwarp_verify()` — one CTA × 8 warps.
- `build_multicta_verify()` / `run_multicta_verify()` — multi-CTA and
  `SR_VIRTUALSMID` verification; `run_multicta_verify(400, 256)` is the stress
  configuration.
- `probe_setlmembase_lanes.py` — lane-varying source election and predicated
  partial-warp SET behavior.

## Open questions

- Verify U8/U16, unaligned, U64 and U128 backing layouts directly.
- Explain the extra one-warp stride between 256-thread resident CTAs.
- Sweep CTA sizes and resource limits to recover the full resident-slot
  allocation rule.
- Determine how `LMEMLOSZ != 0` splits low-local and high-local backing regions.
- Measure `SR_LMEMHIOFF` inside ptxas kernels across the spill-frame matrix to
  recover loader rounding and ABI reserve overhead.
- Re-test on sm_90 hardware; all results here are sm_120 silicon only.
- Test competing SETs issued by separate divergent SIMT groups before
  reconvergence; partial-mask election is known, but group ordering is not.

## SETLMEMBASE settling latency & RZ+imm24 reach (sassdbg probe_mwarp.py)

- **SETLMEMBASE does not take effect immediately.**  Local accesses within the
  first ~10s of cycles after it are flaky: LDLs can observe a lane-split view
  (lane 0 on the new LMB, other lanes still on the old one) or fault 700 when
  the target address was never device-written.  An unbounded delay (a spin
  gate) makes it deterministic; a 4×stall-15 NOP pad (~60 cycles) was *not*
  reliably enough.  Rule: after SETLMEMBASE, never let the first local access
  be time-critical or a read of host-written data.
- **Device-side STL→LDL round-trips at LMEMHIOFF+0x00..0x1B are rock solid**
  once settled (the M3v3 breakpoint handler spills/restores six registers +
  PR this way, across multi-millisecond host-observed parks, two warps
  concurrently on their own LMBs).
- **`STL/LDL [RZ+uImm24]` reach only the low 0x640 dwords of the window**:
  LMEMHIOFF+0x640 = 0x1000000 crosses 2^24 and the assembler silently
  truncates the immediate (observed: 0x10009c0 encoded as 0x0009c0 → 700).
  Deeper frames need register-based local addressing (`STL [R14]`).
