# SYNCS — Shared-memory synchronization (mbarrier + shared uniform atomics)

**Opcode mnemonic:** `SYNCS` — 9 CLASSes / opcodes (below) | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` | **VIRTUAL_QUEUE:** `VQ_SYNCS_UNORDERED_WR` | compute-only (`SHADER_TYPE==CS`)

The Hopper **shared-memory synchronization** instruction: it is what all `mbarrier.*` PTX
lowers to (arrive / expect_tx / try_wait, incl. cluster-scope via distributed shared
memory), plus a set of **shared-memory uniform atomics** (exchange / CAS / load). It is a
**decoupled** op — its result (token/loaded value) is tracked by a write scoreboard, not a
fixed latency. Mechanism/semantics for the TMA + mbarrier producer→consumer flow live in
`../arch/tma_mbarrier.md`; this note is the per-opcode instruction reference.

## Variant taxonomy (9 CLASSes)
| opcode `{b91,[11:0]}` | CLASS | group | role |
|-----------------------|-------|-------|------|
| **0x19a7** | `syncs_arrive_` | mbarrier | arrive / arrive.expect_tx (transaction count) |
| 0x19a7 | `syncs_tcnt_` (ALT) | mbarrier | expect_tx-only (tx count) |
| **0x15a7** | `syncs_phasechk_` | mbarrier | try_wait / test_wait phase-parity check |
| 0x19b1 | `syncs_cctl_` | mbarrier | barrier cache-control (per-addr) |
| 0x09b1 | `syncs_cctl_all_` | mbarrier | barrier cache-control (all) |
| 0x15b1 | `syncs_ld_` | mbarrier | load barrier state (`.WATCH`) into GPR |
| **0x15b2** | `syncs_uniform_exch_` | atomic | shared **exchange** (used by `mbarrier.init`) |
| 0x13b2 | `syncs_uniform_cas_` | atomic | shared **compare-and-swap** |
| 0x19b2 | `syncs_uniform_ld_` | atomic | shared **load** (uniform) |

Opcode structure: `…a7` = mbarrier arrive/phasechk; `…b1` = barrier cctl/ld (GPR);
`…b2` = shared uniform atomics (uniform-predicate guarded, `@UPg`).

## Group A — mbarrier ops
### ARRIVE / expect_tx (`0x19a7`)
`SYNCS.ARRIVE.TRANS64[.RED|.TMASK][.<paramtype>] Rd, [addr], Rb`
- `paramtype` [86:84] `PARAMTYPE` selects the {arrive-count, tx-count} sources:
  `A1TR`(0, hidden default) / `A1T0`(1) / `A0T1`(2) / `A0TR`(3) / `A0TX`(4) / `ART0`(5)
  — `A`=arrive +1/+0, `T`=tx +1/+0/+R(reg)/+X(imm). So `mbarrier.arrive`→`A1T0`,
  `mbarrier.arrive.expect_tx`→`A1TR` (default), `mbarrier.expect_tx`→`A0TR`.
- `retval` [74:73]: `OLDSTATE`(0, hidden → token in `Rd`) / `TMASK`(1) / `RED`(2, remote
  reduce, `Rd`=RZ). Cross-CTA (DSMEM) arrive uses `.RED` (`SYNCS.ARRIVE.TRANS64.RED`).
- operands: `Rd` [23:16] token dest, `Rb` [39:32] count value, addr = `[Ra + URc + off]`
  (`Ra`[31:24], `URc`[69:64], `off`[63:40]).

### PHASECHK / try_wait (`0x15a7`)
`SYNCS.PHASECHK.TRANS64[.TRYWAIT] Pu, [addr], Rb` — `wait` [72] {ONCE / `.TRYWAIT`};
sets predicate `Pu` [83:81] = "has the phase flipped?" (non-blocking; the wait is a
software spin, see `tma_mbarrier.md`).

### mbarrier maintenance
`syncs_cctl_`/`_all_` (`…b1`) = barrier cache control; `syncs_ld_` = load barrier state
into a GPR (`.WATCH` = watch/monitor mode).

## Group B — shared uniform atomics (`@UPg`, `…b2`)
`SYNCS.EXCH.64 URd, [URa(+off)], URb` — atomic exchange; **`mbarrier.init` lowers to this**
(`SYNCS.EXCH.64 URZ, [UR], UR`). `SYNCS.CAS.64 URd,[URa],URb,URc` — compare-and-swap;
`SYNCS.LD.64 URd,[URa]` — uniform load. Fields: `URd`[21:16], `URa`[29:24], `URb`[37:32],
`off`[63:40].

## Bit layout (128-bit)

### SYNCS.ARRIVE.TRANS64 (0x19a7)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [124:122],[109:105] | opex | 8 | `TABLES_opex_0(batch_t,usched_info)` | scheduling |
| [121:116] | req_bit_set | 6 | — | scoreboard wait mask |
| [115:113] | src_rel_sb | 3 | `VarLatOperandEnc(rd)` | read scoreboard |
| [112:110] | dst_wr_sb | 3 | `VarLatOperandEnc(wr)` / `*7` (RZ) | write scoreboard |
| [103:102] | pm_pred | 2 | — | perfmon predicate |
| [91],[11:0] | opcode | 13 | 0x19a7 | |
| [89:87] | Pu | 3 | Predicate | PHASECHK dest predicate |
| [86:84] | paramtype | 3 | PARAMTYPE | A1TR=0,A1T0=1,A0T1=2,A0TR=3,A0TX=4,ART0=5 |
| [83:81] | Pu | 3 | Predicate | ARRIVE dest pred / PHASECHK |
| [80:77] | mem | 4 | `TABLES_mem_0(sem,sco,private)` | memory ordering |
| [74:73] | retval | 2 | — | OLDSTATE=0,TMASK=1,RED=2 |
| [72] | wait | 1 | — | ONCE=0, `.TRYWAIT`=1 (PHASECHK) |
| [69:64] | URc | 6 | UniformRegister | uniform base register |
| [63:40] | Ra_offset | 24 | SImm(24) | signed offset |
| [39:32] | Rb | 8 | Register | count value / token |
| [31:24] | Ra | 8 | Register | address register (RZ=URc-only) |
| [23:16] | Rd | 8 | Register | token destination (ARRIVE only) |
| [15] | Pg_not | 1 | Pg@not | predicate negate |
| [14:12] | Pg | 3 | Predicate | guard predicate |

### Shared uniform atomics (...b2, 128-bit)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [69:64] | URc | 6 | UniformRegister | uniform base (or absent) |
| [63:40] | Ra_offset | 24 | SImm(24) | signed offset |
| [37:32] | URb | 6 | UniformRegister | source / exchange value |
| [29:24] | URa | 6 | UniformRegister | address register |
| [21:16] | URd | 6 | UniformRegister | result register (EXCH/LD) |
| [14:12] | UPg | 3 | UniformPredicate | uniform guard predicate |

CAS variant adds `URc` at [69:64] for the compare value.

### Cache-control (...b1, 128-bit)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [29:24] | URa | 6 | UniformRegister | address register |
| [63:40] | Ra_offset | 24 | SImm(24) | signed offset |
| [23:16] | Rd | 8 | Register | (syncs_ld_ only) |

## Latency
`mio_pipe`, `OP_SYNCS` set. `INST_TYPE_DECOUPLED_RD_WR_SCBD` / `VQ_SYNCS_UNORDERED_WR`:
- the token/loaded-`URd` result is **write-scoreboard tracked** (consumers wait on the SB,
  varying producer→consumer latencies `sm_90_latencies.txt:189`); `_`/`RZ`-dest arrives use
  `wr_sb=7`.
- the `UPg`/predicate result (`PHASECHK` `Pu`) has small fixed latencies (line 346).

## Verified encodings (decoder: `tools/decode_syncs.py`)
Self-test 8/8; **24/24 SYNCS across mbarrier/TMA test cubins** (`mbarrier_test`,
`mbar_arrive_test`, `tma_test`, `tma_store_test`) + 4/4 in the cluster-mbarrier test.

| Lo64 | Hi64 | Disassembly | from |
|------|------|-------------|------|
| 0x00000000ffff79a7 | 0x000fe20008000006 | `SYNCS.ARRIVE.TRANS64 RZ, [UR6], R0` | arrive.expect_tx (A1TR) |
| 0x000000ffff0279a7 | 0x000e240008100006 | `SYNCS.ARRIVE.TRANS64.A1T0 R2, [UR6], RZ` | arrive (token in R2) |
| 0x00000002ff0679a7 | 0x0084220008500004 | `SYNCS.ARRIVE.TRANS64.ART0 R6, [UR4], R2` | arrive n (reg count) |
| 0x000000ffffff79a7 | 0x000fe20008100407 | `SYNCS.ARRIVE.TRANS64.RED.A1T0 RZ, [UR7], RZ` | remote/DSMEM arrive |
| 0x00000000ff0075a7 | 0x000e240008000144 | `SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR4], R0` | try_wait.parity |
| 0x00000004063f85b2 | 0x0000640008000100 | `@!UP0 SYNCS.EXCH.64 URZ, [UR6], UR4` | mbarrier.init |

Hand-check `SYNCS.ARRIVE.TRANS64.A1T0 R2,[UR6],RZ`: opcode 0x19a7; `paramtype`[86:84]=1→A1T0;
`retval`=0→(none); `Rd`[23:16]=2→R2; `URc`[69:64]=6→[UR6]; `Rb`[39:32]=RZ.

## PTX→SASS mapping (summary; details in `tma_mbarrier.md`)
| PTX | SASS |
|---|---|
| `mbarrier.init.shared.b64` | `SYNCS.EXCH.64 URZ, [UR], UR` |
| `mbarrier.arrive.shared.b64 tok,[b]` | `SYNCS.ARRIVE.TRANS64.A1T0 Rd,[..],RZ` |
| `mbarrier.arrive.expect_tx [b],k` | `SYNCS.ARRIVE.TRANS64 RZ,[..],Rk` (A1TR) |
| `mbarrier.expect_tx [b],k` | `SYNCS.ARRIVE.TRANS64.A0TR …` |
| `mbarrier.arrive.release.cluster.b64` (remote) | `SYNCS.ARRIVE.TRANS64.RED …` |
| `mbarrier.try_wait.parity …` | `SYNCS.PHASECHK.TRANS64.TRYWAIT Pu,[..],R` |

Note: mbarrier is a **distinct** cluster/shared-sync mechanism from the CGA hardware
barrier `UCGABAR_*` (`ucgabar_arv.md`) — `barrier.cluster.*` → `UCGABAR`, whereas
`mbarrier.*` (incl. `.cluster` scope via `mapa`/DSMEM) → `SYNCS`.

## Open questions
- `SYNCS.CCTL`/`syncs_ld_` (barrier cache-control / state-load with `.WATCH`) renderings are
  not sampled from emitted code; documented from the ISA fields only.
- `SYNCS.CAS.64`/`SYNCS.LD.64` uniform-atomic operand orderings are spec-derived (not yet
  observed in a compiled kernel).
- `PHASECHK` `ONCE` (non-`.TRYWAIT`) form (blocking `test_wait`) is unsampled.
