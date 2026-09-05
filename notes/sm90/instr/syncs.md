# SYNCS — Shared-memory synchronization (mbarrier + shared uniform atomics)

**Opcode mnemonic:** `SYNCS` — 9 variants on sm_90, 10 on sm_100/sm_120
(Blackwell adds `syncs_flush_`) | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:**
decoupled scoreboard | **VIRTUAL_QUEUE:** `VQ_SYNCS_UNORDERED_WR` |
compute-only (`SHADER_TYPE==CS`)

The Hopper **shared-memory synchronization** instruction implements the state-changing
and phase-checking `mbarrier.*` PTX operations (incl. cluster-scope via distributed shared
memory), plus a set of **shared-memory uniform atomics** (exchange / CAS / load). It is a
**decoupled** op — its result (token/loaded value) is tracked by a write scoreboard, not a
fixed latency. Mechanism/semantics for the TMA + mbarrier producer→consumer flow live in
`../arch/tma_mbarrier.md`; this note is the per-opcode instruction reference.

## Variant taxonomy
| opcode `{b91,[11:0]}` | CLASS | group | role |
|-----------------------|-------|-------|------|
| **0x19a7** | `syncs_arrive_` | mbarrier | arrive / arrive.expect_tx (transaction count) |
| 0x19a7 | `syncs_tcnt_` (ALT) | mbarrier | expect_tx-only (tx count) |
| **0x15a7** | `syncs_phasechk_` | mbarrier | try_wait / test_wait phase-parity check |
| 0x19b1 | `syncs_cctl_` | mbarrier | barrier cache-control (per-addr) |
| 0x09b1 | `syncs_cctl_all_` | mbarrier | barrier cache-control (all) |
| 0x03a7 | `syncs_flush_` (sm_100+) | mbarrier | drain/flush SYNCS work; not a cache writeback |
| 0x15b1 | `syncs_ld_` | mbarrier | load barrier state (`.WATCH`) into GPR |
| **0x15b2** | `syncs_uniform_exch_` | atomic | shared **exchange** (used by `mbarrier.init`) |
| 0x13b2 | `syncs_uniform_cas_` | atomic | shared **compare-and-swap** |
| 0x19b2 | `syncs_uniform_ld_` | atomic | shared **load** (uniform) |

Opcode structure: `…a7` = mbarrier arrive/phasechk; `…b1` = barrier cctl/ld (GPR);
`…b2` = shared uniform atomics (uniform-predicate guarded, `@UPg`).

## Group A — mbarrier ops
### ARRIVE / expect_tx (`0x19a7`)
`SYNCS.ARRIVE.TRANS64[.RED|.TMASK][.<paramtype>] Rd, [addr], Rb`
- `paramtype` [86:84] `PARAMTYPE` selects the {arrive-count, tx-count} sources:
  `A1TR`(0, hidden default) / `A1T0`(1) / `A0T1`(2) / `A0TR`(3) / `A0TX`(4) / `ART0`(5)
  — `A`=arrive +1/+0, `T`=tx +1/+0/+R(reg)/+X(imm). So `mbarrier.arrive`→`A1T0`,
  `mbarrier.arrive.expect_tx`→`A1TR` (default), `mbarrier.expect_tx`→`A0TR`.
- `retval` [74:73]: `OLDSTATE`(0, hidden → pre-operation state token in `Rd`) /
  `TMASK`(1, PTX `.noComplete`) / `RED`(2, no returned state, hence `Rd=RZ`).
  Remote DSMEM operations require the sink destination and therefore use `.RED`, but
  `.RED` is not by itself a "remote reduction" marker: local `expect_tx` and
  `complete_tx` use it too.
- `optout` [75]: `.OPTOUT` is PTX `arrive_drop`; it decrements both the current
  pending-arrival count and the expected count used by later phases.
- operands: `Rd` [23:16] token dest, `Rb` [39:32] count value, addr = `[Ra + URc + off]`
  (`Ra`[31:24], `URc`[69:64], `off`[63:40]).

### PHASECHK / try_wait (`0x15a7`)
`SYNCS.PHASECHK.TRANS64[.TRYWAIT] Pu, [addr], Rb` — `wait` [72] {ONCE / `.TRYWAIT`};
sets predicate `Pu` [83:81] = "has the phase flipped?" (non-blocking; the wait is a
software spin, see `tma_mbarrier.md`).

