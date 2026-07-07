# FLO/BREV/UBREV/BMSK — Bit-Manipulation Instructions

## FLO — Find Leading One

**Opcode:** `0x300` (RRR), `0x1b00` (RCxR), `0xb00` (RCR), `0x1d00` (RUR), `0x900` (RuIR)  
**Pipe:** `mio_pipe`, `$VQ_MUFU`  
**TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

### Semantics

Finds the position of the most significant set bit. Returns bit index (0..31)
or -1 if the input is zero.

`Rd = find_leading_one(Rb)` (U32) or `Rd = find_leading_one_sign_extended(Rb)` (S32)

### Format

`FLO.{U32/S32} Rd, Rb`

- `.U32` (default): unsigned — counts from MSB, returns bit position or -1 if zero
- `.S32`: signed — find leading sign bit, for negation

### PTX mapping

| PTX | SASS |
|-----|------|
| `bfind.u32 %r, %a` | `FLO.U32 Rd, Ra` |
| `bfind.s32 %r, %a` | `FLO.S32 Rd, Ra` |

## BREV — Bit Reverse

**Opcode:** `0x301` (RRR), `0x1b01` (RCxR), `0xb01` (RCR), `0x1d01` (RUR), `0x901` (RuIR)  
**Pipe:** `mio_pipe`, `$VQ_MUFU`  
**TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

### Semantics

Reverses the bit order of a 32-bit value: bit 0 becomes bit 31, bit 1 becomes
bit 30, etc.

`Rd = bit_reverse(Rb)`

### Format

`BREV Rd, Rb`

### PTX mapping

| PTX | SASS |
|-----|------|
| `brev.b32 %r, %a` | `BREV Rd, Ra` |

## UBREV — Uniform Bit Reverse

**Opcode:** `0x12be` (URURUR), `0x18be` (URuIUR)  
**Pipe:** `udp_pipe`, `INST_TYPE_COUPLED_MATH`

### Semantics

Same as BREV but operates on uniform registers. Uses uniform predicates (UPg).

`URd = bit_reverse(URb)`

### Format

`UBREV URd, URb`

### Encoding

```
  [37:32]   6b  URb          (source uniform register)
  [21:16]   6b  URd          (destination uniform register)
  [14:12]   3b  UPg          (uniform predicate, default UPT=7)
```

## BMSK — Bit Mask

**Opcode:** `0x21b` (RRR), `0x1a1b` (RCxR), `0xa1b` (RCR), `0x1c1b` (RUR), `0x81b` (RuIR)  
**Pipe:** `int_pipe`, `INST_TYPE_COUPLED_MATH`

### Semantics

Generate a bit mask. Used by the compiler for BFI (bit field insert).

`Rd = bitmask_pattern(Ra, Rb)` where Ra controls the width and Rb controls the position.

### Format

`BMSK{.W} Rd, Ra, Rb`

- `.C` (default, C=0): clamp mode? — omitted from disassembly
- `.W` (W=1): wrap mode

Supports `.reuse` on Ra and Rb (register read reuse hint).

### Encoding

```
  [75]      1b   cw          CWMode: C=0(default), W=1
  [39:32]   8b   Rb          (second operand — bit position)
  [31:24]   8b   Ra          (first operand — bit width)
  [23:16]   8b   Rd          (destination)
```

### PTX mapping

BMSK is not directly exposed in PTX. It is used as a building block for:
- `bfi.b32` → `SHF.L.U32` + `BMSK` + `LOP3.LUT`
- `bfe.u32` → `SHF.R.U32.HI` + `PRMT`

## Combined PTX→SASS summary

| PTX | SASS | Hardware instruction? |
|-----|------|:---:|
| `fns.b32` | PLOP3 + SHF + SEL (binary search) | No |
| `bfind.u32/s32` | `FLO.U32` / `FLO.S32` | Yes |
| `brev.b32` | `BREV` | Yes |
| — | `UBREV` (uniform variant) | Yes |
| `bfi.b32` | `SHF.L` + `BMSK` + `LOP3` | Partial (BMSK) |
| `bfe.u32` | `SHF.R.U32.HI` + `PRMT` | No |
