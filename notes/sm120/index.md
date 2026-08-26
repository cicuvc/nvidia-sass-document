# notes/sm120 — RTX Blackwell (sm_100/sm_120) encodings & silicon-verified behaviour

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
| `notes/sm120/l2_slice_probe.md` | Attempts to count L2 slices on GB202; single-L2-backend evidence |

## Blackwell-only instructions referenced from these notes

| Mnemonic | Where documented | sm_90 relationship |
|---|---|---|
| QMMA / QMMA.SF | `notes/sm90/arch/hmma_fda_model.md` §QMMA.SF, `tests/asm_construct/test_qmma*.py`, srcFmt enum (E4M3/E3M4/E2M3/E5M2/E3M2/E2M1) | none — Hopper uses QGMMA/WGMMA |
| OMMA / OMMA.SF (MXFP4 e2m1 m16n8k64) | same model note, `test_omma.py` | none |
| Tensor-map helper contract (`cuTensorMap*` → 128-byte descriptor) | `notes/sm90/arch/cutensormap.md`, `tests/asm_construct/test_tmap_helper.py` | TMA descriptors exist on sm90 via UTMALDG/UTMASTG, but the helper bit-patterns recorded were probed on sm_120 |
| F2FP extra destination formats `.E2M1` / MXFP4 PACK_AB_MERGE_C nibble packing | `notes/sm90/instr/f2fp.md` "runs on sm120 hardware" rows | absent from the sm_90 spec dump — do not list them as sm_90 variants |
| CCTL.LDCU.IV.DEEP + UTMACCTL.IV pairing | `notes/sm90/instr/cctl.md` (empirically RTX 5090) | cctl/utmacctl exist on sm_90; this specific IV.DEEP pairing observed only on Blackwell |

## Silicon-only-on-Blackwell claims awaiting a real sm_90 verdict

Consolidated per-instruction register: see **`silver-status.md`**.
Rationale and run matrix: `notes/sm90/arch/sm90_resilver_audit.md`.

Rules of thumb for what stays in `notes/sm90/…` vs moves here:

- Mechanism exists in both ISAs, evidence only from the 5090 → keep the note under
  `sm90/` (it documents an sm_90 ISA object), tag the section's evidence as
  "(silicon: SM120)", and record it in `silver-status.md` until re-tested.
- The instruction/format/ABI item does not exist at all on sm_90 → document it here.
