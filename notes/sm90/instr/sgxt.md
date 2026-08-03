# SGXT — Sign/zero-extend from a bit position

**Opcode mnemonic:** `SGXT` = `0b1000011010` = **0x21a** (RRR) + 4 operand-form variants | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70

SASS lowering of PTX `szext.mode.type` — takes the low **N** bits of `Ra` (N = the value in the
third operand) and sign-extends (S32) or zero-extends (U32) them to 32 bits. Uniform twin:
`USGXT` (see `usgxt.md`).

## Semantics (verified PTX→SASS)
`szext.mode.type d, a, b` → `SGXT[.W][.U32] Rd, Ra, Rb` where:
| PTX | SASS | field |
|-----|------|-------|
| `.s32` (sign-extend, default) | (hidden) | `fmt`=S32 |
| `.u32` (zero-extend) | `.U32` | `fmt`=U32 |
| `.clamp` (default) | (hidden) | `cw`=C |
| `.wrap` | `.W` | `cw`=W |

N = `Rb` (unmasked). For `.s32`, bit (N−1) of `Ra` is replicated up to bit 31; for `.u32`, bits ≥N
are cleared. N=0 → 0. N≥32: `.clamp` returns `Ra` unchanged (N is **not** masked to 5 bits —
verified with N=32, 33 and 0xFFFFFFFF), `.wrap` uses N mod 32 (N=32→0, N=33→1, 0xFFFFFFFF→31).

## Variant overview (5 CLASS variants — position operand shape)
| opcode | form | position operand |
|--------|------|------------------|
| 0x21a  | RRR  | `Rb` register [39:32] |
| 0x81a  | RsIR | immediate [63:32] |
| 0xa1a  | RCR  | const bank c[bank][off] |
| 0x1a1a | RCxR | const bank, extended |
| 0x1c1a | RUR  | uniform register `URb` [37:32] |

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x21a… | selects operand form |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | result |
| [31:24] | `Ra` | Register | value to extend |
| [39:32] | `Rb` | Register | bit width N (RRR; `.reuse` supported) |
| [63:32] | `Sb` | immediate | width N (RsIR) |
| [37:32] | `Ra_URb` | uniform | width N (RUR) |
| [75] | `cw` | `CWMode` | C=0 (clamp, default), W=1 (wrap) |
| [73] | `sz`=`fmt` | `REDUX_SZ` | U32=0, **S32=1 (default)** |

`Rd`/`Ra`/`Rb` ≠ R254. IDEST/ISRC_A/ISRC_B = 32.

## Cross-comparison
| op | operation | note |
|----|-----------|------|
| **SGXT** | sign/zero-extend low N bits (variable N) | PTX `szext` |
| **BFE** | bitfield extract (pos+len) | PTX `bfe` |
| **SHF.L + SHF.R.S32** | `(x<<s)>>s` sign-extend | ptxas' preferred idiom for fixed-width |
| **USGXT** | uniform-register SGXT | uniform datapath |

Note: from plain C (signed bitfields, narrow casts) ptxas emits the **SHF** shift idiom, not
SGXT; SGXT appears when PTX `szext` is used explicitly (or from some library codegen).

## Latency (from sm_90_latencies.txt)
`int_pipe` (FXU_OPS), fixed-latency `COUPLED_MATH`.

## Verified encodings (sm_90, CUDA 13.1 — via `szext` inline asm)
| Lo64 | Hi64 | Disassembly | PTX |
|------|------|-------------|-----|
| `0x0000000d0207781a` | `0x004fca0000000200` | `SGXT R7, R2, 0xd` | `szext.clamp.s32 …,13` |
| `0x000000050209721a` | `0x008fca0000000200` | `SGXT R9, R2, R5` | `szext.clamp.s32` |
| `0x000000050209721a` | `0x008fca0000000a00` | `SGXT.W R9, R2, R5` | `szext.wrap.s32` |
| `0x000000050209721a` | `0x008fca0000000000` | `SGXT.U32 R9, R2, R5` | `szext.clamp.u32` |
| `0x000000050209721a` | `0x008fca0000000800` | `SGXT.W.U32 R9, R2, R5` | `szext.wrap.u32` |

(op/mode differ only in Hi64: `cw`[75]=bit11, `fmt`[73]=bit9.) Decoder:
`tools/decode_sgxt.py` (real vectors + uniform round-trip pass). Test: `tests/sgxt_test.cu`.

### PTX→SASS mapping
- `szext.clamp.s32` → `SGXT` (defaults) · `szext.wrap.s32` → `SGXT.W`
- `szext.clamp.u32` → `SGXT.U32` · `szext.wrap.u32` → `SGXT.W.U32`

## Open questions
- Const-bank (RCR/RCxR) text form unverified (only RRR/imm/uniform paths exercised).

## SM120 verification (`tests/asm_construct/test_sgxt.py`, RTX 5090)

sm_120 keeps 3 variants (RRR `0x21a`, RIR `0x81a`, RUR `0x1c1a`; RCR/RCxR
dropped). The assembler reproduces the ptxas `szext` encodings bit-for-bit
(`SGXT[.W][.U32] R7, R4, 0x5` with `[7:7:{3}:5:1]` — cw [75], fmt [73]).
Silicon-verified 16-case battery + RUR (3 concurrent blocks): sign/zero
extension for N=1..31, N=0 → 0, clamp N≥32 → `Ra` unchanged, wrap N mod 32,
register (RRR) and uniform (RUR) width operands.