### ARRIVE modifier semantics

All effects below are atomic with respect to one barrier operation.  "pending"
and "tx" are logical positive outstanding counts; their physical fields move
in the opposite direction because both are stored in two's complement.

| `paramtype` [86:84] | logical arrive effect | logical tx effect | PTX use |
|---|---:|---:|---|
| A1TR=0 (suffix hidden) | pending −= 1 | tx += Rb | `arrive.expect_tx` |
| A1T0=1 | pending −= 1 | none; Rb must be RZ | ordinary `arrive` |
| A0T1=2 | none | tx += 1; Rb must be RZ | fixed-one internal form |
| A0TR=3 | none | tx += Rb | `expect_tx`; also rendered as the TCNT alias |
| A0TX=4 | none | tx −= Rb | `complete_tx` / async completion |
| ART0=5 | pending −= Rb | none | counted arrive / noComplete |
| 6,7 | — | — | illegal encoding |

The orthogonal return/update modifiers are:

| modifier field | semantic effect |
|---|---|
| OLDSTATE=0 (hidden) | returns an opaque pre-operation phase token in even `Rd:R[d+1]`; the high word carries the old phase/Arrive field, but the low word is not a copy of physical backing and must remain opaque |
| `.TMASK`=1 | returns old high word plus the issuing active-lane mask in token bits [31:0]; used by `.noComplete` and `pending_count` lowering |
| `.RED`=2 | no return value and requires `Rd=RZ`; selected for standalone tx updates and remote/sink operations |
| retval=3 | illegal |
| `.OPTOUT` [75]=1 | additionally decreases Expected by the arrival amount; PTX `arrive_drop` |

With one active lane, `.TMASK.ART0 count=2` returned low word `1`; the
otherwise identical OLDSTATE token's low word was opaque.  Both produced the
same pending count.  `.TMASK.OPTOUT` changed Expected as well.  The internal
`.A0T1` form produced the exact state for one outstanding tx credit
(`0x7fffebfffffffffa` after `init(3)` and eviction).  The ISA permits
modifier combinations beyond those emitted by PTX; the table describes their
orthogonal hardware effects, subject to the explicit validity constraints
(`RED => Rd=RZ`, A1T0/A0T1 => Rb=RZ, even 64-bit destination).

`SYNCS.TCNT.TRANS64.RED [addr],Rb` is an alternate textual decode of exactly
the same bits as `SYNCS.ARRIVE.TRANS64.RED.A0TR RZ,[addr],Rb`; it is not a
separate operation.

### PHASECHK modifiers and operands

`ONCE` ([72]=0, suffix hidden) and `.TRYWAIT` ([72]=1) are both non-blocking
checks that asynchronously write `Pu`.  `.TRYWAIT` marks the first/polling
check; ptxas uses ONCE for `test_wait` and for the second check after a sleep.
For token form, Rb is the token's **high** GPR.  For parity form, ptxas shifts
the 0/1 parity operand into bit 31 before supplying it as Rb.  A PTX suspend
hint expands to:

```
SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [bar], Rstate
@!P0 NANOSLEEP.SYNCS Rhint
@!P0 SYNCS.PHASECHK.TRANS64 P0, [bar], Rstate
```

### mbarrier maintenance / observation

- `SYNCS.CCTL.IV/WB [addr]`: both write the addressed live cache entry to its
  shared backing; `.IV` also invalidates/evicts it, `.WB` retains a usable
  cache entry.  This distinction was verified by WB→LDS→ARRIVE→IV→LDS.
- `SYNCS.CCTL.IVALL/WBALL`: the same operation over all resident mbarrier
  entries.  Both forms wrote two independent entries back in real-device
  probes.  Post-IV/IVALL reuse is deliberately not used to infer cache state:
  PTX declares an invalidated object unusable until it is initialized again.
- `SYNCS.LD.64 Rd,[addr]` reads the live cache state directly, without eviction.
  `.WATCH` returns the same value and does not make subsequent barrier updates
  write through to shared backing.  Its additional monitoring side effect is
  not yet distinguished.
