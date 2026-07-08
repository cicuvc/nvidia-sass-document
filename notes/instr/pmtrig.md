# PMTRIG — Performance Monitor Trigger

**Opcode mnemonic:** `PMTRIG`  
**Pipe:** `fe_pipe` (front-end pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Triggers a performance monitoring event. The 16-bit immediate encodes a bitmask
where each bit corresponds to a performance counter event ID.

`PMTRIG Pp, 0xXXXX`

The `Pp` predicate controls whether the trigger is gated — when `!Pp` is true,
the event is suppressed.

## Format

```
PMTRIG [!]Pp, <16-bit mask>
```

Default `Pp = PT` (always trigger), omitted from disassembly.

## PTX mapping

```
pmevent 0     → PMTRIG 0x1      (bit 0 set)
pmevent 4     → PMTRIG 0x10     (bit 4 set)
pmevent 15   → PMTRIG 0x8000    (bit 15 set, max PTX value)
```

The PTX `pmevent` accepts values 0..15, mapping to `1 << N` in the PMTRIG
immediate. PTX limits to 16 events; the hardware immediate field supports
full 16-bit (65536 events).

## Encoding

```
  [90]       1b  Pp_not      (!Pp: gate the trigger)
  [89:87]    3b  Pp          (predicate, default PT=7)
  [47:32]   16b  imm         (event bitmask)
  [91],[11:0] 13b  opcode    0x801
  [14:12]    3b  Pg          (guard predicate)
  [15]       1b  Pg_not
```

## Verified encodings

| Lo64 | Disassembly |
|------|-------------|
| `0x0000000200007801` | `PMTRIG 0x2` |
| `0x0000002000007801` | `PMTRIG 0x20` |
| `0x0000800000007801` | `PMTRIG 0x8000` |

## Notes

- On `fe_pipe` (front-end), not the normal execution pipes — suggests the
  trigger signal goes directly to the warp scheduler / instruction issue unit.
- No data register operands — `ISRC_B_SIZE=16` (the immediate).
- `IDEST_SIZE=0` — no output register.
- Used by profiling tools (nsys, ncu) to inject performance counter events.
