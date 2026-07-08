# BREAK — Peel lanes out of a convergence barrier

**Opcode mnemonic:** `BREAK` = `0b100101000010` = **0x942** | **Pipe:** `cbu_pipe` (Convergence-Barrier / Branch Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

Part of the Volta+ convergence-barrier family (`BSSY` 0x945 / `BSYNC` 0x941 / `BREAK` 0x942).
See `bssy.md` for the shared model and `cbu_state.md` for the barrier register file.

## Semantics
`@P BREAK Bi` **removes the guarded lanes from convergence-barrier register `Bi`'s
participant set**. Those lanes will no longer be waited on by the matching `BSYNC Bi`.

It is the mechanism for a lane to *leave a convergence region early* — e.g. `break`
/ `goto` / `return` out of a loop or region whose reconvergence point was armed by an
enclosing `BSSY Bi`. `BREAK` itself does **not** branch; ptxas always pairs it with a
following predicated `BRA` to the actual exit target:

```
        @!P0 BREAK B1        ; drop these lanes from B1's participant set
        @!P0 BRA   exit      ; then jump them out of the region
        ...
        BSYNC B1             ; waits only on lanes still in B1
```

Because it edits per-warp barrier state and ends the block, it is marked
`MEM_SCBD_TYPE = BB_ENDING_INST` and is an `RPC_WRITERS` member (updates the
reconvergence-PC / participation state) — both unlike `BSSY`.

## Variant overview
Single CLASS `break_inst_`, one opcode (0x942). No target and no register/immediate
operands — every `ISRC_*`/`IDEST_*` size is 0. The only operand is the barrier
selector `Bi`, plus the optional guard predicate `@Pg` and the (always-`PT` in
practice) `Pp` operand.

## Operands / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | opcode | 0x942 | 13-bit `{bit91, [11:0]}`; bit91=0 |
| [14:12] | `Pg` | guard predicate | 7=PT (default, hidden) |
| [15] | `Pg_not` | `Pg@not` | `@!Px` guard negate — the common `@!P0 BREAK` form |
| [89:87] | `Pnz` (`Pp`) | 2nd predicate operand | printed only if ≠ PT (never observed ≠PT) |
| [90] | `input_reg_sz_32_dist` | `Pp@not` | negate of `Pp` |
| [19:16] | `barReg` | `BD` enum | barrier **B0..B15** to peel from |

Identical to `BSSY`/`BSYNC` minus the `Sa` target field. Shared scheduling/control
word (`req_bit_set` [121:116], `src_rel_sb` [115:113]=7, `dst_wr_sb` [112:110]=7,
`pm_pred` [103:102], `opex` [124:122]∥[109:105]) is the standard per-instruction
control word, not BREAK-specific.

`BD` enum: value `n` → `Bn` for n∈[0,15].

## Bit layout
```
127                                                          0
  ...####################.##..........#####.......................   <- hi64 ctrl word + opcode[91]
  ...............................................####.####...####   <- barReg[19:16], Pnz[89:87], Pg/Pg_not[15:12], opcode[11:0]
```

## Cross-comparison (vs BSSY / BSYNC)
| | BSSY 0x945 | BSYNC 0x941 | **BREAK 0x942** |
|--|-----------|-------------|-----------------|
| target `Sa` | yes [63:34] | no | no |
| role | arm barrier `Bi` (mask + reconv PC) | wait + reconverge on `Bi` | **peel lanes out of `Bi`** |
| `MEM_SCBD` | NONE | NONE | **NON_BARRIER_INT_INST** |
| `MEM_SCBD_TYPE` | BARRIER_INST | BARRIER_INST | **BB_ENDING_INST** |
| `RPC_WRITERS` | no | yes | **yes** |
| `CBU_OPS_WITH_REQ` (`&req=` wait) | no | no | **yes** |
| extra `IERROR` | — | — | `ILLEGAL_INSTR_PARAM` |

So BREAK is the "branch-like" member of the trio: it ends a basic block, writes RPC
state, and honors the `&req=` scoreboard wait — whereas BSSY/BSYNC are pure barrier
bookkeeping.

## Latency
`cbu_pipe` = `BRU_OPS` (`sm_90_latencies.txt:7`). BREAK is additionally listed in
`CBU_OPS_WITH_REQ` (line 219), so it participates in the `TABLE_TRUE(SCOREBOARD)`
`&req=` connector (resolves to `ORDERED_ZERO`). As a `DECOUPLED_BRU` op with
`MIN_WAIT_NEEDED=1` it is ordered by the control word, not a register producer→consumer
latency.

## Verified encodings (decoder: `tools/decode_break.py`, 4/4 match)
| PC | Lo64 | Hi64 | Disassembly | src |
|----|------|------|-------------|-----|
| 0x01f0 | 0x0000000000018942 | 0x000fea0003800000 | `@!P0 BREAK B1` | break_test.cu (kB) |
| 0x02a0 | 0x0000000000017941 | 0x000fea0003800000 | `BSYNC B1`      | break_test.cu (kB) |
| 0x0300 | 0x0000000000007941 | 0x000fea0003800000 | `BSYNC B0`      | break_test.cu (kB) |
| 0x0180 | 0x0000000000018942 | 0x000fea0003800000 | `@!P0 BREAK B1` | bssy_break_test.cu |

Hand-check `@!P0 BREAK B1`: opcode [11:0]=0x942, bit91=0 → BREAK; `barReg` nibble
[19:16]=1 → B1; [15:12]=0x8 → Pg_not=1, Pg=0 → `@!P0`; Pp=[89:87]=PT (hidden). ✓

### Empirical notes (CUDA 13.1 ptxas, sm_90)
- **When it appears:** only for early exits that must peel lanes from an *enclosing*
  barrier (break/goto/return crossing a nested `BSSY`). A simple innermost loop `break`
  is instead folded into the back-edge branch's `Pp` predicate (`@!P0 BRA P1, top`),
  emitting **no** BREAK — see `bssy.md`.
- Always emitted as the pair `@!Pk BREAK Bi ; @!Pk BRA exit`.
- **Rare in stock libraries:** 0 hits in scanned libcublas / libcufft SASS (same as
  BMOV) — it shows up only in irregular-divergence code, so nvdisasm's rendering is
  sampled here from purpose-built kernels rather than shipped binaries.

## Open questions
- Non-`PT` `Pp` on BREAK was never observed; its effect (if any) on which lanes are
  peeled, independent of the `@Pg` guard, is unverified.
- Only `B0`/`B1` selectors observed empirically; the 4-bit `barReg` field trivially
  encodes B0..B15 (same field as BSSY, where B0/B1 are both confirmed), but B2..B15
  in a BREAK were not reproduced by the test kernels.
