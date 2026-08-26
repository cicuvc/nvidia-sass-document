# Cache Descriptor (desc[URx] 64-bit) — bit-field decode

Empirically decoded on sm_120 (RTX 5090, CUDA 12.8) by (a) compiling
`createpolicy` variants and reading the SASS lowering immediates, and (b) reading the
driver-generated policy word at `c[0x0][0x358]` (stream access-policy window) from a
hand-assembled kernel and decoding it with single-factor sweeps.

There are **two distinct 64-bit formats**, distinguished by bit 4 of the UR5 high byte:
`createpolicy`-generated descriptors set `[28]` (0x10 in the priority byte), driver
access-property descriptors keep it clear.

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). The probing test itself is timing/state-sensitive and flaky on both GPUs.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

## Format 1 — `createpolicy` (UR4 = 0)

PTX `createpolicy.{fractional|range}.L2::<prio>[.L2::<sec>].b64` lowers to a uniform
register chain (UMOV / USHF / ULOP3 / …) that builds UR5 only; **UR4 = 0**.

### Priority byte `[31:24]` (both modes)

| bit | value | meaning |
|-----|-------|---------|
| 0 | 0x01 | secondary priority = `evict_first` |
| 1 | 0x02 | primary priority = `evict_first` |
| 2 | 0x04 | primary priority = `evict_last` |
| 3 | 0x08 | **range mode flag** (set by `createpolicy.range`) |
| 4 | 0x10 | constant base (createpolicy-format marker) |

Primary encodings (base 0x10): `evict_unchanged`=0x10, `evict_first`=0x12,
`evict_last`=0x14, `evict_normal`=0x16 (= first|last bits). Secondary
`evict_first` adds 0x01 (bit0); secondary `evict_unchanged`/default adds nothing.
Verified combos: last→0x14, last.first→0x15, first→0x12, first.first→0x13,
normal→0x16, normal.first→0x17, unchanged→0x10, unchanged.first→0x11.

### Fractional mode — UR5 = `prio<<24 | frac_nib<<20`

| bits | field | encoding |
|------|-------|----------|
| [31:24] | priority byte | table above |
| [23:20] | fraction nibble | `ceil(fraction×16) − 1` (1.0→0xF, 0.75→0xB, 0.5→0x7, 0.25→0x3, 0.125→0x1, 1/16→0x0) |
| [19:0]  | 0 | |

ptxas lowering: `UMOV UR4, F; USHF.R.U32 UR4, UR4, 0x4` (F = nibble<<4),
`UMOV UR5, P; ULOP3.LUT UR5, UR5, 0xf, UR4, 0xf8; USHF.L.U32 UR5, UR5, 0x14`,
`UMOV UR4, URZ`. F values: 1.0→0xf0, 0.75→0xb0, 0.5→0x70, 0.25→0x30, 0.1→0x10,
0.0625→(nibble 0, different chain). P values: unchanged 0x100, first 0x120,
last 0x140, normal 0x160 (+0x10 when secondary=first).

### Range mode — UR5 = `prio<<24 | gsz<<20 | agr<<12 | win<<5`

ptxas computes `UR10 = max(ceil(log2(total_size)) − 7, 12)` (granule = 1<<UR10,
floor at 4 KB) and packs:

| bits | field | formula |
|------|-------|---------|
| [31:24] | priority byte | fractional byte + 0x08 (range flag), e.g. last→0x1c, last.first→0x1d, first→0x1a, normal→0x1e, unchanged→0x18 |
| [23:20] | gsz | `UR10 − 12` (0 for total ≤ 512 KB; 2 for 2 MB; 3 for 4 MB) |
| [18:12] | agr | `(addr >> UR10) & 0x7F` (address granule index; verified offsets 0x1000/0x10000/…) |
| [11:5]  | win | `min(((addr + (1<<UR10) + primary_size − 1) >> UR10) − (addr >> UR10), 0x7F)` (primary-range granule span; e.g. 512/2048→1, 4096/16384 unaligned→2, 1 MB/2 MB→64) |
| [4:0]   | 0 | |

