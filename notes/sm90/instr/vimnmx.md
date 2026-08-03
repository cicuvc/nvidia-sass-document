# VIMNMX — Vector Integer Min/Max

**Opcode mnemonic:** VIMNMX  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Vector integer minimum/maximum operation: `Rd = min(Ra, Rb) / max(Ra, Rb)` (direction selected by `Pp@not`: `PT` = min, `!PT` = max; `fmt` only selects signedness). The `.RELU` modifier clamps the result to ≥0 (rectified linear unit activation).

Standard form: `VIMNMX.U32 Rd, Ra, Rb, PT` (or `S32` for signed comparison).  
RELU form: `VIMNMX.RELU Rd, Ra, Rb, PT` — same as U32 but clamps negative results to 0.

Widely used in CUDA DL kernels and integer clamping operations.

**Correction (silicon-verified sm_120, `tests/asm_construct/test_vimnmx.py`):**
the 4-operand sm_120 form's `Pp` slot is **direction-only** and does **not**
write the predicate. `PT`/`!PT` → min/max (the only form ptxas emits).
With a real destination predicate (`P0`..`P6`) the min/max **sense flips**:
`P0..P6` compute **max**, `!P0..!P6` compute **min**, and the predicate is
left unchanged (pre-setting `P0=1` survives the instruction). The
predicate-*output* capability lives in the separate 6-operand
`vimnmx_pred_*` form (sm_90 spec; sm_120 VIMNMX exposes only the 4-operand
form), where `Pu`/`Pv` report "Ra is the result source" and "Ra != Rb"
(same semantics as the Blackwell IMNMX extended form).

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

## SM120 verification (`tests/asm_construct/test_vimnmx.py`, RTX 5090)

sm_120 keeps 3 variants (RRR `0x248`, RIR `0x848`, RUR `0x1c48`; no const-bank
forms) with `FMT_vimnmx` → [74:72] (0=U32, 1=S32, 2=U16x2, 3=S16x2, 4=U8x4,
5=S8x4), `relu` → [76] (signed fmt only, enforced), `Pp` → [89:87] + `Pp@not`
→ [90]. The assembler reproduces the ptxas encodings bit-for-bit
(`VIMNMX.S32 R9, R2, R5, PT/!PT` with `[7:7:{2}:5:1]`).

Silicon-verified (15-case battery, all pass): U32/S32 min-max incl. negatives,
`.RELU` clamp-to-0, RIR immediate, RUR uniform register, U16x2 packed
min/max, the real-predicate direction flip above, and `Pp` not being written
by the 4-operand form.
