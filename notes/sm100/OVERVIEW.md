# sm100 (Blackwell) — encoding changes vs sm_90 (Hopper)

High-level diff of the nvdisasm-dumped ISA description (`sm100_instructions.txt`
+ `sm100_latencies.txt`) against the Hopper dumps. Produced with the ported
tooling: `tools/parse_sm100.py` → `sm100.json`, queried via
`tools/query_sm100.py` (same subcommands as `query_sm90.py`).

## Tooling port
Only two changes were needed to make the sm_90 extractor work on sm100:
1. Added the new base pipe **`ttu_pipe`** to `BASE_PIPES`.
2. Relaxed the sm_90-specific hard-coded validation counts (1589 variants /
   238 mnemonics) — the structural invariants (opcode presence, bit ranges
   ⊆[0,127], width==Σ span) still assert clean.

`parse_sm100.py` prints `validation OK`:

| metric | sm_90 | sm100 |
|--------|------:|------:|
| variants (CLASS + ALT) | 1589 (1168+421) | 1380 (975+405) |
| mnemonics | 238 | 261 |
| enums | 414 | 479 |
| decode tables | 84 | 85 |
| FUNIT fields | 2309 | 2116 |
| pipe entries | 277 | 308 |

## What did NOT change (the decode substrate is stable)
- **128-bit instruction word**, opcode still the 13-bit field
  `{bit[91], bits[11:0]}` (`BITS_13_91_91_11_0_opcode`).
- **Control/scheduling word is byte-identical** — all 565 named `FUNIT uC`
  control fields keep their exact bit positions (0 added / 0 removed / 0 moved).
  See `arch/control_codes.md` for the full comparison; the short version is that
  the wait mask, read/write scoreboards, opex/reuse overload, `usched_info`,
  `batch_t`, and `pm_pred` are all unchanged.
- Register widths (8-bit GPR, 6-bit uniform), predicate encoding (3-bit + not),
  scoreboard set (`SB0..SB5`), and the `opex_0..opex_9` tables are unchanged.

## Mnemonic-set diff (34 added / 11 removed)

**Added (34):**
`ACQSHMINIT CREDUX FADD2 FFMA2 FHADD FHFMA FMNMX3 FMUL2 LDCU LDT LDTM QADD4
QFMA4 QMUL4 REDS STT STTM UGETNEXTWORKID UMEMSETS UMOV.64 UREDGR USTGR
UTCATOMSWS UTCBAR UTCCP UTCHMMA UTCIMMA UTCLDSWS UTCMXQMMA UTCOMMA UTCQMMA
UTCSHIFT UTCSTSWS UVIRTCOUNT`

**Removed (11):**
`BGMMA BMMA HFMA2.MMA HGMMA IGMMA QGMMA RED SPMETADATA ULDC WARPGROUP
WARPGROUPSET`

Some removals are renames rather than deletions:
- `ULDC` → **`LDCU`** (uniform load-constant; classes renamed `uldc_*` →
  `ldcu_*`, still `udp_pipe`).
- `RED` → split into **`REDG` / `REDS` / `REDAS`** (global / shared / async-shared
  reductions).

## Major architectural changes

### 1. tcgen05 tensor cores replace wgmma (biggest change)
The entire Hopper warpgroup-MMA family is gone and replaced by a new
uniform-datapath tensor family. See `arch/tcgen05.md` (TODO) and the sm_90
`arch/tcgen05_vs_wgmma.md` for the microarch background.

- **Removed:** `HGMMA/IGMMA/BGMMA/QGMMA` (async wgmma), `BMMA`, `HFMA2.MMA`,
  `WARPGROUP`/`WARPGROUPSET`, and the whole `GMMA_SCOREBOARD` /
  `GMMA_GROUP_SCOREBOARD` latency machinery (`OPTIONAL_GSB` used 43× on sm_90 →
  0× on sm100).
- **Added (all on `udp_pipe`, uniform-register operands):**
  `UTCHMMA` (FP16/BF16), `UTCIMMA` (int), `UTCQMMA` (FP8/quarter),
  `UTCMXQMMA` (MX-scaled FP8/FP6/FP4), `UTCOMMA`. Plus tensor-core control:
  `UTCBAR` (barrier), `UTCCP` (copy), `UTCSHIFT`, and async warp-specialized
  `UTCLDSWS`/`UTCSTSWS`/`UTCATOMSWS`.
