# WARPSYNC — Warp-lane reconvergence / synchronization (`__syncwarp`)

**Opcode mnemonics:** imm/full-mask `WARPSYNC` = `0b100101001000` = **0x948**; reg-mask = **0x348** | **Pipe:** `cbu_pipe` (Branch / Convergence-Barrier Unit) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

The SASS realization of `__syncwarp(mask)` and the warp-level piece of cooperative-groups /
cluster collectives: it forces a named set of lanes in the warp to **reconverge** (reach the
same PC) before continuing. Unlike `BSYNC` (which reconverges the participants of a
structured convergence *barrier register* `Bi` created by `BSSY`), WARPSYNC synchronizes an
**arbitrary programmer-specified lane mask**.

## Semantics
`@Pg WARPSYNC{mode} {Pp,} {mask} {, target}` blocks each participating lane until all lanes
in the mask have arrived, then reconverges them.
- **mask source:** imm form (0x948) = **full mask** (all lanes, `.ALL`); reg form (0x348) =
  mask from GPR `Ra` (`Ra` = `__syncwarp`'s 32-bit membermask).
- **mode** = `cop` [86:85]: `0` plain / `.ALL`, `1` `.EXCLUSIVE`, `2` `.COLLECTIVE`.
- **COLLECTIVE** additionally carries a **PC-relative target** (`sImm`, SCALE 4) and opens a
  region closed by `ENDCOLLECTIVE` (see "Mode semantics — experimental findings" below).

## Variant overview (6 CLASSes / 2 opcodes / `cop` mode)
| opcode | cop | render | operands |
|--------|-----|--------|----------|
| 0x948 (imm) | 0 | `WARPSYNC.ALL` | — (full mask) |
| 0x948 (imm) | 2 | `WARPSYNC.COLLECTIVE.ALL 0x<target>` | target |
| 0x948 (imm) | 1 | *(invalid → `.???1`)* | — |
| 0x348 (reg) | 0 | `WARPSYNC R<Ra>` | mask reg |
| 0x348 (reg) | 1 | `WARPSYNC.EXCLUSIVE R<Ra>` | mask reg |
| 0x348 (reg) | 2 | `WARPSYNC.COLLECTIVE R<Ra>, 0x<target>` | mask reg + target |

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x948 imm(full-mask) / 0x348 reg-mask |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | predicate operand (printed if ≠ PT) |
| [86:85] | `cop` | mode: 0=ALL/plain, 1=EXCLUSIVE, 2=COLLECTIVE |
| [31:24] | `Ra` | lane-mask register (reg forms) |
| [81:34]∥[23:16] | `sImm` | COLLECTIVE target = `PC+0x10 + sImm*4` (PC-relative) |

`ALLOnly`={ALL=0}, `DIV__EXCLUSIVE`={–,EXCLUSIVE=1}, `COLLECTIVEONLY`={COLLECTIVE=2}.

## Cross-comparison (vs BSYNC)
| | **WARPSYNC** | BSYNC |
|--|--------------|-------|
| what it syncs | an arbitrary **lane mask** (imm-all or GPR) | participants of a **barrier reg `Bi`** |
| paired with | `__syncwarp` / cooperative-groups; COLLECTIVE with `BSSY` | `BSSY Bi` |
| target operand | COLLECTIVE only (PC-rel) | none |
| use | programmer warp sync, collectives | structured if/else/loop reconvergence |

Both reconverge lanes, both `RPC_WRITERS`; WARPSYNC is the *explicit / mask-driven* warp
sync, BSYNC the *structural* one from compiler-inserted barriers.

## Latency
`cbu_pipe` = `BRU_OPS`. `RPC_WRITERS` → **9-cycle** RPC true-dependency
(`sm_90_latencies.txt:411,414`) and in `CBU_OPS_WITH_REQ` (line 219, honors `&req=`).
`DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_warpsync.py`)
Self-test 6/6; **59448/59448 WARPSYNC in libcusparse decoded byte-exact** (both `.ALL` and
`.COLLECTIVE Rn, target`). Reg/EXCLUSIVE/COLLECTIVE.ALL forms via cubin-patch.

| PC | Lo64 | Hi64 | Disassembly | src |
|----|------|------|-------------|-----|
| 0x16c0 | 0x0000000000007948 | 0x000fea0003800000 | `WARPSYNC.ALL` | libcusparse |
| 0x18b0 | 0x0000000006087348 | 0x022fea0003c00000 | `WARPSYNC.COLLECTIVE R6, 0x18e0` | libcusparse |
| 0x00e0 | 0x0000000004087948 | 0x000fea0003c00000 | `WARPSYNC.COLLECTIVE.ALL 0x110` | patch |
| 0x00e0 | 0x0000000004087348 | 0x000fea0003a00000 | `WARPSYNC.EXCLUSIVE R4` | patch |
| 0x00e0 | 0x0000000004087348 | 0x000fea0003c00000 | `WARPSYNC.COLLECTIVE R4, 0x110` | patch |

