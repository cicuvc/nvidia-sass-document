# GB202 scalar and tensor compute-pipeline model

Silicon: RTX 5090 and RTX PRO 6000 Server Edition (GB202, sm_120),
2026-09-14--15.  Companion diagram:
[`gb202_compute_pipelines.svg`](gb202_compute_pipelines.svg).  The underlying
measurements and raw tables are in
[`subcore_compute_conflict.md`](subcore_compute_conflict.md) and
[`rf_writeback_conflict.md`](rf_writeback_conflict.md).

This is a behavioral microarchitecture reconstructed from throughput,
predication, reuse, same/different-subcore contention, forwarding, NCU pipe
activity, and RF writeback collisions.  A named box means that the tests
require a separately observable service or credit domain.  It does not always
mean that a physically distinct FIFO or arithmetic array has been proved.

## Summary hierarchy

The best-fit path for a fixed-latency scalar or tensor instruction is:

```text
warp scheduler
    |
    +-- predicate-insensitive family admission / target-pipe credit
    |       (the effective predicate can suppress later operand/result work)
    |
    +-- subcore-local even/odd RF collection
    |       (one independently addressed warp operand per bank per clock)
    |
    +-- family steering
    |       +-- ALU Heavy admission -------> IADD3/PRMT/logic body
    |       +-- Shared FMA Heavy physical pipe
    |       |       +-- ALU Lite ----------> move/select/minmax/light body
    |       |       `-- FMA Heavy ---------> IMAD/integer-dot body
    |       +-- FMA Lite admission --------> FP32 FADD/FFMA body
    |       +-- packed-FP admission -------> packed FP16 body
    |       `-- tensor admission ----------> HMMA/QMMA and IMMA subpipes
    |
    +-- per-pipe bypass / result staging
    |       (same-pipe and cross-pipe forwarding precede RF commit)
    |
    `-- parity-steered final commit
            +-- even RF-bank 1W service
            `-- odd  RF-bank 1W service
```

The principal distinction is between three levels:

1. **Admission/credit pressure.** This can remain when the instruction is
   predicated off, so it is earlier than architectural execution.
2. **Operand and execution pressure.** Active instructions read RF and occupy
   their execution bodies.  This is where many cross-family slowdowns arise.
3. **Completion/commit pressure.** Bypass can satisfy a dependent consumer
   before the result obtains the parity bank's architectural write service.

This separation is why a single latency-table pipe name cannot be interpreted
as one physical datapath.

### Integrating the scalar admission queues with the leaf-pipe hierarchy

The earlier “INT/FP admission queue” wording should not be read as one common
FIFO.  Predicated-off instructions prove that a target-family reservation is
made before architectural RF reads, but the cross-family matrix rejects one
shared scalar server.  The best-fit refinement is:

```text
                         subcore warp scheduler
                                  |
                    scalar dispatch / family decode
                                  |
          +-----------------------+-----------------------+
          |                       |                       |
   ALU-Heavy credit        Shared-FMA-Heavy        FMA-Lite credit
    (~1 op / 2 cyc)          macro steering          (>=1 op / cyc)
                                /       \
                    ALU-Lite credit   FMA-Heavy credit
                    (>=1 op / cyc      (LO ~1 op / 2 cyc;
                     when RF permits)   HI/WIDE ~1 op / 4 cyc)
          |                         |                       |
          +-------------> early E/O RF collection <--------+
                                  |
                     corresponding execution leaf
                                  |
                       bypass / result staging
```

"Queue" here is behavioral shorthand.  Each box may be a shallow decoded-op
buffer plus a downstream credit, rather than a separately addressable FIFO.
The short-burst probe below measures one SASS-visible active credit and no
extra waiting operation on the slow scalar paths, but not a literal number of
physical storage cells.  A warp reports
`math_pipe_throttle` when the credit needed by its target path cannot be
obtained; this does not imply that all boxes share storage.

The leaf counter supplies the routing label, while the admission experiment
supplies the service/credit boundary:

| Instruction | Admission/credit acquired | Execution leaf |
|---|---|---|
| `IADD3/LOP3/PRMT/SHF/...` | ALU-Heavy | ALU Heavy |
| `MOV/IADD/SEL/FMNMX/ISETP/...` | ALU-Lite side of Shared FMA Heavy | ALU Lite |
| `IMAD/IMUL/IDP` | FMA-Heavy side of Shared FMA Heavy | FMA Heavy |
| `FADD/FFMA/FMUL` | FMA-Lite | FMA Lite |
| `HADD2/HFMA2/HMUL2` | packed-FP steering plus coupled FMA-Heavy/FMA-Lite credits | both FMA leaves |

ALU Lite and FMA Heavy therefore sit under one physical macro-envelope but
must not be represented as one non-overlappable queue.  The reusable-source
`IADD+IMAD`/`MOV+IMAD` streams fill the same FMA-Heavy issue gaps as the
physically separate `FFMA+IMAD` control.  The conservative topology has a
common macro steering point followed by per-leaf credits; a pair-private FIFO
or shared arithmetic stage remains unproved.

Packed FP is the important cross-link.  Its predicated-off form conflicts
with both IMAD and FP32 FMA traffic and increments both FMA leaves.  It is
best modeled as one decoded operation that atomically reserves a coupled
mode/credit across the two sides, not as an instruction dynamically routed
to either leaf.

Finally, admission queues are distinct from the post-execution bypass/result
queues.  Admission pressure occurs before RF collection and is visible under
all-off predication; result queues occur after the arithmetic body, enable
forwarding before architectural commit, and ultimately feed the parity-bank
1W arbiters.

Consumer-specific fixed-latency measurements are recorded separately in
[`alulite_latency.md`](alulite_latency.md) and
[`aluheavy_latency.md`](aluheavy_latency.md), with the FMA-Lite matrix in
[`fmalite_latency.md`](fmalite_latency.md).  They show that the bypass box
cannot be represented by one latency per producer pipe: ALU-Heavy results are
uniformly ready to the same leaf at gap 2, while ALU-Lite/FMA-Lite crossings
are producer-class dependent (gap 2 or safe gap 4), and predicate guard/CBU
distribution is a distinct much later event.  Scalar `FHADD/FHFMA` further
expose two payloads at once: ALU Heavy can see the raw FP16/BF16 value while
the other scalar leaves already see the formatted FP32 result.

