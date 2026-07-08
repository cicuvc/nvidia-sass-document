# LDGSTS — Async global→shared copy (`cp.async`)

**Opcode mnemonics:** `LDGSTS` = `0b1111110101110` = **0x1fae** (RR / desc: global addr in register pair) / `0b1110110101110` = **0x1dae** (RUR: uniform-register base) | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` | **VIRTUAL_QUEUE:** `VQ_AGU_UNORDERED_WR` (16) | compute-only (`SHADER_TYPE==CS`)

## Semantics
LDGSTS is the SASS lowering of PTX **`cp.async`** — the Ampere-era asynchronous
copy that streams data **directly from global memory into shared memory** without
passing through registers (bypassing the register file / L1 round-trip). It is the
*non-TMA* async copy: element/vector granularity (4/8/16 B per thread), each thread
issues its own copy (contrast the single-thread bulk TMA `UTMALDG`/`UBLKCP`).
Completion is tracked by the counted-group scoreboard mechanism
(`LDGDEPBAR` + `DEPBAR.LE`, see `depbar.md`), **not** an mbarrier.

Operands: `LDGSTS.E[.mods] [Rd], <global-addr>[, Pnz]`
- `Rd` — **shared** destination register (field `Rd`[23:16], fed by the `Rb` slot)
- global source — `desc[URc][Ra.64]` (descriptor form, ptxas default on sm_90) or
  `[Ra.64]` (plain 64-bit pair) or uniform-base `[Rb+URc]` (0x1dae)
- `Pnz` — optional predicate: when false, the copy is **zero-filled** (`.ZFILL`)

## Variant overview
| variant | opcode | address form |
|---|---|---|
| `ldgsts__RR32U` | 0x1fae | `[Ra]`(32-bit) + URc + offsets |
| `ldgsts__RR64U` | 0x1fae | `[Ra.64]` + URc + offsets |
| `ldgsts__desc_RRU` | 0x1fae | `desc[URc][Ra.64]` (descriptor) |
| `ldgsts_no_ra__RRU` [ALT] | 0x1fae | RZ-base + URc |
| `ldgsts__RUR` | 0x1dae | `[Rb+URc]` uniform base |
| `ldgsts_memdesc_` | 0x1dae | descriptor |
| `ldgsts_no_ra__RUR` [ALT] | 0x1dae | RZ-base RUR |

`memdesc` bit [76] selects descriptor addressing. **On sm_90 ptxas always emits
the descriptor form** `desc[UR4][Ra.64]` (opcode 0x1fae, memdesc=1) — the same
`desc[UR]` global-addressing convention seen in `LDG`/`STG` (`ldg.md`).

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `e` | (opcode) | — | EONLY_ldgsts | E (only value; always printed `.E` = 64-bit extended addr) |
| `loc` | loc | [81] | LOC | BYPASS=0 (`.BYPASS`), ACCESS=1 (default,unprinted) |
| `cop` | cop | [86:84] | COP | EF=0,EN=1(default),EL=2,LU=3,EU=4,NA=5 (6,7 INVALID) |
| `sp2` | sp2 | [72:71] | SP2 | nosp2=0, LTC64B=1, LTC128B=2, LTC256B=3 (L2 prefetch size) |
| `sz` | sz | [75:73] | SZ_32_64_128 | 32=4(default,unprinted),64=5,128=6 |
| `fc` | fc | [82] | FILLCTRL | nofillctrl=0, ZFILL=1 |
| `sem`/`sco`/`private` | mem | [80:77] | `TABLES_mem_3(...)` | CONSTANT/WEAK/STRONG/MMIO × scope |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 desc[URc] |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

**Key mapping finding:** PTX **`.ca`** → `loc=ACCESS` (default, `LDGSTS.E`),
**`.cg`** → `loc=BYPASS` (`LDGSTS.E.BYPASS`) — i.e. `.ca`/`.cg` control the
**L1 access/bypass (`loc`)** bit, *not* the `cop` field (which stayed EN in all
tested cases). `.cg` (cache-global, bypass L1) requires `sz==128` (CONDITION:
"If BYPASS is specified, size must be 128"). This matches PTX: `cp.async.cg` is
16-byte-only.

Other mappings: `cp-size` 4/8/16 → `sz` 32/64/128; a shorter `src-size` (or a
false `ignore-src` predicate) → `.ZFILL`; `.L2::64B/128B/256B` prefetch →
`sp2` LTC64B/128B/256B; `.L2::cache_hint` → descriptor carries the policy.

## Bit layout (128-bit map, desc/RR form 0x1fae)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard (source regs) |
| [112:110] | dst_wr_sb | `VarLatOperandEnc(wr)` — see below |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x1fae |
| [90] | Pnz_not | zero-fill predicate negate |
| [89:87] | Pnz | zero-fill predicate |
| [86:84] | cop | COP |
| [82] | fc | FILLCTRL (ZFILL) |
| [81] | loc | LOC (BYPASS/ACCESS) |
| [80:77] | mem | sem/sco/private (via `TABLES_mem_3`) |
| [76] | memdesc | 0 / 1 desc |
| [75:73] | sz | SZ_32_64_128 |
| [72:71] | sp2 | SP2 (L2 prefetch) |
| [70] | input_reg_sz | 64-bit Ra distinguisher |
| [69:64] | Ra_URc | descriptor / uniform base UR |
| [63:44] | Rb_offset | 20-bit shared offset |
| [43:32] | Ra_offset | 12-bit global offset |
| [31:24] | Ra | global address register |
| [23:16] | Rd | shared destination register |
| [15] / [14:12] | Pg_not / Pg | predicate |

## Completion & scoreboards
`INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VQ_AGU_UNORDERED_WR` — LDGSTS is a decoupled
op whose write is *unordered*. Observed **`wr_sb=7`** (no ordinary write
scoreboard): the copy's completion is **not** tracked by a normal SB but fed into
the hidden async-group tracker. The group is committed by `LDGDEPBAR`
(`cp.async.commit_group`, sets `wr_sb=k` counting the group on SBk) and waited on
by `DEPBAR.LE SBk, N` (`cp.async.wait_group N`). Full pipeline in
`depbar.md`. `IDEST_SIZE=0` (no register result — data lands in shared).

## Cross-comparison (async copy family)
| op | PTX | granularity | issue | completion |
|---|---|---|---|---|
| **LDGSTS** | `cp.async` | 4/8/16 B per thread | **per-thread** | LDGDEPBAR group + `DEPBAR.LE` |
| `UBLKCP` | `cp.async.bulk` | bulk bytes | single elected thread | mbarrier tx / bulk-group |
| `UTMALDG` | `cp.async.bulk.tensor` | tensor tile | single elected thread | mbarrier tx-count |

LDGSTS is the **only per-thread** async copy; the bulk/TMA ops are single-thread
uniform-datapath. All three land in shared and bypass the register file.

## Latency (from `sm_90_latencies.txt`)
`LDGSTS` ∈ `mio_pipe` (`sm_90_latencies.txt:3`), `VQ_AGU_UNORDERED_WR`. Decoupled
read+write scoreboard type but the write is async/unordered (`wr_sb=7`); real
completion ordering flows through the counted-group scoreboard drained by
`DEPBAR.LE`.

## Verified encodings (`tests/ldgsts_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | PTX |
|---|---|---|---|
| `0x0000000002077fae` | `0x000fe2000b921844` | `LDGSTS.E [R7], desc[UR4][R2.64]` | `cp.async.ca …,4` |
| `0x0000000002077fae` | `0x000fe2000b921a44` | `LDGSTS.E.64 [R7], desc[UR4][R2.64]` | `cp.async.ca …,8` |
| `0x0000000002077fae` | `0x000fe2000b921c44` | `LDGSTS.E.128 [R7], desc[UR4][R2.64]` | `cp.async.ca …,16` |
| `0x0000000002077fae` | `0x000fe2000b901c44` | `LDGSTS.E.BYPASS.128 [R7], desc[UR4][R2.64]` | `cp.async.cg …,16` |
| `0x0000000004077fae` | `0x000fe80008161c44` | `LDGSTS.E.128.ZFILL [R7], desc[UR4][R4.64], P0` | `cp.async.ca …,16,src-size` |
| `0x0000000002077fae` | `0x000fe2000b921d44` | `LDGSTS.E.LTC128B.128 [R7], desc[UR4][R2.64]` | `cp.async.ca.L2::128B …,16` |

