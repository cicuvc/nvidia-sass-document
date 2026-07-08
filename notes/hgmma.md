# HGMMA — Half-precision Group Matrix Multiply-Accumulate

**Opcode mnemonic:** `HGMMA`
**Pipe:** `mio_pipe` (MIO_SLOW_OPS, shared with LDSM/STSM — not fp16_pipe!)
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`
**VIRTUAL_QUEUE:** `$VQ_UMMA`

## Semantics

**Warpgroup-level** (4 consecutive warps = 128 threads) half-precision tensor
core matrix multiply-accumulate. This is the SASS implementation of PTX
`wgmma.fence` + `wgmma.commit_group` + `wgmma.mma_async`.

```
D = A × B + C
```

where A (M×K), B (K×N), C/D (M×N), with **M=64 fixed**, N=8..256 in steps
of 8, K=16 (f16/bf16/e6m9) or K=8 (tf32).

**Key architectural difference from HMMA:** HGMMA operates on matrices whose
data resides in **shared memory**, not registers. A `GMMA:gdesc[UR]` slot is a
shared-memory descriptor in a uniform register that specifies the matrix's
shared memory address, layout, and stride. One or both of A/B matrices are
fetched from shared memory by the tensor core hardware directly.

This is the Hopper async tensor core model — data is staged in shared memory
via TMA (UTMALDG) or LDSM, then consumed asynchronously by HGMMA.

Also see `notes/wgmma.md` for collector model and subcore partitioning.

## Variant overview

HGMMA has **6 encoding variants** (3 addressing modes × dense/sparse):

### Addressing modes

| Class | Opcode | A matrix | B matrix | Notes |
|-------|--------|----------|----------|-------|
| `hgmma_Ra_URb_Rc_` | `0x1df0` | GPR Ra | SMEM via URb descriptor | A in registers |
| `hgmma_URa_Rb_Rc_` | `0x15f0` | SMEM via URa descriptor | GPR Rb | B in registers |
| `hgmma_URa_Rc_` | `0x19f0` | SMEM via URa descriptor | SMEM via URa descriptor | Both in SMEM, no reg B |

On Hopper, the common idiom is both matrices in shared memory (`URa_Rc_`) — A/B tiles are staged asynchronously via TMA (`UTMALDG`) or `LDSM`, never loaded into registers directly. The register-source variants (`Ra_URb_Rc_`, `URa_Rb_Rc_`) exist for **chained GEMM**: compute `A×B` with both operands in SMEM → result lands in registers as `Rd`/`Rc`, then chain with matrix `C` still in SMEM via the register-source variant without reloading the intermediate result. Keeping A/B in registers without this chain pattern would require `LDMATRIX`, consuming 2× RF bandwidth with no benefit over the SMEM path.

Sparse variants share the same opcodes, distinguished by `sp`/`spformat` slots.

### Syntax

```
// A in registers, B in shared memory
@P0 HGMMA.64x128x16.F32 R2, R4, gdesc[UR8], R10, UPT, gsb0

// A in shared memory, B in registers
@P0 HGMMA.64x64x16.F16.F16 R2, gdesc[UR6].tnspA, -R8, R10, UPT

// Both in shared memory
@P0 HGMMA.64x256x16.F16 R2, gdesc[UR4].negA.tnspA.negB.tnspB, R10, UPT, gsb0

