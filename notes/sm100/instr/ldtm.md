# LDTM / LDT — tensor-memory (TMEM) load  → PTX `tcgen05.ld`

**Opcode mnemonic:** `LDTM` (and alt `LDT`) = `0b1100111101110` (0x19ee, 6638)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_WR_SCBD`
**Virtual queue:** `$VQ_TMEM` (=40, a Blackwell-new queue) | **MEM_SCBD_TYPE:** `BARRIER_INST`

New on sm100 (Blackwell). This is the SASS realization of PTX
**`tcgen05.ld`** — an asynchronous, warp-collective load from the 5th-gen
TensorCore **Tensor Memory (TMEM)** into the general register file. TMEM is the
dedicated accumulator/operand memory that replaced the Hopper wgmma register
accumulators; `UTC*MMA` write results into TMEM and `LDTM` reads them back out.

Two mnemonics share the opcode:
- **`LDTM`** — the primary CLASS `ldtm_`; full `.shape`×`.num` matrix via the
  `layout`/`num` modifiers.
- **`LDT`** — an ALTERNATE CLASS (`ldt_`, parented under `ldsm__sImmOffset`) that
  pins `layout=32dp32bit` (`*2`) and exposes only a `SIZE_ldt` {32,64,128}
  modifier. It is the degenerate `.32x32b` form printed under a shorter name.

## Semantics
`LDTM Rd, [URb + Sb_offset]` asynchronously copies a block of TMEM, whose base
column address is `URb + Sb_offset` (a 32-bit TMEM byte/word address), into the
vector of registers starting at `Rd`, **collectively across the warp**. The
number of 32-bit registers written = f(`layout`, `num`) per PTX Table 52. Because
it is decoupled/async, completion is signaled through a **write scoreboard**
(`dst_wr_sb`); consumers must wait on that barrier (PTX `tcgen05.wait::ld`).

`INST_TYPE_DECOUPLED_WR_SCBD` + `src_rel_sb` pinned to `7` (none) confirms the
async model: the instruction has **no read-scoreboard release** (it reads only
the uniform address reg) and its **only** dependency handle is the write
scoreboard it sets when the TMEM data lands. This is the same category used by
`fence_*`, `syncs_flush_`, `utcbar_flush_`, `utcldsws_`.

## Variant overview
| Class | Kind | Opcode | Distinguisher |
|-------|------|--------|---------------|
| `ldtm_` | CLASS | 0x19ee | full `layout`×`num` matrix, optional `.pack::16b` |
| `ldt_` | ALT of `ldsm__sImmOffset` | 0x19ee | `layout` pinned `32dp32bit`; `size`∈{32,64,128} |

There is **no** `.red` (load-with-reduction) SASS variant in this dump — PTX
`tcgen05.ld.red` (min/max) must lower to `LDTM` + a separate reduction, or is
gated to `sm_101a`/`sm_103f` (see PTX target notes).

## Modifiers (LDTM)
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `layout` | `LAYOUT` | [87]∥[82:81] | TMEM access shape (see below) |
| `num` | `NUM` | [85:83] | repeat factor `x1..x128` → sets `IDEST_SIZE` |
| `pack` | `PACK` | [80] | `nopack`(0) / `PACK16BIT`(1) = PTX `.pack::16b` |

`LAYOUT` value-map (matches PTX `.shape`):
| val | name | PTX shape |
|----:|------|-----------|
| 0 | `16dp128bit` | `.16x128b` |
| 1 | `16dp256bit` | `.16x256b` |
| 2 | `32dp32bit` | `.32x32b` |
| 3 | `16dp64bit` | `.16x64b` |
| 4 | `16dp32bit_t0_t15` | `.16x32bx2` (first half, lanes 0–15) |
| 5 | `16dp32bit_t16_t31` | `.16x32bx2` (second half, lanes 16–31) |
| 6,7 | INVALID6/7 | illegal (guarded) |

`NUM`: `x1`=0 … `x128`=7. `dp` = "datapath" (lane group); `NNdpMMbit` = NN lanes
× MM bits per access, the TMEM tiling primitive.

`SIZE_ldt` (LDT only): `32`=0, `64`=1, `128`=2 (INVALID3..7). Sets
`IDEST_SIZE = 32 + (size==64)*32 + (size==128)*96` → 1/2/4 registers.

## Bit layout (128-bit, LDTM)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = 7  (pinned: no read scoreboard — async)
[112:110]           dst_wr_sb    = VarLatOperandEnc(dst_wr_sb)  ← async completion barrier
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x19ee
[87]∥[82:81]        layout       (3b, MSB at 87, interleaved with num)
[85:83]             vecidx       = num
[80]                texunpack    = pack   (reused control bit; "unpack" name is legacy)
[79:72]∥[63:40]     Sb_offset    = 32-bit signed TMEM offset (split field)
[39:32]             Rb           = URb  (uniform base address register)
[23:16]             Rd           = destination base register
[15]                Pg_not ; [14:12] Pg = @UPg predicate (UniformPredicate)
```
Notes:
- Predicate is a **UniformPredicate** (`UPg`), consistent with `udp_pipe` issue.
- Base address is a **UniformRegister** `URb` encoded in the 8-bit `Rb` slot
  [39:32] (uniform value in a GPR-width field).
