# STTM / STT — tensor-memory (TMEM) store  → PTX `tcgen05.st`

**Opcode mnemonic:** `STTM` (and alt `STT`) = `0b1100111101101` (0x19ed, 6637)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TMEM` (=40) | **MEM_SCBD_TYPE:** `BARRIER_INST`

New on sm100 (Blackwell). The store mirror of `LDTM` — the SASS realization of
PTX **`tcgen05.st`**, an asynchronous warp-collective store from registers into
5th-gen TensorCore **Tensor Memory (TMEM)**. See `ldtm.md` for TMEM background;
this note focuses on the store-specific differences.

## Semantics
`STTM tmem[URc + Sc_offset], Rb` asynchronously copies a register vector starting
at `Rb` into the TMEM block based at `URc + Sc_offset`, collectively across the
warp. The register-vector width = f(`layout`, `num`) per PTX Table 53 (identical
to the LDTM load table).

`INST_TYPE_DECOUPLED_RD_SCBD` + `dst_wr_sb` pinned to `7` (none): the store has
**no write scoreboard** (it writes TMEM, not registers) and its only dependency
handle is the **read scoreboard** `src_rel_sb` it releases when the source
registers have been consumed. This is the exact **inverse** of LDTM, which pins
`src_rel_sb=7` and uses `dst_wr_sb`. Async completion (TMEM write visibility) is
ordered separately — PTX `tcgen05.wait::st`, which lowers to `FENCE.VIEW.ASYNC.T`
(see below), not a scoreboard on this instruction.

## Variant overview
| Class | Kind | Opcode | Distinguisher |
|-------|------|--------|---------------|
| `sttm_` | CLASS | 0x19ed | full `layout`×`num` matrix, optional `.unpack::16b` |
| `stt_` | ALT of `stsm_…` | 0x19ed | `layout` pinned `32dp32bit`; `size`∈{32,64,128} |

Like `LDT`, the `STT`/`SIZE_ldt` ALTERNATE is **never emitted** by ptxas (every
`tcgen05.st` shape → `STTM`); it is an assembler-only spelling parented under the
Hopper `STSM` (shared-memory matrix store) class tree.

## Modifiers (STTM)
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `layout` | `LAYOUT` | [87]∥[82:81] | TMEM access shape (same map as LDTM) |
| `num` | `NUM` | [85:83] | repeat factor `x1..x128` → sets `ISRC_B_SIZE` |
| `expand` | `EXPAND16BIT` | [80] | `noexpand16bit`(0) / `EXPAND16BIT`(1) = PTX `.unpack::16b` |

`LAYOUT` / `NUM` value-maps are identical to LDTM (see `ldtm.md`).
`.32x32b`(=2) and `.x1`(=0) are the defaults and are elided by cuobjdump.

The one modifier difference vs LDTM: bit [80] carries **`EXPAND16BIT`**
(`.unpack::16b`, split a 32-bit reg into two 16-bit columns) instead of `PACK`.
Both ride the same legacy `texunpack` control bit.

## Bit layout (128-bit, STTM)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = VarLatOperandEnc(src_rel_sb)  ← read-reg release barrier
[112:110]           dst_wr_sb    = 7  (pinned: no write scoreboard — store)
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x19ed
[87]∥[82:81]        layout       (3b, MSB at 87, interleaved with num)
[85:83]             vecidx       = num
[80]                texunpack    = expand   (.unpack::16b)
[79:72]∥[63:40]     Sb_offset    = 32-bit signed TMEM offset (= Sc_offset; split field)
[71:64]             Ra_URc       = URc  (uniform TMEM base address register)
[39:32]             Rb           = data source base register
[15]                Pg_not ; [14:12] Pg = @UPg predicate (UniformPredicate)
```
Difference from LDTM in operand placement:
- **Data** register `Rb` sits in [39:32] (LDTM's `Rd` was [23:16]; STTM leaves
  [23:16] unused since it has no register *dest*).
- **TMEM address** register `URc` is in [71:64] (`Ra_URc` slot). LDTM put its
  base `URb` in [39:32]; STTM needs [39:32] for the data reg, so the address reg
  moves up to [71:64].
