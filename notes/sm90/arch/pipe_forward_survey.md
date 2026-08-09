# Pipe-to-pipe forwarding survey on SM120 (excluding fma64)

Comprehensive map of which inter-pipe register-forwarding edges exist on
sm120 (RTX 5090 / GB202) and how fast each one is, **excluding every
instruction in the fma64 pipe** (`fma64lite`/`fma64heavy`: DFMA/DADD/DMUL/
conversions).  Method: the stale/fresh boundary sweep from `pipe_forwarding.md`
(applied to GPR, uniform-register and predicate domains) plus static
enumeration from `sm120.json` and the `TABLE_TRUE` matrices.

Reproduce: `python3 tests/asm_construct/test_*_forward.py`.

## Pipes in scope and what each can write/read

| pipe | writes | reads (as consumer) |
|---|---|---|
| int_pipe (FXU) | GPR, predicates | GPR, UR (RUR/RRU), predicates |
| fmalighter_pipe (FMAI/IMAD) | GPR, predicates | GPR, UR (RUR/RRU), predicates |
| fp16_pipe | GPR, predicates | GPR, UR, predicates |
| mio_pipe | GPR (LDG/LDS/ATOMS/RED/MUFU) | GPR (AGU addr, data, MUFU src), UR (desc, UR-offset addr) |
| cbu_pipe | GPR (BMOV), barrier regs | GPR (NANOSLEEP/JMX/BRX/RET late), predicates (branches), UR (BRXU/JMXU) |
| udp_pipe | **UR**, uniform predicates | UR (its own ALU) |
| fe_pipe | **nothing** (NOP/DEPBAR/PMTRIG/STP/VOTE_VTG/CSMTEST) | UR (DEPBAR count), scoreboards |

Consequences: udp is a UR-domain producer only (no GPR writes); fe is a
consumer only (no data writes); the int→udp GPR path goes through the
cross-lane `R2UR`.

## Measured matrix (27 edges, all deterministic; spec = sm120 TABLE_TRUE)

### GPR domain (producer writes R, consumer reads R)

| producer → consumer | spec | minG | class |
|---|---|--:|---|
| int → int (`IADD3`→`IADD3`) | 6 | **2** | fast |
| fmal → fmal (`FADD`→`FADD`) | 4 | **2** | fast |
| fp16 → fp16 (`HADD2`→`HADD2`) | 5 | **2** | fast |
| int → fmal (`IADD3`→`FADD`) | 6 | **3** | fast |
| fmal → int (`FADD`→`IADD3`) | 5 | **3** | fast |
| int → fp16 (`IADD3`→`HADD2`) | 6 | **2** | fast |
| fmal → fp16 (`FADD`→`HADD2`) | 6 | **2** | fast |
| fp16 → int (`HADD2`→`IADD3`) | 5 | **2** | fast |
| fp16 → fmal (`HADD2`→`FADD`) | 5 | **2** | fast |
| int → mio (LDG addr/AGU) | 6 | **1** | late-read |
| fmal → mio (LDG addr/AGU) | 6 | **1** | late-read |
| fp16 → mio (MUFU src) | 6 | **2** | fast |
| int → cbu (`NANOSLEEP` reg) | 6 | **1** | late-read |
| fp16 → cbu (`NANOSLEEP` reg) | 6 | **1** | late-read |
| cbu → int (`BMOV`→`IADD3`) | 2* | **6** | cbu-producer |
| cbu → mio (`BMOV`→`STG` data) | 2* | **1** | late-read |
| mio → int (`MUFU.RCP`→`IADD3`) | 2* | **8** | scoreboard |
| mio → fmal (`MUFU.RCP`→`FADD`) | 2* | **8** | scoreboard |
| mio → fp16 (`MUFU.RCP`→`HADD2`) | 2* | **8** | scoreboard |

(* = the `MIO_CBU_OPS → ALL_OPS = 2` catch-all row, which is wrong for these.)

### UR domain (producer writes UR, consumer reads UR)

| producer → consumer | spec | minG | class |
|---|---|--:|---|
| udp → udp (`UIADD3`→`UIADD3`) | 4 | **2** | fast |
| udp → int (`UIADD3`→`MOV`/`IADD3.RUR`) | 12 | **3** | fast |
| udp → fmal (`UIADD3`→`FFMA.RRU`) | 12 | **3** | fast |
| udp → fe (`UMOV`→`DEPBAR.LE` UR count) | 10 | **2** | fast |
| udp → mio (`UIADD3`→`LDG [R+UR+imm]`) | 12 | **4** | UR-offset (slower than GPR base) |

### Predicate domain (producer writes P, cbu branch reads it)

| producer → consumer | spec | minG | class |
|---|---|--:|---|
| int → cbu (`ISETP`→`@P0 BRA`) | 13 | **7 fine / 12–13 coarse** | slow predicate |
| fp16 → cbu (`HSETP2`→`@P0 BRA`) | 13 | **7 fine / 12 coarse** | slow predicate |
| int → int (predicated `@P0 IADD3`) | 5 | not swept | (see open Q) |

