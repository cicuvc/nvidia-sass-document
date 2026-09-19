# UTCLDSWS

`UTCLDSWS URd` is a scoreboarded 1-CTA load from `$VQ_SW_STATE` into one
uniform register.  The 2-CTA form writes an aligned pair.  The `.ONE`
alternate has exactly the same encoding as the plain spelling, so it cannot
select a different hardware behavior.

## B200 allocator-state probe

`tests/asm_construct/utcldsws_allocator_state_sm100.sass` compares the value
against the independently understood V1 allocator bookkeeping in reserved
shared memory.  It samples before a 32-column allocation, after allocation,
and after deallocation.  A Modal B200 run produced:

| point | `UTCLDSWS` | V1 packed allocator mask | phase |
|---|---:|---:|---:|
| before alloc | `0x00000000` | `0x00000000` | `0` |
| after alloc (`taddr=0`) | `0x00000000` | `0x00010001` | `0` |
| after free | `0x00000000` | `0x00000000` | `0` |

The V1 packed word is `occupied[15:0] | allocation_heads[31:16]`; therefore
`0x00010001` is exactly the expected state for one live 32-column allocation
starting at column zero.  `UTCLDSWS` does **not** return that bitmap or a direct
copy of the allocator's reserved-shared bookkeeping.

Reading SWS before allocation does not disturb the lifecycle: the subsequent
allocation, deallocation, and permit relinquishment complete normally.  A
separate `UTCSTSWS 0xa5a55a5a` followed by a scoreboard-ordered `UTCLDSWS`
also reads back zero.  Thus the pair is not an unrestricted general-purpose
32-bit save/restore register in an ordinary compute kernel; values may be
masked, interpreted as commands, or the state may only become nonzero during
a transient protocol not present after `UTCATOMSWS.FIND_AND_SET` retires.

This does not prove that SWS is unrelated to allocator operation.  All three
instructions share `$VQ_SW_STATE`, and the allocator uses `UTCATOMSWS` for its
hardware reservation.  It proves only that the stable live-allocation bitmap
is not observable through this `UTCLDSWS` form at the sampled boundaries.

## Reproduction

```console
/home/cicuvc/miniconda3/envs/blkw/bin/modal run \
  tests/asm_construct/probe_utcldsws_modal.py
```

The current Modal B200 accepted the V1 entry-fragment allocator.  A control
kernel using the V2 entry fragment failed with CUDA error 719 even without
`UTCLDSWS`, so V2 was deliberately excluded from the comparison.

## Open probes

- Sample while a contending `FIND_AND_SET` is retrying, rather than only at
  instruction boundaries after a successful allocation.
- Test the aligned 2-CTA 64-bit result under a real two-CTA cluster.
- Determine which bit patterns, if any, survive `UTCSTSWS`, and whether this
  depends on entry-fragment/exit-handler state.
