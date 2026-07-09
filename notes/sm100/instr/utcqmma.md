# UTCQMMA / UTCMXQMMA — FP8/FP6/FP4 quarter-precision MMA  → PTX `tcgen05.mma.kind::f8f6f4` / `mxf*`

**Opcode mnemonic:** `UTCQMMA` + `UTCMXQMMA` — four opcodes shared between the two
mnemonics:
GEMM = `0b1010111101010` (0x15ea, A-gdesc) / `0b1100111101010` (0x19ea, A-tmem)
Block-scale = `0b1110111101010` (0x1dea, A-gdesc) / `0b1111111101010` (0x1fea, A-tmem)
**Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42)

New on sm100 (Blackwell). The SASS realizations of the FP8/FP6/FP4 quarter-
precision 5th-gen tensor-core MMA. `UTCQMMA` covers `.kind::f8f6f4` (FP8/FP6
element types, both plain GEMM/convolution and block-scaled); `UTCMXQMMA` covers
the MX-scaled small-integer kinds `.kind::mxf8f6f4`, `.kind::mxf4`,
`.kind::mxf4nvf4` (also block-scaled). They share the same four opcodes — the
disassembler picks the class name based on which form the compiler selected.

## Relationship to UTCHMMA and the opcode family
All five MMA mnemonic classes sit in the same 4-opcode encoding space. `opType`
at [73:72]∥[63] is the hardware discriminant:

| mnemonic | opType | opcodes | PTX kind(s) |
|---|---|---|---|
| `UTCHMMA` | **0** | 0x15ea, 0x19ea | `.kind::f16`, `.kind::tf32` |
| `UTCOMMA` | **1** | 0x15ea, 0x19ea | `.kind::mxf4`, `.kind::mxf4nvf4` |
| `UTCMXQMMA` | **3** | 0x1dea, 0x1fea | `.kind::mxf8f6f4` block-scale |
| `UTCQMMA` GEMM | **0** | 0x15ea, 0x19ea | `.kind::f8f6f4` (no block-scale) |
| `UTCQMMA` scale | **6** | 0x1dea, 0x1fea | `.kind::f8f6f4` / `.kind::mxf8f6f4` block-scale |

When two classes share the same opcode + `opType` (e.g. UTCHMMA vs UTCQMMA GEMM
both at `opType=0` on 0x15ea/0x19ea), the mnemonic is a disassembler label
tracking which PTX CLASS was selected — the element types live in `idesc`.
`UTCOMMA` (opType=1) and `UTCMXQMMA` (opType=3) are analysed in
`notes/sm100/instr/utcomma.md`. `UTCHMMA` (opType=0, GEMM/WS/conv forms) is in
`utchmma.md`.

Confirmed: compiling `.kind::f8f6f4` without `.block_scale` still produces
`UTCQMMA` at opcode 0x15ea — the same opcode `UTCHMMA` uses for f16. The `idesc`
descriptor carries the atype/btype (E4M3/E5M2/E2M3/E3M2/E2M1) to distinguish the
element types; the class name is a disassembler label, not a fundamentally
different encoding from UTCHMMA. `UTCMXQMMA` (opType=3) is for
`.kind::mxf8f6f4.block_scale` only — it shares the scale opcodes with
`UTCQMMA.scale` (opType=6). `UTCOMMA` (opType=1) is for FP4 `.kind::mxf4` /
`.mxf4nvf4`.

## The two encoding formats

### Non-scale (opcodes 0x15ea / 0x19ea) — `opType = 0`
Identical to `UTCHMMA` (see `utchmma.md`). All GEMM/convolution modifiers:
`WS`, `ASHIFT`, `A_REUSE`, `A_KEEP`, `B_REUSE`, `B_KEEP`, `BUFFER`, `scaleU4`,
`enable-input-d` (`UPp`), `disable-output-lane` (unused here).

### Block-scale (opcodes 0x1dea / 0x1fea) — `opType = 6`
The distinguishing field. Block-scale drops all convolution/WS modifiers and
adds a **scale operand in TMEM**:

```
[124:122]∥[109:105] opex
[121:116]           req_bit_set
[115:113]           src_rel_sb
[112:110]           dst_wr_sb = *7
[103:102]           pm_pred
[91]∥[11:0]         opcode     = 0x1dea / 0x1fea
[90]                UPp@not ; [89:87] Pnz = UPp (enable-input-d)
[86]                reuse_a ; [85] cluster_sz(2CTA) ; [84] keep_a
                     rest of WS/BUFFER/scaleU4/ashift bits freed (=0/*0)
[73:72]∥[63]        opType     = 6   ← the scale discriminant
[71:64]             URc  (D accumulator)
[55:48]             URi  (TMEMI: scale operand in TMEM — replaces disable-lane)
[47:40]             TABLES_URa_0(URe,URh)  (= URe; URh=URe+1)
[39:32]             URb  (B descriptor)
[31:24]             URa  (A descriptor / TMEM)
[15]                Pg_not ; [14:12] Pg = @UPg
```

