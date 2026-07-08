# SHFL — Warp shuffle (cross-lane data exchange)

**Opcode mnemonics:** `SHFL` = **0x389** (RRR) / **0x589** (RRI) / **0x989** (RIR) / **0xf89** (RII) | **Pipe:** `mio_pipe` (MIO_SLOW_OPS) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VIRTUAL_QUEUE=$VQ_AGU` | since sm_70

SASS lowering of PTX `shfl.sync` (`__shfl_sync` / `__shfl_up_sync` / `__shfl_down_sync` /
`__shfl_xor_sync`). Each lane reads a 32-bit value `Ra` from another lane of the warp selected
by an index/offset `b` and a bound/segment operand `c`; result goes to `Rd`, and `Pu` receives
the "source-lane-in-range" predicate.

## Semantics (verified PTX→SASS)
| mode `shflmd`[59:58] | SASS | intrinsic | index `b` meaning |
|----------------------|------|-----------|-------------------|
| `IDX`=0  | `SHFL.IDX`  | `__shfl_sync`      | absolute source lane |
| `UP`=1   | `SHFL.UP`   | `__shfl_up_sync`   | subtract delta (toward lane 0) |
| `DOWN`=2 | `SHFL.DOWN` | `__shfl_down_sync` | add delta (toward lane 31) |
| `BFLY`=3 | `SHFL.BFLY` | `__shfl_xor_sync`  | XOR lane mask (butterfly) |

**`c` (bound) operand packing** — `[12:8]` = segmask = `32 - width`; `[4:0]` = clamp:
- IDX / DOWN / BFLY → clamp = `0x1f` (segment upper bound). Full warp (width 32): `c=0x1f`;
  width 8: `c=0x181f`.
- UP → clamp = `0` (segment lower bound); ptxas encodes the all-zero bound as register `RZ`
  (RIR form) rather than an immediate.

**Membermask is dropped** (as with VOTE/MATCH): PTX `shfl.sync` takes a `membermask`, but SASS
`SHFL` has no mask operand — it shuffles over the hardware active-lane mask.

## Variant overview (4 CLASS variants — operand shape)
| opcode | form | index `b` | bound `c` |
|--------|------|-----------|-----------|
| 0x389 | RRR | `Rb` [39:32] | `Rc` [71:64] |
| 0x589 | RRI | `Rb` [39:32] | `Sc` [52:40] (13-bit imm) |
| 0x989 | RIR | `Sb` [57:53] (5-bit imm) | `Rc` [71:64] |
| 0xf89 | RII | `Sb` [57:53] (5-bit imm) | `Sc` [52:40] (13-bit imm) |

Constant srcLane/delta → immediate `Sb`; variable → register `Rb`. Constant width → the
segmask/clamp fold into `Sc`. (RRR not observed from ptxas in these tests.)

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x389/0x589/0x989/0xf89 | 13-bit; selects operand form |
| [14:12] / [15] | `Pg` / `Pg_not` | Pg guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | shuffled result |
| [31:24] | `Ra` | Register | source data value |
| [39:32] | `Rb` | Register | lane index/offset (RRR/RRI) |
| [57:53] | `Sb` | UImm(5) | lane index/offset imm (RIR/RII) |
| [71:64] | `Rc` | Register | bound/segmask+clamp (RRR/RIR) |
| [52:40] | `Sc` | UImm(13) | bound/segmask+clamp imm (RRI/RII) |
| [59:58] | `shflmd` | `Shflmd` | 0=IDX,1=UP,2=DOWN,3=BFLY |
| [83:81] | `Pu` | Predicate | source-lane-in-range (usually PT sink) |
| [124:122]∥[109:105] | `opex` | TABLES_opex_0(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | scoreboards | |
| [103:102] | `pm_pred` | perfmon predicate | |

**`Shflmd`**: `IDX=0, UP=1, DOWN=2, BFLY=3`. `Rd`/`Ra` ≠ R254, ≤MAX_REG-1.

## Latency (from sm_90_latencies.txt)
`mio_pipe` member and listed in **`MIO_SLOW_OPS`** (the slower MIO latency class, alongside
LDS/S2R). Decoupled (`VQ_AGU`): consumers wait on the write scoreboard (`dst_wr_sb`).

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x08001f0702077589` | `0x002e2800000e0000` | `SHFL.DOWN PT, R7, R2, R7, 0x1f` (RRI, reg delta) |
| `0x00001f0702077589` | `0x002e2800000e0000` | `SHFL.IDX PT, R7, R2, R7, 0x1f` (RRI, reg lane) |
| `0x00601f0002077f89` | `0x004e2800000e0000` | `SHFL.IDX PT, R7, R2, 0x3, 0x1f` (RII) |
| `0x00781f0002077f89` | `0x004e2800000e0000` | `SHFL.IDX PT, R7, R2, 0x3, 0x181f` (RII, width=8) |
| `0x08401f0002077f89` | `0x004e2800000e0000` | `SHFL.DOWN PT, R7, R2, 0x2, 0x1f` (RII) |
| `0x0e001f0002077f89` | `0x004e2800000e0000` | `SHFL.BFLY PT, R7, R2, 0x10, 0x1f` (RII, xor 16) |
| `0x0420000002077989` | `0x004e2800000e00ff` | `SHFL.UP PT, R7, R2, 0x1, RZ` (RIR, bound=RZ) |

Decoder: `tools/decode_shfl.py` (all 7 vectors pass). Test: `tests/shfl_test.cu`.

### PTX→SASS mapping
- `__shfl_sync(mask, v, lane, w)` → `SHFL.IDX PT, Rd, v, lane, c(w)`
- `__shfl_up_sync(mask, v, d, w)` → `SHFL.UP PT, Rd, v, d, c` (c=0 → RZ)
- `__shfl_down_sync(mask, v, d, w)` → `SHFL.DOWN …`
- `__shfl_xor_sync(mask, v, m, w)` → `SHFL.BFLY …`
- `c = ((32-width)<<8) | (0x1f for idx/down/bfly, 0 for up)`; mask arg dropped.

## Open questions
- 64-bit / vector shuffles: `__shfl_sync` on 64-bit types splits into two 32-bit SHFLs — not
  a distinct SHFL encoding (`IDEST_SIZE`/`ISRC_A_SIZE` are fixed 32 here).
- `Pu` (source-lane-valid) is always a PT sink in compiler output; no intrinsic exposes it.