Verified across 6 strategy combos × 18 size pairs × 4 address offsets (432 GPU reads,
all matching the formulas).

## Format 2 — access property (`createpolicy.cvt` / stream policy)

Driver-encoded `CUaccessPolicyWindow` (base_ptr, num_bytes, hitRatio, hitProp, missProp),
read at `c[0x0][0x358]`, and the `createpolicy.cvt` result (a **pass-through** — verified:
any 64-bit input becomes the desc verbatim) use the full 64-bit word:

| word | bits | field | formula |
|------|------|-------|---------|
| UR4 | [31:0] | window base | `(base_ptr >> 12) & 0xFFFFFFFF` — full 32-bit word is the 4 KB-aligned address (>>12), no bit shift; driver rounds base down to 4 KB |
| UR5 | [31:24] | hit/miss byte | bit0 = missProp==streaming; bit1 = hitProp ∈ {streaming, normal}; bit2 = hitProp ∈ {persisting, normal} — i.e. hitProp: streaming=0x02, persisting=0x04, normal=0x06; +miss streaming bit0. Equivalent to the createpolicy priority byte minus the 0x10 marker. |
| UR5 | [23:20] | hit-ratio nibble | `floor(hitRatio × 16)` (0.0625→1, 0.125→2, 0.2→3, 0.3→4, 0.45→7, 1.0→15) |
| UR5 | [19:0] | window size | `ceil(num_bytes / 4096) × 32` (20-bit, i.e. size rounded up to 4 KB; 4096→0x20, 32 KB→0x100, 1 MB→0x2000, 127 MB→0xFE000) |

Constraints seen: `missProp == persisting` rejected by the driver (`CUDA_ERROR_INVALID_VALUE`);
`hitProp` may be NORMAL/STREAMING/PERSISTING. Example: hit=persisting, miss=streaming,
ratio=1.0, num=4096, base=0x0c000000 → `0x05f00020_0000c000`
(base>>12 = 0xc000 in UR4; byte 0x05, ratio nibble 0xF, num/128 = 0x20 in UR5).

### Verified factor independence & boundaries (access property)

- **hit/miss byte**: identical for every hitRatio; hitProp {normal,streaming,persisting}
  → byte bits {1+2, 1, 2}, missProp streaming adds bit0 (normal/normal=0x06,
  streaming/normal=0x02, persisting/streaming=0x05, …).
- **ratio nibble** `[23:20] = floor(hitRatio×16)` for all hit/miss/num combos; driver
  rejects hitRatio < 0 or > 1 (`CUDA_ERROR_INVALID_VALUE`).
- **num field**: `ceil(num/4096)×32` (min 32 = 4096 B); num=0 → field 0. Values up to
  127 MB match exactly; **128 MB = 0x100000 overflows the 20-bit field and encodes as 0**
  (bit 20 dropped, ratio nibble untouched) — semantics of the 0x100000-truncated encoding
  (no window vs full window) unverified; 129 MB rejected.
- **base field** `UR4 = (base>>12)&0xFFFFFFFF`: base rounded **down** to 4 KB
  (base+0xFFF unchanged, +0x1000 → UR4+1); the full 64-bit address participates
  (base=2^32 → UR4 = 0x100000, base=2^37 → 0x200000).

Note the two ratio encodings differ: createpolicy fractional uses `ceil(f×16)−1`
(so f=1/16 → 0, f=0.9375 → 0xE), the access property uses `floor(r×16)`
(r=0.9375 → 0xF).

## Reading the descriptor word at runtime

ptxas materializes the createpolicy/cvt result directly into `UR4:UR5` (the desc pair).
To dump it from a compiled kernel, store the policy operand:

