# FSWZADD — sm120 (Blackwell (GB20x)) graphics/compute instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-10  
**Probe:** `experiments/graphics_batch_t/probe_fragment_dfdx.frag`, `probe_fragment_fwidth.frag`, `probe_fragment_lane_warp.frag`  
**Open items:** none for the fragment derivative path; general fields below remain  
**Audit:** `tools/notes_audit.py` · basis: 'silicon-verified' attestation

## Conclusion

`FSWZADD` — `INST_TYPE_COUPLED_MATH`, pipe `fmalighter_pipe`, opcode `0x822`, **1 CLASS**
in the sm120 dump.  A real Vulkan fragment shader confirms that the sm120
graphics compiler emits `FSWZADD.DXY` as the final quad-combine primitive
behind `dFdx`, `dFdy`, and `fwidth`.

## Graphics derivative semantics (sm120/sm75 verified)

The probe interpolates a smooth varying, computes `dFdx(vcolor.xy)` and
`dFdy(vcolor.zw)`, and captures the graphics compiler output through
`VK_KHR_pipeline_binary`.

The perspective-corrected varying values are first shuffled to their quad
neighbours; `FSWZADD.DXY` then combines the neighbour (`Ra`) and current
value (`Rc`) with a lane-specific sign pattern:

```text
SHFL.BFLY PT, R1,  R4, 0x1, 0x1c03   ; lane XOR 1: horizontal neighbour
SHFL.BFLY PT, R3,  R6, 0x2, 0x1c03   ; lane XOR 2: vertical neighbour
SHFL.BFLY PT, R8,  R5, 0x1, 0x1c03
SHFL.BFLY PT, R10, R7, 0x2, 0x1c03

FSWZADD.DXY R0, R1,  R4, PNNPPNNP     ; dFdx(vcolor.x)
FSWZADD.DXY R2, R3,  R6, PNPNNPNP     ; dFdy(vcolor.y)
FSWZADD.DXY R1, R8,  R5, PNNPPNNP     ; dFdx(vcolor.z)
FSWZADD.DXY R3, R10, R7, PNPNNPNP     ; dFdy(vcolor.w)
```

Observed `npCtrl` behavior with the already-shuffled neighbour in `Ra` and
the current value in `Rc`:

| operation | npCtrl | lane 0 / 2 | lane 1 / 3 |
|---|---|---|---|
| `dFdx` | `PNNPPNNP` | `+Ra - Rc` | `-Ra + Rc` |
| `dFdy` | `PNPNNPNP` | lanes 0/1: `+Ra - Rc` | lanes 2/3: `-Ra + Rc` |

The sign changes compensate for which side each lane's XOR neighbour lies
on, producing a consistently positive X/Y derivative.

`SHFL` XOR1/XOR2 directly encode the fragment-quad axes: lane bit 0 is X
parity and lane bit 1 is Y parity.  Integer-attachment readback of
`(gl_SubgroupInvocationID, gl_WarpIDNV, gl_SMIDNV)` gives the complete warp
layout, identical on sm120 and sm75:

```text
y=0:   0   1 | 16  17
y=1:   2   3 | 18  19
y=2:   4   5 | 20  21
y=3:   6   7 | 22  23
y=4:   8   9 | 24  25
y=5:  10  11 | 26  27
y=6:  12  13 | 28  29
y=7:  14  15 | 30  31
         x=0..3
```

For warp-local fragment coordinates `qx=0..3`, `qy=0..7`:

```text
lane = 16 * (qx >> 1) + 2 * qy + (qx & 1)
```

The four pixels of each 2x2 quad are:

```text
lane base + 0 = top-left
lane base + 1 = top-right
lane base + 2 = bottom-left
lane base + 3 = bottom-right
```

The X pattern is `PNNPPNNP`; the Y pattern is `PNPNNPNP`.  The raw sm120
encoding observed is:

```text
FSWZADD.DXY R0, R1, R4, PNNPPNNP
  0x0000006601007822 / 0x001fc40000022004

FSWZADD.DXY R2, R3, R6, PNPNNPNP
  0x0000005a03027822 / 0x001fc40000022006
```

Compared with sm75, `DXY` sets both `div` bits at [81]/[77].  The sm75 form
uses the same low encoding but leaves those bits clear and prints without
the suffix.

`fwidth` reuses the X/Y differences and combines absolute values:

```text
FADD.FTZ R0, |R0|, |R3|
FADD.FTZ R1, |R1|, |R6|
```

Thus `fwidth(x) = abs(dFdx(x)) + abs(dFdy(x))`; no additional derivative
primitive is emitted.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `fswzadd_` | `0x822` | `/FTZ("noftz"):ftz /Round1("RN"):rnd /DIV("nodiv"):div :Rd :Ra :Rc NP:npCtrl` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32` |
| `ILABEL_Ra_SIZE` | `32` |
| `ILABEL_Rc_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_COUPLED_MATH` |
| `ISRC_A_SIZE` | `32` |
| `ISRC_C_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `0` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |

## Encoding

Bit map of the first layout (`fswzadd_`); the other CLASSes differ in their
modifier fields, enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [80:80] | `ftz` | 1 | `ftz` |
| [79:78] | `stride` | 2 | `rnd` |
| [81:81]+[77:77] | `div` | 2 | `div` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [71:64] | `Ra_URc` | 8 | `Rc` |
| [39:32] | `Rb` | 8 | `npCtrl` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | *7 |
| [112:110] | `dst_wr_sb` | 3 | *7 |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_4(batch_t,usched_info,reuse_src_a,reuse_src_c) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `fswzadd_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `fswzadd_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `fswzadd_` | `OOR_REG_ERROR` | Register Ra is out of range |
| `fswzadd_` | `OOR_REG_ERROR` | Register Rc is out of range |
| `fswzadd_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info, reuse_src_a, reuse_src_c |
| `fswzadd_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | ?DRAIN and ?WAITn_END_GROUP tokens are not allowed with .reuse |

## Pipe and latency

Compute pipe(s): `fmalighter_pipe`.  Latency tables (true/output/anti dependency) are not transcribed
here; the dump's own latency section is the reference.

## Measurement

> Verified through real Vulkan fragment shaders.  NVIDIA graphics compiler
> output was captured with `VK_KHR_pipeline_binary`, decompressed, and
> disassembled with nvdisasm.

| field | value |
|---|---|
| host | NVIDIA GeForce RTX 5090 (sm120), NVIDIA TITAN RTX (sm75) |
| probe / test | `experiments/graphics_batch_t/probe_fragment_dfdx.frag`, `probe_fragment_fwidth.frag`, `probe_fragment_lane_warp.frag` |
| measured behaviour | XOR1/XOR2 quad neighbour selection; X=`PNNPPNNP`, Y=`PNPNNPNP`; 4x8 fragment warp layout; `DXY` sets div fields [81]/[77]; `fwidth`=`abs(dx)+abs(dy)` |
| evidence tier after the run | silicon-verified |

## Architecture relationship

This mnemonic is also a compute instruction on: `sm100`, `sm103`, `sm107`, `sm70`, `sm75`, `sm80`, `sm89`, `sm90`.

## Open questions

Program-wide items (decoder round-trip, printed form) are tracked once per architecture in
[`../MEASUREMENTS.md`](../MEASUREMENTS.md); anything specific to this mnemonic belongs here.
<!-- generated:isa-notes:end -->
