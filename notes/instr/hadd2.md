# HADD2 — Packed FP16x2 Add

**Opcode mnemonic:** `HADD2`  
**Pipe:** `fp16_pipe` (= `FP16_OPS`)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd.h0 = Ra.h0 + Rc.h0; Rd.h1 = Ra.h1 + Rc.h1` — per-lane FP16 addition on two packed
halfword pairs. ISWZA lane swizzles select which source halfwords feed each lane.

**F32 accumulator (`.F32` output format):** Instead of packed FP16x2 output, the
result is a single FP32 accumulator: `Rd.f32 = float(Rc.h{sel})` where `Rc.h{sel}`
is the halfword selected by ISWZA. Ra is constrained to `RZ` with negate (gives +0.0),
effectively widening a single FP16 to FP32. This is used for `cvt.f16.f32 → add`.
The cublas widening idiom:
- `HADD2.F32 Rd, -RZ, Src.H0_H0` → widen **low** half to f32
- `HADD2.F32 Rd, -RZ, Src.H1_H1` → widen **high** half to f32

## Variant overview — 11 encoding variants (5 opcodes)

| Variant | Opcode (13b) | Hex | Operand C | ISRC_C_SIZE |
|---------|:-----------:|:---:|-----------|:-----------:|
| `hadd2__RR` | `0b1000110000` | 0x230 | Register | 32 |
| `hadd2_F32__RR` | `0b1000110000` | 0x230 | Register (F32 acc) | 32 |
| `hadd2__RC` | `0b11000110000` | 0x630 | Const bank | 32 |
| `hadd2_F32__RC` | `0b11000110000` | 0x630 | Const bank (F32 acc) | 32 |
| `hadd2__RI` | `0b10000110000` | 0x430 | 2× F16Imm | 32 |
| `hadd2_F32__RI` | `0b10000110000` | 0x430 | 2× F16Imm (F32 acc) | 32 |
| `hadd2_F32i_` (ALT) | `0b10000110000` | 0x430 | 1× F16Imm (hi=0) | 16 |
| `hadd2__RU` | `0b1111000110000` | 0x1e30 | UniformRegister | 32 |
| `hadd2_F32__RU` | `0b1111000110000` | 0x1e30 | UniformRegister (F32 acc) | 32 |
| `hadd2__RCx` | `0b1011000110000` | 0x1630 | UR + UImm offset | 64 |
| `hadd2_F32__RCx` | `0b1011000110000` | 0x1630 | UR + UImm offset (F32 acc) | 64 |

The `.F32` variant vs. regular is distinguished by the `ofmt` field:
`.F32` when `ofmt = F32ONLY_hadd2.F32 (1)`. In `.F32` mode, Ra must be RZ
and Ra@negate must be 1 (enforced by CONDITIONS).

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **ofmt** (output format) | [85],[78] | F16_V2(0), F32(1), BF16_V2(2) |
| **ftz** | [80] | noftz(0), FTZ(1) |
| **sat** | [77] | nosat(0), SAT(1) |
| **iswzA** (on Ra) | [75:74] | H1_H0(0), H0_H0(2), H1_H1(3) |
| **Ra absolute** | [73] | off(0), \|Ra\|(1) |
| **Ra negate** | [72] | off(0), -Ra(1) |
| **iswzB** (on Rc/Sc/URc) | [61:60] | H1_H0(0), H0_H0(2), H1_H1(3) |
| **Rc negate** | [63] | off(0), -Rc(1) |
| **Rc absolute** | [62] | off(0), \|Rc\|(1) |

BF16_V2 output format disallows `.FTZ` and `.SAT` (enforced by CONDITIONS).
`.F32` output format disallows Ra absolute; Ra must be RZ with negate=1.

## Bit layout (hadd2__RR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b)  TABLES_opex_3(batch_t,usched_info,reuse_src_a,reuse_src_c)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7 (no scoreboard)
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 91],[11:0]            opcode       (13b: bit[91]∥[11:0])
[85],[78]               ofmt         (2b)
[80]                    ftz          (1b: UPq_not)
[77]                    sat          (1b: ntz)
[75:74]                 iswzA        (2b: bop)
[73]                    Ra.absolute  (1b: sz)
[72]                    Ra.negate    (1b: e)
[63]                    Rc.negate    (1b: Sb_invert)
[62]                    Rc.absolute  (1b: Sc_absolute)
[61:60]                 iswzB        (2b: hsel)
[39:32]                 Rc           (8b: Rb slot)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not       (1b)
[14:12]                 Pg           (3b: predicate, 7=PT)
```

### Variant differences

- **F32__RR**: Ra.absolute (sz) absent — bit [73] reserved. Condition forces Ra=RZ,
  Ra.negate=1. No reuse_src_a modifier (only reuse_src_c).
- **RC**: Rc field [39:32] replaced by cbank[58:54]/coff[53:40] via ConstBankAddress2.
- **RI**: Rc replaced by Sc[63:48] and Sb[47:32] — two FP16 immediates.
  For BF16_V2 output format, immediates are E8M7; for F16_V2, they are F16Imm.
