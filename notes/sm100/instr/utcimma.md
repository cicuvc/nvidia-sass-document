# UTCIMMA — integer MMA  → PTX `tcgen05.mma.kind::i8`

**Opcode mnemonic:** `UTCIMMA` — `opType = 2` on opcodes 0x15ea (A-gdesc) /
0x19ea (A-tmem)
**Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42)

New on sm100 (Blackwell). `UTCIMMA` = the SASS realization of PTX
**`tcgen05.mma.kind::i8`** (signed/unsigned 8-bit integer MMA). Encoding-
identical to `UTCHMMA` (`opType=0`) except `opType=2` — same modifier set,
operand layout, and GEMM/convolution/WS/ASHIFT forms. The integer-specific
behaviour (saturate, U8 vs S8) lives entirely in the `idesc` descriptor.

## The complete `opType` map (updated)
| mnemonic | opType | opcodes | PTX kind(s) |
|---|---|---|---|
| `UTCHMMA` | **0** | 0x15ea, 0x19ea | `.kind::f16`, `.kind::tf32` |
| `UTCOMMA` | **1** | 0x15ea, 0x19ea | `.kind::mxf4`, `.kind::mxf4nvf4` (block-scale, no WS/conv) |
| **`UTCIMMA`** | **2** | 0x15ea, 0x19ea | **`.kind::i8`** |
| `UTCMXQMMA` | **3** | 0x1dea, 0x1fea | `.kind::mxf8f6f4` block-scale |
| `UTCQMMA` GEMM | **0** | 0x15ea, 0x19ea | `.kind::f8f6f4` (no block-scale) |
| `UTCQMMA` scale | **6** | 0x1dea, 0x1fea | `.kind::f8f6f4` / `.kind::mxf8f6f4` block-scale |

Values 2 belongs to UTCIMMA; the full opType field is 3 bits ([73:72]∥[63]),
so values 0–7 exist — only 0,1,2,3,6 are used in this dump; 4,5,7 are reserved.

## Encoding = UTCHMMA, just `opType=2`
`UTCIMMA` shares the exact modifier set and operand layout from `utchmma.md`:
`WS`[83], `ASHIFT`[74], `A_REUSE`[86], `A_KEEP`[84], `B_REUSE`[82],
`B_KEEP`[81], `BUFFER`[80:79], `scaleU4`[78:75], `UPp`[89:87]+[90],
disable-output-lane (`URi`[55:48]). `URe`/`URh` are the adjacent register pair
(`TABLES_URa_0`). Only `opType` changes:

```
[73:72]∥[63]        opType     = 2   ← UTCIMMA discriminant
```

The integer specifics are in `idesc` (Table 45, `tcgen05_descriptors.md`):
- [3] saturate: no-sat=0 / sat=1 (only meaningful with i8)
- [7:9] atype: U8=0 / S8=1
- [10:12] btype: U8=0 / S8=1
- [4:5] dtype: S32=2
- [13:14] negate A/B: only 0 (no integer negate)

## Verified encoding (cuobjdump, `.kind::i8`, sm_100a)
`/tmp/i8_probe`: `.kind::i8` without WS → `UTCIMMA gdesc[UR6], gdesc[UR8],
tmem[UR10], tmem[UR4], idesc[UR5], UPT` at lo64 `0x00ff0408060075ea` — identical
encoding to UTCHMMA except `opType=2`.

## Cross-references
- `notes/sm100/instr/utchmma.md` — the parent encoding (opType=0); all modifiers
  and bit positions are identical.
- `notes/sm100/instr/utcomma.md`, `utcqmma.md` — the other `opType` variants.
- `notes/sm100/arch/tcgen05_descriptors.md` — idesc Table 45: saturate[3],
  atype/btype[7:12], dtype=S32=2, no negate.
- `notes/sm90/arch/tcgen05_vs_wgmma.md` — the Hopper predecessor had no separate
  integer MMA; wgmma used the same HGMMA for both fp16 and int8. The split into
  separate CLASSes (but shared encoding) is a Blackwell refinement.