Hand-check `WARPSYNC.COLLECTIVE R6, 0x18e0`@0x18b0: opcode 0x348; `cop`[86:85]=2→COLLECTIVE;
`Ra`[31:24]=6→R6; `sImm=0x08`, `0x18c0 + 0x08*4 = 0x18e0`. ✓ Real context:
```
        BSSY  B1, 0x18f0
        WARPSYNC.COLLECTIVE R6, 0x18e0      ; collective sync, continue at 0x18e0
        ...
0x18f0: BRA   0x1060
```

### PTX→SASS mapping
`__syncwarp()` → `WARPSYNC.ALL`; `__syncwarp(mask)` → `WARPSYNC R<mask>`. Cooperative-groups
/ cluster collective barriers → `WARPSYNC.COLLECTIVE Rn, <target>`. Note: at `-O3` a
`__syncwarp()` that the compiler proves redundant (e.g. subsumed by a `SHFL.*.SYNC`) is
elided — WARPSYNC is emitted only where a real warp reconvergence is needed.

## Mode semantics — experimental findings

Two speculations were tested and **corrected by experiment**:

### `.COLLECTIVE` = a compiler-inserted collective-region marker (not `cluster.sync()`)
- `cluster.sync()` / `grid.sync()` / `thread_block.sync()` lower to the **`BAR*`** family,
  and cg `reduce`/`scan` to plain `WARPSYNC`/`REDUX` — **none** emit `.COLLECTIVE`.
- What actually emits it: an **exact 1:1 pairing with `ENDCOLLECTIVE`** (libcusparse:
  57894 `WARPSYNC.COLLECTIVE` ↔ 57894 `ENDCOLLECTIVE`), always the fixed idiom at a
  **post-divergence join right after `EXIT`**, inside `BSSY`/`BSYNC` brackets:
  ```
        EXIT
        BSSY  B1, JOIN
        WARPSYNC.COLLECTIVE Rmask, TGT   ; open region; Rmask = surviving-lane membermask
        NOP                              ; (empty body)
        ENDCOLLECTIVE                    ; close;  TGT = this insn's successor
  TGT:  BSYNC B1
  JOIN: BRA ...
  ```
- Interpretation (evidence-grounded): `.COLLECTIVE` **opens a bracketed region that declares
  the participating lane-set (`Rmask`)** and sets the per-warp `MCOLLECTIVE` state; the
  `target` is the region end (successor of `ENDCOLLECTIVE`). It is a **convergence/correctness
  marker for warp collectives across lane exits**, not a cluster barrier.
- **Trigger (found):** compiling with **`-G`** (device debug) lowers a plain `__syncwarp()`
  into exactly this form — `BSSY; WARPSYNC.COLLECTIVE Rmask,TGT; NOP; ENDCOLLECTIVE; BSYNC`
  — whereas `-O3` collapses the same `__syncwarp()` to `WARPSYNC.ALL`. Confirmed: `-G` emits
  it; `-lineinfo -O3` and `-O0` (without `-G`) do not. So `.COLLECTIVE` is the compiler's
  **explicit, convergence-preserving lowering** of a warp collective, which the optimizer
  normally collapses.
- **Also emitted at `-O3`** by specific internal warp-collective primitives: cusparse's 57894
  COLLECTIVEs sit in optimized code (register `.reuse`, `MATCH.ANY`/`REDUX.OR`/`VOTEU`/
  `ST.STRONG.SYS`/`BRA.DIV` — multi-GPU/system-scope warp aggregation), so a hand-tuned
  collective forces the explicit region even when optimized. That optimized trigger is not
  reproduced by simple CUDA-C kernels here (open).

### `.EXCLUSIVE` = not emitted by ptxas (spec/HW-only)
- **0 occurrences** in libcusparse (8.9M SASS lines, 59448 WARPSYNCs). Cooperative-groups
  `coalesced_threads()` / `binary_partition` / `labeled_partition` `.sync()` all lower to
  **plain `WARPSYNC Rmask`** (cop=0), *not* `.EXCLUSIVE`. So the "partitioned sub-group sync"
  guess is **disproven**; ptxas (CUDA 13.1) never emits `.EXCLUSIVE`. Its true semantics are
  unconfirmed — only the encoding (reg-form cop=1) is known.

## Open questions
- The specific **optimized (`-O3`)** warp-collective primitive that emits
  `WARPSYNC.COLLECTIVE`/`ENDCOLLECTIVE` in cusparse (multi-GPU/system-scope, `MATCH.ANY`-based)
  — the `-G` trigger is found, but the optimized-path source construct isn't reproduced by
  simple kernels here.
- Runtime meaning of `.EXCLUSIVE` (never emitted) and of the COLLECTIVE `target` beyond
  "region successor".
- Non-PT `Pp` on WARPSYNC is unobserved.
