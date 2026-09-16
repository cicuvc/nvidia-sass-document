# GB202 Address Divergence Unit topology

Silicon: RTX 5090 (GB202, sm_120), 2026-09-15.  The starting architectural
description says that the Address Divergence Unit (ADU) handles address
divergence for branches/jumps and also supports constant loads and
block-level barriers.  These probes determine what those categories mean at
the SASS/MIO boundaries and where operand collection occurs.

## Best-fit structure

```text
subcore scheduler / scoreboard
            |
      local MIO instruction queues
            |
   MIO PQ late GPR collection / packet replay <---+
      (subcore-local bandwidth effects)
            |
      SM-wide ADU service/arbitration
            +---- divergent-target replay --------+
       /          |             \
 computed BRX   GPR LDC      block BAR
       |           |             |
 CBU/control   MIO2RF result   barrier state
```

The named counter boundary makes the ordering unusually strong evidence:
`sm__mio_pq_read_cycles_active_pipe_adu` is described as cycles in which the
MIO operand queue sends register operands to the ADU pipe.  Thus, for ADU
operations with a GPR input, the experimentally visible order is **MIO queue
-> late RF collection/PQ read -> ADU**.  This confirms that ADU is downstream
of the late collector.  The measurements do not require the SM-wide box to
be one physically monolithic controller; distributed arbitration with the
same behavior remains possible.

Ordinary LDG/LDS address generation is not in this ADU path.  Those
instructions increment LSU/IDC/L1TEX activity rather than the ADU counters.
The `sm__idc_divergent_*` counters also stay zero for deliberately divergent
BRX targets, so IDC and control-flow address divergence are distinct.

## NCU classification

`probe_adu_topology.py` uses a parameter-free, one-warp kernel.  With 64 test
instructions, the scalable counter contributions are:

| stream | `smsp pipe_adu` | PQ read -> ADU | ADU -> RF writeback | interpretation |
|---|---:|---:|---:|---|
| fixed-target `BRA` (near, far, predicated, or lane-divergent predicate) | 0 | 0 | 0 | no computed target to resolve |
| `BRX RZ,label` | 64 | 0 | 0 | ADU control transfer, no physical target GPR |
| `BRX {R24,R25},label` | 64 | 128 | 0 | two late-read 32-bit target operands |
| `LDC Rd,c[0][0]` | 64 | 0 | 64 | constant-load result returns through ADU MIO2RF |
| `LDC Rd,c[0][R24]` | 64 | `64 + 32` fixed/domain residue | 64 | one indexed-address GPR enters ADU through PQ |
| `LDCU URd,c[0][0]` | 0 | 0 | 0 | uniform constant load is not this ADU pipe |
| `BAR.SYNC 0` | 64 | 0 | 0 | block barrier uses ADU without RF traffic |

The `sm__inst_executed_pipe_adu` SM-domain counter has an unexplained +32
for LDC in this tiny one-warp kernel; the SMSP-domain counter has the exact
instruction slope shown above.  Conclusions use slopes and the exact SMSP
counts, not that residue.

The fixed-target result clarifies NVIDIA's wording.  Predicate divergence on
a `BRA` creates taken and fall-through SIMT groups, but both PCs are encoded
constants and the instruction does not execute on the counted ADU pipe.
`BRX`, whose target can vary by lane, executes there even when every lane's
runtime target happens to be equal.

Effective predication occurs at different points for the three clients.  At
N=256:

| false-predicated stream | admitted by MIOC/CBU | ADU executions | PQ reads | ADU writebacks |
|---|---:|---:|---:|---:|
| `@P6 BRX {R24,R25}` | yes | 0 | 0 | 0 |
| `@P6 LDC Rd,c[0][R24]` | yes | 256 | 0 | 0 |
| `@P6 BAR.SYNC` | yes | 256 | 0 | 0 |

Thus BRX is killed before target collection/ADU execution, whereas LDC and
BAR reserve/execute the ADU pipe before their effective predicate suppresses
operand traffic or a returned value.  A single universal "predicate check at
MIO dequeue" model is insufficient.