## Forwarding taxonomy (6 classes)

1. **Fast fixed-forwarding — minG 1–3.** Every fixed-latency producer (int,
   fmal, fp16, udp-ALU) delivers to every fixed-latency consumer (int, fmal,
   fp16, udp) within 2–3 cycles regardless of pipe pair.  The spec's
   `TABLE_TRUE` values (4–12) are 2–6× conservative upper bounds.
2. **Late-read absorbed — minG 1.** Consumers that read their operand late in
   the pipeline (AGU address, `NANOSLEEP`, `STG` data) see the write at the
   minimum schedulable gap; the producer's latency is hidden.
3. **UR-offset path — minG 4.** A UDP-written UR used as an *address offset*
   (`LDG [R + UR + imm]`) is 2–3× slower than a GPR address base (minG 4 vs 1).
4. **Scoreboard class — minG 8.** Variable-latency mio producers (`MUFU`,
   `LDG`, `ATOMS`) do **not** fast-forward to int/fmal/fp16.  A pure stall gap
   needs ≥8 cycles; real code must `req` the producer's scoreboard.  The spec
   catch-all `MIO_CBU_OPS→ALL_OPS=2` is too optimistic.
5. **cbu producer — minG 6.** `BMOV` (reads barrier state, variable-ish) →
   int needs ~6 cycles; not fast.  (`BMOV`→STG data is absorbed → 1.)
6. **Slow predicate — 7 fine / 12–13 coarse.** Predicate producers
   (`ISETP`/`HSETP2`) → a branch's predicate read has **no fast bypass**: the
   spec 13 is exact in coarse scheduling, and fine-grain stall-1 fillers only
   open a fragile alignment window at S=3 that doesn't hold.
7. **Cross-lane (inferred) — ~40 cyc.** `int/fmal/fp16 → udp` goes through
   `R2UR` (cross-lane broadcast), which needs the ~8×`UMOV` settle seen in
   `test_r2ur.py` (~40 cycles).

## Not-constructible edges

- **fe → \*** — fe_pipe writes no register (NOP/DEPBAR/PMTRIG/STP/VOTE_VTG/CSMTEST).
  (LEPC/RPCMOV/MOV64IUR are int_pipe-classified, not fe.)
- **udp → GPR** — udp writes no GPR (UR2UP writes a uniform predicate; R2UR
  writes UR).  udp→* is always UR-domain.
- **int → fe (GPR)** — DEPBAR reads scoreboards/UR, not GPR.
- **fma64 → \*** / **\* → fma64** — excluded by scope (fma64 pipe).

## Spec-vs-measured summary

| direction | spec | measured | verdict |
|---|---|---|---|
| fixed→fixed (int/fmal/fp16/udp) | 4–12 | 2–3 | spec 2–6× conservative |
| → AGU / NANOSLEEP / STG | 6 | 1 | spec conservative (late-read) |
| udp → mio (UR offset) | 12 | 4 | spec conservative |
| mio → int/fmal/fp16 | 2 | 8 | **spec too optimistic** (scoreboard needed) |
| cbu(BMOV) → int | 2 | 6 | **spec too optimistic** |
| predicate → branch | 13 | 12–13 | **spec exact** (coarse) |

## Inferred edges (not measured; classified by the taxonomy)

| edge | class |
|---|---|
| int/fmal/fp16 → udp (R2UR) | cross-lane ~40 cyc |
| mio → cbu (NANOSLEEP reading a mio result) | scoreboard ~8+ |
| udp → cbu (BRXU/JMXU via UR) | UR domain, likely fast |
| int → mio (STG data, vs the measured LDG addr) | late-read ~1 |
| fmal/fp16 → mio (STG data) | late-read ~1 |
| any → fe (DEPBAR with an int-produced... not constructible) | n/a |

## Open questions

- The `[R + UR + imm]` address form's extra latency (udp→mio 4 vs int/fmal→mio
  1): is it the UR-offset operand-collect or the AGU's uniform-add path?
- Predicate consumers other than branches (predicated `IADD3`/`LDG`): the PRED
  table says int→int-predicated = 5; not swept here.
- Whether the cbu→int `minG=6` is the BMOV barrier-state read or a cbu-write
  path artifact (a second cbu GPR writer would separate them).
- Exact `R2UR` cross-lane latency (documented ~40 cyc from the settle pad, not
  swept with the boundary method).

## Cross-notes

- `pipe_forwarding.md` — method, the udp/int/fmal/cbu/mio edge details, DRAIN
  and issue-floor gotchas.
- `subcore_scheduler.md` — the i%4 subcore mapping and yield-bit mechanism
  behind the "same pipe, no hazard" claims.
- `usched_latency.md` — how ptxas computes stall counts from the same tables.
