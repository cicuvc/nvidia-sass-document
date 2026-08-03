# UPOPC — Uniform Population Count

**Opcode mnemonic:** UPOPC  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Uniform population count (POPC's uniform twin):

```
UPOPC URd, [~]URb|imm32    (0x12bf UUU / 0x18bf imm)
URd = number of set bits in URb; [~] counts ~URb's bits.
```

Silicon-verified on SM120 (`tests/asm_construct/test_upopc.py`, RTX 5090):
12 cases incl. 0 / 0xFFFFFFFF / 0x0F0F0F0F popcounts, `[~]` inversion, and
the imm form.
