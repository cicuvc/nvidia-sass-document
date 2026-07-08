# BSSY — Branch Set Synchronization (establish a convergence barrier)

**Opcode mnemonic:** `BSSY` = `0b100101000101` = **0x945** | **Pipe:** `cbu_pipe` (Convergence-Barrier / Branch Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

Companion opcodes in the same family (share the base CBU layout, documented here for context):
`BSYNC` = **0x941**, `BREAK` = **0x942**.

## Semantics
Volta+ replaced the old SIMT reconvergence stack with explicit, register-named
**convergence barriers**. `BSSY Bi, target` is emitted just before entering a
divergent region:

- It **arms convergence-barrier register `Bi`** (one of B0..B15) with the set of
  threads that are active at this point (the *participating mask*) and records the
  **reconvergence PC = `target`** (the join point after the region).
- It does **not** branch — execution falls through. Divergence happens afterwards
  via ordinary predicated `BRA`s.
- `BSYNC Bi` at the tail of the region blocks each arriving lane until every
  participating lane of `Bi` has reached its `BSYNC` (or been peeled off), then
  **reconverges** them and falls through to the recorded reconvergence PC.
- `BREAK Bi` removes the guarded lanes from `Bi`'s participant set (early exit of a
  loop/region that spans the barrier) so the later `BSYNC Bi` won't wait on them.

`Bi` is the same barrier register file exposed as `CBU_STATE` values 0..15 to
`BMOV` (see `cbu_state.md`): each holds "participating-lane mask + reconvergence PC".

## Variant overview
Two ALTERNATE encodings, **identical bit layout**, same opcode 0x945 — they differ
only in how the assembler is *given* the target immediate:

| CLASS | target operand | meaning |
|-------|----------------|---------|
| `bssy_`     | `RSImm(32)*:Sa`          | relocatable/absolute label; assembler resolves it to a rel. offset |
| `bssy_rel_` | `SImm(32)*:Sa /RelOpt:rel` | explicit relative immediate (`.rel`); `RelOpt` has no encoded bit |

Both store the target as a **30-bit signed field `Sa` at [63:34], `SCALE 4`**, so the
byte displacement = `Sa*4` and
`target = PC_of_BSSY + 0x10 + Sa*4` (i.e. relative to the *next* instruction).
`nvdisasm`/cuobjdump always print the resolved **absolute target** (`BSSY B0, 0xba0`).

## Operands / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | opcode | 0x945 | 13-bit `{bit91, [11:0]}`; bit91=0 here |
| [14:12] | `Pg` | guard predicate | 7=PT (default, hidden) |
| [15] | `Pg_not` | `Pg@not` | `@!Px` guard negate |
| [89:87] | `Pnz` (`Pp`) | 2nd predicate operand | printed only if ≠ PT |
| [90] | `input_reg_sz_32_dist` | `Pp@not` | negate of `Pp` |
| [19:16] | `barReg` | `BD` enum | convergence barrier **B0..B15** |
| [63:34] | `Sa` | branch target | signed, `SCALE 4`, **BSSY only** (absent in BSYNC/BREAK) |

Shared scheduling/control word (common to every sm_90 instruction, not BSSY-specific):
`req_bit_set` [121:116] (`&req=` scoreboard wait mask), `src_rel_sb` [115:113]=7 /
`dst_wr_sb` [112:110]=7 (read/write scoreboard indices, 7=none), `pm_pred` [103:102]
(perf-monitor pred), `opex` [124:122]∥[109:105] = `TABLES_opex_0(batch_t, usched_info)`
(stall/yield scheduling info + batch flags).

`BD` enum: value `n` → `Bn` for n∈[0,15]. `RelOpt` enum: single value `REL`.

## Bit layout (BSSY)
```
127                                                          0
  ...####################.##..........#####.......................   <- hi64 ctrl (opex/req/sb/pm) + opcode[91]
  ##############################..............####################   <- Sa[63:34], barReg[19:16], Pnz, Pg, opcode[11:0]
```

