# SETMAXREG (USETMAXREG) — Dynamic warp register allocation

**Mnemonic:** `USETMAXREG` | **opcodes:** 0x19c8 (immediate), 0x13c8
(uniform-register target) | **pipe:** `udp_pipe` | **type:**
`INST_TYPE_DECOUPLED_RD_WR_SCBD` | **queue:** `VQ_UNORDERED` | compute-only

`USETMAXREG` is the hardware primitive behind PTX
`setmaxnreg.{inc,dec}.sync.aligned.u32`.  It changes the absolute maximum
number of registers owned by a warp and moves the difference to/from a
per-CTA register pool.  This is the register-file mechanism used by Hopper+
warp-specialized kernels: producer warpgroups shrink and donate registers;
consumer/MMA warpgroups grow using the donated pool.

## PTX contract and lowering

PTX requires an immediate target `N` in `[24,256]`, inclusive and a multiple
of 8.  All threads of every warp and all warps in the warpgroup must execute
the same instruction.  After one `setmaxnreg`, the warpgroup must explicitly
synchronize before a later `setmaxnreg`.  Divergent participation is undefined.
The kernel must have a known entry register count (for example
`-maxrregcount=N`); otherwise CUDA 13.1 ptxas reports C7508 and removes the
operation.

| PTX | SASS | blocking behavior |
|---|---|---|
| `setmaxnreg.dec.sync.aligned.u32 N` | `USETMAXREG.DEALLOC.CTAPOOL N` | one queued deallocation; completion is scoreboarded |
| `setmaxnreg.inc.sync.aligned.u32 N` | `USETMAXREG.TRY_ALLOC.CTAPOOL UPu,N` | ptxas retries until `UPu=1` |

The actual CUDA 13.1 increment loop is:

```text
retry:
    NOP                                      // backoff, stall 8
    USETMAXREG.TRY_ALLOC.CTAPOOL UP0, N      // claims write SB
    BRA.U !UP0, retry                        // req-waits the SB
```

`BRA.U` consumes the uniform predicate directly; the older note's
`PLOP3 UP0→P0` step was not present in captured sm_90a or sm_120a code.
Thus PTX `.inc` is blocking only because of a software retry loop.  The SASS
`TRY_ALLOC` itself is a single non-blocking attempt.

PTX 9.3 lists support on sm_90a, sm_100a, sm_110a and sm_120a, plus the
corresponding family-specific targets.  Plain sm_90/sm_120 PTX targets reject
the instruction; the underlying SASS encoding is present in the architecture
database and was executed here in a correctly marked sm_120 cubin.

## Device-verified SASS semantics (RTX 5090, sm_120, CUDA 13.1)

Let `C` be the warp's current absolute allocation target.

### `.DEALLOC.CTAPOOL N`

- Requires `8 <= N <= C` at native SASS level.  A wrong-direction target
  (`N>C`) or `N<8` traps with CUDA 715.
- On completion sets the warp's target to `N` and donates `C-N` registers per
  thread to the CTA pool.  A full four-warp producer group going 128→64 made
  exactly enough pool for a four-warp consumer group to go 128→192; 128→200
  failed.
- It has no predicate destination (`Pu=UPT`) but is still a decoupled queued
  operation.  ptxas assigns a write scoreboard and makes the following
  instruction wait on it.
- `N=C` is a legal no-op and releases nothing.

### `.TRY_ALLOC.CTAPOOL UPu,N`

- Requires `C <= N <= 256`.  `N<C` or `N>256` traps with CUDA 715.
- If the CTA pool contains at least `N-C` registers per thread for every
  participating warp, the allocation is committed and `UPu=1`.
- If the pool is insufficient, it returns `UPu=0` without trapping.  The
  allocation is all-or-none: no partial tail is exposed and the failed attempt
  does not implement PTX's blocking behavior by itself.
- `N=C` is a successful no-op (`UPu=1`) even with an empty pool.
- A 384-thread CTA test used one producer warpgroup to donate exactly enough
  for one of two requesting warpgroups.  One entire requester returned 1 and
  the other entire requester returned 0 (`128/128/128` lanes); no warp/lane
  subset received a partial allocation.  Arbitration selected the later
  warpgroup consistently in this experiment, but ordering/fairness is not an
  architectural guarantee.

The `.CTAPOOL` name is literal: donations are visible to other warpgroups of
the same CTA.  A deliberately incomplete one-warp donation inside a full
warpgroup did not enable its sibling request.  That experiment reinforces the
four-warp granularity but is outside the PTX contract, so no stronger behavior
is claimed for undefined participation.

### Native count granularity versus PTX

The SASS immediate is a direct 10-bit absolute count, not `N/8`.  Hardware
accepted non-multiples such as 129, 231 and 232 and accounted them exactly:
after a producer group donated 104 registers/thread (128→24), a peer 128→232
succeeded while 128→233 returned false.  Native SASS therefore has one-register
granularity and an observed valid absolute range `[8,256]`.  PTX deliberately
narrows this to `[24,256]` and multiples of 8.