- `SYNCS.FLUSH` exists only in sm_100/sm_120.  It has no address, is a
  decoupled write-scoreboard operation, leaves the barrier usable, and does
  **not** write the live entry to shared (LDS retained the pre-init sentinel).
  The minimum verified distinction is that it is not cache maintenance; its
  name and scoreboard shape suggest a SYNCS queue/completion drain, but the
  precise producer set and ordering strength remain unresolved.

## Group B — shared uniform atomics (`@UPg`, `…b2`)
`SYNCS.EXCH.64 URd,[URa],URb`, `SYNCS.CAS.64 URd,[URa],URcmp,URnew`, and
`SYNCS.LD.64 URd,[URa]` are ordinary 64-bit shared-memory uniform atomics:
EXCH/CAS return the old word and LD returns the current word.  A real-device
probe exchanged `0x2222222211111111`, successfully CASed it to
`0x4444444433333333`, and observed both the returned old and final words.
All 64-bit uniform operands are explicit even-aligned pairs; CAS requires the
compare pair at a 4-register boundary and the new pair immediately after it
(`TABLES_URb_0`: `URc=URb+2`).  `@UPg` executes the operation once on the
uniform datapath.  `mbarrier.init` uses EXCH with `URd=URZ`.

## Bit layout (128-bit)

### SYNCS.ARRIVE.TRANS64 (0x19a7)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [124:122],[109:105] | opex | 8 | `TABLES_opex_0(batch_t,usched_info)` | scheduling |
| [121:116] | req_bit_set | 6 | — | scoreboard wait mask |
| [115:113] | src_rel_sb | 3 | `VarLatOperandEnc(rd)` | read scoreboard |
| [112:110] | dst_wr_sb | 3 | `VarLatOperandEnc(wr)` / `*7` (RZ) | write scoreboard |
| [103:102] | pm_pred | 2 | — | perfmon predicate |
| [91],[11:0] | opcode | 13 | 0x19a7 | |
| [86:84] | paramtype | 3 | PARAMTYPE | A1TR=0,A1T0=1,A0T1=2,A0TR=3,A0TX=4,ART0=5 |
| [75] | optout | 1 | `OPTOUT` | `arrive_drop` |
| [74:73] | retval | 2 | — | OLDSTATE=0,TMASK=1,RED=2,3 invalid |
| [72] | wait | 1 | — | ONCE=0, `.TRYWAIT`=1 (PHASECHK) |
| [69:64] | URc | 6 | UniformRegister | uniform base register |
| [63:40] | Ra_offset | 24 | SImm(24) | signed offset |
| [39:32] | Rb | 8 | Register | count value / token |
| [31:24] | Ra | 8 | Register | address register (RZ=URc-only) |
| [23:16] | Rd | 8 | Register | token destination (ARRIVE only) |
| [15] | Pg_not | 1 | Pg@not | predicate negate |
| [14:12] | Pg | 3 | Predicate | guard predicate |

### Shared uniform atomics (...b2, 128-bit)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [63:40] | Ra_offset | 24 | SImm(24) | signed offset |
| [37:32] | URb/table | 6 | UniformRegister | EXCH source; CAS compressed adjacent compare/new pairs |
| [29:24] | URa | 6 | UniformRegister | address register |
| [21:16] | URd | 6 | UniformRegister | result register (EXCH/LD) |
| [73:72] | emuop | 2 | fixed per class | LD=0, EXCH=1, CAS=2 |
| [14:12] | UPg | 3 | UniformPredicate | uniform guard predicate |

For CAS, `TABLES_URb_0(URb,URc)` encodes only the compare-pair base and
requires `URc=URb+2`; there is no independent `[69:64]` CAS operand field.

### Cache-control / state load (...b1, 128-bit)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [31:24] | Ra | 8 | Register | GPR address component |
| [69:64] | URc | 6 | UniformRegister | uniform address component |
| [63:40] | Ra_offset | 24 | SImm(24) | signed offset |
| [72] | cctlop | 1 | CCTL only | IV=0, WB=1 (ALL: IVALL=0, WBALL=1) |
| [73] | mode | 1 | class-fixed | CCTL=0, LD=1 |
| [74] | watch | 1 | LD only | normal=0, WATCH=1 |
| [23:16] | Rd | 8 | Register | LD only, even 64-bit GPR pair |

Blackwell `SYNCS.FLUSH` is opcode 0x03a7 with fixed `op[77:76]=2`; it has no
data/address operands and only a write scoreboard.

