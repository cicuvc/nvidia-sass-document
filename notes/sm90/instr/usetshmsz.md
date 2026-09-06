# SETSMEMSIZE (USETSHMSZ) — Shrink per-warp shared bound, then release CTA SRAM

**Opcode mnemonic:** `USETSHMSZ` = `0b1100111001001` = **0x19c9** (imm / FLUSH) / `0b1001111001001` = **0x13c9** (UR form) | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`, `VIRTUAL_QUEUE=$VQ_UNORDERED` | compute-only (`SHADER_TYPE==CS`)

> **Status: EMPIRICALLY VERIFIED on SM120 (RTX 5090).** Full GPU probe below
> (`tests/asm_construct/test_usetshmsz.py`). ptxas/nvcc (CUDA 13.x) never emit
> this from C/C++ or PTX, and it is absent from libcublas / libcublasLt and the
> crucible ptxas dumps — it is a shrink-only runtime knob, not a compiler
> product. Encodings below are spec-derived + round-trip verified by the
> assembler; the **behavior** is empirically pinned down.

## Semantics (verified on silicon)

`USETSHMSZ size` **shrinks the issuing hardware warp's shared-memory address
bound**.  `USETSHMSZ.FLUSH` is the separate commit operation that submits the
executing warp's current value to the CTA resource allocator and allows the
scheduler to backfill the released SRAM with more CTAs. A size may only
**decrease**; it can never grow back after SRAM may have been reassigned.

Empirically confirmed rules (SM120, decl `#pragma SHARED(0x1000)`, block 32):

1. **Monotone decrease only.** A value **larger than the *current* window**
   traps with `ILLEGAL_INSTRUCTION` (CUDA error 715). `0x1000` on a 4 KiB
   window is legal; `0x2000` (or `0x8000`) is not. "Once shrunk you can't grow
   back" — and the bound is **relative to the current size**, not the initial
   one: after `USETSHMSZ 0x200`, `USETSHMSZ 0x400` is illegal even though
   `0x400 < 0x1000`, while `USETSHMSZ 0x100`/`0x200` remain legal.
2. **Can keep shrinking.** Chains like `0x800 → 0x400 → 0x200 → 0x100 → 0x80
   → 0x0` all execute; even `0x0` is legal.
3. **128-byte granularity.** Legal values are multiples of 128 B: `0x0`,
   `0x80`, `0x100`, `0x180`, `0x1000` … are fine; `0x40`, `0x7F`, `0x101`,
   `0x1C0` trap 715. (0x1C0 = 448 = 3.5·128.)
4. **The state is per hardware warp, not per CTA and not per active SIMT
   group.** With two warps in one CTA, shrinking warp 0 does not prevent warp
   1 from accessing a high shared address, and their monotone bounds evolve
   independently.  But if only lanes 0--15 execute the size instruction on a
   divergent path, lanes 16--31 of the same warp subsequently observe the
   smaller bound.  This reconciles the instruction's uniform datapath with
   the apparently CTA-wide resource it controls.
5. **Each warp's initial bound includes the reserved 1 KiB prefix.** For a
   cubin user declaration `S`, it is `0x400 + align_up(S,0x80)`.  Thus with
   `#pragma SHARED(0x1000)`, `USETSHMSZ 0x1400` is legal and `0x1480` traps
   715.  A fresh CTA/launch receives a fresh initial bound.
6. **The shrink takes effect immediately on that warp's address checks.**
   After setting `0x200`, `STS/LDS` at `@0x80` works but `@0x400` (beyond the new window)
   faults with `ILLEGAL_ADDRESS` (CUDA error 700). Another warp in the CTA can
   still access `@0x400` until it updates its own bound.
7. **`.FLUSH` does not lift the monotone rule:**
   after `0x200` + `.FLUSH`, growing to `0x400` still traps, shrinking to
   `0x100` is still fine.
