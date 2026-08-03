# USHF — Uniform Funnel Shift

**Opcode mnemonic:** USHF  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Uniform funnel shift (SHF's uniform twin): `USHF[.L|.R][.C|.W][.LO|.HI][.U32|.S32|.U64|.S64]
URd, URa, URb|imm, URc`.  Funnel = `{URc high, URa low}`.

**SILICON QUIRK vs SHF (verified SM120, `tests/asm_construct/test_ushf.py`)**:
the "outer" result words drop the cross-word funnel bits:

```
L.HI = (URc << n) | (URa >> (32-n))     full funnel high word
L.LO = URa << n                          URc's bits NOT shifted in!
R.HI = URc >> n                          URa's bits NOT shifted in!
R.LO = (URa >> n) | (URc << (32-n))      full funnel low word
```

Regular SHF includes the cross-word bits in all four words; USHF does not.
`.C` (clamp): n = min(k, 32); `.W`: n = k & 31; `.S32`: arithmetic
sign-fill.  Verified across n=0..31, discriminators, `.W` wrap, `.S32`, and
the imm shift form.