// Sparse
@P0 HGMMA.64x128x16.F16.SP.TID R2, R4, gdesc[UR8], R10, UPT, R12, 0x1
```

### Dense vs Sparse differences

| Feature | Dense | Sparse |
|---|---|---|
| Extra operands | none | Re (metadata), id (2-bit) |
| sp/ spformat | not present | SP, TID/REGOFFSET |
| ISRC_E_SIZE | 0 | 32 |

## Matrix size

**Massive enum**: `SIZE_64x8x16_64x16x16_..._64x256x16_64x8x8_..._64x256x8`.
128 total values (64 non-TF32 sizes with K=16 + 64 TF32 sizes with K=8).
7-bit field at [59:53].

### Size encoding (7-bit at [59:53])

| Range | K | srcfmt | N values |
|---|---|---|---|
| 0–63 | 16 | f16/bf16/e6m9 | N = 8, 16, 24, ..., 256 (32 values, with gaps) |
| 64–127 | 8 | tf32 | N = 8, 16, 24, ..., 256 (32 values, with gaps) |

Valid N values: 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112,
120, 128, 136, 144, 152, 160, 168, 176, 184, 192, 200, 208, 216, 224, 232,
240, 248, 256 (32 values, 8-step).

All other values (INVALID64/65/66/...) are illegal encoding errors.

## Modifiers

### Source format (`srcfmt`) — 2-bit at [77:76]

Same `SRCFMT` as HMMA: F16(0), BF16/E8M7(1), TF32/E8M10(2), E6M9(3).

BF16/TF32/E6M9 require dstfmt=F32. TF32 cannot transpose and uses K=8 sizes only.

### Destination format (`dstfmt`) — 1-bit at [75]

FloatNo64: F16(0), F32(1).

### Negate flags

| Variant | A negate | B negate | Bits |
|---|---|---|---|
| `Ra_URb_Rc_` | Ra@negate [72] | negB [63] | — |
| `URa_Rb_Rc_` | negA [72] | Rb@negate [63] | — |
| `URa_Rc_` | negA [72] | negB [63] | — |

A negate is on the register-based A operand or on the descriptor; B negate
is on the register-based B operand or on the descriptor.

### Transpose flags

| Variant | A transpose | B transpose | Bits |
|---|---|---|---|
| `Ra_URb_Rc_` | — | tnspB [62] | — |
| `URa_Rb_Rc_` | tnspA [61] | — | — |
| `URa_Rc_` | tnspA [61] | tnspB [62] | — |

TF32 cannot be transposed (tnspA/tnspB must be `notnsp*`).

### GMMA Scoreboard (`gsb`) — 3-bit at [86:84]

| Value | Mnemonic | Description |
|:---:|---|---|
| 0 | `gsb0` | Accumulator group 0 |
| 7 | `nooptional_gsb` | No GSB tracking (default) |
| 1–6 | INVALID | Illegal encoding |

The GMMA scoreboard coordinates accumulator ordering across multiple HGMMA
instructions within a warpgroup. `gsb0` tags the accumulator write for
group-level synchronization (used with `wgmma.commit_group`/`wgmma.wait_group`).

## Operand register sizes

| Operand | Size | Notes |
|---|---|---|
| ISRC_A_SIZE | 128 (4 regs) | Always 128-bit for register-based Ra |
| ISRC_B_SIZE | 64+ or 128 | Register-based Rb varies with size; 0 for URa_Rc_ |
| IDEST_SIZE/ISRC_C_SIZE | varies with N | 64 + 64×N_stepping; grows with tile width |

For F16 dst with `64xNx16`:
- N=8: Rc/Rd need 2 regs
- N=16: 4 regs
- N=24: 6 regs
- N=32: 8 regs
- ...increasing by 2 regs per 8 N steps, up to N=256: 64 regs

For F32 dst: register count doubles.

## Shared memory descriptor (`gdesc`)

The `GMMA:gdesc[UniformRegister]` slot is a shared-memory matrix descriptor.
It encodes:
- Base address in shared memory
- Matrix layout (row-major/column-major)
- Stride between rows
- Element size

The 4 uniform registers (aligned to 4) pointed to by URa/URb hold the full
descriptor. The tensor core hardware reads the matrix data directly from
shared memory using this descriptor — no explicit LDSM loads needed.

The descriptor format (base address, stride, layout flags, element size) is
documented in the PTX ISA reference under `wgmma.mma_async` — see the PTX
documentation for the exact bit layout of the 4-register descriptor.

## Bit layout (128-bit)

### hgmma_Ra_URb_Rc_ (0x1df0, dense)

```
[124:122],[109:105] w8  opex
[121:116]           w6  req_bit_set
[115:113]           w3  src_rel_sb       = 7 (fixed)
[112:110]           w3  dst_wr_sb        = 7 (fixed)
[103:102]           w2  pm_pred
[91][11:0]          w13 opcode           (0x1df0)
[90:87]             w4  op (UPp)
[86:84]             w3  cop (gsb)
[77:76]             w2  srcfmt
[75]                w1  dstfmt
[74]                w1  sh               = *0
[73]                w1  sz               = 0
[72]                w1  Ra@negate
[71:64]             w8  Rc
[63]                w1  negB
[62]                w1  tnspB
[59:53]             w7  size
[37:32]             w6  URb
[31:24]             w8  Ra
[23:16]             w8  Rd
[15]                w1  Pg_not
[14:12]             w3  Pg
```

### hgmma_URa_Rb_Rc_ (0x15f0, dense)

```
[59:53]             w7  size
[39:32]             w8  Rb
[29:24]             w6  URa
...otherwise similar layout, tnspA at [61] instead of tnspB at [62]
```

### hgmma_URa_Rc_ (0x19f0, dense)

```
[59:53]             w7  size
[29:24]             w6  URa
...no Rb field, both tnspA at [61] and tnspB at [62]
```

### Sparse variants add

```
[50]                w1  reuse_src_e
[49:48]             w2  id
[47:40]             w8  Re
[81]                w1  spformat (replaces *0)
```

## Key characteristics vs HMMA

| Property | HGMMA | HMMA |
|---|---|---|
| Scope | Warpgroup (4 warps) | Warp (1 warp) |
| Pipe | `mio_pipe` (MIO_SLOW_OPS) | `fp16_pipe` |
| VQ | `$VQ_UMMA` | `$VQ_HMMA` |
| INST_TYPE | DECOUPLED_BRU_DEPBAR_RD_SCBD | COUPLED_EMULATABLE |
| Matrix data source | Shared memory (gdesc) | Registers |
| Matrix dimensions | M=64, N=8..256, K=8/16 | M=16, N=8, K=4/8/16/32 |
| Scoreboard | GMMA scoreboard (gsb) | Variable latency (dst_wr_sb) |
| src_rel_sb | 7 (fixed) | Variable |
| dst_wr_sb | 7 (fixed) | Variable |
| Operand negation | per-variant flags | Ra@negate, Rb@negate |
| Transpose | gdesc modifier (tnspA/B) | None |
| Size encoding | 7-bit, 128 values | 2-bit, 3/4 values |
| Sparse | Yes | Yes |
| Variants | 6 (3 modes × 2 density) | 4 (2 RF modes × 2 density) |

## Latency

HGMMA is on `mio_pipe` (MIO_SLOW_OPS) — the same pipe as LDSM/STSM/LDS/STS.
This is notable because HGMMA is a **compute** instruction that shares the
memory I/O pipe, not fp16_pipe like HMMA.

- `src_rel_sb = 7`, `dst_wr_sb = 7` — fixed-latency, not variable-latency tracked
- GMMA scoreboard (`gsb`) provides warpgroup-level synchronization
- TABLE_TRUE: MIO_SLOW_OPS → consumers follow MIO latency tiers

## PTX→SASS mapping

HGMMA implements PTX `wgmma.mma_async` for fp16/bf16/tf32/e6m9.

| PTX | SASS |
|-----|------|
| `wgmma.mma_async.sync.aligned.m64n8k16.f16.f16.f16` | `HGMMA.64x8x16.F16` |
| `wgmma.mma_async.sync.aligned.m64n128k16.f16.f16.f16` | `HGMMA.64x128x16.F16` |
| `wgmma.mma_async.sync.aligned.m64n256k16.f16.f16.f16` | `HGMMA.64x256x16.F16` |
| TF32 `wgmma.mma_async.sync.aligned.m64n64k8.tf32.tf32.f32` | `HGMMA.64x64x8.F32.TF32` |

The `wgmma.fence` and `wgmma.commit_group` PTX instructions are separate
control instructions (SYNCS, FENCE variants) that interact with the GMMA
scoreboard, not part of the HGMMA instruction itself.

## PTX→SASS detailed cross-reference

Analysis integrating the PTX `wgmma.mma_async` spec and the empirical findings
from `notes/wgmma.md`.

### Instruction lowering

| PTX | SASS | Notes |
|-----|------|-------|
| `wgmma.fence.sync.aligned` | `WARPGROUP.ARRIVE` | BRU-routed, cross-subcore barrier |
| `wgmma.mma_async...` | `HGMMA.64xNxK...` | Async dispatch, returns immediately |
| `wgmma.commit_group` | **(no instruction)** | Folded into the last HGMMA's `gsb0` write |
| `wgmma.wait_group N` | `WARPGROUP.DEPBAR.LE gsb0, N` | 3-bit gsbcnt |

### PTX operands → SASS fields

| PTX operand | SASS encoding | Description |
|---|---|---|
| `d` (accumulator) | Rd + Rc (same reg range) | Accumulator read/write; RZ → scale-d false (A×B only) |
| `a` (reg) | Ra ([31:24]) | A matrix in registers (4 × f16x2 or 4 × b32 per thread) |
| `a-desc` | `gdesc[URa]` | 64-bit descriptor in uniform reg, A in shared memory |
| `b-desc` | `gdesc[URb/URa]` | 64-bit descriptor, B in shared memory |
| `scale-d` | Rc == RZ? → first HGMMA starts fresh | PTX pred: true=accumulate(Rc), false=A×B only(RZ) |
| `imm-scale-a` (±1) | negA flag | 1 → nonega, -1 → negA |
| `imm-scale-b` (±1) | negB flag / Rb@negate | 1 → nonegb, -1 → negB |
| `imm-trans-a` (0/1) | tnspA flag | 0 → notnspa, 1 → tnspA |
| `imm-trans-b` (0/1) | tnspB flag | 0 → notnspb, 1 → tnspB |

### The three HGMMA addressing modes = three PTX syntax forms

PTX `wgmma.mma_async` has two syntax forms for f16/bf16:
1. `d, a, b-desc, scale-d, ...` — A in registers, B via descriptor
2. `d, a-desc, b-desc, scale-d, ...` — both A and B via descriptors

The SASS adds a third combination not directly expressible in single-issue
PTX (but the compiler may split):

| SASS class | A source | B source | PTX form |
|---|---|---|---|
| `hgmma_Ra_URb_Rc_` | GPR Ra | SMEM via URb desc | `d, a, b-desc, ...` |
| `hgmma_URa_Rb_Rc_` | SMEM via URa desc | GPR Rb | (compiler-split from desc-only form?) |
| `hgmma_URa_Rc_` | SMEM via URa desc | SMEM via URa desc | `d, a-desc, b-desc, ...` |

`hgmma_URa_Rb_Rc_` (A in SMEM, B in regs) does not have a direct PTX syntax
equivalent — the PTX always puts B in shared memory. This variant may be
used for compiler optimizations or for type variants where the PTX spec
allows register-based B (e.g., certain integer forms).

### Scale-D: RZ means "start fresh"

In PTX, `scale-d` is a predicate: true = D = A×B + D (accumulate), false =
D = A×B (no prior accumulator). In SASS, this is encoded by whether the
accumulator register (Rc) is RZ or a real register:

- First HGMMA in a chain: `HGMMA R24, gdesc[UR4], RZ, !UPT` — RZ = no accumulate
- Subsequent: `HGMMA R24, gdesc[UR4], R24, ...` — same register = accumulate

The `!UPT` (uniform predicate always-true) on the first HGMMA is interesting:
it ensures the no-accumulate form always executes (scale-d = false in PTX).

### Accumulator collector model (from wgmma.md)

The tensor core holds the accumulator in **dedicated internal storage** (a
collector), not in the general RF, for the duration of a chain to the same
target. Evidence:

1. **No inter-HGMMA wait on same accumulator** — chained HGMMAs to R24 show
   no scoreboard waits despite textbook RAW hazard on R24. Partial sums are
   forwarded inside the tensor core.
2. **Mid-chain RF read forces drain** — inserting a non-tensor instruction
   that reads the accumulator forces: `HGMMA ... gsb0` → `DEPBAR.LE gsb0,0`
   (drain to RF) → `WARPGROUP.ARRIVE` (re-fence).
3. **Accumulator switching costs extra sync** — alternating two independent
   accumulators requires drain + re-fence per switch.

### Sync skeleton for a K-loop

From `notes/wgmma.md` (verified on sm_90a):

```
WARPGROUP.ARRIVE                              # wgmma.fence
HGMMA R24, gdesc[UR4], RZ, !UPT               # k=0, scale-d=false
HGMMA R24, gdesc[UR4], R24                    # k=1, accumulate
HGMMA R24, gdesc[UR4], R24, gsb0              # k=last, write group SB
WARPGROUP.DEPBAR.LE gsb0, 0x0                 # wgmma.wait_group 0
```

**Key observations:**
- Only the **last** HGMMA in a same-accumulator chain writes `gsb0`
- Previous HGMMAs in the chain are ordered by the in-order tensor pipe
- `commit_group` needs no instruction — the group boundary is implicit
  in the tail HGMMA's group-scoreboard write
- Between HGMMAs, the compiler interleaves uniform-datapath instructions
  (`UIADD3`, `ULOP3`, `USHF`) to rebuild the shared-memory descriptor
  (advancing tile address for the next K iteration)

### GMMA scoreboards (from wgmma.md)

HGMMA does **not** use the 6 general scoreboards (SB0–5). Its `src_rel_sb`
and `dst_wr_sb` are both hardwired to 7, and `req_bit_set` only waits on
input data (LDGSTS/TMA/LDG). Instead, two dedicated scoreboards manage
synchronization:

| Scoreboard | Writer | Reader | Latency | Role |
|---|---|---|---|---|
| `GMMA_SCOREBOARD` | `WARPGROUP.ARRIVE` | `HGMMA` | 6 | Fence accumulator regs |
| `GMMA_GROUP_SCOREBOARD` | `HGMMA[gsb0]` | `WARPGROUP.DEPBAR.LE` | 3 | Count outstanding groups |

### Warpgroup subcore partitioning

A warpgroup's 4 warps are distributed one-per-subcore across the SM's 4
subcores. Each subcore has its own tensor core computing a 16×N slice of
the 64×N output. `WARPGROUP.ARRIVE` (BRU-routed) synchronizes all 4
subcores onto the same warpgroup before its HGMMA chain starts, ensuring
the 4 subcores issue in lockstep.

### Matrix descriptor format

The 64-bit GMMA descriptor in the uniform register encodes (PTX spec §Matrix Descriptor Format):
- bits [13:0] → `(start_addr & 0x3FFFF) >> 4` — base address in shared memory
- bits [29:16] → `(leading_dim_byte_offset & 0x3FFFF) >> 4`
- bits [45:32] → `(stride_dim_byte_offset & 0x3FFFF) >> 4`
- bits [51:49] → base offset (0 if at swizzle pattern boundary)
- bits [63:62] → swizzle mode: 0=none, 1=128B, 2=64B, 3=32B

The descriptor is built at runtime by uniform-register arithmetic
(`UIADD3`/`ULOP3`/`USHF`) — the address and layout fields are packed
into the 64-bit register pair spanning 4 uniform registers (aligned).

## Open questions

- **GMMA scoreboard mechanism**: How exactly does `gsb0` interact with
  `wgmma.commit_group`/`wgmma.wait_group` at the hardware level? The
  scoreboard tracking is warpgroup-wide and decoupled from the per-warp
  scoreboard.
