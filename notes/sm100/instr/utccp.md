# UTCCP — async shared-memory → TMEM copy  → PTX `tcgen05.cp`

**Opcode mnemonic:** `UTCCP` = `0b1100111100111` (0x19e7, 6631)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42) | **MEM_SCBD_TYPE:** `BARRIER_INST`

New on sm100 (Blackwell). The SASS realization of PTX **`tcgen05.cp`** — an
asynchronous copy of a matrix from **shared memory** (addressed by a 64-bit UMMA
matrix descriptor) into **Tensor Memory (TMEM)**, with optional on-the-fly
decompression of packed FP6/FP4 source formats to `b8x16`. It is the data-staging
path that feeds `UTC*MMA` operands into TMEM without going through registers.

## Semantics
`UTCCP.T.S[.mode][.srcfmt] tmem[URa + Sa_offset], gdesc[URb]`
- **`.T`** = destination is **T**ensor memory; **`.S`** = source is **S**hared
  memory. Both role tags are always printed by cuobjdump (the `OnlyT`/`SONLY`
  enums each have a single value — the direction is fixed shmem→TMEM).
- `gdesc[URb]` — a **64-bit** UMMA matrix descriptor (`UMMAB` operand,
  `ISRC_B_SIZE=64`) in a register pair starting at `URb`; describes the source
  matrix layout/base in shared memory (same descriptor format as wgmma/UTC MMA).
- `tmem[URa + Sa_offset]` — TMEM destination base (32-bit address in `URa`, plus
  a 32-bit signed immediate offset).

Async / decoupled: `INST_TYPE_DECOUPLED_RD_SCBD` + `src_rel_sb` active,
`dst_wr_sb` pinned `*7`. Like STTM it releases only a **read** scoreboard (it has
no register dest); TMEM-write completion is ordered out-of-band (the MMA that
consumes it, or a `tcgen05.wait`/fence).

## Variant overview
| Class | Kind | Opcode | cluster |
|-------|------|--------|---------|
| `utccp__1CTA` | CLASS | 0x19e7 | `1CTA` (`$VQ_TC_1CTA`) |
| `utccp__2CTA` | CLASS | 0x19e7 | `2CTA` (`$VQ_TC_2CTA`) |
| `utccp_one__1CTA` | ALT | 0x19e7 | + `.ONE` |
| `utccp_one__2CTA` | ALT | 0x19e7 | + `.ONE` |