## Register collection

Every subcore has an even and an odd GPR bank.  At the SASS-visible collector
interface each bank accepts one independently addressed, warp-wide 32-bit
operand row per clock.  The two parity banks operate in parallel:

| Sources needed by one instruction | Minimum collection time |
|---|---:|
| 1 even + 1 odd | about 1 clock |
| 2 even + 1 odd | about 2 clocks |
| 3 even | about 3 clocks |

Reuse masks remove the corresponding RF transactions.  For example, a normal
2E+1O FFMA falls from 2 clocks/instruction to about 1.09 after enough sources
are reused.  IADD3, HFMA2, HADD2, and IMAD remain near 2 clocks/instruction
after their RF demand is reduced, proving that those families also have an
independent admission/backend floor.

Enabling only lane 0, one half warp, even lanes, or odd lanes does not reduce
the per-bank collection cost.  Complementary masks from two same-subcore
warps also do not combine.  Thus the architectural service is not two
independently addressed half-warp reads.  One physical 128-byte port and two
64-byte slices sharing one row decoder remain observationally equivalent.
Calling the circuit `2R` may describe those slices, but the performance model
must use **one warp-row service per bank per clock**.

Each bank also exposes one final architectural write opportunity per service
slot.  The read and write services can overlap.  The proven restriction is
the one-write commit arbitration, not a blanket inability to read and write a
bank simultaneously.

IndexedRF instructions add an early address-selection path without changing
these row services.  `R[URx]` snapshots a committed uniform-register value and
uses it as the GPR/group number before ordinary operand collection or
destination allocation.  Dense indexed HMMA and both directions of indexed
MOV have exactly the same throughput and NCU pipe/throttle signature as their
fixed-register controls.  The selector does not count on `uniform_pipe`, does
not enter MIO, and does not receive the UDP-result forwarding available when
URx is consumed as ordinary ALU data.  Details are in
[`indexed_rf_topology.md`](indexed_rf_topology.md).

Ordinary UR operands expose a separate, equally local constraint.  UR0--UR79
are organized as twenty 128-bit rows, and one subcore can address one row per
clock.  A three-row UDP sensor is delayed by same-subcore UR-source `IADD3`,
`FFMA`, MIO conversions, `LDS [R+UR]`, and descriptor `LDG`; matched GPR-source
controls do not delay it, and every different-subcore control is independent.
False-predicated UR forms retain the collision.  The supported topology is
therefore a common subcore-local URF row service feeding both the early
INT/FP collector and the MIO-side late LSU/XU collector, with reservation
before predicate squash:

```text
URF: one 128-bit row-address service / clock / subcore
       +--> fixed UDP collector
       +--> early INT/FP collector
       `--> MIO queue --> late LSU/XU collector
```

The full row map, throughput table, one-row capacity control, and reproduction
script are in [`udp_urf_topology.md`](udp_urf_topology.md).

## Scalar family admission and execution pipes

| Instruction family | Counter/ISA grouping | Measured local limit | Best-fit resource |
|---|---|---:|---|
| fixed scalar UDP operations (UMOV, UIADD3/UIMAD/ULOP3/USHF, UFADD/UFFMA/UFMUL, etc.) | `udp_pipe`, coupled math | 1 inst/clock/subcore after URF collection | one fully pipelined uniform lane; URF supplies one 128-bit row/clock |
| IADD3, LOP3, SHF, packed conversion, shift/permute and predicate-file operations | `aluheavy` | about 0.5 inst/clock | ALU Heavy admission plus a distinct INT body |
| MOV/SEL, legacy IADD, minmax/compare and VIADD operations | `fmaheavy_subpipe_alulite` | at least about 1 inst/clock when RF reads are reused | ALU Lite subpipe of physical Shared FMA Heavy |
| IMAD, IMUL, integer dot product | `fmaheavy_subpipe_fmaheavy` | IMAD.LO/IDP about 0.5 inst/clock; IMAD.HI/WIDE about 0.25 | FMA Heavy integer multiply/dot body |
| FADD, FFMA | `fmalite` | at least 1 inst/clock when RF reads permit | lighter FP32 FMA/add body |
| HFMA2, HADD2, HMUL2 | each instruction counts on FMA Heavy + FMA Lite + FP16 type | about 0.5 inst/clock | coupled packed-FP execution across both FMA leaves |
| HMNMX2, HSET2, HSETP2 | static `fp16_pipe`, measured `aluheavy` | not yet isolated | packed compare/minmax executes on ALU Heavy |
| 32-bit F2F, F2I, I2F forms | `mio_pipe`, `VQ_MUFU`; exact MUFU queue-conflict and short-burst signature | about 0.125 inst/clock | local XU admission queue and XU-class conversion service |
| 64-bit-source/destination F2F, F2I, I2F forms (FP64 or int64) | also static `mio_pipe`, `VQ_MUFU`, but no dynamic conflict with MUFU/all-32-bit conversion | about 1 inst/18 clocks per **SM** (19 for a 64-bit destination) | distinct SM-shared slow conversion admission/service resource |
| F2FP, F2IP, I2FP | `int_pipe`, measured `aluheavy` | about 0.5 inst/clock before RF-source costs | fixed ALU-Heavy packed conversion path; no XU credit |
| DADD, DFMA | FP64 | about 1 inst/16 clocks per **SM** | one SM-wide pipe fed by all four subcores |

The UDP entry is now backed by a 46-form exhaustive representative sweep.
With all inputs placed in one URF row, every tested integer, logic, HI/WIDE
multiply/add, packed-half, conversion and uniform-predicate form follows
`T(N)=N+5` through 256 operations.  An instruction-by-instruction mixed stream
across those classes has the same slope, so there is no visible Heavy/Lite-
style internal throughput split or mode-switch bubble inside coupled scalar
UDP.  Dependency latency and cross-row collection remain separate costs.

### Official Heavy/Lite hierarchy and integer multiplication

Leaf-level NCU counters resolve the otherwise confusing logical names.  In a
256-instruction stream, after subtracting the NOP-kernel floor, IMAD.LO,
IMAD.HI, IMAD.WIDE, IDP.2A and IDP.4A each add exactly 256 instructions to
`smsp__inst_executed_pipe_fmaheavy_subpipe_fmaheavy`; none adds activity to
ALU Heavy, ALU Lite, or FMA Lite.

A minimal named-kernel scan now covers all 65 encodable scalar-math mnemonics.
It finds a stable static partition across four launches: among notable pairs,
legacy `IADD/IADD32I` use ALU Lite while `IADD3` uses ALU Heavy; `ISETP` uses
ALU Lite while `PSETP/P2R/R2P` use ALU Heavy; and `FMNMX/FSEL/FSET/FSETP` use
ALU Lite while packed conversions use ALU Heavy.  PRMT and BMSK are ALU Heavy,
not dynamically steered.  The earlier apparent split was an NCU launch-ID
pairing error in a large framework containing hundreds of unrelated ALU
instructions.  The exhaustive lists and raw-counter method are in
[`scalar_math_pipe_catalog.md`](scalar_math_pipe_catalog.md).

This matches NVIDIA's hierarchy literally: logical ALU aggregates ALU Heavy
and ALU Lite, but ALU Lite is physically placed in Shared FMA Heavy beside
the FMA Heavy subpipe.  Logical FMA aggregates FMA Heavy and FMA Lite.  A
single flat list of four independent pipes is therefore misleading.

#### What is shared by FMA Heavy and ALU Lite?

The word *Shared* does not mean that the two leaves are one mutually-exclusive
arithmetic server.  In one warp, an alternating reusable-source `IADD` (ALU
Lite) + `IMAD.LO` (FMA Heavy) stream costs 2.167 clocks per pair.  Replacing
`IADD` by `MOV` gives the same 2.167 clocks/pair, and replacing it by `FFMA`
on the physically separate FMA Lite leaf also gives 2.167 clocks/pair.  Thus
an ALU-Lite operation can occupy the issue gap between successive FMA-Heavy
operations; it does not wait for the whole multiply/reduction body to become
idle.

The most conservative physical interpretation is a common **macro-pipe
envelope** with two independently pipelined leaves:

```
subcore scheduler / scalar RF collector
                  |
          Shared FMA Heavy envelope
             /                 \
    ALU Lite leaf          FMA Heavy leaf
  add/select/compare      mul/dot/reduction
             \                 /
        scalar-result staging / RF-write arbitration
