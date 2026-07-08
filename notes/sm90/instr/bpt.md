# BPT — Breakpoint / Trap

**Opcode mnemonic:** `BPT`  
**Pipe:** `cbu_pipe` (constant buffer unit / control pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`  
**VIRTUAL_QUEUE:** `$VQ_CBU`

## Semantics

Generates a breakpoint, trap, or pipeline pause. The `bpt` modifier selects the
action, and the 3-bit `Sb` immediate provides a sub-opcode.

## Format

```
BPT.{TRAP/INT/PAUSE/DRAIN/PAUSE_QUIET} <3-bit Sb>
```

## Modifiers — bits [86:84]

| Value | Mnemonic | Enum | Sb constraint |
|:---:|----------|------|---------------|
| 2 | `.PAUSE` | BPT_PAUSE_DRAIN_PAUSE_QUIET | Any (0..7) |
| 3 | `.TRAP` | BPT_TRAP_INT | Sb ∈ {1..7} |
| 4 | `.INT` | BPT_TRAP_INT | Any (0..7) |
| 5 | `.DRAIN` | BPT_PAUSE_DRAIN_PAUSE_QUIET | Any (0..7) |
| 6 | `.PAUSE_QUIET` | BPT_PAUSE_DRAIN_PAUSE_QUIET | Any (0..7) |

## Variants

2 encoding variants, same opcode `0x95c`:

| Class | bpt source | sb encoding |
|-------|------------|-------------|
| `bpt__noDRAIN` | BPT_TRAP_INT (TRAP=3, INT=4) | Sb at [36:34] |
| `bpt__onlyDRAIN` | BPT_PAUSE_DRAIN_PAUSE_QUIET (PAUSE=2, DRAIN=5, PAUSE_QUIET=6) | Sb at [36:34] |

## Encoding

```
  [86:84]   3b  bpt mode     (*bpt, from enum)
  [36:34]   3b  Sb           (sub-opcode, 0..7)
  [91],[11:0] 13b  opcode    0x95c
```

## Verified encodings

| Lo64 | Disassembly |
|------|-------------|
| `0x000000040000795c` | `BPT.TRAP 0x1` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `trap;` | `BPT.TRAP 0x1` |
