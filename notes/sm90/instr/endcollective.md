# ENDCOLLECTIVE — Close a warp collective-region

**Opcode mnemonic:** `ENDCOLLECTIVE` = `0b100100011011` = **0x91b** | **Pipe:** `cbu_pipe` (dispatch) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

The closing bracket of the warp **collective region** opened by `WARPSYNC.COLLECTIVE`
(see `warpsync.md`). It marks the end of the region over which a specific warp
participant-mask (`MCOLLECTIVE`) is declared.

## Semantics
`@Pg ENDCOLLECTIVE [Pp]` terminates the collective region begun by the preceding
`WARPSYNC.COLLECTIVE Rmask, TGT`. It takes no target and no register operands — just the
guard `Pg` and an optional predicate `Pp`. In every observed case it renders as bare
`ENDCOLLECTIVE`.

The region is a fixed, empty-bodied idiom:
```
        BSSY  B1, JOIN
        WARPSYNC.COLLECTIVE Rmask, TGT   ; open; declares participant mask Rmask
        NOP                              ; (region body — empty)
        ENDCOLLECTIVE                    ; close;  TGT == this insn's successor
  TGT:  BSYNC B1
  JOIN: BRA ...
```
`WARPSYNC.COLLECTIVE`'s target points exactly at ENDCOLLECTIVE's successor, so the
"collective region" is the two/three instructions between them.

## Variant overview
Single CLASS `endcollective_`, one opcode 0x91b. All `ISRC_*`/`IDEST_*` sizes = 0.

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x91b |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | predicate operand (printed if ≠ PT) |

`opex` uses `TABLES_opex_1` (not `opex_0` like the branch family); `src_rel_sb`/`dst_wr_sb`
are pinned `*7`.

## The CBU-family oddity: COUPLED_MATH, not DECOUPLED_BRU
Unlike every other member of the `cbu_pipe` set (`BRA/BSSY/BSYNC/BREAK/WARPSYNC/CALL/…`,
all `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`), ENDCOLLECTIVE is **`INST_TYPE_COUPLED_MATH`**:
it dispatches to the CBU virtual queue (`VQ_CBU`) but is scheduled as a **fixed-latency
coupled** instruction, not a decoupled branch. Consistent with that:
- **not** in `RPC_WRITERS` (it changes no PC / reconvergence state), and
- **not** in `CBU_OPS_WITH_REQ` (no `&req=` scoreboard gating).

So it is pure region bookkeeping — it neither branches nor blocks; it just tears down the
`MCOLLECTIVE` participant declaration.

## Cross-comparison
| | WARPSYNC.COLLECTIVE | **ENDCOLLECTIVE** | BSYNC |
|--|---------------------|-------------------|-------|
| role | open collective region (declare mask) | **close collective region** | reconverge barrier |
| target operand | yes (PC-rel, = ENDCOLLECTIVE successor) | none | none |
| INSTRUCTION_TYPE | DECOUPLED_BRU | **COUPLED_MATH** | DECOUPLED_BRU |
| RPC_WRITERS / CBU_OPS_WITH_REQ | y / y | **n / n** | y / — |

## Verified encodings (decoder: `tools/decode_endcollective.py`)
Self-test 2/2; **57894/57894 ENDCOLLECTIVE in libcusparse decoded byte-exact** — an exact
1:1 match with the 57894 `WARPSYNC.COLLECTIVE`; also 1/1 in the `-G` build.

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| 0x000000000000791b | 0x022fe20003800000 | `ENDCOLLECTIVE` | libcusparse |
| 0x000000000000791b | 0x003fde0003800000 | `ENDCOLLECTIVE` | `-G` build |

### Provenance (from the WARPSYNC investigation)
Emitted only as the closer of a `WARPSYNC.COLLECTIVE` region. Reproduced by compiling a
plain `__syncwarp()` with **`-G`** (device debug), which lowers the sync into the explicit
`WARPSYNC.COLLECTIVE … NOP … ENDCOLLECTIVE` region; `-O3` collapses the same source to
`WARPSYNC.ALL` (no ENDCOLLECTIVE). cusparse additionally emits the pair in optimized
multi-GPU/system-scope warp-aggregation code. See `warpsync.md` for the full analysis.

## Open questions
- Whether ENDCOLLECTIVE has any HW effect beyond clearing the `MCOLLECTIVE` declaration
  (e.g. re-widening the executable mask) is not spec-stated; the empty (`NOP`) region body
  suggests it is a pure marker.
