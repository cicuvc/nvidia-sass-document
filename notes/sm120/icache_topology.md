# GB202 instruction-cache capacity and sharing

Silicon: RTX 5090 (GB202, sm_120), 2026-09-15. These measurements use
assembler-generated 16-byte SASS and NCU's raw ICC/GCC counters. The main
result is:

> The SM-local instruction cache (sm__icc) is best modelled as a **64 KiB,
> 128-byte-line cache shared by all four subcores of one SM**. A simple
> sequential loop remains effectively miss-free through 62.5 KiB and begins
> to conflict at 62.75 KiB, so 64 KiB is the nominal capacity rather than a
> promise that every 64 KiB contiguous loop is simultaneously usable.

The next instruction-cache level seen through gcc__cache_* is much larger.
A warmed 1 MiB sequential loop still produces almost entirely GCC tag hits,
so this experiment establishes only a **GCC residency lower bound of at
least 1 MiB**, not its capacity or sharing scope.

## Probe construction

probe_icache_capacity.py generates one repeated loop containing exactly
N-3 NOPs followed by IADD3; ISETP; BRA. Thus the requested hot-loop size is
exactly N * 16 bytes. It warms the module once and measures many traversals
inside the next launch.

probe_icache_partition.py assigns disjoint copies of the loop to selected
warps:

- same2: warp 0 and warp 4, which are assigned to the same subcore;
- diff2: warp 0 and warp 1, assigned to different subcores;
- diff4: warps 0--3, one on each subcore.

Only the selected warps execute their code paths. Consequently, comparing
the same aggregate code footprint with same2 and diff2 separates a
per-subcore cache from an SM-wide cache.

probe_icache_lines.py is a supplementary construction. It places one
executed branch in each 128-byte-aligned block and traverses the blocks in a
fixed shuffled order. It supports the 512-line nominal-capacity result, but
its absolute miss counts include taken-branch target/fetch effects and
should not be used alone to infer associativity.

## Line size

For the 62.5 KiB sequential loop, one profiled launch executes:

    (3997 NOP + 3 loop-control instructions) * 33 iterations
        = 132000 dynamic instructions.

NCU reports 16612 sm__icc_requests cycles. The ratio is 7.95 instructions
per request; at 16 bytes per SASS instruction this identifies a **128-byte
request/cache-line granularity**. The small difference from exactly eight
is the prologue, epilogue, and loop boundary.

## Capacity boundary

The single-warp sequential sweep gives:

| Hot loop | cycles/NOP | ICC lookup miss | no-instruction stall |
|---:|---:|---:|---:|
| 62.0 KiB | 2.0126 | 9 | 1136 |
| 62.5 KiB | 2.0125 | 9 | 1172 |
| 62.75 KiB | 2.0311 | 41 | 3631 |
| 63.0 KiB | 2.0309 | 105 | 3660 |
| 63.25 KiB | 2.0613 | 169 | 7768 |
| 63.5 KiB | 2.0737 | 233 | 9380 |
| 63.75 KiB | 2.0889 | 266 | 11590 |
| 64.0 KiB | 2.0934 | 267 | 12272 |

Below the knee, the remaining nine misses are essentially fixed launch/cold
traffic. Above it, adding two 128-byte lines adds approximately two misses
per traversal until the miss pattern saturates. The 62.5--64 KiB grey zone
is consistent with a nominal 512-line cache plus alignment, set mapping,
fetch-ahead, and replacement effects. It is not evidence for an unusual
exact capacity of 64000 bytes.

The shuffled sparse-line loop also changes slope around 512 blocks:

| Lines | Footprint | cycles/executed line |
|---:|---:|---:|
| 496 | 62.0 KiB | 25.05 |
| 504 | 63.0 KiB | 25.27 |
| 512 | 64.0 KiB | 25.81 |
| 516 | 64.5 KiB | 26.94 |
| 528 | 66.0 KiB | 31.27 |

Its high baseline is the cost of one shuffled taken branch per line, not
ordinary sequential instruction throughput.

