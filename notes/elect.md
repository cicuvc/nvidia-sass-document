# ELECT — Elect a leader lane in a warp

**Opcode mnemonics:** `ELECT` = **0x182f** (URa/mask form) / **0x082f** (predicate form) | **Pipe:** `cbu_pipe` (dispatch) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH` | **VIRTUAL_QUEUE:** None

Picks **one leader lane** out of a candidate set of lanes in the warp and reports which lane
won — the SASS realization of PTX `elect.sync` and the primitive behind `cg::invoke_one`,
warp-aggregated atomics ("one lane does the atomic"), and single-lane critical sections.

## Semantics
`@Pg ELECT[.IGNOREKILL] Pu, URd, <candidates>` elects a single leader from the candidate
lane set and writes two results:
- **`Pu`** — leader predicate: **true in exactly the elected lane**, false elsewhere.
- **`URd`** — uniform register receiving the **elected lane's id** (may be `URZ` if only the
  predicate is needed).

The candidate set comes from either a **uniform-register membermask `URa`** (`[~]URa` to
invert) or a **predicate `Pp`** (`[!]Pp`); like `elect.sync`, the lowest-numbered active
candidate lane is chosen. `.IGNOREKILL` controls whether killed lanes are considered.

## Variant overview (3 CLASSes)
| opcode `{b91,[11:0]}` | CLASS | candidate source |
|-----------------------|-------|------------------|
| 0x182f | `elect_` | `[~]URa` (uniform-reg membermask) [29:24], invert `e`[72] |
| 0x082f | `elect_Pp_` | `[!]Pp` (predicate) [89:87]/[90] |
| 0x182f | `elect_noURa_` (ALT) | none (rendered as the `elect_` form) |

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | b91=1 → URa form (0x182f), b91=0 → Pp form (0x82f) |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [85] | `ignoreKill` | 1 → `.IGNOREKILL` |
| [83:81] | `Pu` | leader output predicate |
| [21:16] | `URd` | leader-id output uniform reg (URZ=63) |
| [29:24] | `URa` | candidate membermask (URa form) |
| [72] | `e` | `~URa` invert |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | candidate predicate (Pp form) |

## The CBU-family oddity (shared with ENDCOLLECTIVE)
Like `ENDCOLLECTIVE`, ELECT dispatches through the `cbu_pipe` set but is
**`INST_TYPE_COUPLED_MATH`** with `VIRTUAL_QUEUE=None` — a fixed-latency coupled op, not a
decoupled branch. The latency file singles it out: `OP_ELECT = {ELECT}` and
`MIO_CBU_OPS_WITHOUT_ELECT = MIO_OPS + BRU_OPS − OP_ELECT` (`sm_90_latencies.txt:49,171`),
i.e. ELECT is excluded from the normal MIO/CBU latency class and handled specially. It is
neither `RPC_WRITERS` nor `CBU_OPS_WITH_REQ` (it changes no PC and doesn't block).

## Cross-comparison
- vs **VOTE/MATCH** (`mio_pipe`): those reduce/compare across lanes; ELECT specifically
  chooses **one** winner and yields its id + a one-hot predicate.
- vs **WARPSYNC**: WARPSYNC reconverges a mask; ELECT selects a leader within a mask.
- Common pairing: `ELECT` → `@Pu <leader-only work>` (e.g. `@Pu ATOMG…`), then broadcast via
  `SHFL`/uniform reg.

## Verified encodings (decoder: `tools/decode_elect.py`)
Self-test 4/4; `tests/elect_test.cu` (inline `elect.sync`) 1/1. Rare in shipped libs
(0 in libcusparse); URa-form and `.IGNOREKILL` via cubin-patch.

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| 0x00000000003f782f | 0x000fe20003800000 | `ELECT P0, URZ, PT` | `elect.sync` (Pp form, all-active) |
| 0x00000000003f782f | 0x000fe20003a00000 | `ELECT.IGNOREKILL P0, URZ, PT` | patch |
| 0x000000000506082f | 0x000fe2000b860000 | `@P0 ELECT P3, UR6, UR5` | patch (URa form) |
| 0x000000000506082f | 0x000fe2000b860100 | `@P0 ELECT P3, UR6, ~UR5` | patch (inverted mask) |

Hand-check `ELECT P3, UR6, UR5`: opcode 0x182f (b91=1); `Pu`[83:81]=3→P3; `URd`[21:16]=6→UR6;
`URa`[29:24]=5→UR5; `e`[72]=0 (no `~`).

### PTX→SASS mapping
`elect.sync membermask` → `ELECT Pu, URd, Pp`/`URa` (leader-id in `URd`, is-leader in `Pu`).
`cg::invoke_one` / warp-aggregated atomics emit an ELECT to pick the acting lane. Compilers
often discard the leader id (`URd=URZ`) when only the leader predicate is used.

## Open questions
- Whether `URd` is strictly the leader lane-id vs. an encoded leader token is inferred from
  `elect.sync` semantics, not spec-stated.
- Optimized-code emission (which C constructs beyond inline `elect.sync`/`invoke_one`) is
  under-sampled — 0 ELECT in the scanned libcusparse.
