# Control codes — the per-instruction scheduling/control word (sm_90)

**Question:** how are the "control codes" (wait mask, read/write scoreboards, PM
predicate, micro-scheduler info, and operand **reuse** flags) encoded in the
128-bit sm_90 word, and where do reuse flags actually live?
**Status:** resolved (spec-grounded + empirically confirmed in cublas sm_90 SASS).

Every compute CLASS carries the same trailing control block in its `FORMAT`,
written as `$(...)$` scheduling groups:

```
$( { '&' REQ:req '=' BITSET(6/0x0000):req_bit_set } )$
$( { '&' RD:rd  '=' UImm(3/0x7):src_rel_sb } )$     # only if class has read deps
$( { '&' WR:wr  '=' UImm(3/0x7):dst_wr_sb } )$      # only if class has a dest
$( { '?' USCHED_INFO("DRAIN"):usched_info } )$
$( { '?' BATCH_T("NOP"):batch_t } )$
$( { '?' PM_PRED("PMN"):pm_pred } )$
```

## Field map (128-bit, MSB-left)

| Field | Bits | Width | Source / encoder | Meaning |
|-------|------|------:|------------------|---------|
| `req_bit_set` | [121:116] | 6 | `BITSET(6)` | **wait barrier mask** — 1 bit per scoreboard (SB0..SB5); wait on those before issue |
| `src_rel_sb`  | [115:113] | 3 | `VarLatOperandEnc` | **read barrier** — scoreboard index the src operands release; `7`=none |
| `dst_wr_sb`   | [112:110] | 3 | `VarLatOperandEnc` | **write barrier** — scoreboard index the dest releases; `7`=none |
| `pm_pred`     | [103:102] | 2 | `PM_PRED` | perf-monitor predicate: `PMN`=0, `PM1..PM3`=1..3 |
| `opex`        | [124:122] ∥ [109:105] | 8 | `TABLES_opex_N(...)` | overloaded scheduling word (below) |

`VarLatOperandEnc` is identity for 0..7 (`0xffff`→7), so the barrier fields are
just the raw scoreboard index, `7` = "no barrier".

Note the gap: bits [125], [104], and [101:92] are not part of this block for a
given class (opcode occupies bit [91] and [11:0]).

## The `opex` field and its overload with reuse flags

`opex` = `BITS_8_124_122_109_105_opex`, i.e. an 8-bit value split into two
disjoint spans (MSB-first):

```
opex[7:5] = bits[124:122]     # high 3 bits
opex[4:0] = bits[109:105]     # low 5 bits
```

It is packed by a `TABLES_opex_N(...)` lookup that also doubles as the legality
whitelist (`DEFINED TABLES_opex_N(...)` in CONDITIONS fires
`ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR "Invalid combination..."` when the tuple
is absent). The base packing is:

```
opex = (batch_t << 5) | usched_info
```

- `usched_info` (5 bits, `USCHED_INFO` enum) → bits **[109:105]**
  - `0` = `OFF_DECK_DRAIN`/`DRAIN`
  - `1..15` = `W1EG..W15EG` (`WAITn_END_GROUP`)
  - `16` unused
  - `17..27` = `W1..W11` (aka `trans1..trans11`) — note `opex[4]` set
- `batch_t` (3 bits, `BATCH_T` enum) → bits **[124:122]**
  - `0`=NOP, `1`=BATCH_START, `2`=BATCH_START_TILE, `4`=BATCH_END, `5`=BARRIER_EXEMPT
  - `3` is not a valid enum value (rejected by opex_1)

### Reuse flags reuse the same [124:122] bits (Volta lore is correct)

Classes with reuse-able register sources add `{/REUSE("noreuse"):reuse_src_x}`
modifiers and select an `opex` table that packs those flags **into the high 3
bits** [124:122] — the very bits that hold `batch_t` when there is no reuse:

