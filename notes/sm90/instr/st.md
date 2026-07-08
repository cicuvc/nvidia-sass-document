# ST — Store to generic address space

**Opcode mnemonics:** `ST` = `0b1100110000101` = **0x1985** (memdesc/uniform, 64-bit addr) / `0b1110000101` = **0x385** (plain imm-offset) | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_AGU`

## Semantics
ST is the **generic-address-space** store — the write-side counterpart of `LD`
(`ld.md`), just as `STG` mirrors `LDG`. The target state space (global /
shared / local) is **resolved at runtime** from the pointer; PTX `st.u32 [ptr], v`
with no state-space qualifier lowers to `ST`. On sm_90 ptxas emits the **memdesc**
form `ST.E … desc[URc][Ra.64], Rb`.

Operands: `ST[.mods] <dest-addr>, Rb` — destination address first, then the data
register `Rb`. Address forms: `desc[URc][Ra.64+off]` (descriptor, default),
`[Ra+URc+off]` (uniform), `[Ra+off]` (plain).

## Variant overview
| variant | opcode | memdesc | E | address |
|---|---|---|---|---|
| `st__sImmOffset` | 0x385 | 0* | 0 | `[Ra+off]` |
| `st__uImmOffset` | 0x385 | 0* | 0 | `[RZ+off]` |
| `st_uniform__Ra32` | 0x1985 | 0 | 0 | `[Ra+URc+off]` |
| `st_uniform__RaRZ` [ALT] | 0x1985 | 0 | 0 | `[URc+off]` |
| `st_uniform__Ra64` | 0x1985 | 0 | 1 | `[Ra.64+URc+off]` |
| `st_memdesc__Ra64` | 0x1985 | 1 | 1 | `desc[URc][Ra.64+off]` |

*Plain 0x385 hardwires memdesc=0. All observed sm_90 ST use `st_memdesc__Ra64`.

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `e` | e | [72] | E | noe=0 / `.E`=1 (64-bit extended addr) |
| `cop` | cop | [86:84] | COP | EF=0,EN=1(default),EL=2,LU=3,EU=4,NA=5 (6,7 illegal) |
| `sz` | sz | [75:73] | SZ_U8_S8_U16_S16_32_64_128 | U8=0,S8=1,U16=2,S16=3,32=4(default),64=5,128=6 |
| `sem`/`sco`/`private` | mem | [80:77] | **`TABLES_mem_0(...)`** | WEAK/CONSTANT/STRONG/MMIO × scope × private |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 desc |

**Differences from LD:** ST has **no `Pnz`** field (a store has no
predicated-nonzero form) and **no `SP2`** sector-prefetch (that is a load-only
cache hint). It uses **`TABLES_mem_0`** for the mem field — a *different* table
than LD/LDG's `TABLES_mem_1` (loads and stores have separate sem/sco→code maps),
though the observed codes coincide (0=WEAK, 10=STRONG.SYS, …).

`ISRC_B_SIZE = 32 + {64:+32,128:+96}` (data width; `Rb` is the source);
`IDEST_SIZE=0` (a store produces no register result). `.E` → `ISRC_A_SIZE=64`.

## Bit layout (128-bit, st_memdesc__Ra64)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard |
| [112:110] | dst_wr_sb | **`7` (pinned, num)** — a store owns no write scoreboard |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x1985 |
| [90] | input_reg_sz | 64-bit Ra distinguisher (`*`) |
| [86:84] | cop | COP |
| [80:77] | mem | sem/sco/private (`TABLES_mem_0`) |
| [76] | memdesc | 1 (desc form) |
| [75:73] | sz | size |
| [72] | e | E |
| [69:64] | Ra_URc | memory descriptor UR |
| [63:40] | Ra_offset | 24-bit signed offset |
| [39:32] | Rb | source data register |
| [31:24] | Ra | address register |
| [15] / [14:12] | Pg_not / Pg | predicate |

Note no `Rd`/`Pnz`/`sp2` fields (compared to LD): bits [67:64] and [69:68] are
freed, and [23:16] (LD's `Rd`) is unused — the source `Rb` lives at [39:32].

## Cross-comparison (store family)
| op | opcode | space | INST_TYPE |
|---|---|---|---|
| **ST** | 0x1985/0x385 | **generic** (runtime-resolved) | DECOUPLED_RD_SCBD |
| `STG` | — | global | (space-specialized) |
| `STS` | — | shared | `sts.md` |
| `STL` | — | local | `stl.md` |
| `LD` | 0x1980/0x980 | generic (load) | DECOUPLED_RD_WR_SCBD |

ST vs LD: **the store is `DECOUPLED_RD_SCBD` (read scoreboard only)** — it reads
`Rb`/address and needs no write scoreboard (`dst_wr_sb=7` pinned), whereas LD is
`DECOUPLED_RD_WR_SCBD` (its loaded result needs a write scoreboard). Also ST's
opcode is 0x1985 vs LD's 0x1980 (low nibble 5 vs 0) — the same load/store nibble
pattern seen across the memory families (cf. STG/LDG, STS/LDS).

## Latency (from `sm_90_latencies.txt`)
`ST` ∈ `mio_pipe` (MIO_SLOW_OPS), `VQ_AGU`, decoupled **read** scoreboard. The
store's completion isn't tracked by a per-instruction write scoreboard; ordering
against later ops relies on the memory model / fences. Same MIO latency class as
STG/STS.

## Verified encodings (`tests/st_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | PTX |
|---|---|---|---|
| `0x0000000502007985` | `0x001fe2000c101904` | `ST.E desc[UR4][R2.64], R5` | `st.u32` |
| `0x0000000502007985` | `0x001fe2000c101104` | `ST.E.U8 desc[UR4][R2.64], R5` | `st.u8` |
| `0x0000000502007985` | `0x001fe2000c101504` | `ST.E.U16 desc[UR4][R2.64], R5` | `st.u16` |
| `0x0000000402007985` | `0x001fe2000c101b04` | `ST.E.64 desc[UR4][R2.64], R4` | `st.u64` |
| `0x0000000402007985` | `0x001fe2000c101d04` | `ST.E.128 desc[UR4][R2.64], R4` | `st.v4.u32` |
| `0x0000100502007985` | `0x001fe2000c115904` | `ST.E.STRONG.SYS desc[UR4][R2.64+0x10], R5` | `st.volatile.u32 [+16]` |

