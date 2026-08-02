# FLO — Find Leading One

**Opcode mnemonic:** FLO  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

## Semantics

Finds the bit position of the most-significant set bit in a register: `Rd = find_leading_one([~]Rb)`. The `[~]` modifier inverts first, giving find_leading_zero. The `SH` modifier optionally shifts the result (presumably by a fixed amount). Result is 0-based (0–31 for a 32-bit input).

Output `Pu` (predicate) flags special conditions (input zero → all bits set? overflow?).

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `flo__RRR_RRR` | `0x300` | `FLO Rd, Pu, [~]Rb` |
| `flo__RIR` | `0x900` | `FLO Rd, Pu, imm32` |
| `flo__RCR` | `0xb00` | `FLO Rd, Pu, [~]c[bank][offset]` |
| `flo__RCxR` | `0x1b00` | `FLO Rd, Pu, [~]c[URb][offset]` |
| `flo__RUR` | `0x1d00` | `FLO Rd, Pu, [~]URb` |

## Bit layout (RRR — opcode 0x300)

```
[83:81]              Pu         <= Pu (flag predicate)
[74:74]              sh         <= sh (0=nosh, 1=SH)
[73:73]              sz         <= fmt (REDUX_SZ=S32=0)
[63:63]              Sb_invert  <= Rb@invert (1 = [~])
[39:32]              Rb         <= Rb
[23:16]              Rd         <= Rd
[91:91],[11:0]       opcode     <= 0b1100000000
```

## Key features

- **mio_pipe**, **VQ_MUFU**, decoupled scoreboard with variable-latency encoding
- Pu predicate output for flag (e.g., input-was-zero)
- SH modifier for result shift

## Latency

`mio_pipe`, MUFU dispatch. Latency comparable to other MUFU ops (higher than int_pipe).

## Resolved: silicon-verified semantics (SM120)

`tests/asm_construct/test_brev_flo_popc.py` + `tools/decode_brev_flo_popc.py`
confirm FLO = PTX `bfind` exactly:

| SASS | PTX | Rd (valid input) | degenerate |
|------|-----|-------------------|------------|
| `FLO.U32` | bfind.u32 | index of MSB set bit (0..31) | input 0 -> 0xFFFFFFFF |
| `FLO` (S32) | bfind.s32 | index of MSB bit differing from sign (neg: MSB of ~b) | 0 or 0xFFFFFFFF -> 0xFFFFFFFF |
| `FLO.U32.SH` | bfind.shiftamt.u32 | clz(b) | input 0 -> 0xFFFFFFFF |
| `FLO.SH` | bfind.shiftamt.s32 | clz-based (neg: clz(~b)) | 0 or -1 -> 0xFFFFFFFF |

- **Pu = "scan found a bit"**: 1 when Rd is a valid index, 0 in the
  degenerate cases (Rd==0xFFFFFFFF).  It is NOT "input zero" — S32 FLO of
  0xFFFFFFFF also clears Pu (both all-zero and all-ones are degenerate).
- `[~]` inverts Rb first = find leading zero.
- Pu is hidden by ptxas (encoded PT) when unused; `FLO.U32 R0, R2` is the
  common emission.
- ptxas mapping: `bfind.u32/s32` -> FLO.U32/FLO; `bfind.shiftamt.*` -> .SH.

Hand-assembler gotchas: mio_pipe DECOUPLED_RD_WR_SCBD — result write needs a
scoreboard (`wr`) consumed by `req`; the Pu predicate needs ~20 NOP
cross-pipe delay before an @P consumer (like SHFL).  FLO is slow (~MUFU
latency), so dependent consumers should use the scoreboard, not a short stall.