- **Tensor memory (TMEM):** new `LDT`/`STT` and `LDTM`/`STTM` load/store to the
  dedicated tensor-memory space. MMA accumulators/operands live in TMEM
  (`TMEMA`/`TMEMC`/`TMEME` operand types) rather than the register file.
- **Sync model shift:** wgmma tracked completion via a dedicated GMMA scoreboard
  (`OPTIONAL_GSB`). The `UTC*` ops instead carry the **standard** control block
  (`req_bit_set` wait mask + `src_rel_sb`), i.e. tensor-core completion folds
  back into the ordinary scoreboard mechanism (details in
  `arch/control_codes.md`).

### 2. New functional unit: `ttu_pipe` (tree-traversal / ray-tracing)
New base pipe in the latency `OPERATION SETS`, folded into `MIO_OPS`. Ops:
`TTUOPEN TTUCLOSE TTUGO TTULD TTUST TTUMACROFUSE TTUCCTL`. (Datacenter Blackwell
exposing RT-core-style traversal to SASS.)

### 3. Wider operand model
- MMA source roles extended from A–E to **A–I**: new `ISRC_H_SIZE` /
  `ISRC_I_SIZE` predicates (used by `UTC*` for descriptor/scale operands).
- Uniform register file gains range slots `URh`, `URi`, `URa_URc` in the
  latency `TABLE_TRUE(UGPR)`.
- Explicit **64-bit uniform ops**: `UMOV.64`, `UIADD3.64` (uniform-datapath
  64-bit address math).

### 4. New packed math
- **Packed FP32×2:** `FADD2` / `FMUL2` / `FFMA2` on `fmalighter_pipe`,
  `INST_TYPE_COUPLED_MATH`, with `F32x2` / `F32x2.HI_LO` / `F32x2.LO_HI`
  swizzles (new `ISWZA_fadd2` etc. enums). 64-bit dest (`IDEST_SIZE=64`).
- **FP16 quad:** `QFMA4` / `QMUL4` / `QADD4` on `fp16_pipe`.
- `FMNMX3` (3-input FP min/max), `FHADD` / `FHFMA` (half-input FP add/FMA).

### 5. Other additions / churn
- Uniform ops: `CREDUX` (uniform reduce, coupled), `UGETNEXTWORKID`,
  `USTGR`/`UREDGR` (uniform global store/reduce), `UMEMSETS`, `UVIRTCOUNT`,
  `ACQSHMINIT`.
- `CCTL` expanded from 7 → 27 variants (many new cache-control opcodes).
- **73 new opcode values**; enum churn +116 / −51, dominated by new
  narrow-float convert formats (`E5M2`/`E4M3`/`E2M3`/`E3M2`/`E2M1` — FP8/FP6/FP4)
  for the MX tensor path.
- `SPMETADATA` (sparse metadata) removed; sparsity now via `GENMETADATA` (present
  on both) and the MX/`UTC*` descriptors.

## Query cookbook
```bash
python3 tools/parse_sm100.py                 # regenerate sm100.json
python3 tools/query_sm100.py stats
python3 tools/query_sm100.py mnem UTCHMMA
python3 tools/query_sm100.py class utchmma_1cta__A_tmem
python3 tools/query_sm100.py layout fadd2_rc__RRR
python3 tools/query_sm100.py pipe TTUGO
```

## Progress
- **`LDTM`** (`tcgen05.ld`) — documented + decoder validated against real
  `sm_100a` cuobjdump vectors (`notes/sm100/instr/ldtm.md`,
  `tools/decode_ldtm.py`, `tests/ldtm_test.cu`). All 8 shape/num/pack variants
  round-trip. Confirmed: `nvcc -arch=sm_100a` compiles tcgen05 from PTX inline
  asm; `tcgen05.alloc`→`UTCATOMSWS.FIND_AND_SET`, `dealloc`→`UTCATOMSWS.AND`.
- **`STTM`** (`tcgen05.st`) — documented + decoder validated
  (`notes/sm100/instr/sttm.md`, `tools/decode_sttm.py`, `tests/sttm_test.cu`).
  All 8 variants round-trip. Store mirror of LDTM: opcode 0x19ed, scoreboard
  roles swapped (`src_rel_sb` active / `dst_wr_sb` pinned), data reg in [39:32],
  TMEM addr reg in [71:64], `EXPAND16BIT`(`.unpack::16b`). `tcgen05.wait::st`
  → `FENCE.VIEW.ASYNC.T`.
