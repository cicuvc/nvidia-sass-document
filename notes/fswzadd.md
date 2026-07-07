# FSWZADD — FP32 swizzle-add (cross-lane quad partial reduction)

**Opcode mnemonic:** `FSWZADD` = `0b100000100010` = **0x822** | **Pipe:** `fmalighter_pipe` (FP32 FMA pipe, FMAI_OPS) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70 (crucible idx 15)

FP32 **swizzle-add**: within a thread **quad** (4 lanes), combine each lane's `Ra` with the
quad-swizzled `Rc` values, applying a per-lane +/−/0 sign pattern (`npCtrl`). The single-
instruction primitive behind quad partial reductions and screen-space **derivatives**
(ddx/ddy) — and the fused shuffle+add butterfly for small FP32 warp reductions.

> **Status: encoding + npCtrl verified against the spec enum; NO real SASS capture and the exact
> swizzle math is partly inferred.** nvcc did not emit FSWZADD from the compute paths tried
> (float `cg::reduce` over quads/warps, `__shfl_xor` butterflies) and it is absent from
> cufft/cublasLt — it is chiefly a graphics/derivative primitive. Encoding is from the CLASS
> spec; examples are round-trip constructions.

## Semantics (inferred)
For each lane in a quad, `Rd = Σ_quad ( sign · swizzle(Rc) )  (± Ra)`, where the signs come from
`npCtrl` (`P`=+, `N`=−, `Z`=0). Result rounded per `Round1`; optional flush-to-zero (`FTZ`).
The classic use forms quad differences (e.g. `v1−v0`, `v2−v0`) for derivatives, and 4-way
partial sums for reductions.

## npCtrl (the swizzle sign pattern) — `NP` enum, 256 values
Rendered as an **8-char P/N/Z string** = **4 pairs**, one pair per quad lane, each pair a base-4
digit: `PP`=0, `PN`=1, `NP`=2, `ZP`=3 (MSB pair leftmost). E.g. value 0=`PPPPPPPP`,
1=`PPPPPPPN`, 128=`NPPPPPPP`, 255=`ZPZPZPZP`. (Generation verified against the spec enum in
`tools/decode_fswzadd.py`.) `npCtrl` occupies the `Rb` operand slot [39:32].

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x822 | 13-bit |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | FP32 result |
| [31:24] | `Ra` | Register | own-lane FP32 source |
| [71:64] | `Rc` | Register | swizzled FP32 source |
| [39:32] | `Rb` = `npCtrl` | `NP` | 8-bit per-quad-lane sign pattern |
| [79:78] | `stride` = `rnd` | `Round1` | RN=0(hidden), RM=1, RP=2, RZ=3 |
| [80] | `UPq_not` = `ftz` | `FTZ` | noftz=0 / FTZ=1 |
| [77] | `ntz` = `ndv` | `NDV` | nondv=0 / NDV=1 |
| [124:122]∥[109:105] | `opex` | TABLES_opex_3(batch_t,usched_info,reuse_a,reuse_c) | scheduling + `.reuse` |
| [103:102] | `pm_pred` | perfmon predicate | |
| [115:113]/[112:110] | `src_rel_sb`/`dst_wr_sb` | pinned 0x7 | fixed-latency |

`Rd`/`Ra`/`Rc` ≠ R254. IDEST/ISRC_A/ISRC_C = 32 (ISRC_B=0; the `Rb` slot carries `npCtrl`, not a
register read).

## Cross-comparison
| op | reduction | domain |
|----|-----------|--------|
| **FSWZADD** | quad ±/0 FP32 combine (swizzle) | derivatives, quad/butterfly FP reduce |
| **REDUX** | full-warp int reduce | uniform integer reductions |
| **SHFL + FADD** | generic cross-lane | any warp shuffle reduce |

## Latency (from sm_90_latencies.txt)
`fmalighter_pipe` member (`FMAI_OPS`), fixed-latency `COUPLED_MATH` (scoreboards pinned) — same
class as `FFMA`/`FADD`/`FMUL`, i.e. a fast FP32 op with cross-lane quad routing.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64 | Reconstruction |
|------|------|----------------|
| `0x0000000002047822` | `0x0000000000000006` | `FSWZADD R4, R2, R6, PPPPPPPP` |
| `0x0000009902047822` | `0x0000000000000006` | `FSWZADD R4, R2, R6, NPPNNPPN` |
| `0x0000009902047822` | `0x000000000000c006` | `FSWZADD.RZ R4, R2, R6, NPPNNPPN` |
| `0x0000000002047822` | `0x0000000000010006` | `FSWZADD.FTZ R4, R2, R6, PPPPPPPP` |

Decoder + round-trip/NP-enum test: `tools/decode_fswzadd.py`.

## Open questions
- **No real vector**; the exact per-lane swizzle mapping (which quad lane feeds which output,
  how the 4 sign-pairs map to Ra vs Rc terms) is inferred — needs a capture to pin down.
- `NDV` meaning (likely "no default value"/denormal handling) unconfirmed.
- Which toolchain/graphics path emits it on sm_90 (not seen in the compute libraries scanned).