| instr bit | opex bit | flag |
|-----------|---------:|------|
| **122** | opex[5] (+32)  | `reuse_src_a` (`.reuse` on Ra) |
| **123** | opex[6] (+64)  | `reuse_src_b` (`.reuse` on Rb) |
| **124** | opex[7] (+128) | `reuse_src_c` (`.reuse` on Rc) |

So `[124:122] = {reuseC, reuseB, reuseA}` — matching the classic Volta reverse
engineering. In the nvdisasm model this field is **overloaded**: it is `batch_t`
in the no-reuse scheduling context and the reuse bitfield in the reuse context.

(The `FUNIT uC` masks `OEReuseA/B/C` at internal indices 81/82/83 are the
assembler's control-word representation, **not** the final encoding — trust the
`opex`/ENCODING bit positions.)

### opex table variants (whitelist + packer)

| Table | Inputs | Used by |
|-------|--------|---------|
| `TABLES_opex_0` | (batch_t, usched_info) | classes with no reuse operand |
| `TABLES_opex_1` | same, but batch_t≠3 forbidden | special control ops (e.g. ACQBULK) |
| `TABLES_opex_2` | + reuse_src_a | single-source reuse |
| `TABLES_opex_3` | + reuse_src_a, reuse_src_c | Ra/Rc reuse |
| `TABLES_opex_5` | + reuse_src_a, reuse_src_b | Ra/Rb reuse |
| `TABLES_opex_4` | + reuse_src_a, reuse_src_b, reuse_src_c | 3-source reuse (FFMA/IMAD RRR) |

### Mutual-exclusion constraint (why the overload is safe)

Because reuse flags and `batch_t` share [124:122], the spec gates reuse on the
scheduling context:

```
(reuse_* == 1) -> usched_info ∈ {17..27}
  "?DRAIN and ?WAITn_END_GROUP tokens are not allowed with .reuse"
```

When reuse is set, `usched_info` must be a `transN` value (17..27, `opex[4]=1`)
and the opex tables only admit `batch_t == 0` in those rows — freeing [124:122]
to carry reuse. Also `usched_info == 0` (DRAIN) is only legal with `batch_t == 0`
(no batch marker on a drain).

## Verified encodings (cublas sm_90; hi64 = 2nd `/*…*/`)

Reuse bits sit in [124:122] ⊂ hi64. Decoded fields:

| Disassembly | Lo64 / Hi64 | reuse[124:122] | usched | sb (rd/wr) |
|-------------|-------------|:--------------:|:------:|:----------:|
| `IMAD R28, R27.reuse, 0x41, R2`       | `1b1c7824` / `040fe400078e0202` | `001` (A) | 18 | 7/7 |
| `IMAD R17, R0.reuse, R25, R3.reuse`   | `00117224` / `140fe400078e0203` | `101` (A+C) | 18 | 7/7 |
| `IMAD R16, R3, 0x41, R2.reuse`        | `03107824` / `100fe200078e0202` | `100` (C) | 17 | 7/7 |

All three carry `usched_info ∈ {17,18}` (transN), consistent with the reuse
constraint; barriers are 7 (none).

## BATCH_T semantics — empirical survey

The spec only defines the enum; `batch_t` is never referenced in any CONDITION,
PROPERTY, or latency rule. It is carried by **every** class (via one of the
`opex` tables), so it is universally encodable, but the meaning must be inferred.

`BATCH_T "NOP"=0, "BATCH_START"=1, "BATCH_START_TILE"=2, "BATCH_END"=4, "BARRIER_EXEMPT"=5;`
(value **3 has no name** — encodable only through `opex_0`, rejected by `opex_1`).

The names suggest an instruction-grouping / batch-issue scheduling hint
(START/START_TILE open a batch, END closes it, BARRIER_EXEMPT opts an
instruction out of the batch barrier accounting).

### What ptxas actually emits

Scanning ~27M sm_90 instructions across NVIDIA libraries (`.reuse`-free instrs,
so `[124:122]` = batch_t directly):

