# HGMMA — Half-precision Group Matrix Multiply-Accumulate

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** low  
**Last verified:** 2026-08  
**Probe:** not recorded in this note  
**Open items:** 1 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: lives under notes/sm90/; no part named, so the default measurement site sm120 is assumed

## Conclusion

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

Also see `../arch/wgmma.md` for collector model and subcore partitioning.

## The `gdesc[UR]` operand is 128 bits: two raw PTX descriptors (verified)

For the dense SS form (`hgmma_URa_Rc_`, one visible `gdesc[URn]` operand for
**both** smem operands), the encoded UR index names a group of **four
consecutive uniform registers** (URn..URn+3, 128 bits total):

| URs | content |
|-----|---------|
| `{URn, URn+1}` | raw PTX 64-bit shared-memory matrix descriptor of **A** |
| `{URn+2, URn+3}` | raw PTX 64-bit shared-memory matrix descriptor of **B** |

Verified bit-exact (sm_120, 2026-08): the ptxas uniform-datapath chain that
fills these registers

```
S2UR URb, SR_CgaCtaId            ; cluster rank (0 without clusters)
UMOV URa, <tile byte offset>     ; e.g. 0x400
ULEA URa, URb, URa, 0x18         ; += rank << 24
ULOP3.LUT URa, URa, 0x3FFF0, ... ; &= 0x3FFF0
USHF.R.U64 URa, URa, 0x4, UR63   ; >>= 4   (32-bit LSR semantics, pair NOT shifted)
ULOP3.LUT URa, URa, <or-mask>, ..., 0xFC ; |= LBO field bits
UMOV URa+1, 0x8                  ; high word: stride-dim field = 8 (128 B)
```

produces exactly the C++-side PTX descriptor value
`0x400000 | ((__cvta_generic_to_shared(ptr) & 0x3FFF0) >> 4)` in the low word,
with the OR-mask contributing leading-dimension-offset field bits (observed:
bit 22 → LBO 1024 B for A, bit 20 → LBO 256 B for B) and the high word
carrying the stride-dimension-offset field (0x8 → 128 B). Replicating the
chain in hand-written SASS on sm_120 matched `make_desc()` bit-for-bit for
both the A and B pairs. So the hardware consumes the PTX matrix-descriptor
format unmodified — there is no SASS-level repacking, and hand-written
kernels can load the four URs directly (as our assembler experiments did).
The RS form (`hgmma_Ra_URb_Rc_`) exposes only B as a shared operand, but it
retains the fused-gdesc register-slot convention: `gdesc[URb]` reads the B
descriptor from `{URb+2, URb+3}`.  For example, nvcc prints `gdesc[UR8]`
after constructing the descriptor in `UR10:UR11`.  SR instead reads its A
descriptor directly from `{URa, URa+1}`.

## Variant overview

HGMMA has **6 encoding variants** (3 addressing modes × dense/sparse):

### Addressing modes

| Class | Opcode | A matrix | B matrix | Notes |
|-------|--------|----------|----------|-------|
| `hgmma_Ra_URb_Rc_` | `0x1df0` | GPR Ra | SMEM via URb descriptor | A in registers |
| `hgmma_URa_Rb_Rc_` | `0x15f0` | SMEM via URa descriptor | GPR Rb | B in registers |
| `hgmma_URa_Rc_` | `0x19f0` | SMEM via URa descriptor | SMEM via URa descriptor | Both in SMEM, no reg B |

