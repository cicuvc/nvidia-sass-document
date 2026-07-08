# ULEPC — Uniform Load Effective PC

**Opcode mnemonics:** `ULEPC` = `0b1001111001110` = **0x13ce** (URURUR, PC only) / `0b1100111001110` = **0x19ce** (UR_I_R, PC+imm58) | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_90 (crucible idx 238)

The uniform-datapath sibling of `LEPC` (see `lepc.md`). Computes a PC-relative effective address
into a 64-bit **uniform** register pair `URd:URd+1`. Used when the PC address is warp-uniform
(e.g. a uniform `CALL`/relative-address setup), keeping it on the uniform datapath.

> **Status: encoding spec-derived, semantics inherited from verified LEPC; NO direct ULEPC
> capture.** ptxas emitted per-thread `LEPC` (not ULEPC) for the printf/assert paths tried, and
> ULEPC was absent from libcublasLt. Its layout is identical to the empirically-verified LEPC
> except the destination is a uniform register and the pipe is `udp_pipe`; example encodings are
> round-trip constructions.

## Semantics
Same as LEPC, uniform destination:
- **`ULEPC URd`** (0x13ce) — current PC into `URd:URd+1`.
- **`ULEPC URd, sImm58`** (0x19ce) — PC + 58-bit signed offset (`sImm58`[81:24]); cuobjdump
  prints the resolved target `= (instr_addr + 16) + imm` (same convention as LEPC's vprintf
  return-address idiom).
- **`ulepc_rel_`** ALT (0x19ce) — relocatable spelling with `/RelOpt` "REL" + plain `SImm(58)`,
  same bits.

## Variant overview (3 CLASS, 2 opcodes)
| CLASS | opcode | operands |
|-------|--------|----------|
| `ulepc__URURUR` | 0x13ce | `URd` (PC only) |
| `ulepc__UR_I_R` | 0x19ce | `URd, target` (RSImm, resolved) |
| `ulepc_rel_` (ALT) | 0x19ce | `URd, sImm58, .REL` (relocatable) |

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x13ce / 0x19ce |
| [14:12]/[15] | `Pg`/`Pg_not` | uniform-predicate guard (7=UPT hidden) |
| [21:16] | `URd` | dest uniform reg, 64-bit pair (even-aligned, ≤MAX_UREG-2) |
| [81:24] | `sImm58` | signed PC offset (0x19ce); target = (PC+16)+imm |
| [112:110] | `dst_wr_sb` | pinned 0x7 (fixed-latency) |
| [124:122]∥[109:105] | `opex` | scheduling |

## Cross-comparison vs LEPC
| | **LEPC** (int_pipe) | **ULEPC** (udp_pipe) |
|--|---------------------|----------------------|
| dest | GPR pair `Rd`[23:16] (8-bit) | uniform reg pair `URd`[21:16] (6-bit) |
| opcodes | 0x34e / 0x94e | 0x13ce / 0x19ce |
| guard | predicate | uniform predicate |
| use | per-thread PC address | warp-uniform PC address |
| observed | yes (printf return addr) | no direct capture |

Field positions (`sImm58`, guard, pinned `dst_wr_sb`) are otherwise identical.

## Latency (from sm_90_latencies.txt)
`udp_pipe`, fixed-latency `COUPLED_MATH`. `OP_ULEPC = {ULEPC, ULEPCudp_pipe}`, grouped with
`UMOV` (`UMOV_ULEPC`) and part of `ULDC_VOTEU_UMOV_ULEPC` for the `TABLE_*(UGPR)` URd-producer
latency rows.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64 | Reconstruction |
|------|------|----------------|
| `0x00000000000473ce` | `0x0000000008000000` | `ULEPC UR4` |
| `0x00000001000679ce` | `0x0000000008000000` | `ULEPC UR6, 0x100` |
| `0x00000000100679ce` | `0x0000000008000000` | `ULEPC UR6, 0x130` (addr 0x110, LEPC-style) |

Decoder + round-trip test: `tools/decode_ulepc.py`.

## Open questions
- **No real vector**: unconfirmed cuobjdump text form and which uniform-CALL/relative path emits
  it. The resolved-target convention is assumed identical to LEPC's (verified there).
