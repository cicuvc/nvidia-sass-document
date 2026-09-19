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
column address is `URb + Sb_offset` (a 32-bit TMEM column address), into the
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

There is **no** `.red` (load-with-reduction) SASS variant in the sm100 dump.
On sm103 it is a new fused opcode, `LDTM.STAT` (`0x15ee`), rather than an
ordinary `LDTM` plus ALU reduction; see `notes/sm103/instr/ldtm_stat.md`.

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

## Dynamic B200 validation (2026-09-17)

The hand-written sm100a allocator cubin now executes this complete sequence on
a Modal B200:

```sass
R2UR UR10, R5                 // allocated TMEM column address
STTM tmem[UR10], R16
FENCE.VIEW.ASYNC.T            // tcgen05.wait::st, claims SB3
LDTM R17, tmem[UR10]          // waits SB3, then claims SB3
...
STG.E ..., R17                // waits SB3 = tcgen05.wait::ld
```

Lane 0 stores and reads back `0x12340000`; the GPU result is exact.  An nvcc
reference kernel using the same `.32x32b.x1` sequence was also run on B200 and
returned `0x12340000 + lane` for all 32 lanes.  This confirms dynamically that
the default form transfers one independent 32-bit word per lane and that no
standalone load-side wait opcode is required.

A second hand probe stores `{0x12340000+lane, 0x56780000+lane}` with
`STTM.x2`, then recovers the values using two separate loads at
`tmem[base+0]` and `tmem[base+1]`.  Both values match.  Thus the signed
immediate is in **TMEM-column units** (not bytes), and `.32x32b.x2` spans two
consecutive columns.

#### Cross-layout tagged-data tomography (2026-09-19)

A bidirectional tagged probe now writes a unique `(source_thread, source_reg)`
value through one layout and reads it through another.  This establishes that
the apparent checkerboard in the 16-datapath forms is an exact bit permutation
between thread/register coordinates and the canonical `.32x32b` `(row,column)`
view.  It is not necessary to invoke a bank hash to explain the permutation.

Let output thread `t = 4q + p`, and let `j` be the destination-register index
of the 16-datapath LDTM.  The complete mappings are:

```text
.16x64b.x2:   row = q + 8*(p & 1)
              col = ((p >> 1) & 1) + 2*j            j=0..1

.16x128b.x4:  row = q + 8*(j & 1)
              col = p + 4*(j >> 1)                  j=0..7

.16x256b.x1:  row = q + 8*(j >> 1)
              col = 2*p + (j & 1)                   j=0..3
```

The reverse STTM→canonical experiments produce the exact inverse maps.  All
three shapes access canonical TMEM rows **0--15 only**; rows 16--31 are left
untouched.  Their canonical column footprints are respectively 4, 16, and 8
columns—not 2, 8, and 4 as a naïve `32 lanes * register count` byte count would
suggest, because the physical layout has only 16 datapaths.

The split forms have an even simpler meaning:

```text
t0_t15:    active register lanes t=0..15   -> row=t,    col=j
t16_t31:   active register lanes t=16..31  -> row=t-16, col=j
```

Both forms address the **same TMEM rows 0--15** at the supplied TMEM column.
They select which half of the warp carries register data; `t16_t31` is not an
access to TMEM rows 16--31.  nvcc's second half uses
`tmem[base + immHalfSplitOffset]`, so the two thread halves normally land in
different column regions.  Issuing both at the same address makes the second
store overwrite the first, exactly as the mapping predicts.

In bit terms, the visible checkerboard is a routing network: canonical row bit
3 comes from thread bit 0 (`16x64b`), register bit 0 (`16x128b`), or register
bit 1 (`16x256b`), while low column bits are supplied by the complementary
thread/register bits.  This is strong evidence for a structured 16-datapath
transpose, but it remains logically distinct from the number or selector of
physical SRAM banks.

Probe: `tests/asm_construct/probe_sm100_tmem_layout_tomography.py`; the Modal
runner's `--tomography-regs` mode decodes tags as `source_thread:source_reg`.

The hand assembler accepts `tmem[URx+imm]` directly; exact nvcc-vector
round trips live in `tests/asm_construct/test_tcgen05_ldst_sm100.py`.

