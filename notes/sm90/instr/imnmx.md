# IMNMX — Integer Min/Max (legacy)

**Opcode mnemonic:** `IMNMX`  
**Pipe:** `int_pipe`  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

**NOTE:** On sm_90, ptxas emits **VIMNMX** (opcode 0x248), not IMNMX. IMNMX
(opcode 0x217) appears to be a legacy encoding without `.RELU` support.
Both share the same pipe and operand structure.

---

## Semantics

`Rd = MIN(MAX)(Ra, Rb)` — two-operand integer min/max on 32-bit values,
with a predicate output `Pp`.

Signed vs unsigned is controlled by the `REDUX_SZ` modifier:
- `S32`(1): signed comparison
- `U32`(0): unsigned comparison

The min/max sense is selected by `Pp@not` (same as FMNMX):
- `Pp@not=1` (`!PT` in disasm) → **MAX**
- `Pp@not=0` (`PT` in disasm) → **MIN**

## Variant overview — 5 variants

| Variant | Opcode (13b) |
|---------|:-----------:|
| `imnmx__RRR_RRR` | 0x217 |
| `imnmx__RIR_RsIR` | 0x817 |
| `imnmx__RCR_RCR` | 0xa17 |
| `imnmx__RCxR_RCxR` | 0x1a17 |
| `imnmx__RUR_RUR` | 0x1c17 |

No `_pred` variants (cf. FMNMX which has 5 base + 5 pred = 10).

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **fmt** (REDUX_SZ) | [73] | `U32`(0), `S32`(1) |

No ftz/nan/xorsign modifiers (integer semantics, not FP).

## Bit layout (RRR_RRR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 92: 91]               -- gap --
[91],[11:0]             opcode       (13b)
[90]                    Pp.not       (1b: min→0, max→1)
[89:87]                 Pp           (3b: output predicate, 7=PT=discard)
[86:74]                 -- gap --       ← large gap (no nan/ftz/xorsign/Pu/isA)
[73]                    fmt          (1b: REDUX_SZ: 0=U32, 1=S32)
[72:40]                 -- gap --
[39:32]                 Rb           (8b)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not
[14:12]                 Pg           (3b: predicate, 7=PT)
```

## IMNMX vs VIMNMX comparison

| Aspect | IMNMX (0x217) | VIMNMX (0x248) |
|--------|:------------:|:-------------:|
| Variants | 5 (base only) | 10 (5 base + 5 pred) |
| RELU modifier | No | Yes (`.RELU`) |
| FMT enum | `REDUX_SZ` (U32/S32) | `FMT_viaddmnmx` (U32/S32) |
| Emitted by ptxas? | **No** | **Yes** |
| cublas usage | None found | Common |

VIMNMX is the active version — from cublas:
```
VIMNMX R16, R2, R7, PT          ; max(R2, R7) → R16
VIMNMX R0, R0, R3, PT           ; min(R0, R3) → R0 (our kernel)
VIMNMX.U32 R0, R0, R3, PT       ; unsigned min
VIMNMX R0, R0, R3, !PT          ; max
VIMNMX.U32 R0, R0, R3, !PT      ; unsigned max
```

### Encoding verification (VIMNMX from kernel)

All VIMNMX variants share lo64=`0x0000000300007248` (opcode 0x248), with
hi64 encoding the S32/U32 (bit 8 of hi64) and !PT/PT (bit 26 of hi64) selectors.

| hi64 | Disassembly |
|------|-------------|
| `0x004fe20003fe0100` | VIMNMX R0, R0, R3, PT (S32 min) |
| `0x004fe20007fe0100` | VIMNMX R0, R0, R3, !PT (S32 max) |
| `0x004fe20003fe0000` | VIMNMX.U32 R0, R0, R3, PT (U32 min) |
| `0x004fe20007fe0000` | VIMNMX.U32 R0, R0, R3, !PT (U32 max) |
| `0x000fe40003fe0100` | VIMNMX R16, R2, R7, PT (cublas) |

### PTX→SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `max.s32 d, a, b` | `VIMNMX d, a, b, !PT` |
| `min.s32 d, a, b` | `VIMNMX d, a, b, PT` |
| `max.u32 d, a, b` | `VIMNMX.U32 d, a, b, !PT` |
| `min.u32 d, a, b` | `VIMNMX.U32 d, a, b, PT` |

## Latency

IMNMX is on `int_pipe`; same latency class as FXU_OPS: TABLE_TRUE 6–8, TABLE_OUTPUT 1–2, TABLE_ANTI 1–2.

## Verified encodings (cuobjdump, sm_75)

4/4 matches. IMNMX is emitted by ptxas on **sm_75** (arch=sm_75) but not sm_90
(which emits VIMNMX instead). Test kernel: `tests/imnmx_test.cu`; decoder: `tools/decode_imnmx.py`.

| hi64 | Disassembly |
|------|-------------|
| `0x004fca0003800200` | IMNMX R0, R0, R3, PT (S32 min) |
| `0x004fca0007800200` | IMNMX R0, R0, R3, !PT (S32 max) |
| `0x004fca0003800000` | IMNMX.U32 R0, R0, R3, PT (U32 min) |
| `0x004fca0007800000` | IMNMX.U32 R0, R0, R3, !PT (U32 max) |

REDUX_SZ (fmt) at hi64 bit 9: 1=S32, 0=U32. Pp.not at hi64 bit 26.

### PTX→SASS mapping (sm_75)

| PTX | SASS |
|-----|------|
| `max.s32 d, a, b` | `IMNMX d, a, b, !PT` |
| `min.s32 d, a, b` | `IMNMX d, a, b, PT` |
| `max.u32 d, a, b` | `IMNMX.U32 d, a, b, !PT` |
| `min.u32 d, a, b` | `IMNMX.U32 d, a, b, PT` |

Same semantics as VIMNMX on sm_90, but without the `.RELU` modifier and
`_pred` variant.

## Open questions

- What triggers the VIMNMX `_pred` variant (with Pu predicate input)?
- Does VIMNMX `.RELU` map to PTX `min.relu.s32` or is it only for certain reduction patterns?
- At what architecture boundary (sm_8x?) did ptxas switch from IMNMX to VIMNMX?
