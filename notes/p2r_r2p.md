# P2R / R2P — Predicate file ↔ GPR pack / unpack

**Opcode mnemonics:** `P2R` = **0x203** (RRR) + forms | `R2P` = **0x204** (RRR) + forms | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70

Move the warp's per-thread **predicate register file** (P0–P6 + condition state) to/from a GPR.
`P2R` packs predicates into a byte of a GPR; `R2P` unpacks a GPR byte back into predicates.
Used for predicate spill/restore and bit-mask ↔ predicate conversions.

## Semantics (verified)
- **`P2R.Bsel Rd, PR, Ra, mask`** — `Rd` = `Ra` with byte[`Bsel`] replaced by
  `(predicate_file & mask)`. `mask` selects which predicates are packed (bit i → Pi).
  Verified: `P2R R3, PR, R0, 0x7f` packs P0–P6 (mask 0x7f) into byte 0 of R3, other bytes from R0.
- **`R2P.Bsel PR, Ra, mask`** — writes the predicate file from byte[`Bsel`] of `Ra`, only the
  predicates selected by `mask`. Verified: `R2P PR, R2, 0xa` sets P1,P3 (mask 0xa) from byte 0
  of R2, leaving others unchanged.

`PR` is a single-valued token = "the predicate register file" (no encoding bits). `Bsel`
(`B3B0`: B0=0…B3=3) selects which of the 4 bytes of the GPR is packed into / unpacked from;
B0 is the default (hidden in text).

## Variant overview (operand shape of the `mask` operand)
| P2R opcode | R2P opcode | mask form |
|-----------|-----------|-----------|
| 0x203 | 0x204 | `Rb` register (RRR) |
| 0x803 | 0x804 | immediate (RIR) — **verified** |
| 0xa03 | 0xa04 | const bank (RCR) |
| 0x1a03 | 0x1a04 | const bank, extended (RCxR) |
| 0x1c03 | 0x1c04 | uniform register (RUR) |
| 0x803 (`p2r_simple_` ALT) | — | `P2R Rd, PR` (Ra/mask pinned RZ, pack all to B0) |

## Fields (128-bit)
| bits | field | P2R | R2P |
|------|-------|-----|-----|
| [91]∥[11:0] | `opcode` | 0x203/0x803/… | 0x204/0x804/… |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard |
| [23:16] | `Rd` | dest GPR | — (writes PR) |
| [31:24] | `Ra` | merge-base GPR | source GPR |
| [39:32] | `Rb` | mask (RRR) | mask (RRR) |
| [63:32] | imm | mask (RIR, 32-bit) | mask (RIR, 32-bit) |
| [77:76] | `insert`/`a_bsel` | byte select (B0–B3) | byte select (B0–B3) |
| [112:110] | `dst_wr_sb` | pinned 0x7 | pinned 0x7 |
| [124:122]∥[109:105] | `opex` | scheduling (+`.reuse`) | scheduling |

`B3B0`: B0=0, B1=1, B2=2, B3=3. `Rd`/`Ra`/`Rb` ≠ R254. IDEST: P2R=32, R2P=0.

## Cross-comparison (predicate-move family)
| op | dir | granularity |
|----|-----|-------------|
| **P2R** | predicate file → GPR byte | packs P0–P6 under mask |
| **R2P** | GPR byte → predicate file | unpacks under mask |
| **VOTE** | per-lane predicate → GPR (ballot) | warp-wide, one predicate |

## Latency (from sm_90_latencies.txt)
`int_pipe`, fixed-latency `COUPLED_MATH`. `OP_P2R`/`OP_R2P` appear in the
`NON_MATH_PRED_READERS`/predicate-connector groups (they read/write the whole PR file). Both
pin scoreboards (0x7).

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000007f00037803` | `0x000fca0000000000` | `P2R R3, PR, R0, 0x7f` (pack P0–P6) |
| `0x0000000a02007804` | `0x000fe40000000000` | `R2P PR, R2, 0xa` (unpack P1,P3) |

Decoder: `tools/decode_p2r_r2p.py` (real RIR vectors + RRR/byte-select round-trips pass).
Test: `tests/p2r_test.cu`.

### PTX→SASS mapping
- Packing several `setp` predicates into an integer bitmask → `P2R Rd, PR, Ra, mask`.
- Testing individual bits of an integer mask as branch/predicate conditions → `R2P PR, Ra, mask`.
- ptxas also uses these to spill/reload predicates under register pressure.

## Open questions
- Byte-select suffix rendering for `Bsel != B0` is reconstructed (only B0 captured); for R2P the
  `a_bsel` sits after `Ra` in the FORMAT, so it may render on the operand rather than the mnemonic.
- Exact packing of condition-code bits beyond P0–P6 within the byte (mask 0x7f covers 7 preds).