Decoder `tools/decode_ldgsts.py`: **6/6 PASS**. `sz` is Hi64 [75:73]
(`...18`=32, `...1a`=64, `...1c`=128); `.BYPASS` clears loc[81] (`...1c`→`...1c`
with the loc bit low: `0b90` vs `0b92`); `.LTC128B` sets sp2[72:71] (`...1d`);
`.ZFILL` sets fc[82] + a live `Pnz` (P0) with wr_sb=0 here (group in a pipeline).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `cp.async.ca.shared.global [d],[s],4/8/16` | `LDGSTS.E[.64/.128] [Rd], desc[UR][Ra.64]` |
| `cp.async.cg.shared.global [d],[s],16` | `LDGSTS.E.BYPASS.128 …` |
| `cp.async…,cp-size,src-size` (partial) | `…​.ZFILL …, Pnz` (predicated zero-fill) |
| `cp.async…​.L2::128B` | `LDGSTS.E.LTC128B…` |
| `cp.async.commit_group` | `LDGDEPBAR` |
| `cp.async.wait_group N` / `wait_all` | `DEPBAR.LE SBk, N` / `…,0` |

## Open questions
- The `cop` field (EF/EN/EL/LU/EU/NA) stayed **EN** in all tested cp.async forms —
  which PTX qualifier (if any) drives it to EF/EL/etc. for LDGSTS (vs the `.ca/.cg`
  → `loc` mapping found here).
- Non-descriptor forms (0x1dae RUR, plain `[Ra.64]`) — when ptxas prefers them
  over the descriptor form (all sm_90 cases here used desc).
- `sem`/`sco`/`private` (`TABLES_mem_3`) values for cp.async — not exercised
  (all WEAK/nosco here).
