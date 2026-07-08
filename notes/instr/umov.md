# UMOV — Uniform Move

**Opcode mnemonic:** UMOV  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Moves a value into a uniform register: `URd = URb` (register) or `URd = imm32` (immediate).
The simplest uniform-register instruction — pure data movement without computation.

## Variant overview

| Variant | Opcode | Format | Observed? |
|---------|--------|--------|-----------|
| `umov__UR` | `0x1c82` | `UMOV URd, URb` | Yes |
| `umov__UI` | `0x882` | `UMOV URd, imm32` | Yes |

## Bit layout

### Register — opcode 0x1c82

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[37:32]              Ra_URb               <= URb
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
[91:91],[11:0]       opcode               <= 0b1110010000010
```

### Immediate — opcode 0x882

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[63:32]              Ra_offset            <= Sb (imm32)
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
[91:91],[11:0]       opcode               <= 0b100010000010
```

## Verified encodings

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000003f00067c82` | `0x000fe20008000000` | `UMOV UR6, URZ` |
| `0x0000000000047882` | — | `UMOV UR4, 0x0` |
| `0x5f34f76300047882` | — | `UMOV UR4, 0x5f34f763` |
| `0x14f0000000057882` | — | `UMOV UR5, 0x14f00000` |
| `0x0000040000057882` | — | `UMOV UR5, 0x400` |

## Latency

`UDP_subset` group (same as ULEA, ULOP3): output 1–7 cycles, true-dependency 4–12 cycles.
Special case in the latency file: `ULDC_VOTEU_UMOV_ULEPC` is a distinct subgroup for moved-from-constant values with lower latency (2–5 cycles true, 1–4 cycles output).
