# LDTM.STAT — fused TMEM load and per-thread reduction

`tcgen05.ld.red` is not synthesized from ordinary `LDTM` plus ALU
instructions on sm103.  It lowers to the dedicated SASS class
`ldtm_stat_`, printed as `LDTM.STAT`, with opcode `0x15ee`.  Ordinary
`LDTM` remains opcode `0x19ee`.

This instruction has two register destinations:

```text
LDTM.STAT[.layout].xN.ROWOP[.FMT][.NAN] Rd2, Rd, tmem[URb+offset]
```

- `Rd` is the base of the `xN` vector receiving the ordinary TMEM load.
- `Rd2` receives the reduction of those loaded columns for the same thread.
  SASS orders it before the vector destination, reversing their order relative
  to the PTX output tuple (`out`, then `redVal`).
- Both destinations are asynchronous and covered by the instruction's one
  write scoreboard (`INST_TYPE_DECOUPLED_WR_SCBD`, `VQ_TMEM`).

## Real ptxas lowering

CUDA 13.1, `-arch=sm_103a`, produces:

```text
tcgen05.ld.red...32x32b.x2.u32.max {r0,r1}, red, [taddr]
    LDTM.STAT.x2.MAX R7, R4, tmem[UR4]

tcgen05.ld.red...32x32b.x4.s32.min {r0..r3}, red, [taddr]
    LDTM.STAT.x4.MIN.S32 R9, R4, tmem[UR4]

tcgen05.ld.red...32x32b.x2.f32.max.abs.NaN {r0,r1}, red, [taddr]
    LDTM.STAT.x2.MAXABS.F32.NAN R7, R4, tmem[UR4]
```

The PTX `.16x32bx2` composite is split in the same manner as ordinary LDTM:

```text
LDTM.STAT.16dp32bit_t0_t15.x4.MIN R9, R4, tmem[UR4]
LDTM.STAT.16dp32bit_t16_t31.x4.MIN R9, R4, tmem[UR4+0x10]
```

Both instructions name the same `Rd` and `Rd2`.  The first form writes only
threads 0–15 and the second only threads 16–31, so their destination lane sets
do not overlap.  ptxas gives the first instruction no destination scoreboard
(`wr=7`) and has only the second claim one; consequently the PTX-level
`tcgen05.wait::ld` waits for the whole compound operation with one barrier.

## Modifiers and restrictions

| SASS modifier | field | encoding | PTX meaning |
|---|---|---:|---|
| `MAX` | `rowop` | 0 | `.max` |
| `MAXABS` | `rowop` | 1 | `.max.abs` |
| `MIN` | `rowop` | 2 | `.min` |
| `MINABS` | `rowop` | 3 | `.min.abs` |
| default / `S32` / `F32` | `fmt` | 0 / 1 / 2 | `.u32` / `.s32` / `.f32` |
| absent / `NAN` | `nan` | 0 / 1 | default / `.NaN` handling |

The default unsigned format is elided by cuobjdump.  Integer formats allow
only `MAX` and `MIN`; absolute-value operations are F32-only.  `NAN` is also
F32-only.  Unlike ordinary LDTM, `STAT` supports only `32dp32bit` and the two
half-warp `16dp32bit` layouts, and its repeat factor starts at `x2`; there is no
`x1`, `PACK16BIT`, `16dp64bit`, `16dp128bit`, or `16dp256bit` form.

## Encoding

```text
[91]∥[11:0]         opcode       = 0x15ee
[87]∥[82:81]       layout       = 2 (32dp32bit), 4 (t0_t15), 5 (t16_t31)
[85:83]             num          = 1..7 (x2..x128)
[80]                fixed        = 0
[79:72]∥[63:40]    Sb_offset    = signed 32-bit TMEM column offset
[68]                nan
[67:66]             rowop
[65:64]             fmt
[39:32]             URb
[31:24]             Rd2          = scalar reduction destination
[23:16]             Rd           = vector-load destination base
[15]∥[14:12]       uniform predicate
```

The ordinary LDTM scoreboard/control encoding is otherwise retained:
`src_rel_sb=7`, variable-latency `dst_wr_sb`, request mask `[121:116]`, and
the same split TMEM address immediate.

## Direct-SASS hardware validation

The repository assembler's native cubin was executed on a real B300.  No PTX
or ptxas-generated executable participates in this test.  Lane 0 observed:

| form | loaded vector | `redVal` |
|---|---|---|
| `.u32.max` | `9, 2, 15, 4` | `15` |
| `.s32.min` | `-5, 7, -20, 3` | `-20` |
| `.f32.max.abs.NaN` | `1, -4, payload-NaN 0x7fc12345, 2` | canonical NaN `0x7fffffff` |
| `.f32.min.abs` | `4, -2, .5, -8` | `.5` |
| split `.16x32bx2.u32.min` | `9, 2, 15, 4` | `2` |

Thus the ordinary load destination preserves the original bits (including a
NaN payload), while the fused F32 `.NaN` reduction canonicalizes its NaN
result.  The split half-warp pair also produces one coherent vector and scalar
result when both instructions name the same destinations.

The B200 negative control uses a valid sm100a cubin from the same assembler,
then replaces only its six ordinary-LDTM placeholder instruction words with
the corresponding sm103 `0x15ee` words.  The module loads and launches, but
synchronization returns CUDA error 715 and the GPU reports `Illegal Instruction
Encoding`.  This rules out mere rejection of an sm103 ELF on B200: opcode
`0x15ee` itself is unsupported there.

Reproduction corpus: `tests/tcgen05_ld_red.cu`; exact assembler vectors:
`tests/asm_construct/test_tcgen05_ldred_sm103.py`; direct-SASS hardware probe:
`tests/asm_construct/tcgen05_ldred_semantics_sm103.sass` and
`tests/asm_construct/probe_tcgen05_ldred_modal.py`; decoder:
`tools/decode_ldtm.py`.
