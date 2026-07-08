# P2R — Predicate file → GPR pack

**Opcode mnemonic:** `P2R` = **0x203** (RRR) + forms | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70

Pack the warp's per-thread **predicate register file** (P0–P6 + condition state) into a byte of a GPR. Used for predicate spill/restore and bit-mask ↔ predicate conversions.

## Semantics (verified)
`P2R.Bsel Rd, PR, Ra, mask` — `Rd` = `Ra` with byte[`Bsel`] replaced by `(predicate_file & mask)`. `mask` selects which predicates are packed (bit i → Pi).
Verified: `P2R R3, PR, R0, 0x7f` packs P0–P6 (mask 0x7f) into byte 0 of R3, other bytes from R0.

`PR` is a single-valued token = "the predicate register file" (no encoding bits). `Bsel` (`B3B0`: B0=0…B3=3) selects which of the 4 bytes of the GPR is packed into; B0 is the default (hidden in text).

## Variant overview (operand shape of the `mask` operand)
| opcode | mask form |
|--------|-----------|
| 0x203 | `Rb` register (RRR) |
| 0x803 | immediate (RIR) — **verified** |
| 0xa03 | const bank (RCR) |
| 0x1a03 | const bank, extended (RCxR) |
| 0x1c03 | uniform register (RUR) |
| 0x803 (`p2r_simple_` ALT) | `P2R Rd, PR` (Ra/mask pinned RZ, pack all to B0) |

## Fields (128-bit)
| bits | field | P2R |
|------|-------|-----|
| [91]∥[11:0] | `opcode` | 0x203/0x803/… |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [23:16] | `Rd` | dest GPR |
| [31:24] | `Ra` | merge-base GPR |
| [39:32] | `Rb` | mask (RRR) |
| [63:32] | imm | mask (RIR, 32-bit) |
| [77:76] | `insert`/`a_bsel` | byte select (B0–B3) |
| [112:110] | `dst_wr_sb` | pinned 0x7 |
| [124:122]∥[109:105] | `opex` | scheduling (+`.reuse`) |

`B3B0`: B0=0, B1=1, B2=2, B3=3. `Rd`/`Ra`/`Rb` ≠ R254. IDEST: 32.

## Cross-comparison (predicate-move family)
| op | dir | granularity |
|----|-----|-------------|
| **P2R** | predicate file → GPR byte | packs P0–P6 under mask |
| **R2P** | GPR byte → predicate file | unpacks under mask |
| **VOTE** | per-lane predicate → GPR (ballot) | warp-wide, one predicate |

## Latency (from sm_90_latencies.txt)
`int_pipe`, fixed-latency `COUPLED_MATH`. `OP_P2R` appears in `NON_MATH_PRED_READERS`/predicate-connector groups (reads the whole PR file). Pins scoreboard (0x7).

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000007f00037803` | `0x000fca0000000000` | `P2R R3, PR, R0, 0x7f` (pack P0–P6) |

Decoder: `tools/decode_p2r_r2p.py` (real RIR vectors + RRR/byte-select round-trips pass).
Test: `tests/p2r_test.cu`.

### PTX→SASS mapping
- Packing several `setp` predicates into an integer bitmask → `P2R Rd, PR, Ra, mask`.
- ptxas also uses these to spill/reload predicates under register pressure.

## Open questions
- Byte-select suffix rendering for `Bsel != B0` is reconstructed (only B0 captured).
- Exact packing of condition-code bits beyond P0–P6 within the byte (mask 0x7f covers 7 preds).