- Scoreboard roles swap: `src_rel_sb` active / `dst_wr_sb` pinned (LDTM inverse).

## ISRC_B_SIZE (register-vector width)
`ISRC_B_SIZE` (bits) = 32 × (register count), following PTX Table 53 — the same
(num, layout) sum-of-products used by LDTM's `IDEST_SIZE`. CONDITIONS enforce the
NA cells, N-register alignment on `Rb`, and range checks (all keyed on `Rb`
instead of `Rd`).

## Cross-comparison: STTM vs LDTM
| aspect | LDTM (`tcgen05.ld`) | STTM (`tcgen05.st`) |
|--------|--------------------|--------------------|
| opcode | 0x19ee | 0x19ed |
| direction | TMEM → registers | registers → TMEM |
| INST_TYPE | `DECOUPLED_WR_SCBD` | `DECOUPLED_RD_SCBD` |
| active scoreboard | `dst_wr_sb` [112:110] | `src_rel_sb` [115:113] |
| pinned scoreboard | `src_rel_sb`=7 | `dst_wr_sb`=7 |
| GPR operand | dest `Rd` [23:16] | source `Rb` [39:32] |
| TMEM addr reg | `URb` [39:32] | `URc` [71:64] |
| pack modifier [80] | `PACK` (`.pack::16b`) | `EXPAND16BIT` (`.unpack::16b`) |
| completion wait | `tcgen05.wait::ld` (scoreboard) | `tcgen05.wait::st` → `FENCE.VIEW.ASYNC.T` |

## Latency (sm100_latencies.txt)
`STTM`/`STT` are members of `LDTM_STTM_OP` (line 81) together with `LDTM`/`LDT`.
Its GPR dependency row is a uniform **`1`** cycle (issue handoff, not TMEM access
latency); the op is excluded from `UDP_subset` fixed-latency timing (line 218)
and handled as a scoreboard-gated async op. See `ldtm.md` for the full table.

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/sttm_test.cu` → `tests/sttm_test.cubin`. Decoder:
`tools/decode_sttm.py` — all 8 round-trip (**ALL PASS**).

| Disassembly | Lo64 / Hi64 | layout | num | exp | Rb | URc | Soff | src_sb |
|-------------|-------------|:------:|:---:|:---:|:--:|:---:|:----:|:------:|
| `STTM tmem[UR6], R4` | `…79ed` / `0041e20008040006` | 2 `32dp32bit` | 0 `x1` | 0 | R4 | UR6 | 0 | 0 |
| `STTM.x2 tmem[UR6], R4` | `…79ed` / `0081…080c0006` | 2 | 1 `x2` | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp64bit.x2 tmem[UR6], R4` | `…79ed` / `080e0006` | 3 | 1 | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp128bit.x4 tmem[UR6], R4` | `…79ed` / `08100006` | 0 | 2 `x4` | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp256bit tmem[UR6], R4` | `…79ed` / `08020006` | 1 | 0 | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp128bit.EXPAND16BIT tmem[UR6], R4` | `…79ed` / `08010006` | 0 | 0 | 1 | R4 | UR6 | 0 | 0 |
| `STTM.16dp32bit_t0_t15.x2 tmem[UR6], R4` | `…79ed` / `08880006` | 4 | 1 | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp32bit_t16_t31.x2 tmem[UR6+0x10], R4` | `…79ed`(lo bit set) / `088a0006` | 5 | 1 | 0 | R4 | UR6 | 16 | 0 |

Confirmed facts:
- Operand order in the disassembly is `tmem[...], Rb` (dest TMEM first, then data
  register) — the natural store spelling.
- Address reg encodes in [71:64] (`Ra_URc`), data reg in [39:32] (`Rb`) — the
  swap vs LDTM verified.
- `req_bit_set` (wait mask) carries the RAW dependency on the producer that wrote
  the source regs (e.g. `req=0x4`/`0x8` on the first two — waiting on SB2/SB3
  set by the input loads); `src_rel_sb=0` releases scoreboard SB0 on reg read.
- `EXPAND16BIT` (bit[80]=1) verified from `.unpack::16b`.

