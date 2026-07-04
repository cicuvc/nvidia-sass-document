# FFMA — FP32 Fused Multiply-Add

**Opcode mnemonic:** `FFMA`  
**Pipe:** `fmalighter_pipe` (= `FMAI_OPS`)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd = Ra * Rb + Rc` — three-operand fused multiply-add on 32-bit floats.

Each source operand supports optional **negate** (`-`) and **absolute** (`||`) modifiers via
the sign-control bits in the encoding (see Bit layout below). RZ (register 0xFF) reads as 0.0;
writing RZ discards the result.

## Variant overview — 9 encoding variants

| Variant | Opcode (13b) | Operand C | Operand B | C size |
|---------|:-----------:|-----------|-----------|:------:|
| `ffma__RRR_RRR` | 0x223 | Register | Register | 32 |
| `ffma__RRI_RRI` | 0x423 | F32Imm | Register | 32 |
| `ffma__RRC_RRC` | 0x623 | Const bank | Register | 32 |
| `ffma__RRCx_RRCx` | 0x1623 | Const bank + UR | Register | 64 |
| `ffma__RIR_RIR` | 0x823 | Register | F32Imm | 32 |
| `ffma__RCR_RCR` | 0xa23 | Register | Const bank | 32 |
| `ffma__RCxR_RCxR` | 0x1a23 | Register | Const bank + UR | 32 |
| `ffma__RUR_RUR` | 0x1c23 | Register | UniformRegister | 32 |
| `ffma__RRU_RRU` | 0x1e23 | UniformRegister | Register | 32 |

Variant naming: each letter denotes the CBA operand type (`R`=Register, `I`=F32Imm,
`C`=Const bank, `Cx`=Const+UR, `U`=UniformRegister). Opcode = 13 bits ([91]∥[11:0]).

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **fmz** | [80],[76] | `nofmz_hfma2`(0), `FMZ`(1), `FTZ`(2), `INVALID3`(3) |
| **rnd** (rounding) | [79:78] | `RN`(0), `RM`(1), `RP`(2), `RZ`(3) |
| **sat** (saturation) | [77] | `nosat`(0), `SAT`(1) |

- `.RM`, `.RP`, `.RZ`, `.SAT`, `.FTZ` appear as suffixes in disassembly.
- `fmz=INVALID3` triggers `ILLEGAL_INSTR_ENCODING_ERROR`.
- `.reuse` is encoded via `TABLES_opex_*` in the `opex[8]` field; disallowed with
  `?DRAIN` / `?WAITn_END_GROUP`.

## Bit layout (RRR_RRR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b: batch_t, usched_info, reuse)
[121:116]               req_bit_set  (6b: REQ barrier)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 92: 90],[89:81]       -- gap --
[91],[11:0]             opcode       (13b)
[80],[76]               fmz          (2b)
[79:78]                 stride       (2b: rounding)
[77]                    ntz          (1b: sat)
[75]                    Rc.negate
[74]                    Rc.absolute
[73]                    Ra.absolute
[72]                    Ra.negate
[71:64]                 Rc           (8b)
[63]                    Rb.negate
[62]                    Rb.absolute
[61:40]                 -- gap --
[39:32]                 Rb           (8b)
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not
[14:12]                 Pg           (3b: predicate, 7=PT)
[10:4]                  -- gap --
[3:0]                   -- gap --
```

### Variant differences

- **RRI** (imm Sc): Rb→[71:64], no Rc; Sc F32Imm in [63:32]
- **RIR** (imm Sb): Rc→[71:64], no Rb; Sb F32Imm in [63:32]
- **RRU** (URc): Rb→[71:64]; URc in [37:32] (6-bit uniform reg); URc negate/abs in [63:62]
- **RUR** (URb): Rc→[71:64]; URb in [37:32]; URb negate/abs in [63:62] (opcode differs)

## Latency (from sm_90_latencies.txt)

FFMA belongs to `FMAI_OPS` (= `fmalighter_pipe`, excl. IMAD). FFMA itself is in
`FMAI_WITHOUT_IMAD`:

| Dependency | Pipe group × operand role | Cycles |
|-----------|--------------------------|:------:|
| TABLE_TRUE | `FMAI_WITHOUT_IMAD`{Rd} | 4–8 |
| TABLE_OUTPUT | `FMAI_OPS`{Rd} | 1–2 |
| TABLE_ANTI | `FMAI_OPS`{Ra,Rb,Rc} | 1–2 |

Occupancy: `FMAI_Occupancy [2]`.

## Verified encodings (cuobjdump, sm_90)

All 12 test vectors decoded correctly against cuobjdump disassembly.
Test kernel: `tests/ffma_test.cu`; decoder: `tools/decode_ffma.py`.

| Source | Hex (lo64 / hi64) | Disassembly |
|--------|-------------------|-------------|
| kernel | `0x4000000005057823` / `0x001fe20000000000` | FFMA R5, R5, 2, R0 (RIR) |
| kernel | `0x4040000004057423` / `0x001fc60000000005` | FFMA R5, R4, R5, 3 (RRI) |
| kernel | `0x8000000604057e23` / `0x001fe20008000005` | FFMA R5, R4, R5, -UR6 (RRU) |
| kernel | `0x0000000604057e23` / `0x001fc60008000105` | FFMA R5, -R4, R5, UR6 (RRU) |
| kernel | `0x0000000604057e23` / `0x001fe20008004005` | FFMA.RM R5, R4, R5, UR6 |
| kernel | `0x0000000604057e23` / `0x001fe20008008005` | FFMA.RP R5, R4, R5, UR6 |
| kernel | `0x0000000604057e23` / `0x001fe2000800c005` | FFMA.RZ R5, R4, R5, UR6 |
| kernel | `0x0000000604057e23` / `0x001fe20008000005` | FFMA R5, R4, R5, UR6 (plain) |
| kernel | `0x0000000604057e23` / `0x001fe20008002005` | FFMA.SAT R5, R4, R5, UR6 |
| kernel | `0x0000000604057e23` / `0x001fe20008010005` | FFMA.FTZ R5, R4, R5, UR6 |
| kernel | `0x0000000302057223` / `0x001fe200000000ff` | FFMA R5, R2, R3, RZ (RRR) |
| cublas | `0x0000000912130223` / `0x040fe2000000081a` | @P0 FFMA R19, R18, R9, -R26 (RRR) |

Key observations from compiler output:
- Compiler prefers **RRU** over RRR when operands are loaded via `ULDC` (uniform reg)
- `__fmul_rn(a,b)+c` splits into **FMUL+FADD** — no FFMA fusion there
- `a*b+0.0f` → FFMA with RZ (FFMA R5, R2, R3, RZ), still RRR
- PTX `fma.rz.f32` / `fma.rm.f32` / `fma.rp.f32` / `fma.ftz.f32` map directly to FFMA
  with the corresponding suffix via the `rnd`/`fmz` modifier bits

## Open questions

- `.reuse` flag not yet tested (requires paired consumer instructions)
- Const-bank variants (RRC, RRCx, RCR, RCxR) not yet verified with test kernel
- `FFMA32I` (pipe-only alias) relationship to FFMA not fully explored
- No PTX `fma.fmz.f32` — what PTX pattern triggers `.FMZ` suffix?
