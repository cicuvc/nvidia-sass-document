# tcgen05 matrix descriptors — `gdesc` (shared-mem) and `idesc` (instruction)

Reference for the two descriptor operands every `UTC*MMA` (and `UTCCP`) carries.
Both are documented in PTX ISA 9.3 §9.7.17.4 (`~/cs/project/documented-ptx/
09.7.17-...`). This note transcribes the bit layouts and ties them to the SASS
operands we decoded (`utchmma.md`, `utccp.md`).

Three descriptor kinds exist; the zero-column mask (§9.7.17.4.3) is covered in
`tcgen05_microarch_speculation.md` (WS convolution). Here: the **shared-memory
matrix descriptor** (`gdesc`, 64-bit) and the **instruction descriptor** (`idesc`,
32-bit).

## SASS operand mapping (recap)
In `UTCHMMA`/`UTCCP` (see `utchmma.md`):
- `gdesc[URa]` / `gdesc[URb]` — a **64-bit** shared-memory matrix descriptor in a
  uniform-register pair (A and/or B operand). `ISRC_A/B_SIZE = 64`.
- `idesc[URh]` — a **32-bit** instruction descriptor in a uniform register.
- These are *register values*, not immediates — software builds them (often with
  `UMOV`/`ULOP3`/`ULEA` sequences or loads them) before the MMA.

---

## 1. Shared-memory descriptor (`gdesc`) — 64-bit (PTX Table 43)
Describes an A or B multiplicand matrix's location and layout in shared memory.

| Bits | Size | Field | Meaning |
|------|-----:|-------|---------|
| 0–13 | 14 | matrix start address | `matrix-descriptor-encode(addr)` |
| 14–15 | 2 | reserved | must be 0 |
| 16–29 | 14 | leading-dim byte offset (rel) **or** byte address (abs) | encoded |
| 30–31 | 2 | reserved | must be 0 |
| 32–45 | 14 | stride-dim byte offset | encoded |
| 46–48 | 3 | fixed | `0b001` |
| 49–51 | 3 | matrix base offset | swizzle phase (see below) |
| 52 | 1 | **leading-dim stride mode** | 0 = byte-offset relative, 1 = byte-address absolute (sm_103a) |
| 53–60 | 8 | fixed | `0x00` |
| 61–63 | 3 | **swizzle mode** | 0 none / 1 128B-with-32B-atomic / 2 128B / 4 64B / 6 32B (3,5,7 invalid) |

Encoding helper: `matrix-descriptor-encode(x) = (x & 0x3FFFF) >> 4` — i.e. the
three address/offset fields hold **bits [17:4]** of a byte value (so all three
must be **16-byte aligned**; the low 4 bits are implicit 0).

**Swizzle base offset** (bits 49–51): 0 when the swizzle repeating pattern starts
on its natural boundary (128B→1024B, 64B→512B, 32B→256B); otherwise
`base = (pattern_start_addr >> 7) & 0x7`.

**Leading-dim modes** (bit 52):
- *Relative offset* (0): leading-dim stride = byte offset between columns
  (K-major: stride of the 8×2 128-bit-normalized tile; swizzled: assumed 1;
  MN-major: stride between 8-column groups / swizzle-row groups).
- *Absolute address* (1, sm_103a): used when K-dim = 48B would overflow the 128B
  shared-memory boundary — the leading dim points at the second data chunk.
  Restrictions: 128B swizzle only, K-major only (transpose bits must be 0), base
  offset 0.

This is the direct descendant of Hopper's wgmma "GMMA descriptor" (same idea:
start address + leading/stride offsets + swizzle), now used by `UTCCP` (source
matrix) and `UTC*MMA` (A/B operands).

---

## 2. Instruction descriptor (`idesc`) — 32-bit
Carries the shapes, element types, and per-matrix flags — i.e. the **"what kind
of MMA"** info that the SASS mnemonic does *not* encode (recall all of
`.kind::f16/tf32/f8f6f4/i8` map to the same `UTCHMMA` opcode; the type lives
here). The layout is kind-dependent — three tables.

### 2a. Base format — `.kind::tf32/f16/f8f6f4/i8` (PTX Table 45)
| Bits | Size | Field | Values |
|------|-----:|-------|--------|
| 0–1 | 2 | sparsity selector (if sparse) | 0–3 |
| 2 | 1 | **sparsity** | dense=0 / sparse=1 |
| 3 | 1 | saturate (int only) | i8: no-sat=0 / sat=1; else 0 |
| 4–5 | 2 | **dtype** (D type) | tf32→F32=1; f16→F16=0/F32=1; i8→S32=2 |
| 6 | 1 | reserved | 0 |
| 7–9 | 3 | **atype** (A type) | tf32:TF32=2; f16:F16=0/BF16=1; f8f6f4:E4M3=0/E5M2=1/E2M3=3/E3M2=4/E2M1=5; i8:U8=0/S8=1 |
| 10–12 | 3 | **btype** (B type) | (same encoding as atype) |
| 13 | 1 | **negate A** | 0/1 (fp only; i8 no-negate) |
| 14 | 1 | **negate B** | 0/1 (fp only) |
| 15 | 1 | **transpose A** | 0/1 |
| 16 | 1 | **transpose B** | 0/1 |
| 17–22 | 6 | **N** (B dimension) | `N >> 3` (3 LSBs implicit) |
| 23 | 1 | reserved | 0 |
| 24–28 | 5 | **M** (A dimension) | `M >> 4` (4 LSBs implicit) |
| 29 | 1 | reserved | 0 |
| 30–31 | 2 | max B-reuse shift (`.ws`) | none=0 / 8=1 / 16=2 / 32=3 |

