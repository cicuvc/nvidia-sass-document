# `CBU_STATE` — BMOV-addressable warp / convergence-barrier-unit state

**Question:** what is `CBU_STATE`?
**Status:** resolved (spec-grounded; BMOV is too rare to appear in stock libs).

## What it is
`CBU_STATE` is the **operand selector for `BMOV`** — it names *which* piece of
per-warp Convergence-Barrier-Unit / thread state the BMOV reads or writes.
`BMOV` is the compiler's back door for saving/restoring CBU state (barrier spill,
trap/at-exit handlers, state introspection). It lives on the `cbu_pipe`.

- Encoded as a **6-bit field at bits [29:24]** (occupies the `Sa` source slot).
- Two enums:
  - `CBU_STATE` — full 33-value set (0..32).
  - `CBU_STATE_NONBAR` — same set **minus B0..B15** (values 16..32 only); used by
    forms that address the barrier register separately via the `BD` field
    (`barReg`), so a barrier isn't a legal `cbu_state` there.

## The state slots (value -> name)
| val | name | meaning |
|----:|------|---------|
| 0..15 | **B0..B15** | the 16 convergence-barrier registers (participating-lane mask + reconv PC) |
| 16..20 | **THREAD_STATE_ENUM.0..4** | 5 per-lane reconvergence/thread-state slots |
| 21 | TRAP_RETURN_PC.LO | trap-handler return PC (low 32b) |
| 22 | TRAP_RETURN_PC.HI | trap-handler return PC (high) |
| 23 | TRAP_RETURN_MASK | trap-handler return active mask |
| 24 | **MEXITED** | lanes that executed EXIT |
| 25 | **MKILL** | lanes killed by KILL |
| 26 | **MACTIVE** | lanes currently executing (active/exec mask) |
| 27 | **MATEXIT** | lanes pending the at-exit handler |
| 28 | OPT_STACK | (opt) stack bookkeeping |
| 29 | API_CALL_DEPTH | call-depth counter |
| 30 | ATEXIT_PC.LO | at-exit handler PC (low) |
| 31 | ATEXIT_PC.HI | at-exit handler PC (high) |
| 32 | MCOLLECTIVE | collective/CGA participation mask |

The four 32-bit lane masks MACTIVE / MEXITED / MKILL / MATEXIT match the external
lane-state model exactly.

## BMOV directions & modifiers (from the FORMATs)
14 BMOV encoding variants, three functional groups:

1. **Read state -> GPR** — `bmov_clear__Rd`: `BMOV[.CLEAR] Rd, cbu_state`.
   `/CLEAR` reads *and clears* the slot; a condition restricts `.CLEAR` to the
   **barrier** states B0..B15 ("onlyBR"). So `BMOV.CLEAR Rd, B0` = read+disarm B0.

2. **Write GPR/const/imm/UR/bar -> state** — `bmov_pquad__R{R,C,CX,I,UR}R`,
   `bmov_pquad_bar__RBR`: `BMOV[.PQUAD] cbu_state, <src>`.
   `/PQUAD` requires `cbu_state == MACTIVE` (condition "pquad" -> MACTIVE) — a
   per-quad write of the active mask.
   `bmov_clear_bd__Bd` / `bmov_clear_barrier_` write into a barrier register
   (`BD:barReg`) using the `CBU_STATE_NONBAR` selector or a `Ba` barrier.

3. **64-bit ATEXIT_PC set** — `bmov_dst64__{R,C,CX,I,UR}`:
   `BMOV.64 ATEXIT_PC, <src>` (`ONLY64_syncs`, operand `ATEXIT_PCONLY:atexit_pc`)
   — installs the 64-bit at-exit handler PC from reg/const/imm/UR.

## Notes / deltas vs. the external reference
- Reference says "eight THREAD_STATE slots"; the sm_90 enum exposes **five**
  (`THREAD_STATE_ENUM.0..4`).
- sm_90 adds **MCOLLECTIVE** (CGA/collective era) beyond the classic
  MACTIVE/MEXITED/MKILL/MATEXIT set, plus TRAP_RETURN_*, ATEXIT_PC,
  OPT_STACK, API_CALL_DEPTH.
- Barrier register file B0..B15 is exposed here as the low 16 CBU_STATE values —
  consistent with the 4-bit `BD` barrier selector used by BSSY/BSYNC/BREAK; BMOV
  can name all 16 as state, while the `CBU_STATE_NONBAR` forms carry the barrier
  in the separate `BD` field instead.
