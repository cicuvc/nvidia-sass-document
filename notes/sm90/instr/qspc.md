# QSPC — Query address space type (PTX `isspacep`)

**Opcode mnemonic:** `QSPC` = `0x3aa` (GPR base) / `QSPC_URb` = `0x19aa`
(uniform-register base) | **Pipe:** `mio_pipe` (**MIO_SLOW_OPS**) |
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VIRTUAL_QUEUE=$VQ_AGU`,
`MEM_SCBD=NONE/BARRIER_INST`, `MIN_WAIT_NEEDED=1`, `VALID_IN_SHADERS=ISHADER_ALL`

SASS lowering of PTX `isspacep.space p, a` — writes predicate `Pu` with `1`
if the generic address `a` falls inside the window of the given address space.
Unlike a compare, the space windows are *hardware-defined* (each CTA has
global/local/shared windows with generic bases planted in the constant bank),
so the result is exact for arbitrary generic addresses.

## Semantics (verified PTX→SASS)
| PTX | SASS | address operand | QUERY_SPACE |
|-----|------|-----------------|-------------|
| `isspacep.global p, a` | `QSPC.E.G P0, RZ, [a]` | `a` (generic) | `G` = 0 |
| `isspacep.local p, a` | `QSPC.E.L P0, RZ, [a]` | `a` (generic) | `L` = 1 |
| `isspacep.shared{::cta} p, a` | `QSPC.E.S P0, RZ, [a]` | `a` (generic) | `S` = 2 |
| `isspacep.shared::cluster p, a` | `QSPC.E.D P0, RZ, [a]` | `a` (generic) | `D` = 3 |
| `isspacep.const p, a` | **no QSPC** — ISETP window range-check | — | — |
| `isspacep.param::entry p, a` | **no QSPC** — ISETP window range-check | — | — |

`isspacep.const` / `isspacep.param::entry` do **not** lower to QSPC on sm_90:
ptxas expands them into `ISETP`/`ISETP.EX` range comparisons against const-bank
window slots (observed: `c[0x0][0xd0]` lower bound, `c[0x0][0x208]` upper
bound, and `c[0x0][0x198]`/`c[0x0][0x1a0]` for `.param::entry`).  QSPC covers
only the four hardware windows G/L/S/D.

**ptxas always emits the 64-bit `.E` form.**  For a `.u32` operand it
zero-extends into a register pair (`IMAD.MOV.U32 R7, RZ, RZ, RZ` for the GPR
case, `UMOV UR5, URZ` for the uniform case) before the QSPC.  The 32-bit
`noe` forms exist in the spec but were never observed from ptxas (CUDA 12.8).

## Variant overview (15 CLASS variants, 2 opcodes)
| CLASS family | opcode | address syntax | notes |
|--------------|--------|----------------|-------|
| `qspc__RaNonRZ` / `qspc__RaRZ` | `0x3aa` | `[Ra+off]` / `[RZ+off]` | GPR base, 24-bit signed offset |
| `qspc_PuOnly__RaNonRZ/RaRZ` | `0x3aa` | same, `Rd` pinned `*255` | predicate-only dest |
| `qspc_RdOnly__RaNonRZ/RaRZ` | `0x3aa` | same, `Pu` pinned `*7` | Rd-only dest |
| `qspc_urb__Ra32` | `0x19aa` | `[Ra.U32+URb+off]` | 32-bit GPR part + UR base; `e` picks UR pair width |
| `qspc_urb__Ra64` | `0x19aa` | `[Ra.64+URb+off]` | 64-bit GPR pair + 64-bit UR pair (`EONLY`) |
| `qspc_urb__RaRZ` | `0x19aa` | `[RZ.U32+URb+off]` | UR-only base — **the ptxas form** |
| `qspc_urb_PuOnly/RdOnly__*` | `0x19aa` | same 3 address forms | dest-pin variants |

The RaRZ/RaNonRZ split is a legality guard only (both encode `Ra` freely);
`qspc_urb__RaRZ` requires `Ra==RZ` while `qspc_urb__Ra32/Ra64` require a real
register.  `qspc_urb__Ra64` pins bit [90]=1 (`ONLY64`); Ra32/RaRZ leave bit
[90]=0.  `PuOnly` pins `Rd` to RZ (255), `RdOnly` pins `Pu` to PT (7) — ptxas
always uses the full form with `Rd=RZ`.

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x3aa / 0x19aa | 13-bit; bit [91] selects URB family |
| [14:12] / [15] | `Pg` / `Pg_not` | guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | dest GPR (32-bit; ptxas writes RZ) |
| [31:24] | `Ra` | Register | GPR base (pair if `.E` non-URB / Ra64-URB) |
| [90] | `input_reg_sz_*` | `*input_reg_sz_32_dist`=0 / `*input_reg_sz_64_dist`=1 | URB Ra32 vs Ra64 discriminator |
| [39:32] | `Ra_URb` | UniformRegister | URB base (pair if `.E`) |
| [63:40] | `Ra_offset` | SImm/UImm(24) | byte offset (sign-extended for non-RZ) |
| [72] | `e` | `E noe=0, E=1` | 0=32-bit, 1=64-bit address |
| [74:73] | `space` | `QUERY_SPACE` | `G=0, L=1, S=2, D=3` |
| [83:81] | `Pu` | Predicate | result predicate (7=PT hidden) |
| [124:122]∥[109:105] | `opex` | TABLES_opex_0(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | scoreboards | |
| [103:102] | `pm_pred` | perfmon predicate | |

`ISRC_A_SIZE = 32 + (e==E)*32` (non-URB) / 32+…+URb sizes (URB); `IDEST_SIZE=32`.
The `.E` condition requires even-aligned pairs for both `Ra` (non-URB/Ra64) and
`Ra_URb` (URB).  `Ra`/`Rd` ≠ R254, ≤ `MAX_REG_COUNT-1` (pair forms −2).

## Latency (from sm_90_latencies.txt)
`mio_pipe` **and** `MIO_SLOW_OPS` (same class as LDS/STS/S2R — the slow MIO
latency group).  Decoupled (`INST_TYPE_DECOUPLED_RD_WR_SCBD`, `VQ_AGU`):
- **GPR source** (`Ra` address) → QSPC is a `MIO_CBU_OPS` consumer:
  `TABLE_TRUE(GPR) ALL_OPS = { MIO_CBU_OPS : 2 }` — 2-cycle true dependency
  from any register producer into the address operand.
- **Predicate output** (`Pu`): `TABLE_TRUE(PRED) MIO_OPS`{Pu,…} row = 1 —
  predicate true-dependency is 1 cycle to all predicate readers;
  `TABLE_ANTI(PRED) MIO_OPS`{Pr,…,Pg} rows = 1.  (MIO producers have no row
  in `TABLE_OUTPUT(PRED)`; MIO_OPS appears there only as a consumer column.)
- **GPR output** (`Rd`) is *not* in `TABLE_OUTPUT(GPR)` — like other MIO
  decoupled writers, `Rd` completion is tracked by the write scoreboard
  (`dst_wr_sb`); consumers wait on `&wr=`/`&req=` rather than a fixed latency.
- `MIN_WAIT_NEEDED=1`, no `MEM_SCBD` wait requirement (memory-ordering
  barrier class, not a memory op itself).

## Verified encodings (sm_90 CUDA 12.8 + nvdisasm round-trip)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000004ffff79aa` | `0x000e220008000100` | `QSPC.E.G P0, RZ, [RZ.U32+UR4]` |
| `0x00000004ffff79aa` | `0x000e220008020500` | `QSPC.E.S P1, RZ, [RZ.U32+UR4]` |
| `0x00000004ffff79aa` | `0x000e620008000300` | `QSPC.E.L P0, RZ, [RZ.U32+UR4]` |
| `0x00000004ffff79aa` | `0x000e620008000700` | `QSPC.E.D P0, RZ, [RZ.U32+UR4]` |
| `0x00000008ffff79aa` | `0x000e680008000100` | `QSPC.E.G P0, RZ, [RZ.U32+UR8]` |
| `0x0000000006ff73aa` | `0x000e640000000100` | `QSPC.E.G P0, RZ, [R6]` |
| `0x0000000006ff73aa` | `0x000e640000000500` | `QSPC.E.S P0, RZ, [R6]` |
| `0x00000004040079aa` | `0x000e22000c000100` | `QSPC.E.G P0, R0, [R4.64+UR4]` |
| `0x00001004040079aa` | `0x000e22000c000100` | `QSPC.E.G P0, R0, [R4.64+UR4+0x10]` |
| `0x00001000020073aa` | `0x000e220000000000` | `QSPC.G P0, R0, [R2+0x10]` |

