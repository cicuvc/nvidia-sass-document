# GB202 UDP pipeline and uniform-register-file topology

This note separates the fixed-latency scalar part of `udp_pipe` from the
decoupled operations which merely carry the same top-level pipe label.  The
measurements use hand-assembled SM120 SASS on a local RTX 5090.  Performance
counters were unavailable for this pass, so pipe identity comes from the ISA
database and the dynamic conclusions come from clock and conflict probes.

## What `udp_pipe` includes

The SM120 latency description places several very different classes under
`udp_pipe`:

- coupled uniform scalar math: UMOV, UIADD3, UIMAD, ULOP3, USHF, UFADD,
  UFFMA, UFMUL, UIMNMX, conversions, and uniform-predicate operations;
- cross-domain or decoupled producers: R2UR, S2UR/CS2UR, REDUX and LDCU;
- TMA commands and cluster/barrier control operations.

The results below describe the first class.  They must not be applied to TMA,
REDUX, LDCU, or other decoupled backends merely because their static pipe name
is also `udp_pipe`.

## Fixed scalar UDP throughput

With bracket `yield=0`, one warp sustains essentially one instruction per
clock on one subcore:

| instruction | measured throughput |
|---|---:|
| `UMOV URd,imm` / `UMOV URd,URa` | 0.975 inst/clock |
| `UMOV.64` register or immediate | 0.975 inst/clock |
| `ULOP3`, `UIADD3`, `USHF` | 0.975 inst/clock |
| `UIMAD.LO`, `UIMAD.WIDE` | 0.975 inst/clock |
| `UFADD`, `UFFMA`, `UFMUL`, `UIMNMX` | 0.975 inst/clock |

A broader 46-form sweep removes the residual ambiguity about specialized
suboperations.  It keeps all ordinary inputs in the single row UR8--UR11,
rotates independent destinations through UR40--UR71, uses `yield=0`, and
warms each generated kernel for eight launches.  For every form below, 256
independent operations take exactly 261 clocks in every recorded sample:

| Class | Representative forms with identical 1-op/clock slope |
|---|---|
| integer/address | `UIABS`, `UIADD3`, `UIADD3.X`, `UIADD3.64`, `UIMAD.LO`, `UIMAD.HI`, `UIMAD.WIDE`, `ULEA`, `UCLEA`, `UIMNMX`, `UVIADD`, `UVIMNMX` |
| logic/shift | `UBMSK`, `UBREV`, `UFLO`, `UPOPC`, `ULOP/ULOP3`, `USHF`, `USHL`, `USHR`, `USGXT`, `UPRMT` |
| floating point | `UFADD`, `UFMUL`, `UFFMA`, `UFHADD`, `UFHFMA`, `UFMNMX`, `UFSEL`, `UFSET` |
| conversion | `UI2I`, `UI2IP`, `UI2F`, `UI2FP`, `UF2F`, `UF2FP`, `UF2I`, `UF2IP`, `UFRND` |
| uniform predicate | `UISETP`, `UFSETP`, two-output `UPLOP3`, `UPSETP`, `UP2UR` |

Across body sizes 32, 64, ..., 256, representative integer, multiply-high,
packed-half, conversion and predicate streams obey `T(N) = N + 5` after
warm-up.  Therefore the measured 261 clocks contain a five-clock timing
boundary rather than a 1.0195-clock initiation interval.  The backend slope
is exactly one operation per clock.  `UIADD3.64` and the two-word-result
`UIMAD.WIDE` retain that slope, as do two-UP-output `UPLOP3` and all tested
conversion forms.

An eight-way mixed stream rotating `UIADD3`, `UIMAD.HI`, `USHF`, `UFFMA`,
`UFHFMA`, `UF2IP`, `UISETP`, and `UPLOP3` also takes 261 clocks for 256
instructions.  Switching among integer, float, conversion and predicate
functions introduces no observable mode-change bubble.  This does not prove
that every function uses the same arithmetic gates; it proves that a common
one-op/clock UDP admission path is the narrowest visible limit and that no
tested internal function has an initiation interval above one clock.

At 288 or more fully unrolled instructions the time acquires a common
front-end/fetch increment for every tested opcode (for example 288 takes 317
clocks and 512 takes 559).  Because the discontinuity is opcode-independent
and coincides with code-footprint growth, it is excluded from the UDP backend
rate.  Keeping the timed body at or below 256 instructions avoids it.

These figures use operands contained in one uniform-RF row; cross-row reads
are described below.  With `yield=1`, a lone warp reaches only about 0.494
inst/clock.  Two warps assigned to the same subcore restore 0.985 aggregate
inst/clock, and two warps on every subcore reach 3.92 inst/clock per SM.
Therefore the half-rate lone-warp result is scheduler yield behavior, not a
half-rate UDP execution pipe.

