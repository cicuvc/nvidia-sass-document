# CUtensorMap descriptor bit layout (tiled + im2col)

The CUtensorMap is the 128-byte opaque object consumed by the TMA instructions
(`UTMALDG`/`UTMASTG`/`UTMAREGD`/`UBLKRED` and `cp.async.bulk.tensor`). The CUDA
driver API documents the creation calls
([cuTensorMapEncodeTiled / cuTensorMapEncodeIm2col](https://docs.nvidia.com/cuda/cuda-driver-api/group__CUDA__TENSOR__MEMORY.html))
but explicitly leaves the bit layout private ("a tensor map object is an opaque
value").  This note reconstructs the layout empirically by differential probing:
encode descriptors with the driver on a live GPU, vary one parameter at a time,
and diff the 32 little-endian words.  Every field below was cross-checked by
re-encoding descriptors from the field table and comparing byte-for-byte with
the driver output (all probed cases match; `tools/tma_helper.py` is the
bit-accurate forward constructor).

Environment: RTX 5090 (sm_120) / driver 580.65 / CUDA 13.0 (nvcc 13.0).

## Tiled-mode layout (cuTensorMapEncodeTiled)

All fields little-endian.  Words w0..w31 (each 4 bytes):

| word | contents |
|---|---|
| w0..w1 | `globalAddress` (64-bit; w0 = low 32 bits) |
| w2 | flags (bit table below) |
| w3..w7 | `globalStrides[i] / 16` for i = 0..rank-2, one 32-bit word each |
| w8..w12 | `globalDim[i] - 1`, one 32-bit word each (w12 used by rank 5) |
| w13 | `[15:0]` elementStrides[i]-1 packed 3 bits each (i = 0..rank-1, low = dim 0); `[23:16]` reserved (0); `[31:24]` boxDim[0]-1 |
| w14 | boxDim[1..rank-1]-1 in bytes 0..rank-2 (8 bits each) |
| w15 | reserved (0) |
| w16 | tile size in bytes (see below) |
| w17 | reserved (0) |
| w18 | swizzle info: `0x10` for SWIZZLE_NONE; swizzle 1/2/3 → `0x100`/`0x200`/`0x400`; swizzle 4/5/6 → `0x400` |
| w19..w31 | reserved (0) |

### w2 flag bits

| bits | field |
|---|---|
| [3:0] | reserved (0); bit0 = 1 marks im2col mode |
| [6:4] | tensorRank - 1 (3 bits, rank 1..5) |
| [10:7] | element-type **hardware code** (see table below — not the API enum) |
| [12:11] | interleave (0/1/2) |
| [14:13] | `min(swizzle, 3)` |
| [15] | float-OOB-fill flag |
| [16] | TFLOAT32 flag (set with type code 7 or 8) |
| [18:17] | L2 promotion (1..3) |
| [20:19] | `max(swizzle - 3, 0)` |
| [21] | "wide" flag (see below) |

The swizzle value is split into two sub-fields: `[14:13] = min(sw,3)` and
`[20:19] = max(sw-3,0)`.  For swizzle 4..6 both sub-fields are non-zero
(`[14:13] = 3`).

### Element-type code table

The 4-bit field at w2 `[10:7]` is **not** the `CUtensorMapDataType` enum value.
Empirically UINT8..FLOAT32 map 1:1 (0..7), then the order diverges:

| API enum | name | code | API enum | name | code |
|---|---|---|---|---|---|
| 0 | UINT8 | 0 | 8 | FLOAT64 | **9** |
| 1 | UINT16 | 1 | 9 | BFLOAT16 | **10** |
| 2 | UINT32 | 2 | 10 | FLOAT32_FTZ | **8** |
| 3 | INT32 | 3 | 11 | TFLOAT32 | **7 + bit16** |
| 4 | UINT64 | 4 | 12 | TFLOAT32_FTZ | **8 + bit16** |
| 5 | INT64 | 5 | 13 | 16U4_ALIGN8B | 11 |
| 6 | FLOAT16 | 6 | 14 | 16U4_ALIGN16B | 12 |
| 7 | FLOAT32 | 7 | 15 | 16U6_ALIGN16B | 13 |

### "Wide" flag (w2 bit 21)

bit21 = 1 when the tensor needs the extended descriptor interpretation:

- non-interleaved: total element count `Π globalDim[i] ≥ 65536`;
- interleaved: interleaved tile bytes (w16) `≥ 65536`.

This is why the per-rank/position thresholds look strange in isolation — for a
fixed baseline shape the first dimension that pushes the total past 2^16 flips
the bit (e.g. rank 2: dim ≥ 4096 with the other dim = 16; rank 4 dim0: ≥ 128;
rank 5: any dim ≥ 16).  rank-5 descriptors with fewer than 65536 total elements
(e.g. 8^5 = 32768) keep bit21 = 0.

### w16 tile size

- non-interleaved: `elementSize × Π floor(boxDim[i] / elementStrides[i])`
  (the driver stores `floor`, not the documented `ceil`; e.g. box 16×8 f16 with
  elementStrides [1,3] → 16 × floor(8/3) × 2 = 64 bytes);
- interleaved 16B/32B: `Π boxDim[i] × 16` resp. `× 32` (the tile covers the
  whole interleave span per element group);
- packed U4/U6 dtypes (13..15): the driver stores **0**.

Note the API docs say elementStrides[0] is ignored for INTERLEAVE_NONE, but the
descriptor still encodes it (w13 `[2:0]`) and w16 is computed from it.

## Im2col-mode layout (cuTensorMapEncodeIm2col)

Same envelope; only the meaning of a few words changes.  tensorRank must be 3..5.

| word | contents |
|---|---|
| w2 | same flags, bit0 = 1 (im2col marker) |
| w3..w7 | `globalStrides / 16`, rank-1 words (driver canonical order) |
| w8..w12 | `globalDim[i] - 1` |
| w13 | `[15:0]` elementStrides-1 3-bit packed; `[31:24]` `channelsPerPixel - 1` |
| w14 | pixelBox corners, rank-dependent signed precision (below) |
| w15 | `pixelsPerColumn - 1` |
| w16 | `channelsPerPixel × pixelsPerColumn × elementSize` (interleave modifies this; see open questions) |
| w18 | swizzle info, same as tiled |

Corner packing in w14:

| rank | layout |
|---|---|
| 3 | lower[15:0], upper[31:16] (16-bit signed each) |
| 4 | lo0[7:0], lo1[15:8], hi0[23:16], hi1[31:24] (8-bit signed each) |
| 5 | lo0[4:0], lo1[9:5], lo2[14:10], hi0[20:16], hi1[25:21], hi2[30:26] (5-bit signed each) |

The wide flag follows the same total-element rule as tiled
(e.g. rank-4 im2col with dims [16,16,16,16] = 65536 elements → bit21 = 1;
[16,8,8,8] = 8192 → 0).

## Quirks and driver behavior

- `globalStrides` are stored as `/16` in 32-bit words, so strides `≥ 2^36` wrap
  silently (probed: stride = 2^36 → w3 = 0; no wide flag, no error).  The API
  advertises `< 2^40`, but the descriptor field cannot represent that without
  additional bits we did not find.
- w1 (high address word) was always 0 in our probes: the test device exposes
  only 4 GB of memory, so all `cuMemAlloc` pointers stay below 2^32.  The
  64-bit address split (w0 low / w1 high) and
  `cuTensorMapReplaceAddress` writing w0 are confirmed; the high word update
  path is unverified.
- boxDim[0]-1 and boxDim[1..4]-1 live in 8-bit fields (w13 byte 3, w14), so
  boxDim[0] ≤ 256 and boxDim[i≥1] ≤ 256 (driver rejects box0 = 512 for u8).
- `cuTensorMapEncodeIm2col` reorders multi-dim strides internally; pass them
  descending to match the stored order.

## Verified encodings (examples)

Baseline: f16, rank 2, dims [16,16], stride 32, box [16,8], elemStrides [1,1]:

```
w0=0be00000 w1=00000000 w2=00000310 w3=00000002
w8=0000000f w9=0000000f w13=0f000000 w14=00000007
w16=00000100 w18=00000010
```

dtype sweep (rank 2, same shape): u8 → w2 `00000010`, u32 → `00000110`,
f64 → `00000490`, bf16 → `00000510`, tf32 → `00010390`,
16U4_ALIGN8B → `00000590` (box 128×8, dims 256×16, w16 = 0).
Swizzle sweep: 32B → `00002310` + w18 `00000100`; 64B → `00004310` + `00000200`;
128B → `00006310` + `00000400`; 128B_ATOM_32B → `00086310` + `00000400`.
Wide: dim0 = 4096 → `00200310`.

## Tooling

- `tools/tma_helper.py` — bit-accurate forward constructor for tiled and im2col
  descriptors (pure ctypes, no driver call); verified byte-for-byte against
  cuTensorMapEncode* and exercised end-to-end on the GPU by
  `tests/asm_construct/test_tmap_helper.py` (every dtype, rank 1..5,
  swizzle 0..6, interleave, promotion, OOB, element strides and im2col corners,
  plus a UTMALDG load driven by a helper-built descriptor).
- Probe methodology: driver bindings via `assembler.runner._cuda`, one-parameter
  diffs, all results re-decoded by the field model (71 tiled + im2col cases,
  0 mismatches).

## Open questions

- w18 semantics beyond the observed value table (0x10 / 0x100 / 0x200 / 0x400)
  — likely a swizzle pattern/row descriptor, but no deeper meaning extracted.
- w16 for im2col + interleave: one sample (f16, il=16B, cpp 8, ppc 8) stored
  `0x400` (1024) instead of `cpp×ppc×elem` (128); the multiplier rule is
  unverified.
- stride fields ≥ 2^36: where (if anywhere) the upper bits live.
- w1 high-address update via cuTensorMapReplaceAddress (needs a >4 GB device).
