# SETLMEMBASE — Select the warp local-memory backing base

**Opcode mnemonic:** `SETLMEMBASE` = **0x3c1** | **Pipe:** `mio_pipe`
**Status:** silicon-verified on RTX 5090 (GB202, sm_120), CUDA 13.1

`SETLMEMBASE {Ra,Ra+1}` replaces the backing-aperture base used by subsequent
`LDL`/`STL` accesses in the executing warp. It changes real memory selection;
it is not merely a value that can be read back by `GETLMEMBASE`.

## Operand and scheduling

The source is an even-aligned 64-bit GPR pair. The assembler dialect requires
an explicit pair:

```sass
SETLMEMBASE {R4,R5};[7:7:{2}:5:1]
```

The instruction is a decoupled `mio_pipe` consumer with no GPR destination.
The source pair must be ready before it executes. It has no modifier other
than the normal guard predicate.

## Verified state transition

Let `A` be the driver-selected value returned at kernel entry and `B` an
ordinary 1 MiB device allocation. The probe performed:

```text
A = GETLMEMBASE()
STL [frame], old_magic
write back local cache

SETLMEMBASE(B)
assert GETLMEMBASE() == B
STL [frame], new_magic
write back local cache

assert LDG[B + (frame-HIOFF)*32 + lane*4] == new_magic
assert LDG[A + (frame-HIOFF)*32 + lane*4] == old_magic
assert LDL[frame] == new_magic

SETLMEMBASE(A)
assert LDL[frame] == old_magic

SETLMEMBASE(B)
assert LDL[frame] == new_magic

SETLMEMBASE(A)       // restore before EXIT
```

Every check passed for all 32 lanes. For this launch,
`(frame-SR_LMEMHIOFF)*32 = 0x8000`, and the host also observed the redirected
values in allocation `B` at offsets `0x8000..0x807f` after cache writeback and
a system memory barrier.

Therefore the effective aligned-U32 transform after setting base `B` is:

```text
backing_va = B
           + (local_addr - SR_LMEMHIOFF) * 32
           + lane_id * 4
```

`SETLMEMBASE` leaves the local address, `SR_LMEMHIOFF`, and warp lane
interleave unchanged; it replaces only the first term.

## Scope and safety

The observed `GETLMEMBASE` allocation is per warp, and the successful switch
affected all lanes of the probing warp. A predicated, partial-warp SET also
updates this single warp-wide state; source-lane selection is described below.

The replacement allocation must cover every transformed offset that may be
accessed. Supplying an invalid address such as `0x1111111100000000` caused
`CUDA_ERROR_ILLEGAL_ADDRESS` (700). Restore the original base before `EXIT`;
leaving driver-managed local state redirected has not been characterized.

## Lane-varying source operand

Probe: `tests/asm_construct/probe_setlmembase_lanes.py` (RTX 5090 / sm_120).
Each lane was given a different valid address:

```text
Ra[lane] = arena + slot(lane) * 1 MiB
```

`SETLMEMBASE` does not retain 32 independent bases. It elects the operand of
the **lowest-numbered active lane** at that instruction and broadcasts it into
the warp-wide LMB state:

```text
leader = find-first-set(execution_mask)       // lowest physical lane ID
warp_lmem_base = Ra[leader]
```

Evidence:

| SET execution mask | Forward slots `slot(l)=l` | Reverse slots `slot(l)=31-l` |
|---|---:|---:|
| lanes 0–31 | selected slot 0 | selected slot 31 |
| lanes 1–31 | selected slot 1 | selected slot 30 |
| lanes 7–31 | selected slot 7 | selected slot 24 |
| lanes 16–31 | selected slot 16 | selected slot 15 |
| lane 31 only | selected slot 31 | selected slot 0 |

The reverse mapping proves selection is by physical lane ID, not by minimum
address. For every case and repeat:

- the first `GETLMEMBASE` after SET returned one uniform elected value in all
  32 lanes;
- a second GET after 0, 1, 4, 16 or 64 stall-8 NOPs returned the same value;
- the subsequent STL placed all 32 lane words in one 128-byte segment under
  only the elected arena slot;
- the LDL round-trip matched 32/32 lanes.

The probe deliberately uses valid addresses in every lane. It does not yet
establish whether invalid values in non-elected lanes are ignored before any
address validation, nor what happens when separate divergent SIMT groups
execute different SETs before reconvergence. Since the architectural state is
warp-wide, code should treat such competing SETs as order-dependent rather
than as per-group local-memory contexts.

The zero-NOP case still executes two GETs before its first STL. It therefore
shows immediate GET visibility of the elected value, but does not contradict
the separately observed settling latency for a local access placed directly
after SET.

## Correction to the earlier probe

An earlier hand-cubin test concluded that `LDL`/`STL` could not be used and
speculated that modern ptxas spills used generic `LDG`/`STG`. The working probe
established the opposite:

- hand-assembled `LDL`/`STL` execute correctly when the local address is formed
  from the launch ABI state;
- ptxas-generated sm_120 register spills contain real `LDL`/`STL` instructions;
- `EIATTR_FRAME_SIZE` and `EIATTR_MIN_STACK_SIZE` describe the spill frame.

The previous faults were caused by an incorrect local address/context
assumption, not by removal of `LDL`/`STL` support.

See [GETLMEMBASE](getlmembase.md) for the backing-VA formula and
[local-memory backing VA](../arch/local_memory_backing_va.md) for complete
evidence and reproduction instructions.

The corresponding [sm_90 SETLMEMBASE note](../../sm90/instr/setlmembase.md) now
records an independent H20 reproduction of the same A → B → A → B behavior.
