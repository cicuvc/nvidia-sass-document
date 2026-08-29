# JMP — Absolute / constant-bank jump

**Opcode mnemonic:** `JMP` (imm base) = `0b100101001010` = **0x94a**; (const base) = **0xb4a** | **Pipe:** `cbu_pipe` (Branch Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` | **BRANCH_TYPE:** `BRT_BRANCH`

The absolute counterpart to `BRA`: where `BRA` adds a signed offset to the PC, `JMP`
loads the target as an **absolute address** — either an immediate or read from a
**constant bank** (`c[bank][offset]`, the mechanism behind jump tables / far jumps).

## Semantics
`@Pg JMP target` transfers control (for lanes where guard `Pg` holds) to an absolute
target:
- **imm form** (`0x94a`): `target = Sa * 4`, `Sa` a 55-bit unsigned immediate. **No PC is
  added** — verified: the same target-field bits that a `BRA` renders as `0x580` render
  as `0x490` (= `0x124*4`) under `JMP`.
- **const form** (`0xb4a`): `target = c[bank][off]`, `bank` = [58:54], `off` =
  `sign_extend([53:40],14) * 4` (signed byte offset into constant memory).

Like `BRA`, it takes the optional guard `@Pg` and divergence predicate operand `Pp`.

### `.DIV` / `.CONV`: branch on execution-group convergence

Let `A` be the lane mask of the **current SIMT execution group** (not necessarily the
whole warp).  Direct execution on both H20 (SM90) and RTX 5090 (SM120) gives:

- Base `JMP.DIV target` jumps iff the current group is divergent (`A != 0xffffffff`);
  `JMP.CONV target` is its complement and jumps iff the full warp is present.
- The uniform-register form treats `[~]URb` as a 32-bit requested-lane mask `M`.
  `JMP.DIV URb, target` jumps iff `M` contains a lane absent from the current group,
  i.e. `(M & ~A) != 0`; `JMP.CONV URb, target` jumps iff `(M & ~A) == 0`.
  When the condition holds, every lane in `A` transfers together.  `~URb` complements
  `M` before this test.
- Supplying `Pp` instead gives a per-lane divergence predicate.  With a full warp and
  `P0=true` on lanes 0--15, `JMP.DIV P0, target` transfers exactly lanes 0--15, while
  `JMP.CONV P0, target` does not transfer; with `P0=true` on all lanes, the outcomes
  reverse (`DIV` falls through, `CONV` transfers all lanes).  Thus `Pp` describes the
  proposed branch subset: `.DIV` admits a partially selected/diverging subset, whereas
  `.CONV` admits the fully selected/converged case.  The all-false edge is unobservable
  as a transfer, and combinations of nontrivial `Pg` and `Pp` remain unprobed.

The `URb` rule explains the real `BRA.DIV URb, slow_path` pattern around warp
collectives: branch to emulation when the requested participant mask names lanes that
are not in the currently executing group.  The base form is equivalent to requesting
the full-warp mask for this convergence test.

### `.U[.ALL|.ANY]`: uniformize the guard

`.U` turns the lane predicate guard into one uniform branch decision over `A`:

```
JMP.U.ALL: take = ALL lanes in A satisfy Pg    (ALL is the encoded default)
JMP.U.ANY: take = ANY lane  in A satisfies Pg
```

All lanes in `A` then either jump together or fall through together.  For a full warp
where `P0` is true only on lanes 0--15, `@P0 JMP.U.ALL` falls through for all 32 lanes,
whereas `@P0 JMP.U.ANY` transfers all 32.  After first splitting the warp so that
`A={0..15}`, `@P0 JMP.U.ALL` transfers that entire 16-lane group, proving that the
reduction is scoped to the current execution group rather than the original warp.

The uniform-predicate form adds a uniform gate: `JMP.U[.ANY] [!]UPq, target` takes only
when both the reduced `Pg` result and `[!]UPq` are true.  H20 tests with `UP0=false`
showed `UP0` suppressing an otherwise-true `.ANY` and `!UP0` restoring it.

## Variant overview (12 CLASSes, 6 distinct opcodes)
| opcode `{b91,[11:0]}` | family | CLASS | extra operand |
|-----------------------|--------|-------|---------------|
| **0x094a** | imm  | `jmp_imm__CONV_DIV` / `__U` (+`_rel_`) | — |
| **0x194a** | imm  | `jmp_imm_uniform_` (+`_rel_`) | `[~]URb` [29:24] |
| **0x154a** | imm  | `jmp_imm_uniform_pred_` (+`_rel_`) | `[!]UPq` [26:24] |
| **0x0b4a** | const| `jmp_const__CONV_DIV` / `__U` | — |
| **0x1b4a** | const| `jmp_const_uniform_` | `[~]URb` [29:24] |
| **0x174a** | const| `jmp_const_uniform_pred_` | `[!]UPq` [26:24] |

`bit9` of the opcode selects const(1)/imm(0); `bit91` + low bits select the uniform
variants. The `__CONV_DIV` and `__U` classes coexist at the base opcodes and are
disambiguated by the `cond` field value (see below).

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | b9=const/imm, b91=uniform |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | divergence predicate, printed if ≠ PT |
| [33:32] | `cond` | enum varies by variant (below) |
| [86:85] | `depth` | `DEPTH` `.INC`/`.DEC` (call depth), rarely used |
| [80:34]∥[23:16] | `Sa` | **imm** target, 55-bit unsigned; absolute = `Sa*4` |
| [58:54] | `bank` | **const** bank |
| [53:40] | `off` | **const** offset, 14-bit **signed**, byte = `off*4` |
| [29:24]/[30] | `URb`/invert | uniform-register variants |
| [26:24]/[27] | `UPq`/not | uniform-predicate variants |

### `cond` [33:32] rendering (variant-dependent)
| cond | base (`0x?4a`) | uniform-reg (`0x1?4a`) | uniform-pred (`0x154a/0x174a`) |
|-----:|----------------|------------------------|-------------------------------|
| 0 | *(none)* | `.???0` | `.???0` |
| 1 | `.U` | `.???1` | `.U` |
| 2 | `.DIV` | `.DIV` | `.???2` |
| 3 | `.CONV` | `.CONV` | `.???3` |

`.???N` is `nvdisasm`'s literal rendering of an out-of-enum value (base uses
`COND__DIV_CONV`+`UONLY`, uniform-reg uses `COND_DIV_CONV_jmp`, uniform-pred uses `UONLY`).

## Cross-comparison
- vs **BRA** (0x947): same guard/`Pp`/uniform machinery and 128-bit skeleton, but BRA is
  PC-relative signed (`sImm*4`, 56-bit); JMP is absolute (imm `Sa*4` or const bank). Both
  in `OP_BRA_JMP`.
- **Latency difference:** BRA is in `CBU_OPS_WITH_REQ` (honors `&req=`); **JMP is not**.
- vs **BRX**/**JMX** (register-indirect) — JMP's target is immediate/const, not a GPR.

## Latency
`cbu_pipe` = `BRU_OPS`. `RPC_WRITERS` member → **9-cycle** true-dependency on the `RPC`
resource (`sm_90_latencies.txt:411,414`). `DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_jmp.py`)
JMP is **not emitted by ptxas** for the sampled workloads (libcublas/cufft/cusparse/nppif:
0 hits; compilers use relative `BRA`, even for 128-case switches). Ground truth was
obtained by **patching a real cubin instruction and reading `nvdisasm`'s rendering**:
self-test 10/10, plus a **randomized battery of 300 patched encodings decoded 100%**
(all families, cond values, predicates, banks, signed offsets, uniform operands).

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| 0x000000040024094a | 0x000fea0003800000 | `@P0 JMP 0x490` (imm absolute) |
| 0x0000000400240b4a | 0x000fea0003800000 | `@P0 JMP c[0x0][0x0]` (const) |
| 0x000000060024094a | 0x000fea000b800000 | `@P0 JMP.DIV UR0, 0x490` (imm uniform) |
| 0x000000060024054a | 0x000fea000b800000 | `@P0 JMP.???2 UP0, 0x490` (imm uniform-pred) |
| 0x0000000600240b4a | 0x000fea000b800000 | `@P0 JMP.DIV UR0, c[0x0][0x0]` (const uniform) |
| 0x0000010000000b4a | 0x000fea0003800000 | `@P0 JMP c[0x0][0x4]` (off field 1 → 0x4) |
| 0x0080800000000b4a | 0x000fea0003800000 | `@P0 JMP c[0x2][0x200]` (bank 2, off 0x80 → 0x200) |

Hand-check absolute imm: `Sa=(1<<8)|0x24=0x124`, `0x124*4 = 0x490` (no PC added).
Hand-check const signed off: field `0x3d78` → sx14 = `-648` → `-648*4 = -0xa20`.

## Empirical modifier probe

`sassdbg/probe_jmp_modifiers.py` executes absolute JMP targets from heap-resident SASS
and records the decision per lane.  The key matrix matched exactly on H20 (SM90) and
RTX 5090 (SM120):

| current group `A` | operand / guard | `.DIV` | `.CONV` / `.U.ALL` | `.U.ANY` |
|---|---|---|---|---|
| all 32 | no operand | fall through | take all | — |
| lanes 0--15 | no operand | take 0--15 | fall through | — |
| lanes 0--15 | `URb=0x0000ffff` | fall through | take 0--15 | — |
| lanes 0--15 | `URb=0xffff0000` | take 0--15 | fall through | — |
| all 32 | `@P0`, P0 true on 0--15 | — | fall through all | take all |
| lanes 0--15 | `@P0`, P0 true on 0--15 | — | take 0--15 | take 0--15 |

## Open questions
- Since ptxas never emits `JMP`, real-world target operand distributions (constant/RTV
  banks) remain unobserved; modifier semantics instead come from the direct probe above.
- `RTV banks` (24–31), nontrivial simultaneous `Pg`+`Pp`, and `depth`
  (`.INC`/`.DEC`) on JMP remain unexercised.

## Resolved: absolute semantics confirmed; labels do NOT work for JMP (SM120)

Empirically confirmed (SM120, `tests/asm_construct/test_jmp.py`): JMP imm
(`target = Sa*4`, no PC) — a `JMP #label(x)` that the assembler resolves
PC-relative (as it does for BRA) faults with ILLEGAL_ADDRESS because JMP
treats the field as a tiny ABSOLUTE address.  Gotcha for the hand assembler:
**JMP targets must be absolute; the label mechanism (next_pc-relative) is only
valid for BRA**.  The uniform forms encode with the explicit cond modifier:
`JMP.DIV UR4, 0x490` / `JMP.CONV UR4, 0x490` (COND_DIV_CONV_jmp: DIV=2,
CONV=3, no default) and `JMP.U UP0, ...` (UONLY: U=1).