- Empirical: **0** BMOV instructions in 5.6M lines of cublas sm_90 SASS — these
  state moves only appear in irregular-divergence / barrier-spill / trap code,
  so nvdisasm's exact rendering of the state names is not sampled here.

## Resolved: B-register content empirically (SM120, 2026-08)

`tests/asm_construct/test_breg.py` reads B0/B1 via `BMOV Rd, B0` (single read;
two back-to-back BMOVs race in a hand-built cubin — the second clobbers the
first's GPR result, so each probe reads one slot):

- After an **unpredicated full-warp `BSSY B0, target`**, `BMOV R4, B0` returns
  **0xFFFFFFFF** for every lane — the participating-lane mask (all 32 active).
- A **predicated `@P0 BSSY`** (only tid<16 push) returns the subset mask
  **0xFFFF** to the pushed lanes.
- Before any BSSY, B0 = 0x0; after the matching **BSYNC** (entry popped), B0 = 0x0.
- An unused B1 = 0x0.

**Conclusion:** the readable 32-bit B-register content is the **active /
participating thread mask** of the BSSY-established divergence point — not an
address. The reconvergence target is carried by the BSSY instruction's own
PC-relative `Sa` field; the return PC is implied by the hardware sync stack and
is not exposed by the 32-bit `BMOV` read.

## Resolved: CBU_STATE slots empirically (SM120, 2026-08)

`tests/asm_construct/test_cbu_state.py` reads every CBU_STATE slot via `BMOV`
(one slot per kernel; back-to-back BMOVs race in hand-built cubin). A warp-
state slot materializes on the *executing* lanes; other lanes read 0, so each
capture shows `[0, value]`.

| slot | baseline | after @P0 EXIT (tid<16) | inside divergence (tid>=16 skipped) |
|------|----------|--------------------------|---------------------------------------|
| MACTIVE | 0xFFFFFFFF | 0xFFFF0000 (survivors) | 0xFFFF (body lanes) |
| MEXITED | 0x0 | 0xFFFF (exited lanes) | 0x0 |
| MKILL / MCOLLECTIVE | 0x0 | 0x0 | 0x0 |
| MATEXIT | 0xFFFFFFFF | 0xFFFFFFFF | 0xFFFFFFFF |
| THREAD_STATE_ENUM.0 | 0xFFFFFFFF | 0xFFFF0000 | 0xFFFFFFFF |
| THREAD_STATE_ENUM.1..4 | 0x0 | 0x0 | 0x0 |
| TRAP_RETURN_PC.LO | 0x0 | 0x0 | **current PC** |
| TRAP_RETURN_PC.HI | 0x0 | 0x0 | 0x0 |
| TRAP_RETURN_MASK | 0x0 | 0x0 | 0xFFFF0000 (parked lanes) |
| OPT_STACK / API_CALL_DEPTH / ATEXIT_PC.LO/HI | 0x0 | 0x0 | 0x0 |

Interpretation:
- **MACTIVE = current execution mask** (which lanes are active NOW); MEXITED =
  exited-lane mask. Complements after partial EXIT.
- **TRAP_RETURN_PC.LO = the live current PC** (kernel base + offset of the
  reading instruction) — verified identical kernel-base 0x071675B0 across four
  layouts with NOPs inserted before/after the BSSY region.
- **TRAP_RETURN_MASK records the parked (branch-taken) lanes during divergence**
  — the BSSY/BSYNC reconvergence machinery reuses the trap-return state.
- **ATEXIT_PC is NOT set by BSSY** (0x0 baseline and after BSSY) — it is the
  separate at-exit-handler PC, written only via `BMOV.64 ATEXIT_PC, <src>`.
- The BSSY reconvergence *target* is carried by the BSSY instruction's own Sa
  field (PC-relative); the *return* PC bookkeeping surfaces here as
  TRAP_RETURN_PC/TRAP_RETURN_MASK during the divergent region.

## Resolved: MCOLLECTIVE = collective-region participation mask (SM120, 2026-08)

`MCOLLECTIVE` (CBU_STATE 32) is live **only inside a `WARPSYNC.COLLECTIVE
Rmask, TGT` … `ENDCOLLECTIVE` region**: it reads `Rmask & active-lanes` while
the region is open and 0x0 after `ENDCOLLECTIVE`. `WARPSYNC.COLLECTIVE`
requires `Rmask ⊇` the lanes executing it (else ILLEGAL_INSTRUCTION 715). See
`warpsync.md` / `endcollective.md` and `test_warpsync_collective.py`.