- **F32i_ (ALT)**: single F16Imm at [47:32] (Sc slot); the H1 half (Sb) forced to 0.
- **RU**: Rc at [39:32]→[37:32] (6-bit UR); negate/abs at [63:62] on URc.
- **RCx**: URc at [37:32] + offset[53:40] scaled ×4; ISRC_C_SIZE=64.

## Compiler behavior (ptxas, sm_90, CUDA 13.1)

**Plain HADD2 is never emitted by ptxas.** PTX `add.f16x2` (with or without
`.sat`/`.ftz`) is always lowered to `HFMA2.MMA` with `1, 1` multiplier pair:

| PTX | SASS |
|-----|------|
| `add.f16x2 d, a, b` | `HFMA2.MMA Rd, Ra, 1, 1, Rc` |
| `add.sat.f16x2 d, a, b` | `HFMA2.MMA.SAT Rd, Ra, 1, 1, Rc` |
| `add.ftz.f16x2 d, a, b` | `HFMA2.MMA.FTZ Rd, Ra, 1, 1, Rc` |
| `add.ftz.sat.f16x2 d, a, b` | `HFMA2.MMA.FTZ.SAT Rd, Ra, 1, 1, Rc` |
| C++ `a + b` (`__half2`) | `HFMA2.MMA Rd, Ra, 1, 1, Rc` |
| C++ `a - b` | `HFMA2.MMA Rd, Ra, 1, 1, -Rc` |
| C++ `-a + b` | `HFMA2.MMA Rd, -Ra, 1, 1, Rc` |
| C++ `-a - b` | `HFMA2.MMA Rd, -Ra, 1, 1, -Rc` |

**HADD2.F32 IS emitted** for FP16→FP32 widening. Both `(float)__low2half(a)`
(C++) and explicit cublas usage generate `HADD2.F32 Rd, -RZ, Rs.H0_H0`.

Negation on PTX `add.f16x2` operands is illegal (`-%a` → "Operand negation not
allowed for instruction 'add'"). The compiler achieves negation through the
HFMA2.MMA multiplier or through the SASS negate bit for HADD2.F32.

## Latency (from sm_90_latencies.txt)

HADD2 belongs to `FP16_OPS` (= `fp16_pipe`).

| Dependency | Pipe group × operand role | Cycles |
|-----------|--------------------------|:------:|
| TABLE_TRUE(GPR) | `FP16_OPS`{Rd} | 5–8 |
| TABLE_OUTPUT(GPR) | `FP16_OPS`{Rd} | 1–2 |
| TABLE_ANTI(GPR) | `FP16_OPS`{Ra,Rc} | 1–2 |

## Verified encodings (cuobjdump, sm_90)

All test vectors decoded correctly by `tools/decode_hadd2.py` (12/12).

| Source | Lo64 / Hi64 | Disassembly |
|--------|------------|-------------|
| cublas | `0x2000000eff087230` / `0x004fca0000004100` | HADD2.F32 R8, -RZ, R14.H0_H0 |
| cublas | `0x2000000eff0c7230` / `0x004fe40000004100` | HADD2.F32 R12, -RZ, R14.H0_H0 |
| cublas | `0x20000008ff0a7230` / `0x008fc60000004100` | HADD2.F32 R10, -RZ, R8.H0_H0 |
| cublas | `0x2000000eff147230` / `0x004fe40000004100` | HADD2.F32 R20, -RZ, R14.H0_H0 |
| cublas | `0x20000008ff167230` / `0x008fc60000004100` | HADD2.F32 R22, -RZ, R8.H0_H0 |
| cublas | `0x2000000aff0c7230` / `0x010fe40000004100` | HADD2.F32 R12, -RZ, R10.H0_H0 |
| cublas | `0x20000008ff0e7230` / `0x020fe40000004100` | HADD2.F32 R14, -RZ, R8.H0_H0 |
| cublas | `0x2000002bff2b7230` / `0x004fe40000004100` | HADD2.F32 R43, -RZ, R43.H0_H0 |
| cublas | `0x20000009ff097230` / `0x008fc60000004100` | HADD2.F32 R9, -RZ, R9.H0_H0 |
| kernel | `0x20000005ff057230` / `0x001fca0000004100` | HADD2.F32 R5, -RZ, R5.H0_H0 |

### PTX→SASS mapping

PTX `add.f16x2` → `HFMA2.MMA` (never `HADD2`).  
PTX `cvt.rn.f16x2.f32` + `add` → `HADD2.F32` (widening half to float).

## Open questions

- HADD2 non-F32 (packed FP16x2 output) encodings not yet verified
  (ptxas never emits them — need hand-crafted test vectors or a different compiler
  version that might emit HADD2 instead of HFMA2.MMA)
- Const-bank (`RC`), immediate (`RI`), uniform (`RU`), and extended-const (`RCx`)
  variants not yet verified
- Whether HADD2 could be hand-encoded and executed (hardware validates encoding)
- Why ptxas prefers HFMA2.MMA over HADD2 (pipe assignment? throughput?)
