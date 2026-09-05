# ACQSHMINIT — Wait for shared-memory-initialization release state

**Opcode:** 0x877 | **architectures:** sm_100/sm_120 | **pipe:** `cbu_pipe` |
**type:** `INST_TYPE_COUPLED_MATH` | **virtual queue:** none | compute-only

NVIDIA's Binary Utilities reference describes `ACQSHMINIT` as **“Wait for
Shared Memory Initialization Release Status Warp State.”** It is the
control-flow-side acquire/wait primitive for Blackwell's shared-memory
initialization protocol. `UMEMSETS` is the initialization producer/data
operation (“Initialize Shared Memory”), but the two instructions are not a
one-for-one lowering of every PTX `st.bulk`.

## Form and encoding

```text
@Pg ACQSHMINIT
```

There are no explicit data operands, destinations or mode modifiers. sm_100
and sm_120 contain the same single class and encoding.

| bits | field | meaning |
|---|---|---|
| [91]∥[11:0] | opcode | 0x877 |
| [15],[14:12] | `Pg_not`,`Pg` | ordinary per-lane predicate guard |
| [121:116] | `req_bit_set` | syntactically present scheduling request mask |
| [115:113] | `src_rel_sb` | fixed 7 (none) |
| [112:110] | `dst_wr_sb` | fixed 7 (none) |
| [103:102] | `pm_pred` | performance-monitor predicate |
| [124:122]∥[109:105] | `opex` | `TABLES_opex_1` scheduling control |

Canonical encoding (`[7:7:{}:1:0]`):

```text
Lo64 0x0000000000007877
Hi64 0x000fe20000000000
```

The opcode is absent from sm_90. It is legal only in compute/trap shaders.

## Relationship with UMEMSETS and PTX `st.bulk`

The most useful distinction is between the protocol and the PTX lowering:

```text
shared-init producer/data path       UMEMSETS
shared-init release-state consumer   ACQSHMINIT
```

However, CUDA 13.1 ptxas did **not** emit `ACQSHMINIT` for any ordinary
`st.bulk` form tested. This includes `.weak.shared::cta`, the spelling without
`.weak`, an immediately following `LDS`, a following `BAR.SYNC`, and an
immediate `EXIT`; sm_100a and sm_120a produced the same result. All lowered to
`UMEMSETS.64` plus normal program instructions.

Consequently `ACQSHMINIT` is not equivalent to a source-level
`st.bulk.wait`. PTX exposes no such wait instruction. The evidence instead
points to an internal initialization protocol in which some agent establishes
an unreleased **warp state**, UMEMSETS performs the initialization, and
ACQSHMINIT prevents a participating warp from continuing until that state is
released. The documented PTX `st.bulk` path does not by itself establish that
special state in a normal cubin.

## Device observations (RTX 5090, sm_120, CUDA 13.1)

- With no pending initialization state, unguarded `ACQSHMINIT` returns and the
  kernel exits normally. `@!PT` is an ordinary predicated-off no-op.
- Idle issue cost is indistinguishable from a one-cycle CBU instruction in the
  `CS2R SR_CLOCKLO` harness.
- `UMEMSETS` followed by `ACQSHMINIT` in the same warp correctly leaves the
  initialized range zero, but an immediate same-warp `LDS` already observed
  zero without ACQSHMINIT.
- Queuing 1, 2, 4, 8 or 16 full-64-KiB `UMEMSETS` operations and then executing
  ACQSHMINIT added only one issue cycle. At 32 operations the UMEMSETS stream
  back-pressured for about 15.4K cycles, while ACQSHMINIT still added one.
  Therefore it does **not** drain the ordinary `$VQ_AGU` UMEMSETS queue.
- Ad-hoc cross-warp races without the hidden release-state setup were scheduling
  dependent and supplied no supported synchronization guarantee. They are not
  regression tests.

These observations are consistent with the official name: the instruction
waits a dedicated scheduler/warp-state condition, not a scoreboard and not
the generic shared-memory pipeline. When that state is already released,
there is nothing to wait for.

## Scheduling model

`ACQSHMINIT` is operandless `INST_TYPE_COUPLED_MATH` on the CBU, like
`ACQBULK`. It has no virtual queue, read scoreboard or write scoreboard.
Although the grammar carries `REQ`, `ACQSHMINIT` is absent from the latency
file's `CBU_OPS_WITH_REQ` set; the request bits are therefore not evidence of
UMEMSETS completion tracking. Blocking time is external-state dependent and
cannot be inferred from the normal data-connector latency tables.

## Validation

- `tools/decode_acqshminit.py`: default/positive/negative guards and scheduling
  bits.
- `tests/asm_construct/test_acqshminit.py`: sm_120 encoding, sm_90 absence,
  standalone execution and a safe UMEMSETS→ACQSHMINIT smoke test.
- PTX capture: CUDA 13.1 `st.bulk` lowering compiled for sm_100a and sm_120a.

## Open questions

- Which compiler/runtime metadata or internal prologue establishes the
  unreleased shared-init warp state?
- Which agent releases it after UMEMSETS: a designated initialization warp,
  CTA launch microcode, or virtual-resource-management machinery?
- Is the state shared by a warp, warpgroup or complete CTA?
- Does a true pending-state release provide acquire ordering for all initialized
  shared bytes, in addition to control release? The instruction name strongly
  suggests yes, but the public PTX path cannot create the needed state directly.