| library | instrs parsed | non-zero batch_t seen |
|---------|--------------:|-----------------------|
| libcublas    | 2.76M  | 6 × `DEPBAR` batch_t=5 |
| libcublasLt  | 16.99M | 201 × `DEPBAR` batch_t=5 |
| libcusolver  | 2.61M  | 6 × `DEPBAR` batch_t=5 |
| libcusparse  | 5.27M  | none |
| libcufft     | (no sm_90 code) | — |

**Conclusion:** `batch_t` is `NOP(0)` for essentially all instructions. The
*only* non-zero value observed is `5 = BARRIER_EXEMPT`, and it appears
*exclusively on `DEPBAR.LE`* (always with a `WAITn_END_GROUP` usched, e.g.
`DEPBAR.LE SB5, 0x2` @ usched=11). `BATCH_START(1)`, `BATCH_START_TILE(2)` and
`BATCH_END(4)` were **never emitted** by ptxas in any of these workloads.

DEPBAR is itself a legacy variable-latency scoreboard-drain instruction (the
Hopper model normally uses the [121:116] wait-mask instead); tagging it
`BARRIER_EXEMPT` plausibly excludes that drain from the batch/issue barrier
bookkeeping. The START/TILE/END markers appear to be a latent hardware
scheduling capability the compiler does not use for these libraries.

## Cross-arch: sm_75 (Turing) / sm_80 (Ampere) vs sm_90 (Hopper)

`sm_80_instructions.txt` (A100) is structurally the **same as sm_75**: identical
`opex` packing at [124:122]∥[109:105] (`opex_0..opex_9` tables, full reuse-combo
set), same wait-mask/scoreboard fields, and **no `pm_pred`** ([104:102] unused).
`pm_pred` [103:102] remains an sm_90-only addition.

Comparing `sm_75_instructions.txt` against `sm_90_instructions.txt`, the control
word is **almost identical** — Turing already uses the unified `opex`
(`BITS_8_124_122_109_105_opex = TABLES_opex_N(...)`) at the *same* bit positions,
the same `req_bit_set` [121:116] / `src_rel_sb` [115:113] / `dst_wr_sb` [112:110],
and the same `usched_info`/`batch_t`/`reuse` semantics. Differences:

| aspect | sm_75 | sm_90 |
|--------|-------|-------|
| `pm_pred` [103:102] | **absent** (bits [104:102] unused) | present (perf-monitor predicate) — an sm_90 addition |
| reuse-source opex tables | `opex_0..opex_10` — **all 7** reuse-source combos: {a},{b},{c},{ab},{ac},{bc},{abc} | `opex_0..opex_5` — only combos **containing** reuse_src_a: {a},{ab},{ac},{abc} |
| reuse→bit mapping | a→122, b→123, c→124 (identical) | a→122, b→123, c→124 |
| `batch_t` enum | identical (NOP/START/START_TILE/END/BARRIER_EXEMPT) | identical |

So the "other usage on sm_75" is the richer reuse-table set: Turing has
standalone `reuse_src_b` (`opex_2`) and `reuse_src_c` (`opex_8`) tables for
classes whose only reusable register sits in the B or C slot, whereas on sm_90
every reuse-capable class always exposes reuse on the A slot. The reuse *bit
positions* [124:122] are unchanged. `pm_pred` is the only new field at sm_90.

(NB: earlier Maxwell/Pascal had a separate `stall`+`yield` control word; by
Volta/Turing it is already the unified 5-bit `usched_info`, not two fields.)

### Empirical batch_t on sm_75
Scanning sm_75 SASS (`.reuse`-free instrs → [124:122] = batch_t):

### Empirical batch_t survey (all arches)

Scanning SASS (`.reuse`-free instrs → [124:122] = batch_t):

