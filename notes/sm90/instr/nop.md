# NOP — No Operation

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** low  
**Last verified:** unknown  
**Probe:** not recorded in this note  
**Open items:** none  
**Audit:** `tools/notes_audit.py` · basis: lives under notes/sm90/; no part named, so the default measurement site sm120 is assumed

## Conclusion

**Opcode mnemonic:** NOP  |  **Pipe:** `fe_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Does nothing. Dispatched on the FP execution pipeline (`fe_pipe`), presumably to pad instruction slots in warp scheduling without consuming integer pipe resources.

## Variants

| Variant | Opcode |
|---------|--------|
| `nop_` | `0x918` (0b100100011000) |

That's it. One variant, no operands, no modifiers, no encoding fields beyond the 13-bit opcode.

## Bit layout

```
[91:91],[11:0]       opcode     <= 0b100100011000
```

Everything else is reserved/default or scheduler control fields (opex, req, pm_pred, dst_wr_sb, etc.).

## Evidence

## Empirical notes

NOP appears as filler in compiled SASS:
- Between basic blocks for alignment
- Padding warp-synchronous regions
- Filling unused instruction slots in VLIW bundles

## Latency

`fe_pipe`, zero-cycle effective latency (no dependencies). No register operands, nothing to stall on.

