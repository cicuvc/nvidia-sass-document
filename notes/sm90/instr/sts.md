# STS — Store to Shared Memory

**Opcode mnemonic:** `STS`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` (decoupled read-only scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Stores source register `Rb` into shared memory at address `[Ra + stride×URc + offset]`.

- **Plain (sImmOffset):** `smem[Ra + offset] = Rb` (Ra != RZ, signed 24-bit offset)
- **Plain (uImmOffset):** `smem[RZ + offset] = Rb` (Ra == RZ, unsigned 24-bit offset, no stride)
- **Uniform (sts_uniform_):** `smem[RZ + stride×URc + offset] = Rb` (uniform register index)

Compare with LDS which loads *from* shared memory; STS stores *to* shared memory.
The formats are symmetric: LDS reads `Rd`, STS writes `Rb`; LDS has `dst_wr_sb`,
STS has `dst_wr_sb=7` (hardwired, no variable-latency write scoreboard since
there's no destination register).

## Variant overview

3 encoding variants across 2 opcodes:

| Class | Opcode | Ra | Stride | Notes |
|-------|--------|:---:|:---:|-------|
| `sts__sImmOffset` | `0b1110001000` (`0x388`) | Ra != RZ | Yes | Signed 24-bit offset |
| `sts__uImmOffset` | `0b1110001000` (`0x388`) | Ra == RZ (0xFF) | No | Unsigned 24-bit offset |
| `sts_uniform_` | `0b1100110001000` (`0x1988`) | Ra == RZ | Yes | URc uniform register index |

## STS vs LDS — encoding comparison

| Field | LDS | STS |
|-------|-----|-----|
| Semantics | `Rd = smem[...]` | `smem[...] = Rb` |
| Opcode | `0x984` / `0x1984` | `0x388` / `0x1988` |
| Data register | `Rd` @ [23:16] | `Rb` @ [39:32] |
| IDEST_SIZE | 32/64/128 | 0 (no dest) |
| ISRC_B_SIZE | 0 | 32/64/128 |
| dst_wr_sb | VarLatOperandEnc | Hardwired 7 |
| Scoreboard | `INST_TYPE_DECOUPLED_RD_WR_SCBD` | `INST_TYPE_DECOUPLED_RD_SCBD` |
| Uniform reg | URb @ [37:32] | URc @ [69:64] |

## Modifiers

### Size (`sz`) — bits [75:73]

| Value | Mnemonic | Store width | Rb alignment |
|:-----:|----------|-------------|--------------|
| 0     | `.U8`    | 8-bit | — |
| 1     | `.S8`    | 8-bit | — |
| 2     | `.U16`   | 16-bit | — |
| 3     | `.S16`   | 16-bit | — |
| 4     | (default) | 32-bit | — |
| 5     | `.64`    | 64-bit | Rb % 2 == 0 |
| 6     | `.128`   | 128-bit | Rb % 4 == 0 |
| 7     | —        | `ILLEGAL_INSTR_ENCODING_ERROR` |

### Stride (`stride`) — bits [79:78]

Same as LDS: X1=0 (default), X4=1, X8=2, X16=3. Absent from uImmOffset variant.

## Shader constraint

CS shader only (same as LDS):
```
(%SHADER_TYPE == $ST_UNKNOWN) || ((%SHADER_TYPE == $ST_TRAP)||(%SHADER_TYPE == $ST_CS))
```

## Bit layout (non-uniform, 128-bit)

```
Bit  127                                                                          0
      ...###.####...........####.###......##..###.........
      ........#########################.......................

Field (sts__sImmOffset):
  [124:122],[109:105]  8b  opex        <= TABLES_opex_0(batch_t, usched_info)
  [121:116]            6b  req_bit_set         
  [115:113]            3b  src_rel_sb   <= VarLatOperandEnc(src_rel_sb)
  [112:110]            3b  dst_wr_sb    <= 7 (hardwired)
  [103:102]            2b  pm_pred             
  [91],[11:0]         13b  opcode       (0x388 for non-uniform)
  [79:78]              2b  stride       (absent in uImmOffset)
  [75:73]              3b  sz           (U8=0..128=6, INVALID7)
  [63:40]             24b  Ra_offset    (signed/unsigned 24-bit)
  [39:32]              8b  Rb           (source data register)
  [31:24]              8b  Ra           (*Ra for RaRZ/uImmOffset)
  [15]                 1b  Pg_not       
  [14:12]              3b  Pg           
```

### Uniform variant additions

```
  [69:64]  6b  Ra_URc       (uniform register index, different bits from LDS URb)