## Latency
`mio_pipe`, `OP_SYNCS` set. `INST_TYPE_DECOUPLED_RD_WR_SCBD` / `VQ_SYNCS_UNORDERED_WR`:
- the token/loaded-`URd` result is **write-scoreboard tracked** (consumers wait on the SB,
  varying producer→consumer latencies `sm_90_latencies.txt:189`); `_`/`RZ`-dest arrives use
  `wr_sb=7`.
- the `UPg`/predicate result (`PHASECHK` `Pu`) has small fixed latencies (line 346).

## Verified encodings (decoder: `tools/decode_syncs.py`)
Self-test 16/16.  The expanded PTX mapping capture decodes **47/47 SYNCS**
for sm_90 and **47/47** for sm_120; the core lowerings are identical.

| Lo64 | Hi64 | Disassembly | from |
|------|------|-------------|------|
| 0x00000000ffff79a7 | 0x000fe20008000006 | `SYNCS.ARRIVE.TRANS64 RZ, [UR6], R0` | arrive.expect_tx (A1TR) |
| 0x000000ffff0279a7 | 0x000e240008100006 | `SYNCS.ARRIVE.TRANS64.A1T0 R2, [UR6], RZ` | arrive (token in R2) |
| 0x00000002ff0679a7 | 0x0084220008500004 | `SYNCS.ARRIVE.TRANS64.ART0 R6, [UR4], R2` | arrive n (reg count) |
| 0x000000ffffff79a7 | 0x000fe20008100407 | `SYNCS.ARRIVE.TRANS64.RED.A1T0 RZ, [UR7], RZ` | remote/DSMEM arrive |
| 0x00000000ff0075a7 | 0x000e240008000144 | `SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR4], R0` | try_wait.parity |
| 0x00000004063f85b2 | 0x0000640008000100 | `@!UP0 SYNCS.EXCH.64 URZ, [UR6], UR4` | mbarrier.init |

Hand-check `SYNCS.ARRIVE.TRANS64.A1T0 R2,[UR6],RZ`: opcode 0x19a7; `paramtype`[86:84]=1→A1T0;
`retval`=0→(none); `Rd`[23:16]=2→R2; `URc`[69:64]=6→[UR6]; `Rb`[39:32]=RZ.

## Complete PTX v0 → SASS mapping

This table covers the direct `mbarrier.*` family accepted by CUDA 13.1/PTX 9.1.
Optional `.release/.relaxed`, `.cta/.cluster`, and `.shared/.shared::cta`
qualifiers do not change the core instruction shown below.  A remote
`.shared::cluster` destination is sink-only and selects `.RED`.  Acquire waits
add a predicated generic-cache invalidate (`@P CCTL.IVALL`) after PHASECHK.

| PTX operation | SASS lowering |
|---|---|
| `mbarrier.init [b], n` | form `x=(-n)&0xfffff`, `{URs,URs+1}={x<<1,x<<11}`; `SYNCS.EXCH.64 URZ,[URb],URs` |
| `mbarrier.inval [b]` | `SYNCS.CCTL.IV [URb]` |
| `mbarrier.arrive state,[b]` | `SYNCS.ARRIVE.TRANS64.A1T0 Rd,[URb],RZ` |
| `mbarrier.arrive state,[b],n` | `SYNCS.ARRIVE.TRANS64.ART0 Rd,[URb],Rn` |
| `mbarrier.arrive_drop state,[b]{,n}` | same A1T0/ART0 form plus `.OPTOUT` |
| `mbarrier.arrive.noComplete state,[b],n` | `.TMASK.ART0` |
| `mbarrier.arrive_drop.noComplete state,[b],n` | `.TMASK.OPTOUT.ART0` |
| `mbarrier.arrive.expect_tx state,[b],tx` | default A1TR: `SYNCS.ARRIVE.TRANS64 Rd,[URb],Rtx` |
| `mbarrier.arrive_drop.expect_tx state,[b],tx` | default A1TR plus `.OPTOUT` |
| any sink-only/remote version of the preceding operations | `Rd=RZ` and `.RED` (plus `.OPTOUT` for drop) |
| `mbarrier.expect_tx [b],tx` | `SYNCS.ARRIVE.TRANS64.RED.A0TR RZ,[URb],Rtx` |
| `mbarrier.complete_tx [b],tx` | `SYNCS.ARRIVE.TRANS64.RED.A0TX RZ,[URb],Rtx` |
| `mbarrier.test_wait p,[b],state` | `SYNCS.PHASECHK.TRANS64 P,[URb],Rstate_hi` |
| `mbarrier.test_wait.parity p,[b],parity` | `SHF.L parity,31`; same PHASECHK using the shifted value |
| `mbarrier.try_wait[.parity] p,[b],x` | same as test_wait, but `.PHASECHK.TRANS64.TRYWAIT` |
| `mbarrier.try_wait[.parity] p,[b],x,hint` | TRYWAIT; `@!P NANOSLEEP.SYNCS Rhint`; `@!P PHASECHK` |
| `mbarrier.pending_count count,state` | no SYNCS: extract token bits [62:43], negate modulo 2^20 (`LOP3`/`SHF` sequence) |

