# IDE — Integer Dot Expand

**Opcode mnemonic:** `IDE`  
**Pipe:** `int_pipe` (integer execution pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

A hardware configuration/synchronization instruction related to integer dot
product operations. Unlike IDP which has 3 source registers and a destination,
IDE has **no data registers** — only a 16-bit immediate `Sb` that must equal
the magic constant **3088**.

Format: `IDE.{EN/DI} 3088`

The instruction appears to be a fixed-function control operation:
- **action=0 (.EN):** Enable dot-product state machine / pipeline
- **action=1 (.DI, default):** Disable dot-product state machine / pipeline

This is likely used for pipeline management around IDP operations — enabling
and disabling the dot-product accumulator state between IDP.2A.HI sequences
(which split a 4-element dot product into two halves and accumulate via an
internal carry).

## Format

```
IDE{.EN/.DI} <immediate=3088>
```

## No PTX equivalent

IDE has no direct PTX instruction. The compiler emits it automatically as
needed during instruction scheduling — it's a framework-level instruction.

## Encoding

```
  [84]       1b  action    IDEAction: EN=0, DI=1(default)
  [47:32]   16b  Sb        Must equal 3088 (only valid value)
  [91],[11:0] 13b  opcode  0x951
```

## Spec behaviour

- `ISRC_B_SIZE = 16` — the 16-bit Sb is the only "source operand"
- `IDEST_SIZE = 0` — no register output
- Only `Sb == 3088` is a valid encoding; any other value triggers `ILLEGAL_INSTR_ENCODING_ERROR`
- Pipe: `int_pipe` (not fmalighter_pipe like IDP)

## Relationship to IDP

IDP.2A.HI computes the upper half of a 2-element dot product but doesn't
accumulate with Rc — the carry/expansion from 2A.LO is managed through the
IDE-controlled state machine:

```
IDP.2A.LO  Ra.lo, Rb.lo, Rc   → Rd.lo  + internal carry
IDP.2A.HI  Ra.hi, Rb.hi, RZ   → Rd.hi  + internal carry expansion
IDE.DI 3088                   → flush/disable the expansion state
```

This is analogous to IMAD.X/IMAD.HI carry chains, but managed through a
separate control instruction rather than predicate registers.
