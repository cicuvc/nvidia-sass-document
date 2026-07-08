# CALL — Function call (push return address, branch to callee)

**Opcode mnemonics (7 opcodes / 12 CLASSes):** rel-imm `CALL` = **0x944**; abs-imm = **0x943**; abs-const = **0xb43**; abs-reg = **0x343**; rel-reg = **0x344**; abs-ureg = **0x1943**; rel-ureg = **0x1944** | **Pipe:** `cbu_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` | **BRANCH_TYPE:** `BRT_CALL` | **MEM_SCBD_TYPE:** `BB_ENDING_INST`

The subroutine-call branch: transfers control to the callee and arranges for a matching
`RET` to resume at the instruction after the `CALL`. Mirrors the BRA/JMP/BRX target
families (relative-imm, absolute-imm/const, register, uniform-register).

## Semantics
`@Pg CALL.{REL|ABS}[.NOINC] {Pp,} <target>` calls the target for lanes where `Pg` holds.
- `.REL` / `.ABS` — the target family: `.REL` = PC-relative (`target = PC+0x10 + sImm*4`),
  `.ABS` = absolute (raw `sImm*4`, or a constant-bank / register value).
- `depth` [86] = `CALL_DEPTH` {`INC`=0 (default, hidden), `NOINC`=1 → `.NOINC`}: whether
  the hardware **API call-depth counter** (the `CBU_STATE.API_CALL_DEPTH` slot backing the
  on-chip return-address stack) is incremented.
- `Pp` is the divergence predicate; may raise `API_STACK_ERROR`.

**Real ptxas ABI (sm_90/CUDA 13.1):** always `CALL.REL.NOINC` paired with
`RET.REL.NODEC Rxx` — the return address is carried in a **GPR** (e.g. `R20`), not the HW
call-depth stack, so both sides skip the counter (`NOINC`/`NODEC`).

## Variant overview
| opcode `{b91,[11:0]}` | family | target |
|-----------------------|--------|--------|
| 0x0944 (+`_rel_imm_` alt) | REL | imm (56-bit, PC-relative) |
| 0x0344 (+`_rel_reg_` alt) | REL | `Ra` [31:24] + off |
| 0x1944 | REL | `URa` [29:24] + off |
| 0x0943 | ABS | imm (55-bit, absolute) |
| 0x0b43 | ABS | `c[bank][off]` (const bank) |
| 0x0343 | ABS | `Ra` [31:24] + off |
| 0x1943 | ABS | `URa` [29:24] + off |

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | b9 sets abs(1)/rel(0)-ish family; b91 → uniform |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate |
| [89:87]/[90] | `Pp`(`Pnz`)/`Pp_not` | divergence predicate (printed if ≠ PT) |
| [86] | `depth` `CALL_DEPTH` | 0=INC (hidden), 1=`.NOINC` |
| [81:34]∥[23:16] | `sImm` | target/offset, SCALE 4 (abs-imm uses [80:34], 55-bit) |
| [58:54] / [53:40] | const bank / offset | abs-const only; off = `sx14*4` |
| [31:24] | `Ra` | reg forms (RZ=255, 64-bit pair) |
| [29:24] | `URa` | ureg forms (URZ=63) |

### Target/offset rendering
- **imm:** always shown. `.ABS` → raw `sImm*4`; `.REL` → `PC+0x10 + sImm*4` (resolved).
- **const:** `c[bank][sx14([53:40])*4]` (signed).
- **reg/ureg:** `.ABS` shows offset as raw `sImm*4` and **omits it when `sImm==0`**;
  `.REL` shows the PC-resolved offset **always** (even `sImm==0` → prints `PC+0x10`).
- All offsets masked to 40 bits.

## Cross-comparison
| | BRA | JMP | BRX | **CALL** | RET |
|--|-----|-----|-----|----------|-----|
| role | branch | jump | indirect jump | **call (save return)** | return |
| BRANCH_TYPE | BRT_BRANCH | BRT_BRANCH | — | **BRT_CALL** | BRT_RETURN |
| MEM_SCBD_TYPE | — | — | — | **BB_ENDING_INST** | BB_ENDING |
| RPC_WRITERS / CBU_OPS_WITH_REQ | y/BRA-only | y/n | y/y | **y / y** | y/y |
| extra error | — | — | OOR/MISALIGN | **API_STACK_ERROR** | — |

## Latency
`cbu_pipe` = `BRU_OPS`. `RPC_WRITERS` → **9-cycle** RPC true-dependency
(`sm_90_latencies.txt:411,414`); `CBU_OPS_WITH_REQ` (honor `&req=`). `DECOUPLED_BRU`,
`MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_call.py`)
Self-test 8/8; **8494/8494 CALL in libcublas decoded byte-exact**; my `tests/call_test.cu`
(noinline + recursion) emits `CALL.REL.NOINC` (4/4); other families via cubin-patch, with
a **randomized battery of 350 patched encodings decoded 100%**.

| PC | Lo64 | Hi64 | Disassembly | src |
|----|------|------|-------------|-----|
| 0x0170 | 0x0000007800207944 | 0x000fea0003c00000 | `CALL.REL.NOINC 0x7a00` | libcublas |
| 0x00e0 | 0x0000000400240943 | 0x000fea0003800000 | `@P0 CALL.ABS 0x490` | patch |
| 0x00e0 | 0x0000000400240943 | 0x000fea0003c00000 | `@P0 CALL.ABS.NOINC 0x490` | patch |
| 0x00e0 | 0x0000400000000b43 | 0x000fea0003800000 | `@P0 CALL.ABS c[0x0][0x100]` | patch |
| 0x00e0 | 0x0000000404240343 | 0x000fea0003800000 | `@P0 CALL.ABS R4 0x490` | patch |
| 0x00e0 | 0x0000000400240944 | 0x000fea0003800000 | `@P0 CALL.REL 0x580` | patch |
| 0x00e0 | 0x0000000404240344 | 0x000fea0003800000 | `@P0 CALL.REL R4 0x580` | patch |

Hand-check `CALL.REL.NOINC 0x7a00`@0x170: opcode 0x944, depth[86]=1→`.NOINC`,
`sImm=(30<<8)|0x20=0x1e20`, `0x180 + 0x1e20*4 = 0x7a00`. ✓

### PTX→SASS mapping
Non-inlined `__noinline__`/recursive `__device__` functions → `CALL.REL.NOINC <callee>`;
the return address is materialized in a GPR and consumed by `RET.REL.NODEC Rxx` (register
ABI, HW call-depth stack unused). Most device functions are inlined and emit no CALL.

## Open questions
- `CALL.INC`/register-stack returns (`RET` without `.NODEC`) are spec-supported but not
  emitted by the sampled ptxas; only the register-ABI `.NOINC`/`.NODEC` path is observed.
- Absolute/const/uniform CALL forms are unexercised by ptxas here (verified only via
  patching); their real ABI usage (e.g. indirect/virtual calls) is unobserved.