The `_one_` alternates are encoding-identical (`.ONE` display-only). 2CTA maps
PTX `.cta_group::2` (copies into both peer CTAs' TMEM); it selects a different
virtual queue and sets bit[85].

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `mode` | `MODE_128dp256bit_…` | [88]∥[84:83] | shape + multicast, **fused** (see below) |
| `cluster_sz` | `ONLY1CTA`/`ONLY2CTA` | [85] (`ignoreKill`) | 1CTA / 2CTA |
| `src_fmt` | `SRC_FMT` | [81:80] (`selB`) | decompress source format |
| `dst` / `src` | `OnlyT` / `SONLY` | [86] / [87] | direction role tags (fixed) |

### The `mode` field fuses PTX `.shape` **and** `.multicast`
This is the key PTX→SASS insight: PTX spells shape and multicast separately, but
SASS packs both into one 3-bit `mode`:

| PTX `.shape`(`.multicast`) | SASS `mode` | val |
|----------------------------|-------------|----:|
| `.128x256b` | `128dp256bit` | 0 |
| `.4x256b` | `4dp256bit` | 2 |
| `.128x128b` | `128dp128bit` | 3 |
| `.64x128b.warpx2::02_13` | `2x64dp128bit_lw02_lw13` | 4 |
| `.64x128b.warpx2::01_23` | `2x64dp128bit_lw01_lw23` | 5 |
| `.32x128b.warpx4` | `4x32dp128bit` | 6 |
| — (illegal) | INVALID1 / INVALID7 | 1,7 |

The `2x64…` / `4x32…` names encode the multicast fan-out directly: `2x64` = two
warp-halves (warpx2), `lw02_lw13`/`lw01_lw23` = the warp-pair grouping, `4x32` =
warpx4 (all four warps). `dp` = datapath (lane group), matching the `NNdpMMbit`
convention from LDTM/STTM.

`SRC_FMT`: `nosrc_fmt`=0, `U4x16P64`=1 (PTX `.b4x16_p64`), `U6x16P32`=2 (PTX
`.b6x16_p32`), INVALID3. When set, dst is implicitly `.b8x16` (decompression).

## Bit layout (128-bit)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = read-scoreboard release
[112:110]           dst_wr_sb    = *7 (pinned: no write scoreboard)
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x19e7
[88]∥[84:83]        mode         = shape+multicast (3b, MSB at 88)
[87]                cas          = src  (SONLY role tag)
[86]                depth        = dst  (OnlyT role tag)
[85]                ignoreKill   = cluster_sz (2CTA)
[81:80]             selB         = src_fmt (decompress)
[79:72]∥[63:40]     Sb_offset    = Sa_offset (32-bit signed TMEM offset, split)
[39:32]             Rb           = URb (matrix descriptor, 64-bit pair)
[31:24]             Ra           = URa (TMEM base address)
[15]                Pg_not ; [14:12] Pg = @UPg (UniformPredicate)
```
Operand-placement note: unlike LDTM/STTM (which use `Rb`[39:32] for the TMEM
address), UTCCP puts the **descriptor** in `Rb`[39:32] and the **TMEM address**
in `Ra`[31:24] — the descriptor is the primary "source" operand.

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/utccp_test.cu` → `tests/utccp_test.cubin`. Decoder:
`tools/decode_utccp.py` — all 8 round-trip (**ALL PASS**).

| Disassembly | Hi64 | mode | src_fmt |
|-------------|------|:----:|:-------:|
| `UTCCP.T.S tmem[UR6], gdesc[UR8]` | `…08000000` | 0 `128dp256bit` | – |
| `UTCCP.T.S.128dp128bit …` | `…08180000` | 3 | – |
| `UTCCP.T.S.4dp256bit …` | `…08100000` | 2 | – |
| `UTCCP.T.S.2x64dp128bit_lw02_lw13 …` | `…09000000` | 4 | – |
| `UTCCP.T.S.2x64dp128bit_lw01_lw23 …` | `…09080000` | 5 | – |
| `UTCCP.T.S.4x32dp128bit …` | `…09100000` | 6 | – |
| `UTCCP.T.S.128dp128bit.U6x16P32 …` | `…081a0000` | 3 | 2 `.b6x16_p32` |
| `UTCCP.T.S.128dp128bit.U4x16P64 …` | `…08190000` | 3 | 1 `.b4x16_p64` |

(All lo64 = `0x00000008060079e7`: URa=UR6, URb=UR8, role bits src/dst set.)

Confirmed facts:
- `.128x256b`/`.x1` defaults elide to bare `UTCCP.T.S`.
- Multicast is **not** a separate SASS token — it is baked into `mode`
  (`.64x128b.warpx2::02_13` → `.2x64dp128bit_lw02_lw13`, `.32x128b.warpx4` →
  `.4x32dp128bit`). ptxas rejects `.64x128b`/`.32x128b` without the required
  multicast (matches the spec's shape↔multicast requirement).
- Decompression: `.b8x16.b6x16_p32` → `.U6x16P32`, `.b8x16.b4x16_p64` →
  `.U4x16P64` (bits [81:80]).

## Cross-references
- `notes/sm100/instr/ldtm.md`, `sttm.md` — register↔TMEM moves; UTCCP is the
  shmem→TMEM staging path (no register round-trip).
- `notes/sm100/instr/utcatomsws.md` — TMEM allocator; UTCCP writes into the TMEM
  region it hands out.
- `UMMAB`/`gdesc` matrix descriptor — shared with the `UTC*MMA` ops (same 64-bit
  descriptor format).
- `$VQ_TC_1CTA`/`$VQ_TC_2CTA` — the tensor-core copy virtual queues, distinct
  from `$VQ_TMEM` (load/store) and `$VQ_SW_STATE` (allocator).

## Latency (sm100_latencies.txt)
`UTCCP` = part of `OP_TMA_TC` (line 214, with the UTMA* and other UTC* ops);
subtracted from `UDP_subset` and handled as a scoreboard-gated async op.
Completion of the actual shmem→TMEM copy is tracked via the read scoreboard /
downstream MMA, not a fixed latency-table entry.

## Open questions
- Exact bit-layout of the 64-bit `gdesc` matrix descriptor (`URb` pair) — shared
  with UTC MMA; document once UTCHMMA is analyzed.
- TMEM addressing units for `tmem[URa+off]` (same open question as LDTM/STTM).
- Runtime meaning of the `.ONE` alternate (encoding-identical here).
- Whether `depth`/`cas` field names ([86]/[87]) carry any meaning beyond the
  fixed `.T`/`.S` role tags (they are pinned by the single-value `OnlyT`/`SONLY`
  enums).
