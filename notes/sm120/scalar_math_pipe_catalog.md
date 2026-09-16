# GB202 scalar-math leaf-pipe catalog

Silicon: RTX 5090 (GB202, sm_120), 2026-09-15.  Probe:
[`probe_scalar_pipe_catalog.py`](../../tests/asm_construct/probe_scalar_pipe_catalog.py).

## Scope and method

This is an exhaustive **mnemonic-level** scan of every sm_120-encodable
fixed-latency scalar-math instruction in the spec pipe families
`int_pipe`, `fmalighter_pipe`, `fp16_pipe`, and `fma64lite_pipe`.  It covers
65 mnemonics: 36 + 15 + 9 + 5 respectively.

Each kernel contains only six MOV32I initializers, 128 independent instances
of one target operation, and EXIT.  Four launches were profiled with:

```text
smsp__inst_executed_pipe_aluheavy.sum
smsp__inst_executed_pipe_fmaheavy_subpipe_alulite.sum
smsp__inst_executed_pipe_fmaheavy_subpipe_fmaheavy.sum
smsp__inst_executed_pipe_fmalite.sum
smsp__inst_executed_pipe_fma_type_fp16.sum
smsp__inst_executed_pipe_fp64.sum
```

All four launches of every mnemonic produced the same counters.  The six
initial MOV32I instructions always contribute six ALU-Lite operations.  Every
target stream contributes exactly 128 operations to the pipe(s) shown below.

The scope deliberately excludes tensor instructions (`HMMA`, `IMMA`,
`DMMA`, `MXQMMA`, `OMMA`, `QMMA`, `MOVM`) and non-arithmetic fixed-pipe
helpers (`CS2R`, `IDE`, `LEPC`, `RPCMOV`, `VOTE`).  MIO, CBU, UDP and TTU
instructions are separate topology domains, not scalar-math pipe candidates.
Names present only in the inherited pipe sets but having zero sm_120 variants
are also excluded; they are not executable GB202 instructions.

## Measured catalog

### ALU Heavy

| Spec family | Mnemonics |
|---|---|
| `int_pipe` | `BMSK`, `F2FP`, `F2IP`, `I2FP`, `I2I`, `I2IP`, `IABS`, `IADD3`, `ISCADD`, `ISCADD32I`, `LEA`, `LOP`, `LOP3`, `LOP32I`, `P2R`, `PLOP3`, `PRMT`, `PSETP`, `R2P`, `SGXT`, `SHF`, `SHL`, `SHR` |
| `fp16_pipe` in the static spec | `HMNMX2`, `HSET2`, `HSETP2` |

The packed conversion instructions (`F2FP/F2IP/I2FP/I2I/I2IP`) are therefore
ALU-Heavy operations, not FMA or MIO conversions.  The packed-half
compare/minmax instructions are another important exception to a literal
reading of the static `fp16_pipe` family: they execute on ALU Heavy and do not
increment the FP16/FMA counters.

### ALU Lite (the ALU subpipe of physical Shared FMA Heavy)

| Spec family | Mnemonics |
|---|---|
| `int_pipe` | `FMNMX`, `FSEL`, `FSET`, `FSETP`, `IADD`, `IADD32I`, `IMNMX`, `ISETP`, `MOV`, `MOV32I`, `MOV64IUR`, `SEL`, `VIMNMX` |
| `fmalighter_pipe` in the static spec | `VIADD` |

This group is broader than move/select: it includes legacy two-input integer
add, integer/float minmax, scalar compare/set, and the video-add instruction.
Conversely, modern three-input `IADD3`, packed conversions, shifts, LOP/LOP3,
and predicate-file transfers remain ALU Heavy.

### FMA Heavy subpipe of physical Shared FMA Heavy

| Mnemonics | Target-counter result |
|---|---:|
| `FSWZADD`, `IDP.2A`, `IDP.4A`, `IMAD`, `IMUL`, `IMUL32I` | +128 FMA Heavy |