### MIO/LSU interaction probe

The latency dump classifies `LDTM` in `udp_pipe`, while `LDS` and `SHFL` are in
`mio_pipe`; it also subtracts `LDTM_STTM_OP` from the ordinary UDP subset as a
special class.  A B200 mixed-stream probe confirms that this is a real resource
separation, not merely a logical performance-counter label.

Each stream executes 128 groups of four operations (512 of each instruction).
LDTM loads four distinct TMEM columns and performs `tcgen05.wait::ld` per group;
the paired MIO result is consumed so ptxas cannot delete it.  Median SM-clock
intervals are:

| stream | cycles |
|---|---:|
| LDTM only | 2669 |
| LDS only | 6060 |
| SHFL only | 7205 |
| LDTM + LDS, 512 each | 3873 |
| LDTM + SHFL, 512 each | 6950 |

Neither mixed interval approaches the sum (8729 / 9874 cycles).  In particular,
the SHFL mixture is essentially just the slower SHFL stream.  The LDS mixture
is even faster than isolated LDS because the inserted TMEM work/waits give
ptxas a better latency-hiding schedule; it must not be interpreted as a
negative-cost LDTM.  The robust conclusion is that LDTM neither enters the
ordinary MIO admission queue nor consumes the LDS/SHFL LSU/exchange backend.
It uses UDP-side admission plus a distinct TMEM load path.

Probe: `tests/tcgen05_ldst_mio_runtime.cu`.

### B200 bandwidth

`tests/tcgen05_ldst_bandwidth.cu` measures `.32x32b.xN` with 256 steady-state
groups.  One LDTM collective moves `32 lanes * N * 4 = 128N` bytes from one
TMEM chunk into one warp.  The table below uses four independent LDTM
instructions per completion group, so every row contains 1024 collectives;
cycles are the warp-local `clock64` interval.

| form | cycles | cycles/collective | payload B/cycle/chunk |
|---|---:|---:|---:|
| `.x1` | 5259 | 5.136 | 24.92 |
| `.x2` | 5323 | 5.198 | 49.25 |
| `.x4` | 6028 | 5.887 | 86.98 |
| `.x8` | 8012 | 7.824 | 130.88 |
| `.x16` | 12108 | 11.824 | 173.20 |

Increasing the completion group from four to eight `.x16` operations gives
22809 cycles for 2048 collectives, or **183.89 B/cycle/chunk**.  This is the
best directly observed load bandwidth, but is still a batched, completion-safe
figure rather than a claim that 183.89 B/cycle is the physical datapath width.
A two-point `cycles = operations*A + groups*B` fit to the x16 batch-4 and
batch-8 cases gives `A = 10.45 cycles/collective` and an asymptote near
**196 B/cycle/chunk**; treat that value as a microarchitectural estimate.

Four warps were then assigned to the four TMEM chunks of one CTA.  Their x16
batch-8 intervals were 22809, 22820, 22819 and 22818 cycles: effectively
identical to the single-warp interval, with no measurable cross-chunk
slowdown.  Counting all four simultaneous payloads gives **735.2 B/cycle per
SM** (using the slowest warp), almost exactly 4x the per-chunk result.  The same
no-slowdown result holds at `.x1` and `.x4`.  Thus the measured load service is
replicated per subcore/TMEM chunk rather than passing through one SM-wide
LDTM data port.

With eight warps (two per subcore/chunk), the x16 batch-8 intervals rise to
35348--35383 cycles.  The two warps together deliver **237.1 B/cycle per
chunk**, or **948.3 B/cycle per SM**.  A second warp therefore fills much of
the single-warp bubble and brings the shared per-chunk limit close to 256
B/cycle.  This is stronger evidence for a 256 B/cycle service quantum than the
single-warp extrapolation, but by itself cannot distinguish the TMEM read path
from the final RF writeback path.

#### Strictly scheduled raw SASS

The ptxas result above is not the hardware limit.  A fully hand-assembled
kernel was built from `tests/asm_construct/tcgen05_alloc_sm100.sass`, so the
TMEM allocator/deallocator ABI is retained without passing the load stream
through PTX.  It uses:

