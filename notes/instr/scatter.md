# SCATTER — Register-level sub-element byte/nibble permute (write side)

**Opcode mnemonic:** `SCATTER` = `0b1000011000` = **0x218** | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH` | **VIRTUAL_QUEUE:** none (fixed-latency) | any shader (no CS-only guard)

## Semantics
Despite the name, **SCATTER is not a memory store** — it is a **register-level
data-permute** op on the integer math pipe (`int_pipe`, `COUPLED_MATH`, fixed
latency, all operands 32-bit registers). It writes selected **sub-elements**
(8- or 16-bit lanes) taken from source registers into destination byte lanes of
`Rd`, under a 4-bit lane `mask` and an index (`vecidx` + per-`idxsize` selector).
It is the write-side counterpart of **GATHER** (0x241, the read-side gather with
the same coupled-math shape). These are internal helpers for **sub-byte data
layout / structured-sparsity metadata reordering** (packing FP8/FP4 lanes or
2:4-sparse index nibbles), not exposed by a direct user PTX intrinsic.

FORMAT: `SCATTER.<mode>.<elsize>.<idxsize>[.SP] Rd, Ra, Rb, Rc, vecidx, mask`
- `Rd` — destination register (`IDEST_SIZE=32`)
- `Ra`,`Rb`,`Rc` — three 32-bit source registers (element data / index source),
  each with an optional `.reuse` operand-reuse cache flag
- `vecidx` — 7-bit vector/element index
- `mask` — 4-bit destination byte-lane mask

## Variant overview
| variant | opcode | note |
|---|---|---|
| `scatter_` | 0x218 | single class; all behavior via modifiers |

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `mode` | iswzC | [82:81] | MODE_scatter | THREAD=0, QUAD=1, PAIR=2 (3 INVALID) |
| `elsize` | e | [72] | ELSIZE | U8=0, U16=1 (element width) |
| `idxsize` | constSizeU04 | [76:73] | IDXSIZE_scatter | U4_H0=0,U4_H1=1,U8=2,U4_B0=3,U4_B1=4,U4_B2=5,U4_B3=6,U8_H0=7,U8_H1=8 (9–15 INVALID) |
| `sparse` | input_reg_sz_32_dist | [90] | SPARSE | nosparse=0, SP=1 (structured-sparse mode) |
| `reuse_src_a/b/c` | (opex) | [124:122],[109:105] | REUSE | operand-reuse cache (via `TABLES_opex_4`) |
| `batch_t`,`usched_info` | opex | — | — | scheduling (fused into `TABLES_opex_4` with the reuse flags) |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

`vecidx` and `mask` are **operand slots**, not enum modifiers:
| operand | field | bits | width |
|---|---|---|---|
| `vecidx` | vecidx | [89:83] | 7-bit index |
| `mask` | mem | [80:77] | 4-bit lane mask |

**elsize↔idxsize pairing** (CONDITIONS): `.U8` element → idxsize ∈ {U4_H0/H1, U8};
`.U16` element → idxsize ∈ {U4_B0..B3, U8_H0/H1}. `.U16` forbids the top 2 mask
bits (`mask ≤ 3` — only 2 halfword lanes). `.SP` allows at most two mask bits set
(mask ∈ {0..6,8,9,10,12}). A large table of
`mode×elsize×idxsize → max vecidx` bounds caps the index per configuration
(e.g. THREAD.U8.U4_H0 → vecidx ≤ 63; QUAD.U8.U4* → vecidx ≤ 0).

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_4(batch_t,usched_info,reuse_a,reuse_b,reuse_c)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `*7` (no read scoreboard) |
| [112:110] | dst_wr_sb | `*7` (fixed-latency, no write scoreboard) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x218 |
| [90] | sparse | SPARSE (SP) |
| [89:83] | vecidx | 7-bit index |
| [82:81] | mode | MODE_scatter (iswzC slot) |
| [80:77] | mask | 4-bit lane mask (mem slot) |
| [76:73] | idxsize | IDXSIZE_scatter (constSizeU04 slot) |
| [72] | elsize | ELSIZE |
| [71:64] | Rc | source register C |
| [39:32] | Rb | source register B |
| [31:24] | Ra | source register A |
| [23:16] | Rd | destination register |
| [15] / [14:12] | Pg_not / Pg | predicate |

`INST_TYPE_COUPLED_MATH` + `src_rel_sb`/`dst_wr_sb` pinned to `*7` → a
**fixed-latency** op with no decoupled scoreboard (unlike the memory/async ops).

## Cross-comparison
| op | opcode | pipe | role |
|---|---|---|---|
| **SCATTER** | 0x218 | int | register sub-element permute (write/distribute lanes) |
| `GATHER` | 0x241 | int | register sub-element permute (read/collect lanes) — has `datasize`/`num_groups`/`mdidx`/`dstbyte`/`srchalf` |
| `PRMT` | — | int | classic byte permute (4 bytes from 8) |
| `SHF`/`LOP3` | — | int | bit-level shift/logic |

SCATTER/GATHER are the **sub-byte structured-permute** pair — finer-grained than
`PRMT`, with element-size (U8/U16), index-size (U4/U8 sub-selectors), and a sparse
(`.SP`) mode, pointing at 2:4 structured-sparsity metadata handling and low-precision
(FP8/FP4) lane packing for the tensor-core datapaths.

## Latency (from `sm_90_latencies.txt`)
`SCATTER` ∈ `int_pipe`, `INST_TYPE_COUPLED_MATH` — a fixed-latency ALU op (no
virtual queue, no scoreboard ownership). Standard coupled-math dispatch/latency;
`TABLES_opex_4` (with `reuse_src_*`) is the operand-reuse-aware scheduling table
shared by the register-ALU ops.

## Verified encodings
No hardware encodings observed — stock `nvcc`/`ptxas` (CUDA 13.1) does not emit
SCATTER from C/C++ or common PTX, and it is absent from cuBLAS/cuBLASLt sm_90
binaries (grep-confirmed). Documented from the spec field map and validated by an
**encoder↔decoder round-trip**, `tools/decode_scatter.py`: **3/3 synthetic PASS**:
| Disassembly (synthetic) |
|---|
| `SCATTER.THREAD.U8.U4_H0 R4, R8, R12, RZ, 0x0, 0xf` |
| `SCATTER.QUAD.U16.U8 R5, R6, R7, R8, 0x3, 0x3` |
| `SCATTER.PAIR.U8.U8_H0.SP R2, R3, R4, R5, 0x1, 0x5` |

## Open questions
- **Exact operation** — how `vecidx`/`mask`/`idxsize` combine to route source
  sub-elements into `Rd` lanes; the CONDITIONS bounds strongly imply a
  metadata-reorder for 2:4 sparsity + FP8/FP4 packing, but the precise per-lane
  mapping is not spec-stated.
- **What emits it** — likely `ptxas` internally for sparse-MMA operand prep or a
  library-private path; no user PTX intrinsic found. Worth re-probing against a
  `cusparseLt` / sparse-`wmma` build.
- Role of the three sources `Ra`/`Rb`/`Rc` (data vs index vs mask base) vs the
  `vecidx`/`mask` immediates.
- Relationship to `GATHER` (0x241) — presumably the inverse permute; GATHER's
  extra `dstbyte`/`srchalf`/`num_groups` fields suggest an asymmetric pair.
  (GATHER is now documented in `gather.md`.)
