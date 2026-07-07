# HMMA — Half-precision Matrix Multiply-Accumulate

**Opcode mnemonic:** `HMMA`
**Pipe:** `fp16_pipe` (HMMA_OP subset, `$VQ_HMMA`)
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_EMULATABLE`

## Semantics

Warp-collective half-precision tensor core matrix multiply-accumulate:

```
D = A × B + C
```

where A (M×K), B (K×N), C/D (M×N), with M=16, N=8, K∈{4,8,16,32} (K varies
by variant and sparsity). All 32 threads in the warp participate; each thread
holds a fragment of each matrix in its registers.

Also see `notes/hmma_pipeline.md` for scheduling, latency, and stall-encoding details.

## Variant overview

HMMA has **4 encoding variants** across **2 opcodes**:

| Class | Opcode | Dense/Sparse | RF mode |
|-------|--------|:---:|------|
| `hmma_x8_` | `0x23c` | Dense | Register file (Rd, Rc) |
| `hmma_sparse_` | `0x23c` | Sparse (2:4) | Register file (Rd, Rc, Re) |
| `hmma_x8_indexedRF_` | `0x1e79` | Dense | Indexed RF (URd, URc) |
| `hmma_sparse_indexedRF_` | `0x1e79` | Sparse (2:4) | Indexed RF (URd, URc, Re) |

Bit [91]=0 for register-file variants (0x23c), [91]=1 for indexedRF (0x1e79).
Lower 12 bits identical (`0x23c`).

### Syntax

```
// Dense, register file
@P0 HMMA.16816.F16 R2, -R4.reuse, -R6.reuse, R8, !UPT

// Sparse, register file
@P0 HMMA.16832.F16.SP.TID R2, R4.reuse, R6.reuse, R8, !UPT, R10.reuse, 0x1