- one allocated 32-column tile and a permanent `UR10` address;
- 4/6/8/12 `LDTM.x16` operations per batch, all reading the same tile;
- up to twelve independent 16-register destination groups (`REGCOUNT=224`);
- explicitly assigned SB0--SB5 completion scoreboards;
- four batches per loop iteration, 128 batches total;
- a final `CS2R` that waits every claimed scoreboard before taking the end
  timestamp.

Each x16 load transfers 2048 bytes per warp/TMEM chunk.  The zero-jitter B200
results are:

| loads/batch | scoreboard assignment | total cycles | cycles/load | B/cycle/chunk |
|---:|---|---:|---:|---:|
| 4 | 4 SB, one load each | 4118 | 8.043 | 254.63 |
| 6 | 6 SB, one load each | 6166 | 8.029 | 255.09 |
| 8 | 6 SB, uneven 2/2/1/1/1/1 | 8468 | 8.270 | 247.66 |
| 8 | 4 SB, two loads each | 8214 | 8.021 | 255.31 |
| 12 | 6 SB, two loads each | 12310 | 8.014 | 255.54 |

Every balanced case satisfies exactly:

```text
cycles = 22 + 8 * total_LDTM
```

Thus the sustained per-subcore service rate is **one LDTM.x16 every 8 cycles =
256 B/cycle**.  This is no longer an extrapolation.  The two deliberately bad
assignments expose a separate completion-scheduling effect.  The uneven
eight-load case and a four-load case forced onto only two scoreboards both add
exactly `2*(128-1) = 254` cycles: a two-cycle bubble at every boundary between
successive batches.  At least three suitably balanced completion streams are
enough to hide it; four or six also reach the same 256 B/cycle ceiling.

This also answers the PTX-compatibility question more precisely.  LDTM has no
SHIFT-like execution-group envelope, but ptxas register liveness, destination
reuse, consumers, and completion-SB assignment held the earlier single-warp
stream below peak.  Direct SASS removes those scheduling artifacts.

Generator: `tests/asm_construct/probe_tcgen05_ldtm_bare_schedule.py`.

#### 与 UTCHMMA accumulator RMW 的读端竞争

为判断 tensor-core accumulate 是否通过上述普通 LDTM 读口取得 D，warp 1
使用同一套严格调度：63 条 `LDTM.x16` 轮转三组 16-register destination 和
SB0--SB2，每次重用前等待对应 scoreboard。每条读取 2048 B，纯服务时间应为
`63*8 = 504` cycles；连同固定首尾开销，20 次 LDTM-only launch 均精确为
**520 cycles**。

重新去掉 ptxas active-thread-group wrapper 后，整个 warp 直接发射裸 U-path
指令，并在 CTA BAR 前显式 `WARPSYNC.ALL`。短窗口中四条 M128N128
BF16→FP32 accumulate UTCHMMA 使用
`collector::a::fill/use/use/lastuse`；长窗口则扩展为 32 条
`fill/use.../lastuse`，最后都只用一条 UTCBAR（mbarrier count=1）提交。

| workload | UTCHMMA | LDTM |
|---|---:|---:|
| LDTM only | -- | **520** |
| 4×UTCHMMA only | **385** | -- |
| 4×UTCHMMA RMW + 63×LDTM.x16 | **385** | **520** |
| 32×UTCHMMA only | **2177** | -- |
| 270×LDTM.x16 only | -- | **2176** |
| 32×UTCHMMA RMW + 270×LDTM.x16 | **2177** | **2177** |

另一个数据正确性探针直接读取正在执行的 accumulator。shared A/B 均为 BF16
1.0；producer warp 在一个 epoch 内发出一条 overwrite 和 64 条 accumulate，
observer warp 连续 LDTM.x1 同一 D 列。最终 UTCBAR 到达以前，LDTM 已依次读到
`0, 16, 32, ..., 1040`；observer 放在不同 subcore（warp 1）或与 producer
同 subcore（warp 4）结果相同。这证明 LDTM 看到的不是尾部 commit 才整体发布的
快照：UTCHMMA 中间结果持续退休到普通 TMEM 可见状态。因而下面按每条 MMA
计算的逻辑流量不能用“整个 D 一直驻留到尾部”全部消掉，尽管短生命周期的
microtile forwarding/write-combine 仍然可能存在。

