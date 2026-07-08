# BSYNC — Branch Synchronize (wait on a convergence barrier, reconverge)

**Opcode mnemonic:** `BSYNC` = `0b100101000001` = **0x941** | **Pipe:** `cbu_pipe` (Convergence-Barrier / Branch Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

Part of the Volta+ convergence-barrier family (`BSSY` 0x945 / `BSYNC` 0x941 / `BREAK` 0x942).
See `bssy.md` for the shared model and `cbu_state.md` for the barrier register file.

## Semantics
`BSYNC Bi` is the **reconvergence point** of a divergent region that was armed by an
earlier `BSSY Bi`. Each lane that reaches it blocks until **every participating lane of
`Bi`** (as recorded by `BSSY`, minus any peeled off by `BREAK Bi` or exited) has also
arrived, then the warp **reconverges** those lanes and execution continues at the
reconvergence PC that `BSSY` stored (which is the address *after* the `BSYNC` — see
`bssy.md`, where `BSSY`'s target points past its matching `BSYNC`).

It is a barrier-only operation: no branch target, no register/immediate operands, just
the barrier selector `Bi` and an (always-`PT` in practice) predicate operand.

## Variant overview
Single CLASS `bsync_`, one opcode (0x941). Every `ISRC_*`/`IDEST_*` size is 0. The
only operand is `Bi`, plus the optional guard `@Pg` and the `Pp` operand.

## Operands / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | opcode | 0x941 | 13-bit `{bit91, [11:0]}`; bit91=0 |
| [14:12] | `Pg` | guard predicate | 7=PT (default, hidden) |
| [15] | `Pg_not` | `Pg@not` | `@!Px` guard negate |
| [89:87] | `Pnz` (`Pp`) | 2nd predicate operand | printed only if ≠ PT (never observed ≠PT) |
| [90] | `input_reg_sz_32_dist` | `Pp@not` | negate of `Pp` |
| [19:16] | `barReg` | `BD` enum | barrier **B0..B15** to wait on |

Identical layout to `BREAK`, differing only in opcode and properties. Shared
scheduling/control word (`req_bit_set` [121:116], `src_rel_sb` [115:113]=7,
`dst_wr_sb` [112:110]=7, `pm_pred` [103:102], `opex` [124:122]∥[109:105]) is the
standard per-instruction control word, not BSYNC-specific.

`BD` enum: value `n` → `Bn` for n∈[0,15].

## Bit layout
```
127                                                          0
  ...####################.##..........#####.......................   <- hi64 ctrl word + opcode[91]
  ...............................................####.####...####   <- barReg[19:16], Pnz[89:87], Pg/Pg_not[15:12], opcode[11:0]
```

## Cross-comparison (the CBU trio)
| | BSSY 0x945 | **BSYNC 0x941** | BREAK 0x942 |
|--|-----------|-----------------|-------------|
| target `Sa` | yes [63:34] | no | no |
| role | arm barrier `Bi` | **wait + reconverge on `Bi`** | peel lanes out of `Bi` |
| `MEM_SCBD` | NONE | **NONE** | NON_BARRIER_INT_INST |
| `MEM_SCBD_TYPE` | BARRIER_INST | **BARRIER_INST** | BB_ENDING_INST |
| `RPC_WRITERS` | no | **yes** | yes |
| `CBU_OPS_WITH_REQ` (`&req=`) | no | **no** | yes |
| `IERRORS` | ILLEGAL_DECODING, PC_MISALIGNED, PC_WRAP | **ILLEGAL_DECODING, PC_WRAP** | +ILLEGAL_INSTR_PARAM |

BSYNC has no target, so (unlike BSSY) it can't raise `PC_MISALIGNED`; it keeps
`MEM_SCBD_TYPE = BARRIER_INST` (pure barrier bookkeeping, does not end the block the
way `BREAK` does), yet it *is* an `RPC_WRITERS` member because reconverging updates the
warp's reconvergence PC.

## Latency
`cbu_pipe` = `BRU_OPS` (`sm_90_latencies.txt:7`). BSYNC is an `RPC_WRITERS` member
(line 411): on the `RPC` hard resource, `TABLE_TRUE(RPC)` gives writers a **latency of
9 cycles** (line 414) to a consumer reading RPC. It is *not* in `CBU_OPS_WITH_REQ`, so
it does not itself gate on the `&req=` scoreboard connector. As a `DECOUPLED_BRU` op
with `MIN_WAIT_NEEDED=1` its issue is otherwise ordered by the control word.

## Verified encodings (decoder: `tools/decode_bsync.py`, 6/6 match)
| PC | Lo64 | Hi64 | Disassembly | src |
|----|------|------|-------------|-----|
| 0x0160 | 0x0000000000007941 | 0x000fea0003800000 | `BSYNC B0` | switch kernel |
| 0x01f0 | 0x0000000000017941 | 0x000fea0003800000 | `BSYNC B1` | nested-loop |
| 0x0250 | 0x0000000000007941 | 0x000fea0003800000 | `BSYNC B0` | nested-loop |
| 0x02a0 | 0x0000000000017941 | 0x000fea0003800000 | `BSYNC B1` | break_test (kB) |
| 0x0300 | 0x0000000000007941 | 0x000fea0003800000 | `BSYNC B0` | break_test (kB) |
| 0x0b90 | 0x0000000000007941 | 0x000fea0003800000 | `BSYNC B0` | libcublas |

Hand-check `BSYNC B1`: opcode [11:0]=0x941, bit91=0 → BSYNC; `barReg` nibble [19:16]=1
→ B1; Pg=[14:12]=7 & Pg_not=0 → no guard; Pp=[89:87]=7 → hidden. ✓

### Empirical notes (CUDA 13.1 ptxas, sm_90)
- Always the tail of a `BSSY Bi … BSYNC Bi` bracket; the `BSSY` target is the
  instruction right after `BSYNC`, so lanes fall through the join after reconverging.
- Common in stock libraries (unlike `BREAK`/`BMOV`): every divergent region in
  libcublas is bracketed by `BSSY`/`BSYNC`.
- The control word `0x000fea…` seen here encodes the usual stall/yield; not
  BSYNC-specific.

## Open questions
- Non-`PT` `Pp` on BSYNC was never observed; whether a non-PT `Pp` restricts which
  lanes are reconverged is unverified.
- Only `B0`/`B1` observed empirically; the 4-bit `barReg` trivially reaches B0..B15.