The supported physical-scope model is one fully pipelined scalar UDP lane per
subcore, with admission capacity of one instruction per clock.  None of the
tested integer-multiply or floating-point operations exposes a slower
execution initiation interval once uniform-RF collection is removed.

### Fixed GPR producers forward into the R2UR entrance

Ordinary UDP arithmetic consumes URs, so `R2UR` is the relevant GPR-to-UR
cross-domain entrance.  A poison/fresh sweep that settles the slow R2UR output
separately measures its GPR input boundary:

| producer -> `R2UR` | latency-table gap | first reliable fresh gap |
|---|---:|---:|
| `IADD3` | 6 | 2 |
| `FADD` | 6 | 3 |
| `HADD2` | 6 | 3 |

Immediately overwriting the source GPR after R2UR leaves the old captured
value in every run, proving that R2UR collects its GPR source early.  The
fresh values at gaps 2--3 therefore come from the fixed INT/FMA/FP16 bypass
network, not from a late read after RF commit.  R2UR subsequently performs its
cross-lane conformity/capture operation and exposes the UR result on the much
slower 13--15-cycle output path.  The two stages must not be conflated.

## Uniform RF is organized as 20 rows of four 32-bit words

SM120 exposes UR0--UR79.  Operand collection follows the exact mapping:

```text
row       = UR index >> 2
word/bank = UR index & 3
row width = 4 * 32 = 128 bits
```

The read-side throughput is determined by the number of **distinct rows** an
instruction needs, not by parity and not simply by the number of operands:

| ULOP3 sources | distinct rows | throughput/subcore |
|---|---:|---:|
| UR8, UR9, UR10 | 1 | about 1 inst/clock |
| UR8, UR10, UR12 | 2 | about 0.5 inst/clock |
| UR8, UR12, UR16 | 3 | about 0.333 inst/clock |
| UR72, UR73, UR74 | 1 | about 1 inst/clock |
| UR74, UR75, UR76 | 2 | about 0.5 inst/clock |

Repeated references to the identical UR are broadcast from the one row read.
`UIMAD.WIDE` provides a four-source confirmation: UR8, UR9, UR10 and UR11
are collected at one instruction per clock, whereas UR8, UR13, UR18 and UR19
occupy three rows and take approximately three clocks per instruction.

Rotating-source streams give the corresponding averages.  Three consecutive
URs sliding across row boundaries average 1.5 row reads/instruction and reach
about 0.655 inst/clock.  Three even-numbered URs occupy two rows and reach
0.497, while three indices separated by four occupy three rows and reach
about 0.341.

Thus calling the structure “four banks with four independent read ports” is
misleading.  A closer performance model is:

```text
one 128-bit row-address/read service per subcore per clock
  -> four 32-bit word lanes selected by UR[1:0]
  -> broadcast/routing to the instruction's operand slots
```

All words in one row can be returned together, but two arbitrary rows cannot
be addressed in the same clock.  This is analogous to four bank slices behind
one shared row decoder rather than four independently addressed 1R banks.

## INT, FP, and MIO consumers meet at the same URF read service

A cross-warp probe uses a three-row `ULOP3` stream as a read-port occupancy
sensor.  Alone it takes 387 clocks for 128 instructions (3.023 clocks/op).
A second warp either reads a GPR, reads one UR row, or executes the UR form
under the architecturally-false predicate P6.  Warp 4 is on the same subcore
as the sensor; warp 1 is the different-subcore control.

| Contender family | same-subcore GPR | same-subcore UR | false-predicated UR | different-subcore UR |
|---|---:|---:|---:|---:|
| `IADD3` (ALU Heavy) | 3.023 | 3.938 | 3.938 | 3.016 |
| `FFMA` (FMA Lite) | 3.031 | 3.969 | 3.969 | 3.016 |
| `F2F/F2I/I2F` (MIO/XU) | 3.023 | 3.406 | 3.406 | 3.016 |
| `LDS [RZ+UR]` (MIO/LSU) | 3.023 | 3.969 | 3.969 | 3.016 |
| descriptor `LDG` (MIO/LSU) | 3.031 | 3.57--3.71 | 3.72 | 3.016 |

The LDG result has more run-to-run phase variation than the other families,
but its localization and false-predicate control are unambiguous.  Increasing
the contender length from 1x to 8x does not further change the steady overlap:
one sensor-length contender already covers the timed region.

The experiment establishes one **subcore-local UR row-read/collector
service**, reached by all of these paths.  It is not a UDP-only operand port:

```text
fixed UDP operand collection --------------------+
INT/FP early operand collection -----------------+--> one 128-bit UR row/clock
MIO queue -> late LSU/XU operand collection ------+
```