单条 M128N128 UTCHMMA 的追赶实验也给出了 LDTM 自身粒度信息。D 从 0 overwrite
为 16.0f 时，`LDTM.x16` 可在一条 MMA 尚未完成时返回 `4 old + 12 new`，且该
四列裂口随 LDTM 起始列平移，说明 x16 至少包含可分时服务的四列 beat。三条
背靠背 `LDTM.x2` 可返回 `old pair -> new pair -> new pair`；无论从偶数列还是
奇数列开始，单个 x2 内尚未观察到一新一旧。因此 x2 很可能以二列 transaction
提供相干观察，但这也意味着它可能恰好遮蔽 UTCHMMA 更细的写入次序，不能单凭
该现象证明 tensor 写回的物理原子单元就是二列。三条 outstanding x1 的正序
`col0,1,2` 与逆序 `col2,1,0` 都返回 `old,new,new`，进一步证明相邻列裂口可以
只是连续请求跨过可见性切换，而不是空间扫描方向。完整实验和跨 subcore 相位对照见
`utchmma.md` 的“单条 N128 指令的中间可见性”。

32 条 MMA 对每个 chunk 读取 `32*16 KiB = 512 KiB` accumulator，平均
**240.8 B/cycle/chunk**；270 条 LDTM.x16 读取 540 KiB，平均
**254.1 B/cycle/chunk**。两者合计约 **494.9 B/cycle/chunk**，并发后各自时间
仍逐周期不变。若共用单个 256-B/cycle/chunk 读后端，combined 至少应接近
两段服务时间之和，而不是与二者的最大值相同。

结合 `sttm.md` 中同样无竞争的饱和写侧结果，可以确定 tensor RMW 在普通
LDTM/STTM admission 之后仍有独立的**逻辑 service capacity**；但实验尚不能
唯一推出物理上另有一对 R/W 口。`clock64` 计的是 SM 时钟：若 TMEM array
以 2x SM 频率运行、端口 double-pumped，或每个 SM cycle 有两个内部 service
phase，同一个物理阵列也能在本实验中表现得像独立 RMW datapath。新长窗口已
把可见合计读压力提高到约 **495 B/SM-cycle/chunk**，因此任何共享后端都必须
至少接近 512 B/SM-cycle；实验仍恰好没有超过一个合理的 512-B/cycle 2x
后端。

因此“专用 RMW 口”是当前最简模型，而“更高 TMEM 时钟/多相单阵列”仍是等价
候选。单条 tensor stream 与一个已饱和普通 LDTM port 的渐近和正好逼近而不会
明显超过 512 B/cycle，因此区分二者更适合改变 SM/TMEM 的相对时钟，或寻找
第三个独立 read producer。

这个第三压力源随后由同 chunk 的 STTM 流提供。519 条 LDTM.x16 与两个 warp
各 512 条 STTM.x8 的总普通流量为 2,111,488 B，8270-cycle 公共窗口对应
255.32 B/cycle；因此普通 LDTM/STTM 实际共用一条约 256-B/cycle 的**双向**
service path。并发 128 条 UTCHMMA 后，普通窗口增至约 8528 cycles（约 3%），
而 MMA 保持 8321 cycles。accumulate 与 overwrite 的结果逐周期相同，故该
小信号更像 tensor/ordinary 的固定仲裁或 overwrite 仍保留物理 RMW，不能只按
逻辑 D-read 字节数解释。完整 duplex 数据见 `sttm.md`。

把 LDTM 移到另一个 chunk 后，LDTM 与 STTM 不再相加：control 分别约
4168 和 4096 cycles，公共窗口约 4200；再加入 128 条 UTCHMMA 后仅变成
4169 和 4108。故 256-B/cycle 双向限制属于 per-chunk/同-subcore 普通 TMEM
path，而不是 SM-wide UDP 总入口。

Probe: `tests/asm_construct/probe_sm100_utchmma_sttm_rmw.py` (B200,
2026-09-18).

#### TMEM column granularity and alignment

