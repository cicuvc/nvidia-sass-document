# GETLMEMBASE — Get local-memory base address (sm120)

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-08  
**Probe:** `tests/asm_construct/probe_lmem_transform.py` on RTX 5090 (GB202, sm120)  
**Open items:** 2 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: explicit RTX 5090 silicon verification

## Conclusion

`GETLMEMBASE RD` reads the executing warp's 64-bit local-memory backing-aperture
base into `{RD,RD+1}`.  The base is warp-uniform, but the allocation is not CTA-
or SM-uniform: software must execute the instruction in each warp rather than
reconstructing the base from `CTAID`.

The sm120 encoding and scoreboard shape match the sm90 instruction; see
[`../../sm90/instr/getlmembase.md`](../../sm90/instr/getlmembase.md) for the
shared ISA description.  This note records the sm120 hardware result.

## sm120 address transform

For an aligned U32 local word in lane `l` of a warp:

```text
backing_va = GETLMEMBASE(warp)
           + (local_addr - SR_LMEMHIOFF) * 32
           + lane_id * 4
```

The multiplier is 32 because local words are warp-interleaved into 128-byte
backing segments: one four-byte local word owns 32 lanes × 4 bytes = `0x80`
bytes of backing data.

## Verified results

The probe performs `STL`, a local-cache writeback, then reads the derived
backing address with `LDG`:

| scope | result |
|---|---|
| one warp, 32 lanes | 32/32 matched |
| one 256-thread CTA, 8 warps | 256/256 matched |
| 16 CTAs × 256 threads | 4096/4096 matched |
| 400 CTAs × 256 threads | 102400/102400 matched |

The same derived address was readable by a second kernel after writer
completion.  Unlike the H20 result, the sm120 run did not fault when reusing a
saved default base across kernels in that experiment; this remains an
allocation/resident-slot property rather than a portable pointer.

## Layout

The per-thread high-local span is `0x640` bytes:

```text
warp_stride = 0x640 * 32 = 0xc800
SM_stride   = 0x640 * 1536 = 0x258000
```

The `0x258000` SM stride reflects GB202's 1536 thread slots per SM.  A 400-CTA
run covered all 170 virtual SM IDs.  For 256-thread CTAs, observed resident
slots started at 0, 9, 18 and 27 warp strides, leaving one warp-slot-sized gap
between CTA allocations.  The full resident-slot allocation policy remains
unresolved; execute `GETLMEMBASE` per warp for correctness.

## References

- [Full sm120 local-memory backing study](../arch/local_memory_backing_va.md)
- [sm90/H20 companion note](../../sm90/instr/getlmembase.md)

## Open questions

- The exact resident-slot allocator policy, including the one-extra-warp gap
  between adjacent 256-thread CTAs, is not fully characterized.
- U8/U16 and unaligned accesses have not been directly probed.
