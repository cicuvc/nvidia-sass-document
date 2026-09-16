# Uniform-indexed GPR topology on GB202

Silicon: RTX 5090 (GB202, sm_120).  Probe sources:
`tests/asm_construct/probe_hmma_indexed_rf.py` and
`tests/asm_construct/probe_mov_indexed_rf.py`.

## Meaning and supported forms

The spec notation `RF:indexUR[UniformRegister:UR]` denotes a GPR selected by a
uniform register.  In assembler dialect this is written `R[URx]`.  The UR
contains the numeric GPR base; it is a selector, not the tensor/MOV data.

The following forms execute correctly on sm_120:

```
MOV R50, R[UR4]
MOV R[UR5], R16
MOV R[UR4], 0x76543210
HMMA.16816.F32.BF16 R[UR4], A, B, R[UR4], UPT
```

For indexed HMMA the encoding requires `URd == URc`, so it is necessarily an
in-place dynamic accumulator.  Setting UR4=40 makes both destination and C
refer to `{R40,R41,R42,R43}` for F32 accumulation.

## No additional visible execution resource

Direct and indexed forms have identical timing:

- rotating fixed-register versus indexed HMMA: 64/128/256/512 instruction
  medians are 2022/4070/8166/16358 clocks for both;
- direct versus indexed MOV, in both read and write directions:
  256/512/1024/2048 instructions take 517/1029/2053/4101 clocks for both;
- same-subcore scalar and uniform-pipe victim tests find no repeatable
  fixed-versus-indexed penalty.

NCU agrees exactly.  For 512 HMMAs, fixed and indexed runs both report 512
HMMA-pipe instructions, 66 ALU instructions, zero uniform-pipe instructions,
15838 `math_pipe_throttle`, zero `mio_throttle`, and 346 `wait`.  For 2048
direct/indexed MOV reads both report 2178 ALU instructions, zero uniform-pipe
instructions, zero math/MIO/dispatch throttle, and 602 `wait`.

Thus indexedRF is not dispatched through the UDP/uniform pipe or MIO, and it
does not add a visible tensor admission, scalar issue, or RF-collection cost.

## Selector sampling and forwarding

An `UMOV UR4,44` producer followed by either indexed MOV or indexed HMMA gives
the same boundary: gaps 0--1 still select the old GPR group and gap 2 onward
selects the new group.  In contrast, an ordinary `IADD3` consuming UR4 as data
sees the new value at gap 0, demonstrating a UDP-to-ALU forwarding path that
the indexed selector does not use.

The reverse experiment issues indexed MOV/HMMA first and then overwrites UR4.
Even at gap 0, the already-issued operation always uses the old selector.
Repeated same-UR versus unrelated-UR overwrite streams also have exactly the
same timing, so this is not a late read protected by a visible WAR stall.

The narrowest model consistent with the data is:

```
committed URF read -> early indexed-register decoder / GPR address mux
                  -> ordinary GPR collector or destination allocation
```

The selector is snapshotted at or near issue/dispatch, before tensor operand
collection.  It reads committed URF state and lacks the normal uniform-result
forwarding path.  After resolution, HMMA follows the ordinary tensor/RF path
and MOV follows `int_pipe`; the indexed decoder itself is throughput-hidden.

This places indexedRF alongside the subcore issue/RF-address frontend rather
than in MIO, UDP execution, or the tensor backend.
