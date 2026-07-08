# BRA — Relative branch

**Opcode mnemonic:** `BRA` (base) = `0b100101000111` = **0x947** | **Pipe:** `cbu_pipe` (Branch / Convergence-Barrier Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The workhorse control-flow instruction: a PC-relative branch to a signed offset. Works
with the convergence-barrier machinery (`BSSY`/`BSYNC`/`BREAK`, see `bssy.md`) — a `BRA`
guarded by a predicate is how the compiler actually diverges a warp inside a `BSSY…BSYNC`
region.

## Semantics
`@Pg BRA target` transfers control to `target = PC + 0x10 + sImm*4` for the lanes where
the guard predicate `Pg` holds (relative to the *next* instruction; `sImm` is 56-bit
signed, `SCALE 4`). Unpredicated `BRA` is an unconditional jump.

The optional second predicate operand `Pp` (`BRA Pp, target`) is the **divergence
predicate**: it names the lanes the branch must account for when partial divergence
occurs — in practice it appears on loop back-edges (`@!P0 BRA P1, top`, P1 = "keep
looping" set) and is paired with `BSYNC` for reconvergence.

## Variant overview (8 CLASSes, 3 distinct opcodes)
| opcode `{b91,[11:0]}` | CLASS(es) | extra operand | note |
|-----------------------|-----------|---------------|------|
| **0x947** (b91=0) | `bra__CONV_DIV`, `bra__U` (+ `_rel_` alts) | — | plain `BRA{.DIV/.CONV} {Pp,} target` |
| **0x1947** (b91=1) | `bra_uniform_` (+ `_rel_`) | `[~]URb` [29:24] | `BRA.DIV {Pp,} [~]URb, target` |
| **0x1547** (b91=1) | `bra_uniform_pred_` (+ `_rel_`) | `[!]UPq` [26:24] | uniform-predicate form |

`_rel_` alternates only change how the assembler is *given* the target (`RSImm` label vs
explicit relative), same bits. `bra__U` shares 0x947 with `bra__CONV_DIV` but carries a
`USEL` bit at [84]; `nvdisasm` renders the plain form.

## Operands / fields (128-bit, `bra__CONV_DIV`)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | opcode | 0x947 | b91 selects uniform variants (0x1947/0x1547) |
| [14:12] | `Pg` | guard predicate | 7=PT (default, hidden) |
| [15] | `Pg_not` | `Pg@not` | `@!Px` |
| [89:87] | `Pnz` (`Pp`) | divergence predicate | printed only if ≠ PT |
| [90] | `input_reg_sz_32_dist` | `Pp@not` | negate of `Pp` |
| [33:32] | `cond` | `COND__DIV_CONV` | 0=none, 2=`.DIV`, 3=`.CONV` |
| [86:85] | `cop` | `DEPTH` | 0=none, 1=`.INC`, 2=`.DEC` (call-depth), 3=INVALID |
| [84] | `OR` | `usel`/`*0` | `USEL` ALL/ANY for `bra__U`; 0 otherwise |
| [81:34]∥[23:16] | `sImm` | target | 56-bit signed, `SCALE 4`; hi 48b ∥ lo 8b |

Uniform-variant extra fields: `bra_uniform_` `Sa`=URb [29:24] + `URb_invert` [30] (`~`);
`bra_uniform_pred_` `UPq` [26:24] + `UPq_not` [27] (`!`). Shared control word
(`req_bit_set`/`src_rel_sb`/`dst_wr_sb`/`pm_pred`/`opex`) is the standard per-instruction
scheduling field, not BRA-specific.

## Bit layout (base BRA)
```
127                                                          0
  ...####################.##..........########..##################   <- ctrl word, opcode[91], Pp, depth, sImm(hi48)
  ################################........########################   <- sImm(hi) | sImm(lo8)[23:16], cond[33:32], Pg
```

## Cross-comparison
- vs **JMP** (absolute) / **BRX**/**BRXU** (register/uniform-register indirect) /
  **CALL**/**RET** — all `cbu_pipe`, all `RPC_WRITERS`; BRA is the PC-relative immediate form.
- vs the **CBU trio**: BRA does the actual control transfer; `BSSY`/`BSYNC` only manage the
  convergence barrier that the divergent BRAs live inside.
- Like `BREAK` (and unlike `BSSY`/`BSYNC`), BRA is in `CBU_OPS_WITH_REQ` (honors `&req=`).

## Latency
`cbu_pipe` = `BRU_OPS` (`sm_90_latencies.txt:7`). BRA is an `RPC_WRITERS` member
(line 411) → **9-cycle** true-dependency on the `RPC` hard resource (line 414), and is in
`CBU_OPS_WITH_REQ` (line 219) so it participates in the `&req=` scoreboard connector.
`DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_bra.py`)
Self-test 9/9, **and 125741/125741 BRA instructions in libcublas.so decoded byte-exact.**

| PC | Lo64 | Hi64 | Disassembly |
|----|------|------|-------------|
| 0x00c0 | 0x0000000000208947 | 0x000fea0003800000 | `@!P0 BRA 0x150` |
| 0x0120 | 0x00000000000c7947 | 0x000fec0003800000 | `BRA 0x160` |
| 0x0170 | 0xfffffffc00e08947 | 0x000fea000083ffff | `@!P0 BRA P1, 0x100` |
| 0x01c0 | 0xfffffffc00fc7947 | 0x000fc0000383ffff | `BRA 0x1c0` (self-loop, sImm=-4) |
| 0x14b0 | 0x0000001207e87947 | 0x000fea000b800000 | `BRA.DIV UR7, 0x2860` (uniform, b91=1) |
| 0x1100 | 0x0000001e05887947 | 0x000fea000b800000 | `BRA.DIV UR5, 0x2f30` (uniform, b91=1) |

Hand-check `BRA.DIV UR7, 0x2860`@0x14b0: b91=1,[11:0]=0x947 → `bra_uniform_`; cond[33:32]=2
→`.DIV`; URb[29:24]=7 →UR7; sImm=(4<<8)|0xe8=0x4e8, `0x14c0 + 0x4e8*4 = 0x2860`. ✓

Validate any dump: `python3 tools/decode_bra.py <sass.txt>`.

### Empirical notes (CUDA 13.1 ptxas, sm_90)
BRA-form frequency in ~125.7k libcublas branches:
- `BRA target` (unconditional/guarded) — ~121.5k (96.6%)
- `BRA Pp, target` — P0..P6 divergence-predicate forms (~2.9k)
- `BRA.DIV URb, target` — uniform-register variant 0x1947, URb∈{UR4..UR19} (~2.9k)
- **Never observed:** `.CONV`, `.INC`/`.DEC` (call-depth), `~URb` invert, and the entire
  `bra_uniform_pred_` (0x1547 / `UPq`) variant — these exist in spec but ptxas doesn't
  emit them here.

## Open questions
- Exact microarchitectural role of `URb` in `BRA.DIV URb` (uniform-register form): it
  supplies a uniform value/thread-set for the divergent branch, but whether it is a target
  set, active mask, or reconvergence hint is not pinned down from the spec alone.
- `.CONV`, `.INC`/`.DEC`, and the `UPq` uniform-predicate form are spec-defined but
  unsampled; their exact printed spelling/ordering is inferred from FORMAT, not verified.
