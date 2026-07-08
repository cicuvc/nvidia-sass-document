# LDG — Load from Global Memory

**Opcode mnemonic:** `LDG`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` (decoupled read/write scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_AGU_UNORDERED_WR`

## Semantics

Loads data from global device memory into destination register `Rd`. On sm_90,
global memory accesses are **memory-descriptor-based**: a uniform register pair
`URb` holds a 64-bit memory descriptor (base address + access attributes), and
the load address is formed as `desc[URb][Ra + offset]`.

- **Memdesc (desc form):** `Rd = *global(URb, Ra + offset)` — URb holds the
  memory descriptor, Ra is a 64-bit register pair offset.
- **Uniform:** `Rd = *global(Ra + URb + offset)` — URb is a uniform index into
  the address.
- **Plain:** `Rd = *global(Ra + offset)` — base register only, no uniform component.

### Memory descriptor ∈ 64-bit pointer

The `desc[URb]` descriptor is **not** a complex bitfield like WGMMA/TMA
descriptors. It is a **64-bit global-memory base address** loaded from constant
memory via `ULDC.64`:

```
ULDC.64 UR4, c[0x0][0x208]     # load kernel-param pointer value into UR4 pair
LDG.E R3, desc[UR4][R2.64]     # UR4 = base addr, R2:R3 = per-thread offset
```

**sm_89 → sm_90 structural evolution:**
```
sm_89:  ULDC.64 UR4, c[0x0][0x118]     # load pointer
        IMAD.WIDE R2, R4, R5, c[...]    # compute addr = pointer + offset
        LDG.E R3, [R2.64]               # load from synthesized address

sm_90:  ULDC.64 UR4, c[0x0][0x208]     # load pointer
        LDG.E R3, desc[UR4][R2.64]      # hardware fuses base + offset in AGU
```

On sm_89 the compiler emitted an explicit `IMAD.WIDE` to add base+offset before
the load. On sm_90 this addition is folded into the LDG hardware — the
descriptor provides the base, the register(s) provide the offset, and the AGU
(Address Generation Unit) produces the final physical address. The `desc`
syntax in cuobjdump strictly means **"base address handle"**, not a structured
descriptor with sub-fields.

The 64-bit value itself is just a global-memory virtual address — the same
pointer value the kernel received as a parameter. Hardware uses it for
virtual→physical translation, bounds checking, and access-control enforcement.

## Variant overview

LDG has **6 encoding variants** across **2 opcodes**:

| Class | Opcode | memdesc | E | Ra | Address |
|-------|--------|:---:|:---:|:---:|---------|
| `ldg__sImmOffset` | `0x381` | 0* | 0 | Ra≠RZ | `[Ra + offset]` |
| `ldg__uImmOffset` | `0x381` | 0* | 0 | Ra=RZ | `[RZ + offset]` |
| `ldg_uniform__Ra32` | `0x1981` | 0 | 0 | Ra≠RZ | `[Ra + URb + offset]` |
| `ldg_uniform__RaRZ` [ALT] | `0x1981` | 0 | 0 | Ra=RZ | `[URb + offset]` |
| `ldg_uniform__Ra64` | `0x1981` | 0 | 1 | Ra≠RZ(64) | `[Ra.64 + URb + offset]` |
| `ldg_memdesc__Ra64` | `0x1981` | 1 | 1 | Ra≠RZ(64) | `desc[URb][Ra.64 + offset]` |

*\* Plain 0x381 always has memdesc=0 hardwired (bit[76] not present in the encoding layout).*

### Empirical note

**All LDG instructions in `libcublas.so` and user-compiled kernels on sm_90 use the
`ldg_memdesc__Ra64` form** (`LDG.E desc[URb][Ra.64+offset]`). The plain and uniform
non-memdesc forms are not emitted by ptxas — the compiler always wraps global
addresses in memory descriptors.

## Modifiers

LDG has the richest modifier set of any MIO instruction:

### E — Extended address — bit [72]

| Value | Mnemonic | ISRC_A_SIZE | Ra width |
|:-----:|----------|:-----------:|:--------:|
| 0     | (default, omitted) | 32 | Single register |
| 1     | `.E` | 64 | Register pair (Ra % 2 == 0) |

### COP — Cache operator — bits [86:84]

| Value | Mnemonic | Cache hint |
|:-----:|----------|-----------|
| 0     | `.EF` | Evict-first |
| 1     | (default, omitted) | Evict-normal |
| 2     | `.EL` | Evict-last |
| 3     | `.LU` | Last-use |
| 4     | `.EU` | Evict-unchanged |
| 5     | `.NA` | No-allocate |
| 6–7   | —       | `ILLEGAL_INSTR_ENCODING_ERROR` |

### SP2 — Sector-cache prefetch — bits [69:68]

| Value | Mnemonic | Prefetch size |
|:-----:|----------|---------------|
| 0     | (default, omitted) | None |
| 1     | `.LTC64B` | 64 byte |
| 2     | `.LTC128B` | 128 byte |
| 3     | `.LTC256B` | 256 byte |

### SEM / SCO / PRIVATE — memory qualifier — bits [80:77]

Encoded via `TABLES_mem_1(sem, sco, private)` into a 4-bit field:

| SEM | SCO | PRIVATE | Encoded | Qualifier string |
|-----|-----|:---:|:---:|------------------|
| WEAK(1) | nosco(0) | noprivate(0) | 0 | (default, none) |
| CONSTANT(0) | nosco(0) | noprivate(0) | 4 | `.CONSTANT` |
| WEAK(1) | CTA(1) | noprivate(0) | 2 | `.CTA` |
| STRONG(2) | GPU(4) | PRIVATE(1) | 6 | `.STRONG.GPU.PRIVATE` |
| MMIO(3) | GPU(4) | noprivate(0) | 8 | `.MMIO.GPU` |