- **`UTCATOMSWS`** (TMEM allocator primitive) — documented + decoder validated
  (`notes/sm100/instr/utcatomsws.md`, `tools/decode_utcatomsws.py`,
  `tests/utcatomsws_test.cu`). 3 opcodes (CAS 0x13e3 / FAS 0x15e3 / OP 0x19e3),
  1CTA+2CTA vectors round-trip. `tcgen05.alloc` = `ELECT` + `UTCATOMSWS.FIND_AND_SET`
  spin loop (no hardware alloc opcode); `dealloc` = `UTCATOMSWS.AND`. Uses the
  new `$VQ_SW_STATE` virtual queue.
- **`UTCCP`** (`tcgen05.cp`) — documented + decoder validated
  (`notes/sm100/instr/utccp.md`, `tools/decode_utccp.py`, `tests/utccp_test.cu`).
  Opcode 0x19e7, all 8 shape/multicast/decompress variants round-trip. Async
  shmem→TMEM copy from a 64-bit UMMA matrix descriptor. Key finding: PTX `.shape`
  and `.multicast` are **fused** into one SASS `mode` field
  (`.64x128b.warpx2::02_13`→`.2x64dp128bit_lw02_lw13`). Uses `$VQ_TC_1CTA`/`2CTA`.
- **`tcgen05.fence::before/after_thread_sync`** — emit **zero SASS**
  (`notes/sm100/instr/tcgen05_fence.md`, `tests/tcgen05_fence_test.cu`,
  `tests/tcgen05_fence_ctx.cu`). Pure compile-time code-motion fences; ordering
  of the decoupled async ops rides on control-word scoreboards. Contrast
  `tcgen05.wait::st`→`FENCE.VIEW.ASYNC.T` (real).
- **`tcgen05.wait::ld`/`::st`** — completion waits, asymmetric
  (`notes/sm100/instr/tcgen05_wait.md`, `tests/tcgen05_wait_test.cu`).
  `wait::ld` emits **no opcode** (LDTM write-scoreboard + wait mask); `wait::st`
  → **`FENCE.VIEW.ASYNC.T`** (opcode 0x3c6, memType T=2 at [73:72]). The `.T`
  fence variant + `$VQ_FENCE_T` are **sm100-new** (sm_90 has only `.S`/`.G`).
- **`tcgen05.commit`** → **`UTCBAR`** (opcode 0x13e9) — documented + decoder
  validated (`notes/sm100/instr/utcbar.md`, `tools/decode_utcbar.py`,
  `tests/tcgen05_commit_test.cu`). Makes an mbarrier `[URa]` track async-op
  completion (non-blocking, vs the blocking `wait::*`). `.2CTA` (bit85),
  `.MULTICAST` (bit75, `ctaMask` in URc). Separate flush form at 0x9e9.
- **MMA family** — all 5 tcgen05 MMA mnemonics share 4 opcodes and are
  distinguished by `opType` [73:72]∥[63]:
  `HMMA`(0, f16/tf32) / `COMMA`(1, mxf4/mxf4nvf4) / `CIMMA`(2, i8) /
  `CMXQMMA`(3, mxf8f6f4 scale) / `CQMMA` GEMM(0, f8f6f4) / `CQMMA` scale(6).
  Documented: `utchmma.md`, `utcomma.md`, `utcimma.md`, `utcqmma.md`.
  Encodings + decoders validated on real sm_100a vectors.
- **`UGETNEXTWORKID`** (work-stealing `clusterlaunchcontrol.try_cancel`) —
  documented + decoder validated (`notes/sm100/instr/ugetnextworkid.md`,
  `tools/decode_ugetnextworkid.py`). Opcode 0x13ca, `$VQ_WORKID`=43.
  `SELFCAST`[72]=0 writes a 16B opaque response to `[URa]` with mbarrier
  completion at `[URb]` (register pair, `TABLES_URa_0` fusion). Lowering:
  `mbarrier.init`→`SYNCS.EXCH.64`, `try_cancel`→`UGETNEXTWORKID.SELFCAST`,
  `query_cancel`→`LDS.128`+standard bitfield decode (no unique opcode).
