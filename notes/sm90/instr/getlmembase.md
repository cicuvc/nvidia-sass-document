# GETLMEMBASE — Get local-memory base address

**Opcode mnemonic:** `GETLMEMBASE` = `0b1111000000` = **0x3c0** | **Pipe:** `mio_pipe` | since **sm_70**

> **Status: silicon-verified on H20 (sm_90), 2026-08.** ptxas/nvcc does not
> normally emit this instruction, but a hand-assembled cubin executes it.

Read the executing warp's 64-bit **local-memory backing-aperture base**. This is
distinct from the generic local-window base in `c[0x0][0x20]` / `SR_LWINLO`.

## Semantics
`GETLMEMBASE Rd` reads the current warp-uniform backing base into a 64-bit
register pair `Rd:Rd+1` (no source; `IDEST_SIZE=64`).

## Variant overview
Single CLASS / opcode, no modifiers — guard predicate and one 64-bit register operand.

## Fields (128-bit)
| bits | field | value |
|------|-------|-------|
| [91]∥[11:0] | `opcode` | 0x3c0 |
| [14:12]/[15] | `Pg`/`Pg_not` | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | dest (64-bit pair) |
| [124:122]∥[109:105] | `opex` | scheduling |
| [121:116] | `req_bit_set` | scoreboard req mask |
| [115:113] | `src_rel_sb` | read scoreboard |
| [112:110] | `dst_wr_sb` | write scoreboard |
| [103:102] | `pm_pred` | perfmon predicate |

Register constraint: 64-bit operand must be even-aligned, `!= R254`, `<= MAX_REG-2`; `RZ` allowed.

INSTRUCTION_TYPE: `INST_TYPE_DECOUPLED_RD_WR_SCBD`, VIRTUAL_QUEUE: `$VQ_UNORDERED`.

## Latency (from sm_90_latencies.txt)
`mio_pipe` member. Produces a 64-bit GPR pair; decoupled/unordered — consumers wait on `dst_wr_sb`.

## Constructed encodings
| Lo64 | Hi64* | Reconstruction |
|------|-------|----------------|
| `0x00000000000273c0` | `0x0000000000000000` | `GETLMEMBASE R2` (R2:R3) |
| `0x00000000000473c0` | `0x0000000000000000` | `GETLMEMBASE R4` (R4:R5) |

\* Hi64 shows only opcode bit[91]; real scheduling bits are compiler-chosen. Decoder: `tools/decode_lmembase.py`.

## Open questions
- **Unconfirmed** cuobjdump text form (bare `GETLMEMBASE Rd` assumed) and whether the 64-bit pair prints with a `.64` suffix.
- Whether any current path (trap handler, driver context save/restore) still issues it.

## H20 silicon verification and sm120 comparison (2026-08)

The same probe now passes on H20 / sm_90 and RTX 5090 / sm_120. For aligned U32
local accesses on both architectures:

```text
backing_va = GETLMEMBASE(warp)
           + (local_addr - SR_LMEMHIOFF) * 32
           + lane_id * 4
```

H20 single-warp values were:

```text
c[0][0x28] / local_addr = 0x00fffdc0
c[0][0x20] / SR_LWINLO  = 0x03000000
SR_LMEMHIOFF            = 0x00fff9c0
GETLMEMBASE             = 0x00003ffffd000000
lane-0 backing VA       = 0x00003ffffd008000
```

The direct `STL` → derived-VA `LDG` alias and generic-local `LD` alias both
matched 32/32 lanes. One CTA with eight warps matched 256/256; adjacent warp
bases were `0xc800` apart, identical to sm120 for the same `0x640` per-thread
high-local span.

For H20, the virtual-SM stride was:

```text
0x320000 = 2048 thread slots * 0x640 bytes/thread
```

This differs from GB202's `0x258000 = 1536 * 0x640`, reflecting the different
per-SM thread capacity. A 400-CTA run covered all 78 virtual SM IDs. Resident
256-thread CTA bases used offsets `0`, `0x70800`, `0xe1000`, `0x151800`, i.e.
0, 9, 18 and 27 warp strides.

### Global-alias cache caveat on Hopper

After the first 312 CTAs (four resident slots × 78 SMs), backing slots were
reused. Without a `CCTL.IVALL` before the verifying `LDG`, only 80000/102400
lane checks matched: the global alias could read an old L1 line from the prior
slot occupant. Adding `CCTL.IVALL` produced 102400/102400 matches. The address
transform was unchanged; this is a cache-alias visibility requirement.

Also, trying to reuse a completed kernel's saved default `GETLMEMBASE` from a
second kernel faulted with error 700 on H20. Treat the default aperture as
launch/resident-slot state, not as a persistent cross-kernel pointer. This
differs from the observed sm120 experiment, where the second-kernel read worked.

`GETLMEMBASE` also reads back exactly the value installed by `SETLMEMBASE`.
Multi-warp and multi-CTA results confirm that each warp should obtain its own
base.

See the dedicated [sm_120 GETLMEMBASE note](../../sm120/instr/getlmembase.md)
and the [full local-memory backing study](../../sm120/arch/local_memory_backing_va.md).
