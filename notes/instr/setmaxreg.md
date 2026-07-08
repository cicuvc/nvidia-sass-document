# SETMAXREG (USETMAXREG) — Warp register-pool alloc/dealloc hint

**Opcode mnemonic:** `USETMAXREG` = `0b1100111001000` = **0x19c8** (imm form) / `0b1001111001000` = **0x13c8** (UR form) | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VIRTUAL_QUEUE=$VQ_UNORDERED` | compute-only (`SHADER_TYPE==CS`)

SASS lowering of PTX `setmaxnreg.action.sync.aligned.u32` — a hint to change the maximum
per-thread register count owned by the executing warp, used for **warp specialization** on
Hopper (producer warps `dec` to release registers; consumer/MMA warps `inc` to grow their
file). A pool of spare registers is maintained per-CTA; the instruction moves registers
between the warp and that pool. Register file changes always happen at the tail of the file.
Requires `sm_90a` and a launch with a known max register count (else ptxas ignores it:
warning `C7508 'setmaxnreg' ignored; unable to determine register count at entry`).

## Semantics (verified PTX→SASS)
| PTX | SASS | role |
|-----|------|------|
| `setmaxnreg.dec.sync.aligned.u32 N` | `USETMAXREG.DEALLOC.CTAPOOL N` | release registers down to N (→ CTA pool) |
| `setmaxnreg.inc.sync.aligned.u32 N` | `USETMAXREG.TRY_ALLOC.CTAPOOL UPu, N` (+ retry loop) | request registers up to N (from CTA pool) |

`N` = absolute per-thread max register count, encoded **directly** in the immediate field
(PTX range 24–256, multiple of 8). The `.CTAPOOL` modifier names the source/target pool.

**`.inc` is a spin-loop.** The alloc op is non-blocking: `TRY_ALLOC` writes a uniform
predicate `UPu` = "allocation succeeded". ptxas builds the blocking PTX `.inc` semantics as:
```
L: NOP
   USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x40   ; UP0 = success
   PLOP3.LUT P0, PT,PT,PT, UP0, 0x80, 0x0   ; P0 = UP0
   @!P0 BRA L                               ; retry until granted
```
`.dec` (DEALLOC) writes no predicate (`Pu` pinned to PT) and does not block.

## Variant overview (8 CLASS variants)
| CLASS | opcode | mode modifier | src B | dest pred |
|-------|--------|---------------|-------|-----------|
| `usetmaxreg__Ib_alloc`      | 0x19c8 | `/TRY_ALLOCONLY` "TRY_ALLOC"=2 | UImm(10) | UPu |
| `usetmaxreg__Ib_dealloc`    | 0x19c8 | `/DEALLOCONLY`   "DEALLOC"=1    | UImm(10) | — (PT) |
| `usetmaxregAlloc__Ib_alloc` (ALT) | 0x19c8 | `/ALLOCONLY` "ALLOC"=2 | UImm(10) | UPu |
| `usetmaxregAlloc__Ib_dealloc` (ALT) | 0x19c8 | `/DEALLOCONLY`=1 | UImm(10) | — |
| `usetmaxreg__URb_alloc`       | 0x13c8 | TRY_ALLOC=2 | UniformRegister | UPu |
| `usetmaxreg__URb_dealloc`     | 0x13c8 | DEALLOC=1   | UniformRegister | — |
| `usetmaxregAlloc__URb_alloc` (ALT) | 0x13c8 | ALLOC=2 | UniformRegister | UPu |
| `usetmaxregAlloc__URb_dealloc` (ALT) | 0x13c8 | DEALLOC=1 | UniformRegister | — |

- Two operand shapes: **immediate** `Sb` (opcode 0x19c8, `ISRC_B_SIZE=10`) and **uniform
  register** `URb` (opcode 0x13c8, `ISRC_B_SIZE=32`, `Ra_URb` at [37:32]). ptxas emits the
  immediate form for the PTX constant operand.
- **ALLOC vs TRY_ALLOC are encoding-identical** (both `mode`/`num`=2). The `usetmaxregAlloc*`
  ALT classes are just an alternate assembler spelling; cuobjdump always disassembles `num==2`
  as **`.TRY_ALLOC`**. So only two distinct mode encodings exist: DEALLOC=1, ALLOC/TRY=2.

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x19c8 (imm) / 0x13c8 (UR) | 13-bit |
| [14:12] / [15] | `Pg` / `Pg_not` | UPg guard | uniform predicate guard (7=PT hidden) |
| [41:32] | `Sb` | UImm(10) | register count N (imm form) |
| [37:32] | `Ra_URb` | UniformRegister | register count in UR (UR form) |
| [73:72] | `num` | `*mode` | 1=DEALLOC, 2=ALLOC/TRY_ALLOC |
| [74]    | `sh`  | `pool` | 1=CTAPOOL |
| [83:81] | `Pu`  | UPu | dest uniform predicate (alloc: success flag; dealloc: PT) |
| [124:122]∥[109:105] | `opex` | TABLES_opex_0(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | scoreboard | |
| [103:102] | `pm_pred` | perfmon predicate | |

## Latency (from sm_90_latencies.txt)
`udp_pipe` member; `USETMAXREG_OP = {USETMAXREG, USETMAXREGudp_pipe}`. Produces the uniform
predicate `UPu`: `TABLE_TRUE(UPRED)` and `TABLE_OUTPUT(UPRED)` rows for `USETMAXREG_OP` are
all **1** cycle (fastest UPRED producer — the success flag is available next cycle so the
retry loop is tight). No GPR result (`IDEST_SIZE=0`).

## Verified encodings (sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000080000079c8` | `0x000e0000080e0500` | `USETMAXREG.DEALLOC.CTAPOOL 0x80` |
| `0x00000060000079c8` | `0x000e0000080e0500` | `USETMAXREG.DEALLOC.CTAPOOL 0x60` |
| `0x00000040000079c8` | `0x000e0000080e0500` | `USETMAXREG.DEALLOC.CTAPOOL 0x40` |
| `0x00000018000079c8` | `0x000e0000080e0500` | `USETMAXREG.DEALLOC.CTAPOOL 0x18` |
| `0x000000f0000079c8` | `0x000e240008000600` | `USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0xf0` |
| `0x000000c0000079c8` | `0x000e240008000600` | `USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0xc0` |
| `0x00000080000079c8` | `0x000e240008000600` | `USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x80` |
| `0x00000040000079c8` | `0x000e240008000600` | `USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x40` |

Note dec-128 and inc-128 share Lo64 (`Sb`=0x80) but differ in Hi64 (`num` 1 vs 2).
Decoder: `tools/decode_setmaxreg.py` (all 8 vectors pass). Tests: `tests/setmaxreg_dec.cu`
(`-maxrregcount=128`), `tests/setmaxreg_inc.cu` (`-maxrregcount=64`).

### PTX→SASS mapping
- `setmaxnreg.dec.sync.aligned.u32 N` → `USETMAXREG.DEALLOC.CTAPOOL N`
- `setmaxnreg.inc.sync.aligned.u32 N` → `USETMAXREG.TRY_ALLOC.CTAPOOL UPu, N` wrapped in a
  `@!P0 BRA` retry loop (blocking until pool grants the registers).

## Open questions
- Whether the standalone `.ALLOC` (non-TRY, blocking-in-hardware?) form is ever emitted, or if
  ptxas only ever uses TRY_ALLOC + software retry. All observed inc lowerings use TRY_ALLOC.
- The UR (`0x13c8`) operand form was not observed from ptxas (constant operand always inlined);
  no test vector captured for it.