First 7 rows: real `cuobjdump -arch sm_90 -sass` captures from
`tests/qspc_test.cu` (ptxas always chooses the URB `RaRZ` form when the address
is uniform, the GPR form when data-dependent).  Last 3 rows: hand-assembled
SASS round-tripped through `assembler/` and verified with `nvdisasm`
(`tests/asm_construct/test_qspc.py`).  Decoder: `tools/decode_qspc.py`
(all 16 vectors pass).  Test: `tests/qspc_test.cu`.

### On-GPU semantic verification (sm_120, RTX 5090, CUDA 13.0)
The hand-built SASS test (`tests/asm_construct/test_qspc.py`) runs on
hardware and checks all four windows with both address forms (GPR base and
URB base), 12/12 pass:

| queried address | `.G` | `.L` | `.S` | `.D` |
|-----------------|------|------|------|------|
| global (cuMemAlloc ptr) | 1 | 0 | 0 | 0 |
| shared generic `0x1_00000400` | 0 | 0 | 1 | 1 |
| local `0x3fff000` | 0 | 1 | 0 | 0 |

Empirically mapped sm_120 window model (single CTA): global =
`[0x0, 0x03f00000) ∪ [0x04000000, …)`, per-thread local =
`[0x03f00000, 0x04000000)` (16 MiB, stack at `0x03fffda0`), shared generic
base = `0x1_00000000` (so `0x1_00000400` is the first shared byte past the
reserved 1 KiB).  This differs from the sm_90 layout where ptxas fed QSPC the
shared-space offset form `(CgaCtaId<<24)|0x400` and the generic shared/local
bases lived in cbank `[0x18]/[0x20]`; on sm_120 those cbank slots read 0 in
hand-built cubins, so the test constructs window addresses directly.