The raw generator was extended so that vector width and starting TMEM column
can be varied without changing the instruction count, destination registers,
scoreboard assignment, or loop schedule.  Each test below contains 1536
loads.  The steady-state results are:

| LDTM width | even start column | odd start column | even B/cycle | odd B/cycle |
|---:|---:|---:|---:|---:|
| x1 | 2534 cycles | 2534 cycles | 77.59 | 77.59 |
| x2 | 2534 cycles | 3373 cycles | 155.18 | 116.58 |
| x4 | 3373 cycles | 4630 cycles | 233.16 | 169.86 |
| x8 | 6166 cycles | 7702 cycles | 255.09 | 204.22 |
| x16 | 12310 cycles | 13846 cycles | 255.54 | 227.19 |

All tested even columns (0, 2, 4, 8, and 16, subject to vector bounds) are
equivalent.  The x16 odd starts 1, 3, 7, and 15 are likewise identical; odd
columns 1 and 31 are also equivalent for x1.  Repeatedly
reading one column, alternating 0/1, 0/2, 0/8, or 0/16, and walking linearly
through columns do not expose an additional history-dependent conflict.

For x8 and x16, where the TMEM service path rather than narrow-instruction
admission is the limiting factor, the result is exact:

```text
service cycles/load = ceil((vector_columns + (start_column & 1)) / 2)
total cycles         = 22 + sum(service cycles for every load)
```

Thus the visible read datapath consumes **one aligned two-column sector per
cycle**.  One column carries 32 lanes x 4 bytes = 128 bytes, so a sector is
256 bytes.  An even-aligned x16 touches eight sectors and sustains 256 B/cycle;
an odd-aligned x16 touches nine sectors and necessarily falls to 227.2 B/cycle.
The mixed x16 streams confirm additivity: all-even is 12310 cycles, all-odd is
13846, and a 50/50 even/odd stream is exactly 13078.

This is an externally visible form of column banking/granularity, but it does
not behave like a conventional persistent bank conflict between successive
requests.  In particular, an even-aligned x8 stream repeatedly hits the same
four two-column sectors and still reaches 255.1 B/cycle; moving alternate
requests to other sectors does not improve it.  The observed penalty is the
extra aligned sector touched *within a misaligned vector instruction*, not two
queued LDTMs contending because their column numbers hash to the same bank.
The narrower x1/x2/x4 streams hit an independent admission/completion floor,
so their absolute rates should not be used to infer the number of physical
TMEM SRAM banks; they nevertheless preserve the same parity boundary effect
once a request spans more than one sector.

A later equal-byte layout matrix supplies the missing conflict evidence from
the 16-datapath forms.  `LDTM.16dp256bit.x1` and
`LDTM.16dp128bit.x4` both settle at about eight cycles/op even though the
former moves only half as many bytes.  The symmetric STTM experiment removes
LDTM scoreboard depth as a confounder and shows that x256's same-parity
per-phase column set has an exact two-way bank penalty.  Thus the visible bank
selector contains column bit 0; whether row-half XORs that bit remains open.
See "Intra-instruction bank conflict from 16-datapath layouts" in `sttm.md`.

A corrected exhaustive modifier sweep also executes all **90** LDTM
layout/NUM/bit-80 combinations (45 layouts with and without `PACK16BIT`).  For
1536 serial scoreboard-waited loads, `PACK16BIT(layout,xN)` lands on the same
wide-form service step as `nopack(layout,x2N)`: it doubles the TMEM columns
consumed while retaining the encoded destination-register span.  The full
ladder is `32dp32bit`/split-half, `16dp64bit`, `16dp128bit`, `16dp256bit` =
approximately `NUM/2`, `NUM`, `2*NUM`, `8*NUM` service cycles without PACK,
and twice those values with PACK.  The persistent jump from `2*NUM` to
`8*NUM` is the same-parity-column penalty seen by STTM.  Absolute small-N
totals include the LDTM admission/completion floor and should not be read as
pure SRAM cycles.  Probe:
`tests/asm_construct/probe_sm100_tmem_modifier_sweep.py`.

#### Destination RF-bank discrimination