- `Sb_offset` is a 32-bit immediate split as [79:72]∥[63:40] (PTX
  `immHalfSplitoff` for the `.16x32bx2` shapes rides here).
- `layout`/`num` share the [87:81] region interleaved: `layout[2]`=bit87,
  `num[2:0]`=[85:83], `layout[1:0]`=[82:81].

## IDEST_SIZE (register-vector width)
`IDEST_SIZE` (bits) = 32 × (register count). The count follows PTX Table 52:
| num | 16x32bx2 / 16x64b / 32x32b | 16x128b | 16x256b |
|-----|:--:|:--:|:--:|
| x1 | 1 | 2 | 4 |
| x2 | 2 | 4 | 8 |
| … | … | … | … |
| x128 | 128 | NA | NA |

The spec encodes this as a giant sum-of-products over (num, layout) in
`PREDICATES.IDEST_SIZE`; the CONDITIONS enforce the NA cells (e.g. `num==x128`
forbidden for `16x128bit`/`16x256bit`) plus N-register alignment
(`Rd % 2/4 == 0` for wide layouts) and `Rd ≤ MAX_REG_COUNT - N` range checks.

## Related instructions
- **`STTM` / `STT`** (0x19ed) — the store counterpart → PTX `tcgen05.st`. Same
  `layout`/`num` scheme; `STTM` swaps `dst_wr_sb`→`src_rel_sb` (it reads regs,
  releases a read scoreboard) and replaces `pack` with `EXPAND16BIT`
  (`.unpack::16b`). Adds source reg `Rb` [39:32] and TMEM addr `URc` [71:64].
- **`UTC*MMA`** — producers that write TMEM (`TMEMC`/`TMEME` accumulator
  operands). `LDTM` is the consumer that drains TMEM to registers.
- **`UTCBAR`** — tensor-core barrier (PTX `tcgen05.wait`/commit); pairs with the
  `dst_wr_sb` set by `LDTM` for cross-op ordering.
- **`LDSM`/`STSM`** — the Hopper shared-memory matrix load/store; `LDT` is
  literally an ALTERNATE of the `ldsm_` class tree, i.e. TMEM reuses the LDSM
  encoding family with a new opcode + TMEM operand type.
- Contrast Hopper **wgmma**: there was no TMEM; accumulators lived in registers,
  so no `LDTM`-equivalent was needed. See `notes/sm100/OVERVIEW.md` and sm_90
  `arch/tcgen05_vs_wgmma.md`.

## Latency (sm100_latencies.txt)
`LDTM`/`LDT`/`STTM`/`STT` form `LDTM_STTM_OP` (line 81), a member of the GPR
dependency tables. Its producer→consumer **true-latency row is uniformly `1`**
cycle in both `TABLE_TRUE(GPR)` and the UGPR table:
```
LDTM_STTM_OP`{Rd @RdRange,Rd2 @Rd2Range} : 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
```
This `1` is **not** the TMEM access latency — it is the fixed issue/dispatch
handoff. The real (variable, long) TMEM read latency is tracked out-of-band via
the **write scoreboard** `dst_wr_sb` (decoupled model), exactly like a global
load. `LDTM_STTM_OP` is also *subtracted* from `UDP_subset` (line 218), i.e. it
is excluded from the ordinary fixed-latency UDP timing and handled as a
scoreboard-gated op.

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/ldtm_test.cu` → `tests/ldtm_test.cubin`. All 8 hand-decoded
against the bit layout above — **every field matches** (opcode, layout, num,
pack, Rd, URb, Sb_offset). TMEM address prints as `tmem[URb(+off)]`.