| arch / library | instrs | non-zero batch_t |
|---|---|---|
| sm_75/libcublas    | 2.41M | none |
| sm_75/libcusolver  | 2.23M | none |
| sm_80/libcublas    | 2.54M | none |
| sm_80/libcusolver  | 2.45M | none |
| sm_90/libcublas    | 2.76M | 6 × `DEPBAR` batch_t=5 |
| sm_90/libcublasLt  | 16.99M | 201 × `DEPBAR` batch_t=5 |
| sm_90/libcusolver  | 2.61M | 6 × `DEPBAR` batch_t=5 |
| sm_90/libcusparse  | 5.27M | none |

**Conclusion for dual-issue:** Across ~37M instructions spanning Turing (sm_75),
Ampere (sm_80), and Hopper (sm_90), ptxas has **never** emitted
`BATCH_START(1)` / `BATCH_START_TILE(2)` / `BATCH_END(4)`. The only non-zero
batch_t is `BARRIER_EXEMPT(5)` on DEPBAR, and only on sm_90. If A100
dual-issue is real, the compiler does not express it as batch_t grouping — the
opposite of the claim that "dual-issue is in the instruction, not the
scheduler."

## Reconciliation with external "scheduling-control word" notes

An external (unverified) writeup was checked against these two source dumps:

- **CORRECT:** `opex = (batch_t<<5) | usched_info`; wait mask [121:116];
  read/write scoreboards [115:113]/[112:110] (7=none); reuse mutually exclusive
  with `?DRAIN`/`?WAITn_END_GROUP`; `pm_pred` is sm_90+.
- **WRONG — opex width/span:** it claims opex is *9 bits* over
  `[105:109]+[122:125]`. It is **8 bits** over [109:105]∥[124:122]; **bit 125 is
  reserved**, and `[127:125]` are *all* reserved (no `BITS_` field touches them),
  not just [127:126].
- **WRONG — "layout identical on all arches":** true only for the shared fields;
  `pm_pred` [103:102] exists on sm_90 but not sm_75, and the opex reuse-table set
  differs.
- **OVER-STATED — "batch or stall, not both":** `TABLES_opex_0` (the majority of
  non-reuse classes) freely allows `batch_t ∈ 1..5` together with a stall
  (`usched_info` 1..27). The batch⊕stall restriction only appears in the
  reuse-carrying tables (and `opex_1`), and its real cause is the [124:122]
  bit-overload with reuse, not a hardware "batch xor stall" rule.
- **MISLEADING — "OEReuseA/B/C at bits 46/45/44":** those are column indices in
  the internal `FUNIT` OE mask view (→ instruction bits 81/82/83), *not* the
  final encoding. The real reuse bits are **[124:122]** (verified by decode).
  sm_75 additionally carries `OEReuseA_70/B_70/C_70` (a legacy sm_70 OE view).
- **UNSUPPORTED — dual-issue via batch_t:** across ~34M sm_75+sm_90 instructions
  ptxas never emits `BATCH_START/START_TILE/END`. If co-issue is real, the
  compiler does not express it here.

## Open questions
- ~~Exact runtime semantics of `WAITn_END_GROUP` vs `transN`~~ — **resolved** in
  `usched_latency.md`: `eff_stall = usched&0xF` is the issue-to-issue gap
  derived from the `sm_90_latencies.txt` `TABLE_TRUE` matrices; `bit4` is the
  end-group/yield selector (`transN`/bit4=1 = independent successor, keep
  issuing; `WnEG`/bit4=0 + `DRAIN` = dependency stall / group boundary / yield).
- Whether `req_bit_set` bit ordering (SB0 = LSB [116]) is confirmed against a
  producer/consumer pair with a set wait mask (samples above all have mask=0).
- Runtime effect of `BATCH_START/BATCH_START_TILE/BATCH_END` — never emitted by
  ptxas in surveyed libraries, so semantics remain inferred from the names only.
- Why `batch_t=3` is encodable (via `opex_0`) yet has no enum name.
