# Silver-status register — claims proven only on Blackwell silicon

Derived from `notes/sm90/arch/sm90_resilver_audit.md`.  Each row is a behaviour whose
**only** hardware evidence is an RTX 5090 run (or an RTX 5090-captured encoding
vector).  Status updates go here first; when a row is confirmed on real sm_90
silicon the corresponding note's section header should say so and this row can be
marked done.

`blocked-vectors` = test contains hard-coded `(lo64,hi64)` reference tuples captured
from sm_120 assembly; byte-exact check fires under ASSEMBLER_ARCH=sm90 while the GPU
semantics half behaves.
`blocked-dialect` = test source uses sm_120 FORMAT shapes that the sm_90 spec
rejects at match time (needs a per-arch source rewrite).
`blocked-uldc`    = kernel loads the default cache descriptor with the sm_120
`LDCU + req={x}` pattern; on sm_90 ULDC writes no scoreboard ⇒ ILLEGAL_ADDRESS(700)
(`assembler_sm90_port.md`, "ULDC timing investigation").

## Instructions / mechanisms without a sm_90 silicon verdict yet

| Note | Claim depending on SM120-only evidence | Test | Blocker |
|---|---|---|---|
| instr/ldg.md | desc[UR] LDG semantics & scoreboard choreography | test_ldg | blocked-uldc |
| instr/stg.md | STG + policy-descriptor store paths | test_ldg_stg | blocked-uldc |
| instr/ldgsts.md | cp.async chunking & scoreboard releases | test_ldgsts | blocked-uldc |
| instr/hmma.md; arch/hmma_fda_model.md; arch/hmma_pipeline.md | HMNA/FDA behaviour, fragment results, pad requirements | test_hmma, test_hmma_precision, test_hmma_model | blocked-uldc |
| instr/s2ur.md | SR_CTAID.X *last-writer-wins* among CTAs | test_s2ur | **delta**: H20 reads 1 where RTX 5090 read 2 (grid=3 case) — needs probe, not just rerun |
| instr/r2ur.md | R2UR.FILL nonconformity-mask lanes semantics | test_r2ur | blocked-dialect (`R2UR …FILL` variant absent from sm_90 spec) |
| instr/up2ur.md | UPR→UR add/mask forms | test_up2ur | blocked-vectors (GPU half passed) |
| instr/voteu.md | VOTEU.ANY/EQ ballot+UP capture | test_voteu | blocked-vectors (GPU half passing) |
| instr/atom.md (ATOM/ATOMG) | nvcc-exact encodings incl. scope/pred bit patterns | test_atom | blocked-vectors |
| instr/imnmx.md | predicate-form IMNMX encoding | test_imnmx | blocked-dialect |
| instr/uldc.md (+depcheck model) | LDCU.128 form; desc-dependency CFG edge | test_ldcu, test_depcheck | blocked-dialect / arch-conditional edge (ULDC dst_wr_sb=*7) |
| instr/umov.md | UMOV.64 pair-load form | test_umov | blocked-dialect (sm_90 has no .64 variant; spec offers URd←imm32 / URd←URb only) |
| instr/usel.md | USEL.64 | test_usel | blocked-dialect |
| instr/uimad.md | UIMAD.HI combined form | test_uimad | blocked-dialect |
| instr/uisetp.md | UISETP …AND…U64; UP-sourced compare operands | test_uisetp | blocked-dialect (sm_90 UISETP carries merge-predicate slots) |
| instr/viadd.md | VIADD.U32 modifier name | test_viadd | blocked-dialect (sm_90 modifier set is FMT_viadd) |
| instr/mbarrier.md / arch/tma_mbarrier.md | SYNCS-based mbarrier kernel chain w/ UIADD3 forms | test_mbarrier | blocked-dialect (UIADD3 slot typing differs) |
| instr/ublkcp.md (+multicast section), utmacctl.md, utmaldg.md, utmaredg.md, utmastg.md | TMA-store/load descriptor pointer flows; "MULTICAST does NOT work" verdict | test_ublkcp*, test_utma* | blocked-dialect: ELECT rejected by sm_90 db conditions inside these kernels |
| instr/uclea.md | const-scale window rules (#constSizeU04 ≤ 8) | test_uclea | blocked-condition: sm_90 spec restricts immediates the sm_120 form uses |
| instr/yield.md | spin-lock forward-progress boundaries | test_yield | **delta-ish**: FAILURES on H20 (subcore_yield passes) — scheduler/state differences to document per-SKU |
| arch/cache_descriptor.md | default-cdesc semantics behind ULDC/LDCU probes | test_cache_desc | flaky both GPUs (per-stream attribute state); pre-existing |
| kernel-param ABI (>8-byte params land where?) | bigparam zero-reads for bytes ≥8 on H20 | test_bigparam | **delta**: param placement differs from the SM120 0x380 layout findings |

## Already dual-verified (for contrast)

Families re-replicated on H20 during the audit run (see audit §1): forwarding
boundary sweeps (23/27 edges), MUFU/FFMA latencies & throughput, depbar, cbu_state,
BSSY/BSYNC/BRX/JMX/BREAK/BPT/TRPC/WARPSYNC, HFMA2/HADD2/HSET2/HMNMX2,
conversions, PRMT/SHF/SHFL/VOTE/ELECT/NANOTRAP, uniform ALU stack
(UIADD3/ULEA/ULEPC/ULOP3/UPOPC/UPLOP3/UPRMT/USGXT/USHF), LDS/LDSM/lmembase,
UBLKRED/UBMSK/UBREV, VIMNMX/IABS/IMAD(.X)/IADD3/QSPC/PDL/PMTRIG/
CLMAD/IDP/SGXT/RTT/SETCTAID/S2R/BMOV/REUSE — plus everything previously marked
"verified sm_90 + sm_120" (f2fp-hopper subset, hfma2 quirk, bpt/shf PTX mappings).

## Resilver progress log (H20, remote Hopper)

Suite-runs with `ASSEMBLER_ARCH=sm90`, tools/run_tests.py:

| Date | Pass/Fail | Notes |
|---|---|---|
| run 1 | 83 / 40 | pre-fix baseline (SM120-only suite) |
| b1 | 89 / 34 | arch/depcheck/up2ur/voteu/atom vectors; s2ur flake |
| b2 | 89 / 34 | dialect gates start; wiring bugs introduced |
| b3 | 93 / 30 | imnmx reduced surface, uimad/uiclea(u) gates land |
| b4 | 93 / 30 | archutil v3: ULDC-doctrine REMOVED — see port-note |
| b5 | 95 / 28 | test_ldg green via canonical template |
| b6 | 98 / 25 | UI-URZ & MOV→UMOV rules restored; umov/usel/udp_int green |
| b7 | 99 / 24 | **UniformRegister.URZ encoded as 63 (enum truth)**; ELECT lo-parity with ptxas |
| b8 | 101 / 22 | wide-slot exemption for URZ; r2ur/viadd gates finish |
| b9 | 102 / 21 | LDCU rewrite restricted to genuine .64 lines (ldcu green) |
| — | hang | ublkcp/utmaldg deadlocked H20 → bare-URZ spelling adopted, family blacklisted under sm90 (`HANG_SUSPECT_sm90.txt`) |
| b11 | 103 / 117 (88%) | first clean full pass; test_mbarrier now GREEN |
| b12 | 106 / 117 | hmma trio + ldgsts? canonical template verified on H20 |
| b13 | 106 / 117 | bigparam & viadd turn green; ldg_stg fixed (illegal combo dropped) |
| **b14** | **113 / 123** | TMA family un-blacklisted and GREEN: utmaldg/stg/redg/utmacctl(+mcast OQ), ublkcp, hmma trio, ldg_stg — suite clean end-to-end |

### B14 residual reds (10) — all characterised
| Test | Status |
|---|---|
| f2fp, omma, qmma ×2, tmap_helper | by-design Blackwell-only |
| cache_desc, int_cbu_forward, s2ur(flaky when poisoned-context races appear) | flaky/timing, known |
| yield | per-SKU forward-progress boundaries — needs the bounded probe |
| ldgsts | LDGSTS encode bits [70,74,83] differ vs nvcc on sm_90 — deep-dive pending |
| ublkcp_multicast | downgraded to INFO/OQ: multicast delivers data but hand-built mbar completion semantics unresolved |

### New architecture findings recorded this session
* `CCTL.E.C.LDCU.IV.{DEEP,SHALLOW}` is **Blackwell-only**: the sm_90 ISA dump
  has no cctl_c_ldcu_* classes, libcublasLt(Hopper) only ever emits
  `CCTL.IVALL`, and a live ptxas(sm_90a, CUDA 12.8) compile of the documented
  tensormap.cp_fenceproxy/acquire fence chain lowers to a single
  `UTMACCTL.IV [UR4]` (lo=0x…79b9).
* On Hopper **`UTMACCTL.IV` alone refreshes the descriptor/LDCU cache**
  (isolation-matrix probe): unlike sm_120 where CCTL.DEEP must precede it.
  `UTMACCTL.IVALL` alone leaves stale entries.
* Multicast rejection codes differ (sm_120:715 ILLEGAL_INSTRUCTION-encoding;
  sm_90 executes) — PTX docs put `.multicast` at sm_90+.
* mbarrier choreography rule for hand-built kernels: init must be fenced from
  consumer observation (BAR.SYNC.DEFER_BLOCKING right after SYNCS.EXCH.64),
  expect_tx folded before issuing the bulk copy.

### Final per-arch parameter layout rule (H20, bank sweep probe_bankmap.py)
Params are placed **contiguously at PARAM_CBANK base** in declaration order:
`out<8> @0x210`, `p<N> @0x218` with word k at `base+8+4k` — no alignment
holes up to 128B. The original "bigparam zeros" finding was a stale sm_120
constant (0x38c) inside the test, not an ABI delta. test_bigparam is now
arch-aware (`assembler.arch.current().param_base`) and GREEN.

### Dead-assertion note
`STG.E.WEAK.SYS.ORDERED` MatchErrors on BOTH spec dbs — removed as an
unreachable assertion.

### Root cause that unblocked the largest chunk
`assembler/operand.py` encoded `URZ == 255` (GPR convention) while the ISA enum
says `UniformRegister.URZ == 63`. Every CLASS condition of the form
`(URx == \`UniformRegister@URZ)` therefore evaluated false, rejecting a whole
family of legal placeholders. After the fix our `ELECT P1, URZ, PT` lo64 is
bit-identical to what nvcc emits on sm_90a. No generated bits changed for real
registers — only condition evaluation, asm printing and depcheck sentinels.

### Key resolved findings
* S2UR SR_CTAID.X "1 vs 2" was a **race artifact** of intra-process context
  poisoning (see sticky-fault gotcha) — repeats flip between runs.
* The ldg-family 700s were never cache-descriptor related: depcheck had
  flagged missing address-producer req coverage; canonical template fixes them
  (`ldg` done; `ldg_stg`, `ldgsts`, hmma trio still need the refactor).

### Remaining open items
* SYNCS.EXCH.64 sm_90 spelling rejected by matcher despite spec-shaped args
  (`test_mbarrier`) — needs ptxas-reference diff on H20.
* ELECT: conditions pass and direct SassEncoder encodes fine, but through
  assemble_flat a nondeterministic `TypeError: 'tuple' object cannot be
  interpreted as an integer` escapes without internal frames (blocks
  ublkcp/utma respins). Tooling bug, next-session target.
* bigparam >8-byte param zero-read on H20 (ABI probe pending).
* yield forward-progress boundaries per-SKU note row.

### Fresh finds from the last pass (open)
* **VIADD negate-A positional delta**: under sm90 the `.32` form encoding
  `VIADD R2, -R0, R1` does not set the hi64 bit72 that sm120 uses for
  negate-a — captured in `test_viadd` byte check ("U32-Ra"). Next step:
  nvcc-reference bit hunt with `-arch=sm_90a` and a PTX snippet forcing the
  negate through arithmetic instead of modifier.
* TMA/UBLKCP hand-built kernels deadlock on H20 even after assembling —
  blacklist stays until FENCE/arrive-expect_tx ordering is reconciled with
  nvcc-generated reference (target: dump ptxas SASS for
  cp.async.bulk.tensor + mbarrier completion chain).
