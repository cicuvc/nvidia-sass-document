# VIMNMX — Vector Integer Min/Max

**Opcode mnemonic:** VIMNMX  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Vector integer minimum/maximum operation: `Rd = min(Ra, Rb) / max(Ra, Rb)` (direction determined by fmt field). The `.RELU` modifier clamps the result to ≥0 (rectified linear unit activation). The predicate form outputs `Pp` indicating which operand was selected.

Standard form: `VIMNMX.U32 Rd, Ra, Rb, PT` (or `S32` for signed comparison).  
RELU form: `VIMNMX.RELU Rd, Ra, Rb, PT` — same as U32 but clamps negative results to 0.

Widely used in CUDA DL kernels and integer clamping operations.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `vimnmx__RRR` | `0x248` | `VIMNMX Rd, Ra, Rb, Pp` |
| `vimnmx__RIR` | `0x848` | `VIMNMX Rd, Ra, imm32, Pp` |
| `vimnmx__RCR` | `0xa48` | `VIMNMX Rd, Ra, c[bank][offset], Pp` |
| `vimnmx__RCxR` | `0x1a48` | `VIMNMX Rd, Ra, c[URb][offset], Pp` |
| `vimnmx__RUR` | `0x1c48` | `VIMNMX Rd, Ra, URb, Pp` |

Plus `vimnmx_pred_*` ALTs (different encoding of Pp output).

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| fmt | num | [73:72] | 0=U32(unsigned min/max), 1=S32(signed), 2/3=… |
| relu | memdesc | [76] | 0=norelu, 1=.RELU(clamp≥0) |

## Bit layout (RIR — opcode 0x848, most common form)

```
[90:90]              input_reg_sz <= Pp@not
[89:87]              Pnz          <= Pp (3-bit predicate)
[76:76]              memdesc      <= relu
[73:72]              num          <= fmt
[63:32]              Ra_offset    <= Sb (imm32)
[31:24]              Ra           <= Ra
[23:16]              Rd           <= Rd
[91:91],[11:0]       opcode       <= 0b100001001000
```

## Verified encodings

From `i2i_test.cu` (sm_90, CUDA 13.1):

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x000000ff02077848` | `0x004fca0003fe0000` | `VIMNMX.U32 R7, R2, 0xff, PT` |
| `0x000000ff02077848` | `0x004fca0003fe1100` | `VIMNMX.RELU R7, R2, 0xff, PT` |

The RELU variant sets bit [76]=1; the U32 variant sets fmt=0.

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. `FXU_OPS` group. Coupled scoreboard, standard integer-pipe latency.
