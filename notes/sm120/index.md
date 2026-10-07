# notes/sm120 — RTX Blackwell (sm_100/sm_120) encodings & silicon-verified behaviour

<!-- notes-status -->
**Status:** historical  
**Evidence:** mixed  
**Tier confidence:** medium  
**Last verified:** 2026-09  
**Probe:** not recorded in this note  
**Open items:** none  
**Audit:** `tools/notes_audit.py` · basis: 'silicon-verified' attestation

## Conclusion

This directory collects everything that is **specific to Blackwell** and therefore
does not belong in the sm_90 reference notes:

1. **Blackwell-only instruction encodings** — opcodes/variants that exist in
   sm_120 hardware (and/or the `sm_120` spec dump) but have **no counterpart in the
   sm_90 ISA**, or whose Hopper counterpart is a different mnemonic.
2. **Behaviour verified on Blackwell silicon only** (RTX 5090, GB202) where a real
   sm_90 re-test has not yet confirmed the same result.

Everything here was validated with: CUDA 12.8–13.1 ptxas/nvcc, driver 580.x,
RTX 5090, and the repo's SASS assembler (`assembler/`, arch=sm120) unless stated.

## Contents

| File | Topic |
|---|---|
| `encoding-addressing.md` | SM120 encoding substrate, control-word/stall encoding, `desc[UR]` cache-policy word decode, UTMALDG direct-pointer model, const-bank 0 layout, regcount rule, BSSY/SIMT-stack findings, S2R write-scoreboard requirement |
| `arch/local_memory_backing_va.md` | Silicon-derived local-address → backing-VA transform; warp/SM/CTA layout, SETLMEMBASE switching, and ptxas spill-frame EIATTR metadata |
| `arch/shared_memory_allocator.md` | Shared allocator: 100 KiB/SM pool, 128-byte quantum, 1 KiB static reserved prefix, USETSHMSZ accounting, and fragmentation probes |
| `subcore_compute_conflict.md` | GB202 per-subcore scalar/tensor execution conflicts, forwarding-based ALU topology, and raw NCU math/MIO throttle evidence |
| `fixed_admission_depth.md` | Corrected two-producer fixed scalar admission depths, complete mixed-leaf matrix, B200 comparison, and NCU leaf/throttle cross-check |
| `rf_writeback_conflict.md` | Even/odd 2R1W register-file writeback arbitration and same-subcore collision probes |
| `mio_lsu_xu_topology.md` | MIO/LSU/XU queue locality, LDG address-latch boundary, SM-wide LSU scaling, SHFL placement, throttle/OOO-completion behavior, and RF return paths |
| `adu_topology.md` | GB202 ADU placement after late MIO operand collection; BRX target replay, LDC/BAR classification, predication, and shared-vs-local scaling |
| `cbu_topology.md` | GB202 CBU queues and state paths; ADU-assisted group splitting, convergence fast path, scheduler stalls, effective credits, and cross-queue arbitration |
| `icache_topology.md` | GB202 frontend instruction cache: SM-wide 64 KiB ICC, 32 sets x 16 ways x 128 B, direct VA[11:7] index, virtual tag identity, ~12-target trace buffer, multi-subcore lookup conflicts, and GCC lower bound |
| `indexed_rf_topology.md` | Uniform-indexed GPR addressing (`R[URx]`) for MOV/HMMA: no extra pipe or throughput cost, early committed-URF selector snapshot, and no UDP forwarding |
| `udp_urf_topology.md` | GB202 uniform datapath: one fixed scalar UDP instruction/clock/subcore; 80-entry URF as 20 x 128-bit rows with a measured 1R2W throughput model |
| `gb202_sm_topology.svg` | Whole-SM architecture map synthesized from the frontend, RF, scalar/tensor, MIO, ADU/CBU, LSU/L1TEX, shared-memory, and LDGSTS probes |
| `gb202_compute_pipelines.svg` | One-subcore scalar/tensor pipeline hypothesis: RF collection, INT/FP family admission, specialized bodies, tensor subpipes, forwarding, and RF commit |
| `gb202_compute_pipelines.md` | Textual companion to the compute-pipeline diagram: measured hierarchy, family queue/pipe assignments, forwarding/writeback, and throttle relationships |
| `fixed_pipeline_forwarding_latency_zh.md` | 固定执行管线转发延迟中文总表：各 scalar leaf、predicate、MIO/CBU/R2UR/UDP 边、旁路带宽与 RF commit 建模规则 |
| `fixed_pipeline_issue_to_use_zh.md` | 固定管线持续依赖链的真实 issue-to-use 周期：phase-safe 4-cycle scalar path、WIDE low/high 的 consumer-specific 2/3/4/5/7-cycle 路径、HI operand-specific 4/9-cycle 路径、predicate guard 分流和转发修正规则 |
| `fixed_pipeline_latency_handoff_zh.md` | 固定管线延迟研究暂停交接：已确认参数、探针入口、复现命令、设计陷阱、未完成矩阵和恢复检查清单 |
| `alulite_latency.md` | ALU-Lite GPR/predicate pipeline latency: consumer-specific bypass boundaries, selector-vs-guard predicate paths, and initial cycle-simulator parameters |
| `aluheavy_latency.md` | Complete ALU-Heavy latency matrix: same-leaf and producer-class cross-leaf GPR bypasses, predicate loopback, and guard/CBU distribution |
| `fmalite_latency.md` | FMA-Lite latency matrix: universal t+2 FP32 bypass and the raw FP16/BF16 vs formatted-FP32 scalar result stages |
| `fmaheavy_latency.md` | FMA-Heavy latency matrix: early `Ra` payload, split WIDE low/high readiness, multiply `Pu`, and consumer-specific bypasses |
| `fp16_latency.md` | Coupled packed-FP latency: universal t+2 result broadcast, immediate-form `Ra` window, and HADD2.F32 crossing |
| `fp64_redirect_latency.md` | FP64/CLMAD redirected completion: layout-dependent unsafe visibility and the required event/scoreboard simulator model |
| `instr/getlmembase.md` | Silicon semantics of the warp-local backing base and its role in the local-address → device-VA transform |
| `instr/setlmembase.md` | Silicon proof that SETLMEMBASE redirects subsequent LDL/STL backing accesses |
| `notes/sm120/l2_slice_probe.md` | Attempts to count L2 slices on GB202; single-L2-backend evidence |

