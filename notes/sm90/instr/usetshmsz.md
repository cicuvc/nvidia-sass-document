# SETSMEMSIZE (USETSHMSZ) — Set shared-memory size (shrink-only, uniform)

**Opcode mnemonic:** `USETSHMSZ` = `0b1100111001001` = **0x19c9** (imm / FLUSH) / `0b1001111001001` = **0x13c9** (UR form) | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`, `VIRTUAL_QUEUE=$VQ_UNORDERED` | compute-only (`SHADER_TYPE==CS`)

> **Status: EMPIRICALLY VERIFIED on SM120 (RTX 5090).** Full GPU probe below
> (`tests/asm_construct/test_usetshmsz.py`). ptxas/nvcc (CUDA 13.x) never emit
> this from C/C++ or PTX, and it is absent from libcublas / libcublasLt and the
> crucible ptxas dumps — it is a shrink-only runtime knob, not a compiler
> product. Encodings below are spec-derived + round-trip verified by the
> assembler; the **behavior** is empirically pinned down.

## Semantics (verified on silicon)

`USETSHMSZ` **shrinks the CTA's shared-memory window** to the given byte size,
issued from the uniform datapath. The window is a runtime, per-launch state:
the instruction may only **decrease** it, never grow it back.

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
4. **Initial window = the size the driver allocated for the CTA** (here the
   cubin `SHARED` declaration). Setting a value above it is illegal — which is
   also why `USETSHMSZ` is per-launch: the next kernel launch resets the
   window to its own allocation, so a shrink in one kernel does **not** affect
   a later kernel's initial window.
5. **The shrink takes effect immediately on the window.** After setting
   `0x200`, `STS/LDS` at `@0x80` works but `@0x400` (beyond the new window)
   faults with `ILLEGAL_ADDRESS` (CUDA error 700). So the reduction is real,
   not a no-op.
6. **`.FLUSH`** executes cleanly and does **not** lift the monotone rule:
   after `0x200` + `.FLUSH`, growing to `0x400` still traps, shrinking to
   `0x100` is still fine. It commits the pending size; the "can't grow back"
   constraint is unaffected.
7. **UR form** (`0x13c9`, size from a uniform register) obeys the same
   monotone + granularity rules.

### Occupancy effect: verified NEGATIVE

The natural guess — "shrinking hands SRAM back so the block scheduler can
reside more CTAs" — was tested and **does not hold** on SM120 (RTX 5090).
An occupancy probe (block 32, decl 16K/32K/64K, 1000 blocks, each CTA bumps
a global active counter and atomically max-tracks the peak during a fixed
spin) shows the peak concurrent CTA count is determined **statically by the
launched shared size**, and USETSHMSZ does not change it:

| decl | peak CTA/SM (no USI) | peak CTA/SM (USETSHMSZ 4K) |
|------|---------------------|----------------------------|
| 16K  | 5 | 5 |
| 32K  | 3 | 3 |
| 64K  | 1 | 1 |

So the shrink tightens the **current CTA's** window (verified: a shrunk CTA
faults on accesses beyond the new window) but the released SRAM is **not**
used to schedule additional CTAs.  CTA residency is fixed at launch by the
cubin `SHARED` declaration; the instruction does not feed the block
scheduler.  What the freed SRAM *does* change (L1 carve-out?) was not
measurable in this harness and remains open.

Reading: it is a fire-and-forget configuration hint on the uniform datapath
(`DECOUPLED_RD_SCBD`, no destination, `VQ_UNORDERED`) — hardware turns a
"too large" request into `ILLEGAL_INSTRUCTION`. Likely purpose is Blackwell
L1/shared re-partitioning where a CTA can hand SRAM back to the L1/shared
pool at runtime; the shrink persists only for the lifetime of the launch.

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
`tests/asm_construct/test_usetshmsz.py`.

## Open questions
- Why does the ISA expose a shrink-only runtime knob? It does **not** raise
  occupancy (verified); the freed SRAM's actual effect (L1 carve-out? cluster
  pool hand-back?) needs a performance probe. On Blackwell it may exist for
  future/driver-driven use or PDL-style dependent launches, none of which
  this harness exercises.
- Whether the freed window is actually re-partitioned toward L1 (performance
  probe possible: shrunk kernel vs same kernel with no USETSHMSZ, measure
  local-memory/global latency).
- CTA- vs cluster-scoped effects when multiple CTAs share an SM.
