# UBREV — Uniform Bit Reverse

**Opcode mnemonic:** UBREV  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Reverses the order of bits in a uniform register: `URd = bit_reverse(URb)`. Bit 0 becomes bit 31, bit 1 becomes bit 30, etc. Equivalent to `BREV` for uniform registers.

Silicon-verified on SM120 (`tests/asm_construct/test_ubrev.py`, RTX 5090):
9/9 cases — RUR (param input) and RIR (imm 0x0F0F0F0F) forms, bit 0 ↔ bit 31.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `ubrev__URURUR_URUR` | `0x12be` | `UBREV URd, URb` |
| `ubrev__URuIUR_URI` | `0x18be` | `UBREV URd, imm32` |

## Bit layout (noimm — opcode 0x12be)

```
[37:32]         Ra_URb    <= URb
[21:16]         URd       <= URd
[91:91],[11:0]  opcode    <= 0b1001010111110
```

Imm variant: URb replaced with 32-bit immediate at [63:32].

## Latency

`UDP_subset` group: output 1–7 cycles, true-dependency 4–12 cycles.

## SM120 verification notes (uniform-datapath behavior)

The assembler encodes both variants bit-for-bit (RUR `0x12be`, RIR `0x18be`;
`URb` → [37:32], `URd` → [23:16], imm → [63:32], `UPg`/`UPg@not` → [14:12]/[15]).
Consuming a udp-written UR into a GPR requires care, learned empirically:

- A uniform register freshly written by `LDCU` (const-bank load) is **not
  reliably readable by the first udp consumer** of a kernel — the first read
  returns the previous launch's stale value.  A dummy udp read (`UMOV UR9, UR6`,
  result discarded) before the real consumer settles the datapath.
- A GPR-pipe consumer (`IADD3 Rd, ..., URb, ...`) reading a udp-written UR
  needs an intervening udp instruction (e.g. `UMOV`) for the value to be
  stable; direct reads race.
- `LDCU` param reads lag ~4 launches when the CUBIN module is reused across
  launches in this assembler/driver setup (fresh module per launch is
  correct; regular `LDC` is not affected).

Verified recipe:
`LDCU UR6, #param(in)` (wr=SB2) → `UMOV UR9, UR6` (dummy, req={2}) →
`UBREV UR8, UR6` (req={2}) → `UMOV UR10, UR8` → `IADD3 R3, PT, PT, RZ, UR8, RZ`
→ fillers → `STG`.