### tcgen05 store-side lowering (same kernel)
| PTX | SASS |
|-----|------|
| `tcgen05.st.sync.aligned.32x32b.x1.b32 [ta], {r0}` | `STTM tmem[URc], Rb` |
| `tcgen05.st.sync.aligned.16x128b.x4.b32 [ta], {r0..r7}` | `STTM.16dp128bit.x4 tmem[URc], Rb` |
| `…16x128b.x1.unpack::16b… [ta], {r0,r1}` | `STTM.16dp128bit.EXPAND16BIT tmem[URc], Rb` |
| `…16x32bx2.x2… [ta], 16, {r0,r1}` | `STTM.16dp32bit_t0_t15/_t16_t31.x2 tmem[URc+0x10], Rb` (`immHalfSplitoff`→`Sc_offset`) |
| `tcgen05.wait::st.sync.aligned` | `FENCE.VIEW.ASYNC.T` |

## Open questions
- The `STT`/`SIZE_ldt` ALTERNATE is present in the ISA description but has not
  been observed from ptxas.
- Exact ordering guarantees of `FENCE.VIEW.ASYNC.T` for `tcgen05.wait::st` vs the
  `src_rel_sb` read barrier — the fence orders the async TMEM write visibility,
  the scoreboard only orders source-register reuse.

## Dynamic B200 validation (2026-09-17)

A hand-assembled allocator/STTM/LDTM/deallocator kernel now runs successfully
on B200.  For `.32x32b.x1`, all lanes execute `STTM tmem[UR10], R16`, followed
by `FENCE.VIEW.ASYNC.T`; the subsequent `LDTM` observes the stored lane value.
This independently confirms the direction, collective 32-lane behavior, and
the separation between STTM's source-release scoreboard and the store-visibility
fence.

The `.32x32b.x2` probe preserves two different per-lane values, and two
subsequent `.x1` loads at offsets 0 and 1 recover them independently.  This
establishes that STTM `Sc_offset` uses TMEM-column units and that `.x2` writes
two consecutive columns.

### MIO/LSU interaction probe

Static classification places STTM in the special UDP-side `LDTM_STTM_OP`
class, not `mio_pipe`.  On B200, 512-operation streams measured:

| stream | cycles |
|---|---:|
| STTM only | 2126 |
| LDS only | 6060 |
| SHFL only | 7205 |
| STTM + LDS, 512 each | 3460 |
| STTM + SHFL, 512 each | 6949 |

The TMEM stores are issued in groups of four followed by `tcgen05.wait::st`.
The mixed times are nowhere near the serial sums (8186 / 9331 cycles); the SHFL
mixture is almost exactly bounded by SHFL alone.  As with LDTM, the surprisingly
short LDS mixture reflects instruction scheduling and latency hiding around the
TMEM waits, not acceleration of LDS.  It nevertheless rules out a shared
throughput bottleneck at the ordinary MIO queue, LSU pipe, or SHFL/LDS exchange
path for this workload.  STTM uses UDP-side admission and its own TMEM store
backend.

Probe: `tests/tcgen05_ldst_mio_runtime.cu`.

### B200 bandwidth

The bandwidth probe issues `.32x32b.xN` in completion-safe batches.  Each STTM
collective transfers `128N` bytes from a warp into its TMEM chunk.  With four
stores followed by `tcgen05.wait::st`, 256 groups (1024 collectives) measure:

| form | cycles | cycles/collective | payload B/cycle/chunk |
|---|---:|---:|---:|
| `.x1` | 4156 | 4.059 | 31.54 |
| `.x2` | 4219 | 4.120 | 62.13 |
| `.x4` | 4986 | 4.869 | 105.15 |
| `.x8` | 7042 | 6.877 | 148.90 |
| `.x16` | 11154 | 10.893 | 188.02 |

Eight `.x16` stores per fence improve the directly observed result to 19614
cycles for 2048 collectives, or **213.84 B/cycle/chunk**.  Fitting the batch-4
and batch-8 data separates an estimated 8.26 cycles of per-store service from
the per-group fence/loop cost, predicting an asymptote of **247.9
B/cycle/chunk**.  This strongly suggests a 256 B/cycle physical store path,
although 256 B/cycle remains an inference rather than a directly attained
number.