Three additional probes tested whether the limit is specifically the two-bank
RF writeback (`2 * 1W * 128 B/cycle`):

1. A hand SASS stream maps 2048 `LDTM.x1` destinations to all-even, all-odd,
   or alternating registers.  All three take exactly **9216 cycles**.  This is
   not evidence against banking: `.x1` completes only once per 4.5 cycles and
   cannot saturate even one 128 B/cycle write port.
2. An nvcc cubin was patched in place (preserving all TMEM metadata) so every
   `.x1` destination cycles through six even, six odd, or six alternating
   registers with identical WAW distance.  From two through eight warps per
   subcore there is still no stable parity penalty.  Even at eight warps the
   aggregate payload is only about **57 B/cycle/subcore**, still far below a
   single bank's proposed 128 B/cycle ceiling.
3. An `LDTM.x16` was followed by eight FFMA writes, either all-even or
   alternating.  Both layouts have identical timing at every tested phase.
   The apparent FFMA penalty is also present, cycle-for-cycle, when LDTM is
   replaced by a NOP (gap 0: NOP stream 9727 cycles, either FFMA stream 11264),
   so it is fixed-pipe self-cost rather than demonstrated LDTM/RF contention.

Conclusion: the raw-SASS experiment now establishes an exact 256 B/cycle
per-subcore service ceiling, but does not by itself locate that ceiling at RF.
Wide LDTM destinations are necessarily consecutive and balanced across banks,
while narrow LDTM is admission-bound before it can stress one bank.  The
fixed-pipe interference experiment below argues that this ceiling is not
ordinary fixed-pipe writeback arbitration.

#### Independently phase-aligned fixed-pipe writer

That missing test was subsequently run with warp 0 timing one `LDTM.x16` plus
its write-scoreboard wait, while warp 4 (the same subcore/scheduler mapping)
issued eight consecutive FFMA writes.  A warp-1 FFMA stream supplied the
different-subcore control.  The first nvcc version was not clean enough:
ptxas interleaved `VIADD` operand construction with the FFMA operations.
`sassdbg.lift` was therefore used to locate the contender basic block and an
equal-length replacement was assembled and patched into the original nvcc
cubin.  This preserves the loader-injected TMEM allocator/capmerc metadata;
rebuilding the lifted function without that metadata faults at runtime.

The replacement is exactly eight 1E+1O FFMA instructions writing alternating
register banks, followed by NOP padding.  Moving this burst through all 14
available issue slots produced no phase-dependent LDTM delay.  After the four
repeatable first-context warm-up samples (25 cycles), every phase settles at
**24 cycles**; the same-subcore NOP and different-subcore FFMA controls are
25 cycles in their corresponding fresh contexts.  Occasional first samples
are 26 cycles, but no aligned peak repeats.

This rules out a model in which fixed-pipe writes back-pressure the observed
LDTM completion and make its scoreboard wait longer.  It does **not** by itself
prove two physically separate RF arrays or write ports: an arbiter could give
LDTM priority and delay the FFMA side, and `tcgen05.wait::ld` could conceivably
release at a result queue before final RF deposition.  The result nevertheless
makes “the measured x16 ceiling is simply the ordinary fixed-pipe RF write
port” substantially less likely.  A symmetric experiment that times a
late-collected FFMA result is needed to distinguish independent ports from
strict LDTM priority.

Probe: `tests/tcgen05_ldst_bandwidth.cu` (B200, 2026-09-17).
Bank probes: `tests/asm_construct/probe_tcgen05_ldtm_rf_banks.py`,
`tools/patch_ldtm_bank_cubin.py`, and
`tests/asm_construct/probe_tcgen05_ldtm_rf_storm.py`.  The two-warp source and
metadata-preserving clean-block patcher are
`tests/tcgen05_ldtm_fixed_rf_conflict.cu` and
`tools/patch_tcgen05_ldtm_fixed_rf.py`.

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
- Is the `LDT`/`SIZE_ldt` ALTERNATE ever emitted by any front-end path, or is it
  purely an assembler alias?
- `pack`/`texunpack` bit [80] shares a name with the legacy texture-unpack
  control bit — confirmed here to encode `.pack::16b` (=1).
