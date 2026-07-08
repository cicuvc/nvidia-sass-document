# GATHER — Register-level sub-element gather (read side; sparse-MMA metadata)

**Opcode mnemonic:** `GATHER` = `0b1001000001` = **0x241** | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH` | **VIRTUAL_QUEUE:** none (fixed-latency) | any shader

## Semantics
Like `SCATTER`, **GATHER is not a memory load** — it is a **register-level
sub-element gather** on the integer math pipe (`int_pipe`, `COUPLED_MATH`, fixed
latency, all operands 32-bit registers). It collects sub-byte data elements from
the source registers into `Rd`, driven by a **metadata index** (`mdidx`) with a
configurable data element size, index size, and group count. It is the read-side
counterpart of `SCATTER` (0x218, `scatter.md`).

In `ref_memo.txt` GATHER (idx 173) sits directly beside **GENMETADATA** (174) and
**SPMETADATA** (175) — confirming this pair is the **2:4 structured-sparsity
metadata handling** cluster (plus low-precision FP8/FP4 lane packing) for the
tensor-core datapath, not a general gather/scatter memory primitive.

FORMAT: `GATHER.<datasize>.<idxsize>.<num> Rd, Ra, Rb, Rc, mdidx, dstbyte, srchalf`
- `Rd` — destination register (`IDEST_SIZE=32`)
- `Ra`,`Rb`,`Rc` — three 32-bit source registers (data + index source), each with
  an optional `.reuse` operand-reuse cache flag
- `mdidx` — 4-bit metadata index
- `dstbyte` — 2-bit destination byte selector (printed, default 0)
- `srchalf` — 1-bit source-half selector (printed, default 0)

## Variant overview
| variant | opcode | note |
|---|---|---|
| `gather_` | 0x241 | single class; all behavior via modifiers |

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `datasize` | datasize | [62:61] | DATASIZE | 16=0, 8=1, 4=2 (3 INVALID) — element bit-width |
| `idxsize` | size | [76:75] | IDXSIZE | U2=0, U4=1, U8=2 (3 INVALID) — index bit-width |
| `num` | num | [54:53] | NUM_GROUPS | 1G=0, 2G=1, 4G=2 (3 INVALID) — group count |
| `reuse_src_a/b/c` | (opex) | [124:122],[109:105] | REUSE | operand-reuse (via `TABLES_opex_4`) |
| `batch_t`,`usched_info` | opex | — | — | scheduling (fused into `TABLES_opex_4`) |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

Operand slots (immediates, not enums):
| operand | field | bits | width |
|---|---|---|---|
| `mdidx` | mdidx | [81:78] | 4-bit metadata index |
| `dstbyte` | dstbyte | [58:57] | 2-bit dest-byte selector |
| `srchalf` | srchalf | [56] | 1-bit source-half selector |

**datasize↔num** (CONDITIONS): `.16` → only `1G`; `.8` → up to `2G`; `.U8` idx →
up to `2G`. **idxsize×num → max mdidx** table caps the index (finer index = more
entries): U2/1G→≤14, U2/2G→≤12, U2/4G→≤8; U4/1G→≤6, U4/2G→≤4, U4/4G→≤0;
U8/1G→≤2, U8/2G→≤0. `.reuse` forbids the `?DRAIN`/`?WAITn_END_GROUP` usched tokens
(shared with all coupled-math ALU ops).

## Bit layout (128-bit map)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_4(batch_t,usched_info,reuse_a,reuse_b,reuse_c)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `*7` (no read scoreboard) |
| [112:110] | dst_wr_sb | `*7` (fixed-latency) |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x241 |
| [81:78] | mdidx | 4-bit metadata index |
| [76:75] | idxsize | IDXSIZE (size slot) |
| [73] | size | `*0` (pinned) |
| [72] | e | 0 (pinned) |
| [71:64] | Rc | source register C |
| [62:61] | datasize | DATASIZE |
| [58:57] | dstbyte | 2-bit dest-byte selector |
| [56] | srchalf | 1-bit source-half selector |
| [54:53] | num | NUM_GROUPS |
| [39:32] | Rb | source register B |
| [31:24] | Ra | source register A |
| [23:16] | Rd | destination register |
| [15] / [14:12] | Pg_not / Pg | predicate |

Fixed-latency (`src_rel_sb`/`dst_wr_sb` pinned `*7`, `COUPLED_MATH`, no VQ).

## Cross-comparison
| op | opcode | fields unique to it | role |
|---|---|---|---|
| `SCATTER` | 0x218 | `mode`(THREAD/QUAD/PAIR), `elsize`(U8/U16), `.SP`, `vecidx`(7b), `mask`(4b) | write/distribute sub-elements |
| **GATHER** | 0x241 | `datasize`(16/8/4), `num`(1G/2G/4G), `mdidx`(4b), `dstbyte`, `srchalf` | read/collect sub-elements |

The pair is **asymmetric**: SCATTER carries a mode + lane-mask + sparse flag;
GATHER carries a data-width + group-count + byte/half selectors and a metadata
index. Both share the three-source `Ra/Rb/Rc` coupled-math shape and the
`TABLES_opex_4` reuse-aware scheduling. Together with `GENMETADATA`/`SPMETADATA`
they form the structured-sparsity operand-prep toolkit; finer-grained than `PRMT`.

## Latency (from `sm_90_latencies.txt`)
`GATHER` ∈ `int_pipe`, `INST_TYPE_COUPLED_MATH` — fixed-latency ALU op, no virtual
queue or scoreboard ownership; standard coupled-math dispatch with `TABLES_opex_4`
operand-reuse scheduling.

## Verified encodings
No hardware encodings observed — stock `nvcc`/`ptxas` (CUDA 13.1) does not emit
GATHER, and it is absent from cuBLAS/cuBLASLt sm_90 binaries (grep-confirmed).
Documented from the spec field map and validated by an **encoder↔decoder
round-trip**, `tools/decode_gather.py`: **3/3 synthetic PASS** (respecting the
datasize↔num and idxsize×num→mdidx bounds):
| Disassembly (synthetic) |
|---|
| `GATHER.16.U2.1G R4, R8, R12, RZ, 0xe, 0x0, 0x0` |
| `GATHER.8.U4.2G R5, R6, R7, R8, 0x4, 0x2, 0x1` |
| `GATHER.4.U8.2G R2, R3, R4, R5, 0x0, 0x3, 0x0` |

## Open questions
- **Exact operation** — how `mdidx`/`dstbyte`/`srchalf`/`idxsize`/`num` combine to
  route source sub-elements into `Rd`. The bound tables (finer index → more
  entries; larger data → fewer groups) fit a metadata-expansion for 2:4 sparsity,
  but the per-lane mapping is not spec-stated.
- **What emits it** — likely `ptxas`-internal for sparse-MMA operand prep or a
  `cusparseLt`/sparse-`wmma` library path; no user PTX intrinsic found. Worth
  re-probing against a structured-sparsity build alongside `GENMETADATA`/`SPMETADATA`.
- Roles of `Ra`/`Rb`/`Rc` (data vs metadata source) vs the immediates.