## The 64 KiB cache is shared by the SM

The decisive NCU comparison is:

| Placement | Per-path code | Aggregate code | cycles/NOP | ICC lookup miss |
|---|---:|---:|---:|---:|
| same subcore, 2 warps | 24 KiB | 48 KiB | 2.032 | 51 |
| different subcores, 2 warps | 24 KiB | 48 KiB | 2.029 | 21 |
| same subcore, 2 warps | 32 KiB | 64 KiB | 2.19 | 1085 |
| different subcores, 2 warps | 32 KiB | 64 KiB | 2.18 | 1050 |
| four subcores, 4 warps | 12 KiB | 48 KiB | 2.065 | 101 |
| four subcores, 4 warps | 16 KiB | 64 KiB | 2.37 | 4201 |

If each subcore owned a private 64 KiB ICC, diff2 would retain a 64 KiB
per-path boundary and diff4 would not thrash with only 16 KiB per path.
Instead, same-subcore and cross-subcore placements have the same aggregate
64 KiB knee. The most economical topology is therefore:

           subcore 0 fetch/issue ----+
           subcore 1 fetch/issue ----+--> shared SM ICC: 512 x 128 B (~64 KiB)
           subcore 2 fetch/issue ----+             |
           subcore 3 fetch/issue ----+             v
                                               GCC / lower I$

Four warps executing the same path retain the single-path 62.5--64 KiB
boundary, confirming that residency is by instruction address rather than
being duplicated per consuming subcore.

## Set organization and index function

probe_icache_hash.py executes heap-resident SASS placed at exact,
128-byte-aligned device virtual addresses. Each selected line contains a
JMP to the next selected line; the gaps contain no executed NOPs. This
separates address mapping from total contiguous code size.

There is a small target/trace buffer downstream of ICC. With the JMP in slot
0 of every non-control line, rings of up to 12 arbitrary 4-KiB-spaced target
lines generate only fixed launch traffic (119 ICC request cycles at 12
targets and 2048 traversals). Thirteen targets abruptly produce 38982 ICC
request cycles. The result is not merely a tiny decoded-instruction store:
putting six NOPs before every JMP still leaves the 12-target ring absorbed.
Moving the JMP to the last slot of each line changes the cutoff to nine
targets; ten targets spill into ICC. Thus the structure is best described as
a **roughly 12-entry control-flow target/trace buffer**, whose usable depth
depends on branch placement and fall-through fetch timing, rather than as a
fixed byte-capacity cache.

The critical NCU boundaries were reproduced on 2026-09-21 with driver
590.48.01 and NCU 2026.3:

| JMP placement | targets | `sm__icc_requests.sum` |
|---|---:|---:|
| slot 0 | 12 | 119 |
| slot 0 | 13 | 38982 |
| slot 7 (`body_nops=7`) | 9 | 121 |
| slot 7 (`body_nops=7`) | 10 | 26706 |

This counter-visible structure must not be conflated with an
IVALL-resistant loop buffer.  A 2026-09-21 rerun corrected a timing bug in the
old self-modification probe: its 4096-iteration tight target could finish
before the asynchronous patcher was admitted.  With 262144 iterations, all
nine trials in which the patcher completed before target exit observed the
new instruction under per-iteration `CCTL.I.IVALL`; the only zero-transition
trial acked after the target had already finished.  The stronger M11a
frozen-warp experiment independently found 30/30 new instructions after one
IVALL with zero padding.  Its no-IVALL control was stale in 29/30 trials (one
uncontrolled fresh fetch), demonstrating lack of coherence rather than
persistent replay across IVALL.

Associativity must be inferred with rings larger than this buffer. Once that
confound is removed, the conflict knees are:

