# CLMAD — Carry-less (GF(2)) multiply-add

**Opcode mnemonic:** `CLMAD` = **0x22c** (RRR) + 6 operand-form variants | **Pipe:** `fma64lite_pipe` (shares the FP64 datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_EMULATABLE`, `VIRTUAL_QUEUE=$VQ_REDIRECTABLE` | since sm_82 (crucible idx 179)

Carry-less multiply-add over **GF(2)[x]** (polynomial arithmetic, no carries): multiply is
XOR-of-shifts, "add" is XOR. The building block for CRC and GF(2ᵏ) crypto (AES-GCM/GHASH) —
the GPU analog of x86 `PCLMULQDQ`.

> **Status: semantics authoritative, encoding spec-derived, NO real SASS capture.** PTX
> `clmad` requires **PTX ISA 9.3** but CUDA 13.1's ptxas caps at **9.1**
> (`Unsupported .version 9.3; current version is '9.1'`), so it cannot be emitted with this
> toolchain. Semantics below are from the PTX ISA doc (authoritative); the encoding is from the
> CLASS ENCODING; example encodings are round-trip constructions.

## Semantics (PTX `clmad.mode.u64 d, a, b, c`)
```
tmp[127:0] = 0
for i in 0..63: if (a>>i)&1: tmp ^= (b << i)     # carry-less 64x64 -> 128 product
d = (mode==.lo ? tmp[63:0] : tmp[127:64]) ^ c    # pick half, then carry-less add (XOR) c
```
`d = HILO(a ⊗ b) ⊕ c`, all operands unsigned 64-bit. `.LO`/`.HI` select the low/high 64 bits of
the 128-bit product. (Verified in the decoder: `clmul(x+1, x+1) = x²+1 = 0b101`.)

## Variant overview (7 CLASS variants — operand shape)
| opcode | form | B operand | C operand |
|--------|------|-----------|-----------|
| 0x22c  | RRR  | `Rb` reg [39:32] | `Rc` reg [71:64] |
| 0xa2c  | RCR  | const bank (Sb) | `Rc` reg |
| 0x1a2c | RCxR | const bank (extended addr) | `Rc` reg |
| 0x62c  | RRC  | `Rb` reg | const bank (Sc) |
| 0x162c | RRCx | `Rb` reg | const bank (extended) |
| 0x1c2c | RUR  | uniform `URb` [37:32] | `Rc` reg |
| 0x1e2c | RRU  | `Rb` reg [71:64] | uniform `URc` [37:32] |

Standard MAD operand family (reg / const-bank / uniform for the B and C sources). All operands
are **64-bit register pairs** (`IDEST/ISRC_A/B/C_SIZE = 64`), even-aligned, ≠R254.

## Modifiers / fields (128-bit, RRR)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x22c… | 13-bit; selects operand form |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | dest (64-bit pair) |
| [31:24] | `Ra` | Register | src A (64-bit pair) |
| [39:32] | `Rb` | Register | src B (RRR/RRC…); or `Ra_URb`[37:32] uniform |
| [71:64] | `Rc` | Register | src C (or Rb when C is const/uniform) |
| [58:54]/[53:40] | `Sb_bank`/`Sb_offset` | const-bank addr | const forms |
| [77] | `ntz` = `hilo` | `HILO` | 0=LO, 1=HI |
| [124:122]∥[109:105] | `opex` | TABLES_opex_4(batch_t,usched_info,reuse_a/b/c) | scheduling + `.reuse` |
| [121:116] | `req_bit_set` | scoreboard | |
| [115:113]/[112:110] | `src_rel_sb`/`dst_wr_sb` | scoreboards | |
| [103:102] | `pm_pred` | perfmon predicate | |

`HILO`: `LO=0, HI=1`. Source-reuse flags (`.reuse`) on Ra/Rb/Rc via `opex`.

## Pipe / latency (from sm_90_latencies.txt)
`fma64lite_pipe` — the FP64-lite datapath, shared with `DFMA/DADD/DMUL/DSETP/DMMA`. `CLMAD_OP =
{CLMAD, CLMADfma64lite_pipe}` is its own latency group (carved out of `FMALITE_OPS`). True-dep
latency ≈ **12–13** cycles (`TABLE_TRUE` `CLMAD_OP` row), i.e. FP64-pipe class, not a fast ALU
op. `COUPLED_EMULATABLE` = the op may be software-emulated on parts lacking the unit;
`VQ_REDIRECTABLE` lets it be dispatched to the FP64 unit.

## Constructed encodings (SYNTHETIC — round-trip only, not silicon-verified)
| Lo64 | Hi64 | Reconstruction |
|------|------|----------------|
| `0x000000060402722c` | `0x0000000000000008` | `CLMAD.LO R2, R4, R6, R8` |
| `0x000000060402722c` | `0x0000000000002008` | `CLMAD.HI R2, R4, R6, R8` |
| `0x00000002ff0a722c` | `0x00000000000000ff` | `CLMAD.LO R10, RZ, R2, RZ` |

Decoder + round-trip test: `tools/decode_clmad.py`. Test (does not compile on CUDA 13.1):
`tests/clmad_test.cu`.

### PTX→SASS mapping (expected)
- `clmad.lo.u64 d, a, b, c` → `CLMAD.LO Rd, Ra, Rb, Rc`
- `clmad.hi.u64 d, a, b, c` → `CLMAD.HI Rd, Ra, Rb, Rc`
- const/uniform B or C operands → the RCR/RRC/RUR/RRU forms.

## Open questions
- **No real SASS vector** (toolchain PTX cap 9.1 < 9.3). Unverified: exact cuobjdump text for
  const-bank/uniform forms, whether `.LO` is printed or hidden as default, and the reuse-flag
  rendering.
- Confirm the 12–13-cycle latency and whether both halves (`.LO`+`.HI`) are ever fused.
