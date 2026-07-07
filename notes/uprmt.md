# UPRMT — Uniform Byte Permute

**Opcode mnemonic:** UPRMT  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Permutes bytes from source registers into a destination uniform register. Equivalent to PRMT for uniform registers. The `imm32` (or URb) is a 4-byte permute control word, where each byte selects a source byte channel from the concatenation of `{URa, URc}` (or `{URa, imm32}` / `{URa, URb}`).

The `idx` modifier (IDXOnly, always 0 on sm_90) indicates indexed permute mode.

## Variant overview

| Variant | Opcode | Format | Observed? |
|---------|--------|--------|-----------|
| `uprmt__URURUR` | `0x1296` | `UPRMT URd, URa, URb, URc` | No |
| `uprmt__URIUR` | `0x1896` | `UPRMT URd, URa, imm32, URc` | **Yes** |

## Bit layout

### Imm — opcode 0x1896

```
[124:122],[109:105]  opex        <= TABLES_opex_1
[121:116]            req_bit_set
[72:72]              e           <= idx (IDX=0)
[69:64]              Ra_URc      <= URc
[63:32]              Ra_offset   <= Sb (imm32 permute control)
[29:24]              Sa          <= URa
[21:16]              URd         <= URd
[15:15]              Pg_not      <= UPg@not
[14:12]              Pg          <= UPg
[91:91],[11:0]       opcode      <= 0b1100010010110
```

### Noimm — opcode 0x1296

Same layout but URb at [37:32] instead of imm32 at [63:32].

## Verified encodings

From libcublas (sm_90, CUDA 13.1):

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000888004047896` | — | `UPRMT UR4, UR4, 0x8880, URZ` |
| `0x0000888006047896` | — | `UPRMT UR4, UR6, 0x8880, URZ` |
| `0x000088800e047896` | — | `UPRMT UR4, UR14, 0x8880, URZ` |
| `0x00008880130b7896` | — | `UPRMT UR11, UR19, 0x8880, URZ` |
| `0x0000888009047896` | — | `UPRMT UR4, UR9, 0x8880, URZ` |

The value `0x8880` is the common permute control — each byte 0x88 selects byte 0 from the source, producing a byte-replicate. URc is always URZ (second source treated as zero).

## Latency

`UDP_subset` group: output 1–7 cycles, true-dependency 4–12 cycles.

## Open questions

- **Noimm variant (0x1296):** Never emitted by ptxas. When would a register-based permute control be needed vs immediate?
- **Permute control encoding:** The 4-byte control word encodes source byte indices. 0x8880 selects bytes 0,0,0,0 from the first source. The exact mapping of control byte → source byte index needs further investigation.
