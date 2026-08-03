# UIMAD — Uniform Integer Multiply-Add

**Opcode mnemonic:** UIMAD  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Uniform integer multiply-add (IMAD's uniform twin), **SIGNED (S32) by
default** on sm_120 (silicon-verified, `tests/asm_construct/test_uimad.py`):

```
UIMAD.LO   URd = (signed(URa) * signed(URb) + URc) & 0xFFFFFFFF     (0x12a4)
UIMAD.HI   URd = high32(signed64(URa) * signed64(URb)) + URc        (0x12a6)
             -- the addend is added to the HIGH word!
UIMAD.WIDE {URd,URd+1} = signed64(URa) * signed64(URb) + signed64(URc)  (0x12a5)
```

**Plain `UIMAD` (no modifier) matches the HI variant on sm_120** (opposite
of IMAD where plain = LO).  Imm forms: `URb` imm (0x18a4/0x18a6) and `URc`
imm (0x14a4) verified.

Verified: LO/plain-HI over signed products (e.g. `0xFFFFFFFF * 2` → LO
`0xFFFFFFFE`, HI `0xFFFFFFFF`), HI addend-to-high-word, WIDE signed 64-bit
products (`0x12345678 * 0x9ABCDEF0` → `0xF8CC93D6242D2080`), imm forms.