Key takeaways:
- **M/N live here, not in the opcode.** `N = idesc[17:22] << 3` (step 8),
  `M = idesc[24:28] << 4` (step 16). This is why the SASS `UTCHMMA` mnemonic has
  no shape suffix — the geometry is a runtime descriptor value.
- **transpose/negate** (bits 13–16) are the "Transpose/Negate A/B" ops from the
  chapter's Table 54 (tf32/f16/f8f6f4 support both; i8 transpose-yes/negate-no).
- Bits 30–31 (**max B-reuse shift**) only apply to `.ws` — the weight-stationary
  collector's B-reuse window, tying back to the 2×2 WS layout in
  `tcgen05_microarch_speculation.md`.

### 2b. `.kind::mxf8f6f4` (PTX Table 46) — block-scaled FP8/6/4
Differs from the base format to carry **block-scale** metadata:
| Bits | Field | Values |
|------|-------|--------|
| 0–1 | reserved | 0 |
| 2 | sparsity | dense=0/sparse=1 |
| 4–5 | **B scale-factor data ID** | 0–3 |
| 7–9 / 10–12 | atype / btype | E4M3=0/E5M2=1/E2M3=3/E3M2=4/E2M1=5 |
| 13–14 | negate A / B | 0/1 |
| 15–16 | transpose A / B | 0/1 |
| 17–22 | **N** | `N >> 3` |
| 23 | **scale matrix type** (scale_A/B) | UE8M0=1 |
| 27–28 | **M** | `M >> 7` (note: 7 LSBs implicit, not 4) |
| 29–30 | **A scale-factor data ID** | 0–3 |

### 2c. `.kind::mxf4` / `.kind::mxf4nvf4` (PTX Table 47) — FP4 block-scaled
| Bits | Field | Values |
|------|-------|--------|
| 2 | sparsity | dense=0/sparse=1 |
| 4–5 | B scale-factor data ID | 0 or 2 |
| 7–9 | atype | E2M1=1 |
| 10–11 | btype (**2 bits** here) | E2M1=1 |
| 13–14 | negate A / B | 0/1 |
| 15–16 | transpose A / B | mxf4: no-transpose=0; mxf4nvf4: transpose bits present |
| 17–22 | **N** | `N >> 3` |
| 23 | scale matrix type | mxf4: UE8M0=1; mxf4nvf4: UE4M3=0/UE8M0=1 |
| 27–28 | **M** | `M >> 7` |
| 29–30 | A scale-factor data ID | 0 or 2 |
| 31 | **K dimension** | (dense K=64 / sparse K=128)=0; (dense K=96)=1 |

The MX variants trade the base format's dtype/saturate/reuse-shift fields for
**scale-factor data IDs** (which of the `[scale-A-tmem]`/`[scale-B-tmem]` operands
and their block-vector layout) and a coarser **M >> 7** granularity — MX MMAs are
issued as `UTCMXQMMA`/`UTCQMMA` (see those, TODO), and D/accumulator + scales sit
in TMEM.

---

## Why these matter for the microarch model
- **Shape is descriptor-driven, not opcode-driven** — confirms the "one
  `UTCHMMA` opcode, geometry chosen at runtime" picture in
  `tcgen05_microarch_speculation.md`. M/N step granularity (M>>4, N>>3 base;
  M>>7 for MX) matches the PTX shape tables the geometry deduction used.
- **transpose/negate in idesc** = the A/B feed can be transposed/negated at the
  tensor-core input — relevant to how operands enter the systolic array (the
  transpose bit picks row- vs column-major feed; §9.7.17.3.1 leading-dim
  definitions differ by major-ness).
- **`gdesc` swizzle modes** (32/64/128B) are the shared-memory bank-conflict-free
  layouts the staging path (`UTCCP`) and the MMA operand fetch expect — the same
  swizzle family as Hopper wgmma / TMA.
- **max B-reuse shift** (idesc[30:31], `.ws` only) is a direct hardware knob for
  the weight-stationary collector's reuse window.

## Cross-references
- `notes/sm100/instr/utchmma.md` — the MMA that consumes both descriptors.
- `notes/sm100/instr/utccp.md` — uses `gdesc` (source matrix) for shmem→TMEM copy.
- `notes/sm100/arch/tcgen05_microarch_speculation.md` — shape/layout inference
  that these descriptors ground.
- `notes/sm90/arch/wgmma.md` — Hopper GMMA descriptor (the `gdesc` ancestor).

## Open questions
- The `matrix-descriptor-encode` bit-packing of the built `gdesc` as it appears
  in the `UMOV`/`ULOP3` construction SASS — decode a real cublas/cutlass
  Blackwell kernel to confirm the field placement empirically.
- Scale-factor data ID semantics (which TMEM scale operand / block-vector size)
  for the MX kinds — pairs with `UTCMXQMMA` analysis.
- Whether ptxas ever emits a non-trivial `idesc` at compile time or always leaves
  it as a runtime-computed value (our tests passed it as a kernel argument).
