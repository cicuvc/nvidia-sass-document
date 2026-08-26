# Resilver audit — which asm_construct-backed claims still need real sm90 verification

**Motivation:** most `notes/sm90/instr/*` sections tagged *"Resolved: silicon-verified
(SM120)"* were validated on **RTX 5090 (Blackwell)** because `assembler/` originally
targeted sm_120 and the local GPU is an RTX 5090.  This audit separates those claims into
(1) already re-replicated on real Hopper silicon, (2) blocked by tooling/reference-vector
issues, and (3) genuine sm90≠sm120 behavioral deltas needing deeper probing.

## Environment of the first full sm90 rerun

- GPU: **NVIDIA H20, compute_cap 9.0**, driver 580.76.05 (cc9.0 == sm_90 family;
  H20 is bandwidth/reduced-throughput Hopper, not H800/H100 — absolute *throughput*
  numbers won't transfer to H100-class parts, but ISA/scheduler/scoreboard behaviour does).
- Harness: repo synced to remote, `ASSEMBLER_ARCH=sm90`, `tools/run_tests.py -j 6`.
- Result: **123 tests: 83 pass / 40 fail** (~110 s wall).

## 1. Re-replicated on H20 (SM120-only evidence may be upgraded to dual-verified)

The passing set covers essentially every non-failing semantic probe:

| Domain | Tests passing on H20 |
|---|---|
| Integer | iadd3, imad(.X), iabs, sgxt, shf, lop3, bmsk/brev/flo/popc, prmt, vimnmx, lea |
| FP32 | ffma (+throughput), fmul/fadd, fmnmx/fset, fchk, fswzadd, mufu (+latency, +throughput) |
| FP16 | hadd2/hmul2, hfma2 (incl. SAT quirk) , hfma2_iswz, hset/hsetp2/hmnmx2 |
| Convert | i2i/i2f/f2i/f2f (`conversions`), f2fp_hopper (Hopper F2FP subset) |
| Uniform | uiadd3, ulea, ulepc, ulop3, upopc, uplop3, uprmt, usgxt, ushf, umov? no — see §3 |
| Memory/lmem | lds_sts, ldsm, lmembase, ublkred (S2G), reuse |
| CBU/control flow | bssy_bsync, brx, jmp/jmx, break, bpt_trap, depbar, rtt, cbu_state, trpc_write, warpsync_collective, setctaid, s2r, pdl, pmtrig, qspc, clmad_idp, usetshmsz |
| Forwarding sweeps | int→int, int→cbu (+pred), fp16→{int,fmal}, fmal→mio, mio→{fp16,int,fmal}, fp16→mio, fp16→cbu, cbu→int/mio, udp→fe, pred_forward, subcore_yield |

Consequences for notes: the measured forwarding boundaries in
`pipe_forwarding.md`/`pipe_forward_survey.md` (minG values for 23/27 edges),
`usched_latency.md` (transN boundary — via depbar/pmtrig/yield/subcore probes),
`control_codes.md` opex layout, `mufu.md` latency numbers, ffma/mufu throughput
figures all reproduced within tolerance on H20 silicon.

## 2. Expected sm120-only failures (notes already correct)

- `test_qmma`, `test_qmma_sf`, `test_omma`, `test_tmap_helper`: QMMA/OMMA/tensor-map
  helper paths are sm_120a instructions (sm90 uses QGMMA/WGMMA) — cannot assemble
  against sm90 db.  Notes (`hmma_fda_model.md`, `cutensormap.md`) keep "Blackwell" tags.
- `test_f2fp`: its E2M1/E5M2 MXFP4-style variants do **not exist in the sm_90 spec**
  (MatchError is correct).  Hopper-equivalent coverage lives in `test_f2fp_hopper.py`,
  which **passes** on H20.

## 3. Blocked reruns (tooling must catch up before the note claim counts as re-verified)

### 3a. Hard-coded sm_120 reference vectors in test sources (byte-exact checks)
`test_up2ur.py` / `test_voteu.py` / `test_atom.py` embed `(lo64,hi64)` tuples captured
from sm120 assembly and fail on the control-word bits (stall/opex region), while their
GPU-semantics halves behave correctly.  Fix: emit expected encodings from the active
arch's db, or store per-arch REF tables.
*Affected notes:* up2ur.md, voteu.md, atom.md (semantics unaffected so far).

### 3b. Matcher/dialect gaps against the sm_90 ISA db (MatchError)
These reveal real FORMAT-shape differences between the two spec dumps and need either
test-source rewrites or sm90-db coverage fixes before the wrapped notes can count as
resilvered:

| Test | Shape mismatch seen on sm90 db |
|---|---|
| test_imnmx | predicate-form IMNMX slots differ (PRED,PRED,...) |
| test_ldcu | `LDCU .128` modifier form (sm90 uses ULDC dialect, port-note aliasing incomplete) |
| test_umov | `UMOV.64` variant absent/different |
| test_usel | `USEL.64` variant absent/different |
| test_uimad | `UIMAD.HI` |
| test_uisetp | `UISETP …AND…U64` combined form |
| test_viadd | `VIADD.U32` modifier name/position |
| test_r2ur | `R2UR …FILL` variant |
| test_mbarrier | UIADD3 parsed with UPRED operand types (slot-typing differs from sm120) |
| test_ublkcp(+multicast), test_utmacctl, test_utmaldg, test_utmaredg, test_utmastg | ELECT rejected: OOR_REG_ERROR "Uniform register URd out of range" under sm90 db conditions |
| test_uclea | ILLEGAL_INSTR_ENCODING_ERROR "#constSizeU04 cannot be greater than 8" — sm90 spec conditions stricter than sm120 |

*Relying notes:* r2ur.md, s2ur.md, uimad.md, uisetp.md, viadd.md, ublkcp.md,
utmacctl.md, utmaldg.md, utmaredg.md, utmastg.md, uclea.md, mbarrier.md/tma_mbarrier.md.

### 3c. CUDA_ERROR_ILLEGAL_ADDRESS (700) at first kernel — the known ULDC-synchronous trap
`test_ldg`, `test_ldg_stg`, `test_ldgsts`, `test_hmma`, `test_hmma_precision`,
`test_hmma_model` (after model self-test) all die when the hand-built kernel loads the
default cache descriptor via `LDCU/ULDC {URx,URx+1}` and consumes it behind a `req`
wait — legal on sm120 (LDCU is DECOUPLED_WR_SCBD), illegal on sm90 where **ULDC is
COUPLED_MATH with dst_wr_sb=\*7** (see `assembler_sm90_port.md`).  Sources need the
sm90 pattern (stall≥1 or yield=1, desc load adjacent to consumer).
*Relying notes:* ldg.md, stg.md, ldgsts.md, hmma.md, hmma_fda_model.md,
cache_descriptor.md — until rerun, their silicon sections remain SM120-only.

## 4. Genuine H20(sm90) vs RTX 5090(sm120) deltas found during this audit

1. **S2UR of SR_CTAID.X last-writer rule** (`test_s2ur`): grid=3 case reads **1** on
   H20 vs **2** recorded on sm120 ("last writer wins" among CTAs differs, or CTA
   launch order/uniform-datapath propagation differs).  → investigate & amend
   `s2ur.md`; r2ur rerun blocked by 3b.
2. **>8-byte kernel params read zeros** (`test_bigparam`: big[4..7]==0): scalar
   params at c[0x0][0x210] work (param base verified), but the 128-byte param window
   behaves differently than the sm120 0x380 layout — likely placement/alignment or
   driver copies only a prefix.  Needs a dedicated probe before trusting any
   "large struct by value" statement written from sm120 findings (§6 of
   `notes/sm120/encoding-addressing.md`).
3. **Yield forward-progress** (`test_yield` FAILED; `test_subcore_yield` PASSED):
   spin-lock-with-yield boundaries differ between H20 scheduler state and the sm120
   numbers; per-SKU/clock sensitivity documented in `yield.md` should gain an H20 row.
4. **depcheck CFG edges**: "LDG w/o desc req" and "DEPBAR.LE UR threshold" edges are
   architecture-conditional (on sm90 ULDC writes no scoreboard ⇒ desc-dependency edge
   disappears).  Depcheck should key off `INST_TYPE_COUPLED_MATH/dst_wr_sb=*7` when
   arch=sm90 rather than unconditional LDCU-writes-SB assumptions.
5. `test_cache_desc` flaky on both GPUs (pre-existing, per-stream attribute state).

## 5. Action checklist (priority order)

1. [ ] Rewrite LDCU-consuming kernels in ldg/ldg_stg/ldgsts/hmma*/hmma_model to the
     ULDC-stall/NOP pattern; rerun on H20 → upgrades ldg/stg/ldgsts/hmma/
     hmma_fda_model/cache_descriptor silicon sections.
2. [ ] Probe SR_CTAID.X write-race rules on H20 (n-grid × repeated capture); amend
     s2ur.md (SM120 section) with the sm90 result; unlock r2ur companion (needs 3b fix).
3. [ ] Big-param ABI probe on sm90 (where do bytes ≥8 land; KPARAM alignment rules);
     reconcile against `notes/sm120/encoding-addressing.md` §6 and `cubin_elf.md`.
4. [ ] Fix 3a stale REF vectors (up2ur/voteu/atom) to per-arch generation.
5. [ ] Add sm90-dialect sources/db coverage for 3b mnemonics; first targets: ELECT +
     UTMA family (needed for TMA-on-Hopper respin of utmaldg/utmastg/utmaredg/utmacctl
     and mcast question — `ublkcp.md`'s "multicast doesn't work" was observed ONLY on
     RTX 5090; Hopper H100 supports multicast cluster mode, so expect different outcome).
6. [ ] Arch-aware depcheck modelling (ULDC dst_wr_sb=*7 ⇒ no desc edge on sm90).
7. [ ] After each rerun, move the "Verified encodings/semantics" table header from
     "(SM120)" to "(sm90: H20 + sm120: RTX 5090)" in the affected note, keeping the
     original observation history.