```

## Latency

MIO pipe, MIO_SLOW_OPS subset, decoupled read-only scoreboard.

- `INST_TYPE_DECOUPLED_RD_SCBD`: only read scoreboard active; write side is
  hardwired (no output register to track).
- `ISRC_A_SIZE = 32` (address register), `ISRC_B_SIZE = 32/64/128` (data register)
- `IDEST_SIZE = 0` — no destination, no write dependency created
- As consumer: same MIO_SLOW_OPS latency (8 cycles from compute producers)
- No output dependency latency — STS doesn't produce a register value

## Verified encodings

All verified against `cuobjdump -arch sm_90 -sass` from `libcublas.so`:

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x002080061a00c388` | — | `@!P4 STS [R26+0x2080], R6` |
| `0x000000151a009388` | — | `@!P1 STS [R26], R21` |
| `0x0020a0081400a388` | — | `@!P2 STS [R20+0x20a0], R8` |
| `0x0000401718008388` | — | `@!P0 STS [R24+0x40], R23` |
| `0x0021200d16007388` | — | `STS [R22+0x2120], R13` |
| `0x000080081b00b388` | — | `@!P3 STS.64 [R27+0x80], R8` |
| `0x000000121b009388` | — | `@!P1 STS.64 [R27], R18` |
| `0x0000000c07007388` | — | `STS.64 [R7], R12` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `st.shared.u32 [%ra], %rb` | `STS [Ra], Rb` |
| `st.shared.u64 [%ra], %rd` | `STS.64 [Ra], Rb` |
| `st.shared.v4.u32 [%ra], %rb` | `STS.128 [Ra], Rb` |
| `__shared__` C++ store | `STS` with computed register address |

## Shared-memory address model — where `Ra` (the base) comes from

The `Ra` address fed to `STS`/`LDS` is **not** loaded from constant memory. Unlike
the local/stack base (`c[0x0][0x28]`) and the global descriptor (`c[0x0][0x208]`),
the shared window base is **computed from special registers** in the prologue:

```
S2UR UR5, SR_CgaCtaId        ; CTA rank within its cluster/CGA (0 if non-clustered)
UMOV UR4, 0x400
ULEA UR4, UR5, UR4, 0x18     ; UR4 = (CgaCtaId << 24) + 0x400   ← shared window base
LEA  R0, Rtid, UR4, 0x2      ; addr = (tid<<2) + base
STS  [R0], ...
```

So the shared-space (STS/LDS) byte address is:

```
addr = (SR_CgaCtaId << 24) + 0x400 + local_offset
```

- `0x400` — per-CTA base offset (first 1 KiB of the window is reserved).
- `SR_CgaCtaId << 24` — **distributed shared memory (DSMEM)**: each CTA in a
  cluster owns a 16 MiB (`1<<24`) slice; bits [31:24] select the CTA rank so a CTA
  can address a peer's shared memory (`mapa`). Non-clustered launch ⇒ rank 0 ⇒ base
  `0x400`.

The **generic** address of shared memory (`__cvta_shared_to_generic`) prepends a
high-32-bit window base from `SR_SWINHI`:

```
generic_ptr = { SR_SWINHI, (SR_CgaCtaId<<24)+0x400+offset }   ; hi:lo
```

### Empirical (H800 PCIe, driver 580.82.07, CUDA 12.8)

Probes: `tests/smem_base_dump.cu`, `tests/smem_cluster_dsmem.cu`.

| Quantity | Value | Notes |
|----------|-------|-------|
| shared base (offset 0, generic) | `0x00007f4d_00000000` | high 32b = `SR_SWINHI` (per-context virtual window, varies) |
| `&smem[0]` shared offset | `0x400` | non-clustered ⇒ `CgaCtaId=0` |
| `&smem[0]` generic | `0x00007f4d_00000400` | = base + `0x400` |
| cluster CTA0 offset | `0x00000400` | `__cluster_dims__(2,1,1)` |
| cluster CTA1 offset | `0x01000400` | delta = `0x0100_0000` = `1<<24` ✓ |

The `1<<24` per-rank delta confirms the DSMEM slicing. See `s2ur.md`
(`S2UR SR_CgaCtaId`), `ulea.md` (`ULEA …, 0x400, 0x18`), and `ldc.md`
(constant-bank preset region, which does **not** hold a shared base).

## Open questions

- **Stride variants `.X4`/`.X8`/`.X16`**: Not present in cublas.
- **`sts_uniform_` (URc variant)**: What triggers the uniform register form?
- **Why URc at [69:64] vs LDS's URb at [37:32]?** The bit position difference
  is notable — possibly reflects a different micro-architectural pipeline slot.

## Resolved: silicon-verified (SM120)

`tests/asm_construct/test_lds_sts.py` confirms STS shares the LDS addressing/
window semantics (see lds.md): 32-bit/64-bit stores, narrow stores
(U8/S8/U16/S16), immediate and register offsets, uniform `[RZ+URb+off]`.
STS is DECOUPLED_RD_SCBD (no result scoreboard — there is no destination
register); the stored data register must be scoreboard-ready like any input.
Shared-window allocation note in lds.md applies (dynamic shared_mem at
launch; static section not yet consumed by the driver).