| Address stride | Number of lines | Lines per direct-index set | cycles/visit |
|---:|---:|---:|---:|
| 4 KiB (32 lines) | 16 | 16 | 32.16 |
| 4 KiB (32 lines) | 17 | 17 | 42.01 |
| 4 KiB (32 lines) | 20 | 20 | 62.29 |
| 2 KiB (16 lines) | 32 | 16 in each of 2 sets | 32.29 |
| 2 KiB (16 lines) | 33 | 17 in one set | 42.31 |

The one-line transition at exactly 16 resident tags identifies **16 ways**.
Together with the 64 KiB capacity and 128-byte line this gives **32 sets**:

    32 sets * 16 ways * 128 bytes = 65536 bytes.

The direct set-index candidate is:

    line offset = VA[6:0]
    set index   = VA[11:7]
    tag key     = virtual-address identity above bit 11

The address-controlled conflict oracle filled one set with line offsets
0,32,...,480, then tested a seventeenth line. Candidates whose line-number
low five bits were zero conflicted; changing only line bit 0 removed the
extra conflict. Individual tag bits were then toggled while preserving the
low five line bits:

- line bits 5--8 are exercised by the original sixteen 4 KiB-spaced ways;
- line bits 9--24 were tested as power-of-two candidate offsets;
- equivalently, byte-address bits 12--31 were tested.

Every tested high-bit-only candidate remained congruent, while the adjacent
candidate with line bit 0 set moved out of the filled set. No XOR folding of
VA[31:12] into VA[11:7] was observed. The currently supported index formula
is therefore simply:

    set = (instruction_VA >> 7) & 0x1f

This does not prove that still higher VA bits never participate, but it
rules out the usual low-order XOR folds throughout the practically tested
range.

## Concurrent lookup ports and control-flow-sensitive conflicts

probe_icache_banks.py gives one 13--16-target ring to each of one to four
warps, with the warps placed on distinct subcores. A single 13-target stream
costs 32.198 cycles per target visit. Favorable four-stream placement at
sets 0,4,16,20 costs 32.05--32.21 cycles per stream and reaches 0.12418
aggregate visits/cycle, indistinguishable from four times the single-stream
rate. The shared ICC/fetch path can therefore maintain **four independent
subcore streams without mutual slowdown**; it is not one globally
serialized lookup port.

Other placements interfere strongly even though every ring occupies only
13 of the set's 16 ways. For two slot-0-JMP streams, fixing one at set 0
gives the following cyclic relative-set pattern:

| Relative set delta | Aggregate visits/cycle | Classification |
|---:|---:|---|
| 3--7, 11--21, 25--29 | 0.06211 | full 2-stream rate |
| +/-1, +/-8, +/-9 | 0.053--0.055 | partial interference |
| +/-2 | 0.045--0.046 | strong interference |
| +/-10 | 0.041--0.042 | strongest interference |

The pattern is translation-invariant: shifting the first ring from set 0
to set 5 or 13 preserves it exactly. It is also unchanged when the virtual
spacing between the two rings varies from 52 KiB through 2 MiB. This rules
out the tested tag bits as inputs to this conflict relation and localizes it
to the low instruction-address/fetch path.

This is **not yet an ordinary static bank-number hash**. Moving each JMP
from slot 0 to slot 7 shifts the strongest conflict centers from relative
sets +/-2 and +/-10 to +/-3 and +/-11, while favorable deltas still sustain
exactly twice the corresponding single-stream rate. Branch placement and
speculative fall-through fetch therefore change which ICC-side resources a
target consumes. The externally supported model is a banked or multiported
ICC preceded/followed by a control-flow-sensitive fetch window; assigning a
single `bank = f(VA[...])` formula from the slot-0 rings would be spurious.

## Tag identity: GPU-VMM alias experiment

probe_icache_alias.py maps one 2 MiB physical allocation at two distinct GPU
virtual addresses. Sixteen physical code lines, spaced by 4 KiB and
therefore mapping to one ICC set, are executed alternately through the two
aliases. The heap code is identical in both mappings and toggles its current
JMX base after each traversal. A second experiment uses two distinct
physical allocations as a positive control.

