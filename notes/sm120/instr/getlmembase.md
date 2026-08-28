# GETLMEMBASE — Read the warp local-memory backing base

**Opcode mnemonic:** `GETLMEMBASE` = **0x3c0** | **Pipe:** `mio_pipe`
**Status:** silicon-verified on RTX 5090 (GB202, sm_120), CUDA 13.1

`GETLMEMBASE {Rd,Rd+1}` returns the 64-bit base of the executing warp's
physical local-memory backing aperture. It does **not** return the generic
local-window base (`SR_LWINLO`) and is not by itself the backing VA of local
address zero or the current stack frame.

## Operand and scheduling

The destination is an even-aligned 64-bit GPR pair. In the assembler dialect
the pair must be explicit:

```sass
GETLMEMBASE {R18,R19};[4:7:{}:5:1]
```

The instruction is a decoupled `mio_pipe` producer; a consumer must wait for
its write scoreboard. It has no source operand or modifier other than the
normal guard predicate.

## Address meaning

For an aligned 32-bit word at local address `local_addr`, lane `l` accesses the
same backing word through `LDG`/`STG` at:

```text
backing_va = GETLMEMBASE(warp)
           + (local_addr - SR_LMEMHIOFF) * 32
           + l * 4
```

The corresponding generic-local address used by `LD`/`ST` is instead:

```text
generic_local = SR_LWINLO + local_addr
```

Thus the two bases have different roles:

| Value | Role |
|---|---|
| `SR_LWINLO` / `c[0x0][0x2f8]` | converts a local address to generic local space |
| `GETLMEMBASE` | selects the warp's device backing aperture |
| `SR_LMEMHIOFF` | local address represented by offset zero in that aperture |

In one measured launch:

```text
local_addr / c[0][0x37c] = 0x00fffdc0
SR_LWINLO                 = 0x03000000
SR_LMEMHIOFF              = 0x00fff9c0
GETLMEMBASE               = 0x00003fffe6c00000
```

Consequently lane 0's current-frame word was backed at
`GETLMEMBASE + 0x8000`, not at `GETLMEMBASE + local_addr`.

## Scope and allocation layout

The returned value is warp-uniform: every lane in a warp observes the same
base. It is not CTA-uniform or SM-uniform.

For the measured high-local span:

```text
thread_local_span = SR_LWINSZ - SR_LMEMHIOFF = 0x640
adjacent-warp GET stride = thread_local_span * 32 = 0xc800
```

The transform matched all threads in these probes:

- one CTA, 8 warps: 256/256;
- 16 CTAs × 256 threads: 4096/4096;
- 400 CTAs × 256 threads: 102400/102400 across 170 virtual SM IDs.

Resident warp slots are scheduler state, so a base should not be reconstructed
from `CTAID`. Execute `GETLMEMBASE` in every warp that needs the value.

## Relationship to SETLMEMBASE

After `SETLMEMBASE {Ra,Ra+1}`, a subsequent `GETLMEMBASE` returns exactly the
64-bit value supplied. More importantly, that value becomes the backing base
used by later `LDL`/`STL`; this was verified by switching repeatedly between
the driver-selected base and an ordinary device allocation.

See [SETLMEMBASE](setlmembase.md) for the switching experiment and
[local-memory backing VA](../arch/local_memory_backing_va.md) for the full
multi-warp/multi-CTA measurements and reproduction details.

## Boundaries of the result

- The backing aperture is device-accessible through `LDG`/`STG`, but host
  `cuMemcpyDtoH` directly from the default `GETLMEMBASE` address was rejected.
- The verified transform is for aligned U32 accesses in the high-local segment.
  U8/U16, unaligned accesses and a nonzero `SR_LMEMLOSZ` remain untested.
- The concrete values and occupancy layout above are sm120-specific. The
  [sm_90 GETLMEMBASE note](../../sm90/instr/getlmembase.md) records an H20
  reproduction of the transform, with a different SM aperture stride and a
  stricter global-alias cache/lifetime caveat.