`cp.async.mbarrier.arrive[.noinc]` is adjacent PTX but uses the separate
`ARRIVES.LDGSTSBAR.64.TRANSCNT/ARVCNT` family (see `arrives.md`).  Bulk/TMA
instructions with `.mbarrier::complete_tx` decrement the same tx count from
their own async engines; see `../arch/tma_mbarrier.md`.

PTX ISA 9.3 additionally specifies `.layout::v1`, `.phase_type::{primary,
conditional}`, payload-report wait destinations, and `mbarrier.check_layout`.
CUDA 13.1's ptxas only supports the v0 forms, so those newer forms currently
have no captured SASS mapping in this repository.

Note: mbarrier is a **distinct** cluster/shared-sync mechanism from the CGA hardware
barrier `UCGABAR_*` (`ucgabar_arv.md`) — `barrier.cluster.*` → `UCGABAR`, whereas
`mbarrier.*` (incl. `.cluster` scope via `mapa`/DSMEM) → `SYNCS`.

## Verified semantics & behavior boundaries (sm_120, RTX 5090, CUDA 13.1)

Hand-written SASS verification (`tests/asm_construct/test_mbarrier.py`,
`tests/mbarrier_ops_test.cu` — the latter captures the nvcc/ptxas lowering of
every `mbarrier.*` PTX op on sm_120):

The nvcc lowering is **identical on sm_90 and sm_120** (same SYNCS encodings;
only the shared-address setup and cbank slots differ) — verified by compiling
`tests/mbarrier_ops_test.cu` for both archs.

| PTX | SASS | verified behavior |
|-----|------|-------------------|
| `mbarrier.init [b], n` | `SYNCS.EXCH.64 URZ, [UR], UR` | writes `((0x100000−n)<<11)<<32 \| (0x100000−n)<<1`; phase completes after `n` arrives |
| `mbarrier.arrive` | `SYNCS.ARRIVE.TRANS64.A1T0 Rd, [UR], RZ` | arrive+1; token = opaque old state (high word encodes pending count + phase bit 63) |
| `mbarrier.arrive.expect_tx` | `SYNCS.ARRIVE.TRANS64 Rd, [UR], R` (A1TR) | arrive+1, tx += R |
| `mbarrier.expect_tx [b], k` | `SYNCS.ARRIVE.TRANS64.RED.A0TR RZ, [UR], R` | **tx += R** (A0TR adds) |
| `mbarrier.complete_tx [b], k` | `SYNCS.ARRIVE.TRANS64.RED.A0TX RZ,[UR],R` | **A0TX subtracts**; the formerly attributed A0TR was the separate preceding `expect_tx` in the capture kernel |
| `mbarrier.try_wait.parity` | `SYNCS.PHASECHK.TRANS64.TRYWAIT P, [UR], R` | non-blocking predicate; **parity operand is bit 31 of Rb** (`0`/`0x80000000`) |
| `mbarrier.test_wait.parity` | `SYNCS.PHASECHK.TRANS64 P, [UR], R` | same, no TRYWAIT bit |
| `mbarrier.arrive.shared::cluster` | `SYNCS.ARRIVE.TRANS64.RED.A1T0 RZ, [UR], RZ` | remote/DSMEM arrive (Rd must be RZ) |
| `mbarrier.inval` | `SYNCS.CCTL.IV [UR]` | writes the live cache entry back to shared and invalidates the object/cache entry |