### Register-window boundary and contents

Allocation changes happen at the tail.  For an allocation target `N`, usable
architectural GPRs are:

```text
R0 ... R(N-3)       usable
R(N-2), R(N-1)      reserved/unavailable
R(N) ...            outside the owned window
```

This is the architecture's existing two-register headroom rule, now verified
across reconfiguration:

- after `DEALLOC 64`, R61 works and R62 faults;
- after a successful `TRY_ALLOC 192`, R189 works and R190 faults;
- the same `N-2` boundary was seen at non-multiple targets 24 and 65.

Newly obtained registers have undefined contents and must be initialized.
On this RTX 5090, R100 was written with `0xdeadbeef`, released by 128→64, then
reacquired by 64→128; it read back as zero in repeated runs.  Zeroing is an
implementation observation, not a contractual guarantee.

### Operand and predication forms

The immediate and uniform-register variants have identical behavior.  The UR
form was hand-assembled and device-verified (`UR8=64` produced the same
successful no-op as immediate 64); ptxas cannot select it because PTX requires
an integer constant.

The instruction is guarded by a uniform predicate `@UPg`, so a SASS issue is
uniform within each warp.  PTX's stronger `.aligned` rule additionally
requires all four warps in the warpgroup to participate identically.

## Variant taxonomy and encoding

The dump contains four primary classes and four alternate `usetmaxregAlloc*`
classes:

| shape | opcode | mode | source | destination |
|---|---:|---:|---|---|
| immediate alloc | 0x19c8 | 2 | `Sb[41:32]`, UImm10 | `UPu[83:81]` |
| immediate dealloc | 0x19c8 | 1 | `Sb[41:32]`, UImm10 | UPT |
| UR alloc | 0x13c8 | 2 | `URb[37:32]` | `UPu[83:81]` |
| UR dealloc | 0x13c8 | 1 | `URb[37:32]` | UPT |

The alternate `.ALLOC` grammar and primary `.TRY_ALLOC` grammar both encode
`mode=2` with the same destination predicate.  They are bit-identical, so
there is no independently encodable blocking `.ALLOC` operation: cuobjdump
renders the bits as `.TRY_ALLOC`, and blocking is supplied by the retry loop.

Common fields:

| bits | field | meaning |
|---|---|---|
| [91]∥[11:0] | opcode | 0x19c8 immediate / 0x13c8 UR |
| [15],[14:12] | `UPg_not`,`UPg` | uniform guard |
| [73:72] | `mode` | 1=DEALLOC, 2=TRY_ALLOC/ALLOC; 0/3 have no class |
| [74] | `pool` | 1=CTAPOOL (only exposed pool) |
| [83:81] | `UPu` | success predicate for alloc; 7 for dealloc |
| [121:116] | `req_bit_set` | scoreboard wait mask |
| [115:113],[112:110] | `rd`,`wr` | source-release / destination scoreboard |
| [124:122]∥[109:105] | `opex` | scheduling controls |

## Scheduling and latency

`USETMAXREG` is on `udp_pipe`, but resource reconfiguration is decoupled via
`VQ_UNORDERED`.  Both modes must be ordered with a write scoreboard:

- `TRY_ALLOC` writes `UPu`; ptxas's following `BRA.U` req-waits its SB.
- `DEALLOC` has no data destination, but ptxas still claims an SB and the first
  following instruction waits before using the new register window/pool state.

The latency table's UPRED connector is 1 cycle; this describes predicate
forwarding after the queued operation produces its result, not a guarantee
that a contended allocation completes in one wall-clock cycle.

## Cubin metadata and assembler support

ptxas records the entry allocation and reconfiguration capability with:

- device-wide `EIATTR_REGCOUNT` = entry allocation;
- per-kernel `EIATTR_MAXREG_COUNT` = the same known entry count;
- empty `EIATTR_REG_RECONFIG` marker in ptxas output.

Patching out `REG_RECONFIG` did not change execution on the tested sm_120, so
it is descriptive metadata rather than proven hardware enablement.  The
assembler nevertheless emits it for ptxas fidelity and now treats an explicit
`#pragma MAXREG_COUNT(N)` as authoritative instead of inflating it from raw
instruction-bit heuristics.

## Validation

- `tools/decode_setmaxreg.py`: immediate + UR forms, guards and both modes.
- `tests/setmaxreg_{inc,dec}.cu`: ptxas mapping captures for sm_90a/sm_120a.
- `tests/asm_construct/test_usetmaxreg.py`: real-device pool accounting,
  success/failure, contention, UR form, raw bounds and tail-window probes.

## Open questions

- CTA-pool arbitration/fairness between simultaneous requesting warpgroups.
- Exact behavior of predicated-off destinations and malformed mode/pool bits.
- Behavior for incomplete warpgroup participation is intentionally left
  undefined, matching PTX.
