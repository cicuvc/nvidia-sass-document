# UTCHMMA — 5th-gen tensor-core FP16/BF16 MMA  → PTX `tcgen05.mma.kind::f16`

**Opcode mnemonic:** `UTCHMMA` — two opcodes by A source:
A-from-gdesc = `0b1010111101010` (0x15ea, 5610), A-from-tmem = `0b1100111101010` (0x19ea, 6634)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42)

New on sm100 (Blackwell). `UTCHMMA` = **U**niform **T**ensor-**C**ore **H**alf-precision
**M**atrix-**M**ultiply-**A**ccumulate — the SASS realization of PTX
**`tcgen05.mma.kind::f16`** (and `.kind::tf32`, `.kind::f8f6f4` share this
opcode; the exact element types are carried by the `idesc` instruction
descriptor, not the mnemonic). Computes `D = A*B + D` with the accumulator and
operands in **Tensor Memory (TMEM)**.

## Semantics
`UTCHMMA A, B, tmem[D], tmem[E], idesc, UPp [, scaleU4]`
- Single-thread-issued (unlike Hopper wgmma's warpgroup-collective model): one
  thread launches the whole MxNxK MMA. Async / decoupled.
- **`D = A*B + D`** when `UPp` (enable-input-d) is true; **`D = A*B`** when false.
- Optional **`scaleU4`** scales the input accumulator: `D = A*B + D*(2^-scaleU4)`
  (PTX `scale-input-d`, valid only for f16/tf32, range 0–15).

Like STTM/UTCCP it is `INST_TYPE_DECOUPLED_RD_SCBD` (reads descriptors/TMEM,
releases a read scoreboard); completion is signalled to an mbarrier via
`UTCBAR` (`tcgen05.commit`) or awaited via the standard mechanism.

## Operands (cuobjdump order)
| pos | SASS | bits | PTX role |
|-----|------|------|----------|
| A | `gdesc[URa]` / `tmem[URa]` | [31:24] | A matrix (shared-mem descriptor **or** TMEM) |
| B | `gdesc[URb]` | [39:32] | B matrix (shared-mem descriptor, 64-bit) |
| D | `tmem[URc]` | [71:64] | destination + accumulator D (TMEM) |
| E | `tmem[URe]` | [47:40] | tmemE (secondary TMEM operand) |
| idesc | `idesc[URh]` | (URe+1) | instruction descriptor (32-bit, in shared/uniform) |
| pred | `UPp` | [89:87]+[90] | enable-input-d predicate |
| imm | `scaleU4` | [78:75] | scale-input-d (optional) |

Two operands are register **pairs** so the encoding fuses them:
- **`URe`/`URh` fusion:** field [47:40] = `TABLES_URa_0(URe, URh)`, which is just
  `URe` with the constraint `URh == URe + 1`. So `tmem[UR4], idesc[UR5]` encodes
  as field=4; the idesc register is always the tmemE register + 1 (adjacent
  aligned pair). The 64-bit A/B/E descriptors likewise require even-aligned base
  regs (`% 2 == 0` CONDITIONS).
- **`URi`** (disable-output-lane mask register) rides field [55:48]; encodes
  `URZ` when the PTX `{disable-output-lane}` vector is all-zero.

`ISRC_A_SIZE=64, ISRC_B_SIZE=64, ISRC_E_SIZE=64` (descriptor/pair operands),
`ISRC_C_SIZE=32`.

## Variant overview
| Class | Kind | Opcode | A source |
|-------|------|--------|----------|
| `utchmma_1cta__A_gdesc` | CLASS | 0x15ea | shared descriptor |
| `utchmma_1cta__A_tmem` | CLASS | 0x19ea | TMEM (+`.ASHIFT`) |
| `utchmma_2cta__A_gdesc` / `_A_tmem` | CLASS | 0x15ea/0x19ea | `.2CTA` |
| `utchmma_{1,2}cta_one__A_*` | ALT | — | `.ONE` (encoding-identical) |

The two opcodes differ only in operand-A type (gdesc vs tmem) and bit[74]
(`sh`=`ASHIFT`, only meaningful when A is in TMEM).

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `cluster_sz` | `ONLY1CTA`/`ONLY2CTA` | [85] | `.2CTA` = PTX `.cta_group::2` |
| `ws` | `WS` | [83] | weight-stationary mode (enables B_KEEP/B_REUSE/BUFFER1-3) |
| `ashift` | `ASHIFT` | [74] | `.ASHIFT` (A-from-TMEM only): shift A rows down |
| `reuse_a` | `REUSE_A` | [86] | `.A_REUSE` (collector::a::use; not with WS) |
| `keep_a` | `KEEP_A` | [84] | `.A_KEEP` (collector fill; not with WS) |
| `reuse_b` | `REUSE_B` | [82] | `.B_REUSE` (requires WS) |
| `keep_b` | `KEEP_B` | [81] | `.B_KEEP` (requires WS) |
| `buffer` | `BUFFER` | [80:79] | `BUFFER0..3` (1-3 require WS) |

The `collector_usage` / weight-stationary (`.WS`) machinery here is the SASS
side of PTX `.collector::{a,bN}::{fill,use,lastuse,discard}` and the activation-
stationary MMA forms. `.ashift` maps directly.

### Activation-stationary vs Weight-stationary vs Convolution
These are **two orthogonal axes**, not three parallel modes:

**Axis 1 — which operand stays resident in the collector buffer** (data-reuse
optimization; `WS` bit [83]):

| mode | activation | weights | PTX | collector on | # buffers |
|------|-----------|---------|-----|:---:|:---:|
| Activation-stationary | `A` | `B` | default `tcgen05.mma` (`.WS`=0) | `A` | 1 (`.collector::a::*`) |
| Weight-stationary | `B` | `A` | `tcgen05.mma.ws` (`.WS`=1) | `B` | 4 (`.collector::b0..b3::*`) |

The name refers to which *activation* matrix stays put. The SASS `WS` bit flips
the collector semantics, enforced by the CONDITIONS: `.A_REUSE`/`.A_KEEP` only
with `.WS`=0; `.B_REUSE`/`.B_KEEP`/`.BUFFER1-3` only with `.WS`=1. So WS is
**not a separate mnemonic** — just bit [83] toggling collector-A(1 buffer) ↔
collector-B(4 buffers).

**Axis 2 — GEMM vs Convolution** (application, not a mode): the same `UTCHMMA`
does both. Convolution stores activations in `A` **or** `B` and weights in the
other (hence it *uses* AS or WS), with a **mirror pair** of sliding-window tools:
- **AS conv** uses **`.ashift`** (bit [74]) — shifts A's rows down by one (`M`=128/256
  only, A-from-TMEM opcode 0x19ea only, ⊥ `.A_KEEP`/`.A_REUSE`): activation (A)
  streams as **rows**, window slides by a row.