Key changes from non-scale:
- **`URi`[55:48] now encodes a TMEM address** — the scale operand
  (`scale-A-tmem` or `scale-B-tmem` in PTX). In the non-scale form URi was the
  disable-output-lane mask register; here it is `TMEMI:tmemI[URi]` (a new operand
  type, `TMEMI TMEM`).
- **`WS`[83], `BUFFER`[80:79], `scaleU4`[78:75], `ashift`[74] freed** — block
  scaling is a different operational mode; these GEMM/conv controls don't apply.
- **`opType` = 6** is the hardware discriminant selecting the block-scale datapath
  (non-scale = 0).

`ISRC_A/B/C/E_SIZE = 64/64/32/64` (same as UTCHMMA). The scale-operand size is
not independently sized — scale_factor_data_ID in idesc (bits [4:5] for B-scale,
[29:30] for A-scale) selects which TMEM scale blocks are used.

### Operands (cuobjdump order, block-scale)
`UTCHMMA gdesc|tmem[A], gdesc[B], tmem[D], tmem[E], idesc, tmem[scale], UPp`

| pos | SASS | bits | PTX role |
|-----|------|------|----------|
| A | `gdesc/tmem[URa]` | [31:24] | A matrix |
| B | `gdesc[URb]` | [39:32] | B descriptor |
| D | `tmem[URc]` | [71:64] | accumulator |
| E | `tmem[URe]` | [47:40] | tmemE |
| idesc | `idesc[URh]` | URe+1 | instruction descriptor (32-bit, carries scale IDs) |
| scale | `tmem[URi]` | [55:48] | **scale operand in TMEM** (replaces disable-lane) |
| pred | `UPp` | [89:87]+[90] | enable-input-d |

`URe`/`URh` are still the adjacent register pair (`TABLES_URa_0`).

The PTX block-scale syntax carries both `[scale-A-tmem]` and `[scale-B-tmem]` as
separate operands, but the SASS has a **single** `tmem[scale]` operand — the
scale-factor data IDs in `idesc` select between A-scale and B-scale blocks, and
multiple MMAs may share the same scale TMEM using different data IDs. This is
consistent with the MX idesc layout (`tcgen05_descriptors.md`): both scale
matrices sit in TMEM at addresses derived from the same data-ID scheme.

## Verified encodings (cuobjdump, `.kind::mxf8f6f4.block_scale`, sm_100a)
Source: `tests/utcqmma_test.cu` → `tests/utcqmma_test.cubin`. Decoder:
`tools/decode_utcqmma.py` — all round-trip (**ALL PASS**).

| Disassembly | Lo64 / Hi64 | opcode | 2CTA | URi(scale) |
|---|---|---|---|---|
| `UTCQMMA.2CTA gdesc[UR6], …, tmem[UR12], UPT` | `…7dea` / `0ba0030a` | 0x1dea | 1 | UR12 |
| `UTCQMMA tmem[UR7], …, tmem[UR10], UPT` | `…7fea` / `0b800306` | 0x1fea | 0 | UR10 |
| `UTCQMMA gdesc[UR6], …, tmem[UR12], UPT` | `…7dea` / `0b80030a` | 0x1dea | 0 | UR12 |

## Cross-references
- `notes/sm100/instr/utchmma.md` — the parent mnemonic; non-scale encoding shared
  (opcodes 0x15ea/0x19ea, opType=0).
- `notes/sm100/arch/tcgen05_descriptors.md` — idesc Table 45 (base, f8f6f4
  atype/btype values: E4M3=0/E5M2=1/E2M3=3/E3M2=4/E2M1=5) and Tables 46/47
  (MX scale-factor data IDs, M>>7 granularity).
- `notes/sm100/arch/tcgen05_microarch_speculation.md` — geometry consistent with
  the non-scale case.
- `notes/sm100/instr/utcshift.md` — `.ashift` fuses into non-scale 0x19ea; scale
  variant has no ashift.

## Open questions
- How exactly does the single `tmem[scale]` address disambiguate between
  scale-A and scale-B operands in the block-scale PTX syntax? (The data IDs in
  idesc[4:5]/[29:30] are 2-bit selectors — likely byte-offsets within the
  same TMEM base or slot indices into a scale-table region.)
- `TMEMI` — the new TMEM scale operand type — is the 7th TMEM name (A/B/C/E/I/D
  across the family). Its exact TMEM column layout versus the scale block-vector
  size (`.scale_vec::1X/2X/4X` / `.block16/32`).
- Why does `.kind::f8f6f4` without block-scale print `UTCQMMA` rather than
  `UTCHMMA` when it uses the same opcodes? (Disassembler coherence: the class
  name tracks the PTX kind even though the encoding is identical.)

(Note: this note covers `UTCQMMA`; the UTCHMMA non-scale encoding is in
`utchmma.md` — they are the same encoding at opcodes 0x15ea/0x19ea. See the
opcode family table above.)