```

The likely shared pieces are steering/admission into the physical block,
operand-delivery wiring or collector interface, clock/control, and the result
staging/writeback merge.  The multiplier and its reduction/HI/WIDE machinery
are clearly FMA-Heavy-only.  The experiment cannot prove a pair-private FIFO,
read port, adder, or write port: the one-warp issue limit, RF collectors, and
scalar writeback arbitration are also shared by otherwise separate scalar
pipes.  Likewise, same-subcore two-warp contention is strongly asymmetric
when a fast contender starves an IMAD victim, but the same effect occurs for
FMA Lite versus FMA Heavy and is therefore scheduler fairness, not evidence
of a common arithmetic body.

So the useful working model is: **shared entrance/exit and physical placement,
separate execution bodies with overlappable pipeline occupancy**.  Whether
ALU Lite also time-multiplexes a particular early adder or result formatter
inside the FMA-Heavy macro remains unresolved.

The names are **not a per-instruction multiplier-width selector**.  Narrow
IDP.4A/IDP.2A, ordinary low-half IMAD, high-half IMAD, and wide-result IMAD
all take the same FMA Heavy leaf.  However, the internal implementation of
that leaf can still explain the name: it is the capability-rich pipe that
must contain the full integer partial-product/reduction machinery, whereas
FMA Lite need only implement the FP32/FP16 arithmetic subset.  ALU Lite can
reuse steering, operand, and adder/logic resources around that physical pipe
without itself using its multiplier.

The result mode changes occupancy *within* FMA Heavy.  With a 1024-operation
stream, IMAD.LO measures 2.077 clocks/instruction and IMAD.HI/WIDE measure
4.074.  Marking all three source slots reusable changes these to 2.075 and
4.073 respectively.  Thus the twofold HI/WIDE cost is not late RF collection;
the best-fit model is two internal service beats (partial-product/result
selection or return bandwidth) in the same leaf pipe.  This experiment does
not distinguish which internal stage is doubled.

### Simple INT

IADD3, LOP3, and SHF mutually expose the same approximately two-clock
admission domain.  Even a one-source IADD3 retains this floor, so it is not an
RF-bandwidth artifact.  Simple INT has no predicate-insensitive cross-conflict
with FP32, packed FP, or IMAD.  Active cross-family instructions can still
slow it by consuming the shared RF collector.

### FP32 lighter pipe

FADD and FFMA can accept approximately one instruction per clock when source
reuse leaves at most one operand in each parity bank.  A usual 2E+1O FFMA
appears to have 0.5-inst/clock throughput only because it needs two even-bank
row services.  Two same-subcore low-RF FFMA streams interleave near one
aggregate instruction/clock, whereas two low-RF IADD3 streams remain limited
near 0.5.

Thus FFMA and IADD3 may have the same throughput in ordinary code while being
limited at different levels: FFMA by RF collection and IADD3 by its family
admission/backend.

### IMAD and packed FP

IMAD has its own approximately 0.5-inst/clock admission behavior and does not
show a predicate-insensitive conflict with FFMA.  Packed FP16 also has a
0.5-inst/clock floor, but it has an unusual early interaction with every
tested fmalighter-shaped family:

- predicated-off HFMA2 conflicts strongly with FADD/FFMA;
- predicated-off HFMA2 conflicts strongly with IMAD;
- predicated-off IMAD does not similarly conflict with FFMA;
- simple INT does not participate in this early cross-family interaction.

The relation is not consistent with one uniform fmalighter server.  The most
conservative model is a **packed-FP steering or mode-credit constraint** that
can block FP32 and IMAD admission, while the three families retain distinct
execution bodies.  The tests do not prove that FP16 and FP32 share arithmetic
lanes.

The later exhaustive leaf-counter scan sharpens the packed body itself:
ordinary HADD2/HFMA2/HMUL2 (and HFMA2.MMA on sm_120) count once on both FMA
Heavy and FMA Lite per instruction.  HADD2.F32 widening counts only on FMA
Heavy, while HMNMX2/HSET2/HSETP2 execute on ALU Heavy.  See
[`scalar_math_pipe_catalog.md`](scalar_math_pipe_catalog.md).

## Tensor admission and subpipes

GB202 exposes a subcore-local tensor admission/credit level followed by at
least two distinguishable backend subpipes:

```text
shared tensor admission / credits
             |
       +-----+------+            both may be active together
       |            |
 HMMA/QMMA       IMMA
  subpipe        subpipe
  5090: 32       5090: 16
  PRO 6000: 16   PRO 6000: 16
  cycles/inst    cycles/inst
