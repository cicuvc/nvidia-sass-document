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
