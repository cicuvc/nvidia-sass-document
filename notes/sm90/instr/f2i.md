# F2I — float→integer convert

**Opcode mnemonic:** `F2I`  |  **Pipe:** `mio_pipe` (`VIRTUAL_QUEUE=$VQ_MUFU`)  |
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

Converts a floating-point source (F16 / F32 / F64 / BF16) to an integer
(U8/S8/U16/S16/U32/S32 or, in the `Rd64` forms, U64/S64) with a selectable
rounding mode, optional FTZ (flush input denormals) and NTZ.

Unlike the fixed-latency math pipes (FADD/IADD3/FFMA/HMMA), **F2I is a
variable-latency MUFU-queue op**: it sets a *write scoreboard* on its result and
consumers wait on it via `req_bit_set`; its RAW latency is `ORDERED_ZERO`
(scoreboard-ordered), not a fixed cycle count.

## Semantics
`Rd = (int_dstfmt) round_rnd( [|] [-] src )`, `src` from register / const-bank /
uniform-register / immediate. Rounding modes (PTX `.rzi/.rni/.rmi/.rpi`):

| Round3 | value | meaning | PTX | C helper |
|---|--:|---|---|---|
| ROUND | 0 | round to nearest even | `.rni` | `__float2int_rn` |
| FLOOR | 1 | toward −∞ | `.rmi` | `__float2int_rd` |
| CEIL  | 2 | toward +∞ | `.rpi` | `__float2int_ru` |
| TRUNC | 3 | toward zero | `.rzi` | `(int)f` |

## Variant overview (81 variants; opcode = 13-bit)
| form | source operand | opcode (32-bit dst) |
|---|---|--:|
| `f2i__Rb_*`  | register | `0x305` |
| `f2i__Cb_*`  | const bank `c[..][..]` | `0xb05` |
| `f2i__CXb_*` | const bank (extended/ULDC desc) | `0x1b05` |
| `f2i__URb_*` | uniform register | `0x1d05` |
| `f2i__Ib_*` / `_IU_` | immediate | (imm form) |
| `f2i_Rd64__*` | 64-bit dest (U64/S64) | high-bit set forms |
| `f2i_swap__*` | operand-swap encodings | — |

Each form × {srcfmt 16b/32b/64b/bf16} × {dstfmt} gives the 81 variants.

## Modifiers (field positions, register form `f2i__Rb_32b`)
| modifier | slot | bits | values |
|---|---|---|---|
| srcfmt | `cop` | [86:84] | F32=2 (F16/F64/BF16 other) |
| ftz | `UPq_not` | [80] | noftz=0 / FTZ=1 |
| rnd | `stride` | [79:78] | ROUND/FLOOR/CEIL/TRUNC (see table) |
| ntz | `ntz` | [77] | nontz=0 / NTZ=1 |
| dstfmt | `dstfmt` | [76:75],[72] | U8=0,S8=1,U16=2,S16=3,U32=4,S32=5 |
| src negate | — | [63] | `-` |
| src abs | — | [62] | `\|·\|` |

Default assembler form is `S32.F32` with `ROUND`; nvdisasm omits the defaults
(so plain `F2I` = S32←F32, RN).

## Bit layout (128-bit, register form)
```
[124:122]∥[109:105] opex   [121:116] req_bit_set  [115:113] src_rel_sb
[112:110] dst_wr_sb        [103:102] pm_pred       [91]∥[11:0] opcode
[86:84] cop(srcfmt) [80] ftz [79:78] rnd [77] ntz [76:75]∥[72] dstfmt
[63] src.neg [62] src.abs  [39:32] Rb  [23:16] Rd  [15]∥[14:12] Pg
```

