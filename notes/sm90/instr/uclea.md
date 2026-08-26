# UCLEA — Uniform Clear Effective Address

**Opcode mnemonic:** UCLEA  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

<!-- arch-scope-banner -->
> **Arch scope:** the em-window rules were measured on RTX 5090 (sm_120); the sm_90 spec
> additionally rejects immediates >8 (#constSizeU04), so several sm_120 probes cannot
> assemble under ASSEMBLER_ARCH=sm90 until sources are split per arch. See
> `notes/sm120/silver-status.md`.

## Semantics

**Silicon-verified on SM120 (`tests/asm_construct/test_uclea.py`, RTX 5090) —
the assumed "align down" semantics are WRONG on sm_120.** The instruction
computes:

```
URd.64 = (URa.64 << 6) + URb        (URb = 32-bit uniform or imm16)
```

a hardwired 6-bit left shift (×64) of the full 64-bit `URa` pair plus the
32-bit offset, truncated to 64 bits. `constSize` (validated 0–16) has **no
observable effect** (K=0, 5, 16 all produce identical results), and `UPu`
is **never asserted** (probed: 32/64-bit carry, truncation, zero, low-bit
patterns). Both URd and URa are 64-bit values (even-aligned register pairs).

Possible interpretation: the "clear effective address" scales a
64-byte-granular descriptor index (`URa`) by 64 and adds a byte offset
(`URb`) — i.e. the constSize notion is vestigial on sm_120. No empirical
examples found in libcublas or ptxas output on sm_90, CUDA 13.1.

## Variant overview

| Variant | Opcode | Format |
|---------|--------|--------|
| `uclea__URb` | `0x1cbc` | `UCLEA URd, UPu, URa, URb, constSize` |
| `uclea__Imm` | `0x18bc` | `UCLEA URd, UPu, URa, imm16, constSize` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| constSizeU04 | constSizeU04 | [76:73] | 0–8 (2<sup>n</sup> alignment) |

## Bit layout

### URb variant — opcode 0x1cbc

```
[83:81]         Pu             <= UPu
[76:73]         constSizeU04   <= constSize
[37:32]         Ra_URb         <= URb
[29:24]         Sa             <= URa
[21:16]         URd            <= URd
[91:91],[11:0]  opcode         <= 0b1110010111100
```

### Imm variant — opcode 0x18bc

URb replaced with 16-bit immediate at [47:32].

## Latency

`UDP_subset` group. IDEST_SIZE=64 (register pair), ISRC_A_SIZE=64. Latency: 1–7 cycles output, 4–12 cycles true-dependency.

## Open questions

- No empirical examples. Likely used for TMA descriptor base-address alignment in UTMA sequences.
- `constSize` range 0–8 means alignment up to 256 bytes. Typical TMA descriptors require 32-byte (constSize=5) or 128-byte alignment.
- ~~UPu predicate output — overflow? carry? zero?~~ **Resolved (sm_120): UPu is
  never asserted in any probe**; the constSize field likewise has no
  observable effect — silicon computes `(URa.64 << 6) + URb`.
