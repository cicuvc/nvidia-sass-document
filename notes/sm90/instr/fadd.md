# FADD — FP32 Add

**Opcode mnemonic:** `FADD`  
**Pipe:** `fmalighter_pipe` (= `FMAI_OPS`)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Semantics

`Rd = Ra + Rc` — two-operand floating-point add on 32-bit floats.

Each source operand supports optional **negate** (`-`) and **absolute** (`||`) via
sign-control bits. RZ (register 0xFF) reads as 0.0. No B source operand (`ISRC_B_SIZE = 0`).

## Variant overview — 5 encoding variants

| Variant | Opcode (13b) | Operand C | C size |
|---------|:-----------:|-----------|:------:|
| `fadd__RRR_RR` | 0x221 | Register | 32 |
| `fadd__RRI_RI` | 0x421 | F32Imm | 32 |
| `fadd__RRC_RC` | 0x621 | Const bank | 32 |
| `fadd__RRCx_RCx` | 0x1621 | Const bank + UR | 64 |
| `fadd__RRU_RU` | 0x1e21 | UniformRegister | 32 |

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| **ftz** | [80] | `noftz`(0), `FTZ`(1) |
| **rnd** (rounding) | [79:78] | `RN`(0), `RM`(1), `RP`(2), `RZ`(3) |
| **sat** (saturation) | [77] | `nosat`(0), `SAT`(1) |

`.RM`, `.RP`, `.RZ`, `.SAT`, `.FTZ` appear as suffixes in disassembly. `.reuse` flag
encoded via `TABLES_opex_*`.

## Bit layout (RRR_RR, 128-bit MSB-left)

```
[127:125]               -- gap --
[124:122],[109:105]     opex         (8b)
[121:116]               req_bit_set  (6b)
[115:113]               src_rel_sb   = *7
[112:110]               dst_wr_sb    = *7
[103:102]               pm_pred      (2b)
[ 92: 90],[89:81]       -- gap --
[91],[11:0]             opcode       (13b)
[80]                    ftz          (1b)
[79:78]                 stride       (2b: rounding)
[77]                    ntz          (1b: sat)
[76:74]                 -- gap --       ← note: no Rc.negate/abs (cf. FFMA [75:74])
[73]                    Ra.absolute
[72]                    Ra.negate
[71:40]                 -- gap --       ← note: no Rc register at [71:64] (cf. FFMA)
[63]                    Rc.negate
[62]                    Rc.absolute
[61:40]                 -- gap --
[39:32]                 Rc           (8b)   ← mapped from "Rb" slot in encoding
[31:24]                 Ra           (8b)
[23:16]                 Rd           (8b)
[15]                    Pg.not
[14:12]                 Pg           (3b: predicate, 7=PT)
```

### Variant differences

- **RRI** (imm Sc): Sc F32Imm in [63:32]; no Rc register field
- **RRU** (URc): URc in [37:32] (6-bit uniform reg); URc negate/abs in [63:62]
- **RRC/RRCx**: C operand at [63:32] with bank/offset encoding

## Key differences from FFMA

| Aspect | FFMA | FADD |
|--------|------|------|
| Sources | Ra, Rb, Rc | Ra, Rc only |
| Opcode space | 9 variants | 5 variants |
| fmz/ftz | 2-bit fmz [80],[76] | 1-bit ftz [80] |
| Rc negate/abs | [75],[74] | [63],[62] |
| Rc register | [71:64] | [39:32] |
| Imm position (C) | [63:32] (Sc in RRI) | [63:32] (Sc in RRI) |

The swapped Rc encode position is a notable difference — in FADD the C operand sits at
[39:32] (what would be Rb in FFMA), while in FFMA the C operand is at [71:64].

## Latency (from sm_90_latencies.txt)

FADD belongs to `FMAI_OPS` (= `fmalighter_pipe`). Same latency class as FFMA:

| Dependency | Pipe group × operand role | Cycles |
|-----------|--------------------------|:------:|
| TABLE_TRUE | `FMAI_OPS`{Rd} | 5–8 |
| TABLE_OUTPUT | `FMAI_OPS`{Rd} | 1–2 |
| TABLE_ANTI | `FMAI_OPS`{Ra,Rc} | 1–2 |

Note: FFMA is in `FMAI_WITHOUT_IMAD` while FADD is directly in `FMAI_OPS`, but the
TABLE_TRUE latencies are the same range (4–8 for FFMA, 5–8 for FADD).

## Verified encodings (cuobjdump, sm_90)

14/14 test vectors match. Test kernel: `tests/fadd_test.cu`; decoder: `tools/decode_fadd.py`.

| Source | Lo64 / Hi64 | Disassembly |
|--------|------------|-------------|
| kernel | `0x4040000005057421` / `0x001fca0000000000` | FADD R5, R5, 3 (RRI) |
| kernel | `0x8000000504057221` / `0x001fc60000000100` | FADD R5, -R4, -R5 (RRR) |
| kernel | `0x0000000504057221` / `0x001fe4000000c000` | FADD.RZ R5, R4, R5 |
| kernel | `0x8000000504057221` / `0x001fca0000000000` | FADD R5, R4, -R5 |
| kernel | `0x8000000405057221` / `0x001fe40000000000` | FADD R5, R5, -R4 |
| kernel | `0x0000000504057221` / `0x001fc60000004000` | FADD.RM R5, R4, R5 |
| kernel | `0x0000000504057221` / `0x001fe40000008000` | FADD.RP R5, R4, R5 |
| kernel | `0x0000000504057221` / `0x001fca0000000000` | FADD R5, R4, R5 (plain) |
| kernel | `0x00000006ff057e21` / `0x000fe20008000000` | FADD R5, RZ, UR6 (RRU) |
| kernel | `0x0000000504057221` / `0x001fc60000010000` | FADD.FTZ R5, R4, R5 |
| kernel | `0x0000000504057221` / `0x001fe40000002000` | FADD.SAT R5, R4, R5 |
| cublas | `0x800000ff1920e221` / `0x004fe20000000100` | @!P6 FADD R32, -R25, -RZ |
| cublas | `0x800000ff1504c221` / `0x000fe20000000100` | @!P4 FADD R4, -R21, -RZ |
| cublas | `0x800000ff0f089221` / `0x004fe20000000100` | @!P1 FADD R8, -R15, -RZ |

Key compiler observations:
- `a + 0.0f` → FADD Ra, RZ (cublas pattern) or optimized to RRU (kernel pattern)
- PTX `add.rz.f32` / `add.rm.f32` / `add.rp.f32` / `add.sat.f32` / `add.ftz.rn.f32`
  all map directly to FADD with corresponding modifier suffix
- `a - b` → FADD Ra, -Rc (`Rd = Ra + (-Rc)`)
- `-a + b` → FADD -Ra, Rc; `-a - b` → FADD -Ra, -Rc

## Open questions

- Const-bank variants (`fadd__RRC_RC`, `fadd__RRCx_RCx`) not yet verified
- `FADD32I` (pipe-only alias) relationship to FADD not explored
