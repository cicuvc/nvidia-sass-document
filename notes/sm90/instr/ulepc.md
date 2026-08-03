# ULEPC — Uniform Load Effective PC

**Opcode mnemonics:** `ULEPC` = `0b1001111001110` = **0x13ce** (URURUR, PC only) / `0b1100111001110` = **0x19ce** (UR_I_R, PC+imm58) | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_90 (crucible idx 238)

The uniform-datapath sibling of `LEPC` (see `lepc.md`). Computes a PC-relative effective address
into a 64-bit **uniform** register pair `{URd,URd+1}` (even-aligned). Verified on sm_120 silicon
(RTX 5090) — semantics identical to the verified LEPC.

## Semantics (verified on sm_120)
- **`ULEPC {URd,URd+1}`** (0x13ce) — the **address of the ULEPC instruction itself** into the
  64-bit uniform pair. Confirmed with the GPR twin `LEPC {Rd,Rd+1}` placed one instruction
  later: both return their own addresses (values differ by exactly 0x10).
- **`ULEPC {URd,URd+1}, sImm58`** (0x19ce) — `(instr_addr + 16) + sImm58` (next-instruction-
  relative, same convention as LEPC). `#label(tgt)` operands resolve to `target - next_pc`, so
  the result is exactly the target's address — verified equal to `LEPC Rd, #label(tgt)` for the
  same label, and for raw immediates (`+0x40`, `-0x10`) the arithmetic matches.
- 64-bit pair: hi word read 0 for kernel-text addresses (this driver maps text below 4 GB).

## Variant overview (3 CLASS, 2 opcodes)
| CLASS | opcode | operands |
|-------|--------|----------|
| `ulepc__URURUR` | 0x13ce | `{URd,URd+1}` (PC only) |
| `ulepc__UR_I_R` | 0x19ce | `{URd,URd+1}, target` (RSImm, resolved) |
| `ulepc_rel_` (ALT) | 0x19ce | `{URd,URd+1}, sImm58, .REL` (relocatable) |

## Fields (128-bit)
| bits | field | notes |
|------|-------|------|
| [91]∥[11:0] | `opcode` | 0x13ce / 0x19ce |
| [14:12]/[15] | `Pg`/`Pg_not` | uniform-predicate guard (7=UPT hidden) |
| [23:16] | `URd` | dest uniform reg, 64-bit pair — **sm_120: 8-bit**; sm_90: 6-bit at [21:16] |
| [81:24] | `sImm58` | signed PC offset (0x19ce); result = (instr+16)+imm |
| [112:110] | `dst_wr_sb` | pinned 0x7 (fixed-latency) |
| [124:122]∥[109:105] | `opex` | scheduling |

`URd` even-aligned, ≤MAX_UREG-2. IDEST_SIZE=64. Explicit register-group syntax is required
(`ULEPC {UR16,UR17}`, not `ULEPC UR16`).

## Cross-comparison vs LEPC
| | **LEPC** (int_pipe) | **ULEPC** (udp_pipe) |
|--|---------------------|----------------------|
| dest | GPR pair `{Rd,Rd+1}`[23:16] (8-bit) | uniform pair `{URd,URd+1}` (sm_90 [21:16] 6-bit / sm_120 [23:16] 8-bit) |
| opcodes | 0x34e / 0x94e | 0x13ce / 0x19ce |
| guard | predicate | uniform predicate |
| pc-only | own address (verified sm_120) | own address (verified sm_120) |
| imm form | (instr+16)+imm58 | (instr+16)+imm58 (verified same target as LEPC) |

## Latency (from sm_90_latencies.txt)
`udp_pipe`, fixed-latency `COUPLED_MATH`. `OP_ULEPC = {ULEPC, ULEPCudp_pipe}`, grouped with
`UMOV` (`UMOV_ULEPC`) and part of `ULDC_VOTEU_UMOV_ULEPC` for the `TABLE_*(UGPR)` URd-producer
latency rows.

## Verified encodings (sm_120, RTX 5090 — assembler + GPU)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000000000473ce` | `0x000fca0008000000` | `ULEPC {UR4,UR5}` |
| `0x00000000000479ce` | `0x000fca0008000000` | `ULEPC {UR4,UR5}, 0x0` |
| `0x00000000400479ce` | `0x000fca0008000000` | `ULEPC {UR4,UR5}, 0x40` |
| `0xfffffffff00479ce` | `0x000fca000803ffff` | `ULEPC {UR4,UR5}, -0x10` |

Decoder + round-trip test: `tools/decode_ulepc.py`.

## Open questions
- None blocking: semantics now silicon-verified. The `.REL` relocatable ALT form is still
  linker-only (untestable without an actual relocation), and non-converged/diverged warps are
  untested (PC address is warp-uniform by construction).