The smaller conversion penalty is consistent with its approximately
one-per-eight-clock XU admission/service rate: it presents requests to the
late collector less frequently.  LDS presents essentially a full one-row
pressure stream.  Descriptor LDG also reserves the shared service, although
memory/LSU queue phasing makes its average pressure less deterministic.  The
test cannot distinguish an SRAM-array read from a collector reservation that
holds the same row-address resource, so “read service” deliberately includes
both implementations.

False-predicated UR forms retain the full collision while matched GPR forms
do not.  Therefore UR operand selection/reservation occurs before effective
predicate squash.  For MIO instructions this locates the late UR collector
after the family has entered MIO but before the request is discarded or sent
to its execution backend.

As a capacity check, the same matrix was repeated with the sensor's three
operands in one UR row.  Its rate is 2.039 clocks/op with or without every
same-subcore contender above.  Two yield-enabled warps alternate issue, so
the sensor and contender together request only one row per clock and exactly
fit the port.  Conflict appears only when the three-row sensor removes that
otherwise idle read-service capacity; this rules out ordinary two-warp
dispatcher contention as the cause of the slowdown.

## Write-side bounds

The current experiments establish these bounds:

- scalar `UMOV` and 64-bit `UMOV.64` both sustain one instruction per clock,
  so fixed UDP result commit accepts at least two adjacent 32-bit words per
  clock;
- `UIMAD.WIDE` has the same one-per-clock rate, independently confirming the
  64-bit result case;
- a phase-aligned stale/fresh probe makes `UIADD3` and a later `UMOV` become
  visible to non-forwarded indexedRF selectors in the same absolute clock.
  Swapping selector observation order shows that both values are already
  committed in that clock.  There is no boundary shift for same-row/different-
  word, different-row/same-word, or different-row/different-word destinations.
  The fixed UDP return side therefore has **at least two independently
  addressed 32-bit write services per clock**; one row-wide 1W port is ruled
  out;
- the stronger version aligns 64-bit `UIMAD.WIDE` and `UMOV.64` results.
  All four result words become visible in the same absolute clock, verified
  by placing each selector first in turn.  The boundary remains identical
  when both pairs occupy one row and when they occupy two different rows.
  Thus fixed UDP commit accepts at least two independently row-addressed,
  at-least-64-bit writes per clock, for at least 128 aggregate result bits;
- `LDCU.128` completes a four-word, aligned destination row at the same
  observed 11-clock scoreboard boundary as LDCU.32/.64;
- a ULOP3 stream can read one fixed row and write destinations cycling across
  unrelated rows at one instruction per clock, proving that read and write
  row addresses are not forced through one shared address slot.

An overlapping same-subcore experiment placed a scoreboarded LDCU completion
inside an active UMOV write stream.  Changing the storm between another word
of the same row and the same word position of another row did not change the
LDCU completion boundary.  Repeated one-warp LDCU/UMOV sequences likewise
showed no row-specific active-versus-predicated difference.  This rules out a
simple, immediately visible collision between the decoupled and fixed return
paths.  It does not establish whether LDCU shares either of the two fixed UDP
write services: completion buffering or a separate 128-bit LDCU ingress can
hide arbitration.

The narrowest write model is therefore **two independently row-addressed
fixed-UDP write ports, each at least 64 bits wide, plus a decoupled completion
path capable of depositing a 128-bit LDCU row**.  Together with the 128-bit
read result, a compact performance notation is `1R2W`, where `R` means one
128-bit row access and each proven `W` carries at least a 64-bit adjacent
pair.  This is a throughput-level port model, not yet proof of the SRAM macro
layout.  Where the LDCU path finally merges remains unresolved.

## Reproduction

- `tests/asm_construct/probe_udp_urf.py`: UDP throughput, subcore scaling,
  row mapping, read collection, 32/64-bit result widths.
- `tests/asm_construct/probe_udp_arithmetic.py`: 46 coupled arithmetic,
  conversion and uniform-predicate forms plus a cross-class mixed stream;
  same-row independent operands isolate the one-op/clock backend slope.
- `tests/asm_construct/probe_fixed_r2ur_forward.py`: separates fixed-pipe to
  R2UR input forwarding from R2UR's later uniform-result latency and includes
  a post-R2UR overwrite test for early versus late GPR collection.
- `tests/asm_construct/probe_urf_writeback.py`: cross-warp LDCU versus active
  UDP write storm.
- `tests/asm_construct/probe_urf_writeback_serial.py`: repeated single-warp
  completion/write collision amplification.
- `tests/asm_construct/probe_urf_writeback_boundary.py`: phase-aligned fixed
  UDP writes observed through non-forwarded indexedRF selectors.
- `tests/asm_construct/probe_urf_writeback_4w.py`: two aligned 64-bit UDP
  producers, proving four result words and two row addresses per clock.
- `tests/asm_construct/probe_urf_cross_pipe.py`: INT, FP, conversion, LDS and
  LDG uniform-source contention against one- and three-row UDP sensors, with
  same/different-subcore and false-predicate controls.
