# SETSMEMSIZE (USETSHMSZ) — Set shared-memory size (uniform hint)

**Opcode mnemonic:** `USETSHMSZ` = `0b1100111001001` = **0x19c9** (imm / FLUSH) / `0b1001111001001` = **0x13c9** (UR form) | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`, `VIRTUAL_QUEUE=$VQ_UNORDERED` | compute-only (`SHADER_TYPE==CS`)

> **Status: NOT empirically verified.** ptxas/nvcc (CUDA 13.1) never emitted this from the
> C/C++ or inline-PTX I could construct, and it is absent from libcublas / libcublasLt and
> the crucible ptxas dumps. No PTX mnemonic maps to it in the ISA 9.3 docs. Everything below
> is spec-derived (from the CLASS ENCODING) plus **semantic speculation**; the encodings are
> constructed from the field layout, not captured from silicon.

## Semantics (speculation)
"**U-SET-SHM-SZ**" = uniform *Set Shared-Memory Size*. Opcode `0x19c9` sits immediately after
`USETMAXREG` (`0x19c8`) and shares its shape (udp_pipe, compute-only, `DECOUPLED_*_SCBD`,
`VQ_UNORDERED`, uniform-predicate guard, imm/UR/modifier trio). Both look like Hopper
**dynamic resource-partitioning hints** issued from the uniform datapath.

Best guess: it declares/updates the amount of **shared memory** the CTA (or CGA/cluster) will
use — i.e. the SASS-level counterpart of dynamic shared-memory reconfiguration
(`cudaFuncAttributeMaxDynamicSharedMemorySize`) and/or distributed-shared-memory (DSMEM) setup
for thread-block clusters. The 20-bit byte-size immediate (≤ 1 MiB range) comfortably covers
Hopper's ~227 KiB max shared window. Being `DECOUPLED_RD_SCBD` with no destination, it is a
fire-and-forget configuration hint (reads a scoreboard for ordering; writes nothing).

The `.FLUSH` form (no operand) most likely **commits/flushes** a pending size configuration.
Unlike `USETMAXREG`, there is **no predicate output** — it is not a try/allocate op, just a
size announcement, consistent with a hint that cannot fail.

## Variant overview (3 CLASS variants)
| CLASS | opcode | operand | `e`[72] | ISRC_B_SIZE |
|-------|--------|---------|---------|-------------|
| `usetshmsz__Ib`    | 0x19c9 | `UImm(20)` byte size `Sb` | 0 | 20 |
| `usetshmsz__FLUSH` | 0x19c9 | none, `/FLUSHONLY` modifier | 1 | 0 |
| `usetshmsz__URb`   | 0x13c9 | `UniformRegister` `URb` (size in UR) | 0 | 32 |

`FLUSHONLY "FLUSH"=1`. The single distinguishing bit `e`[72]: `0` = normal (size via imm or
UR), `1` = `.FLUSH`. imm vs UR is selected by opcode (`0x19c9` vs `0x13c9`).

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

## Latency (from sm_90_latencies.txt)
`udp_pipe` member (`USETSHMSZ, USETSHMSZudp_pipe` listed in the pipe). No dedicated latency
row observed beyond generic udp_pipe behavior; no GPR/UGPR result (`IDEST_SIZE=0`), so it
contributes no true/output dependency to consumers — only scoreboard ordering via `req_bit_set`.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64* | Reconstruction |
|------|-------|----------------|
| `0x00008000000079c9` | `0x0000000008000000` | `USETSHMSZ 0x8000` |
| `0x000fffff000079c9` | `0x0000000008000000` | `USETSHMSZ 0xfffff` |
| `0x0000000500007 3c9` | `0x0000000008000000` | `USETSHMSZ UR5` |
| `0x00000000000079c9` | `0x0000000008000100` | `USETSHMSZ.FLUSH` |

\* Hi64 shows only the opcode bit[91] and `e` bit[72]; real scheduling/scoreboard bits
(`opex`, `req_bit_set`, …) are compiler-chosen and unknown. Decoder + round-trip test:
`tools/decode_usetshmsz.py`.

## Open questions
- **Unconfirmed semantics** — the "shared-memory size" reading is inference from the mnemonic
  and its `USETMAXREG` neighbor; needs a real emission to confirm operand units (bytes?
  granularity?) and what `.FLUSH` commits.
- What toolchain path emits it (cluster kernels? a specific driver ABI prologue?) — none of the
  available libraries contain it.
- Whether the size is CTA-scoped or cluster/CGA-scoped (DSMEM).
