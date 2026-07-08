# R2P — GPR → Predicate file unpack

**Opcode mnemonic:** `R2P` = **0x204** (RRR) + forms | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70

Unpack a GPR byte back into the warp's per-thread **predicate register file** (P0–P6 + condition state). The reverse of `P2R`.

## Semantics (verified)
`R2P.Bsel PR, Ra, mask` — writes the predicate file from byte[`Bsel`] of `Ra`, only the predicates selected by `mask`.
Verified: `R2P PR, R2, 0xa` sets P1,P3 (mask 0xa) from byte 0 of R2, leaving others unchanged.

`PR` is a single-valued token = "the predicate register file" (no encoding bits). `Bsel` (`B3B0`: B0=0…B3=3) selects which byte of the GPR is unpacked from; B0 is the default (hidden in text).

## Variant overview (operand shape of the `mask` operand)
| opcode | mask form |
|--------|-----------|
| 0x204 | `Rb` register (RRR) |
| 0x804 | immediate (RIR) — **verified** |
| 0xa04 | const bank (RCR) |
| 0x1a04 | const bank, extended (RCxR) |
| 0x1c04 | uniform register (RUR) |

## Fields (128-bit)
| bits | field | R2P |
|------|-------|-----|
| [91]∥[11:0] | `opcode` | 0x204/0x804/… |
| [14:12]/[15] | `Pg`/`Pg_not` | guard |
| [31:24] | `Ra` | source GPR |
| [39:32] | `Rb` | mask (RRR) |
| [63:32] | imm | mask (RIR, 32-bit) |
| [77:76] | `insert`/`a_bsel` | byte select (B0–B3) |
| [112:110] | `dst_wr_sb` | pinned 0x7 |
| [124:122]∥[109:105] | `opex` | scheduling (+`.reuse`) |

`B3B0`: B0=0, B1=1, B2=2, B3=3. `Ra`/`Rb` ≠ R254. IDEST: 0 (writes PR only).

## Cross-comparison (predicate-move family)
| op | dir | granularity |
|----|-----|-------------|
| **P2R** | predicate file → GPR byte | packs P0–P6 under mask |
| **R2P** | GPR byte → predicate file | unpacks under mask |
| **VOTE** | per-lane predicate → GPR (ballot) | warp-wide, one predicate |

## Latency (from sm_90_latencies.txt)
`int_pipe`, fixed-latency `COUPLED_MATH`. `OP_R2P` appears in predicate-connector groups (writes the whole PR file). Pins scoreboard (0x7).

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000a02007804` | `0x000fe40000000000` | `R2P PR, R2, 0xa` (unpack P1,P3) |

Decoder: `tools/decode_p2r_r2p.py` (real vectors + byte-select round-trips pass).
Test: `tests/p2r_test.cu`.

### PTX→SASS mapping
- Testing individual bits of an integer mask as branch/predicate conditions → `R2P PR, Ra, mask`.
- ptxas also uses these to spill/reload predicates under register pressure.

## Open questions
- Byte-select suffix rendering for `Bsel != B0` is reconstructed (only B0 captured); for R2P the `a_bsel` sits after `Ra` in the FORMAT, so it may render on the operand rather than the mnemonic.
