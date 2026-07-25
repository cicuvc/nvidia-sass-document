# LDG — Load from Global Memory

**Opcode mnemonic:** `LDG`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` (decoupled read/write scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_AGU_UNORDERED_WR`

## Semantics

Loads data from global device memory into destination register `Rd`. On sm_80+,
global memory accesses use a **64-bit policy descriptor** model: `desc[UR4]`
consumes the UR4:UR5 pair as a 64-bit L2 cache eviction policy word. UR4 provides
the low 32 bits (base policy, default = 0 = no special policy). UR5 provides the
high 32 bits encoding cache priority, fraction/window, and other L2 hints set up
by `createpolicy`.

- **Memdesc (desc form):** `Rd = *global(Ra + offset)` with cache policy from
  `UR4:UR5`. Ra is a 64-bit register pair providing the byte address (typically
  loaded from the kernel parameter at `c[0x0][0x380]` via `LDC.64`).
- **Uniform:** `Rd = *global(Ra + URb + offset)` — URb provides a uniform
  address offset.
- **Plain:** `Rd = *global(Ra + offset)` — base register only, no uniform component.

### 64-bit cache policy descriptor (empirically confirmed, sm_120)

`desc[UR4]` uses the UR4:UR5 uniform register pair as a **64-bit policy word**,
not a table index. The compiler always loads the pair via `LDCU.64 UR4, c[0x0][off]`.

- **UR4 (low 32 bits):** typically 0 (default/no special policy). All tested
  values produce the same behavior — the hardware appears to use a fixed base
  policy when no explicit cache hint is needed.
- **UR5 (high 32 bits):** encodes L2 cache eviction policy — priority bits,
  fraction nibble (for fractional mode) or window bits (for range mode). Set
  by `createpolicy` PTX and lowered via UMOV+USHF+ULOP3 on sm_120, or direct
  UMOV literal on sm_80.
- **UR5 field validation:** any byte in UR5 set to all-1s (0xFF) causes a
  hardware fault — the hardware validates each byte-aligned field within the
  policy word.

**Evidence against "table index" interpretation and for "policy descriptor":**

1. **UR5 matters, UR4 doesn't (within valid range):** Setting UR5 to different
   values changes cache policy behavior (e.g. `createpolicy.fractional` produces
   specific UR5 bit patterns). UR4 is always 0 in compiler output.
2. **UR5 byte-0xFF causes faults:** The hardware validates UR5 byte fields;
   0xFFFF0000, 0xFF000000, 0x00FF0000 etc. all fault. 0xDEADBEEF works fine.
   This is cache-policy field validation, not a table lookup.
3. **`ULDC.64` loads 64 bits, not 6:** The compiler loads both UR4 and UR5 as a
   pair, and both are consumed. The "6-bit index" theory only considered UR4.
4. **No descriptor table exists:** All UR4 values (0, 1, 4, 8, 16, 0x100,
   0xFFFFFFFF) produce identical behavior — they all encode "default policy".
   There is no table with different base addresses at different indices.

The compiler idiom:
```
LDCU.64 UR4, c[0x0][0x358]     # load default policy (0) into UR4:UR5
LDC.64  R2, c[0x0][0x380]      # load byte address (kernel param)
LDG.E   R3, desc[UR4][R2.64]   # load with cache policy from UR4:UR5
```

On sm_89 the compiler emitted an explicit `IMAD.WIDE` to add base+offset. On
sm_90+ this is folded into the AGU — the descriptor provides translation
parameters and the register(s) provide the byte address.

### 64-bit descriptor word (UR4:UR5) and cache policy — sm_120

`desc[UR4]` actually uses the UR4:UR5 pair as a **64-bit descriptor word**, not just UR4
alone. The compiler always loads the pair via `LDCU.64 UR4, c[0x0][offset]` (64-bit load).
The lower 32 bits (UR4) provide the base descriptor index (typically 0 for default global
memory). The upper 32 bits (UR5) encode **cache eviction policy** and other attributes in
a byte-packed format.

**Evidence:**
- `LDCU.64 UR4, c[0x0][0x358]` loads 64 bits into UR4:UR5; STG/LDG only names `desc[UR4]`
  but UR5 is implicitly consumed.
- Any byte in UR5 set to `0xFF` (all 8 bits) causes an execution fault — the hardware
  validates specific byte-aligned fields within the 64-bit descriptor.
- `0xDEADBEEF` in UR5 works fine (no byte = 0xFF); `0xFFFF0000` faults.

**Cache policy encoding (fractional, from `createpolicy` PTX → SASS):**

The PTXAS lowering pattern for `createpolicy.fractional.L2::<policy>.b64` is:
```
UMOV UR4, F_val                       # fraction * 16 (e.g. 0xf0 for 1.0)
USHF.R.U32 UR4, UR4, 0x4             # → low nibble = fraction value
UMOV UR5, P_val                       # priority encoding
ULOP3.LUT UR5, UR5, 0xf, UR4, 0xf8   # combine priority + fraction
USHF.L.U32 UR5, UR5, 0x14            # << 20: shift to UR5[31:12]
UMOV UR4, URZ                         # UR4 = 0 (base descriptor)
```

