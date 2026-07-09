# UTCOMMA / UTCMXQMMA — FP4 MX block-scale MMA  → PTX `tcgen05.mma.kind::mxf4` / `.mxf4nvf4`

**Opcode mnemonic:** `UTCOMMA` + `UTCMXQMMA` — shared opcode space, distinguished
by `opType` (the hardware discriminant):
`UTCOMMA` = `opType=1` on opcodes 0x15ea (A-gdesc) / 0x19ea (A-tmem)
`UTCMXQMMA` = `opType=3` on opcodes 0x1dea (A-gdesc) / 0x1fea (A-tmem)
**Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42)

New on sm100 (Blackwell). The SASS realizations of FP4 block-scaled MMA.
`UTCOMMA` covers `.kind::mxf4` and `.kind::mxf4nvf4` and adds the
`SCALE_VECTOR_SZ` modifier; `UTCMXQMMA` covers `.kind::mxf8f6f4` (FP8/FP6/FP4
MX, see `utcqmma.md` for that note). The mxf4 kinds only have block-scale;
there is no non-scale FP4 path.

## The complete MMA `opType` family
All five mnemonic classes share the same 128-bit encoding space; `opType` at
[73:72]∥[63] is the hardware multiplexer:

| mnemonic | opType | opcodes | PTX kind(s) |
|---|---|---|---|
| `UTCHMMA` | **0** | 0x15ea, 0x19ea | `.kind::f16`, `.kind::tf32` |
| `UTCOMMA` | **1** | 0x15ea, 0x19ea | `.kind::mxf4`, `.kind::mxf4nvf4` |
| `UTCMXQMMA` | **3** | 0x1dea, 0x1fea | `.kind::mxf8f6f4` block-scale |
| `UTCQMMA` (GEMM) | **0** | 0x15ea, 0x19ea | `.kind::f8f6f4` (no block-scale, encodes via `idesc` atype) |
| `UTCQMMA` (scale) | **6** | 0x1dea, 0x1fea | `.kind::mxf8f6f4` / `.f8f6f4` block-scale |

When two classes share the same `opType`+opcode (e.g. UTCHMMA vs UTCQMMA on
0x15ea, both `opType=0`), the mnemonic is a disassembler label tracking which
PTX CLASS was selected — the element types live in `idesc`, not the opcode.

## Semantics (UTCOMMA, `opType=1`)
Same `D=A*B+D` in TMEM, single-thread issued, asynchronous. Block-scale: the
scale matrices `[scale-A-tmem]` / `[scale-B-tmem]` are addressed via the `TMEMI`
operand (`URi`[55:48]), with scale-factor data IDs in `idesc` selecting between
A-scale and B-scale blocks. The `SCALE_VECTOR_SZ` modifier carries the
`.scale_vectorsize` qualifier from PTX (`.scale_vec::NX` or `.block16`/`.block32`).

### Key differences from the fp16/tf32 UTCHMMA:
- **No `WS`, no `BUFFER`, no `ASHIFT`, no `scaleU4`** — block-scale is a
  different operational mode; these GEMM/conv controls don't apply. Bits
  [83:74] are freed.
- **`URi`[55:48] encodes a TMEM scale operand** (`TMEMI:tmemI`) instead of the
  disable-output-lane mask.
- **`SCALE_VECTOR_SZ`** at bit [62] selects the block-scale grouping:
  `4X`=0 / `2X`=1 (PTX: `.scale_vec::4X`/`.block16` = 0, `.scale_vec::2X`/
  `.block32` = 1; default for `.mxf4` is `.block32` = 1).

## Variant overview (UTCOMMA)
| Class | Kind | Opcode | mod |
|---|---|---|---|
| `utcomma_1cta__A_gdesc` | CLASS | 0x15ea | `SCALE_VECTOR_SZ` |
| `utcomma_1cta__A_tmem` | CLASS | 0x19ea | `SCALE_VECTOR_SZ` |
| `utcomma_2cta__A_gdesc` / `_A_tmem` | CLASS | 0x15ea/0x19ea | + `.2CTA` |
| `…_one__*` (4) | ALT | — | `.ONE` (display-only) |

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `cluster_sz` | `ONLY1CTA`/`ONLY2CTA` | [85] | `.2CTA` |
| `scale_vector_sz` | `SCALE_VECTOR_SZ` | [62] | `.4X`(0) / `.2X`(1) — scale vector size |
| `reuse_a` | `REUSE_A` | [86] | `.A_REUSE` (collector on A, for inter-MMA reuse) |
| `keep_a` | `KEEP_A` | [84] | `.A_KEEP` (collector fill) |

