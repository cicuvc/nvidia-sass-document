# CCTL — Cache control (L1/L2 line ops & whole-cache invalidate/writeback)

**Opcode mnemonics:** `CCTL` = `0b100110001111` = **0x98f** (imm-offset / whole-cache) / `0b1110110001111` = **0x1d8f** (uniform-reg offset) | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_UNORDERED`

## Semantics
CCTL performs **cache-control** operations on the data/uniform/constant/instruction
caches: per-line prefetch/writeback/invalidate/discard on a given address, or
whole-cache invalidate/writeback (the `*ALL` ops). It is the generic/global cache
manager (contrast `CCTLL` = L1-local cache, `CCTLT` = texture cache, `UTMACCTL` =
TMA descriptor cache). PTX sources: `prefetch`, `prefetchu`, `discard`,
`applypriority`, and compiler-inserted L1 invalidations (e.g. the `.acquire`
`CCTL.IVALL` after an mbarrier phase flip, `notes/tma_mbarrier.md`).

Two operand families:
- **Address form:** `CCTL[.E].<cache>.<cop> [Ra+off]` — a single line/range
- **Whole-cache noSrc:** `CCTL.<cop>` (cop ∈ IVALL/IVALLP/WBALL/WBALLP) — no address
  (`Ra` pinned RZ, `src_rel_sb`/`cache` pinned)

## Variant overview
| variant | opcode | form | cache selectable |
|---|---|---|---|
| `cctl__sImmOffset` | 0x98f | `[Ra+off]` (Ra≠RZ) | D/U/C/I |
| `cctl__uImmOffset` | 0x98f | `[RZ+off]` | D/U/C/I |
| `cctl__sUROffset` | 0x1d8f | `[Ra+URb]` | D/U/C/I |
| `cctl__uUROffset` | 0x1d8f | `[URb]` | D/U/C/I |
| `cctl__IVALL_WBALL_D_U_noSrc` | 0x98f | whole-cache | D or U |
| `cctl__IVALL_WBALL_C_noSrc` | 0x98f | whole-cache | C (const) |
| `cctl__IVALL_WBALL_I_noSrc` | 0x98f | whole-cache | I (instr) |

The whole-cache forms split by which cache the `*ALL` targets (D/U vs C vs I) via
`CACHE_D_U`/`CONLY`/`IONLY` enums; the address forms take the full `Cache` enum.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `cop` (address) | op | [90:87] | COP_PF1_PF2_WB_IV_RS_PML2_DML2_RML2 | PF1=0,PF2=1,WB=2,IV=3,RS=5,PML2=9,DML2=10,RML2=11 |
| `cop` (whole-cache) | op | [90:87] | COP_IVALL_IVALLP_WBALL_WBALLP | IVALL=4,IVALLP=6,WBALL=7,WBALLP=8 |
| `cache` | cache | [80:78] | Cache | D=0(default,unprinted),U=1,C=2,I=3 |
| `e` | e | [72] | E | noe=0 / `.E`=1 (64-bit address) |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

**COP meanings:** `PF1`/`PF2` prefetch to L1/L2; `WB` writeback; `IV` invalidate;
`RS` reset; `PML2`/`DML2`/`RML2` = L2 priority/demote/reset-line (map to
`applypriority`/`discard`); `IVALL`/`WBALL` = invalidate-all/writeback-all
(+`P` = "peer"/persist variants). The two enums share the 4-bit `op` field —
address ops use codes {0,1,2,3,5,9,10,11}, whole-cache ops use {4,6,7,8}.

## Bit layout (128-bit)
| bits | field | source | notes |
|---|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0` | |
| [121:116] | req_bit_set | scoreboard wait mask | |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` (addr) / `7` (noSrc) | |
| [112:110] | dst_wr_sb | `7` (pinned — no write scoreboard) | |
| [103:102] | pm_pred | perfmon predicate | |
| [91]∥[11:0] | opcode | 0x98f / 0x1d8f | |
| [90:87] | op | cop | |
| [80:78] | cache | Cache | |
| [72] | e | E | |
| [63:32] | Ra_offset | 32-bit offset (imm form only) | |
| [37:32] | Ra_URb | uniform base (0x1d8f UR form) | overlaps offset region |
| [31:24] | Ra | address register (RZ=255 for noSrc) | |
| [15] / [14:12] | Pg_not / Pg | predicate | |

`IDEST_SIZE=0` (no result); `ISRC_A_SIZE = e ? 64 : 32` (address regs).

## The `CCTL_NO_SB` distinction (TODO idx 107 vs 108)
`ref_memo` lists `CCTL_NO_SB` (idx 107) and `CCTL` (idx 108) separately. There is
**one mnemonic** in the sm_90 spec (`CCTL`); the "NO_SB" form is the same op with
its scoreboard-wait control tail suppressed — the **whole-cache noSrc** classes
pin `src_rel_sb=7` (no read-scoreboard dependency), which is exactly the
"no scoreboard wait" behavior. So `CCTL_NO_SB` = the `*ALL`/noSrc encodings.

## Cross-comparison
| op | opcode | target cache |
|---|---|---|
| **CCTL** | 0x98f/0x1d8f | generic/global data cache (L1/L2), + U/C/I |
| `CCTLL` | — | L1 **local**-memory cache (`notes` TBD) |
| `CCTLT` | — | texture cache (excluded) |
| `UTMACCTL` | 0x19b9/0x9b9 | TMA descriptor cache (`notes/utmacctl.md`) |

## Latency (from `sm_90_latencies.txt`)
`CCTL` ∈ `mio_pipe`, `VQ_UNORDERED`. Decoupled read-scoreboard op, no register
result. Fire-and-forget cache maintenance; ordering vs subsequent accesses relies
on the memory model (e.g. the `CCTL.IVALL` under `@P0` after `SYNCS.PHASECHK`
provides the acquire-side L1 invalidation).

## Verified encodings (`tests/cctl_test.cu` + `tests/tma_test.cubin`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | PTX |
|---|---|---|---|
| `0x000000000200798f` | `0x001fe20000000100` | `CCTL.E.PF1 [R2]` | `prefetch.global.L1` / `prefetchu.L1` |
| `0x000000000200798f` | `0x001fe20000800100` | `CCTL.E.PF2 [R2]` | `prefetch.global.L2` |
| `0x000000000200798f` | `0x001fe20005800100` | `CCTL.E.RML2 [R2]` | `discard.global.L2` |
| `0x000000000200798f` | `0x001fe20005000100` | `CCTL.E.DML2 [R2]` | `applypriority.global.L2::evict_normal` |
| `0x00000000ff00098f` | `0x001fe20002000000` | `@P0 CCTL.IVALL` | compiler acquire-fence (post-mbarrier) |

Decoder `tools/decode_cctl.py`: **5/5 PASS**. `op` (cop) is Hi64 [90:87 → shows in
the `...00`/`...80`/`...05_80`/`...05_00` nibbles]: PF1=0, PF2=1, DML2=10, RML2=11;
IVALL=4 with `Ra=RZ` (0xff) and no address.

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `prefetch.global.L1 [p]` / `prefetchu.L1 [p]` | `CCTL.E.PF1 [Ra]` |
| `prefetch.global.L2 [p]` | `CCTL.E.PF2 [Ra]` |
| `discard.global.L2 [p], n` | `CCTL.E.RML2 [Ra]` (reset/discard L2 line) |
| `applypriority.global.L2::evict_normal [p], n` | `CCTL.E.DML2 [Ra]` (demote L2 priority) |
| (compiler acquire) | `@P CCTL.IVALL` (invalidate all L1) |

**Key finding:** the L2 data-movement PTX ops map cleanly onto the L2 CCTL COPs —
`discard`→`RML2` (reset/remove line), `applypriority`→`DML2` (demote), and the
`prefetch` family to `PF1`/`PF2`. `prefetch.global.L1` and `prefetchu.L1` both
lower to `CCTL.E.PF1`.

## Open questions
- `WB`/`IV`/`RS`/`PML2` address COPs and `IVALLP`/`WBALL`/`WBALLP` whole-cache COPs
  — which PTX/compiler patterns emit them (not triggered here).
- `.U`/`.C`/`.I` cache selectors (uniform/constant/instruction) — likely from
  `prefetchu`/const-path/icache maintenance; `prefetchu.L1` still gave `.PF1`
  on the D cache here.
- The `applypriority.L2::evict_last` PTX form (ptxas rejected it in CUDA 13.1) —
  which COP it would select (likely `PML2`).