**Consuming the result predicate (decoupled write):** QSPC is
`INST_TYPE_DECOUPLED_RD_WR_SCBD` — the `Pu` result is written asynchronously.
ptxas emits `QSPC … &wr=0x1` and consumers wait with `&req={1}`; hand-written
SASS must do the same (`[1:7:{1}:1:0]` on QSPC, `req={1}` on the reader).
Without the wr/req scoreboard pairing the reader sees a *stale* predicate from
an earlier QSPC (observed: results shuffled between runs).

**Toolchain caveats seen while building the test:** in this repo's hand-built
cubins on the CUDA 13.0 driver, `LDCU` (uniform cbank load) returns 0 for
cbank offsets `0x358` and `0x380+` (desc slot and param area) even though
`LDC` reads the same slots correctly and nvcc-built cubins load them via
`LDCU`/`ULDC` fine; and the `desc[{URx,URy}]` global-store operand is
decorative here (stores succeed with a garbage descriptor).  The QSPC test
therefore loads addresses with `LDC` into GPRs or materializes them with
`MOV32I`/`UMOV`, and only uses the URB form with values it constructed itself.

### PTX→SASS mapping
- `isspacep.global/.local/.shared/.shared::cluster` → `QSPC[.E].<G|L|S|D>`.
- `.shared` defaults to `::cta` (`S`); `.shared::cluster` → `D`.
- `.u64` → `.E` (pair source).  `.u32` → also `.E` — ptxas zero-extends.
- `isspacep.const` / `isspacep.param::entry` → ISETP window range-checks
  against const-bank window slots (no QSPC).
- Address in uniform regs → URB form `[RZ.U32+URb]` (ptxas hoists kernel
  params with `ULDC`/`LDCU` + `ULEA`); address in GPRs → `[Ra]` form.

## Cross-comparison
- **QSPC vs ISETP lowering:** only G/L/S/D windows have QSPC encodings; the
  const and param windows are software-range-checked.  The 4-bit
  `QUERY_SPACE` field (`G/L/S/D`) is the hardware window selector — `D`
  (3) is shared::cluster (sm_90+; `isspacep.shared::cluster` requires sm_90).
- **URB addressing** matches LDS/STS/ATOMS-style `[Ra + URb + off]` operand
  groups (`ILABEL_Ra_SIZE`/`ILABEL_Ra_URb_SIZE` split the source across a
  GPR part and a uniform part; `SIDL_NAME=QSPC_URb` for URB classes).
- **Dest forms:** the Pu-only / Rd-only / full triad parallels MATCH
  (`.ALL` writes `Pu`+`Rd`) — QSPC's full form with `Rd=RZ` is what ptxas
  emits; the pinned variants are assembler/decoder-level alternatives.

## Open questions
- The meaning of the `D` (3) space name ("Device"? "Cluster-shared"?); the
  spec exposes only the enum, empirical mapping is `.shared::cluster`.
- Whether any compiler emits the `noe` (32-bit) or Ra32/Ra64-URB QSPC forms
  (ptxas 12.8 does not — they round-trip through the assembler but have no
  observed producer).
- ptxas occasionally emits extra ISETP/PLOP3 range-check code around QSPC in
  optimized kernels (observed self-cancelling in `qspc_gpr_u32`); whether
  that guards some window edge cases or is dead code is unconfirmed.
- sm_120 window geometry (global/local/shared bases above) was mapped on one
  driver; whether the boundaries (local `0x03f00000`, shared `0x1_00000000`)
  are arch-fixed or driver-configured is unconfirmed.
- The hand-built-cubin `LDCU`-reads-0 quirk (uniform cbank not populated at
  `0x358`/`0x380+` for this repo's ELFs) deserves a follow-up in the
  assembler ELF writer, since nvcc cubins read those slots fine.