- **WS conv** uses a **`zero-column-mask-desc`** (a 64-bit descriptor, PTX
  §9.7.17.4.3; no `.ashift`): activation (B) streams as **columns**, and a
  periodic run-length mask zeroes B columns for padding/dilation/halo. In both,
  the **collector holds the activation** (A / B respectively).

```
             GEMM            Convolution
AS (.WS=0)   default mma     act=A wet=B, collector A, window via .ashift (rows)
WS (.WS=1)   .ws             act=B wet=A, collector B, window via zero-col mask (cols)
```
PTX splits this into 6 syntax forms; SASS collapses them all into `UTCHMMA`,
distinguished by `WS`[83] + `ASHIFT`[74] + collector bits (`A_REUSE`[86]/
`A_KEEP`[84]/`B_REUSE`[82]/`B_KEEP`[81]/`BUFFER`[80:79]). See
`notes/sm100/arch/tcgen05_microarch_speculation.md` for the inferred im2col-free
convolution dataflow.

## Bit layout (128-bit)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = read-scoreboard release
[112:110]           dst_wr_sb    = *7 (pinned)
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x15ea / 0x19ea
[90]                UPp@not ; [89:87] Pnz = UPp (enable-input-d)
[86]                reuse_a  [85] cluster_sz(2CTA)  [84] keep_a  [83] ws
[82]                reuse_b  [81] keep_b            [80:79] buffer
[78:75]             scaleU4
[74]                sh = ashift (A-tmem) / *0 (A-gdesc)
[73:72]∥[63]        opType = 0
[71:64]             URc  (D accumulator, TMEM)
[55:48]             URi  (disable-output-lane mask reg)
[47:40]             TABLES_URa_0(URe,URh)  (= URe; URh=URe+1)
[39:32]             URb  (B descriptor)
[31:24]             URa  (A descriptor / TMEM)
[15]                Pg_not ; [14:12] Pg = @UPg
```

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/utchmma_test.cu` → `tests/utchmma_test.cubin`. Decoder:
`tools/decode_utchmma.py` — all 4 round-trip (**ALL PASS**).