With four warps simultaneously targeting the four TMEM chunks, the batch-8
x16 intervals were 19602, 19613, 19612 and 19611 cycles.  There is no visible
cross-chunk serialization.  The aggregate directly observed throughput is
**855.4 B/cycle per SM**, essentially 4x the single-chunk result; `.x1` and
`.x4` show the same scaling.  Together with the MIO/LSU separation result,
this supports one independently serviced TMEM load/store datapath per
subcore/chunk, with UDP providing instruction admission rather than a shared
SM-wide bulk-data path.

At eight warps (two per subcore/chunk), intervals are 33713--33732 cycles.
Each subcore now sustains **248.7 B/cycle** across its two warps, or **994.7
B/cycle per SM**.  This directly approaches the inferred 256 B/cycle/chunk
store limit and confirms that the lower single-warp number was partly an
insufficient-outstanding-work effect.

An independently completed UTCCP stream does not consume this store bandwidth.
With `STTM.x8` held at 251.99 B/cycle in chunk 0, four concurrent UTCCP
producers add 63.90 B/cycle CTA-wide (15.98 B/cycle into each chunk).  STTM's
interval changes only from 66580 to 66605 cycles, while UTCCP changes from
131277 to 131299 cycles.  Targeting the same columns 0--7 or disjoint columns
8--15 gives identical results.  Thus UTCCP does not serialize through STTM's
ordinary 256 B/cycle chunk write port; see `utccp.md` for the full matrix and
the raw-SASS producer-rate probe.

Raw SASS does reveal a distinct ordering rule that must not be mistaken for
write-port contention.  With UTCCP and STTM interleaved by one execution group,
a sufficiently deep stream targeting the same columns can deadlock if
`FENCE.VIEW.ASYNC.T` precedes the UTCCP `UTCBAR`/mbarrier completion.  Changing
STTM to columns 8--15, or completing UTCCP before executing the STTM fence,
makes the same 32-batch stream finish in 45249 cycles.  Thus a simulator needs
both independent UTCCP/STTM data ingress and an address/order-aware completion
dependency; treating the fence as a blind drain of only an isolated STTM FIFO
is insufficient.

UTCCP multicast provides a stronger port-separation test.  Four normalized
warpx2 or warpx4 producers reach about 122 B/cycle CTA-wide, or 30.5
B/cycle/chunk, on the UTCCP destination side.  Running that stream beside
STTM.x8 changes STTM from 66580 to 67296 cycles; same-column and disjoint-column
cases are identical.  Producer warps on other schedulers are unchanged, while
the one producer sharing a scheduler with the STTM warp pays a fixed ~5.7k
issue-cycle penalty.  Hence the small mixed slowdown is front-end scheduling,
not serialization of approximately 30.5 + 250 B/cycle through one 256 B/cycle
TMEM write datapath.

This physical-port conclusion is now provisional.  A clean builtin-allocator
`.warpx4` control reaches about **64 B/cycle/chunk** without STTM (four warps:
1024 operations each in 33388 cycles; eight warps: 1024 each in 66677 cycles),
and does not approach the nominal 128 B/cycle/chunk.  The clean mixed case must
measure both streams independently: unchanged STTM alone would also be
consistent with a shared array write port that gives STTM priority and
throttles UTCCP.  See the rebaseline in `utccp.md`.

The clean mixed repeat rules out that priority-only explanation.  Four UTCCP
warps remain at 63.7 B/cycle/chunk while two same-chunk STTM.x8 warps remain at
245.8 B/cycle/chunk, for about **309.5 B/cycle/chunk** of concurrent logical
traffic.  Overlapping and disjoint columns have identical intervals.  The
result proves independent ingress capacity, but not necessarily two SRAM
write ports: a single banked array sink of at least 310 B/cycle/chunk behind a
256 B/cycle STTM ingress and a 64 B/cycle UTCCP ingress explains the data.  In
particular, the STTM asymptote must no longer be identified directly with the
deepest TMEM-array write bandwidth.