8. **UR form** (`0x13c9`, size from a uniform register) obeys the same
   monotone + granularity rules.

### Attempts to find a growth protocol (negative)

The shrink-only conclusion was retested on an idle RTX 5090 specifically to
exclude a missing timing or allocation handshake.  After shrinking from
`0x800` and attempting to return to `0x1000`, every tested sequence trapped
with error 715:

- adjacent shrink/grow and shrink followed by 256 long-stall NOPs;
- a CTA `BAR.SYNC` between the operations, including both warps participating;
- `.FLUSH`, a long wait, and a second `.FLUSH`;
- `ACQSHMINIT` before and/or after `.FLUSH` (despite its name, that instruction
  waits for shared-memory-initialization release status; it is not an allocator
  acquire operation).

Launching the kernel with an additional 4 KiB of dynamic shared memory raised
the fresh-warp bound as expected: a direct `USETSHMSZ 0x2400` succeeded.  It
still did not permit `0x800 -> 0x1800`, proving the failure is the monotone
current-bound check rather than exhaustion of the CTA's original allocation.

The encoding audit also found no hidden USETMAXREG-like allocation mode.
Bits 73--90 are marked unused in the USETSHMSZ immediate form.  Setting each
one individually left a legal initial size operation executable but did not
make a subsequent growth legal.  The structured patterns corresponding to
USETMAXREG's `TRY_ALLOC`, `TRY_ALLOC.CTAPOOL`, and `UPT` output-predicate fields
also still trapped on growth.  This does not mathematically exclude a wholly
unknown opcode or a complex multi-bit protocol, but it rules out the plausible
documented, synchronization, resource, and adjacent-encoding paths.  The
observed USETSHMSZ state is therefore strictly monotone for a warp lifetime.

### `.FLUSH` and dynamic occupancy (verified positive)

The original probe tested the size write alone and therefore produced a
misleading negative result.  The operation is explicitly two-phase:

1. one or more warps update their bounds with `USETSHMSZ size`;
2. a warp executes `USETSHMSZ.FLUSH`, committing its current value as the
   CTA allocator target.

On the 170-SM RTX 5090, with 5000 launched CTAs and a global live-CTA peak
counter, the block-32 results are:

| static declaration / runtime action | GPU-wide peak CTAs | CTA/SM |
|---|---:|---:|
| 64 KiB / none | 170 | 1 |
| 64 KiB / shrink to 4 KiB only | 170 | 1 |
| 64 KiB / shrink to 4 KiB + FLUSH | 1360 | 8 |
| 64 KiB / FLUSH only | 170 | 1 |
| 3 KiB user / none (4 KiB total static control) | 1360 | 8 |

Thus `.FLUSH` really returns shared SRAM to the scheduler; this is not an L1
carve-out hint.  With block 64, 64 KiB→32 KiB+FLUSH reaches 2 CTA/SM while a
static 32 KiB kernel reaches 3 CTA/SM.  This follows the measured progressive
backfill rule exactly: a newly admitted CTA must initially fit its static
`64 KiB + 1 KiB reserved` charge before it can execute its own shrink+FLUSH,
so dynamic residency need not equal a kernel launched with the smaller static
declaration.

The allocator charge after FLUSH is exactly the immediate total-window value;
the static 1 KiB prefix is not added again.  Full allocation/fragmentation
measurements and the admission formula are in
`notes/sm120/arch/shared_memory_allocator.md`.

A single warp's shrink+FLUSH is sufficient to release CTA SRAM on an idle GPU,
even if another warp retains its larger address bound. Hardware therefore does
not enforce a collective update. This is unsafe unless software guarantees the
other warps will never use the released range. Having multiple warps FLUSH
different values produced launch failure 719; the exact disagreement semantics
remain undefined. Earlier apparent 700 faults from partial FLUSH coincided with
another training workload occupying the GPU and are withdrawn.

