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

## Bit layout (RRR 0x22b, 128-bit)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [124:122],[109:105] | opex | 8 | `TABLES_opex_4(batch_t,usched_info,reuse_src_a,reuse_src_b,reuse_src_c)` | scheduling + reuse hints |
| [121:116] | req_bit_set | 6 | — | scoreboard wait mask |
| [115:113] | src_rel_sb | 3 | `VarLatOperandEnc(src_rel_sb)` | read scoreboard |
| [112:110] | dst_wr_sb | 3 | `VarLatOperandEnc(dst_wr_sb)` | write scoreboard |
| [103:102] | pm_pred | 2 | — | perfmon predicate |
| [91],[11:0] | opcode | 13 | 0x22b | RRR form |
| [79:78] | rnd | 2 | Round1 | RN=0(hidden),RM=1,RP=2,RZ=3 |
| [75] | Rc@negate | 1 | Rc@negate | `-Rc` |
| [74] | Rc@absolute | 1 | Rc@absolute | `\|Rc\|` |
| [73] | Ra@absolute | 1 | Ra@absolute | `\|Ra\|` |
| [72] | Ra@negate | 1 | Ra@negate | `-Ra` |
| [71:64] | Rc | 8 | Register | FP64 addend B pair |
| [63] | Rb@negate | 1 | Rb@negate | `-Rb` |
| [62] | Rb@absolute | 1 | Rb@absolute | `\|Rb\|` |
| [39:32] | Rb | 8 | Register | FP64 addend B pair |
| [31:24] | Ra | 8 | Register | FP64 addend A pair |
| [23:16] | Rd | 8 | Register | result pair |
| [15] | Pg_not | 1 | Pg@not | predicate negate |
| [14:12] | Pg | 3 | Predicate | guard predicate |

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

**Note (correction):** the CLASS spec encoding above is **correct** — verified empirically.
An earlier version of this note claimed the ptxas encoding put the rounding/negate bits in
positions differing from the spec. That was a **mistake**: it recorded only Lo64, but `rnd`
([79:78]) and the negate/abs bits ([75:72]) live in **Hi64**. With Hi64 captured, the spec
positions match exactly (see "Verified encodings").

## Verified encodings (sm_90, CUDA 13.1 — full lo64 + hi64)

RRR form (`tests/dfma_test.cu`), `Rd`=R8, `Ra`=R2, `Rb`=R4, `Rc`=R6:

| Disassembly | Lo64 | Hi64 | rnd/neg bits (Hi64) |
|-------------|------|------|---------------------|
| `DFMA R8, R2, R4, R6` | `0x000000040208722b` | `0x008fce0000000006` | rnd=0 (RN) |
| `DFMA.RM R8, R2, R4, R6` | `0x000000040208722b` | `0x008fce0000004006` | rnd=1 → bit[14] |
| `DFMA.RP R8, R2, R4, R6` | `0x000000040208722b` | `0x008fce0000008006` | rnd=2 → bit[15] |
| `DFMA.RZ R8, R2, R4, R6` | `0x000000040208722b` | `0x008fce000000c006` | rnd=3 → bits[15:14] |
| `DFMA R8, -R2, R4, -R6` | `0x000000040208722b` | `0x008fce0000000906` | Ra@neg[72]+Rc@neg[75] |

The four rounding modes share an identical Lo64 (only Hi64 `rnd`[79:78]=Hi64 bits[15:14]
changes) — which is exactly why a Lo64-only capture appeared to "lose" the rounding field.
Decoder: `tools/decode_dfma.py` (confirms spec positions).

### PTX to SASS mapping

| PTX | SASS |
|-----|------|
| `fma.rn.f64 %rd, %ra, %rb, %rc` | `DFMA Rd, Ra, URb, Rc` (UR promoted) |
| `fma.rm.f64` | `DFMA.RM` |
| `fma.rp.f64` | `DFMA.RP` |
| `fma.rz.f64` | `DFMA.RZ` |

## Open questions

- **FP64 operand negation:** PTX `fma.f64` does not expose operand negation directly in inline
  asm (`__fma_rn(-a,b,-c)` folds the negation into the DFMA `-Ra`/`-Rc` bits [72]/[75], as
  verified above), unlike some F32 paths. This is a PTX-frontend convenience, not a hardware
  limitation — the DFMA negate/abs bits are always available.

*(Resolved: the earlier "encoding mismatch" open question was a Lo64-only measurement error;
the CLASS spec rounding/negate positions are correct — see the Note above.)*
