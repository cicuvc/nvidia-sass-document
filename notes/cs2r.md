# CS2R — Counter/Constant Special-register → Register

**Opcode mnemonic:** `CS2R` = `0b100000000101` = **0x805** | **Pipe:** `int_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`, `VIRTUAL_QUEUE=None` (fixed latency) | since sm_70

The **fixed-latency** counterpart of `S2R`: reads a special register into a GPR on the int
pipe (coupled, scoreboards pinned), used for the free-running counters (clock/timer) and the
`CS2R Rd, SRZ` **zeroing idiom** (materialize 0, esp. a 64-bit register pair). TODO entries
`CS2R_32`/`CS2R_64` are the two size modes of this one instruction.

## Semantics (verified)
`CS2R[.32] Rd, SRa` → `Rd = SRa`. **64-bit is the default** (reads `SRa:SRa+1` into
`Rd:Rd+1`); `.32` reads a single 32-bit special register. Unlike `S2R` (decoupled, `mio_pipe`,
variable latency for e.g. `SR_TID`), CS2R is coupled/fixed-latency — appropriate for counters
and constants that are cheap and don't need scoreboard tracking.

Common uses:
- `clock64()` → `CS2R Rd, SR_CLOCKLO` (64-bit pair CLOCKLO:CLOCKHI).
- `clock()` → `CS2R.32 Rd, SR_CLOCKLO` (32-bit).
- `%globaltimer` → `CS2R Rd, SR_GLOBALTIMERLO` (64-bit).
- **Zeroing**: `CS2R Rd, SRZ` sets a 64-bit pair to 0 in one instruction (SRZ=255); the
  compiler's idiom for clearing register pairs.

## Variant overview
Single CLASS `cs2r_` / opcode 0x805, parameterized by `sz` (QInteger 32/64).

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x805 | 13-bit |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | dest (pair when 64-bit, even-aligned) |
| [79:72] | `SRa` | SpecialRegister | source SR (pair when 64-bit; SRZ=255=zero) |
| [80] | `UPq_not`=`sz` | `QInteger` | **64=1 (default, hidden)**, 32=0 (`.32`) |
| [112:110] | `dst_wr_sb` | pinned 0x7 | fixed-latency, no write scoreboard |
| [124:122]∥[109:105] | `opex` | scheduling | |

64-bit mode requires `Rd`/`SRa` even-aligned. `IDEST/ISRC_A = 32 + (sz==64)*32`. See
`s2r_s2ur.md` for the full SpecialRegister index map (`SR_CLOCKLO`=80, `SR_CLOCKHI`=81,
`SR_GLOBALTIMERLO`=82, `SR_GLOBALTIMERHI`=83, `SRZ`=255, …).

## Cross-comparison
| | **CS2R** (0x805) | **S2R** (0x919) |
|--|------------------|-----------------|
| pipe | int_pipe (coupled, fixed) | mio_pipe (decoupled, MIO_SLOW) |
| size | 32 or **64** (pair) | 32 |
| typical SR | CLOCK/GLOBALTIMER counters, SRZ | TID/CTAID/LANEID/lanemasks |
| scoreboard | none (pinned) | write scoreboard |

Both `S2R` and `CS2R` are in `OP_S2UR_S2R` (can read a warpgroup-MMA scoreboard SR).

## Latency (from sm_90_latencies.txt)
`int_pipe` (FXU_OPS), fixed-latency `COUPLED_MATH` — fast, no scoreboard wait (contrast S2R's
decoupled MIO_SLOW path).

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000000047805` | `0x000fe20000015000` | `CS2R R4, SR_CLOCKLO` (clock64) |
| `0x0000000000047805` | `0x000fe20000015200` | `CS2R R4, SR_GLOBALTIMERLO` |
| `0x0000000000057805` | `0x000fe20000005000` | `CS2R.32 R5, SR_CLOCKLO` (clock) |

Round-trip (synthetic) also covers the `CS2R Rd, SRZ` zeroing idiom (both sizes).
Decoder: `tools/decode_cs2r.py` (reuses the SR map from `decode_s2r_s2ur.py`).
Test: `tests/cs2r_test.cu`.

### PTX→SASS mapping
- `clock64()` → `CS2R Rd, SR_CLOCKLO`; `clock()` → `CS2R.32 Rd, SR_CLOCKLO`
- `%globaltimer` → `CS2R Rd, SR_GLOBALTIMERLO`
- clearing a 64-bit register pair → `CS2R Rd, SRZ` (compiler idiom).

## Open questions
- None significant; both size modes and counter/zero uses verified.
