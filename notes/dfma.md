# DFMA — FP64 Fused Multiply-Add

**Opcode mnemonic:** `DFMA`  
**Pipe:** `fma64lite_pipe` (lightweight FP64 pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_EMULATABLE`  
**VIRTUAL_QUEUE:** `$VQ_REDIRECTABLE`

## Semantics

`Rd = Ra * Rb + Rc` in double-precision (FP64). All operands are 64-bit
register pairs (Rd/Ra/Rb/Rc must be even register numbers, % 2 == 0).

The "lite" pipe indicates lower-throughput FP64 execution compared to the
`fma64heavy_pipe` used for higher-throughput FP64 on H100.

## Format

```
@Pg DFMA{.rnd} Rd, [-]|[||]Ra{.reuse}, [-]|[||]Rb{.reuse}, [-]|[||]Rc{.reuse}
```

## Variant overview

9 encoding variants across 5 opcode base values:

| Class | Opcode | Registers |
|-------|--------|:---:|
| `dfma__RRR_RRR` | `0x22b` | Ra, Rb, Rc all regular |
| `dfma__RRsI_RRI` | `0x42b` | Rb immediate |
| `dfma__RRC_RRC` | `0x62b` | Rb constant bank |
| `dfma__RsIR_RIR` | `0x82b` | Ra immediate |
| `dfma__RCR_RCR` | `0xa2b` | Ra constant bank |
| `dfma__RCxR_RCxR` | `0x1a2b` | Ra const bindless |
| `dfma__RUR_RUR` | `0x1c2b` | Rb uniform register |
| `dfma__RRU_RRU` | `0x1e2b` | Rc uniform register |
| `dfma__RRCx_RRCx` | `0x162b` | Rb const bindless |

## Modifiers

### Rounding — rnd

| Value | Mnemonic | PTX |
|:---:|----------|-----|
| 0 | (default, RN) | `fma.rn.f64` |
| 1 | `.RM` | `fma.rm.f64` |
| 2 | `.RP` | `fma.rp.f64` |
| 3 | `.RZ` | `fma.rz.f64` |

### Negate/Absolute

Each source operand (Ra, Rb, Rc) supports `[-]` (negate) and `[||]` (absolute
value). Not all combinations may be valid simultaneously.

### `.reuse`

Register read reuse hint on Ra, Rb, Rc. Incompatible with DRAIN tokens.

## RUR variant encoding (spec)

For the `RUR_RUR` variant, Rb is replaced by a 6-bit uniform register at
[37:32]:

```
  [79:78]   2b  rnd           (rounding)
  [75]      1b  Rc@negate     
  [74]      1b  Rc@absolute   
  [73]      1b  Ra@absolute   
  [72]      1b  Ra@negate     
  [71:64]   8b  Rc            
  [63]      1b  URb@negate    
  [62]      1b  URb@absolute  
  [37:32]   6b  URb           (uniform register)
  [31:24]   8b  Ra            
  [23:16]   8b  Rd            
  [15]      1b  Pg_not        
  [14:12]   3b  Pg            
  [91],[11:0] 13b  opcode     (0x1c2b for RUR_RUR)
```

**Note:** Empirical encodings from ptxas show an alternate encoding (bits[11:0]=0xc2b,
bit[91]=0) that uses a different field layout — the rounding and negate bits
do not match the spec positions above. The spec encoding is documented for
reference; the actual ptxas-generated encoding uses positions that differ
from the formal CLASS definition. See "Open questions" below.

## Verified encodings

| Disassembly | Lo64 | PTX |
|-------------|------|-----|
| `DFMA R2, R10, UR4, R12` | `0x000000040a027c2b` | `fma.rn.f64` |
| `DFMA.RM R6, R10, UR4, R12` | `0x000000040a067c2b` | `fma.rm.f64` |
| `DFMA.RP R8, R10, UR4, R12` | `0x000000040a087c2b` | `fma.rp.f64` |
| `DFMA.RZ R10, R10, UR4, R12` | `0x000000040a0a7c2b` | `fma.rz.f64` |

### PTX to SASS mapping

| PTX | SASS |
|-----|------|
| `fma.rn.f64 %rd, %ra, %rb, %rc` | `DFMA Rd, Ra, URb, Rc` (UR promoted) |
| `fma.rm.f64` | `DFMA.RM` |
| `fma.rp.f64` | `DFMA.RP` |
| `fma.rz.f64` | `DFMA.RZ` |

## Open questions

- **Encoding mismatch:** The observed ptxas encoding (lo bits[11:0]=0xc2b,
  bit[91]=0) matches the spec's RUR_RUR lo-bits but not the hi-bits. The
  rounding and negate modifiers use positions different from the CLASS
  ENCODING section. This may indicate a newer variant not captured in the
  spec dump, or a ptxas optimization that uses a different encoding variant.
- **FP64 operand negation:** PTX `fma.f64` does not support operand negation
  in inline asm, unlike F32 `fma.rn.f32` which does. This may be a PTX
  limitation — the hardware supports negation via the negate/absolute bits.