Final UR5 value layout (bits [31:0]):
```
[31:24]  priority byte (shifted from ULOP3 bits [11:4])
[23:20]  fraction nibble = fraction × 16 - 1
[19:0]   zero
```

**Priority byte [31:24] bit assignments:**

| Bit | Value | Meaning |
|-----|-------|---------|
| 4   | 0x10  | `evict_unchanged` (retain current priority) |
| 5   | 0x20  | `evict_first` |
| 6   | 0x40  | `evict_last` |
| 8   | —     | always set (base/L2 flag?) |

Observed combinations (P_val → final priority byte):

| PTX priority | P_val | Priority byte |
|-------------|-------|---------------|
| `L2::evict_last` | 0x140 | 0x14 |
| `L2::evict_first`, `L2::evict_first.L2::evict_unchanged` | 0x120 | 0x12 |
| `L2::evict_unchanged.L2::evict_first` | 0x110 | 0x11 |

**Fraction nibble [23:20]:**

| Fraction | F_val | F_val >> 4 | Final nibble |
|----------|-------|-----------|-------------|
| 1.0  | 0xf0 | 0x0f | 0xF |
| 0.75 | 0xb0 | 0x0b | 0xB |
| 0.5  | 0x70 | 0x07 | 0x7 |
| 0.25 | 0x30 | 0x03 | 0x3 |

Encoding: `nibble = fraction × 16 - 1` (so 1.0 → 15 = 0xF).

**Range-based policy** — more complex PTXAS lowering with USHF.R.U64 address
arithmetic. The total_size determines the shift chain via `UF2I.U32.CEIL.NTZ`:

```
UF2I.U32.CEIL.NTZ UR4, log2(total)   # e.g. 12 for 4096, 14 for 16384
UIADD3 UR4, UR4, -7                  # → log2(total) - 7
UVIMNMX.S32 UR10, UR4, 0xc           # UR10 = max(log2(total)-7, 12)
USHF.L  UR4, 1, UR10                 # UR4 = 1 << UR10
UIADD3  UR4, UR4, primary_size - 1   # → (1<<UR10) + primary - 1
USHF.R.U64 (address >> UR10)         # align address to UR10-bit granule
# … further address math, adding/subtracting shifted address, then UIMNMX 0x7F
```

The final UR5 has window bits packed via ULOP3 chain at bits [12:5] after total
shift of 20:

| primary / total | ratio | UR5 LOW | window bits [12:5] | decoded |
|-----------------|-------|---------|--------------------|---------|
| 512 / 2048 | 1/4 | 0x20 | 1 | `total/128` — or adapter-chosen granularity |
| 1024 / 4096 | 1/4 | 0x20 | 1 | (same window for all total < 16384) |
| 2048 / 8192 | 1/4 | 0x20 | 1 | |
| 4096 / 16384 | 1/4 | 0x40 | 2 | total/4096? (16384/4096=4, but 2) |
| 8192 / 32768 | 1/4 | 0x60 | 3 | |
| 1024 / 8192 | 1/8 | 0x20 | 1 | ratio does NOT affect window |
| 512 / 4096 | 1/8 | 0x20 | 1 | |

The window field depends only on **total size**, not the ratio. Apparent
mapping: `window = min(total / 8192, 3) * 32 + 32` (clamps to 0x20 for
total ≤ 8192, 0x40 for 16384, 0x60 for 32768). The hardware likely uses
this as `total / 128` capped and quantized.

**Priority byte for range mode:**

| Priority | Priority byte | vs fractional |
|----------|--------------|---------------|
| evict_last | 0x1c | 0x14 (fractional used 0x14) |
| evict_first | 0x1a | 0x12 |
| evict_last + evict_first | 0x1d | — |

Range mode priority bytes are fractional+8 (0x14+0x08=0x1c, 0x12+0x08=0x1a).
Bit 3 set in the priority byte appears to be a "range mode" flag.

**CVT mode** (`createpolicy.cvt.L2.b64 policy, access-property`):

Converts an access property handle (obtained from CUDA Driver API e.g.
`cudaStreamSetAttribute` / `CUaccessPolicyWindow`) into a cache policy.
Produces a **non-zero UR4** value — both halves of the 64-bit pair are populated,
unlike fractional and range which only use UR5. Observed via stream-level policy:

```
Default stream:   c[0x0][0x358] = 0x00000000_00000000  (no policy)
Stream with L2:   c[0x0][0x358] = 0x05800087_f2cc0400  (persisting + streaming)
```

The driver places the stream's access policy window directly at c[0x0][0x358];
the `LDCU.64 UR4, c[0x0][0x358]` idiom in compiler SASS picks up this default
policy for the entire kernel. Explicit `createpolicy` params use a different
cbank offset (kernel parameter slot).

**Impact on STG/LDG:** When `.L2::cache_hint` is used with a `cache_policy` operand,
the policy value occupies UR5 (upper 32 bits) while UR4 = 0 (default descriptor).
The full 64-bit `desc[UR4:UR5]` value is passed to the AGU hardware, which
interprets UR5 as cache-control metadata.

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