```

The quoted RTX 5090 occupancies are for the tested `HMMA.16816.F32.BF16`,
`QMMA.16832.F32.E4M3.E4M3`, and `IMMA.16816.U8.U8` forms.  RTX PRO 6000 is an
important SKU control: naked RZ-source slopes are exactly 16 clocks for all
three forms, whereas RTX 5090 is exactly 32 for HMMA/QMMA and 16 for IMMA.
The 5090 therefore has a twofold FP32-accumulating tensor admission/backend
limit; these numbers are not universal latencies for every shape or SKU.

The measured relationships are:

- HMMA and QMMA increment `tensor_subpipe_hmma` and have identical occupancy
  and same-subcore contention signatures.  A mixed HMMA+QMMA stream confirms
  that they share the reported subpipe resource.
- IMMA increments a distinct `tensor_subpipe_imma` counter and, on RTX 5090,
  takes half the active duration of these HMMA/QMMA forms.
- HMMA/QMMA and IMMA partially overlap on one subcore.  For the mixed pair,
  the individual subpipe counts add to 24576 cycles while overall tensor
  activity is about 19528 cycles.  They therefore cannot be aliases for one
  completely non-overlappable arithmetic body.
- Despite that backend overlap, a same-subcore mixed pair adds about 9300
  math-throttle events relative to different-subcore placement.  This is the
  evidence for a common tensor admission/dispatch queue or shared credit pool
  ahead of the two subpipes.
- A predicated-off tensor contender retains its full subpipe-active count and
  nearly all contention.  Tensor admission and pipe reservation occur before
  effective predication suppresses the result.

The short-burst experiment below resolves the SASS-visible tensor depth as one
common steering credit and one active credit per tested leaf, with no extra
waiting operation.  Calling these queues is still only a behavioral model;
they may instead be busy/credit scoreboards around the backend subpipes.

HMMA/QMMA/IMMA results are not protected by the six general scoreboards in
the tested synchronous forms.  Consumers require conservative spacing
(currently at least 16 NOPs in the assembler tests).  The diagram therefore
shows tensor-specific completion staging rather than putting these results in
the ordinary fixed-pipe bypass queue.

Tensor operands nevertheless share the subcore-local scalar RF-delivery
frontend.  `probe_tensor_rf_paths.py collect` times a two-even-row `FADD RZ`
stream against otherwise identical active tensor instructions with either
normal GPR sources or all-RZ sources.  Result writes, tensor admission and
backend occupancy remain present in both cases.  The same-subcore GPR-minus-RZ
cost, after the different-subcore control, is about 1.97 clocks/HMMA, 1.85
clocks/QMMA and 1.77 clocks/IMMA; every different-subcore delta is zero.  For
HMMA, isolating A, B and C gives approximately 0.71, 0.51 and 0.96 clocks per
instruction respectively.  Thus all three explicit operand groups use a
resource shared with scalar RF collection.  The non-additive RTX 5090 costs
alone undercount the physical row demand because its tensor backend leaves
large collection holes; the full-rate control below resolves this ambiguity.

The unrestricted RTX PRO 6000 control resolves why those RTX 5090 costs were
so small.  With the same probe, HMMA and QMMA full-ABC pressure rises from
about 1.9 to 4.43 clocks/instruction, while IMMA remains exactly 1.77.  HMMA's
A-only/B-only/C-only components become 1.77/1.32/2.21, close to the logical
2/1/2 per-bank row counts of the three groups.  Thus the 5090's 32-clock
HMMA/QMMA floor leaves collector holes that hide roughly half the source
traffic; it is not evidence for a half-width tensor operand interface.  The
best model is ordinary shared parity-bank row service feeding a tensor group
packer, with overlap and scheduling phase accounting for the remaining
non-additivity.

These are deliberately reuse-disabled cold-read costs.  Dense sm_120 HMMA,
QMMA and IMMA expose an `Rb.reuse` bit but no reuse bit for Ra or Rc; the
corresponding sm_90 HMMA class exposes both `Ra.reuse` and `Rb.reuse`.
`test_hmma_reuse.py` verifies the sm_120 bit functionally with two consecutive
HMMAs: when the first destination overwrites its own Rb registers, the next
HMMA reads the pre-write cached Rb only when reuse is set.  Interleaving the
HMMA warp with the scalar victim removes the timing benefit, consistent with
the reuse slot being displaced before the next HMMA.  A tightly consecutive
tensor sequence can therefore reduce Rb RF traffic, but cannot reuse the
explicit C accumulator through this control bit.

The Ampere-style "hold Ra, rotate Rb/C/D" schedule has no corresponding
measurable optimization on sm_120.  The sm_80 dense HMMA encoding has explicit
Ra and Rb reuse flags, whereas sm_120 retains only Rb.  A back-to-back
`Rd==Ra` discriminator also rejects default implicit Ra reuse.  RTX 5090 reads
the complete newly written Ra immediately because its 32-clock admission
floor already covers the producer latency.  Full-rate RTX PRO 6000 instead
reads one stable mixed old/new fragment at gaps 0--5 and the complete new Ra
from gap 6 onward; it never matches the complete old-Ra reference that a reuse
entry supplies.  This is a non-scoreboarded streaming RAW visibility window,
not reuse.

Fixed-Ra and per-instruction rotating-Ra streams give identical
scalar-collector interference on both RTX 5090 (9266/9313 clocks) and RTX PRO
6000 (10466/10471), with identical different-subcore controls.  Finally, on
PRO 6000 a single-warp threshold sweep inserts 3--8 two-even-row FADDs between
HMMAs; every fixed/rotating pair still has exactly zero delta.  Thus neither an
explicit/default reuse entry nor a transparent Ra fragment residency produces
visible bandwidth or throughput benefit on the tested Blackwell HMMA.

The complementary fixed-Rb/rotating-Ra schedule identifies the asymmetry more
precisely.  Repeated Rb addresses with reuse disabled behave exactly like
rotating Rb, so there is no automatic address-matched cache.  Enabling the
surviving `Rb.reuse` bit demonstrably changes operand values, but a valid
fixed-Rb stream has the same timing with the bit on or off.  This remains true on PRO
6000 after replacing Ra, Rc and Rd with RZ (Rb is then the only tensor RF
source) and sweeping 0--10 scalar FADDs across several issue thresholds.
Thus Rb reuse is architecturally functional but performance-invisible in the
tested 16/32-clock HMMA admission regimes.  Its likely direct wins are less RF
switching/energy and preserving the only reusable fragment placement, rather
than increasing standalone HMMA throughput.  Dense HMMA retains both Ra and
Rb reuse in the sm_80, sm_90 and sm_100 descriptions; sm_120 removes Ra but
keeps Rb, making Rb the portable placement for a repeatedly consumed operand.

Aliasing C to the destination does not expose a separate RF-read service.
With A/B set to RZ and equal 20-group rotations, 512 `Rc!=Rd` HMMAs and 512
`Rc==Rd` HMMAs produce exactly the same same-subcore scalar-read interference
(minimum/median 8884/8950 clocks) and the same different-subcore control
(8325/8355.5).  Thus an in-place synchronous HMMA still consumes the same
observable tensor operand-delivery resource for C.  This rules out a
performance-independent RMW read path that bypasses the common RF frontend.
It cannot distinguish one physical C/RMW port behind the same row decoder and
credit from a conventional grouped read; those implementations are
behaviorally equivalent here.

The same `Rc!=Rd` versus `Rc==Rd` discriminator is bit-for-bit identical on
the full-rate RTX PRO 6000 as well (4664/4667 clocks in both cases for the
2048-instruction scalar victim).  The negative RMW result is therefore not an
artifact of RTX 5090 tensor throttling.

The result side also reaches the ordinary final RF service.  In
`probe_tensor_rf_paths.py retire`, changing only the four-register tensor
destination from RZ to GPRs delays a simultaneously completing hot LDG by one
clock at discrete phase alignments.  HMMA/QMMA hit phases 2/6/10 and IMMA hits
3/7/11; even- and odd-destination LDGs behave identically because every tested
tensor result group contains two registers of each parity.  This proves shared
completion capacity at or immediately before the parity-bank commit point,
but does not prove that tensor results traverse the INT/FP fast-bypass queue.

## Forwarding and writeback

Fixed-pipe output first enters a bypass/result-staging network:

- same-pipe dependent forwarding is visible at roughly two cycles;
- INT-to-fmalighter or fmalighter-to-INT forwarding adds roughly one crossbar
  hop and is visible at about three cycles;
- the forwarding reach includes the MIO-side late collector: `MOV.64` or the
  last of two `FFMA` address producers can feed an immediately following LDG
  at gap 1, and `HADD2` feeds MUFU at gap 2, well before the approximately
  5.4--5.8-clock scoreboard-visible RF commit;
- it also reaches the early GPR collector at the uniform-domain entrance:
  `IADD3→R2UR` is fresh from gap 2 and `FADD/HADD2→R2UR` from gap 3; R2UR's
  subsequent 13--15-cycle UR result latency is a separate cross-lane stage;
- a scoreboard-visible architectural commit appears later, around 5.4--5.8
  cycles in the calibrated fixed-pipe probes.

Consequently, aligning nominal producer latencies does not necessarily create
an observable RAW delay: a consumer may receive a forwarded value while one
of the writes is still waiting in a result queue.

### Effective bandwidth of the fixed-result bypass

`probe_fixed_bypass_width.py` and `probe_fixed_bypass_throughput.py` constrain
the operand side of that network.  The sustained probe always issues the same
three producers, rotates four register sets, and compares a consumer of the
current pending set with an otherwise identical consumer of the previous,
already committed set.  A verified gap-2 schedule keeps every local-pipe
observation fresh; producer destinations, parity, writeback pressure and
register/reuse pattern are matched.

For both INT and FMA producers/consumers the active-minus-control result is:

| pending tags consumed | parity layout | extra clocks/iteration |
|---|---|---:|
| one distinct tag | any | 0 |
| two distinct tags | E+O | 0 |
| two distinct tags | E+E or O+O | 2 |
| three distinct tags | 2+1 split | 0 |
| three distinct tags | E+E+E | 2 |
| one tag repeated in all three slots | any | 0 |

Pair tests for AB, AC and BC give the same same-parity penalty, excluding a
special operand-slot explanation.  Repeating one tag is free, so one bypass
lookup can broadcast to several operand slots; bandwidth is counted in
distinct pending-result tags, not syntactic operands.

The smallest consistent collection model is one warp-wide 32-bit result tag
per parity per approximately two-clock collection phase.  Even and odd lanes
operate together.  A three-source instruction naturally spans enough phases
for a 2+1 parity split, while a third same-parity tag needs one additional
phase.  In byte terms this is an effective lower-level transport of roughly
`128 B / 2 clocks = 64 B/clock/parity`, or about **128 B/clock/subcore** across
both parities.  This is an effective collector/bypass bandwidth, not proof of
one physical 64-byte wire.

`probe_fixed_bypass_cross_throughput.py` repeats the matched experiment for
INT-result -> FMA-consumer and FMA-result -> INT-consumer.  At their verified
gap-3 schedule, one through three distinct forwarded operands, every parity
layout, and repeated-tag broadcast all match the committed-RF control exactly
(12.039 clocks/iteration in the stable run).  Thus the cross-pipe hop adds
latency but no additional observable bandwidth restriction once scheduled at
its legal gap; its extra collection phase is sufficient for all three source
operands.

A 16-warp run supplies four active warps per subcore.  The INT loop is already
limited by INT execution throughput (about 34--35 clocks/iteration), hiding
the two-clock per-warp collection bubble.  The FMA loop remains sensitive:
same-parity pending pairs add about two clocks while mixed-parity and repeated-
tag cases are approximately unchanged.  The parity service is consequently
shared at subcore scope rather than being a private per-warp latch.  Exact
multi-warp rates retain scheduler-phase noise, so the 64-B/clock/parity figure
should be read as the clean single-warp effective service model.

For MIO consumers in particular, the table latency is a bound on value
availability at the late collector, not a deadline by which the RF array must
have been updated.  The collector either takes a pending result from fixed-pipe
bypass/staging or is interlocked until that result becomes forwardable.  This
is what allows late register sampling to remain correct while architectural
writeback arbitration is still outstanding.

The decisive writeback experiment overlaps a scoreboarded LDG completion
with a one-write-per-issue FFMA stream.  Only a same-subcore FFMA stream
targeting the same destination parity delays the load; opposite-parity and
different-subcore streams do not.  This proves that fixed-pipe results and
MIO2RF eventually meet at a subcore-local parity-bank 1W commit service.

XU/MUFU follows a related but distinct path:

```text
local XU admission -> late RF collection -> local XU backend
                                        -> independent XU return
                                        -> final RF-bank commit arbiter
