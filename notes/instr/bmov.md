# BMOV — Barrier / CBU-state move

**Opcode mnemonic:** `BMOV` = base **0x355/0x356/0x357** (+ operand-form high bits) | **Pipe:** `cbu_pipe` (BRU_OPS) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD[_WR]_SCBD`, `VIRTUAL_QUEUE=$VQ_UNORDERED` | since sm_70

The compiler's back door for reading/writing per-warp **Convergence-Barrier-Unit (CBU) state**:
the 16 convergence-barrier registers `B0–B15`, the lane masks (MACTIVE/MEXITED/MKILL/MATEXIT),
trap/at-exit PCs, etc. Used only for barrier spill/restore and trap/at-exit handlers — **not
emitted by nvcc** (0 in cublas). See `../arch/cbu_state.md` for the full `CBU_STATE` selector map.

> **Status: encoding spec-derived, round-trip only (no real captures).** BMOV appears only in
> irregular-divergence / trap code, so nvdisasm's exact rendering is unsampled.

TODO consolidation: **BMOV_R** (idx 55) = the register/state forms; **BMOV_B** (idx 54) = the
barrier-register (`BD`) forms; **BMOV** (idx 56) — all one instruction, documented here.

## Direction / functional groups (14 CLASS variants)
| group | opcode(s) | form | meaning |
|-------|-----------|------|---------|
| read state → GPR | 0x355 | `BMOV[.CLEAR] Rd, cbu_state` | read CBU slot; `.CLEAR` = read+disarm (barrier slots) |
| write state ← src | 0x356/0x956/0xb56/0x1b56/0x1d56 | `BMOV[.PQUAD] cbu_state, {Rb\|imm32\|C\|CX\|UR}` | write a CBU slot |
| write state ← barrier | 0xf56 | `BMOV[.PQUAD] cbu_state, Bd` | write slot from a barrier register |
| barrier dest | 0xf55 | `BMOV Bd, cbu_state_nonbar` / `BMOV.CLEAR Bd, Ba` | write/clear a barrier register |
| 64-bit at-exit PC | 0x357/0x957/0xb57/0x1b57/0x1d57 | `BMOV.64 ATEXIT_PC, {Rb\|imm\|C\|CX\|UR}` | install the 64-bit at-exit handler PC |

Source-operand high opcode bits (shared with other ops): `0x3..`=R, `0x9..`=I, `0xb..`=C,
`0x1b..`=CX, `0x1d..`=UR, `0xf..`=barrier(BD).

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | selects direction (…55/56/57) + operand form |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [29:24] | `Sa` = `cbu_state` | 6-bit CBU_STATE selector (or `Ba` barrier in clear_barrier) |
| [23:16] | `Rd` | dest GPR (read form) |
| [39:32] | `Rb` | source GPR (write/dst64 reg forms) |
| [63:32] | `Sb` | 32-bit immediate (pquad RIR) |
| [80:34]∥[23:16] | `Sb` (SCALE 4) | 55-bit at-exit PC immediate (dst64 I) |
| [19:16] | `barReg` (`BD`) | 4-bit barrier register B0–B15 |
| [84] | `OR` | = `clear` (read) / `pquad` (write); `.CLEAR`/`.PQUAD` |
| [112:110] | `dst_wr_sb` | pinned 0x7 |

Modifiers: `sz` `ONLY32`(.32)/`ONLY64_syncs`(.64) — both encode 0, so 32 vs 64 is
opcode-distinguished (…56 vs …57). `CLEAR`: noclear=0/CLEAR=1. `PQUAD`: nopquad=0/PQUAD=1
(requires `cbu_state==MACTIVE` — a per-quad active-mask write). `CBU_STATE` (full 0–32) vs
`CBU_STATE_NONBAR` (16–32; barrier carried in the separate `BD` field).

## Cross-comparison (barrier/convergence family)
| op | scope | what |
|----|-------|------|
| **BMOV** | convergence-barrier regs B0–B15 + CBU lane-state | save/restore CBU state |
| **BSSY/BSYNC/BREAK** | B0–B15 | set up / wait / break convergence barriers |
| **B2R/R2B** | named `bar.sync` barriers (0–15) + warp state | barrier-result / arrive-state moves |

BMOV and BSSY/BSYNC share the `cbu_pipe` and the 16 barrier registers; BMOV is the state
mover, BSSY/BSYNC are the control-flow reconvergence ops.

## Latency (from sm_90_latencies.txt)
`cbu_pipe` (= `BRU_OPS`). Decoupled/`VQ_UNORDERED`; read form writes a GPR (consumers wait on
write scoreboard), write forms have no GPR result.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64 | Reconstruction |
|------|------|----------------|
| `0x0000000000047355` | `0x0000000000000000` | `BMOV R4, B0` |
| `0x0000000000047355` | `0x0000000000100000` | `BMOV.CLEAR R4, B0` |
| `0x000000061a007356` | `0x0000000000100000` | `BMOV.PQUAD MACTIVE, R6` |
| `0x0000000800007357` | `0x0000000000000000` | `BMOV.64 ATEXIT_PC, R8` |
| `0x000000001a037f56` | `0x0000000000100000` | `BMOV.PQUAD MACTIVE, B3` |
| `0x0000000002057f55` | `0x0000000000100000` | `BMOV.CLEAR B5, B2` |

Decoder + round-trip test: `tools/decode_bmov.py`.

## Open questions
- **No real vectors** — exact nvdisasm text (size suffix `.32`, state-name spelling, at-exit
  imm rendering) is unverified. See `cbu_state.md` for the state-selector reconciliation.
