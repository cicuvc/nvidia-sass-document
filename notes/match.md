# MATCH — Warp match (find lanes sharing a value)

**Opcode mnemonic:** `MATCH` = `0b1110100001` = **0x3a1** | **Pipe:** `mio_pipe` (MIO_FAST_OPS) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VIRTUAL_QUEUE=$VQ_UNORDERED` | since **sm_70**

SASS lowering of PTX `match.sync` (`__match_any_sync` / `__match_all_sync`). Broadcasts and
compares source `Ra` across the active lanes of the warp and returns, in `Rd`, a 32-bit lane
bitmask (bit `i` = lane `i` has the same value). Applies within a single warp.

## Semantics (verified PTX→SASS)
| PTX / intrinsic | SASS | result |
|-----------------|------|--------|
| `match.any.sync.b32` / `__match_any_sync` | `MATCH.ANY Rd, Ra` | `Rd` = mask of lanes whose `Ra` equals mine |
| `match.all.sync.b32` / `__match_all_sync` | `MATCH.ALL Pu, Rd, Ra` | `Rd` = full active mask if **all** active lanes match (else 0); `Pu` = "all matched" |
| `.b64` variants | `MATCH.{ANY,ALL}.U64 …` | 64-bit compare of a register pair `Ra:Ra+1` |

- **`.ANY`** — always writes `Rd` (per-lane match mask). No predicate output.
- **`.ALL`** — writes `Rd` (all-active mask or 0) **and** predicate `Pu` (all-lanes-equal flag).

**Membermask is dropped.** PTX `match.sync` takes a `membermask` operand, but SASS `MATCH` has
**no mask operand** — verified: even a runtime-variable mask (`__match_any_sync(m, …)`) lowers
to a bare `MATCH.ANY Rd, Ra` with no mask register. The op operates on the hardware active-lane
mask; the PTX membermask is used only for PTX-level correctness, not encoded in SASS.

## Variant overview (2 CLASS variants, same opcode 0x3a1)
| CLASS | `op`[79] | dest predicate | operand width |
|-------|----------|----------------|---------------|
| `match__ANY` | 1 (`ANY`) | none (`Pu` pinned PT) | `.U32`/`.U64` |
| `match__ALL` | 0 (`ALL`) | `Pu` [83:81] | `.U32`/`.U64` |

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x3a1 | 13-bit |
| [14:12] / [15] | `Pg` / `Pg_not` | Pg guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | dest mask (`.b32`, always 32-bit) |
| [31:24] | `Ra` | Register | source value (32-bit; 64-bit pair if `.U64`) |
| [73] | `sz` | `MATCH_SZ` | 0=U32 (default, hidden), 1=U64 |
| [79] | `op` | `ALLOnly`/`ANYONLY` | **0=ALL, 1=ANY** |
| [83:81] | `Pu` | Predicate | ALL: "all matched" dest; ANY: PT(7), hidden |
| [124:122]∥[109:105] | `opex` | TABLES_opex_0(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | scoreboards | |
| [103:102] | `pm_pred` | perfmon predicate | |

**`MATCH_SZ`**: `U32=0, U64=1`. `ALLOnly "ALL"=0`, `ANYONLY "ANY"=1`.
`ISRC_A_SIZE = 32 + (sz==U64)*32` — `.U64` reads a register pair `Ra:Ra+1` (even-aligned,
≠R254). `Rd`/`Ra` also ≠R254, ≤MAX_REG-1.

## Latency (from sm_90_latencies.txt)
`mio_pipe` member; **not** in `MIO_SLOW_OPS` (unlike `SHFL`), so `MATCH ∈ MIO_FAST_OPS` — the
faster MIO latency class. Produces a 32-bit GPR (`Rd`) and, for `.ALL`, a predicate (`Pu`);
consumers wait via the write scoreboard (`dst_wr_sb`), since it is decoupled/unordered.

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000020773a1` | `0x002e2800000e8000` | `MATCH.ANY R7, R2` |
| `0x00000000020773a1` | `0x004e2800000e8200` | `MATCH.ANY.U64 R7, R2` |
| `0x00000000020773a1` | `0x004e240000000000` | `MATCH.ALL P0, R7, R2` |
| `0x00000000020773a1` | `0x004e240000000200` | `MATCH.ALL.U64 P0, R7, R2` |

(Lo64 identical: `Rd`=R7[23:16], `Ra`=R2[31:24], opcode/`Pg`=PT. The ANY/ALL, U32/U64, and
`Pu` differences live in Hi64: `op`[79]=bit15, `sz`[73]=bit9, `Pu`[83:81]=bits[19:17].)
Decoder: `tools/decode_match.py` (all 4 vectors pass). Test: `tests/match_test.cu`.

### PTX→SASS mapping
- `__match_any_sync(mask, v)` → `MATCH.ANY Rd, Ra` (mask arg dropped)
- `__match_all_sync(mask, v, &pred)` → `MATCH.ALL Pu, Rd, Ra` (mask arg dropped)
- 64-bit value → `.U64` with `Ra` as a register pair.

## Open questions
- Whether ptxas ever inserts a `WARPSYNC`/vote before `MATCH` to honor a non-full membermask
  (none observed for the constant or variable-mask cases tested here).
