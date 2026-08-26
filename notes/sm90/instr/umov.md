# UMOV — Uniform Move

**Opcode mnemonic:** UMOV  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). A real sm_90 rerun is currently blocked because the accompanying test source
> uses sm_120 FORMAT shapes the sm_90 spec rejects at match time.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

## Semantics

Moves a value into a uniform register: `URd = URb` (register) or `URd = imm32` (immediate).
The simplest uniform-register instruction — pure data movement without computation.

**Silicon-verified on SM120 (`tests/asm_construct/test_umov.py`, RTX 5090):**
register and imm32 forms (0x1c82 / 0x882), plus `.64` pair (`{URd,URd+1} <-
{URb,URb+1}`) and 64-bit immediate forms.  UMOV is also the standard udp
"settling" filler used across all uniform-instruction tests (dummy first
read / GPR-consumer settling).

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