With every chunk saturated by two STTM warps, standalone STTM reaches about
1001 B/cycle per SM.  Adding four `.warpx4` UTCCP producers leaves about 981
B/cycle of STTM plus 255 B/cycle of UTCCP, approximately **1235 B/cycle per
SM** combined.  Hence there is no new SM-wide serialization near the aggregate
four-chunk STTM ceiling; any eventual merge or array arbitration remains
chunk-local or is wider than the tested traffic.

### Column alignment and service-beat granularity

A two-warp, same-chunk `STTM.x4` sweep keeps the total payload fixed at 8 MiB
(8192 stores per warp) and changes only the starting column:

| starting column | CTA span (cycles) | aggregate payload B/cycle | cycles/store across both producers |
|---:|---:|---:|---:|
| 0 | 34264 | 244.8 | 2.091 |
| 1 | 49260 | 170.3 | 3.007 |
| 2 | 34264 | 244.8 | 2.091 |
| 3 | 49260 | 170.3 | 3.007 |
| 4 | 34264 | 244.8 | 2.091 |

This rejects a simple four-column alignment unit: column 2 is identical to
columns 0 and 4.  The exact even/odd pattern instead supports a **two-column =
256-byte service beat**.  An aligned x4 store consumes two beats; an odd-based
x4 crosses the two-column boundary and consumes three, with a partial beat at
each edge.  The observed approximately 2 versus 3 cycles/store is nearly the
direct beat count.

The split may occur in the STTM packing/ingress path rather than in the SRAM
array itself, so this is not yet proof of two-column physical banking.  It is
nevertheless consistent with an eight-column tensor-core result being retired
as one 256-byte beat per cycle for four cycles.  Probe:
`tests/asm_construct/probe_sm100_utccp_sttm_clean.py` (B200, 2026-09-18).

### 与 UTCHMMA accumulator RMW 的写端竞争

UTCCP 的 destination 流量较低，仍可能不足以压出藏在 STTM admission 后的
TMEM array 瓶颈。为此又构造了更强的第二入口：warp 0 裸发射 32 条
M128N128K16 BF16→FP32 **accumulate** UTCHMMA，按
`A_KEEP → A_REUSE|A_KEEP ... → A_REUSE` 使用 A collector，最后用一条裸
UTCBAR 提交。整个 warp 执行 U-path 指令，不再使用旧的 lane-0
execution-group wrapper；所有 CTA BAR 前也显式汇聚。每条 MMA 仍对完整
64-KiB D tile 做 TMEM read-modify-write，32 条对每个 chunk 产生 512 KiB
写流量和等量读流量。

STTM contender 使用同一 subcore 上的 warp 1/5，各静态展开 256 条
`STTM.x8`，目标为与 D 不重叠的 columns 256--263。每条 collective 搬运
1024 B，故两 warp 合计 512 KiB；其约 2k-cycle 窗口已经把普通 STTM 入口推到
约 256 B/cycle/chunk。warp 0 位于另一个 scheduler，排除了 UTCHMMA 发射线程
直接抢占这两个 STTM warp 的 issue slot。

五次 launch 的稳态结果为：

| workload | UTCHMMA warp | STTM warp 1 | STTM warp 5 | STTM common span |
|---|---:|---:|---:|---:|
| 2×256 STTM.x8 only | -- | 1898 | 2020 | **2035** |
| 32×UTCHMMA RMW + STTM | **2177** | 1914--2074 | 1798--2038 | **2042--2074** |

混合时两个 STTM warp 之间会重新分配调度份额，但公共服务窗口只变化数十
cycles，UTCHMMA 自身始终精确为 2177 cycles。tensor write 平均约
**240.8 B/cycle/chunk**，普通 STTM 约 **252--258 B/cycle/chunk**，合计约
493--499 B/cycle/chunk。若 D 写回与 STTM 串行通过单个 256-B/cycle/chunk
写端，512 KiB tensor write 应让 combined 增加约 **2048 cycles**；实测没有
这个信号。

