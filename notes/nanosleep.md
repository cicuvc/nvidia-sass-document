# NANOSLEEP — Timed warp back-off sleep (`__nanosleep`)

**Opcode mnemonics:** `NANOSLEEP` — `0x95d` (imm / `.CLEAR`) / `0x35d` (reg) / `0xb5d` (const) / `0x1b5d` (constX) / `0x1d5d` (uniform) | **Pipe:** `cbu_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`

Suspends the issuing warp for approximately **N nanoseconds** — the **timed cousin of
`YIELD`**. Where `YIELD` gives up one scheduling turn, `NANOSLEEP` backs off for a duration,
the classic exponential-backoff primitive for spin/poll loops (`__nanosleep(ns)`).

## Semantics
`@Pg NANOSLEEP[.RAND][.WARP][.SYNCS] <duration>` deschedules the warp for ~`duration`
nanoseconds (a hint; hardware rounds/caps it). The duration source names the variant:
immediate, register, constant-bank, or uniform register.
- **`.RAND`** — randomize/jitter the sleep (avoid thundering-herd on shared resources).
- **`.WARP`** (OPTIONAL_WARP) / **`.SYNCS`** (SYNCS_MOD) — warp/sync-scope modifiers.
- **`NANOSLEEP.CLEAR`** (the `_clear_` form, `clear` bit [83]) — cancels a pending sleep;
  takes no duration.

## Variant overview (6 CLASSes)
| opcode `{b91,[11:0]}` | CLASS | duration |
|-----------------------|-------|----------|
| 0x095d | `nanosleep__I` | imm `Sb`[63:32] (ns) |
| 0x095d | `nanosleep_clear_` | none (`.CLEAR`, clear bit [83]) |
| 0x035d | `nanosleep__R` | reg `Rb`[39:32] |
| 0x0b5d / 0x1b5d | `__C` / `__CX` | constant bank |
| 0x1d5d | `__U` | uniform reg `[39:32]` |

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | selects duration source |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | predicate operand (printed if ≠ PT) |
| [86] | `rand` | → `.RAND` |
| [85] | `warp` | → `.WARP` (OPTIONAL_WARP) |
| [84] | `syncs` | → `.SYNCS` (SYNCS_MOD) |
| [83] | `clear` | → `.CLEAR` (imm opcode only) |
| [63:32] | `Sb` | imm duration (ns) |
| [39:32] | `Rb` | reg/ureg duration |

Modifier print order: `NANOSLEEP{.RAND}{.WARP}{.SYNCS}`.

## Cross-comparison (the back-off / wait primitives)
| | **NANOSLEEP** | YIELD | BSYNC | BAR.SYNC |
|--|---------------|-------|-------|----------|
| effect | sleep ~N ns | yield one turn | wait for barrier reg participants | wait for CTA barrier |
| timed? | **yes** | no | no | no |
| operand | duration | — | `Bi` | baridx, count |
| pipe | cbu | cbu | cbu | mio |

All three cbu ops (`NANOSLEEP`/`YIELD`/`BSYNC`) express "I'm waiting"; NANOSLEEP is the only
*timed* one and pairs with a spin loop the same way YIELD does (see `yield.md`).

## Latency
`cbu_pipe` = `BRU_OPS`; `DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`. Both an **`RPC_WRITERS`**
member (9-cycle RPC true-dependency, `sm_90_latencies.txt:411`) and in
**`CBU_OPS_WITH_REQ`** (line 219, honors `&req=`).

## Verified encodings (decoder: `tools/decode_nanosleep.py`)
Self-test 7/7; `tests/nanosleep_test.cu` (`__nanosleep`) 3/3 (imm + reg). `.RAND`/`.WARP`/
`.SYNCS`/`.CLEAR` modifiers via cubin-patch.

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| 0x000000640000795d | 0x000fea0003800000 | `NANOSLEEP 0x64` | `__nanosleep(100)` |
| 0x000000200000795d | 0x000fea0003800000 | `NANOSLEEP 0x20` | `__nanosleep(32)` |
| 0x000000040000735d | 0x004fea0003800000 | `NANOSLEEP R4` | `__nanosleep(ns)` |
| 0x000000640000795d | 0x000fea0003c00000 | `NANOSLEEP.RAND 0x64` | patch |
| 0x000000640000795d | 0x000fea0003880000 | `NANOSLEEP.CLEAR` | patch |

Hand-check `NANOSLEEP 0x64`: opcode 0x95d (imm), `Sb`[63:32]=0x64 → `0x64` (100 ns).

### PTX→SASS mapping
`__nanosleep(imm)` → `NANOSLEEP 0x<ns>`; `__nanosleep(reg)` → `NANOSLEEP R<n>`. Typically
placed at the top of a spin/poll loop body (like YIELD, but with an escalating delay).

## Open questions
- Exact meaning of `.WARP`/`.SYNCS` modifiers and the hardware duration rounding/cap are not
  spec-stated.
- `.CLEAR` semantics (which pending sleep it cancels, and how it is emitted from C) is
  unverified — only the encoding/rendering is confirmed via patch.
