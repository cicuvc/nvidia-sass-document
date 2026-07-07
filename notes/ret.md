# RET — Return from subroutine

**Opcode mnemonics:** `RET` (reg) = `0b100101010000` = **0x950**; (uniform reg) = **0x1950** | **Pipe:** `cbu_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` | **BRANCH_TYPE:** `BRT_RETURN` | **MEM_SCBD_TYPE:** `BB_ENDING_INST`

The counterpart to `CALL`: returns control to the caller, resuming at the address held in
a register (`ISRC_A_SIZE = 64` → `Ra`/`URa` is a 64-bit register pair holding the return
PC) plus an immediate displacement.

## Semantics
`@Pg RET.{REL|ABS}[.NODEC] {Pp,} R<Ra> 0x<off>` returns for lanes where `Pg` holds.
- `.REL` / `.ABS` (`addr` bit [85]) — displacement family: `.REL` = PC-relative
  (`off = PC+0x10 + sImm*4`), `.ABS` = raw `sImm*4`.
- `depth` [86] = `RET_DEPTH` {`DEC`=0 (default, hidden), `NODEC`=1 → `.NODEC`} — whether
  the hardware **API call-depth counter** is decremented (the pop matching `CALL`'s INC).
- `Pp` is the divergence predicate.

**Real ptxas ABI (sm_90/CUDA 13.1):** always `RET.REL.NODEC R<n>` — the return address is
carried in a **GPR** (paired with `CALL.REL.NOINC`), so the HW call-depth stack is unused
(`NODEC`/`NOINC`). The printed offset resolves to `0x0` because the real target is the
register value; the immediate is a PC-relative displacement chosen so `PC+0x10+sImm*4 = 0`.

## Variant overview (8 CLASSes / 2 opcodes)
| opcode `{b91,[11:0]}` | reg | classes |
|-----------------------|-----|---------|
| 0x0950 | `Ra` [31:24] | `ret__REL`, `ret__ABS`, `ret_rel__RIR`, `ret_rel_reg__RIR` |
| 0x1950 | `URa` [29:24] | `ret__REL_UR`, `ret__ABS_UR`, `ret_rel__URIR`, `ret_rel_reg__URIR` |

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | b91=1 → uniform-register form (0x1950) |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | divergence predicate (printed if ≠ PT) |
| [86] | `depth` `RET_DEPTH` | 0=DEC (hidden), 1=`.NODEC` |
| [85] | `addr` `RET_ADDR` | 0=`.REL`, 1=`.ABS` (encoded as `ignoreKill`/`*addr`) |
| [81:34]∥[23:16] | `sImm` | displacement, 56-bit signed, SCALE 4 |
| [31:24] | `Ra` | return-address GPR pair (RZ=255) |
| [29:24] | `URa` | uniform form |

Offset rendering: `.REL` → `(PC+0x10 + sImm*4) & 0xffffffffff`; `.ABS` → `(sImm*4) &
0xffffffffff`. Always shown (unlike BRX/CALL.ABS reg, RET does not omit a zero offset).

## Cross-comparison (CALL ↔ RET)
| | CALL | **RET** |
|--|------|---------|
| role | push return addr, branch to callee | pop / branch to return addr in reg |
| depth field | `CALL_DEPTH` INC/NOINC [86] | `RET_DEPTH` DEC/NODEC [86] |
| addr modes | ABS/REL + const/imm/reg/ureg | REL/ABS × reg/ureg only |
| BRANCH_TYPE | BRT_CALL | **BRT_RETURN** |
| ptxas ABI form | `CALL.REL.NOINC <callee>` | `RET.REL.NODEC R<n> 0x0` |

Both `RPC_WRITERS` (9-cyc RPC), `CBU_OPS_WITH_REQ` (honor `&req=`), `BB_ENDING_INST`,
`DECOUPLED_BRU`, `MIN_WAIT_NEEDED=1`.

## Latency
`cbu_pipe` = `BRU_OPS`; `RPC_WRITERS` → **9-cycle** RPC true-dependency
(`sm_90_latencies.txt:411,414`).

## Verified encodings (decoder: `tools/decode_ret.py`)
Self-test 5/5; **1228/1228 RET in libcublas decoded byte-exact**; `tests/call_test.cu`
emits `RET.REL.NODEC R20/R6` (2/2); ABS/ureg/DEC forms via cubin-patch with a
**randomized battery of 350 patched encodings decoded 100%**.

| PC | Lo64 | Hi64 | Disassembly | src |
|----|------|------|-------------|-----|
| 0x0320 | 0xfffffffc14347950 | 0x004fec0003c3ffff | `RET.REL.NODEC R20 0x0` | call_test |
| 0x0370 | 0xfffffffc06207950 | 0x000fec0003c3ffff | `RET.REL.NODEC R6 0x0` | call_test |
| 0x00e0 | 0x0000000404240950 | 0x000fea0000200000 | `@P0 RET.ABS P0, R4 0x490` | patch |
| 0x00e0 | 0x0000000404240950 | 0x000fea0000000000 | `@P0 RET.REL P0, R4 0x580` | patch |
| 0x00e0 | 0x0000000404241950 | 0x000fea0008400000 | `@P1 RET.REL.NODEC P0, UR4 0x580` | patch |

Hand-check `RET.REL.NODEC R20 0x0`@0x320: opcode 0x950; depth[86]=1→`.NODEC`;
addr[85]=0→`.REL`; `Ra`[31:24]=0x14→R20; `sImm=-0xcc`, `0x330 + (-0xcc)*4 = 0`. ✓

### PTX→SASS mapping
Every non-inlined `__device__` function ends in `RET.REL.NODEC R<n>` where `R<n>` (a
64-bit pair) holds the caller-provided return address; pairs with `CALL.REL.NOINC`.

## Open questions
- `.DEC` (HW call-depth-stack returns) and `.ABS` returns are spec-supported but not
  emitted by the sampled ptxas (register ABI uses `.REL.NODEC` exclusively).
- The uniform-register (`URa`) RET forms are unexercised by ptxas here (patch-verified
  only); their ABI use case is unobserved.