```

MUFU does not increment `mio2rf_writeback_active`.  Its return path is
therefore separate from MIO2RF until both reach the final bank arbiter.  It
also does not use the fixed INT/FP fast-forwarding path: with no scoreboard
wait, both `MUFU -> IADD3` and `MUFU -> FADD` first observe the new value at
about 8.4 clocks, versus roughly 2--3 clocks for fixed-pipe producers.  Thus
"independent XU return" is not merely another name for the INT/FP bypass
network.

The return has an early route back to MIO operand collection, and it is not
XU-private.  With an identical producer/setup, `probe_mufu_self_forward.py`
finds first-fresh gaps of 7 into both another MUFU and STG's late store-data
collector, versus 8 into `IADD3`/`FADD`.  The LSU result excludes an XU-only
loopback: the early result is visible at least as far as the common LSU/XU
late-RF collector.

A same-subcore parity-write blockade distinguishes that visibility from an RF
read-stage offset.  Thirty-two even-bank FFMA writes delay even R40 MUFU
completion by about 4--9 clocks beyond matched odd-bank and predicated-off
controls, yet do not move the STG poison/fresh boundary.  At the deliberately
bimodal gap-5 edge, pooled fresh counts are 885/900 for same-even, 891/900 for
same-odd and 885/900 for predicated-off, despite the same-even completion
median being another 4--5 clocks later.  The result is therefore forwarded
from XU result staging to the MIO late collector before the final RF commit.

This path provides no automatic RAW safety.  STG source-release timing is 29
clocks without a prefix and 31 with either an independent or dependent MUFU;
the dependent request receives no extra completion wait and reads poison when
underscheduled.  Both another MUFU and an empty LSU request miss the result
through gaps 1--6.  The diagram should therefore show an XU-result-staging
bypass into the MIO late collector, labeled `no dependency interlock`; it
remains distinct from the dependable scoreboard completion path through RF
commit.

MIO2RF completion staging has an analogous pre-commit edge.  SHFL results
become visible to MUFU and STG at gap 12 but to IADD3 only at gap 14; LDS gives
the same two-clock separation at gaps 11 versus 13.  An even-bank FFMA storm
can add four clocks to an even SHFL's final completion (75 versus 71 clocks
for odd/off controls at the clean phase -23, gap-13 window) without changing
the dependent MUFU result in 300/300 runs.  The MIO collector therefore sees
MIO2RF completion staging before the latter wins the final RF write arbiter.

The consolidated operand-return picture is:

```text
fixed INT/FMA result staging ----+
XU result staging ---------------+--> MIO late collector
MIO2RF completion staging -------+          |
                                 |          +--> LSU/XU request packet
                                 `--> parity-banked RF commit
```