Decoder `tools/decode_st.py`: **6/6 PASS**. `sz` is Hi64 low nibble (`...19`=32,
`...11`=U8, `...15`=U16, `...1b`=64, `...1d`=128); `.volatile` → `mem=10`
(`STRONG.SYS`, `...59`); the 24-bit offset (`+0x10`) sits in [63:40]; the low byte
`04` of Hi64 is the pinned `dst_wr_sb=7`∥`req` control tail.

### PTX→SASS mapping
| PTX | SASS (sm_90) |
|---|---|
| `st.u32 [genericptr], v` | `ST.E desc[URc][Ra.64], Rb` |
| `st.u8/u16/u64` | `ST.E.U8 / .U16 / .64` |
| `st.v4.u32` | `ST.E.128` |
| `st.volatile.u32 [p+16], v` | `ST.E.STRONG.SYS desc[URc][Ra.64+0x10], Rb` |
| `st.global.*` | `STG.E …` (space-specialized, not ST) |

**Key finding (mirrors LD):** `st.volatile` (generic) → `ST.E.STRONG.SYS` — the
volatile qualifier maps to STRONG semantics + SYS scope (`TABLES_mem_0` code 10),
forcing a system-scoped, uncached, ordered store.

## Open questions
- Non-memdesc / plain 0x385 forms — not emitted by ptxas on sm_90.
- Whether ST/STG's `TABLES_mem_0` ever diverges from LD/LDG's `TABLES_mem_1` for
  some sem/sco/private combo (both agree on the values probed here).
- The `.private` and cluster-scope (`CTA`) qualifiers for generic ST — not
  triggered by the basic kernels here.