| Mapping | cycles/visit | ICC requests | ICC lookup miss |
|---|---:|---:|---:|
| one VA, 16 tags | 53.75 | 196622 | 63 |
| two VAs, same physical pages | 130.74 | 393137 | 196578 |
| two VAs, different physical pages | 130.74 | 393137 | 196582 |

The same-physical aliases behave bit-for-bit like distinct physical pages:
the two virtual mappings form 32 independently resident tags in one 16-way
set and continuously thrash. They are not coalesced by physical page
identity. Thus ICC is **functionally virtual-tagged**, or at minimum carries
a virtual-address alias identity with behavior equivalent to a VIVT cache.
The tested aliases differ by 2 MiB while retaining identical VA[11:0], also
directly confirming that VA bit 21 is tag material rather than an index
hash input.

What can be recovered experimentally is the tag equivalence relation:
different virtual line addresses are different ICC tags, even when they map
the same physical bytes. The literal internal SRAM tag encoding or a
lossless/compressed tag hash is not externally observable; hardware must
still disambiguate full virtual line identities to preserve correctness.

## Meaning of the GCC counters

The metric name gcc__cache_requests_type_instruction_lookup_miss is easy to
misread. It counts instruction requests arriving from an upstream lookup
miss. Its tag_hit and tag_miss subdivisions describe the GCC lookup result.
It is therefore wrong to interpret a rise in the unsuffixed metric at
128 KiB as a 128 KiB GCC capacity.

For warmed sequential loops:

| Loop | GCC incoming miss requests | GCC tag hit | GCC tag miss |
|---:|---:|---:|---:|
| 512 KiB | 32234 | 32220 | 14 |
| 640 KiB | 40423 | 40409 | 14 |
| 768 KiB | 48532 | 48518 | 14 |
| 1 MiB | 64916 | 64900 | 16 |

Thus ICC thrashing is serviced almost entirely as GCC hits through at least
1 MiB. The throughput transition near 128--192 KiB is a lower-level
service-bandwidth/latency effect, not a demonstrated GCC capacity boundary.

## What remains unknown

- whether the 62.5 KiB conflict-free sequential limit is caused primarily
  by fetch-ahead, reserved entries, or set imbalance;
- ICC replacement policy, the internal bank/port graph behind the measured
  relative-set conflicts, and whether VA bits above bit 31 affect it;
- the literal target/trace-buffer entry format and the reason its usable
  depth changes from 12 to 9 when the JMP moves to the last instruction slot;
- GCC capacity, line size, and whether GCC is per-SM, per-TPC, or shared at
  a wider scope;
- the literal relationship between the counter-visible target/trace entries
  and the ordinary ICC/fetch pipeline.  They are flushed or bypassed by
  `CCTL.I.IVALL`; the old claim of persistent tight-loop replay was retracted.

## Reproduction

    python3 tests/asm_construct/probe_icache_capacity.py \
      --sizes-kib 60,62,62.5,62.75,63,63.5,64,96
    python3 tests/asm_construct/probe_icache_partition.py \
      --actors diff4 --path-kib 16
    python3 tests/asm_construct/probe_icache_lines.py \
      --lines 480,496,504,512,516,528
    python3 tests/asm_construct/probe_icache_hash.py \
      --stride-lines 16,32,64 --counts 12,13,16,17,20,32
    python3 tests/asm_construct/probe_icache_hash.py \
      --stride-lines 32 --counts 8,9,10,11,12,13 --body-nops 7
    python3 tests/asm_construct/probe_icache_banks.py --sets 0,4,16,20
    python3 tests/asm_construct/probe_icache_banks.py --sets 0,2
    python3 tests/asm_construct/probe_icache_alias.py single
    python3 tests/asm_construct/probe_icache_alias.py same
    python3 tests/asm_construct/probe_icache_alias.py different

For raw counters, profile the second launch (--launch-skip 1) and collect
sm__icc_requests*, gcc__cache_requests_type_instruction_lookup_miss*, and
smsp__warps_issue_stalled_no_instruction.