**Phase / parity model (verified):** the barrier's current phase has a parity
bit (state bit 63).  `PHASECHK.parity(P)` returns TRUE iff the phase with
parity `P` has already completed — i.e. iff the current phase's parity differs
from `P`.  `init(n)` → after `n` arrives the phase completes and the parity
flips; the next `n` arrives complete the next phase, etc.

**Completion rule (verified):** a phase completes when the pending arrive
count reaches 0 **and** the pending tx count reaches 0.  `expect_tx(k)` leaves
the phase open until `complete_tx(k)` drains the tx credit (verified: 128
pending blocks, +A0TX(128) completes; 128+128 pending, +A0TX(256) completes).

### Physical 64-bit `layout::v0` word (cache-eviction verified)

The barrier normally lives in an SM-local **mbarrier cache**.  An LDS before
eviction can read stale/zero shared backing and is not evidence about the live
state.  `tests/asm_construct/test_mbarrier_state.py` performs each state
transition, executes `SYNCS.CCTL.IV`, req-waits its scoreboard, and only then
uses `LDS.64`.  RTX 5090/sm_120 measurements establish:

| bits | width | physical field | decoded logical value |
|---|---:|---|---|
| 0 | 1 | zero for `layout::v0` | reserved in v0; likely the v0/v1 discriminator in PTX 9.3 |
| 20:1 | 20 | `Expected` | `expected = (-field) mod 2^20` |
| 41:21 | 21 | `Tx` | `outstanding_tx = (-field) mod 2^21` |
| 42 | 1 | lock/poison | zero in all valid quiescent states; forcing it to one makes the next mbarrier op fault 719 |
| 62:43 | 20 | `Arrive` | `pending = (-field) mod 2^20` |
| 63 | 1 | phase parity | toggles on phase completion |

Equivalently, for valid v0 states observed here:

```
word = ((-expected      & 0xfffff)  << 1)
     | ((-outstandingTx & 0x1fffff) << 21)
     | ((-pending       & 0xfffff)  << 43)
     | (phase << 63)
```

The 20/21/20 widths agree with PTX 9.3's architectural v0 ranges:
Expected/Pending use 20-bit counts, while tx-count is signed in
`[-(2^20-1), 2^20-1]`.  The formula above names the positive outstanding
case measured by `expect_tx`; the physical 21-bit field itself is signed.

Decisive observed words (post-`CCTL.IV`):

| state | backing word |
|---|---:|
| `init(1)` | `0x7ffff800001ffffe` |
| `init(3)` | `0x7fffe800001ffffa` |
| `init(3); arrive` | `0x7ffff000001ffffa` |
| `init(3); arrive_drop` | `0x7ffff000001ffffc` |
| `init(3); expect_tx(64)` | `0x7fffebfff81ffffa` |
| `init(3); expect_tx(0x12345)` | `0x7fffebdb977ffffa` |
| `init(2); arrive; arrive` | `0xfffff000001ffffc` |

Thus SEMU's prior positive `pending_tx << 21` encoding was wrong: the logical
counter can remain positive internally, but its physical field is the 21-bit
two's complement.  `arrive_drop` proves that Expected and Arrive are distinct:
both fields move from -3 to -2.  A normal arrive only changes Arrive.  The
returned arrival token is the opaque pre-operation state; `pending_count`
decodes its Arrive field rather than loading the current barrier.

**Scoreboard usage (hand-written SASS):** SYNCS is decoupled
(`INST_TYPE_DECOUPLED_RD_WR_SCBD`); the result token/predicate is written
asynchronously and tracked on `wr_sb`.  ptxas emits e.g. `SYNCS.EXCH … &wr=0x2`
then waits with `req={2}` (or via `BAR.SYNC`); consumers of the `P0` phase
predicate must `req` the PHASECHK's `wr_sb`.  Without the pairing, reads race
(observed garbage).

**try_wait spin-loop shape (critical, verified on sm_120):** the consumer's
PHASECHK loop MUST branch back on the PHASECHK's own predicate, exactly as
ptxas emits it:
```
poll:
    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR], RZ   &wr=0x1
    @!P0 BRA poll                                  &req={1}
```
Replacing the back-edge with a timeout counter's derived predicate
(`@P0 BRA done; IADD3 …; ISETP P1,…; @P1 BRA poll`) makes the mbarrier phase
NEVER complete — verified with a 0x2000000-iteration counter (~0.8 s) while
the `@!P0` back-edge completes in microseconds; NOPs inside the loop are
harmless.  This blocks TMA `cp.async.bulk … complete_tx::bytes` completions
as well (see `ublkcp.md`).  Presumably the completion/flush machinery only
recognizes the try_wait spin when the PHASECHK predicate feeds the
control-flow back-edge directly.