// Indexed register file
@P0 HMMA.16816.F16 RF:URd[UR4], R8.reuse, R10.reuse, RF:URc[UR4], !UPT
```

### Dense vs Sparse differences

| Feature | Dense (`hmma_x8_*`) | Sparse (`hmma_sparse_*`) |
|---|---|---|
| Size enum | `SIZE_1688_16816_1684` | `SIZE_1688_16816_16832` |
| Re operand | none | Re (metadata reg) |
| id operand | none | 2-bit immediate (0 or 1) |
| reuse_src_e | \*0 | variable |
| loc/spformat field | \*0 | SPFORMAT (TID=0, REGOFFSET=1) |
| ISRC_E_SIZE | 0 | 32 |

### Register-file vs IndexedRF differences

| Feature | Register file (`hmma_*_`) | IndexedRF (`hmma_*_indexedRF_`) |
|---|---|---|
| Rd source | 8-bit register Rd [23:16] | RF:indexURd — reads from uniform register file at index URd |
| Rc source | 8-bit register Rc [71:64] | RF:indexURc — reads from uniform register file at index URc |
| IDEST_SIZE | 64 (F16 dst) / 128 (F32 dst) | 32 |
| ISRC_C_SIZE | 64 (F16) / 128 (F32) | 32 |
| URd==URc constraint | none | **must be equal** |

## Modifiers

### Matrix size (`size`) — bits [78,75]

Dense `SIZE_1688_16816_1684`:

| Value | Mnemonic | M×N×K | Notes |
|:---:|---|---|---|
| 0 | `1688` | 16×8×8 | Default |
| 1 | `16816` | 16×8×16 | Not TF32 |
| 2 | `1684` | 16×8×4 | TF32 only |
| 3 | INVALID3 | — | Illegal encoding |

Sparse `SIZE_1688_16816_16832`:

| Value | Mnemonic | M×N×K | Notes |
|:---:|---|---|---|
| 0 | `1688` | 16×8×8 | TF32 only in sparse mode |
| 1 | `16816` | 16×8×16 | 2× dense K (A is sparse) |
| 2 | INVALID2 | — | Illegal encoding |
| 3 | `16832` | 16×8×32 | Non-TF32 only |

### Source format (`srcfmt`) — bits [83:82]

| Value | Mnemonic | Precision | Constraints |
|:---:|---|---|---|
| 0 | `F16` | IEEE fp16 | Default, supports F16/F32 dst |
| 1 | `BF16` (=E8M7) | BFloat16 | dstfmt must be F32 |
| 2 | `TF32` (=E8M10) | TensorFloat-32 | dstfmt must be F32; size restricted |
| 3 | `E6M9` | 6-bit exp, 9-bit mantissa | dstfmt must be F32 |

### Destination format (`dstfmt`) — bit [76]

| Value | Mnemonic | Accumulator precision | Rd/Rc register count |
|:---:|---|---|---|
| 0 | `F16` | fp16 | 2 regs (64b) |
| 1 | `F32` | fp32 | 4 regs (128b) |

### Negate — bits [72] (Ra), [63] (Rb)

Both A and B operands support negation. `Ra@negate` at [72], `Rb@negate` at [63].

### Reuse — encoded in opex table

`/REUSE` qualifier on Ra, Rb, and Re (sparse) operands. When set, the
operand is held in the tensor core's operand reuse cache across the
instruction group.

Constraints:
- `.reuse` cannot be combined with `DRAIN`/`WAITn_END_GROUP` usched tokens
- Typically used when the same weight/activation fragment is shared across
  multiple MMA instructions (e.g., accumulate chain)

### Sparse format (`spformat`) — bit [81] (sparse only)

| Value | Mnemonic | Description |
|:---:|---|---|
| 0 | `TID` | Thread-ID based metadata |
| 1 | `REGOFFSET` | Register-offset based metadata |

### Uniform predicate (`UPp`) — bits [90:87], via TABLES_Pnz_0

The uniform predicate (UPT/UP0–UP3) is encoded through the `TABLES_Pnz_0`
lookup table combining `UPp@not` and `UPp`. The resulting 4-bit `op` field
at [90:87] encodes both the predicate value and its negation.

## Operand register sizes

ISRC_A/B/C/E_SIZE and IDEST_SIZE depend on size, srcfmt, and dstfmt:

| Condition | ISRC_A_SIZE | ISRC_B_SIZE | IDEST/ISRC_C |
|---|---|---|---|
| F16/BF16/E6M9, size=1688 | 128 (4 regs) | 64 (2 regs) | 64 (F16) / 128 (F32) |
| F16/BF16/E6M9, size=16816 | 256 (8 regs) | 128 (4 regs) | 64 (F16) / 128 (F32) |
| TF32, size=1688 | 256 (8 regs) | 128 (4 regs) | 128 (F32 only) |
| TF32, size=1684 | 128 (4 regs) | 64 (2 regs) | 128 (F32 only) |

Alignment: Rd/Rc always aligned to 2; Ra/Rb alignment depends on register count.

## Latency

See `notes/hmma_pipeline.md` for detailed empirical analysis. Key values:

| Metric | Value |
|---|---|
| TABLE_TRUE HMMA→HMMA (accumulator RAW) | 28 cycles |
| Effective accumulate gap (measured) | ~24 cyc (accumulator bypass) |
| TABLE_OUTPUT HMMA→HMMA (WAW) | 1 cycle |
| Pipe occupancy | FMALITE_Occupancy [2] |
| Scoreboard model | Fixed-latency (dst_wr_sb=7, no write scoreboard) |

## PTX→SASS mapping

HMMA implements PTX `mma.sync.aligned` for fp16/bf16/tf32/e6m9 types.

| PTX | SASS |
|-----|------|
| `mma.sync.aligned.m16n8k8.f16.f16.f16` | `HMMA.1688.F16` |
| `mma.sync.aligned.m16n8k16.f16.f16.f16` | `HMMA.16816.F16` |
| `mma.sync.aligned.m16n8k8.f16.f16.f32` | `HMMA.1688.F32` |
| `mma.sync.aligned.m16n8k16.f16.f16.f32` | `HMMA.16816.F32` |
| `mma.sync.aligned.m16n8k8.tf32.tf32.f32` | `HMMA.1688.F32.TF32` |
| `mma.sync.aligned.m16n8k4.tf32.tf32.f32` | `HMMA.1684.F32.TF32` |
| Sparse `mma.sync.aligned.m16n8k16.f16.f16.f16` | `HMMA.16816.F16.SP.TID` |
| Sparse `mma.sync.aligned.m16n8k32.f16.f16.f16` | `HMMA.16832.F16.SP.TID` |

`.reuse` is a ptxas scheduling optimization, not a PTX-level qualifier — the
compiler infers it from operand lifetimes.

## Cross-comparison

| Property | HMMA | IMMA |
|---|---|---|
| Pipe | `fp16_pipe` | `int_pipe` |
| Data type | fp16/bf16/tf32/e6m9 | u8/s8/u4/s4 |
| Accumulator | f16/f32 | s32 |
| TABLE_TRUE latency | 28 cyc | 28 cyc |
| Sparse supported | yes | yes |

## Open questions

- **IndexedRF usage**: When does ptxas choose indexed register file
  addressing over standard register file? Possibly for uniform-register-resident
  accumulators or warp-uniform matrices.
- **BF16 vs E8M7 encoding**: BF16 and E8M7 share the same srcfmt encoding
  value (1). How does the hardware distinguish them, or are they treated
  identically? (BF16 = E8M7 format is the same 1-8-7 bit layout.)
- **`.1684` vs `.1688` TF32**: The `.1684` size for TF32 is unusual (K=4
  instead of K=8). Why does TF32 alone get a half-K variant?