## Cross-comparison (the CBU convergence-barrier family)
| mnem | opcode | operands | role |
|------|--------|----------|------|
| **BSSY**  | 0x945 | `Bi, target` | arm barrier `Bi`, set reconv PC = target |
| **BSYNC** | 0x941 | `Bi`         | wait for all participants of `Bi`, reconverge |
| **BREAK** | 0x942 | `Bi`         | peel guarded lanes out of `Bi`'s participant set |

All three: `cbu_pipe`, `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`, same
`@Pg`/`Pp`/`barReg` base layout; only BSSY carries a target. `BSYNC` is an
`RPC_WRITERS` member (changes the reconvergence PC); BSSY is not. `BREAK` (with the
other true branches) is in `CBU_OPS_WITH_REQ` — it participates in the `&req=`
scoreboard-wait dependency; **BSSY/BSYNC do not**.

## Latency
`cbu_pipe` = `BRU_OPS` in `sm_90_latencies.txt:7`. In the scoreboard true-dependency
table (`TABLE_TRUE(SCOREBOARD)`, line 220) all these ops resolve to `ORDERED_ZERO`.
Being `DECOUPLED_BRU` with `MIN_WAIT_NEEDED=1`, they issue to the branch unit and are
ordered by the control word rather than a producer→consumer register latency.

## Verified encodings (decoder: `tools/decode_bssy.py`, 9/9 match)
| PC | Lo64 | Hi64 | Disassembly | src |
|----|------|------|-------------|-----|
| 0x0960 | 0x0000023000007945 | 0x000fe20003800000 | `BSSY B0, 0xba0`  | libcublas |
| 0x0d00 | 0x0000012000007945 | 0x000ff20003800000 | `BSSY B0, 0xe30`  | libcublas |
| 0x0090 | 0x000000d000007945 | 0x000fe20003800000 | `BSSY B0, 0x170` | switch kernel |
| 0x0160 | 0x0000000000007941 | 0x000fea0003800000 | `BSYNC B0`        | switch kernel |
| 0x00b0 | 0x000001a000007945 | 0x000fe20003800000 | `BSSY B0, 0x260` | nested-loop |
| 0x00f0 | 0x0000010000017945 | 0x000fe20003800000 | `BSSY B1, 0x200` | nested-loop |
| 0x0180 | 0x0000000000018942 | 0x000fea0003800000 | `@!P0 BREAK B1`   | nested-loop |
| 0x01f0 | 0x0000000000017941 | 0x000fea0003800000 | `BSYNC B1`        | nested-loop |
| 0x0250 | 0x0000000000007941 | 0x000fea0003800000 | `BSYNC B0`        | nested-loop |

Hand-check of `BSSY B0, 0xba0`@0x960: `Sa=0x230>>... = 140`, `140*4=0x230`,
`0x960+0x10+0x230 = 0xba0`. ✓ `barReg` nibble [19:16]=0 → B0. ✓

### Divergent-region idiom (empirical, CUDA 13.1 ptxas, sm_90)
```
        BSSY  B0, JOIN          ; arm barrier, JOIN = addr after BSYNC
        @!P0 BRA  case_x        ; ordinary predicated divergence
        ...
        BRA   PRE_SYNC          ; each path funnels to just before BSYNC
PRE_SYNC:
        BSYNC B0                ; reconverge here
JOIN:   ...                    ; BSSY target points here (past BSYNC)
```
Loops with `break`: the compiler usually **avoids `BREAK`**, instead threading the
loop-exit condition into the branch's `Pp` operand: `@!P0 BRA P1, LOOP_TOP` (P1 =
"keep looping" mask) followed by `BSYNC`. `BREAK Bi` is emitted for early exits that
must peel lanes out of an *enclosing* barrier — e.g. a `goto`/break to an outer loop
across a nested `BSSY B1`: `@!P0 BREAK B1 ; @!P0 BRA outer_sync`.

## Open questions
- The `Pp`/`Pnz` operand on BSSY itself is always `PT` in observed code (only branches
  like `BRA`/`BREAK` carry a non-PT `Pp`). Its precise effect on the armed participant
  mask when `Pp != PT` is not yet corroborated empirically.
- `Sa` is a 30-bit field scaled by 4 (±4 GiB / instruction-granular reach). Targets are
  always 16-byte aligned in practice; whether a non-16B-aligned `Sa` is legal (vs. just
  unused low bits) is unverified.
