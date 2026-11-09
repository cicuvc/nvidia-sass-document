# SETLMEMBASE — Set local-memory base address (sm120)

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-08  
**Probe:** local-memory base-switch probe on RTX 5090 (GB202, sm120)  
**Open items:** 2 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: explicit RTX 5090 silicon verification

## Conclusion

`SETLMEMBASE RA` writes the executing warp's local-memory backing-aperture base
from the 64-bit pair `{RA,RA+1}`.  It is the reverse of `GETLMEMBASE` and
redirects subsequent `LDL`/`STL` backing accesses for that warp.

The sm120 encoding and scoreboard shape match the sm90 instruction; see
[`../../sm90/instr/setlmembase.md`](../../sm90/instr/setlmembase.md) for the
shared ISA description.  This note records the sm120 hardware result.

## Verified behavior

The switch experiment alternates the base `A → B → A → B` and verifies:

- `GETLMEMBASE` immediately reports the newly installed base;
- `STL` under `B` is visible through the derived global backing VA in `B`;
- the old word in `A` remains unchanged;
- `LDL` selects the `B`, then `A`, then `B` value as the base changes;
- a host read of the ordinary allocation observes the redirected store.

The result establishes that sm120 `SETLMEMBASE` changes the backing used by
subsequent local accesses.  The observed scope is warp-level; divergent-execution
scope was not exercised because the test warp executed convergently.

## References

- [Full sm120 local-memory backing study](../arch/local_memory_backing_va.md)
- [sm90/H20 companion note](../../sm90/instr/setlmembase.md)

## Open questions

- Exact state scope under divergent execution is not established.
- The real cuobjdump text form and compiler-emission paths remain unconfirmed.
