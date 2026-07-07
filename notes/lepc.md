# LEPC — Load Effective PC

**Opcode mnemonics:** `LEPC` = `0b1101001110` = **0x34e** (RRR, PC only) / `0b100101001110` = **0x94e** (R_I_R, PC+imm58) | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | sm_70 (RRR) + sm_90 variant (R_I_R)

Computes a PC-relative effective address into a 64-bit register pair `Rd:Rd+1`
(`IDEST_SIZE=64`, even-aligned, ≠R254). Verified on sm_90 via the **printf lowering**, where it
forms the **return address** for a manual `CALL.ABS.NOINC` to `vprintf`.

## Semantics (verified)
Observed idiom (printf → vprintf call):
```
/*0110*/  LEPC R20, 0x130        ; R20 = 0x130 = the address right after the CALL
/*0120*/  CALL.ABS.NOINC R8      ; call vprintf; NOINC = no auto return push
/*0130*/  <return point>         ; execution resumes here
```
`CALL.ABS.NOINC` does not push a return address, so ptxas materializes it explicitly with
`LEPC`. The printed operand is the **resolved absolute target**, computed as
`target = (instr_addr + 16) + sImm58` (next-instruction-relative). In the capture the raw
`sImm58 = 0x10` (one instruction width, spanning the CALL), so `0x110 + 0x10 + 0x10 = 0x130`.

Two forms:
- **`LEPC Rd`** (0x34e, RRR) — just the current PC. Classic sm_70 idiom
  (`LEPC Rd; … BRX Rd+off` jump tables). Not observed on sm_90 (BRX is self-relative there).
- **`LEPC Rd, sImm58`** (0x94e, R_I_R) — PC + 58-bit signed offset in one instruction (sm_90).
  The `RSImm` prints as a resolved target, not a raw offset.

The **`lepc_rel_`** ALT class shares opcode 0x94e and identical bits but uses a `/RelOpt` "REL"
modifier with a plain `SImm(58)` — the relocatable spelling (immediate supplied by a linker
relocation); it decodes to the same bits as R_I_R.

## Variant overview (3 CLASS, 2 opcodes)
| CLASS | opcode | operands | note |
|-------|--------|----------|------|
| `lepc__RRR`   | 0x34e | `Rd` | PC only (sm_70; not seen on sm_90) |
| `lepc__R_I_R` | 0x94e | `Rd, target` (RSImm, resolved) | PC+imm (sm_90) |
| `lepc_rel_` (ALT) | 0x94e | `Rd, sImm58, .REL` | relocatable form, same bits |

## Fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x34e / 0x94e | 13-bit |
| [14:12] / [15] | `Pg` / `Pg_not` | Pg guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | dest PC, 64-bit pair (even-aligned, ≠R254) |
| [81:24] | `sImm58` | (R)SImm(58) | signed PC offset (0x94e only); target = (PC+16)+imm |
| [124:122]∥[109:105] | `opex` | TABLES_opex_1(batch_t,usched_info) | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask | |
| [115:113] / [112:110] | `src_rel_sb` / `dst_wr_sb` | **pinned 0x7** | fixed-latency, no variable scoreboard |
| [103:102] | `pm_pred` | perfmon predicate | |

## Cross-comparison
| | **LEPC** (int_pipe) | **ULEPC** (idx 238, udp_pipe) |
|--|---------------------|-------------------------------|
| dest | GPR pair `Rd` | uniform reg (`URd`) |
| use | per-thread PC address | warp-uniform PC address |
| latency group | int_pipe COUPLED_MATH | `OP_ULEPC`, grouped with `UMOV` (`UMOV_ULEPC`) |

`ULEPC` is the uniform-datapath sibling (documented separately).

## Latency (from sm_90_latencies.txt)
`int_pipe`, fixed-latency `COUPLED_MATH` (scoreboards pinned 0x7). Produces a 64-bit GPR pair.
`ULEPC` sits in `OP_ULEPC`/`UMOV_ULEPC` and uses the `ULDC_VOTEU_UMOV_ULEPC` connector rows for
`TABLE_*(UGPR)` latencies.

## Verified encodings (sm_90, CUDA 13.1)
| Addr | Lo64 | Hi64 | Disassembly |
|------|------|------|-------------|
| 0x110 | `0x000000001014794e` | `0x000fce0000000000` | `LEPC R20, 0x130` |
| 0x1d0 | `0x000000001014794e` | `0x000fce0000000000` | `LEPC R20, 0x1f0` |

Raw `sImm58`=0x10 in both; the printed target differs only because the instruction address
differs (target = addr+16+imm). Decoder: `tools/decode_lepc.py` (real vectors + round-trips
pass). Test: `tests/lepc_test.cu` (printf).

### Round-trip only (not observed on sm_90)
`LEPC R2` (RRR, 0x34e), negative offsets — verified self-consistent via encode↔decode.

### PTX→SASS mapping
- `printf(...)` → sets up arg buffer, then `LEPC Rd, <ret>` + `CALL.ABS.NOINC <vprintf>` (LEPC
  supplies the return address that NOINC does not auto-push).

## Open questions
- Whether the R_I_R immediate ever prints as a raw offset or `.REL` relocatable form in other
  contexts (only the resolved-target vprintf-return case was captured).
- Whether `LEPC Rd` (RRR) is ever emitted on sm_90 (not seen; BRX/CALL are self-relative).