Only non-default qualifiers (not `WEAK + nosco + noprivate`) are printed.

### Pnz — NZ predicate — bits [67:64]

Encoded via `TABLES_Pnz_0(Pnz@not, Pnz)`:

| Pnz@not | Pnz | Encoded | Mnemonic |
|:---:|:---:|:---:|----------|
| 0 | 7 (PT) | 0 | (default, omitted) |
| 0 | 0 | 7 | `P0` |
| 0 | 1 | 6 | `P1` |
| ... | ... | ... | ... |
| 1 | 0 | 15 | `!P0` |

### Pu — Write predicate — bits [83:81]

Default PT(7), omitted. When non-default, prints `Pu` between the mnemonic and
`Rd`. Analogous to the carry output predicate on integer/float instructions.

### Size — bits [75:73]

| Value | Mnemonic | Width | Rd alignment |
|:-----:|----------|-------|-------------|
| 0–1   | `.U8`/`.S8` | 8-bit | — |
| 2–3   | `.U16`/`.S16` | 16-bit | — |
| 4     | (default) | 32-bit | — |
| 5     | `.64` | 64-bit | Rd % 2 == 0 |
| 6     | `.128` | 128-bit | Rd % 4 == 0 |
| 7     | — | `ILLEGAL_INSTR_ENCODING_ERROR` |

## Bit layout (ldg_memdesc__Ra64, 128-bit)

```
Bit  127                                                                          0
      ...###.####...#...##..#.#...#...####.###......##..###.........
      .........######..##################...........................................
```

| Bits | Width | Field | Source |
|------|:---:|-------|--------|
| [124:122],[109:105] | 8 | opex | TABLES_opex_0 |
| [121:116] | 6 | req_bit_set | slot |
| [115:113] | 3 | src_rel_sb | VarLatOperandEnc |
| [112:110] | 3 | dst_wr_sb | VarLatOperandEnc |
| [103:102] | 2 | pm_pred | slot |
| [91],[11:0] | 13 | opcode | 0x1981 |
| [90] | 1 | input_reg_sz_32_dist | *reserved |
| [86:84] | 3 | cop (COP) | slot |
| [83:81] | 3 | Pu | slot |
| [80:77] | 4 | mem (SEM/SCO/PRIVATE) | TABLES_mem_1 |
| [76] | 1 | memdesc | 1 (desc form) |
| [75:73] | 3 | sz (size) | slot |
| [72] | 1 | e (E) | slot |
| [69:68] | 2 | sp2 (SP2) | slot |
| [67:64] | 4 | Pnz | TABLES_Pnz_0 |
| [63:40] | 24 | Ra_offset | slot |
| [37:32] | 6 | Ra_URb (memory descriptor) | slot |
| [31:24] | 8 | Ra (address register) | slot |
| [23:16] | 8 | Rd (destination) | slot |
| [15] | 1 | Pg_not | slot_attr |
| [14:12] | 3 | Pg | slot |

## Latency

MIO pipe, MIO_SLOW_OPS subset ($VQ_AGU_UNORDERED_WR).

- `ISRC_A_SIZE = 32` or `64` (E-dependent)
- Output dependency managed via decoupled scoreboard (VarLatOperandEnc on dst_wr_sb)

Same MIO_SLOW_OPS latency as LDS/STS.

## Verified encodings

All verified against `cuobjdump -arch sm_90 -sass` from `libcublas.so` and user kernels:

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000800812068981` | `0x000ea2000c1e9900` | `@!P0 LDG.E.CONSTANT R6, desc[UR8][R18.64+0x80]` |
| `0x0000000812159981` | `0x000ee2000c1e9900` | `@!P1 LDG.E.CONSTANT R21, desc[UR8][R18.64]` |
| `0x0001000810089981` | `0x001162000c1e9900` | `@!P1 LDG.E.CONSTANT R8, desc[UR8][R16.64+0x100]` |
| `0x0000000402037981` | `0x000ea2000c1e1900` | `LDG.E R3, desc[UR4][R2.64]` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `ld.global.u32 %r, [%rd]` | `LDG.E Rd, desc[URb][Ra.64]` |
| `ld.global.ca.u32 %r, [%rd]` | `LDG.E.EF Rd, desc[URb][Ra.64]` |
| `ld.global.cs.u32 %r, [%rd]` | `LDG.E.CONSTANT Rd, desc[URb][Ra.64]` |
| `ld.volatile.global.u32 %r, [%rd]` | `LDG.E Rd, desc[URb][Ra.64]` (via mem qualifier) |
| Kernel pointer access (`*ptr`) | `LDG.E desc[URb][Ra.64]` |

All global loads on sm_90 go through memory descriptors — there is no plain
register-only address form in practice.

## Open questions

- **Plain 0x381 forms (ldg__sImmOffset/uImmOffset):** What scenario triggers
  these? Not observed in user code or cublas. Possibly a legacy/simulated path.
- **Non-64-bit E forms:** What generates E=noe loads? All observed instances
  use E=1 (.E).
- **SP2 prefetch (.LTC64B/.LTC128B/.LTC256B):** What triggers sector-cache
  prefetch on LDG?
- **Pnz predicate:** Never observed with non-PT Pnz in traces. What code
  pattern produces a non-trivial Pnz?