| Disassembly | Lo64 / Hi64 | opcode |
|-------------|-------------|:------:|
| `UTCHMMA.2CTA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UPT` | `…75ea` / `0ba0000a` | 0x15ea |
| `UTCHMMA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UPT, 0x3` | `…75ea` / `0b80180a` | 0x15ea |
| `UTCHMMA tmem[UR7], gdesc[UR8], tmem[UR6], tmem[UR4], idesc[UR5], UPT` | `…79ea` / `0b800006` | 0x19ea |
| `UTCHMMA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UP0` | `…75ea` / `0800000a` | 0x15ea |

Confirmed facts:
- Opcode 0x19ea (A-from-TMEM) vs 0x15ea (A-from-shared-descriptor).
- `.2CTA` = bit[85]; `scaleU4` = [78:75] (`, 0x3`); enable-input-d predicate
  `UPp` = [89:87] (`UP0` vs default `UPT`).
- tmemE/idesc adjacency verified: `tmem[UR4], idesc[UR5]` → field[47:40]=4.
- The `{disable-output-lane}` vector (passed as all-zero) encoded `URi`=URZ.

### PTX → SASS mapping
| PTX | SASS |
|-----|------|
| `tcgen05.mma.cta_group::1.kind::f16 [D], a-desc, b-desc, idesc, {mask}, p` | `UTCHMMA gdesc[URa], gdesc[URb], tmem[URc], tmem[URe], idesc[URh], UPp` |
| `…[D], [a-tmem], b-desc, idesc, {mask}, p` | `UTCHMMA tmem[URa], gdesc[URb], …` (opcode 0x19ea) |
| `…, p, scale-input-d` | `…, UPp, scaleU4` |
| `.cta_group::2` (mask vector size 8) | `.2CTA` |
| `.ashift` | `.ASHIFT` (A-tmem only) |

The `.kind::f16`/`.tf32`/`.f8f6f4` distinction is **not** in the mnemonic — all
map to `UTCHMMA`; the element types live in the 32-bit `idesc`. Integer
(`.kind::i8`) is a separate mnemonic `UTCIMMA`; FP8-quarter is `UTCQMMA`;
MX-scaled is `UTCMXQMMA`.

## Cross-references
- `notes/sm100/instr/utccp.md` — stages A/B matrices shmem→TMEM; shares the
  `UMMAA`/`UMMAB` 64-bit matrix-descriptor operand type.
- `notes/sm100/instr/ldtm.md` / `sttm.md` — move the D accumulator between TMEM
  and registers.
- `notes/sm100/instr/utcbar.md` — `tcgen05.commit`; commits UTCHMMA completion to
  an mbarrier.
- `notes/sm90/arch/wgmma.md`, `notes/sm90/arch/tcgen05_vs_wgmma.md` — the Hopper
  predecessor (HGMMA) and the microarch shift to TMEM/single-thread issue.
- Sibling MMAs (TODO): `UTCIMMA` (int), `UTCQMMA` (FP8), `UTCMXQMMA` (MX-scaled),
  `UTCOMMA`.

## Latency (sm100_latencies.txt)
`UTCHMMA` is a `TCMMA_OPS` / tensor-core async op (excluded from `UDP_subset`
fixed latency). Completion is mbarrier/scoreboard-tracked, not a fixed
latency-table cycle.

## Open questions
- Full 64-bit `UMMAA`/`UMMAB` matrix-descriptor + 32-bit `idesc` bit layouts —
  **documented** in `notes/sm100/arch/tcgen05_descriptors.md` (from PTX Tables
  43/45–47). Remaining: confirm the built-descriptor field placement against real
  descriptor-construction SASS.
- `tmemE` (URe) role — secondary accumulator/scale operand? (`ISRC_E_SIZE=64`.)
- `opType` [73:72]∥[63] is pinned 0 here — what selects nonzero values?
- Weight-stationary (`.WS`) + collector-buffer runtime semantics.
