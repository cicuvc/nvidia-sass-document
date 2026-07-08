# CCTLL — Local-memory cache control

**Opcode mnemonics:** `CCTLL` = `0b100110010000` = **0x990** (imm-offset / whole-cache noSrc) / `0b1110110010000` = **0x1d90** (uniform-reg offset) | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_UNORDERED`

## Semantics
CCTLL is the **local-memory** counterpart of `CCTL` (`cctl.md`): cache-control
(prefetch / writeback / invalidate / reset) targeting the per-thread **local memory**
(stack / register spill / `.local` state space) caches. PTX `prefetch.local.L1/L2`
lowers to it. Structurally a stripped-down CCTL — same `op`/`Ra`/offset layout,
but **no cache selector** (always local, no D/U/C/I) and **no `.E`** (local
addresses are 32-bit), with a reduced COP set.

Two operand families (as CCTL):
- **Address form:** `CCTLL.<cop> [Ra+off]` — a single local-memory line
- **Whole-cache noSrc:** `CCTLL.IVALL` / `CCTLL.WBALL` — no address (`Ra` pinned RZ,
  `src_rel_sb` pinned)

## Variant overview
| variant | opcode | form |
|---|---|---|
| `cctll__sImmOffset` | 0x990 | `[Ra+off]` (Ra≠RZ) |
| `cctll__uImmOffset` | 0x990 | `[RZ+off]` |
| `cctll__Ra_nonRz_UR` | 0x1d90 | `[Ra+URb]` |
| `cctll__Ra_RZ_UR` | 0x1d90 | `[RZ+URb]` |
| `cctll__IVALL_WBALL_D_U_noSrc` | 0x990 | whole-cache (`IVALL`/`WBALL`) |

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `cop` (address) | op | [90:87] | COP_PF1_PF2_WB_IV_RS | PF1=0,PF2=1,WB=2,IV=3,RS=5 |
| `cop` (whole-cache) | op | [90:87] | COP_IVALL_WBALL | IVALL=4, WBALL=7 |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

**vs CCTL:** CCTLL drops the `cache` [80:78] selector (local only), the `e` [72]
extended-address bit, and the L2 COPs (`PML2`/`DML2`/`RML2`) and `IVALLP`/`WBALLP`
peer variants. It keeps the core five line COPs {PF1,PF2,WB,IV,RS} plus the two
whole-cache ops {IVALL,WBALL}. Offset is **24-bit** [63:40] (vs CCTL's 32-bit
[63:32]), reflecting the smaller local address space.

## Bit layout (128-bit)
| bits | field | source | notes |
|---|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0` | |
| [121:116] | req_bit_set | scoreboard wait mask | |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` (addr) / `7` (noSrc) | |
| [112:110] | dst_wr_sb | `7` (pinned — no write scoreboard) | |
| [103:102] | pm_pred | perfmon predicate | |
| [91]∥[11:0] | opcode | 0x990 / 0x1d90 | |
| [90:87] | op | cop | |
| [63:40] | Ra_offset | 24-bit offset (imm form) | |
| [37:32] | Ra_URb | uniform base (0x1d90 UR form) | |
| [31:24] | Ra | address register (RZ=255 for noSrc) | |
| [15] / [14:12] | Pg_not / Pg | predicate | |

`IDEST_SIZE=0`, `ISRC_A_SIZE=32` (local addresses are always 32-bit — no `.E`).

## Cross-comparison
| op | opcode | target | address width | cache selector |
|---|---|---|---|---|
| `CCTL` | 0x98f/0x1d8f | generic/global (L1/L2), U/C/I | 32-bit off, `.E` 64-bit addr | D/U/C/I |
| **CCTLL** | 0x990/0x1d90 | **local memory** | 24-bit off, 32-bit addr | none (local only) |
| `UTMACCTL` | 0x19b9/0x9b9 | TMA descriptor cache | — | — |

CCTL and CCTLL sit at adjacent opcodes (0x98f / 0x990) — the global vs local
cache-control pair, mirroring the STG/STL, LDG/LDL space split.

## Latency (from `sm_90_latencies.txt`)
`CCTLL` ∈ `mio_pipe`, `VQ_UNORDERED`. Decoupled read-scoreboard op, no register
result; fire-and-forget local-cache maintenance.

## Verified encodings (`tests/cctll_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | PTX |
|---|---|---|---|
| `0x0000000000007990` | `0x0001e40000000000` | `CCTLL.PF1 [R0]` | `prefetch.local.L1` |
| `0x0000000000007990` | `0x0001e40000800000` | `CCTLL.PF2 [R0]` | `prefetch.local.L2` |

Decoder `tools/decode_cctll.py`: **2/2 PASS**. `op` (cop) is Hi64 [90:87]: PF1=0
(`...00`), PF2=1 (`...80` in that nibble). No `.E`, no cache selector printed.

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `prefetch.local.L1 [p]` | `CCTLL.PF1 [Ra]` |
| `prefetch.local.L2 [p]` | `CCTLL.PF2 [Ra]` |

Directly parallels CCTL's `prefetch.global.L1/L2 → CCTL.PF1/PF2`, just routed to
the local-memory cache path.

## Open questions
- `WB`/`IV`/`RS` address COPs and `IVALL`/`WBALL` whole-cache COPs for local memory
  — which patterns emit them (local writeback/invalidate is rare; not triggered).
- The `0x1d90` uniform-register-offset form — when ptxas prefers it (local accesses
  are usually plain `[Ra+off]`).
