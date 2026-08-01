# BPT — Breakpoint / Trap

**Opcode mnemonic:** `BPT` (0x95c)  **Pipe:** `cbu_pipe`
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`  **VIRTUAL_QUEUE:** `$VQ_CBU`

## Semantics

`BPT.TRAP <Sb>` / `BPT.INT <Sb>` — breakpoint / trap / interrupt injection.
Selector `bpt` at [85]|[76]|[71] (`BPT_TRAP_INT`: TRAP=3, INT=4), trap
selector `Sb` (UImm 3-bit at [23:16]).  Two scheduling variants
(`noDRAIN` / `onlyDRAIN`).  No destination; a predicate guard only.

## PTX→SASS mapping (verified sm_90 + sm_120)

**PTX `trap;` / `__trap()` → `BPT.TRAP 0x1`** (lo=`0x000000040000795c`,
opcode 0x95c).  This is the real, user-visible trap — unlike NANOTRAP (which
the runtime swallows), BPT.TRAP causes the kernel launch to fail.

## Verified behavior (SM120, clean subprocess per case — a real trap poisons
## the CUDA context with 719 that persists in-process)

`tests/asm_construct/test_bpt_trap.py`:

| variant | Sb | result |
|---------|----|--------|
| `BPT.TRAP` | 1, 3, 7 | **CUDA_ERROR_LAUNCH_FAILED (719)** — trap fires |
| `BPT.TRAP` | 2, 4, 5, 6 | kernel runs (store OK) — no trap |
| `BPT.INT`  | 1..7 | kernel runs — interrupt masked in compute |
| `BPT.TRAP` | 0 | assembler rejects (CONDITION: TRAP illegal for Sb=0) |

ptxas deliberately emits `BPT.TRAP 0x1` — Sb=1 is a trap-firing selector
(odd values 1/3/7 fire, even values don't).  `BPT.INT` never faults in a
compute launch.

## BPT vs NANOTRAP

| | BPT.TRAP | NANOTRAP |
|--|----------|----------|
| Purpose | user-visible trap (PTX `trap`) | driver hardware fault injection |
| Pipe | cbu_pipe | cbu_pipe |
| On compute | **launch fails 719** | swallowed, ~10k-cycle cost |
| Emitted by ptxas | yes (`trap;`) | no (driver/runtime) |