## Latency / pipeline (the point of interest)
- `mio_pipe`, `VQ_MUFU`, `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `PREDICATES`
  `IDEST_SIZE=32, ISRC_B_SIZE=32`.
- `TABLE_TRUE(SCOREBOARD): … = ORDERED_ZERO` — result availability is signalled
  by a scoreboard, not a fixed cycle count. (`TABLE_TRUE(GPR)` gives only the
  small fixed component `MIO_CBU_OPS→ALL = 2`.)
- **As a producer:** F2I sets `dst_wr_sb` (a write scoreboard) whenever its
  result is live; the dependent consumer sets the matching `req_bit_set` bit.
- **As a consumer:** F2I waits on its source's scoreboard (e.g. the `LDG` that
  produced the float) via `req_bit_set`.

### In-order MUFU-queue scoreboard optimisation (empirical)
In the dependent chain (`tests/f2i_test.cu :: f2i_dep`, 16× `(int)f[t+i]` summed):
```
F2I.TRUNC.NTZ R14, R14   stall=8  wr_sb=0        # sets SB0 on R14
F2I.TRUNC.NTZ R9,  R9    stall=1  wr_sb=7        # NO scoreboard
IADD3 R10, R14, R13, R10 stall=7  req=000001     # waits SB0 (=R14)
```
Only *some* F2I set a scoreboard. Because F2I issue in program order through the
single in-order MUFU queue, waiting on the **latest** F2I's scoreboard
transitively guarantees all earlier same-queue F2I have completed — so ptxas
scoreboards only the sync-point producers and leaves the rest at `wr_sb=7`. With
only 6 scoreboards (SB0–5, mostly consumed by `LDG`), this economises heavily.

## Latency vs sequence (empirical, `tests/f2i_lat_test.cu`)

Because F2I is scoreboard-tracked, its true result latency is **not** a fixed
stall you can read off the instruction — it is signalled at runtime. Constructing
consecutive F2I sequences confirms this and separates the two observable numbers:

**1. Independent F2I → throughput, not latency.** 8–16 unrelated F2I issue at a
steady **~8-cycle cadence** (consecutive-F2I issue gap = 8 in `f2i_indep`/
`f2i_tput`). That is the MIO/MUFU single-warp issue ceiling for F2I, not its
latency. Their `LDG` inputs sit 26–69 cycles upstream (memory latency, hidden by
the load scoreboards).

**2. F2I result → consumer is scoreboard-protected.** The consumer is placed as
close as **2–5 cycles** statically and carries a `req_bit_set` wait on the F2I's
`dst_wr_sb`; the real (variable) latency is enforced dynamically by the
scoreboard. So the static gap is *not* the latency — matching
`TABLE_TRUE(SCOREBOARD)=ORDERED_ZERO`.

**3. Dependent recirculation** (`f2i_dep_chain`: `x = (int)((float)x*1.5+1)`),
per-iteration structure:
```
F2I.TRUNC.NTZ R3, R3   stall=2  wr_sb=0      # sets SB0
I2FP.F32.S32  R5, R3   stall=5  req=000001   # waits SB0 (scoreboard), fixed-latency pipe
FFMA          R5,R5,R0 stall=6                # fixed latency
F2I.TRUNC.NTZ R5, R5   stall=2  wr_sb=0      # next
```
- Full F2I→F2I iteration gap = **13 cycles** (2+5+6), and it is **dominated by
  the fixed-latency ops** (`I2FP` 5 + `FFMA` 6), *not* by F2I. F2I contributes
  only its 2-cycle issue stall plus a runtime scoreboard wait.
- ptxas deliberately picks **`I2FP` (int_pipe, fixed latency)** over `I2F`
  (mio/MUFU, scoreboard) for the int→float step, keeping the loop on the fast
  fixed pipe; only the unavoidable F2I stays on the MUFU queue.

**Conclusion:** unlike the fixed-latency pipes (where a dependent chain's stall
spacing *equals* the `TABLE_TRUE` latency — see `../arch/usched_latency.md`), a
consecutive-F2I sequence exposes only (a) the ~8-cyc MIO issue throughput and
(b) scoreboard serialisation. F2I's own execution latency is variable and
scoreboard-hidden, so it cannot be read from static stall counts — exactly what
`ORDERED_ZERO` in the latency file encodes.

## Verified encodings (`tests/f2i_test.cu`, sm_90)
| SASS | source | rounding / fmt |
|---|---|---|
| `F2I.TRUNC.NTZ Rd, Rs` | `(int)f` | S32←F32, RZ |
| `F2I.NTZ Rd, Rs` | `__float2int_rn` | S32←F32, RN |
| `F2I.FLOOR.NTZ Rd, Rs` | `__float2int_rd` | RM |
| `F2I.CEIL.NTZ Rd, Rs` | `__float2int_ru` | RP |
| `F2I.U32.TRUNC.NTZ Rd, Rs` | `(unsigned)f` | U32←F32 |
| `F2I.S64.F64.TRUNC Rd, Rs` | `(long long)d` | S64←F64 (no NTZ) |

### PTX→SASS
`cvt.rzi.s32.f32` → `F2I.TRUNC.NTZ`; `cvt.rni/rmi/rpi` → default/`FLOOR`/`CEIL`;
`cvt.*.u32.f32` → `.U32`; `cvt.*.s64.f64` → `.S64.F64`. The `.NTZ` tag appears on
F32 sources (denormal handling); F64 conversions omit it.

## Cross-comparison
- Sibling MUFU-queue converts: `F2F` (float↔float), `I2F` (int→float),
  `I2FP`/`F2IP` (packed), `F2I64`/`I2F64`. All share `VQ_MUFU` +
  decoupled-scoreboard behaviour.
- Contrast with the fixed-latency pipes documented in `../arch/usched_latency.md`:
  those never write a scoreboard and are protected by stall counts; F2I is the
  opposite — scoreboard-protected, stall counts only cover MIO issue throughput.

## Open questions
- Exact F2I result latency distribution (scoreboard = variable; would need a
  latency microbenchmark, not static SASS).
- F16/BF16 source lowering: `(int)__half2float` did not emit a direct `F16`-src
  F2I here (went through promotion) — confirm whether `cvt.rzi.s32.f16` PTX emits
  the `_16b` F2I variant directly.
