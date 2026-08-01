# NANOTRAP — Hardware Trap Injection

**Opcode mnemonic:** `NANOTRAP` (R=0x35a, I=0x95a, C=0xb5a, CX=0x1b5a, U=0x1d5a)
**Pipe:** `cbu_pipe`  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`  **VIRTUAL_QUEUE:** `$VQ_UNORDERED`

## Semantics

Injects a hardware trap.  Operand = trap address/selector (register, uniform
register, immediate, or constant bank), plus an optional predicate `Pp`
([89:87], with `@not` at [90]) and a `/RAND` modifier (`depth` [86]) for
randomized injection.  `IDEST_SIZE=0`, `ISRC_B_SIZE=32`.  Not emitted by
ptxas — it is a driver/runtime/ABI primitive.

## Verified behavior (SM120, single-warp probe, 2026-08)

`tests/asm_construct/test_nanotrap.py` (CS2R SR_CLOCKLO timing around trap
loops):

1. **No user-visible side effect in a CUDA launch.**  Execution always
   continues; the register operand is unchanged and a following store
   succeeds.  The injected trap is swallowed by the runtime (no fault).

2. **Cheap in isolation.**  A single `NANOTRAP` costs ~20 cycles (vs ~13
   for 2 NOPs).

3. **Repeated traps can trigger a ~10k-cycle device event.**  The
   probability and cost depend on the trap address:

   | addr | trigger rate | event cost |
   |------|-------------|-----------|
   | 0x00 | 100% | ~54k cyc (many) / ~11k (one) |
   | 0x7f | 100% | ~10.7k |
   | 0x80 | ~52–68% | ~10.8k |
   | 0x81 | ~44–56% | ~10.7k |
   | 0x100+ | ~24% (probabilistic) | ~10.7k |

4. **Trap suppression vs stacking.**  `0x7f`/`0x80`/`0x81` events do NOT
   stack: 1 trap == 64 traps ≈ 10.7k cyc (the first fires, subsequent ones
   are suppressed).  `0x00` DOES stack: each additional trap adds
   ~700–1800 cyc (16k cyc for 8 traps) — trap vector 0 is handled per
   injection.

5. **`.RAND`** does not change the observed cost in this probe.

## Interpretation

NANOTRAP's trap-vector address controls both *whether* the injection fires
(probabilistically) and *how it is handled* (suppressed vs per-trap).  In a
plain compute launch the trap handler runs on-device (~10k cycles) but the
runtime masks the user-visible fault, so the only observable effect is the
time cost.  Trap vector 0 is the "immediate/trap-every-time" selector with
per-injection handling.  This matches a hardware-exception-injection design
where the driver uses NANOTRAP for fault injection / testing / debug without
disturbing the compute context.

## Cross-references

- `cbu_state.md` — the CBU / convergence-barrier unit that NANOTRAP shares
  the `cbu_pipe` with (BRU/CBU ops, `CBU_OPS_WITH_REQ` set in the latency
  file).
- `fp64_control.md` — earlier note listing NANOTRAP among cbu_pipe ops.