The evidence constrains behavior, not whether these are three physical mux
inputs or one tagged pending-result structure shared around the collector.

Completion alignment supplies the common endpoint.  In a single-warp sweep,
an even (odd) MUFU result is delayed by about one clock only by an even-only
(odd-only) FFMA write stream.  A cross-warp same-subcore check reproduces the
same +1-clock parity effect in a clean alignment window (`N=32`, phases
-12/-8, 100 repeats); moving the FFMA warp to another subcore removes it.  Cross-warp
runs are scheduler-bimodal outside that window, so this is localization
evidence rather than a calibrated queue-depth result.

Tensor completion has the same high-level distinction.  HMMA/QMMA/IMMA have
their own non-scoreboarded accumulator/result staging, then contend with an
LDG for the final RF completion service.  They should therefore be drawn as a
third input to the parity commit merge, not as users of the INT/FP bypass
queue.  A tiny generic merge buffer immediately before the bank arbiters
remains observationally equivalent.

A sustained mixed-write check repeats one RZ-source tensor instruction with
16 even-bank RZ-source FADD writes and compares tensor GPR versus RZ
destinations.  The extra cost is about 1.15 clocks/block for RTX 5090 HMMA,
0.83 for RTX PRO 6000 HMMA/QMMA and 0.70 for its IMMA.  This reinforces the
shared final commit point, but the non-scaling SKU difference shows that
per-pipe result staging and phase smoothing prevent interpreting the delta as
a raw count of RF write cycles.