```ptx
createpolicy.fractional.L2::evict_last.b64 pol, 0.75;
ld.global.L2::cache_hint.u32 %0, [%1], pol;
mov.u64 %2, pol;          // ptxas emits MOV.64 R8, UR6  (UR6:UR7 = desc)
```

The driver-placed default policy is read with `LDCU.64 {UR4,UR5}, c[0x0][0x358]`.
**Gotcha:** after `cuStreamSetAttribute(CU_STREAM_ATTRIBUTE_ACCESS_POLICY_WINDOW, …)`,
the cbank word lags ~4 kernel launches (same as the LDCU parameter lag) — warm up with
≥6 launches before reading, or you read a stale value (observed 4× stale, then stable).

## When is the descriptor generated dynamically? (address/fraction dependence)

The descriptor is **not** derived from the memory-access address. It is computed from the
`createpolicy` *operands* (which may themselves be runtime values):

| createpolicy form | desc computation | dynamic? |
|-------------------|------------------|----------|
| `fractional` with immediate fraction | compile-time constants (`UMOV UR5, P; …`) | no |
| `fractional` with **register** fraction | `UFMUL UR4, fr, 15.99; UF2I.U32.TRUNC.NTZ; <<4; &0xf0` | yes — per-run fraction value |
| `range` | USHF/ULOP3 chain built from `[a]`, `psz`, `tsz` (UR10/granule) | yes — per-run `[a]` address (agr/win fields) |
| `cvt` | pass-through of the access-property operand (driver cbank word) | yes — per-run property value |

Verified (RTX 5090, `range_split` kernel: `createpolicy.range … [p_a], 512, 2048` +
`ld … [p_ld]` + dump):
- changing the **load address** `p_ld` leaves the dumped desc unchanged;
- changing the **policy address** `p_a` changes the `agr` field (`(p_a>>12)&0x7f`).

Two loads sharing one policy (e.g. `[p]` and `[p+128]`) use the **same** descriptor word —
ptxas computes the desc once and both `LDG.E … desc[URx]` reference it. The hardware matches
each access address against the range encoded in the fixed descriptor (primary/secondary
window via agr/win), it does not re-derive the descriptor per access.

The register-fraction lowering (`fr × 15.99` then truncate) yields
`fraction_nib = floor(fr × 16)` for all practical values — numerically identical to the
immediate-form `ceil(f×16) − 1` (0.75→0xB, 1.0→0xF, 1/16→0x0, 0.9375→0xE, all verified).

## Hardware validation (STG vs LDG)

Feeding arbitrary descriptor words to `STG.E desc[URx]` / `LDG.E desc[URx]`:
- **LDG**: every value tested (0, fractional/range encodings, access-property words,
  0xFF bytes anywhere) executes without fault — the load path does not validate.
- **STG**: valid createpolicy and access-property encodings work; `0xFFFF0000` in UR5
  (0xFF in the priority/ratio bytes [31:16]) raises **CUDA_ERROR_ILLEGAL_INSTRUCTION (715)**;
  `0x0000FFFF` in the UR5 low word (num field) and `0xDEADBEEF` (no 0xFF byte) are accepted.
  So the earlier "any UR5 byte = 0xFF faults" note applies only to the **high** UR5 bytes
  ([31:16], the priority/ratio fields) on the store path; the exact illegal-value set is
  still partially unverified (further probing after a 715 poisons the CUDA context).

## Open questions

- The 128 MB `num_bytes` encoding truncates to 0 in the 20-bit field; whether hardware
  treats that as "no window", "full window", or rejects it behaviorally is untested
  (num=128 MB is the driver-accepted maximum).
- Whether hardware distinguishes the two formats by UR5 bit4 (0x10) alone, and what a
  createpolicy-format word with UR4 ≠ 0 does, is not yet verified behaviorally.
- Exact STG descriptor validation: which UR5 high-byte values besides 0xFF are rejected,
  and whether UR4 (base field) participates in validation.