## ADU address-divergence replay is per unique target

For `brx_div`, lane `i` puts `(i mod K)*32` in the BRX target pair, selecting
one of K distinct two-instruction paths under BSSY/BSYNC.  Six values of K
give exact linear counts for 16 static BRX instructions:

| distinct targets per BRX | 1 | 2 | 4 | 8 | 16 | 32 |
|---:|---:|---:|---:|---:|---:|---:|
| `smsp pipe_adu` executions | 16 | 32 | 64 | 128 | 256 | 512 |
| RF -> PQ write cycles | 32 | 64 | 128 | 256 | 512 | 1024 |
| PQ read cycles -> ADU | 32 | 64 | 128 | 256 | 512 | 1024 |
| IDC divergent replays | 0 | 0 | 0 | 0 | 0 | 0 |

The ADU therefore processes one target group at a time.  Every unique target
causes one ADU execution and rereads both 32-bit halves of the target pair.
Crucially, the RF-to-PQ *write* counter grows along with the PQ-to-ADU read
counter.  The operand vector is not merely collected once and replayed from
a private ADU cache: each target group visibly traverses the complete
late-collection transaction again.  This implies a replay/feedback edge from
ADU target classification to the upstream collector.  It is actual replay at
the ADU/PQ boundary even though the NCU counter named
`IDC divergent_instruction_replays` does not count it.

## Shared backend versus local late collection

`probe_adu_scaling.py` selects warps 0 and 4 for the same subcore, or 0 and 1
for different subcores.  Aggregate issue rates (warp instructions/clock) are:

| stream | one warp | same-subcore 2 | different-subcore 2 | four subcores | all 8 warps |
|---|---:|---:|---:|---:|---:|
| LDC immediate | 0.208 | 0.293 | 0.292 | 0.370 | 0.425 |
| LDC indexed by one GPR | 0.154 | 0.189 | 0.284 | 0.362 | 0.420 |
| `BAR.SYNC` | 0.139 | 0.241 | 0.242 | 0.476 | 0.481 |

Immediate LDC and BAR need several warps to hide their per-warp latency, then
approach a common approximately 0.5 instruction/clock SM-wide ceiling.
Indexed LDC behaves differently only when its two warps share a subcore:
0.189 instead of 0.284 instruction/clock.  Different-subcore indexed LDC is
almost identical to immediate LDC.  The extra bottleneck is therefore the
subcore-local late operand path before the shared ADU service point, rather
than a per-subcore ADU backend.

BRX is not useful for measuring the backend ceiling: a dependent sequence of
control transfers costs about 36 clocks/BRX with RZ and 39 clocks/BRX with a
real target pair.  Multiple warps overlap that redirect latency without
making ADU throughput the limiting resource.

## Interaction with LSU and XU clients

The extended `probe_mio_topology.py` compares ADU clients with SHFL/LSU and
MUFU/XU traffic.  The strongest placement result is indexed LDC under a long
same-subcore SHFL stream:

| indexed-LDC victim | cycles/instruction |
|---|---:|
| solo | 5.24 |
| same-subcore active SHFL | 12.05 |
| same-subcore false-predicated SHFL | 5.25 |
| different-subcore active SHFL | 5.24 |

The active-only, same-subcore interaction is the expected collision at the
late GPR collector.  Immediate LDC, which has no GPR operand, does not show
that large active/control separation.  MUFU changes indexed LDC only from
5.25 to 5.36 cycles/instruction, while a MUFU victim remains at 7.98 under
LDC traffic.  This asymmetry is compatible with separate client queues and
priority/reservation at the local collection fabric; it is not evidence for
one flat FIFO shared by ADU, LSU, and XU.

## Probe entry points

- `tests/asm_construct/probe_adu_topology.py`: pipe classification,
  predication, and 1--32-target BRX divergence.
- `tests/asm_construct/probe_adu_scaling.py`: same/different-subcore ADU
  scaling.
- `tests/asm_construct/probe_mio_topology.py`: ADU/LSU/XU contention matrix.