## Queue and credit levels

### 2026-09-15 short-burst depth probe

[`probe_scalar_admission_depth.py`](../../tests/asm_construct/probe_scalar_admission_depth.py)
and
[`probe_tensor_admission_depth.py`](../../tests/asm_construct/probe_tensor_admission_depth.py)
put an unconsumed short instruction burst between two `CS2R SR_CLOCKLO`
reads.  Scalar targets write `RZ`, use `yield=0`, and reuse every ordinary
source; the principal controls are guarded by architecturally-false `P6`.
The ending clock read has no dependency on a target result.  Consequently, a
FIFO of depth Q in front of a slower backend would appear as Q one-clock
increments before the curve changes to the backend drain slope.

No such fast prefix exists for the scalar Heavy or packed paths:

| Burst | `T(0)` | `T(1)` | `T(2)` | Later increment | Effective active credits |
|---|---:|---:|---:|---:|---:|
| `@P6 IADD3` / ALU Heavy | 5 | 6 | 8 | 2 | 1 |
| `@P6 IMAD.LO` / FMA Heavy | 5 | 6 | 8 | 2 | 1 |
| `@P6 HFMA2` / coupled packed FP | 5 | 6 | 8 | 2 | 1 |
| reusable active `IADD` / ALU Lite | 5 | 6 | 7 | 1 | not fillable at 1-op/clock input |
| reusable active `FFMA` / FMA Lite | 5 | 6 | 7 | 1 | 1, with blocking control below |

Here “one active credit” includes the operation currently being serviced: it
means **zero additional waiting operations** are visible behind it.  The
first operation can be admitted one clock after the starting clock read, but
the second Heavy/packed operation cannot be accepted until the two-clock
service boundary.

Two backend-blocking controls remove the ambiguity for fast scalar leaves:

- One active packed `HFMA2` followed by a predicated-off `FFMA` measures 6
  clocks for the prefix alone and 8 with the `FFMA`, rather than 7.  Thus an
  FMA-Lite request cannot sit in a waiting entry while packed FP owns that
  leaf.
- One active `IMAD.HI` followed by a predicated-off instruction measures 6
  clocks for the prefix and 9 for ALU Lite, ALU Heavy, or FMA Lite, and 10
  for another FMA-Heavy request.  A non-math `CS2R` can nevertheless issue
  immediately after the prefix.  This exposes a common scalar-math
  entrance/collector credit, held for the four-beat HI operation, rather than
  a general scheduler blockage.  No decoded math operation is observably
  buffered in front of that busy entrance.

The ALU-Lite leaf itself cannot be made slower than the one-op/clock supply
rate using a clean instruction from the same leaf: `IADD`, `MOV`, and the
two-register `MOV64IUR` control all sustain one per clock.  Its literal
leaf-private storage depth therefore remains unidentifiable.  What is
observable to the scheduler is still bounded by the one-credit common
entrance when that entrance is busy; claiming a deeper ALU-Lite FIFO would
require a downstream blocker that does not also consume RF/writeback or the
common collector.

Tensor bursts show the same absence of a hidden waiting FIFO, at much larger
service intervals:

| Burst on RTX 5090 | `T(0)` | `T(1)` | `T(2)` | Later increment | Effective leaf credits |
|---|---:|---:|---:|---:|---:|
| `@P6 HMMA.16816.F32.BF16` | 5 | 6 | about 38 | about 32 | 1 |
| `@P6 QMMA.16832.F32.E4M3.E4M3` | 5 | 6 | about 38 | about 32 | 1 |
| `@P6 IMMA.16816.U8.U8` | 5 | 6 | 22 | exactly 16 | 1 |

HMMA/QMMA clock spans have several-clock clock-domain/DVFS jitter, but the
cumulative slope is the same 32 clocks/instruction seen by the NCU occupancy
counter.  IMMA is exact.  In both cases the second instruction immediately
falls onto the backend slope; there is no second accepted operation waiting
behind the active one.

Alternating the two tensor leaves locates the common tensor credit.  The
first two points are `5, 6, 24` for HMMA-then-IMMA and `5, 6, 22` for
IMMA-then-HMMA; they are not `5, 6, 7`.  The common steering/admission credit
is therefore also effectively one entry and is held for roughly 16--18
clocks.  Once released, HMMA and IMMA backends can overlap, consistent with
the earlier mixed-subpipe NCU result, while another HMMA must still wait for
its 32-clock leaf credit.

FP64 is the important exception: it exposes a genuinely deeper redirectable
admission window.  Predicated-off `DADD` (the static description labels it
`VQ_REDIRECTABLE`) gives:

```text
N       0  1  2  3  4   5   6   7   8   9 ...
T(N)    5  6  7  8  9  14  15  25  43  61 ...
```

Thus one warp can inject four consecutive operations at one per clock before
backpressure becomes visible; after the transient, the issue-visible clock
span grows by about 18 clocks per predicated-off operation (19 for the active
DADD control).  This is compatible with the approximately 16-cycle backend
occupancy once scheduler and clock-domain overhead are separated.
Multi-warp placement separates the two limits:

- eight warps mapped to the same subcore, each injecting one DADD, give seven
  local spans of 6 clocks and one delayed span of 11 clocks;
- two same-subcore warps can inject six total operations without a delayed
  local span, while the eighth aggregate operation is delayed;
- four different-subcore warps can each inject four operations before the
  common SM backend drain dominates.

The SASS-visible model is therefore **7 usable FP64 redirect/admission
credits per subcore**, with a **4-credit consecutive-burst limit per warp**,
feeding the one-per-SM FP64 server.  A physical eight-entry queue with one
head/reserved slot is plausible, but the experiment only proves seven usable
credits; it must not silently round the observed value up to eight.

These are **SASS-visible credit depths**, not proof of the number of SRAM or
flop entries.  A one-bit busy token, a non-pipelined collector latch, and a
one-entry FIFO with its head in service are indistinguishable.  The strong
result is that there is no extra decoded-op backlog between the scheduler and
the tested non-FP64 scalar/tensor services; FP64's redirectable path is the
measured exception with a multi-entry admission window.