## Per-instruction sm_120 reference (`instr/`)

`instr/` now holds one note per **compute** mnemonic whose sm_120 form differs from the
sm_90 dump, plus every Blackwell-only compute mnemonic: **105 notes**, generated from
`sm120_instructions.txt` by `tools/sm120_notes_gen.py` (re-run it after a parser change;
`--check` fails when the tree is stale). Each note carries the CLASS list, FORMAT-derived
operand shapes, the 128-bit ENCODING map, PROPERTIES, legal-encoding conditions, pipe
membership, how many committed fixture cubins use the mnemonic, and where its sm_120
measurements live.

Machine registry of every measurement and the note that holds it:
[`measurements_index.md`](measurements_index.md) (`tools/sm120_measurements_index.py`).
The numbers are **not** copied into the instruction notes — an index plus a pointer keeps
one authoritative copy.

## Blackwell-only instructions referenced from these notes

| Mnemonic | Where documented | sm_90 relationship |
|---|---|---|
| QMMA / QMMA.SF / MXQMMA / OMMA | `instr/qmma.md`, `instr/mxqmma.md`, `instr/omma.md` (encodings) + `notes/sm90/arch/hmma_fda_model.md` §QMMA.SF, `tests/asm_construct/test_qmma*.py` (semantics, srcFmt enum E4M3/E3M4/E2M3/E5M2/E3M2/E2M1) | none — Hopper uses QGMMA/WGMMA |
| Uniform FP/convert/compare stack: `UFADD UFFMA UFMUL UFMNMX UFSEL UFSET UFSETP UFRND UF2F UF2I UF2IP UFHADD UFHFMA UI2F UI2I UI2IP UI2FP UIABS UIMNMX UVIADD UVIMNMX CS2UR` | `instr/<mnem>.md` | absent from the sm_90 dump — the sm_90 uniform ALU has no FP half |
| `UGETNEXTWORKID` | `instr/ugetnextworkid.md` | absent from the sm_90 dump |
| `UMEMSETS`, `UVIRTCOUNT` | `instr/umemsets.md`, `instr/uvirtcount.md` | absent from the sm_90 dump |
| Tensor-map helper contract (`cuTensorMap*` → 128-byte descriptor) | `notes/sm90/arch/cutensormap.md`, `tests/asm_construct/test_tmap_helper.py` | TMA descriptors exist on sm90 via UTMALDG/UTMASTG, but the helper bit-patterns recorded were probed on sm_120 |
| F2FP extra destination formats `.E2M1` / MXFP4 PACK_AB_MERGE_C nibble packing | `instr/f2fp.md` + `notes/sm90/instr/f2fp.md` "runs on sm120 hardware" rows | absent from the sm_90 spec dump — do not list them as sm_90 variants |
| CCTL.LDCU.IV.DEEP + UTMACCTL.IV pairing | `instr/cctl.md`, `instr/utmacctl.md` + `notes/sm90/instr/cctl.md` (empirically RTX 5090) | cctl/utmacctl exist on sm_90; this specific IV.DEEP pairing observed only on Blackwell |

## Silicon-only-on-Blackwell claims awaiting a real sm_90 verdict

Consolidated per-instruction register: see **`silver-status.md`**.
Rationale and run matrix: `notes/sm90/arch/sm90_resilver_audit.md`.

Rules of thumb for what stays in `notes/sm90/…` vs moves here:

- Mechanism exists in both ISAs, evidence only from the 5090 → keep the note under
  `sm90/` (it documents an sm_90 ISA object), tag the section's evidence as
  "(silicon: SM120)", and record it in `silver-status.md` until re-tested.
- The instruction/format/ABI item does not exist at all on sm_90 → document it here.