- **Fabric instructions** (`UBLKCP`/`UBLKRED`/`UBLKPF`) — documented
  (`notes/sm100/instr/fabric.md`). PTX ISA 9.3, assembled via CUDA 13.3 ptxas.
  `UBLKCP` (0x13ba) handles `fabric.try_put`/`try_get` (shared↔fabric async
  copy, `$VQ_TMA_UNORDERED_WR`); `SYNCS.ARRIVE.TRANS64.RED.A0TX` provides
  mbarrier completion tracking; `fabric.submit`→`UTMACMDFLUSH`+`CCTL.IVALL`.
  `ELECT` wrapping provides the "try" single-lane semantics. `try_red`/
  `UBLKRED`(0x13bb)/`UBLKPF`(0x13bc) spec-identified but ptxas 13.3.73 couldn't
  assemble the reduction forms.
- **TMA scatter/gather** (`UTMALDG`/`UTMASTG`) — documented
  (`notes/sm100/instr/tma_scatter_gather.md`). `cp.async.bulk.tensor.2d.tile::gather4`
  → `UTMALDG.2D.GATHER4` (0x15b4, mode=4/dim=1); `tile::scatter4` → `UTMASTG.2D.
  SCATTER4` (0x13b5, mode=2). Same `$VQ_TMA_UNORDERED_WR` + `ELECT` dispatch as
  all TMA ops. 5-element tensorCoords packed as 128-bit descriptor pair.
- **Packed FP32x2** — `FFMA2`/`FADD2`/`FMUL2` documented separately
  (`notes/sm100/instr/ffma2.md`, `fadd2.md`, `fmul2.md`). PTX `fma.f32x2` /
  `add.f32x2` / `mul.f32x2`. `fmalighter_pipe`, `INST_TYPE_COUPLED_MATH`. All
  share `ISWZA_fadd2` swizzle (F32x2/LO_HI/F32), per-element negate/absolute,
  shared rnd/ftz control. `FFMA2` = 5 variants (RRR/RRU/RRI/RIR/RUR), `FADD2`
  = 3 (RRR/RRU/RRI), `FMUL2` = 3 (RRR/RUR/RIR). Verified `FFMA2` via inline PTX
  asm.
- **`UMEMSETS`** (`st.bulk`) — documented (`notes/sm100/instr/umemsets.md`).
  Opcode 0x13cb, bulk shared-memory zero-init via AGU queue (`$VQ_AGU`).
  `URa`=dst addr, `URb`=URZ, `URc`=size/8. Verified on sm_100a.
- **`CREDUX`** (`redux.sync` F32 extension) — documented
  (`notes/sm100/instr/credux.md`). Opcode 0x2cc, coupled uniform reduction
  (`INST_TYPE_COUPLED_MATH`), sm100-new. Adds F32 (MIN/MAX + ABS/NaN) to the
  classic REDUX (0x3c4). `op`[79:78]: MAX=0, MAXABS=1, MIN=2, MINABS=3;
  `sz`[74:73]: U32=0, S32=1, F32=2; `NaN`[77]. Verified 3 forms on sm_100a.

## Open questions
- **Descriptors** — `notes/sm100/arch/tcgen05_descriptors.md` transcribes the
  64-bit shared-memory matrix descriptor (`gdesc`) and 32-bit instruction
  descriptor (`idesc`, 3 kind-dependent layouts) from PTX Tables 43/45–47. Shape
  (M/N/K), element types, transpose/negate, sparsity, swizzle, and MX scale IDs
  all live in these runtime descriptor values — not in the SASS opcode.

## Open questions
- Remaining `UTC*` (MMA family) bit-layout decode + cuobjdump vectors.
- TMEM addressing model — units (column vs byte) for `LDTM`/`STTM` confirmed as
  `tmem[URx+off]`, but the offset semantics still open.
- Semantics of the new MX scale operands (`scaleU4`, `SCALE_VECTOR_SZ`).
- `ttu_pipe` op encodings and latency rows.
- Whether the `LDT`/`STT`/`SIZE_ldt` ALTERNATEs are ever emitted (ptxas emits
  `LDTM`/`STTM` for every `tcgen05.ld`/`.st` shape, incl. `.32x32b.x1`).