| Disassembly | Lo64 / Hi64 | layout | num | pack | Rd | Soff |
|-------------|-------------|:------:|:---:|:----:|:--:|:----:|
| `LDTM R0, tmem[UR6]` | `…79ee` / `0008040000` | 2 `32dp32bit` | 0 `x1` | 0 | R0 | 0 |
| `LDTM.x2 R24, tmem[UR6]` | `…1879ee` / `080c0000` | 2 | 1 `x2` | 0 | R24 | 0 |
| `LDTM.16dp64bit.x2 R2, tmem[UR6]` | `…0279ee` / `080e0000` | 3 `16dp64bit` | 1 | 0 | R2 | 0 |
| `LDTM.16dp128bit.x4 R4, tmem[UR6]` | `…0479ee` / `08100000` | 0 `16dp128bit` | 2 `x4` | 0 | R4 | 0 |
| `LDTM.16dp256bit R12, tmem[UR6]` | `…0c79ee` / `08020000` | 1 `16dp256bit` | 0 | 0 | R12 | 0 |
| `LDTM.x2.PACK16BIT R18, tmem[UR6]` | `…1279ee` / `080d0000` | 2 | 1 | 1 | R18 | 0 |
| `LDTM.16dp32bit_t0_t15.x2 R16, tmem[UR6]` | `…1079ee` / `08880000` | 4 | 1 | 0 | R16 | 0 |
| `LDTM.16dp32bit_t16_t31.x2 R16, tmem[UR6+0x10]` | `…1079ee`(lo hi bit set) / `088a0000` | 5 | 1 | 0 | R16 | 16 |

Confirmed layout facts:
- `layout`/`num` interleave is exactly `layout[2]`=bit87, `num`=[85:83],
  `layout[1:0]`=[82:81] (e.g. `32dp32bit`=2 → bit82 set; `16dp256bit`=1 → bit81;
  the `_t0_t15`/`_t16_t31` values 4/5 set bit87).
- `Sb_offset` split field [79:72]∥[63:40] verified: `immHalfSplitoff=16` →
  `Soff=16` (the `.16x32bx2` second-half case).
- Each LDTM sets a **distinct write scoreboard** (`dst_wr_sb` = 0,1,7,2,3,4,7,5),
  confirming the decoupled async model — completion is tracked per-SB, and
  consumers wait via the [121:116] mask (`tcgen05.wait::ld`).

### Empirical: ptxas never emits the `LDT` short form
Every case — including plain `.32x32b.x1` — was emitted as **`LDTM`**, never
`LDT`. The `LDT`/`SIZE_ldt` ALTERNATE appears to be an assembler-only spelling
(or reserved for a path ptxas doesn't take from `tcgen05.ld`). Defaults
`.32dp32bit`/`.x1` are elided in the disassembly.

### Rest of the tcgen05 family (same kernel)
| PTX | SASS lowering |
|-----|---------------|
| `tcgen05.alloc.cta_group::1` | `UTCATOMSWS.FIND_AND_SET.ALIGN` (atomic TMEM-allocator find/set on a shared bitmap, in an `ELECT`+`NANOSLEEP` spin loop) |
| `tcgen05.dealloc` | `UTCATOMSWS.AND` |
| `tcgen05.relinquish_alloc_permit` | (no dedicated op; folds into surrounding sync) |
| `tcgen05.wait::ld` | realized via the LDTM **write-scoreboard** + wait mask (no standalone barrier op needed here) |

So TMEM allocation is a software-managed bitmap in shared memory manipulated by
`UTCATOMSWS` (uniform tensor-core atomic, warp-specialized) — not a hardware
allocator opcode.

## PTX → SASS mapping
| PTX | SASS |
|-----|------|
| `tcgen05.ld.sync.aligned.32x32b.x1.b32 {r0}, [ta]` | `LDTM R0, tmem[URb]` (defaults elided) |
| `tcgen05.ld.sync.aligned.32x32b.x2.b32 {r0,r1}, [ta]` | `LDTM.x2 R0, tmem[URb]` |
| `tcgen05.ld.sync.aligned.16x128b.x4.b32 {r0..r7}, [ta]` | `LDTM.16dp128bit.x4 R0, tmem[URb]` |
| `…16x32bx2…x2… [ta], 16` | `LDTM.16dp32bit_t0_t15/_t16_t31.x2 R…, tmem[URb+0x10]` |
| `…{.pack::16b}` | `LDTM….PACK16BIT …` (`pack`=1, bit[80]) |

`.sync.aligned` are implicit (warp-collective is intrinsic to the op); the
uniform predicate `@UPg` provides conditional execution.

## Open questions
- How does PTX `tcgen05.ld.red` (min/max reduction) lower? No `.red` SASS variant
  in this dump — split into `LDTM` + reduction, or arch-gated (PTX notes restrict
  `.red` to `sm_101a`/`sm_103f`)?
- Exact TMEM addressing semantics: `tmem[URb+off]` — is the offset a column
  index or byte address? (`ILABEL_URb_SIZE=32` = 32-bit address label.)
- Is the `LDT`/`SIZE_ldt` ALTERNATE ever emitted by any front-end path, or is it
  purely an assembler alias?
- `pack`/`texunpack` bit [80] shares a name with the legacy texture-unpack
  control bit — confirmed here to encode `.pack::16b` (=1).