(For `UTCMXQMMA` at `opType=3`, see the block-scale encoding in `utcqmma.md`
— same operand layout with `opType=3` instead of 1, no `SCALE_VECTOR_SZ`.)

## Bit layout (128-bit, UTCOMMA, opType=1)
```
[124:122]∥[109:105] opex      = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set
[115:113]           src_rel_sb
[112:110]           dst_wr_sb = *7
[103:102]           pm_pred
[91]∥[11:0]         opcode    = 0x15ea / 0x19ea
[90]                UPp@not ; [89:87] Pnz = UPp
[86]                reuse_a  [85] cluster_sz(2CTA)  [84] keep_a
[83:74]             — (WS/BUFFER/scaleU4/ashift freed)
[73:72]∥[63]        opType     = 1   ← UTCOMMA discriminant
[71:64]             URc (D accumulator)
[62]                scale_vector_sz (.4X=0, .2X=1)
[55:48]             URi (TMEMI: scale operand in TMEM)
[47:40]             TABLES_URa_0(URe,URh)  (= URe; URh=URe+1)
[39:32]             URb (B descriptor)
[31:24]             URa (A descriptor/TMEM)
[15]                Pg_not ; [14:12] Pg = @UPg
```
`ISRC_A/B/C/E_SIZE = 64/64/32/64` (same as UTCHMMA).

### Operands (cuobjdump order)
`UTCOMMA[.4X|2X] gdesc|tmem[A], gdesc[B], tmem[D], tmem[E], idesc, tmem[scale], UPp`

| pos | SASS | bits | PTX role |
|-----|------|------|----------|
| A | `gdesc/tmem[URa]` | [31:24] | A matrix |
| B | `gdesc[URb]` | [39:32] | B descriptor |
| D | `tmem[URc]` | [71:64] | accumulator |
| E | `tmem[URe]` | [47:40] | tmemE |
| idesc | `idesc[URh]` | URe+1 | instruction descriptor (32-bit, carries scale data IDs and K-dim + M>>7 per Table 47) |
| scale | `tmem[URi]` | [55:48] | scale operand in TMEM |
| pred | `UPp` | [89:87]+[90] | enable-input-d |

## Verified encodings (cuobjdump, `kind::mxf4.block_scale`, sm_100a)
Source: `tests/utcomma_test.cu` → `tests/utcomma_test.cubin`. Decoder: shared
with `decode_utchmma.py` (same opcodes, opType selects the path — TODO: merge
the scale/opType paths into a unified decoder).

| Disassembly | Lo64 / Hi64 | opType | scale_vec |
|---|---|---|---|
| `UTCOMMA.4X gdesc[UR6], …, tmem[UR12], UPT` | `…75ea` / `0b80000a` | 1 | 0 (.4X) |
| `UTCOMMA gdesc[UR6], …, tmem[UR12], UPT` | `…75ea` / `0b80000a` | 1 | 1 (.2X default) |

Confirmed: `.kind::mxf4` → `UTCOMMA` (opType=1); `.scale_vec::4X` →
`.4X` (bit62=0); `.scale_vec::2X` → (default, bit62=1). `.kind::mxf4nvf4`
also maps to `UTCOMMA` (verified with `.scale_vec::4X`).

## Cross-references
- `notes/sm100/instr/utchmma.md` — the fp16/tf32 baseline; opType=0, same
  opcodes, many more modifiers.
- `notes/sm100/instr/utcqmma.md` — FP8 quarter precision; opType=0 (non-scale)
  and opType=6 (block-scale on 0x1dea/0x1fea).
- `notes/sm100/arch/tcgen05_descriptors.md` — idesc Table 47 (mxf4/mxf4nvf4:
  atype/btype E2M1=1, K-dim at bit[31], M>>7, scale data IDs, scale matrix type
  UE8M0/UE4M3).
- `notes/sm100/arch/tcgen05_microarch_speculation.md` — M>>7 granularity matches
  the MX MMA geometry.

## Open questions
- The exact TMEM layout of scale blocks (`.scale_vec::1X/2X/4X` or
  `.block16/32`) and how the single `tmem[scale]` address + data IDs resolve
  to A-scale/B-scale per element.
- `opType` values 2, 4, 5 — unused in the dump: reserved, or used by other
  microarch modes not yet exposed?
