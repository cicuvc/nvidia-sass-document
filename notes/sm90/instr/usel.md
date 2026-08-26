# USEL — Uniform Select

**Opcode mnemonic:** USEL  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). A real sm_90 rerun is currently blocked because the accompanying test source
> uses sm_120 FORMAT shapes the sm_90 spec rejects at match time.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

## Semantics

Uniform register conditional select: `URd = UPp ? URa : URb` (noimm) or `URd = UPp ? URa : imm32` (imm).
The uniform predicate `UPp` controls which source is forwarded to the destination.

**Silicon-verified on SM120 (`tests/asm_construct/test_usel.py`, RTX 5090):**
32-bit form `URd = UPp ? URa : URb|imm` with `[!]UPp` negation all correct.

**64-bit register-form QUIRK:** `USEL.64 {URd,URd+1}, {URa,URa+1}, {URb,URb+1}, UPp`
with `UPp=1` selects the URa pair correctly, but with `UPp=0` the result is
`{URb, URb}` — the HIGH word duplicates the LOW word (URb+1 is not read).
The 64-bit IMM form is correct on both paths (`UPp=0` → `{imm, 0}`).

## Variant overview

| Variant | Opcode | Format | Observed? |
|---------|--------|--------|-----------|
| `usel__URURUR_UUU` | `0x1287` | `USEL URd, URa, URb, [?]UPp` | Yes |
| `usel__URuIUR_URIR` | `0x1887` | `USEL URd, URa, imm32, [?]UPp` | Yes |

## Bit layout

### Noimm — opcode 0x1287

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[90:90]              input_reg_sz_32_dist <= UPp@not
[89:87]              Pnz                  <= UPp
[37:32]              Ra_URb               <= URb
[29:24]              Sa                   <= URa
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
[91:91],[11:0]       opcode               <= 0b1001010000111
```

### Imm — opcode 0x1887

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[90:90]              input_reg_sz_32_dist <= UPp@not
[89:87]              Pnz                  <= UPp
[63:32]              Ra_offset            <= Sb (imm32)
[29:24]              Sa                   <= URa
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
[91:91],[11:0]       opcode               <= 0b1100010000111
```

## Verified encodings

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000506057287` | — | `USEL UR5, UR6, UR5, UP0` |
| `0x0000000506057287` | — | `USEL UR5, UR6, UR5, !UP0` |
| `0x000000050a057287` | — | `USEL UR5, UR10, UR5, UP0` |
| `0x0000001004047887` | — | `USEL UR4, UR4, 0x10, UP0` |
| `0x0000000804047887` | — | `USEL UR4, UR4, 0x8, UP0` |
| `0xfffffc000a0a7887` | — | `USEL UR10, UR10, 0xfffffc00, UP0` |

## Latency

`UDP_subset` group (same as ULEA, ULOP3): output 1–7 cycles, true-dependency 4–12 cycles.