On Hopper, PTX exposes the first and third rows: A may be in registers while B
is in shared memory (RS), or both may be in shared memory (SS).  The middle
row is an additional native SASS mode, called **SR** below.  Its B-fragment
layout and arithmetic semantics are now measured directly; see
[`Undocumented SR mode`](#undocumented-sr-mode-shared-a-register-b).

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
| ISRC_B_SIZE | 8N bits (`N/4` regs) | Register B in SR mode; 0 for URa_Rc_ |
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

In SS mode the fused `gdesc` group is four uniform registers (two 64-bit
descriptors).  SR reads its single A pair at the visible base.  RS exposes a
single B shared operand but retains its offset within the four-register slot,
so `gdesc[URb]` reads `{URb+2,URb+3}`.  The tensor core hardware reads that
matrix directly from shared memory — no explicit LDSM load is needed.

The descriptor format (base address, stride, layout flags, element size) is
documented in the PTX ISA reference under `wgmma.mma_async` — see the PTX
documentation for the exact bit layout of the 4-register descriptor.

## Undocumented SR mode: shared A, register B

`hgmma_URa_Rb_Rc_` is a real matrix multiply mode:

```
D = A(shared descriptor) * B(register fragment) + C
```

It was mapped on a Modal H100 (2026-09-25) with dense `m64n8k16` and
`m64n16k16` for BF16/F16, plus `m64n8k8` and `m64n16k8` for TF32 (all with
F32 output).  The probe is
`tests/asm_construct/probe_hgmma_sr_layout.py`.  It constructs a no-swizzle
K-major A tile with `A[m,k] = (k == m % K)`, sets exactly one register B
element to 1.0, and locates it in D.  The full sweeps covered all 512/1024
register halves per 16-bit format for n8/n16 and all 256/512 TF32 register
elements.  Every input component mapped cleanly with no holes, aliases, or
hidden reductions.

### B fragment mapping

For F16/BF16, let:

- `w = (tid % 128) / 32` be the warp within the warpgroup;
- `lane = tid % 32`;
- `j` be the zero-based 32-bit register number within the Rb group;
- `h` be 0 for its low 16-bit half and 1 for its high half.

That half contains:

```
B[k,n]
k = 8*(j % 2) + 2*(lane % 4) + h
n = 8*(j / 2) + lane / 4
```

where the divisions are integer divisions.  The Rb group has `N/4` registers
per thread, so each warp carries exactly `16*N` elements: one complete K×N B
tile.  Each additional register pair supplies the next eight columns.

For n8, each lane has two registers:

| lane | Rb[0].lo/hi | Rb[1].lo/hi |
|---:|---|---|
| `4q+p` | `{B[2p,q], B[2p+1,q]}` | `{B[8+2p,q], B[9+2p,q]}` |

For n16, Rb[2]/Rb[3] have the same K mapping and columns `q+8`.  Geometrically
this is the published register-A fragment applied to B-transpose, with the
registers ordered by 8-column B tile and then by 8-row K tile.  In particular,
the middle two registers for n16 are ordered `(n=0..7,k=8..15)` followed by
`(n=8..15,k=0..7)`.

For TF32, each 32-bit register is one element.  With the same `lane` and `j`
definitions:

```
B[k,n]
k = 4*(j % 2) + lane % 4
n = 8*(j / 2) + lane / 4
```

Thus n8 uses two registers per lane and n16 uses four.  This is the same
8-column/half-K tiling as the 16-bit mapping, with one TF32 value replacing a
pair of packed 16-bit values.

### Per-warp ownership

The four register fragments are independent.  A B component supplied by warp `w`
only changes D rows `16w..16w+15`; the other three row bands remain zero.  A
normal matrix multiply must therefore replicate the same B tile in all four
warps.  Supplying different fragments intentionally computes each 16-row
band against a different B matrix.

### Shared descriptor selection is warpgroup-wide

The shared descriptor is not selected independently by each warp.  A second
H100 probe (`tests/asm_construct/probe_hgmma_perwarp_desc.py`) placed four
distinct descriptors in the four warps' uniform registers and cyclically
rotated their assignment.  In both addressing modes the hardware selected
the descriptor supplied by **warp 0** for the entire warpgroup:

```
SR: A_desc_effective = A_desc_from_warp_0
RS: B_desc_effective = B_desc_from_warp_0
```

For SR, four constant A tiles containing 1, 2, 4, and 8 were multiplied by
all-one register B fragments.  With assignments `[1,2,4,8]`, all four
16-row output bands contained 16; rotating warp 0 onto the 2 or 8 tile made
all bands contain 32 or 128.  Descriptors from warps 1--3 had no observable
effect.

The RS test used all-one register A fragments and separately calibrated each
B descriptor.  Every different-descriptor run exactly matched the control
run for warp 0's descriptor, across all four output row bands.  Consequently
the useful decomposition of SR is asymmetric: B is genuinely per-warp, but A
is one warpgroup-wide shared tile chosen through warp 0's descriptor.  The
documented RS form has the complementary behavior: A is per-warp while B is
one warpgroup-wide shared tile chosen through warp 0's descriptor.

The measured mapping also explains the spec's source widths:

| shape | B regs/thread | bytes/warp | logical B tile |
|---|---:|---:|---:|
| m64n8k16 | 2 | 256 | 16×8 BF16/F16 = 256 B |
| m64n16k16 | 4 | 512 | 16×16 BF16/F16 = 512 B |
| m64n8k8 | 2 | 256 | 8×8 TF32 = 256 B |
| m64n16k8 | 4 | 512 | 8×16 TF32 = 512 B |

The closed-form mapping predicts the larger N encodings, whose
`ISRC_B_SIZE = 8N` property extends in 64-bit steps for every additional eight
columns.  The exhaustive hardware sweeps performed so far are n8 and n16 for
F16, BF16, and TF32; larger-N layout is an extrapolation of the encoding rule
and observed tiling.

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
from `../arch/wgmma.md`.

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
equivalent — the PTX always puts B in shared memory.  Its native semantics and
B layout are given in the empirical SR section above.

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

From `../arch/wgmma.md` (verified on sm_90a):

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

## History / retracted hypotheses

> Claims below were **superseded, refuted, or never settled** by later work; they are kept
> for provenance. Do not cite them as current.

## Open questions

- **GMMA scoreboard mechanism**: How exactly does `gsb0` interact with  <!-- open-question: open blocked-by "blocker (inferred): needs a Hopper session (sm_90) -- no local part" -->
  `wgmma.commit_group`/`wgmma.wait_group` at the hardware level? The
  scoreboard tracking is warpgroup-wide and decoupled from the per-warp
  scoreboard.

