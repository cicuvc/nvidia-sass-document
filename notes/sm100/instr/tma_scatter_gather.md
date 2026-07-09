# TMA scatter/gather — `UTMALDG.GATHER4` / `UTMASTG.SCATTER4`  → PTX `cp.async.bulk.tensor.tile::gather4/scatter4`

**PTX:** `cp.async.bulk.tensor.2d.tile::gather4` / `.tile::scatter4`
(§9.7.9.26.5.2, PTX ISA 9.3, `sm_100a+`)
**SASS:** `UTMALDG` (load, 0x13b4 TILED / 0x15b4 GATHER4) — `UTMASTG` (store, 0x13b5)
**Pipe:** `udp_pipe` | **VIRTUAL_QUEUE:** `$VQ_TMA_UNORDERED_WR`
**Status:** confirmed on `sm_100a` with CUDA 13.3 ptxas
(`tests/fabric_test.cu` extended with gather4/scatter4 PTX).

`cp.async.bulk.tensor` is the **tensor-map-based** async copy superset of
`cp.async.bulk`. The `.tile::gather4` and `.tile::scatter4` load-mode qualifiers
compress or expand the tensor layout: gather4 combines four source rows into one
destination tile; scatter4 splits one source tile into four destination rows.
These ride on the existing **`UTMALDG`** / **`UTMASTG`** TMA load/store ops with
the new mode values.

## Lowering
| PTX | SASS | opcode | mode bits |
|-----|------|:------:|-----------|
| `.tile::gather4` (global→shared) | `UTMALDG.2D.GATHER4 [URb], [URa]` | 0x15b4 | mode=4, dim=1(2D) |
| `.tile::scatter4` (shared→global) | `UTMASTG.2D.SCATTER4 [URa], [URb]` | 0x13b5 | mode=2, dim=1(2D) |
| `.tile` (base) | `UTMALDG.1D.TILED …` / `UTMASTG.1D.TILED …` | 0x13b4 / 0x13b5 | mode=0 |

All are `ELECT`-wrapped (single leader lane issues the TMA command), asynchronous
+ mbarrier-completion-tracked (load) or bulk-group (store). The tensorCoords
`{col, row0..row3}` are the 5 u32 coordinates packed into a 128-bit descriptor
register pair passed to the TMA engine.

## Encoding (`UTMALDG`/`UTMASTG` common)
```
[124:122]∥[109:105] opex       = TABLES_opex_0(batch_t, usched_info)
[91]∥[11:0]         opcode     = 0x13b4/0x15b4 (load) / 0x13b5 (store)
[85]                cluster_sz (2CTA)
[84:82]             mode       = TILED(0) / GATHER4(4, load) / SCATTER4(2, store)
[81:79]             dim        = TENSORDIM: 1D(0) .. 5D(4)
[76]                = 0
[39:32]             URb (dst shared-memory address; tensorMap ptr on store)
[31:24]             URa (tensorMap descriptor ptr pair; src smem on store)
```

## Cross-references
- `notes/sm100/instr/fabric.md` — TMA unordered-write queue (`$VQ_TMA_UNORDERED_WR`),
  same `ELECT` leader-lane dispatch.
- `notes/sm90/arch/tma_mbarrier.md` — TMA + mbarrier background (the Hopper-era
  ancestor; UTMALDG/UTMASTG are the Blackwell TMA load/store primitives).
- `notes/sm100/arch/tcgen05_microarch_speculation.md` — the tensor-map descriptor
  format fed from global memory overlaps conceptually with the tcgen05 `gdesc`.

## Open questions
- `IM2COL`/`IM2COL_W`/`IM2COL_W_128` modes — im2col kernel offload to the TMA
  (same UTMALDG/UTMASTG ops, different mode values). Not tested here.
- The exact 128-bit descriptor register pair layout for tensorCoords + tensorMap
  pointer — this is the TMA's internal descriptor, parallel to the tcgen05
  `gdesc`.
- Whether GATHER4 exists on the store side or SCATTER4 on the load side — the
  opcode family (0x13b4/0x13b5 vs 0x15b4) suggests GATHER4 may be load-only and
  SCATTER4 store-only, matching the PTX syntax asymmetry.