**EIATTR MBARRIER register byte:** `EIATTR_MBARRIER_INSTR_OFFSETS` entries
encode the mbarrier address register in the 4th u32's byte 2 (ptxas:
`0x00070100` INIT with `(R255+UR7)`, `0x0004010a` TRYWAIT with `(R255+UR4)`).
The assembler hardcoded 0x06 (UR6); it now derives the value from the
instruction — `Sa` [29:24] for SYNCS.EXCH (the address sits in `URa` there),
`Ra_URc` [69:64] for PHASECHK/CCTL/ARRIVE.  (Patching ptxas's entries to wrong
registers did not change behavior, so this is a metadata-correctness issue,
not the completion blocker.)

**Behavior boundaries (traps, CUDA error 719):**
- negative tx count: `A0TX(-64)` with 0 pending underflows the pending-tx
  field; the op itself does not trap but the barrier is corrupted and the next
  `mbarrier` op on it traps.
- `init(0)`: phase 0 is immediately complete; a subsequent `arrive` traps.
- mbarrier ops at shared address 0 (or outside the shared window) trap —
  the address must be the real shared-space form `(CgaCtaId<<24)|off`
  (CgaCtaId = 0 for the first CTA on sm_120).

**State visibility / eviction:** a plain `LDS` right after an mbarrier operation
does not read the live object because it is still resident in the mbarrier
cache.  `SYNCS.CCTL.WB` writes an entry back while retaining it;
`SYNCS.CCTL.IV` writes it back and invalidates/evicts it.  For destructive
debug observation, issue CCTL.IV and req-wait its scoreboard before LDS.64.
At the PTX level this is `mbarrier.inval`, so no further mbarrier operation may
legally use that object until re-initialization; the backing bytes may then be
repurposed/read.  `IVALL` also exposed two resident objects in one operation.

**Toolchain notes found while building the test:**
- the assembler's auto `MBARRIER_INSTR_OFFSETS` was 4-byte entries; the driver
  expects 16-byte `{offset, 0xff, 0, kind_flags}` entries (flags captured from
  ptxas: EXCH=0x00060100, A1T0=0x00060101, OPTOUT=0x00060103, PHASECHK=
  0x00060106, CCTL.IV=0x00060108, TRYWAIT=0x0006010a, A0TR=0x0006010b,
  A0TX=0x0006010c, TMASK.ART0=0x00ff0102) — fixed in `sass_elf.py`.
- `_compute_regcount` treated UMOV's 32-bit immediate as a register; a count
  value with low byte ≥ 0xfe inflated regcount past 255 and failed the launch
  (`0xFFFFE` for `init(2)`) — fixed.
- `IMAD Rd, RZ, RZ, URx` reads 0 for a uniform source in hand-built cubins;
  use `MOV Rd, URx` (mov__RU) to move a uniform register to a GPR.
- the assembler's ULEA: `.HI` returns the high 32 bits of the 64-bit
  `(URa<<scale)+URb+URc`; ptxas's barrier-address `ULEA` (default LO) form is
  not assemblable through the 6-operand syntax yet — use `UMOV` for the
  single-CTA address `0x400`.

## Open questions
- `SYNCS.CCTL.WB`, `SYNCS.CCTL.{IVALL,WBALL}`, and `syncs_ld_` `.WATCH` are
  ISA-spec-visible internal operations but are not emitted by the captured PTX.
  Their basic data effects are device-verified; `.WATCH`'s extra side effect is not.
- Blackwell `SYNCS.FLUSH` is proven not to write mbarrier backing, but exactly
  which pending SYNCS/TMA producers it drains and its ordering scope remain open.
- Bit 42 behaves as a lock/poison validity bit when injected, but its transient
  lock protocol cannot be observed by a quiescent post-eviction LDS.
- PTX 9.3 `layout::v1` physical layout and its SASS lowering remain open; the
  installed CUDA 13.1 ptxas does not accept those new syntax forms.
