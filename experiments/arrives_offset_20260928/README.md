# ARRIVES immediate-offset investigation (2026-09-28)

Scope: RTX 5090 / sm120, CUDA 13.1 runtime and Compute Sanitizer.  The DISM
production kernel was not modified.  `build_variants.py` operates on a copied
cubin/executable from the one-slot reproducer.

## Encoding result

`ARRIVES`, `SYNCS.ARRIVE.RED.A0T1`, and `SYNCS.ARRIVE.ART0` all encode the
address immediate as an unscaled signed 24-bit byte offset in bits 63:40.
For example, changing `ARRIVES ... [UR7+0x8]` to `[UR10]` changes only:

- bits 63:40: `8 -> 0`;
- bits 69:64: address register `7 -> 10`.

The scheduling/control bits and every other instruction-data bit are equal.
Exact words for all three families are in `encoding.log`.

There is an additional cubin contract that is easy to miss:
`EIATTR_MBARRIER_INSTR_OFFSETS` repeats the address expression.  Its third
u32 stores the byte offset and byte 2 of its fourth u32 stores the address
register.  In the original cubin it describes the async arrive as
`(R255 + UR7 + 8)`.  A binary SASS patch that does not update this metadata is
not a valid equivalent experiment.  `cuobjdump -elf` confirms the patched
metadata decodes as `(R255 + UR10)` when updated.

## Reproduction rerun

Unmodified clang-built executables, tasks 7/173 and 7 persistent iterations:

| form | tasks=7 | tasks=173 | numeric |
|---|---:|---:|---|
| local allocator, `[UR7+8]` | racecheck 3072 errors | 138240 errors | pass |
| identity-shuffle, `[UR4]` | 0 hazards | 0 hazards | pass |

Logs are `race_{offset,zero}_{7,173}.log`.  Thus the previously reported split
reproduces, but these two compiler outputs still differ in address
materialization and surrounding scheduling.

## Attempted same-cubin patch and boundary

The producer-side NOP at PC 0x770 was replaced with a uniform expression meant
to materialize `UR10 = UR7 + 8`; selected address operands and the matching
EIATTR records were patched in place.  This retained ELF sections, instruction
PCs, and all other words.  The original-offset control remained numerically
correct.  The zero-offset forms hung or read stale data, so they are **not**
valid racecheck comparators.  The experiment does not establish whether the
failure is an overlooked uniform-register dependency/encoding issue or a
further loader/hardware metadata contract.  Those outputs must not be used as
evidence that `[UR+8]` and `[UR]` have different hardware address semantics.

## Supported conclusions

- `+8` is a byte offset and the SASS decoder/assembler agree on its field.
- The mbarrier EIATTR redundantly carries register plus offset; future binary
  experiments must patch it along with SASS.
- Current sanitizer correlation with the immediate-offset form is repeatable.
- No hardware misaddress, alignment defect, or sanitizer false positive has
  been proved.  A decisive next experiment should materialize the full address
  in compiler-generated code while holding the producer schedule constant, or
  first add a direct UR-value readback to validate a hand-patched base.

## Direct live-state experiment

`probe_arrives_state.py` removes the full ring pipeline from the question.  It
uses a physical barrier at shared byte address `0x408` in both variants:

- zero form: `UR6=0x408`, operations use `[UR6]`;
- immediate form: `UR6=0x400`, operations use `[UR6+0x8]`.

Thirty-two lanes issue 1--48 cold/dispersed `LDGSTS` copies per lane, then the
compiler lowering pair `SYNCS.ARRIVE.RED.A0T1` +
`ARRIVES.LDGSTSBAR.TRANSCNT`, followed by an ordinary arrival and phase wait.
`SYNCS.LD.64` samples live barrier state before and after each step.  The test
keeps the raw word and decodes the documented full 21-bit tx field; it does not
use the ambiguous 17-bit mask.

Representative raw states (16 copies/lane):

| point | raw64 | encoded tx[41:21] | logical `(-field) mod 2^21` |
|---|---:|---:|---:|
| init / after LDGSTS | `0x7fff0000001fffc0` | `0` | 0 |
| after A0T1 | `0x7fff03fffc1fffc0` | `0x1fffe0` | 32 |
| immediately after ARRIVES | `0x7fff03fffc1fffc0` | `0x1fffe0` | 32 |
| after ordinary arrival | `0x000003fffc1fffc0` | `0x1fffe0` | 32 |
| after phase completion | `0xffff0000001fffc0` | `0` | 0 |

The immediate snapshot catches pending copies rather than only seeing zero.
After completion the tx field drains and the phase flips.  Payload bytes match
exactly.  For copy counts 1, 4, 8, 16, 32, and 48, three repetitions each,
the zero and immediate forms have bit-identical states at every sample and
identical correct payloads (`state_<copies>_<rep>.log`).

This directly rules out different hardware barrier-address or completion
semantics for the two address encodings in the tested bounded context.  In
combination with the stable racecheck split in the full reproducer, the
remaining evidence strongly points to sanitizer tracking/code-shape behavior,
not an actual `[UR+8]` hardware synchronization failure.  It remains scoped to
this address, copy range, and sm120 test rather than proving every possible
input or pipeline safe.
