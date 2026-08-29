# RPCMOV — Move to/from the RPC (return-PC) register

**Opcode mnemonics (10 CLASSes):** read 32-bit `RPCMOV.32 Rd, Rpc.LO/HI` = **0x353** (`rpcmov_srcPc_`); write 32-bit `RPCMOV.32 Rpc.LO/HI, Rb` = **0x352** (`rpcmov_dstPc_`); write 64-bit = **0x1b54 / 0x0b54 / 0x0954 / 0x1d54** (`rpcmov_dstPc64__{CXb,Const,Imm,URb}`) | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

Moves between GPRs and the otherwise-inaccessible **RPC register** — the
hardware return-PC slot associated with `CALL`/`RET`.  32-bit forms name
the halves as `Rpc.LO` / `Rpc.HI` (`PC_REG` operand); 64-bit forms name
`Rpc` (`RPCONLY`) and are write-only (no `srcPc64` read variant exists).

## Semantics
- `RPCMOV.32 Rd, Rpc.LO|Rpc.HI` — read one half of RPC into `Rd` (what a
  callee uses to learn where it was called from).
- `RPCMOV.32 Rpc.LO|Rpc.HI, Rb` / `RPCMOV.64 Rpc, ...` — write RPC
  (pre-seed a return address; the 64-bit forms take a register pair /
  const / 57-bit immediate scaled by 4, like `CALL.ABS`).

## Empirical (sm_120, `sassdbg/probe_callheap2.py` / `probe_callheap3.py`)

- **`CALL.ABS` with a GPR target writes RPC = VA of the CALL instruction
  itself**; the return address is `RPC + 0x10`.  A callee returns with
  `RET.ABS.NODEC {RpcPair}, 0x10` (skip the CALL) or `, 0x0`
  (re-execute the site — the breakpoint-handler pattern).
- **ABS uniform-register and immediate target forms execute the call but
  do NOT populate RPC**; `RPCMOV` in their callee reads changing launch
  residue on sm_120 and stable zero on H20/sm_90.  This is independent
  of INC/NOINC.  A handler for these forms must receive its return VA
  separately.
- **`CALL.REL` also does NOT write RPC** — `RPCMOV` after a REL call reads
  an indeterminate value (observed both `0` and launch residue across
  runs).  ptxas's `CALL.REL.NOINC` ABI never touches RPC, consistent with
  this.
- RPC is a **single register, not a stack**: nesting overwrites it
  (a callee that CALLs again must spill RPC first), and `RET_DEPTH.DEC`
  does not restore any outer value.
- With **no active CALL** at all, `RPCMOV.32` reads `0` (or residue) —
  no trap.
- A **divergent** (half-warp) `CALL.ABS` gives each executing group its
  own RPC view (the same site VA); both groups return correctly.
- RPCMOV results feed later instructions like any `int_pipe` result;
  claiming the same write scoreboard as an outstanding LDCU lets a
  single `{req}` wait cover both (see `sassdbg/patch.py` handler).

### `RPC_WRITERS` latency set vs. visible RPC writes (sm_120)

`sm_90_latencies.txt` places many CBU operations in `RPC_WRITERS`, but
this is a **resource-hazard classification**, not a promise that every
member overwrites the value readable through `RPCMOV`.  In
`sassdbg/probe_rpc_writers.py`, Rpc.LO was first seeded to `0x12345000`,
then one candidate operation was executed, followed by 16 NOPs and one
Rpc.LO read:

| observed visible effect | operations |
|---|---|
| RPC = instruction PC | `WARPSYNC.ALL`, `BSYNC`, `BRX R`, `JMX R`, `RET R`, `CALL.ABS R` |
| RPC = next instruction PC | `BREAK`, `YIELD`, `NANOSLEEP 0` |
| RPC remains the sentinel | `BRA`, `JMP imm`, `BRXU`, `JMXU`, `RET UR`, `CALL.ABS UR`, `CALL.ABS imm` |

NOP also preserves the sentinel as the negative control.  Thus latency
analysis must honor the whole `RPC_WRITERS` set and its 9-cycle resource
dependency, while semantic analysis must remain variant-specific.  The
current-PC/next-PC values plausibly serve replay, reconvergence, and
resume bookkeeping, but that role is an inference rather than a
spec-stated guarantee.

## Use in sassdbg

The slot-less breakpoint handler (`sassdbg/patch.py`) is reached by
patching the site word with `CALL.ABS.NOINC PT, {R252,R253}, 0x0`;
the handler's first two instructions are `RPCMOV.32 R248, Rpc.LO` /
`RPCMOV.32 R249, Rpc.HI`, which yield the **site VA** — the breakpoint's
identity, with zero per-site plumbing.

## Open questions
- What writes RPC besides `CALL.ABS` (driver/API calls? `RPCMOV` dst
  forms are obviously one — what uses them)?
- Is the unread-64 variant a real hardware limitation or just an
  encoding-space choice?