因此比 UTCCP 对照更强的结论是：**tensor-core accumulator RMW 不经过普通
STTM 的 256-B/cycle/chunk ingress/write datapath**。但“独立逻辑通道”不等于
“独立物理写口”：若 TMEM array 相对 SM clock 以 2x 运行、double-pumped，或
每个 SM cycle 有多个内部 service phase，同一个多-bank 阵列也能吸收当前约
493--499 B/SM-cycle/chunk 的混合平均流量。可以排除的是任何明显低于约
500 B/SM-cycle 的共享后端，但仍不能排除约 512-B/SM-cycle 的共享后端。

Probe: `tests/asm_construct/probe_sm100_utchmma_sttm_rmw.py` (B200,
2026-09-18). Cubin 完全由本仓库 assembler 生成；未 patch nvcc cubin。

#### LDTM/STTM 双向流与 tensor RMW

进一步把一个 LDTM warp 和两个 STTM warp 放在同一 subcore/chunk，且让二者
访问不重叠列。长 control 包含 519 条 LDTM.x16 和每个 STTM warp 512 条
STTM.x8：

```
LDTM bytes = 519 * 2048       = 1,062,912 B
STTM bytes = 2 * 512 * 1024   = 1,048,576 B
total                            2,111,488 B
common span                   = 8,270 cycles
rate                          = 255.32 B/cycle/chunk
```

两类相反方向的普通访问时间几乎严格相加，证明 LDTM 与 STTM 共用一条约
**256 B/cycle/chunk 的双向逻辑 service path**，而不是各自拥有可同时满速的
256-B/cycle 读口和写口。这个“path”可能包含共同 admission 和数据端口；当前
实验不要求二者在 SRAM 阵列上使用同一物理线路。

再并发 128 条裸 UTCHMMA 后，MMA 固定为 8321 cycles；普通 duplex span 从
8270 增至约 8528 cycles，吞吐降到约 247.6 B/cycle（约 3%）。按 accumulate
语义计，tensor D read+write 为 4 MiB/chunk，即约 504.1 B/cycle；两类流量的
表观和约 751.7 B/cycle/chunk，接近自然候选
`512-B/cycle tensor RMW + 256-B/cycle ordinary = 768 B/cycle`，但还不能把
768 当作已测出的硬上限。

把所有 UTCHMMA 改成 `enable-input-d=false` 的 overwrite 后，MMA、LDTM、
STTM 和总 span **逐周期完全相同**。因此这 3% 信号不能简单归因于逻辑
accumulator read 字节数：硬件可能在 overwrite 时仍执行固定粒度的内部
read/masked-RMW，也可能是在与方向无关的 tensor/ordinary admission 或 array
grant 上产生固定仲裁。可靠结论是 tensor RMW 具有高带宽、优先且基本独立的
通道，但与普通双向路径并非完全无耦合。

这个小耦合近似按 tensor wave 数线性增长。128 条、每条 64-cycle 的 MMA 使
普通窗口增加约 258 cycles，即约 **2.02 cycles/MMA**；duration-matched 的
64-MMA 版本使约 4200-cycle control 增至稳态 4335--4351，约
**+135--151 cycles**，接近 128-cycle 预测。当前最简候选是每条 64-cycle
M128N128 wave 从同 chunk 的普通 path 抽走约两个 service slots，也就是 tensor
活跃时普通 path 获得约 **31/32** 的 grant。该比例在 accumulate 与 overwrite
之间不变，说明它是固定仲裁节拍而不是按逻辑 D-read 字节收费；由于普通 warp
间偶有份额重分配，`2 cycles/MMA` 仍记作近似模型而非精确 ISA 保证。

cross-chunk 对照排除了 SM-wide UDP admission 作为上述主瓶颈。保持 STTM 在
warps 1/5 对应的 chunk 1，而把 LDTM 从同 chunk 的 warp 9 移到 chunk 2 的
warp 2：control 中 LDTM=4168 cycles、两个 STTM warp=3838/4096，公共窗口约
4200，而不是同 chunk 时的 8270。加入 128 条 UTCHMMA 后分别为
4169、3851/4108，几乎逐周期不变；MMA 仍为 8321。

