# PRMT — Byte Permute

**Opcode mnemonic:** PRMT  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Permutes bytes across two source registers (or register+immediate/constant/UR) into a destination. The permute control is a 4-byte word where each byte selects a byte lane from the concatenated double-word `{Ra, Rc}` (or `{Ra, imm}` for immediate variants).

Common patterns:
- `PRMT Rd, Ra, 0x8880, RZ` — extract/splat byte 0 of Ra to all 4 bytes (byte broadcast / truncation)
- `PRMT Rd, Ra, 0x5410, Rb` — interleave bytes from Ra and Rb (packing)
- `PRMT Rd, Ra, 0x76543210, Rb` — identity (pass-through)
- `PRMT Rd, Ra, 0x4444, RZ` — extract byte 4 (sign-extension helper)

The `pmode` field selects the permute mode (IDX=0 on sm_90). Three source operands: Ra, Rb (or imm/const/UR), and the select/control operand (Rc or imm32). `.reuse` flags available on all register operands.

## Variant overview

| Variant | Opcode | Format (Third operand highlighted) |
|---------|--------|-----------------------------------|
| `prmt__RRR_RRR` | `0x216` | `PRMT Rd, Ra, Rb, Rc` |
| `prmt__RRuI_RRI` | `0x416` | `PRMT Rd, Ra, Rb, imm32` |
| `prmt__RIR` | `0x816` | `PRMT Rd, Ra, imm32, Rc` |
| `prmt__RRC` | `0x616` | `PRMT Rd, Ra, Rb, c[bank][offset]` |
| `prmt__RRCx` | `0x1616` | `PRMT Rd, Ra, Rb, c[UR][offset]` |
| `prmt__RCR` | `0xa16` | `PRMT Rd, Ra, c[bank][offset], Rc` |
| `prmt__RCxR` | `0x1a16` | `PRMT Rd, Ra, c[UR][offset], Rc` |
| `prmt__RUR` | `0x1c16` | `PRMT Rd, Ra, URb, Rc` |
| `prmt__RRU` | `0x1e16` | `PRMT Rd, Ra, Rb, URc` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| pmode | pmode | [74:72] | IDX=0 (indexed mode) |

## Bit layout

### RRR (opcode 0x216)

```
[74:72]         pmode    <= pmode
[71:64]         Rc       <= Rc (permute control, 8-bit register)
[39:32]         Rb       <= Rb (second source)
[31:24]         Ra       <= Ra (first source)
[23:16]         Rd       <= Rd
[91:91],[11:0]  opcode   <= 0b1000010110
```

### RIR (opcode 0x816) — most common ptxas form

```
[74:72]         pmode    <= pmode
[71:64]         Rc       <= Rc (third source register, often RZ=255)
[63:32]         Ra_offset <= imm32 (permute control)
[31:24]         Ra       <= Ra
[23:16]         Rd       <= Rd
[91:91],[11:0]  opcode   <= 0b100000010110
```

## Verified encodings

From `i2i_direct.cu` (sm_75, CUDA 13.1):

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000888002077816` | `0x004fd000000000ff` | `PRMT R7, R2, 0x8880, RZ` |

## Empirical notes

PRMT is the workhorse for integer width conversions on modern architectures. ptxas replaces I2I, narrow integer truncation, and byte extraction with PRMT sequences:
- `cvt.u16.u32` → `PRMT Rd, Ra, 0x8880, RZ`
- `cvt.u8.u32` → `PRMT Rd, Ra, 0x8880, RZ` (same encoding, 8-bit implicit)

Common immediate patterns:
- 0x8880 = select byte 0, replicate 4 times (broadcast/truncate)
- 0x5410 = bytes 0,1,4,5 (pack two 16-bit values)
- 0x76543210 = identity (all 4 bytes pass through)

## Cross-comparison

| Property | PRMT | UPRMT |
|----------|------|-------|
| Pipe | `int_pipe` | `udp_pipe` |
| Registers | Regular (Rd,Ra,Rb,Rc) | Uniform (URd,URa,URb,URc) |
| Opcode base | `0x216` | `0x1296` |
| Immediate variant | 0x816 (most common) | 0x1896 |

## Latency

`int_pipe`, `FXU_OPS` group. Standard integer-pipe latency (1 cycle typical). Coupled scoreboard.

## Resolved: silicon-verified semantics + operand-order correction (SM120)

`tests/asm_construct/test_prmt.py` (34 cases) + `tools/decode_*` round-trip.
**Critical correction to the spec-derived operand order** — the SASS form is
`PRMT Rd, Ra, Rb, Rc` with **Rb = SELECTOR and Rc = source B**:

| form | opcode | syntax | roles |
|------|--------|--------|-------|
| RRR  | 0x216  | `PRMT Rd, Ra, Rb, Rc` | Ra=srcA, **Rb=selector**, Rc=srcB |
| RIR  | 0x816  | `PRMT Rd, Ra, imm, Rc` | Ra=srcA, **imm=selector**, Rc=srcB |
| RRuI | 0x416  | `PRMT Rd, Ra, Rb, imm` | Ra=srcA, **Rb=selector**, imm=srcB |

The selector is the THIRD operand (or imm), source B is the FOURTH.  This
only surfaced under silicon test — the ptxas RRR emission puts sel in the 4th
slot, but the hardware reads the 3rd as selector (ptxas arranges its operands
accordingly).  Wrong order silently permutes the wrong registers.

IDX selector: 16-bit, LSB-first nibbles (c[3:0] -> d.b0 ... c[15:12] -> d.b3).
nibble 0-7 = copy source byte n; nibble 8-15 = sign-extend byte (n-8): the
output byte becomes 0xFF if the source byte's bit 7 is set, else 0x00.

Specialized modes (F4E/B4E/RC8/ECL/ECR/RC16): all four outputs use the SAME
selector c[1:0], picking a fixed 4-row pattern (verified for all 4 rows each).

Hand-assembler gotchas: PRMT is int_pipe COUPLED_MATH — no own scoreboard
(dst_wr_sb=*7); load all inputs (incl. the selector) with `wr=SB1` and let
`PRMT req={1}` wait, or MOV32I+NOPs.  The result writeback needs a few
instructions before an immediate store reads it.

## PRMT -> STG back-to-back: minimum stall = 0

Measured on SM120: `PRMT R10, R0, R4, R1` immediately followed by
`STG.E ..., R10` (no NOP / no intervening instruction) produces the correct
result at **every** stall 0..15.  There is no functional minimum — stall=0
works.  The LSU's data-read stage lands after the int_pipe PRMT writeback, so
the consumer does not need a scheduler gap.

Caveats that DO matter (separate from the data path):
- The PRMT stall gates its *inputs* (the `req={1}` waits on the LDC-loaded
  sources), not the PRMT->STG output gap.
- The result STG must still see a valid descriptor (UR4) and address (R2):
  in the minimal kernel (STG with `req={}` as the FIRST store) the descriptor/
  address loads weren't reliably landed and faulted 700.  Either give them
  their own scoreboards and `req` them, or let earlier stores (which waited
  `req={1}`) land them first.
- Valid stall range for PRMT is 0..15; stall=16 encodes an illegal
  batch_t/usched_info combo (TABLES_opex_7) — rejected at assemble time.