## Variant overview (3 CLASS variants)
| CLASS | opcode | operand | `e`[72] | ISRC_B_SIZE |
|-------|--------|---------|---------|-------------|
| `usetshmsz__Ib`    | 0x19c9 | `UImm(20)` byte size `Sb` | 0 | 20 |
| `usetshmsz__FLUSH` | 0x19c9 | none, `/FLUSHONLY` modifier | 1 | 0 |
| `usetshmsz__URb`   | 0x13c9 | `UniformRegister` `URb` (size in UR) | 0 | 32 |

`FLUSHONLY "FLUSH"=1`. The single distinguishing bit `e`[72]: `0` = normal
(size via imm or UR), `1` = `.FLUSH`. imm vs UR is selected by opcode
(`0x19c9` vs `0x13c9`).

## Bit layout (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x19c9 (imm/FLUSH) / 0x13c9 (UR) | 13-bit |
| [14:12] / [15] | `Pg` / `Pg_not` | UPg guard | uniform predicate guard (7=PT hidden) |
| [51:32] | `Sb` | UImm(20) | shared-mem byte size (imm form) |
| [37:32] | `Ra_URb` | UniformRegister | size in UR (UR form) |
| [72] | `e` | `*flush` / 0 | 1 = `.FLUSH`, 0 = normal |
| [124:122]∥[109:105] | `opex` | TABLES_opex_0(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | scoreboard | |
| [103:102] | `pm_pred` | perfmon predicate | |

## Cross-comparison vs USETMAXREG (adjacent opcode)
| | **USETMAXREG** 0x19c8 | **USETSHMSZ** 0x19c9 |
|--|----------------------|----------------------|
| resource | per-warp register count | shared-memory size |
| INSTRUCTION_TYPE | DECOUPLED_RD_**WR**_SCBD | DECOUPLED_RD_SCBD |
| dest predicate | UPu (alloc success) | none |
| imm width | 10-bit (`Sb`[41:32]) | 20-bit (`Sb`[51:32]) |
| modifier bits | `num`[73:72] mode, `sh`[74] pool | `e`[72] flush |
| PTX | `setmaxnreg` | (none found) |
| verified behavior | — | shrink-only, 128B granule, 715 on grow |

## Latency (from sm_90_latencies.txt)
`udp_pipe` member (`USETSHMSZ, USETSHMSZudp_pipe` listed in the pipe). No
dedicated latency row observed beyond generic udp_pipe behavior; no
GPR/UGPR result (`IDEST_SIZE=0`), so it contributes no true/output dependency
to consumers — only scoreboard ordering via `req_bit_set`. The size read
(`Sb` imm or `URb`) is a uniform-datapath operand, so `src_rel_sb` ordering
applies when the size comes from a freshly-loaded UR.

## Verified encodings
| Lo64 | Hi64 | Disassembly | case |
|------|------|-------------|------|
| `0x00008000000079c9` | `0x000fe20008000000` | `USETSHMSZ 0x8000` | imm, shrink 32K on 64K decl OK |
| `0x00000005000073c9` | `0x000fe20008000000` | `USETSHMSZ UR5` | UR form |
| `0x00000000000079c9` | `0x000fe20008000100` | `USETSHMSZ.FLUSH` | FLUSH form |

Decoder + round-trip test: `tools/decode_usetshmsz.py`. GPU behavior probe:
`tests/asm_construct/test_usetshmsz.py`.  Scope/collective/backfill research
probe: `tests/asm_construct/probe_usetshmsz_scope.py`. Growth-protocol and
reserved-bit falsification probe:
`tests/asm_construct/probe_usetshmsz_grow.py`.

## Open questions
- Exact hardware contract when CTA warps disagree needs a dedicated corruption
  probe after another CTA actually occupies the prematurely released range.
  Multiple inconsistent FLUSH values faulted 719.
- Interaction with clusters and PDL/dependent launches.
