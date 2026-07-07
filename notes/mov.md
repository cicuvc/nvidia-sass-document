# MOV — Move Register

**Opcode mnemonic:** MOV  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Moves data into a register: `Rd = Rb` (or `Rd = imm32` / `Rd = c[bank][offset]` / `Rd = URb`). The destination register Rd can optionally target a specific pixel/channel mask via the `PixMask` field (4-bit, default 0xf = all channels).

Supports `.reuse` on the source operand for pipeline optimization (officially exposed in CUDA inline PTX).

## Variant overview

| Variant | Opcode | Format | Bits |
|---------|--------|--------|------|
| `mov__RR` | `0x202` | `MOV Rd, Rb, PixMask` | [39:32]=Rb, [23:16]=Rd |
| `mov__RI` | `0x802` | `MOV Rd, imm32, PixMask` | [63:32]=imm |
| `mov__RC` | `0xa02` | `MOV Rd, c[bank][offset], PixMask` | ConstBankAddress |
| `mov__RCx` | `0x1a02` | `MOV Rd, c[URb][offset], PixMask` | Extended const |
| `mov__RU` | `0x1c02` | `MOV Rd, URb, PixMask` | [39:32]=URb |
| `mov_indexedRF_IRFd__Rb` | `0x1478` | `MOV URd[R], Rb, PixMask` | Indexed reg file |
| `mov_indexedRF_IRFd__Ib` | `0x1878` | `MOV URd[R], imm32, PixMask` | Indexed imm |
| `mov_indexedRF_IRFd__Cb` | `0x1a78` | `MOV URd[R], c[bank][offset], PixMask` | Indexed const |
| `mov_indexedRF_Rd_` | `0x1c78` | `MOV Rd, R[URb], PixMask` | Reversed indexed |

## Bit layout (RR — opcode 0x202)

```
[75:72]              PixMaskU04 <= PixMask (4-bit, default 0xf)
[39:32]              Rb         <= Rb (8-bit register)
[23:16]              Rd         <= Rd (8-bit register)
[15:15]              Pg_not     <= Pg@not
[14:12]              Pg         <= Pg
[91:91],[11:0]       opcode     <= 0b1000000010
```

RI variant: Rb replaced with 32-bit immediate at [63:32].

## Key features

- `PixMask` / `PixMaskU04`: 4-bit field (default 0xf = all four 8-bit channels). Used for pixel-shader channel select, but present on all MOV variants including compute.
- `.reuse`: Pipeline optimization flag embedded in opex bits, controlled by `TABLES_opex_7`.
- **Indexed Register File**: `mov_indexedRF_*` variants access `URd[R]` — uniform-register-indexed register file, used for parameter/constant spilling.

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. Falls under `FXU_OPS` group in GPR tables (same as basic int ALU ops). Output latency: 1 cycle typical.