因此普通 256-B/cycle 双向 path 是 **per chunk / 同 subcore 局部资源**。tensor
RMW 对每个 chunk 都有独立并行能力；只有 LDTM+STTM 已同时填满同一个 chunk
的普通双向 path 时，才出现约 3% 的次级本地仲裁信号。

The `.16x32bx2.x2` half-split form provides a more direct view of the
half-column packing.  nvcc lowers one PTX operation into two SASS operations:

```text
STTM.16dp32bit_t0_t15.x2  tmem[base],        {Ra,Rb}
STTM.16dp32bit_t16_t31.x2 tmem[base+offset], {Ra,Rb}
```

Each SASS half moves `16 rows * 32 bits * 2 = 128 bytes`, i.e. two 64-byte
half-columns.  With base fixed at column zero, scanning
`immHalfSplitOffset=0..7` gives:

| offset | CTA span (cycles) |
|---:|---:|
| 0 | 35079 |
| 1 | 49281 |
| 2 | 35079 |
| 3 | 49281 |
| 4 | 35079 |
| 5 | 49281 |
| 6 | 35079 |
| 7 | 49281 |

There are 16384 logical PTX pairs across the two producer warps.  The fast and
slow cases therefore take about 2.14 and 3.01 cycles/pair respectively.  The
natural decomposition is one service cycle for the aligned lower half plus
one cycle for an even-aligned upper half, or two cycles when the upper half
starts at an odd column and straddles two 128-byte bank words.

This strongly supports a 64-byte half-column and 128-byte bank-word packing,
but it does not reveal the proposed higher-bit/XOR bank hash.  The two PTX
halves are separate SASS instructions and enter service serially, so their
relative bank identities cannot create a same-cycle two-request conflict in
this probe.  Distinguishing the bank hash requires putting the two half-SASS
streams in independent producer warps and comparing same-bank versus
different-bank column mappings.

That independent-warp experiment was also run.  Warp 4 repeatedly issues only
`t0_t15` at column 0, while warp 8 repeatedly issues only `t16_t31` at columns
0--3.  Under the proposed checkerboard diagram, offsets 0 and 3 should use the
other bank and offsets 1 and 2 the same bank.  The result is instead purely an
alignment pattern:

| upper-half column | proposed relationship | CTA span (cycles) |
|---:|---|---:|
| 0 | different bank, aligned | 36979 |
| 1 | same bank, misaligned | 51405 |
| 2 | same bank, aligned | 36979 |
| 3 | different bank, misaligned | 51405 |

In particular, the clean aligned comparison 0 versus 2 is bit-for-bit
identical.  This does not disprove the bank mapping: the two warps together
approach one 128-byte half-STTM instruction per cycle, which is also exactly
what one 128-byte bank port could accept.  A shared per-subcore STTM admission
limit therefore hides any benefit from selecting two different banks.  A
decisive bank-hash probe needs a second ingress that bypasses this admission
point, such as UTCCP or tensor-core writeback, contending with one half-STTM
stream while the destination column mapping is varied.

Probe: `tests/tcgen05_ldst_bandwidth.cu` (B200, 2026-09-17).

Bring-up also exposed a scheduling-sensitive failure in the following
late-read `STG`, even when STTM/LDTM were replaced by `MOV`.  A factorized B200
control matrix gives:

| LDC write SB | LDC stall | gap before STG | STG waits LDC SB | result |
|---:|---:|---:|:---:|:---:|
| 1 | 1 | 0 | yes | fault 700/716 |
| 1 | 2 | 0 | yes | pass |
| 2 | 1 | 0 | yes | fault 716 |
| 2 | 2 | 0 | yes | pass |
| 2 | 2 | 0 | no | fault 716 |
| 2 | 1 | one stall-1 NOP | yes | pass |

Thus neither scoreboard number nor an unrelated wait bit is responsible.  A
scoreboard wait is still necessary, so two cycles do not cover the real LDC
data latency.  Instead, the LDC producer and its first scoreboard waiter need
at least two issue cycles of separation: back-to-back issue (`stall=1`) can
miss the newly created claim, while either `stall=2` or one intervening NOP
lets the waiter observe it and then block until actual LDC completion.  This is
a scoreboard-claim visibility/admission constraint, not an STTM restriction.