Previously tested `IMAD.LO`, `IMAD.HI`, and `IMAD.WIDE` all select this same
leaf.  HI/WIDE have twice the internal issue occupancy of LO, but do not select
a different execution pipe.

### FMA Lite

| Mnemonics | Target-counter result |
|---|---:|
| `FADD`, `FADD32I`, `FFMA`, `FFMA32I`, `FHADD`, `FHFMA`, `FMUL`, `FMUL32I` | +128 FMA Lite |

`FHADD/FHFMA` are scalar FP16/BF16-result operations on FMA Lite; they are not
the packed-two-lane FP16 pipe described next.

### Coupled packed-FP16 execution on both FMA leaves

| Mnemonics | FMA Heavy | FMA Lite | FP16 type |
|---|---:|---:|---:|
| `HADD2`, `HADD2_32I`, `HFMA2`, `HFMA2_32I`, `HMUL2`, `HMUL2_32I` | +128 | +128 | +128 |

One packed instruction is counted once on **each** FMA leaf, plus once by the
FP16 type classifier.  The best behavioral interpretation is that its two
packed lanes engage the Heavy and Lite arithmetic subpipes together, rather
than the three counters naming three serial stages.

Two modifier controls matter:

| Mode | FMA Heavy | FMA Lite | FP16 type | Interpretation |
|---|---:|---:|---:|---|
| `HADD2.F32` | +128 | 0 | +128 | single-half widening/add path uses only the Heavy leaf |
| `HFMA2.MMA` | +128 | +128 | +128 | on sm_120, same coupled leaves as plain packed HFMA2 |

Thus the inherited sm_90 distinction that assigns `HFMA2.MMA` to
`fma64lite_pipe` does not describe GB202 execution.  The sm_120 alternate
class shares the ordinary packed-FP16 execution counters.  `HADD2.F32`, on
the other hand, is a genuine same-mnemonic mode that changes leaf occupancy.

### FP64 pipe

| Mnemonics | Target-counter result |
|---|---:|
| `CLMAD`, `DADD`, `DFMA`, `DMUL`, `DSETP` | +128 FP64 |

`CLMAD` therefore shares the exposed FP64 execution domain despite performing
carry-less integer multiplication.  No sm_120 variant exists for the inherited
`fma64heavy_pipe` names `DMNMX` or `DSET`.

## Static spec family versus measured leaf

The latency/spec pipe family is useful for dependency tables, but it is not
always the physical leaf selected on GB202:

| Static family anomaly | Measured leaf |
|---|---|
| `VIADD` in `fmalighter_pipe` | ALU Lite |
| `HMNMX2/HSET2/HSETP2` in `fp16_pipe` | ALU Heavy |
| packed `HADD2/HFMA2/HMUL2` (including `HFMA2.MMA`) in `fp16_pipe` | FMA Heavy + FMA Lite together |
| `HADD2.F32` widening mode | FMA Heavy only (+ FP16 type) |
| `CLMAD` in `fma64lite_pipe` | exposed FP64 pipe |

No target mnemonic in the minimal four-replay scan showed variable
Heavy/Lite routing.  An earlier apparent PRMT/BMSK split came from pairing NCU
launch IDs incorrectly in a harness that performs one warm-up plus one measured
launch and contains hundreds of framework ALU operations.  The minimal named
kernels resolve PRMT and BMSK unambiguously as ALU Heavy.

This catalog is exhaustive by mnemonic, not by every modifier/operand-form
variant.  The tested modes cover each distinct opcode family plus already
known mode-sensitive cases (IMAD low/high/wide, IDP 2A/4A, HADD2.F32, and
HFMA2.MMA).  A future
variant-level scan would be relevant only where modifiers plausibly change
the arithmetic width or result format; ordinary register/immediate/constant
operand forms are expected to retain the mnemonic's leaf.
