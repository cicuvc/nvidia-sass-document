# SM120 shared-memory allocator: capacity, quantum, and fragmentation

> **Silicon:** RTX 5090 (GB202, sm_120), 170 `SR_VIRTUALSMID` values.
> **Probe:** `tests/asm_construct/probe_usetshmsz_allocator.py`.

## Result

For a static user shared-memory declaration of `S` bytes, the scheduler charge
on this GPU is exactly

```
static_charge(S) = 0x400 + align_up(S, 0x80)
```

The per-SM allocation pool is **102400 bytes (100 KiB)** and the independent
CTA residency ceiling for the block-32 probe is **8 CTA/SM**.  The `0x400`
term is the known driver-reserved shared prefix (user shared starts at
`0x400`), not rounding noise.

Consequences:

- allocation quantum = **128 bytes**;
- ordinary rounding/internal fragmentation = **0--127 bytes per CTA**;
- fixed reserved cost = **1024 bytes per CTA** before `USETSHMSZ`;
- maximum static user declaration = **101376 bytes** (`0x18c00`), because
  `0x18c00 + 0x400 = 0x19000 = 102400`;
- a 102400-byte user declaration is rejected at launch.

## Static transition measurements

The probe parks every resident CTA, records `SR_VIRTUALSMID`, and binary
searches the last byte retaining each occupancy.  Every one of the 170 SMs
reported the same count.

| resident CTA/SM | largest user request | request + 1024 | total charge |
|---:|---:|---:|---:|
| 1 | 101376 | 102400 | 102400 |
| 2 | 50176 | 51200 | 102400 |
| 3 | 33024 | 34048 | 102144 |
| 4 | 24576 | 25600 | 102400 |
| 5 | 19456 | 20480 | 102400 |
| 6 | 16000 | 17024 | 102144 |
| 7 | 13568 | 14592 | 102144 |
| 8 | 11776 | 12800 | 102400 |

The 256-byte residuals in the 3/6/7 rows are the indivisibility remainder of
the 128-byte per-CTA quantum, not a second allocation granularity.

## USETSHMSZ changes the accounting basis

The immediate `T` is the **total shared window top**, including the reserved
prefix, rather than a user-byte count.  With `#pragma SHARED(0x1000)`, the
largest legal initial value is `T=0x1400`; `0x1480` traps 715.

After `USETSHMSZ T; USETSHMSZ.FLUSH`, the resident CTA's allocator charge is
`T` directly:

```
runtime_charge(T) = T                 # T must be 128-byte aligned
```

There is no additional 1 KiB term after the explicit resize.  This explains
runtime backfill exactly.  For a kernel with a static 32 KiB user declaration,
a newly admitted CTA initially costs `32768+1024=33792` bytes.  Existing CTAs
resized to `T` allow a final population `N` when

```
(N - 1) * T + 33792 <= 102400,       N <= 8
```

| runtime `T` | measured CTA/SM | formula |
|---:|---:|---:|
| 4096 | 8 | 8 |
| 8192 | 8 | 8 |
| 12288 | 6 | 6 |
| 16384 | 5 | 5 |
| 20480 | 4 | 4 |
| 24576 | 3 | 3 |

The initial static charge in the inequality matters: a queued CTA cannot run
its own resize until the scheduler first admits it at the larger static size.

## Fragmentation verdict

### Internal fragmentation: yes, bounded

Static requests round upward to 128 bytes, wasting at most 127 bytes per CTA.
The separate 1024-byte reserved prefix is real fixed overhead, not internal
fragmentation in the usual allocator sense.  An explicit runtime size is
already required to be a multiple of 128, so it introduces no additional
rounding loss.

### External fragmentation: none observable in same-kernel backfill

Start with three static-32-KiB CTAs per SM, then shrink each to 16 KiB.  A
simple contiguous-segment allocator would leave three separated tails, none
large enough to admit the next CTA at its 33792-byte initial charge.  It would
remain at 3 CTA/SM.  Silicon instead reaches **5 CTA/SM**, exactly the pooled
capacity prediction.  The full target sweep above follows the same formula.

Therefore the scheduler-visible allocator behaves as a **128-byte-granular
capacity pool**, or equivalently has remapping/compaction sufficient to hide
external fragmentation.  This does not prove the physical SRAM rows are
non-contiguous; it proves no external fragmentation is visible to CTA
admission in this experiment.

Cross-kernel hole-filling was also attempted with two nonblocking streams.
It is not a valid exact-boundary oracle: Hyper-Q sometimes delays the second
kernel wholesale even when capacity exists.  Those diagnostics remain behind
the probe's `--external` flag and are not used for the verdict above.

## Measurement discipline

- Run only on an otherwise idle GPU.  A training workload can consume SM
  slots and make a correct allocator state appear under-filled.
- Dynamic backfill can take longer than 100 ms.  The probe parks CTAs and
  observes for at least 1 second; the earlier three-sample/15-ms plateau test
  intermittently mistook the initial wave for the final occupancy.
- Require all 170 virtual SM IDs and uniform per-SM counts.  A GPU-wide total
  alone cannot distinguish allocator behavior from an uneven/busy device.
