# UMEMSETS — bulk shared-memory zero-init  → PTX `st.bulk`

**Opcode mnemonic:** `UMEMSETS` = `0b1001111001011` (0x13cb, 5067)
**Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_AGU` (=15, the AGU unordered queue)

New on sm100 (Blackwell). `UMEMSETS` = **U**niform **MEM**ory **SET**S — the
SASS realization of PTX **`st.bulk`**, a bulk zero-initialization of a shared
memory region. It fills `[URa + offset]` with zeros for `URc * 8` bytes (the size
being in units of 8 — the ONLY64 modifier).

## Semantics
`UMEMSETS.64 [URa + URa_offset], URb, URc` where `URb` must be **URZ**(0xff in
the 8-bit uniform register field — the CONDITION enforces it), and `URc` is a
byte count in units of 8. The operation asynchronous; `src_rel_sb` is active
(releases a read scoreboard once the memory-set has completed). `ISRC_B_SIZE=64`
(URb is a 64-bit pair carrying the init value, enforced as URZ:URZ).

This is the hardware memset(0) for shared memory. The `size` PTX operand
constraint (multiple of 8, max 16777216) follows from `URc` encoding in 8-byte
units.

## Variant overview
| Class | Kind | Opcode |
|-------|------|--------|
| `umemsets_` | CLASS | 0x13cb |

Single variant (no alternates). The `.64` suffix in cuobjdump comes from the
`ONLY64` enum bit [82].

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `sz` | `ONLY64` | [82] | always 64-bit init (single value) |

## Bit layout (128-bit)
```
[91]∥[11:0]         opcode     = 0x13cb
[82]                ONLY64
[71:64]             URc (size in 8-byte units)
[54:40]             URa_offset (24-bit signed immediate)
[39:32]             URb (must be URZ = 0xff)
[31:24]             URa (dst shared-memory address)
[15]                Pg_not ; [14:12] Pg = @UPg
```
`$VQ_AGU` — the AGU (address-generation unit) unordered queue, same as global
stores (`ST.E.STRONG.GPU`) and atomics, not the TMA or TC queue.

## Verified encoding (cuobjdump, sm_100a, CUDA 13.3 ptxas)
```
st.bulk.shared::cta [dst], n, 0  →  UMEMSETS.64 [UR5], URZ, UR4
  opcode=0x13cb  URa=UR5(dst)  URb=URZ(0xff)  URc=4(n>>3)  ONLY64=1
```
pxtas generates `USHF.R.U32.HI UR4, URZ, 0x3, UR4` to compute `n>>3` before
issuing UMEMSETS.

## Cross-references
- `notes/sm100/instr/utcatomsws.md` — TMEM allocator (different queue but same
  uniform-shmem-management pattern).
- `notes/sm90/arch/memory_model.md` — shared-memory bulk zero-init is a
  sm100-new feature.

## Open questions
- `initval` is restricted to 0 in PTX — is this a hardware limitation (only
  zero-init is possible) or a toolchain restriction?
- `URb` must be URZ — the single zero pattern. A future bulk-fill with non-zero
  value would need a different operand constraint.
