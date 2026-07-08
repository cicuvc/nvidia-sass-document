# DMUL — FP64 Multiply

**Opcode:** `0x228` (RRR), `0x828` (RsIR, immediate), `0xa28` (RCR), `0x1a28` (RCxR), `0x1c28` (RUR)
**Pipe:** `fma64lite_pipe`, `$VQ_REDIRECTABLE` | **TYPE:** `INST_TYPE_COUPLED_EMULATABLE` | since sm_70

## Semantics

`Rd = (±|Ra|) * (±|Rb|)` in double-precision (FP64). All operands are 64-bit register pairs
(even-aligned, ≠R254). 2-operand FP64 multiply — same structural family as FMUL (F32) and
HMUL2 (F16). No FTZ (FP64 keeps denormals); IEEE rounding mode via `.rnd`.

## Format

`@Pg DMUL{.rnd} Rd, [-]|[||]Ra{.reuse}, [-]|[||]Rb{.reuse}`

## Modifiers / fields (128-bit)

| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x228… selects operand form |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | result pair |
| [31:24] | `Ra` | multiplicand A pair |
| [39:32] | `Rb` | multiplicand B pair (RRR) |
| [63:32] | imm | FP64 immediate high-32b (RsIR) |
| [37:32] | `Ra_URb` | uniform B (RUR) |
| **[79:78]** | **`stride`=`rnd`** | **RN=0 (hidden), RM=1, RP=2, RZ=3 — a simple 2-bit field** |
| [72]/[73] | `Ra@negate`/`Ra@absolute` | `-Ra` / `|Ra|` |
| [63]/[62] | `Rb@negate`/`Rb@absolute` | `-Rb` / `|Rb|` (RRR form) |

**Correction:** an earlier version of this note claimed "rounding modifier encoding is managed
via opex/scoreboard configuration rather than a simple 2-bit field." That was **wrong** — an
artifact of recording only Lo64. `rnd` is a plain 2-bit field at **[79:78] in Hi64**, identical
to DADD/DFMA; verified below.

## Verified encodings (sm_90, CUDA 13.1 — full lo64 + hi64)

RRR form, `Rd`=R6, `Ra`=R2, `Rb`=R4 (four rounding modes share Lo64; only Hi64 `rnd` changes):

| Disassembly | Lo64 | Hi64 | PTX |
|-------------|------|------|-----|
| `DMUL R6, R2, R4` | `0x0000000402067228` | `0x008fce0000000000` | `mul.rn.f64` |
| `DMUL.RM R6, R2, R4` | `0x0000000402067228` | `0x008fce0000004000` | `mul.rm.f64` |
| `DMUL.RP R6, R2, R4` | `0x0000000402067228` | `0x008fce0000008000` | `mul.rp.f64` |
| `DMUL.RZ R6, R2, R4` | `0x0000000402067228` | `0x008fce000000c000` | `mul.rz.f64` |
| `DMUL R4, R2, 2.5` | `0x4004000002047828` | `0x004fce0000000000` | `mul` by imm (RsIR) |

`rnd`[79:78] = Hi64 bits[15:14]: RN=0, RM=1(0x4000), RP=2(0x8000), RZ=3(0xc000). FP64 immediate
= high 32 bits of the double at [63:32] (`2.5`=0x40040000…). Decoder: `tools/decode_dmul.py`
(all vectors pass). Test: `tests/dmul_test.cu`.

## DMUL vs DFMA vs DADD

| Property | DADD (idx 123) | DMUL (idx 124) | DFMA (idx 122) |
|----------|:---:|:---:|:---:|
| Operation | `±a ± b` | `a * b` | `a*b + c` |
| Opcode base | 0x229 | 0x228 | 0x22b |
| Variants | 5 | 5 | 9 |
| ISRC_C_SIZE | 0 | 0 | 64 |
| `rnd` | [79:78] | [79:78] | [79:78] |

All three: `fma64lite_pipe`, `COUPLED_EMULATABLE`, `VQ_REDIRECTABLE`, in `FMALITE_OPS`.

## PTX to SASS

| PTX | SASS |
|-----|------|
| `mul.rn.f64 %rd, %ra, %rb` | `DMUL Rd, Ra, Rb` |
| `mul.rm.f64` / `.rp` / `.rz` | `DMUL.RM` / `.RP` / `.RZ` |
| `(-a)*b` | `DMUL Rd, -Ra, Rb` (negate bit [72]) |
| `a * const` | RsIR immediate (`DMUL Rd, Ra, <double>`) if it fits high-32b, else RCR |

## Open questions

- Const-bank (RCR/RCxR) text form unverified (only RRR/imm exercised).
