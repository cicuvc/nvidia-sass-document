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