The compute-side structures should not all be called one queue:

| Level | Scope | What is established |
|---|---|---|
| common scalar-math entrance/collector credit | per subcore | 1 active operation; no extra waiting operation visible |
| simple-INT admission | per subcore | 1 active credit, approximately 0.5-inst/clock service |
| IMAD admission | per subcore | 1 active credit; LO approximately 0.5-inst/clock, HI/WIDE approximately 0.25 |
| packed-FP admission | per subcore | 1 coupled active credit, approximately 0.5-inst/clock plus packed-FP/fmalighter steering interaction |
| FP32 FMA-Lite admission | per subcore | 1 active leaf credit under packed-FP blockage; otherwise accepts 1 inst/clock |
| ALU-Lite leaf admission | per subcore | literal private depth unidentifiable at its 1-inst/clock service rate; common entrance is one credit |
| tensor common admission/credits | per subcore | 1 visible steering credit, held about 16--18 clocks in tested forms |
| tensor HMMA/QMMA leaf credit | per subcore | 1 active operation, 32 clocks on RTX 5090 |
| tensor IMMA leaf credit | per subcore | 1 active operation, 16 clocks on RTX 5090 |
| FP64 redirect/admission | per subcore -> one shared-SM backend | 7 usable aggregate credits; at most 4 consecutive fast admissions from one warp; drain about 18--19 clocks/op |
| XU admission queue | per subcore, MIO side | about 2 effective credits; feeds late collector and local XU |
| bypass/result queues | per execution pipe or family | required by forwarding/writeback observations; exact depths unresolved |
| even/odd commit service | per subcore and parity | one architectural write opportunity per bank service slot |
| FP64 service | one per SM | backend occupancy about 1 instruction/16 clocks; issue-visible DADD burst cadence about 18--19, shared by four subcores |

The LSU queue, CBU queue, ADU, and downstream LSU request credits belong to
the wider MIO topology and are shown in
[`gb202_sm_topology.svg`](gb202_sm_topology.svg); they are not scalar-math
queues.

The fixed-latency result paths are now measured separately from these service
rates.  In particular, FMA-Heavy LO results normally reach consumers at t+2,
whereas WIDE low halves reach the Lite/FMA leaves at t+1 and WIDE high halves
at t+2.  An underscheduled ALU-Heavy consumer can observe the producer's
original `Ra` instead of either the stale destination or arithmetic result;
the final ALU-Heavy crossing is t+3 with fine packing and t+4 as a safe coarse
boundary.  See [`fmaheavy_latency.md`](fmaheavy_latency.md) for the complete
GPR and predicate matrix.

Coupled packed-FP register forms (`HADD2/HMUL2/HFMA2`, including
`HFMA2.MMA`) broadcast their final result to all four scalar leaves at t+2,
despite occupying both FMA leaves for service.  The `_32I` multiply/FMA forms
and the widening `HADD2.F32` mode retain a t+4-safe ALU-Heavy crossing; see
[`fp16_latency.md`](fp16_latency.md).

FP64/CLMAD is not part of that fixed RAW table.  Fresh-context unsafe probes
show favorable DADD/DMUL visibility near nominal gap 16 and DFMA/CLMAD near
20 with dense issue, but sparse/coarse layouts delay completion to roughly
48--56 and CLMAD can be non-monotonic.  This redirectable SM-shared path must
therefore complete through an event plus scoreboard release, as detailed in
[`fp64_redirect_latency.md`](fp64_redirect_latency.md).

## Throttle and contention relationships

NCU defines `math_pipe_throttle` as warp cycles waiting for an execution pipe
to become available.  The counter exposes backpressure; it does not by itself
prove an intentional high-watermark policy or one shared global math FIFO.

The GB202 saturation tests give:

| Source family | Active pipe signature | `math_pipe_throttle` |
|---|---|---|
| IADD3/simple INT | `aluheavy` | yes |
| FADD/FFMA | `fmalite` | no above idle residue in the tested stream |
| HFMA2/HADD2 | `fmalite` + `fmaheavy` | yes |
| HMMA/QMMA | tensor + HMMA subpipe | strong |
| IMMA | tensor + IMMA subpipe | strong |
| MUFU | XU/MIO, not scalar math | no; produces `mio_throttle` instead |

The best current interpretation is:

```text
math_pipe_throttle = OR/summary of unavailable per-target pipe credits
                      {ALUHEAVY, FMAHEAVY, tensor admission/subpipes, ...}
```

It is not evidence that INT, FP16, and tensor instructions occupy one FIFO.
Their same-subcore interactions and different-subcore independence locate
the relevant credit domains inside each subcore.

Predication separates admission from later work:

- predicated-off IADD3/HFMA2/HADD2 retain substantial pipe activity and math
  throttle;
- predicated-off HMMA/QMMA/IMMA retain essentially complete tensor occupancy
  and most tensor throttle;
- all-off scalar instructions suppress RF reads, so operand-collector cost
  disappears even when an earlier family credit remains reserved;
- predicated-off MUFU can still consume XU/MIO admission and produce MIO-side
  pressure.

The other throttle names describe different queue boundaries:

- `mio_throttle`: no free entry/credit in the relevant MIO instruction path;
  this is the important signal for XU/MUFU and several decoupled operations.
- `lg_throttle`: inability to obtain a free local LSU instruction-queue
  entry.  It is not a generic L1TEX or math throttle.
- `math_pipe_throttle`: fixed/tensor execution-pipe credit pressure described
  above.

## Confidence boundaries

High-confidence conclusions are the subcore-local E/O collection behavior,
separate INT and FP32 execution capacity, the independent 0.5-inst/clock
family floors, two tensor subpipe counters, partial HMMA/IMMA overlap,
subcore-local tensor contention, forwarding before commit, and the final
parity-bank 1W arbitration.

The following remain hypotheses: literal FIFO depths for fixed math and
tensor admission, whether the packed-FP steering constraint is a mux, mode
bit, or shared packet queue, the exact number of physical RF read slices, and
the tensor-to-scalar completion merge topology.
