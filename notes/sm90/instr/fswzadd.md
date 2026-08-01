# FSWZADD — FP32 swizzle-add (cross-lane quad partial reduction)

**Opcode mnemonic:** `FSWZADD` = `0b100000100010` = **0x822** | **Pipe:** `fmalighter_pipe` (FP32 FMA pipe, FMAI_OPS) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70 (crucible idx 15)

FP32 **swizzle-add**: within a thread **quad** (4 lanes), combine each lane's `Ra` with the
quad-swizzled `Rc` values, applying a per-lane +/−/0 sign pattern (`npCtrl`). The single-
instruction primitive behind quad partial reductions and screen-space **derivatives**
(ddx/ddy) — and the fused shuffle+add butterfly for small FP32 warp reductions.

> **Status: semantics resolved on sm_120 with a clean hand-built ELF (2026-08):
> `FSWZADD.NDV` = signed lane-local add `s_a·Ra + s_b·Rc` (npCtrl pair signs,
> lane%4); `FSWZADD` (nondv) = 0.0.  Cross-lane quad swizzle not observable
> from compute.  Encoding verified against the CLASS spec; the earlier
> patch-based "Rd=Ra" result was a control-word artifact (see Resolved).**
> nvcc does not emit FSWZADD from compute paths (it is a graphics/derivative
> primitive); examples are round-trip constructions plus the clean kernel probe.

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
- **Cross-lane quad swizzle unobservable from compute**: even with clean
  encoding, Rc contributes only lane-locally.  Presumably the graphics
  pixel-quad network the npCtrl pairs address is not populated in a CUDA
  launch; needs a graphics-context capture to confirm.
- `NDV` naming meaning (likely "no default value": without it the quad
  network supplies a default 0) unconfirmed.
- Which toolchain/graphics path emits it on sm_90 (not seen in the compute libraries scanned).

## Resolved (SM120 empirical, clean hand-built ELF, 2026-08)

Re-probed with a **clean hand-built ELF** once the assembler gained S2R/LDG
support: `S2R` lane-id → per-lane `LDG` of Ra/Rc → `FSWZADD` → `STG` result,
with correct scoreboards (`LDCU.64 UR4` desc, S2R wr=SB0, LDG wr=SB1/SB2,
first-use `req`).  All 256 npCtrl patterns and modifier combos tested.

**Finding: the NDV bit is the master switch.**
- `FSWZADD` (nondv): **Rd = 0.0**, regardless of Ra, Rc, npCtrl, rounding.
- `FSWZADD.NDV`: **Rd = s_a·Ra + s_b·Rc**, purely **lane-local** (no
  cross-lane quad contribution reachable from compute).

**npCtrl semantics (NDV):** the 8-char P/N/Z string is 4 base-4 pairs, one
per quad lane; **lane%4 selects pair k**, and pair "ab" means *a* scales Ra
(`P`=+1, `N`=−1, `Z`=0) and *b* scales Rc (`P`=+1, `N`=−1).  Verified:
`PPPPPPPP`=Ra+Rc, `NPPNNPPN`(NP,PN,NP,PN)=[−Ra+Rc, +Ra−Rc, …] per lane,
`NPNPNPNP`=Rc−Ra, `ZPZPZPZP`=Rc.

**Other verified modifiers:** rounding `Round1` at [79:78] behaves (RN/RP
confirmed on 1e8+1 → 100000000/100000008, ulp=8); `.FTZ` flushes denormals;
NaN/Inf propagate.

**The earlier patch-based probe was wrong.**  Binary-patching an FFMA
placeholder (reusing FFMA's hi64 scheduling/control word) reported "Rd = Ra
pass-through" on sm_75 + sm_120.  The clean encoding shows that result was
an **artifact of the bogus control word** (the FFMA hi64 carries a different
opex/operand-bank layout than FSWZADD).  Discard that conclusion; the note's
original "swizzle network unreachable" hypothesis is superseded by the
signed lane-local add above.

**Open:** the true quad swizzle (cross-lane Rc routing) is not observable
from compute even with clean encoding — the graphics pixel-quad network that
the npCtrl pairs presumably address is not populated in a CUDA launch.
