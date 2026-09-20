# UTCHMMA — 5th-gen tensor-core FP16/BF16 MMA  → PTX `tcgen05.mma.kind::f16`

**Opcode mnemonic:** `UTCHMMA` — two opcodes by A source:
A-from-gdesc = `0b1010111101010` (0x15ea, 5610), A-from-tmem = `0b1100111101010` (0x19ea, 6634)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42)

New on sm100 (Blackwell). `UTCHMMA` = **U**niform **T**ensor-**C**ore **H**alf-precision
**M**atrix-**M**ultiply-**A**ccumulate — the SASS realization of PTX
**`tcgen05.mma.kind::f16`** (and `.kind::tf32`, `.kind::f8f6f4` share this
opcode; the exact element types are carried by the `idesc` instruction
descriptor, not the mnemonic). Computes `D = A*B + D` with the accumulator and
operands in **Tensor Memory (TMEM)**.

## Semantics
`UTCHMMA A, B, tmem[D], tmem[E], idesc, UPp [, scaleU4]`
- Warp-scalar U-path issue (unlike Hopper wgmma's warpgroup-collective model):
  all active lanes may execute the instruction, but hardware launches one
  MxNxK operation for that warp. Async / decoupled.
- **`D = A*B + D`** when `UPp` (enable-input-d) is true; **`D = A*B`** when false.
- Optional **`scaleU4`** scales the input accumulator: `D = A*B + D*(2^-scaleU4)`
  (PTX `scale-input-d`, valid only for f16/tf32, range 0–15).

Like STTM/UTCCP it is `INST_TYPE_DECOUPLED_RD_SCBD` (reads descriptors/TMEM,
releases a read scoreboard); completion is signalled to an mbarrier via
`UTCBAR` (`tcgen05.commit`) or awaited via the standard mechanism.

## Operands (cuobjdump order)
| pos | SASS | bits | PTX role |
|-----|------|------|----------|
| A | `gdesc[URa]` / `tmem[URa]` | [31:24] | A matrix (shared-mem descriptor **or** TMEM) |
| B | `gdesc[URb]` | [39:32] | B matrix (shared-mem descriptor, 64-bit) |
| D | `tmem[URc]` | [71:64] | destination + accumulator D (TMEM) |
| E | `tmem[URe]` | [47:40] | tmemE (secondary TMEM operand) |
| idesc | `idesc[URh]` | (URe+1) | instruction descriptor (32-bit, in shared/uniform) |
| pred | `UPp` | [89:87]+[90] | enable-input-d predicate |
| imm | `scaleU4` | [78:75] | scale-input-d (optional) |

Two operands are register **pairs** so the encoding fuses them:
- **`URe`/`URh` fusion:** field [47:40] = `TABLES_URa_0(URe, URh)`, which is just
  `URe` with the constraint `URh == URe + 1`. So `tmem[UR4], idesc[UR5]` encodes
  as field=4; the idesc register is always the tmemE register + 1 (adjacent
  aligned pair). The 64-bit A/B/E descriptors likewise require even-aligned base
  regs (`% 2 == 0` CONDITIONS).
- **`URi`** (disable-output-lane mask register) rides field [55:48]; encodes
  `URZ` when the PTX `{disable-output-lane}` vector is all-zero.

`ISRC_A_SIZE=64, ISRC_B_SIZE=64, ISRC_E_SIZE=64` (descriptor/pair operands),
`ISRC_C_SIZE=32`.

## Variant overview
| Class | Kind | Opcode | A source |
|-------|------|--------|----------|
| `utchmma_1cta__A_gdesc` | CLASS | 0x15ea | shared descriptor |
| `utchmma_1cta__A_tmem` | CLASS | 0x19ea | TMEM (+`.ASHIFT`) |
| `utchmma_2cta__A_gdesc` / `_A_tmem` | CLASS | 0x15ea/0x19ea | `.2CTA` |
| `utchmma_{1,2}cta_one__A_*` | ALT | — | `.ONE` (encoding-identical) |

The two opcodes differ only in operand-A type (gdesc vs tmem) and bit[74]
(`sh`=`ASHIFT`, only meaningful when A is in TMEM).

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `cluster_sz` | `ONLY1CTA`/`ONLY2CTA` | [85] | `.2CTA` = PTX `.cta_group::2` |
| `ws` | `WS` | [83] | weight-stationary mode (enables B_KEEP/B_REUSE/BUFFER1-3) |
| `ashift` | `ASHIFT` | [74] | `.ASHIFT` (A-from-TMEM only): shift A rows down |
| `reuse_a` | `REUSE_A` | [86] | `.A_REUSE` (collector::a::use; not with WS) |
| `keep_a` | `KEEP_A` | [84] | `.A_KEEP` (collector fill; not with WS) |
| `reuse_b` | `REUSE_B` | [82] | `.B_REUSE` (requires WS) |
| `keep_b` | `KEEP_B` | [81] | `.B_KEEP` (requires WS) |
| `buffer` | `BUFFER` | [80:79] | `BUFFER0..3` (1-3 require WS) |

The `collector_usage` / weight-stationary (`.WS`) machinery here is the SASS
side of PTX `.collector::{a,bN}::{fill,use,lastuse,discard}` and the activation-
stationary MMA forms. `.ashift` maps directly.

### Activation-stationary vs Weight-stationary vs Convolution
These are **two orthogonal axes**, not three parallel modes:

**Axis 1 — which operand stays resident in the collector buffer** (data-reuse
optimization; `WS` bit [83]):

| mode | activation | weights | PTX | collector on | # buffers |
|------|-----------|---------|-----|:---:|:---:|
| Activation-stationary | `A` | `B` | default `tcgen05.mma` (`.WS`=0) | `A` | 1 (`.collector::a::*`) |
| Weight-stationary | `B` | `A` | `tcgen05.mma.ws` (`.WS`=1) | `B` | 4 (`.collector::b0..b3::*`) |

The name refers to which *activation* matrix stays put. The SASS `WS` bit flips
the collector semantics, enforced by the CONDITIONS: `.A_REUSE`/`.A_KEEP` only
with `.WS`=0; `.B_REUSE`/`.B_KEEP`/`.BUFFER1-3` only with `.WS`=1. So WS is
**not a separate mnemonic** — just bit [83] toggling collector-A(1 buffer) ↔
collector-B(4 buffers).

**Axis 2 — GEMM vs Convolution** (application, not a mode): the same `UTCHMMA`
does both. Convolution stores activations in `A` **or** `B` and weights in the
other (hence it *uses* AS or WS), with a **mirror pair** of sliding-window tools:
- **AS conv** uses **`.ashift`** (bit [74]) — shifts A's rows down by one (`M`=128/256
  only, A-from-TMEM opcode 0x19ea only, ⊥ `.A_KEEP`/`.A_REUSE`): activation (A)
  streams as **rows**, window slides by a row.  Standalone `UTCSHIFT` readback
  shows four independent 32-row subcore shifts; the fused `.ASHIFT` is expected
  to share that segmentation but still needs a direct tagged-row test.
- **WS conv** uses a **`zero-column-mask-desc`** (a 64-bit descriptor, PTX
  §9.7.17.4.3; no `.ashift`): activation (B) streams as **columns**, and a
  periodic run-length mask zeroes B columns for padding/dilation/halo. In both,
  the **collector holds the activation** (A / B respectively).

```
             GEMM            Convolution
AS (.WS=0)   default mma     act=A wet=B, collector A, window via .ashift (rows)
WS (.WS=1)   .ws             act=B wet=A, collector B, window via zero-col mask (cols)
```
PTX splits this into 6 syntax forms; SASS collapses them all into `UTCHMMA`,
distinguished by `WS`[83] + `ASHIFT`[74] + collector bits (`A_REUSE`[86]/
`A_KEEP`[84]/`B_REUSE`[82]/`B_KEEP`[81]/`BUFFER`[80:79]). See
`notes/sm100/arch/tcgen05_microarch_speculation.md` for the inferred im2col-free
convolution dataflow.

## Bit layout (128-bit)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = read-scoreboard release
[112:110]           dst_wr_sb    = *7 (pinned)
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x15ea / 0x19ea
[90]                UPp@not ; [89:87] Pnz = UPp (enable-input-d)
[86]                reuse_a  [85] cluster_sz(2CTA)  [84] keep_a  [83] ws
[82]                reuse_b  [81] keep_b            [80:79] buffer
[78:75]             scaleU4
[74]                sh = ashift (A-tmem) / *0 (A-gdesc)
[73:72]∥[63]        opType = 0
[71:64]             URc  (D accumulator, TMEM)
[55:48]             URi  (disable-output-lane mask reg)
[47:40]             TABLES_URa_0(URe,URh)  (= URe; URh=URe+1)
[39:32]             URb  (B descriptor)
[31:24]             URa  (A descriptor / TMEM)
[15]                Pg_not ; [14:12] Pg = @UPg
```

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/utchmma_test.cu` → `tests/utchmma_test.cubin`. Decoder:
`tools/decode_utchmma.py` — all 4 round-trip (**ALL PASS**).

| Disassembly | Lo64 / Hi64 | opcode |
|-------------|-------------|:------:|
| `UTCHMMA.2CTA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UPT` | `…75ea` / `0ba0000a` | 0x15ea |
| `UTCHMMA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UPT, 0x3` | `…75ea` / `0b80180a` | 0x15ea |
| `UTCHMMA tmem[UR7], gdesc[UR8], tmem[UR6], tmem[UR4], idesc[UR5], UPT` | `…79ea` / `0b800006` | 0x19ea |
| `UTCHMMA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UP0` | `…75ea` / `0800000a` | 0x15ea |

Confirmed facts:
- Opcode 0x19ea (A-from-TMEM) vs 0x15ea (A-from-shared-descriptor).
- `.2CTA` = bit[85]; `scaleU4` = [78:75] (`, 0x3`); enable-input-d predicate
  `UPp` = [89:87] (`UP0` vs default `UPT`).
- tmemE/idesc adjacency verified: `tmem[UR4], idesc[UR5]` → field[47:40]=4.
- The `{disable-output-lane}` vector (passed as all-zero) encoded `URi`=URZ.

### PTX → SASS mapping
| PTX | SASS |
|-----|------|
| `tcgen05.mma.cta_group::1.kind::f16 [D], a-desc, b-desc, idesc, {mask}, p` | `UTCHMMA gdesc[URa], gdesc[URb], tmem[URc], tmem[URe], idesc[URh], UPp` |
| `…[D], [a-tmem], b-desc, idesc, {mask}, p` | `UTCHMMA tmem[URa], gdesc[URb], …` (opcode 0x19ea) |
| `…, p, scale-input-d` | `…, UPp, scaleU4` |
| `.cta_group::2` (mask vector size 8) | `.2CTA` |
| `.ashift` | `.ASHIFT` (A-tmem only) |

The `.kind::f16`/`.tf32`/`.f8f6f4` distinction is **not** in the mnemonic — all
map to `UTCHMMA`; the element types live in the 32-bit `idesc`. Integer
(`.kind::i8`) is a separate mnemonic `UTCIMMA`; FP8-quarter is `UTCQMMA`;
MX-scaled is `UTCMXQMMA`.

## B200 动态探测：BF16 `M128xNxK16`

测试见 `tests/tcgen05_utchmma_bandwidth.cu` 和
`tests/tcgen05_utchmma_interaction.cu`。测试由一个 warp 的 U path 发射 512 条
`tcgen05.mma.cta_group::1.kind::f16`，A/B 位于 shared memory，D 为 TMEM
中的 FP32；最后用 `tcgen05.commit` + mbarrier 等待真正完成，而不是只测
前端发射。A/B 均填为 BF16 1.0 时，overwrite 后用 LDTM 读到
`0x41800000`（16.0f），因而 descriptor 和计算路径已经过基本正确性验证。

### 基本吞吐和物理 wave

| descriptor shape | 512 条总周期 | 表观周期/条 | 结论 |
|---|---:|---:|---|
| M128, N=8/16/32/64/128 | 34,459（短循环） | 67.30 | N≤128 都占一个相同的物理 wave |
| M64, N=128 | 34,459 | 67.30 | M64 不缩短执行时间，M 方向物理粒度至少为 128 |
| M128, N=256 | 约 65,730 | 128.38 | 两个 N128 wave |
| M64, N=256 | 约 65,707 | 128.33 | 同上 |
| M128, N128，6 路静态展开 | 32,977 | 64.41 | 去掉大部分循环控制开销后逼近 64 cycle/wave |

U-path `UTCHMMA` 和 `UTCBAR` 本身就是 warp-scalar 指令，手写 SASS 可以直接
裸发射；所有 active lanes 经过该指令也只形成一次 warp 级操作。ptxas 在
`UTCHMMA` 周围生成的 ELECT/PLOP/retry 序列，是把 PTX 更一般的
active-thread-group 语义契约降到硬件 U-path 的兼容层，不是 native SASS 的
admission 或 completion 握手。

最新的 `tests/asm_construct/utchmma_issue_base_sm100.sass` 已在 B200 上验证：
同一个 warp 可连续裸发射 **32 条 UTCHMMA**，随后用一条裸 `UTCBAR` 正常
收束。ptxas 长流同样能在一个 commit window 内提交约 512 条 UTCHMMA。
先前“4 条成功、5 条报 719”、插入 pre-commit gap 后边界变化等现象，来自把
本已 warp-scalar 的 U 指令再次套入不完整/不匹配的 PTX 兼容 wrapper；它们
不是硬件 queue 深度或 `UTCHMMA→UTCBAR` latency，已从架构模型中撤销。

`UTCBAR` 对 mbarrier 的约束是 phase 到达计数，不是 warp 归属：每次 UTCBAR
给目标 barrier 注册一个 arrive-on event，多个 warp 可以共享同一对象。
`init_count` 应等于下一次 phase 切换前预期的 UTCBAR 总数再加其他 arrival；
例如 4 个 warp 各发两次 UTCBAR、且没有其他 arrival 时应设为 8。count 偏小会
提前切 phase，偏大则必须由剩余 arrival 补齐后才能完成。

旧版 `tools/patch_utchmma_schedule.py` 仍可用于研究 ptxas wrapper 内部的
read-release scoreboard 分配，但其结果不能推出裸 U-path SASS 的硬件要求。
未 patch 的 ptxas 长流仍给出 64.41 cycle/wave，因此 64-cycle 物理 wave
结论不受上述 wrapper 误用影响。

一个 `M128xN128xK16` wave 含 262,144 次 MAC；64 cycle 对应：

- **4,096 MAC/cycle = 8,192 FLOP/cycle**；
- N256 恰好拆成两个约 64-cycle wave；
- overwrite（`enable-input-d=false`）与 accumulate（true）完全同速；
- `.collector::a::fill/use/lastuse` 不改变计算吞吐。

这里的“物理 M128/N128 wave”指执行时间粒度。较小的逻辑 shape 是否仍从
shared memory 读取完整的 padded tile，不能仅由计算时间推断。

### 与 Hopper WGMMA 对应的候选内部 tile 模型

目前最简洁的解释是 Blackwell 沿用 Hopper 的 GMMA 数据流，但把每个
subcore 的 BF16 lhs slice 从 `16x16` 加宽为 `32x16`：

| | Hopper HGMMA `m64n128k16` | Blackwell UTCHMMA `m128n128k16` |
|---|---:|---:|
| 每 subcore 的 A slice | 16x16 BF16 = 512 B | 32x16 BF16 = 1 KiB |
| 四 subcore 的 A 流量 | 2 KiB = 16 wavefronts | 4 KiB = 32 wavefronts |
| 每个 n8 的 B tile | 16x8 BF16 = 256 B = 2 wavefronts | 相同 |
| N128 的 B 流量 | 4 KiB = 32 wavefronts | 相同 |
| A+B 总流量 | 48 wavefronts | **64 wavefronts** |
| 稳态计算时间 | 约 64 cycles（compute floor） | **约 64 cycles** |

因此 Blackwell 的 M128N128 指令恰好需要 `64 * 128 B` shared operand，和
64-cycle 执行时间闭合为 **一个 128-B operand wavefront/cycle**。B 的
`16x8` tile 仍可像 Hopper 一样在四个 subcore 间广播；翻倍的是每个
subcore 消费的 A 行数和 BF16 MAC 宽度，而不是 B 广播流量。

输出端也独立闭合：每个 subcore 若每 cycle 产生一个 `m8n8` FP32 tile，
就是 `8*8*4 = 256 B/cycle/subpartition`，恰好等于从 64-KiB D tile / 64
cycles 反算出的 TMEM 写入率。等价表述是每个 subcore 每两 cycle 产生一个
`m16n8` 输出。相比 Hopper 的一个 `m8n8` FP32 tile / 约两 cycles，输出和
MAC 速率均翻倍。

这个模型已同时满足 MAC 数、M/N/K shape、shared operand 字节数、执行
周期和 TMEM 写带宽，但 `32x16` A slice 与 `m8n8/cycle` 仍属于由这些守恒
关系反推的结构，尚未被 tagged-row/column 数据实验直接观察。

### TMEM 端口开销

M128xN128 的 FP32 D tile 为 64 KiB。若 64 cycle 内完成，则每个 SM 的
tensor 后端平均产生 **1,024 B/cycle 的 D 写入**；accumulate 还需读取同一
64 KiB，等价于 **1,024 B/cycle 读 + 1,024 B/cycle 写/RMW**。按四个 SM
subpartition 均分则分别是 256 B/cycle/subpartition。

并行运行另一个 warp 的裸 LDTM.x16 或 STTM.x16 流时：

- UTCHMMA 时间不变（plain 34,458 cycles，A-reuse 34,381 cycles）；
- LDTM 流从 143,366 增至 144,319 cycles，只有约 0.7% 变化；
- STTM 流为 180,259 cycles，混合前后相同。

因此 UTCHMMA 的 D RMW 几乎确定不经过普通 LDTM/STTM 的窄端口；更合理的
模型是 tensor core 与 TMEM 间存在专用宽 RMW datapath。这个结果也解释了
普通 LDTM/STTM 约 256 B/cycle/subpartition 的端口为何无法承载上述聚合
带宽。

后续用饱和 STTM 做了更强的写侧对照。32 条裸 M128N128 accumulate
UTCHMMA 采用 `collector::a::fill/use.../lastuse`，合计向每个 chunk 产生
512 KiB D 写入；另两个同-subcore warp 各发 256 条 `STTM.x8`，合计 512 KiB，
已把普通 STTM 入口推到约 256 B/cycle/chunk。STTM-only 的公共 span 约
2035 cycles，混合后约 2042--2074 cycles；MMA 自身始终为 2177 cycles。两类
流量合计约 493--499 B/cycle/chunk，仍几乎完全重叠。因而这里的“专用”不只
是从低强度 overlap 推断：tensor RMW 与饱和 STTM 确实具有独立的逻辑写入
capacity。更深层仍可共享一个约 512-B/cycle、double-pumped 或多相的 SRAM
阵列。完整数据和构造见 `sttm.md` 及
`tests/asm_construct/probe_sm100_utchmma_sttm_rmw.py`。

读侧也得到了同样结果。一个严格 scoreboard-closed 的单 warp LDTM.x16 流
中，270 条 load 单独运行 2176 cycles；与 32 条 accumulate UTCHMMA 并行时
LDTM/MMA 分别仍为 2177/2177 cycles。两者合计读压力约
494.9 B/cycle/chunk，明显排除普通 256-B/cycle 单口串行模型。

写侧和读侧的两个饱和实验共同支持：**UTCHMMA 的 D accumulator 不经过
LDTM/STTM 的普通 admission/datapath，并具有独立的逻辑 RMW service
capacity**。最简物理模型是专用 RMW 口，但还存在等价候选：TMEM array 可以
相对 SM clock 以 2x 运行、端口 double-pumped，或每个 SM cycle 提供多个内部
service phase。当前混合平均压力已达到约 493--499 B/SM-cycle/chunk，仍恰好
没有超过一个可能的 512-B/SM-cycle 共享后端。
读侧完整数据见 `ldtm.md`。

最后把普通读写同时压满：同 chunk 的 519 条 LDTM.x16 加两个 warp 各 512 条
STTM.x8，在没有 MMA 时以 8270 cycles 搬运 2,111,488 B，恰好是
255.32 B/cycle。这证明普通 LDTM/STTM 共用约 256-B/cycle 的双向 service
path。并发 128 条 UTCHMMA 后，MMA 仍固定 8321 cycles，普通 duplex span
增至约 8528 cycles（约 3%）。tensor RMW 按逻辑读写流量计约
504.1 B/cycle，与普通约 247.6 B/cycle 合计约 751.7 B/cycle/chunk；这接近
但没有撞穿 `512 tensor + 256 ordinary = 768 B/cycle` 的候选深层能力。

值得注意的是，把全部 MMA 从 accumulate 改成 overwrite（`!UPT`）后所有
周期逐项不变。因此不能认定 overwrite 会在物理 TMEM 阵列上省掉 accumulator
read；也不能把 3% slowdown 单独解释成总数据字节带宽。它同样可能来自固定的
RMW beat，或方向无关的 tensor/ordinary admission/array-grant 仲裁。

#### D 地址轮转与多 warp 调度

上述“每条 MMA 都产生完整 TMEM RMW”只是 ISA 语义字节数，不能直接当作 SRAM
流量。早期 Modal 运行曾把远端调用未返回误判为 kernel 不完成，并据此记录了
`A B C A`/`A B C B` 的两-context residency 边界；该结论已经复测证伪。裸
SASS 中无论使用同一个 `UR10+imm`，还是先用 UIADD3 生成 UR30/UR31/UR32 三个
完整 D 基址，三/四个 128-column D tile 均可在 accumulate 模式下反复回访。
8 条独立-base-UR 的 `A B C A A B C A` 五次重复均正常完成，为 646--654
cycles。当前没有证据支持“每 warp/subcore 只能维护两个 D context”。

中途 UTCBAR 也可以正常工作：两段 MMA 各发一条 UTCBAR，并把同一 mbarrier 的
init count 设为 2，16 条合计约 1157 cycles。此前“UTCBAR 后不能继续 MMA”的
推断同样撤回；正确约束仍只是 phase 切换前的 arrival 总数必须匹配 init count。

多 warp 版本随后验证通过。每个 warp 使用私有 128-column D tile、私有
mbarrier，并只在 epoch 尾部发一条 UTCBAR；64 条 M128N128 accumulate 的结果为：

| issuing warps | 每 warp 的 D 数 | 每 warp 计时（cycles，典型值） |
|---:|---:|---|
| 1 | 1 | 4230 |
| 2 | 1 | 8262 / 8312 |
| 3 | 1 | 12294 / 12408 / 12392 |
| 4 | 1 | 16326 / 16493 / 16474 / 16458 |
| 2 | 2（CTA 共四个 D） | 8262 / 8312 |

因此多个 warp 的 epoch 可以同时 outstanding，后端会在 warp 间公平交错，
但总吞吐仍只有约一条 M128N128/64 cycles：增加 issuing warp 不增加 TC 峰值。
四 warp 的结束时间只差约 170 cycles，排除“完整跑完一个长 epoch 后才切到下一
warp”的粗粒度串行。`64+2` MMA 的不平衡测试中，总 span 为 4358 cycles；短
warp 放在 warp 0 时 326 cycles 完成，放在 warp 1 时约 504 cycles 完成，也支持
细粒度调度并显示轻微的 warp/到达次序偏置。

为了区分 warp-local 与 subcore-local admission/context，把 issuing warp 固定到
同一个 subcore（warp id 相差 4）后重复：

| issuing warp ids | placement | common span（cycles） |
|---|---|---:|
| 0, 1 | 不同 subcore | 8326 |
| 0, 4 | 同一 subcore | 8326 |
| 0, 4, 8 | 同一 subcore | 12422 |
| 0, 4, 8, 12 | 同一 subcore | 16523 |

公共时间只随总 MMA 数线性增长，与 placement 无关；同一 subcore 放入四个
issuing warp 也没有容量拐点。个别后加入 warp 会提前约 0.5--0.9k cycles 完成，
说明本地 front-end/admission 公平性受 warp 顺序影响，但 SM-wide tensor 后端的
总服务率不变。当前数据既不支持“两 context/warp”，也不支持“两 context/subcore”；
若存在 context table，其容量至少高于本实验并且不是峰值吞吐瓶颈。

CTA 内四个 D 按“两个 warp、每 warp 两个”正常反复访问且完全不降速。同一 warp
轮转三/四个 D 也正常，故该实验不能区分 context 配额绑定 warp 还是 subcore：
目前根本没有观察到可用于定位的 context-capacity 拐点。

`scaleD=0`（SASS 末 operand 为 `!UPT`）与 accumulate 的吞吐完全相同：同一
warp 轮转 1、2、3、4 个 D，64 MMA 均严格为 4230 cycles。四个 warp 各自
overwrite 私有 D 时，计时也与 accumulate 逐项相同
（典型值 16326 / 16493 / 16474 / 16458 cycles）。32 条四-D overwrite 与两个
warp 的饱和 STTM.x8 并行时，MMA 为
2182 cycles；STTM-only 公共 span 约 2035 cycles，混合后各 STTM warp 仍约
1778--2055 cycles，没有稳定退化。也就是说，即便主动轮转 D、排除“所有 MMA
只驻留并累加同一个 D”这一解释，普通 STTM 写路仍看不到 tensor 写流的竞争。

普通 LDTM 的并发可见性实验进一步否定了完整 D 驻留。shared A/B 被填成 BF16
1.0；warp 0 在单个 completion epoch 中先发一条 overwrite、再发 64 条
accumulate，理论上同一 D 元素依次为 `16, 32, ..., 1040`。warp 1 同时连续
LDTM.x1 同一列并写出 lane-0 样本，在最终 UTCBAR 之前实际截获了
`0, 16, 32, ..., 1040` 的完整递增序列。把 observer 移到 warp 4、与 producer
warp 0 位于同一 subcore，结果相同。因此结果在 MMA 流执行期间持续退休到普通
TMEM 可见状态，而不是只在 commit 时整体写回。仍可能存在少量内部 microtile
forwarding/write-combine，但其生命周期短于整条 MMA stream，不能用来解释此前
与 LDTM/STTM 几乎无争用的结果。

### 单条 N128 指令的中间可见性（2026-09-18）

进一步把 producer 缩成**恰好一条** overwrite M128N128 UTCHMMA，并在另一个
warp 中用普通 LDTM 追赶其写回。D 预先清零，A/B 均为 BF16 1.0，因此旧值为
`0x00000000`，新值为 `0x41800000`（16.0f）。producer 使用固定 16 条 NOP 的
代码布局，只改变调度控制中的 stall，排除了增删指令造成的 PC/取指相位变化。

结果证明可以在单条指令内部截获变化：

- 一条 `LDTM.x16` 曾稳定读到前 4 列为 0、后 12 列为 16；把起始列从 0 改成
  1 后仍是相对于 LDTM 起点的 `4 old + 12 new`。
- 三条背靠背 `LDTM.x2` 读同一个二列范围时，在过渡相位读到
  `old pair -> new pair -> new pair`。
- 对偶数起始 `(0,1)` 和跨假定边界的奇数起始 `(1,2)`，每个 x2 返回值始终是
  `{old,old}` 或 `{new,new}`；当前没有观察到 `{old,new}`。
- 修正探针 timer 对齐后，三条同时 outstanding 的 `LDTM.x1` 也可正常工作。
  正序读 `col0,col1,col2` 与逆序读 `col2,col1,col0` 都稳定得到
  `old -> new -> new`，裂口跟随请求序号而不跟随列号。

这说明单条 UTCHMMA 的结果在 UTCBAR 之前已经能被普通 LDTM 观察到，且至少在
`LDTM.x2` 的观察粒度上二列是相干的；它与“每 2 列一个 256-B/chunk 退休单元”
相容。但它**还不能证明**偶数对就是物理写回原子单元：LDTM.x2 本身可能把两列
作为一个不可交错的读 transaction，掩盖其内部写入顺序。

还做了同一 CTA 两个 observer 的正序/逆序实验。两 warp 在共同 PC 上先用
predicated UIADD3 构造不同的 TMEM 地址，再分别读 `(0,1),(2,3),(4,5)` 与逆序。
交换两种顺序后，`old -> new -> new` 模式跟随物理 warp/时间槽，而不跟随列号；
另一个 subcore 同时已经全新。这表明跨 subcore 的 observer 相位差足以伪装成
“低列先写”，故现阶段不能宣称已测出列扫描方向。类似地，x16 的 `4+12` 裂口
会随起始列平移，更像 LDTM.x16 自身的四列 service beat，而不是 UTCHMMA 的
四列写回边界。x1 正/逆序结果还表明，一个在相邻列上看似明确的 frontier 也可能
纯粹是连续读请求跨过了全局可见性切换点。

探针为 `tests/asm_construct/probe_sm100_utchmma_intra_writeback.py`。其窄读模式
特意保留三个全局未使用 scoreboard 给 allocator builtin，允许三条 x1/x2
同时 outstanding。x1 bring-up 中一次 716 最终查明是 12-B 样本区之后的
64-bit timer 被错误放在未对齐的 `out+0xc`，并非 LDTM.x1 的硬件限制。

### 运行中改写 D：直接证明 late accumulator RMW（2026-09-19）

上述 LDTM observer 只证明结果渐进退休，单独看仍兼容“UTCHMMA 开始时预取旧
D、稍后分块写回”。新的三值实验直接让另一个 warp 在**单条 accumulate
UTCHMMA 执行途中**用 `STTM.x8` 覆写其 32-row chunk：初始 D=1.0，BF16
ones 的 K16 乘积为 16.0，中途写入 D=64.0。因此最终值具有唯一解释：

| result | interpretation |
|---:|---|
| 17.0 | MMA 使用旧 D；STTM 位于 D-read 后、MMA writeback 前 |
| 64.0 | STTM 位于 MMA writeback 后并成为最终写入者 |
| **80.0** | MMA 读取途中写入的 64，再加 16；直接证明 late D read/RMW |

为避免把入口等待误当成指令已执行，producer 记录两个时钟：UTCHMMA 前的
pre-issue，以及 UTCHMMA 后第一条 `CS2R`。后者只有在 UTCHMMA 已通过
admission 后才能执行，所以是 admission 时刻的上界；它在所有 launch 中均为
pre-issue+17 cycles。modifier 同时记录 STTM 前和 `FENCE.VIEW.ASYNC.T` 后的
实际时钟，分析完全不使用源码 NOP 数作为相位。

按 `mutation_start - admission_upper` 对密集边界扫描分组，结果为：

| measured phase | modified chunk 的 256 个值 |
|---:|---:|
| +21, +25, +27, +29, +31 | **全部 80.0** |
| +32, +33, +35, +37 | **全部 17.0** |
| +39 及以后 | **全部 64.0** |

未修改的 control chunk 始终为 17.0；单条 MMA 的 completion 窗口为 132
cycles，mutation STTM 到 fence completion 为 8 cycles。最关键的 +21…+31
样本中，modifier 的 start 已明确晚于“UTCHMMA 后第一条指令”，最终却得到
`64+16=80`；发射时整体捕获 accumulator 的模型无法产生这个值。

因此可以把结论收紧为：**UTCHMMA 对 D 执行分阶段的 late
read-modify-write，而不是在 admission 时整体 snapshot accumulator**。+33…+37
的 lost-update 窗口与 +39 后的 late-STTM 窗口还直接分离了内部 D-read 和
writeback。当前 N8 实验的被修改 chunk 整体同值，尚未解析一个 chunk 内更细的
RMW microtile 顺序；那需要对不同列/行 slice 分别写入 tag 再扫相位。

随后把 nominal phase 53--63 的缺失奇数档全部补齐，并对每档重复 6--8 次。
以 `FENCE.VIEW.ASYNC.T` 后的 mutation-done 时钟（相对 admission upper bound）
分组，两个翻转点逐周期分离且没有重叠：

| mutation visible phase | result |
|---:|---:|
| <=39 | 80.0 |
| 40--45 | 17.0 |
| >=46 | 64.0 |

所以 D-read 发生在 phase 39/40 的边界，MMA writeback 发生在 45/46 的边界；
相同 STTM+fence 观察延迟在两次翻转中抵消，中心间隔为 **6 SM cycles**。若只按
离散时间戳给严格区间，则是 5--7 cycles。这个 B200 N8 BF16 accumulate 的
read-to-write 窗口约为此前 Hopper HGMMA register-mutation 实验中约 12-cycle
窗口的一半。该数字描述本 microtile 的可见 RMW pipeline 距离，不代表整条
132-cycle UTCHMMA 的首读到末写跨度。

探针：`tests/asm_construct/probe_sm100_utchmma_d_mutation.py`；Modal runner 的
`--d-mutation-results` 输出实际 admission/mutation 相位以及四个 warp 的值计数。

为尝试扩大单条指令的观察窗口，又加入 warp 2--5 的四路饱和 `LDS.128`
contender。四个 warp 覆盖四个 subcore，每轮各发三条独立 LDS.128（SB0--SB2）
再显式等待；12 轮远长于单条 MMA 的活动区间。control 与 contention 均使用
192-thread CTA，避免额外 resident warp 本身成为变量。producer 的计时区间为
UTCHMMA 前的 `CS2R` 到 UTCBAR/mbarrier wait 后的 `CS2R`：

| workload | five launch durations |
|---|---|
| no LDS contender | `215,215,215,215,215` cycles |
| 4-way saturated LDS.128 | `215,215,215,215,215` cycles |

LDS 压力改变了 producer/observer 的相对调度相位：同一 x1 三读在 control 的
冷启动样本为全新，而 contention 中出现一次 `old,new,new`。但 MMA 完成区间
逐周期完全不变，所以这不是可见性窗口被拉长，只是 observer 相位移动。结果与
长流仲裁结论一致：shared-read arbiter 强优先保护 tensor operand wave，压力
主要回灌到 LDS 队列。因而“用普通 LDS 拖慢一条 UTCHMMA”在 B200 上不可行；
若要扩大窗口，需要直接竞争 tensor backend/同 subcore tensor context，或构造
能增加 UTCHMMA 自身 operand wave 数的合法 descriptor/layout，而不是增加低优先级
shared client。

#### 运行中改写 RHS：n 方向遍历次序（2026-09-19）

为避免连续 LDTM 的请求顺序伪装成写回方向，另一个探针不在 UTCHMMA 运行中
读取 TMEM，而是改写它尚在消费的 shared-memory RHS：warp 0 发一条 overwrite
M128N256 BF16 MMA；warp 1 在可调的绝对时钟相位用两条相邻 `STS.128` 把一个
1-KiB B stripe 从 BF16 1.0 改为 2.0。UTCBAR 完成后才一次性导出 D。输出
16.0/24.0/32.0 分别表示对应 D 元素消费了全旧、一半新、一半旧、全新的 RHS。
每次 launch 同时记录 UTCHMMA issue、两条 STS 和 completion 的实际 `clock64`，
分析按实测的 `mutation_start - mma_issue`，不按源码中的名义 delay 分组。

双 modifier warp 的初版先确认了 shared 地址映射：连续的 stripe 0--3 依次影响
TMEM 中连续的 n 区间，约为列 4--67、68--131、132--195、196--255；stripe
4 只在尾部 244--255 留下 half 效果，stripe 5--7 完全无影响。当前 exporter 的
列 0--3 反复得到 0/launch residue，故不拿它们判断方向。随后改成单 warp 连续
写完整 stripe，消除了两个 warp 相差十几 cycle 的调度歧义。代表性的稳定结果
如下（`new`=32.0，`half`=24.0，省略全旧区域）：

| 实测 mutation 相位 | stripe 0 | stripe 1 | stripe 2 | stripe 3 |
|---:|---|---|---|---|
| +5 cycles | 4--51 new；52--67 half | new/half | new/half | new/half |
| +21 cycles | 4--67 half | 68--115 new；116--131 half | new/half | new/half |
| +37 cycles | old | 68--131 half | 132--179 new；180--195 half | new/half |
| +53 cycles | old | old | 132--195 half | 196--243 new；244--255 half |
| +67 cycles | old | old | old | 196--211 new；212--255 half |
| +85 cycles 左右 | old | old | old | old |

这个随时间向高列平移的对角前沿直接证明：在当前 K-major、无 swizzle 的
M128N256 构造中，UTCHMMA **按递增 n 消费 B**。四个约 64-column 的 shared
stripe 的消费相位依次约错开 16 cycles；stripe 内又能分辨出 16-column 边界。
它也与 N256 的两个连续 N128 物理 wave 相容；本探针记录的
issue→UTCBAR/mbarrier-wait 区间稳定为 256 cycles（包含提交和等待路径开销）。

严格地说，RHS mutation 直接标记的是 operand fetch/consume 顺序，而不是 TMEM
端口提交瞬间；最终 D 的列顺序再结合上一节已由并发 LDTM 证明的“单条指令中途
写回可见”，强烈支持 TMEM 也按低 n 到高 n 推进，但若要把 fetch、compute、
TMEM retire 三段各自的固定延迟拆开，仍需把本探针与同相位 LDTM snapshot 合并。
探针为 `tests/asm_construct/probe_sm100_utchmma_rhs_mutation.py`；Modal runner 的
`--rhs-mutation-results` 会直接输出每次 launch 的实测相位和压缩后的列区间。

#### disable-output-lane 语义与 bank-hash 碰撞尝试（2026-09-19）

新的 M128N8 overwrite 探针先把 D 清零，再分别设置四个连续 mask UR，并导出
完整的 128×8 FP32 结果。全开得到 128 行 `0x41800000`（16.0），全关得到
128 行 0。单独开放一个 32-bit mask word 的结果精确为：

| 开放的 mask word | 被 UTCHMMA 更新的 TMEM rows |
|---|---|
| UR28 | 0--31 |
| UR29 | 32--63 |
| UR30 | 64--95 |
| UR31 | 96--127 |

mask bit 的语义也被直接确认：**1=禁止该 row 写回，0=允许**。因此把四个 word
都设为 `0xffff0000` 会只更新每个 32-row chunk 的 rows 0--15；全部设为
`0x0000ffff` 则只更新 rows 16--31。重复 launch 的边界逐行一致，没有观察到
mask word 或 bit 的额外 swizzle。

随后用这个能力尝试区分候选 checkerboard
`bank = row_half XOR ((column >> 1) & 1)`。固定 UTCHMMA 只写每个 chunk 的
下 16 行，另一个 warp 在逻辑地址不重叠的 column 8/10 上发
`STTM.16dp32bit_t0_t15.x2`，扫描实际相位。单条 victim 后再做同地址、同
layout 的 LDTM RAW readback，强制计时终点越过普通 TMEM 可见性；还测试了
16 条 half-STTM burst。稳态结果为：

- 单 victim + RAW readback：column 8/10 均为 **10 cycles**；
- 16-victim burst：从 `sttm_start-mma_issue = +5` 扫到 `+101` cycles，固定
  tensor 下半 mask 时 column 8/10 始终相同；
- 固定 `t0_t15` victim、改用 tensor 上半 mask 复测，同样没有 column 8/10
  的互补或反转；名义 phase 继续推到 MMA 完成以后也没有出现 parity 差异；
- 同期 M128N8 UTCHMMA 的 issue→commit/wait 区间固定为 **133 cycles**。

Tagged tomography 同时纠正了早期探针的命名假设：SASS 的
`t0_t15/t16_t31` 选择寄存器数据来自哪个线程半区，两者在相同 TMEM 地址上都
访问 canonical rows 0--15，并不分别代表 TMEM row lower/upper half。因此最终
矩阵固定使用 `t0_t15`，只通过 UTCHMMA mask 翻转真正的 TMEM row half。

因此在覆盖绝大部分 MMA 活动窗口的当前时间分辨率上，没有观察到候选 XOR 所
要求的互补峰。这个负结果不能否定物理 checkerboard：此前饱和实验已经表明
tensor D 写回和普通 LDTM/STTM 拥有近乎独立的逻辑 service path；这里进一步
说明，即便用 lane mask 把 tensor 写回缩到一个 row half，普通路径的完成延迟
仍没有暴露最终 SRAM-bank 仲裁。后续不应继续简单增加 STTM 数量，而应寻找能
从 tensor/UTCCP 入口产生窄、可选 half-column 请求的第二客户端，或改做逻辑
布局的 tagged-data tomography。

探针为 `tests/asm_construct/probe_sm100_utchmma_bank_hash.py`；Modal runner 的
`--bank-mask-results` 和 `--bank-collision-results` 分别压缩完整 row mask 输出
和实测碰撞时序。

后续 16-datapath STTM/LDTM 单指令吞吐矩阵终于给出了独立于上述跨入口碰撞的
bank 证据：`16dp256bit.x1` 每个内部 phase 访问四个同奇偶列并产生精确 2x
penalty，而连续四列的 `16dp128bit.x4` 能使用两路服务能力。因此可见 bank
selector 至少包含 column bit 0；但该实验的每个判别 phase 固定一个 row half，
仍不能判断最终形式是 `column_parity` 还是
`column_parity XOR row_half`。详见 `sttm.md` 的
“Intra-instruction bank conflict from 16-datapath layouts”。

#### 多 warp 间的后端调度粒度（2026-09-18）

为了区分“多条 UTCHMMA 以内部 wave 粒度交错”和“选中一条指令后连续执行其
全部 wave”，使用两个 producer warp 分别发一条 N256（两个 N128 物理 wave）
和一条 N8（一个物理 wave），第三个 warp 用三条同时 outstanding 的 LDTM.x1
连续观察 N256 的低半、高半以及 N8 的独立 D 区域。两条指令绑定同一个
mbarrier，init count 为 2；因此 completion timestamp 会在两者都完成后聚团，
不能单凭 UTCBAR 后的计时判断并行范围，D 的中间可见次序才是判据。

注意 UTCHMMA 的 D operand 编码没有 immediate offset。探针最初写成
`tmem[UR10+0x100]`，通用语法匹配器虽接受文本却没有把 offset 编进指令，实际
仍是 `tmem[UR10]`。有效版本先用 UIADD3 得到 `UR11=UR10+0x100`，再令 N8 使用
`tmem[UR11]`。UTCBAR 地址前的直接 `UMOV UR18,0x600` 也固定采用
`stall=5,yield=1`；较短的 `stall=1,yield=0` 会使多 warp 探针不完成。

| producer 0 → producer 1 | LDTM 顺序 | 首次见新值的 round |
|---|---|---|
| N256 → N8 | low, high, N8 | `0, 1, 4`（两次完全一致） |
| N256 → N8 | N8, high, low | `5, 1, 0` |
| N8 → N256 | low, high, N8 | `0, 3/4, 0` |
| N8 → N256 | N8, high, low | `0, 3/4, 0` |

正反观察顺序均表明：N256 先获准时，其低/高两个 N128 wave 连续变为可见，N8
只能在两者之后提交；交换到达顺序后，N8 先可见，随后才是 N256 的低/高部分。
没有出现 `N256-low -> N8 -> N256-high`。所以在当前两个 ready warp、BF16
M128N256 与 M128N8 构造下，tensor backend 至少在 **一条 UTCHMMA 所包含的
N128 wave 之间不可抢占**：仲裁/乱序可以选择下一条指令，但一旦选中 N256，
它会保有后端直到两个物理 wave 均发出/退休。

这解释了长 stream 中多个 warp 的 completion 时间为何非常接近：各 warp 可以
积压多条指令，调度器可在**指令边界**轮转，且共享 mbarrier 会把可见 completion
进一步聚合；它不要求一条指令内部的不同 N128 wave 相互穿插。当前实验仍不能
排除一个 N128 wave 内部各 microtile 的并行执行或乱序退休，只能把跨指令
可抢占边界收紧到“不细于完整 N256 指令”。探针为
`tests/asm_construct/probe_sm100_utchmma_backend_interleave.py`。

#### ready/arrival 仲裁与 warp quantum（2026-09-18）

在上述双 producer 探针中给 warp 0 的 N256 加入可调 `NOP`（每条
`stall=8,yield=1`），并把 `CS2R` 放在延迟之后、紧贴 UTCHMMA 之前。翻转边界
落在 3/4 条 NOP 之间：

| warp 0 延迟 | 两条指令前的 CS2R 次序 | D 可见次序 |
|---:|---|---|
| 3 NOP | N256 比 N8 早 8 cycles | N256-low、N256-high、N8 |
| 4 NOP | N8 比 N256 早 4 cycles | N8、N256-low、N256-high |

只改变 12-cycle 的相对到达关系便使胜者同步翻转；反向延迟 warp 1 时仍由
warp 0 的 N256 先执行。因此第一次选择不是“固定等待低 warp id”，而是从已经
ready 的候选中选择较早到达的队头。对当前两 warp 构造，行为等价于
oldest-ready。

仅凭退休交替，最初看起来整个后端不像一个把所有已发 UTCHMMA 按时间排到底的
全局 FIFO。新的
`probe_sm100_utchmma_warp_quantum.py` 让 warp 0/1 各连续裸发 8 条 M128N8
accumulate，分别写两个私有 D；observer 同时读取两个 D。每条退休使可见值增加
16，因此 `16,32,...,128` 的转换顺序直接给出指令调度顺序，不需要在每条 MMA
之间插入 UTCBAR。

无人工延迟时，两次代表性运行的转换 round 为：

| stream | run 1 | run 2 |
|---|---|---|
| warp 0 / A | `0,3,9,14,20,26,31,37` | `2,5,10,16,22,27,33,39` |
| warp 1 / B | `6,11,17,23,28,34,40,43` | `7,13,19,24,30,36,42,44` |

即初始领先的 A 先完成两条，之后为
`A3,B2,A4,B3,...,A8,B7,B8`。给 A 加 4 条 NOP、使 B 先到后，一次运行从
`B1,A1,B2,A2,...` 开始；另一次 B 在 A ready 前先完成两条，之后仍恢复
`A1,B3,A2,B4,...` 的逐条交替。起始领先量随两个 warp 真正进入 ready 集合的
时刻变化，稳定态 quantum 则是 **一条完整 UTCHMMA**。

随后把 producer 改为可选 warp id，并在每条 UTCHMMA **之前**保存 CS2R：

- 跨 subcore 的 warp 0/1 中，领先 stream 的 8 个时间戳通常全部保持
  **17-cycle** 间隔；另一个 stream 也可连续保持 6--8 条，接近尾部才出现
  39/51/78-cycle backpressure。
- 同 subcore 的 warp 0/4 中，两条 stream 很快共同出现 24/39/48/78/117/156-cycle
  间隔膨胀；即使某个 warp 在源码控制流上更早到达后续 UTCHMMA，也不能像跨
  subcore 那样连续通过入口。
- 把同 subcore 对换成 warp 1/5、令 warp 0 只负责 allocator 后，仍得到
  20/39/53/78/117-cycle 的同类膨胀，排除了 warp 0 身份或 allocator 工作造成
  的特殊相位。

这里必须区分“UTCHMMA 前的 CS2R 已执行”和“UTCHMMA 已 admission”。指令本身
可以停在入口，因此第 `i+1` 个 CS2R 才是第 `i` 条 UTCHMMA 已成功发射的上界。
按这个上界重建后，同 subcore 与跨 subcore 的退休顺序都和实际 admission 的
合并顺序一致；此前看似 backend 对同一 warp 的旧指令进行 round-robin 重排，
实际是这些指令尚未进入 TC queue，而是在各自 warp scheduler 状态中等待入口
credit。

因此当前最小模型修正为：**TC admission 容量按 subcore 共享，而不是每 warp
各有一条可独立灌满的 queue**。同一 subcore 的多个 warp 在上游 scheduler 中
各自保留阻塞指令，竞争该 subcore 的 queue/credit；不同 subcore 可以并行地以
最低 17-cycle 间隔填入各自队列。更下游存在 SM-wide tensor dispatcher，从
四个 subcore 队头取指；一旦选中一条 UTCHMMA，它在完整指令边界之前不可抢占。

实验能定位的是容量与 backpressure 的归属。物理实现仍可能是一个真正的
per-subcore FIFO，也可能是带 warp tag/小型 per-warp 分区、但共用一组 per-subcore
credits 的结构；二者对当前实验等价。可以明确排除的是“每 warp 拥有彼此独立、
可同时填满的 TC admission queue”。

#### admission 容量的短 burst 定量（2026-09-20）

`probe_sm100_utchmma_admission_modal.py` 把每条 UTCHMMA 的静态 stall 从 12
缩到 1，并保留每条指令前的 CS2R。于是第 `i+1` 个时间戳减第 `i` 个时间戳
给出第 i 条 UTCHMMA admission 加随后 CS2R 的上界；无阻塞基线为 7 cycles。
把第二个 producer 延后 32 条 stall-8 NOP 后，领先 producer 的中位间隔为：

| placement | M128N8 | M128N128 |
|---|---|---|
| warp 0/1，跨 subcore | `7,7,7,7,7,7,15` | `7,7,7,7,7,7,15` |
| warp 0/4，同 subcore | `7,7,7,7,8,8,13` | `7,7,7,7,8,8,13` |

前六条按入口基线通过，第七次尝试开始 backpressure；五次重复一致。去掉 observer、
改用 overwrite (`!UPT`) 后边界不变，因此不是 LDTM 观察流量或 accumulator RAW
造成。N8 与 N128 的容量边界相同而后端执行时间明显不同，说明 credit 以完整
UTCHMMA 指令计数，而不是以 N-wave 计数。

因此现有数据把上述定性模型进一步收紧为：**约 6 个可用 UTCHMMA admission
credits/subcore，由该 subcore 的 warps 共享**。这里的 6 仍是 backpressure 所见
的有效容量，不足以区分六槽 FIFO 与等价的分布式 credit 实现。完整 MIO 对照和
原始边界见 `../arch/b200_mio_admission_depth.md`。

探针 bring-up 还暴露出一个独立协议点：`UTCBAR -> mbarrier_wait -> CTA barrier ->`
下一段 UTCHMMA 的构造会不完成；而中途 UTCBAR 不等待、用正确 init count 在尾部
统一等待可以正常运行。中间态实验因此严格使用一个 epoch 和尾部唯一 UTCBAR；
这个跨 completed-epoch 的规则需另行分析，不能再误判成 accumulator residency。

这意味着前文约 493--752 B/cycle 的 tensor+ordinary 数字是**逻辑流量上界**，
不是已证明的 TMEM SRAM 流量。“几乎无端口争用”本身不能区分专用超宽 RMW 口、
多相/高频 TMEM array，以及 TC 内少量 microtile forwarding；完整 D residency
目前没有直接证据。

该次级仲裁近似为每条 64-cycle M128N128 wave 抽走两个普通 service slots：
128 MMA 使普通窗口增加约 258 cycles；duration-matched 的 64-MMA 测试增加约
135--151 cycles（存在普通 warp 份额重分配噪声）。等价候选是 tensor 活跃时
同 chunk 普通 path 约取得 31/32 的 grant。accumulate/overwrite 完全相同，
支持“固定 grant 节拍”而不是按逻辑 accumulator-read 字节收费。

把普通 LDTM 从 STTM 所在 chunk 1 移到 chunk 2 后，普通读写从同-chunk 的
约 8270-cycle 串行窗口恢复为约 4200-cycle 并行窗口；加入 128 条 UTCHMMA
后 LDTM 4168→4169、STTM 4096→4108，MMA 仍为 8321。由此可把模型进一步
收紧为：普通 LDTM/STTM 共用 **每 chunk 一条** 256-B/cycle 双向 path；tensor
RMW 在各 chunk 上基本独立，只在同一 chunk 的普通双向 path 已完全饱和时留下
约 3% 的深层本地仲裁。

### 与 UBLKCP/TMA 的交叉实验

在同一份裸 SASS 生成器中加入 warp 3 的 UBLKCP 流，分别测试 shared→global
的 `UBLKCP.G.S` 和 global→shared 的 `UBLKCP.S.G`。请求大小均为 4 KiB；
G.S 用 `UTMACMDFLUSH + DEPBAR` 关闭完成，S.G 用独立 transaction-counted
mbarrier 关闭。所有请求复用同一个源/目的区间，因此这里测的是稳定仲裁吞吐，
不应解释为大范围顺序地址的 DRAM 带宽。

| workload | UTCHMMA | UBLKCP | ordinary TMEM |
|---|---:|---:|---:|
| 64×G.S only | -- | **8238** | -- |
| 64×G.S + 128×MMA | **8321** | **12288--12349** | -- |
| 192×S.G only | -- | **6541--6569** | -- |
| 192×S.G + 128×MMA | **8321** | **6525--6561** | -- |
| same-chunk duplex + 64×G.S | -- | **8242--8251** | span 约 **8.2k** |
| same-chunk duplex + 192×S.G | -- | **6537--6551** | span 约 **8.2k** |

单独运行时，G.S 的有效速率约为 31.8 B/cycle，S.G 约为 120 B/cycle。
加入 UTCHMMA 后，G.S 的完成时间稳定增加约 50%，而 UTCHMMA 本身逐周期不变；
S.G 与 UTCHMMA 则近乎完全重叠。这与前面的 shared operand 结果吻合：
UTCHMMA 的 gdesc operand fetch 与 TMA shared→global 都消耗 shared-array **读侧**
服务，并且 tensor 请求优先；TMA global→shared 使用写侧入口，未与 tensor
operand read 形成相同冲突。

这个 50% 不是模糊的平均值：以 G.S-only 的 8238-cycle 工作量计，combined
中 MMA 占据前 8321 cycles，随后 G.S 还需约 `12349-8321=4028` cycles；故
MMA 活跃窗口内 G.S 完成的等效工作为 `8238-4028=4210` cycles，服务率恰为
baseline 的 `4210/8321=50.6%`。最简单模型是 tensor wave 连续活跃时，
shared-read arbiter 只给 UBLKCP.G.S 约一半 grant；这不是总字节带宽自然饱和，
因为 G.S 自身仅约 32 B/cycle，而更像入口按 client/beat 固定分时。

更关键的是，两种 UBLKCP 方向都不改变同 chunk LDTM+STTM 的约 8.2k-cycle
普通 TMEM 双工窗口；反过来普通 TMEM 流也不改变 UBLKCP 的完成时间。四者同时
运行（MMA + LDTM + STTM + UBLKCP）时，周期数可由上述两两效应组合解释：
MMA 仍为 8321，G.S 仍约 12.3k / S.G 仍约 6.54k，普通 TMEM 与无 UBLKCP
的 MMA+duplex 控制落在相同的约 8.5k 稳态簇。因而 UBLKCP 不经过每-chunk
256-B/cycle 的普通 TMEM 双向 path；它位于 shared/TMA 侧，和 TMEM 普通端口
只在更上游的 warp/UDP admission 或更下游的 shared-array 仲裁处可能相遇。

### Shared-memory operand 端

逻辑上，每个 M128xN128xK16 BF16 MMA 需要 A=4 KiB、B=4 KiB。若每条都
重新取数，则 64-cycle wave 对应 **128 B/cycle/SM** 的 operand payload；
若 collector 确实保留 A，稳态只需 B 的 **64 B/cycle/SM**。但是目前的
仲裁实验表明，不能把这些逻辑字节数直接解释成普通 LDS datapath 的占用：

- 一个独立、无 bank conflict、每轮八条 independent LDS 的 warp，单独运行
  8,192 条需 24,638 cycles；
- 与 M128N128 UTCHMMA 并行时需 29,114 cycles，增加 4,476 cycles，约
  **8.7 cycles/MMA**；A collector reuse 时增加约 4,207 cycles；
- N8 的增加量约 4,126 cycles，和 N128 很接近；
- N256 的 UTCHMMA 时间翻倍到约 65,776 cycles，但同一段 LDS 仍为
  29,114 cycles（A-reuse 为 28,941），与 N128 几乎相同；
- UTCHMMA 自身时间在所有混合实验中不变。

这说明 tensor operand fetch 对 LDS 有优先级，并在 shared-memory array
入口或其附近发生仲裁。连续饱和 UTCHMMA 时，LDS 的相对服务率约为
`24638/29114 = 84.6%`，即 tensor 通路占用或阻塞约 **15.4%** 的 shared
服务机会。N256 在 LDS 测量窗口内执行的 MMA 指令数约减半但内部 wave 数
不变，而 LDS 时间也不变；所以仲裁更像由连续的内部 compute wave 按固定
duty cycle 取得 shared grant，而不是“每条 UTCHMMA 固定阻塞若干周期”。

另一方面，N8 与 N128、plain 与 A-reuse 的标量-LDS 干扰都接近；单凭该
探针还不能证明较小 N 是否少读 B，或 collector 是否真的省去 shared-array
读取。下面的 LDS.128/A-from-TMEM 对照解决了其中的 A/collector 问题；B
流量仍需更饱和的 occupancy meter 才能定量。

#### LDS.128 与 A-from-TMEM 判别

上面的标量 LDS 流仍受自身发射/late-RF 路径限制。改用四条 independent
`LDS.128` 的展开体后，每条产生四个无 bank-conflict shared wavefront；取
2,048 条使总 payload 仍为 1 MiB，并以相同的 128-thread launch 对照：

| workload | LDS.128 流周期 | 相对 baseline |
|---|---:|---:|
| LDS.128 only | 20,036 | -- |
| gdesc A UTCHMMA + LDS.128 | 20,765 | +729 |
| gdesc A、collector fill/use/lastuse + LDS.128 | 20,162 | +126 |
| TMEM A UTCHMMA + LDS.128 | 20,075 | +39 |

四种情况下 UTCHMMA 自身均保持约 34.45k cycles。A-from-TMEM 的 A tile
先由四个 warp 用 STTM.x8 填入四个 32-row TMEM chunk；overwrite MMA 后
LDTM 读回 `0x41800000`（16.0f），确认 `32x16` BF16 A 布局和 opcode
0x19ea 路径正确，而不只是一个未 fault 的错误 descriptor。

这个对照给出两个比标量 LDS 清楚得多的结论：

1. gdesc 形式确实反复使用 shared-array 的 A 读取服务；将 A 搬到 TMEM
   后，LDS.128 干扰几乎完全消失。
2. `.collector::a::fill/use/lastuse` 也几乎达到 A-from-TMEM 的效果，证明
   collector 命中会省掉后续 shared A 读取，而不只是减少某种前端开销。

因此候选模型中的每-subcore `32x16` lhs tile 以及总计 4-KiB A tile 获得了
直接的端口竞争支持。剩余约 +39/+126 cycles 太小，当前单 warp LDS.128
仍不足以把 B 广播流量定量还原为 32 个 wavefront；要像 Hopper 一样做精确
逐-wavefront 计账，还需要多个 contender warp。

后续独立基准已确认 B200 与 Hopper 一样：单 LDS.128 流只能提供约 0.526
wavefront/cycle，四 subcore 才达到约 1.01 aggregate wavefront/cycle；详见
`../arch/b200_lsu_exchange_topology.md`。因此本节单 contender 的差值只能作
端口投影，不能视作 shared data stage 的饱和带宽占用。

#### 四 contender 饱和实验

工具链补齐后，`probe_sm100_utchmma_lds_saturation.py` 从零生成 V1
entry-fragment、512-column TMEM allocator、mbarrier 和 payload；执行路径不再
依赖 patch/lift nvcc cubin。warp 0 发射 UTCHMMA，warps 1--4 按 `warp_id % 4`
覆盖四个 subcore。每个 LDS warp 静态展开 36 条 `LDS.128`，每三条分别 claim
SB0--SB2 后显式等待，故不存在 destination 过早复用或未关闭请求。

短窗口使用 4 条 M128N128K16 BF16/BF16→F32 overwrite UTCHMMA，分成两个
2-MMA completion group；两组使用两个预先初始化的独立 mbarrier。结果为：

| workload | MMA cycles | LDS warp cycles | common span |
|---|---:|---:|---:|
| LDS-only | -- | 615 / 619 / 639 / 627 | **643** |
| UTCHMMA-only | **627--629** | -- | 627--629 |
| combined | **642--647** | 876 / 880 / 902 / 890 | **906** |

LDS-only 共包含 `4 warps × 36 instructions × 4 wavefronts = 576` 个 128-B
wavefront。加入 4 条 UTCHMMA 后，LDS 公共窗口增加 `906-643=263` cycles，
即 **65.75 cycles/UTCHMMA**。而一个 M128N128K16 BF16 操作数对正好需要：

```
A: 128 × 16 × 2 B = 4096 B = 32 wavefront
B:  16 × 128 × 2 B = 4096 B = 32 wavefront
合计                            64 wavefront
```

测得增量与 64 个 128-B operand wavefront 几乎逐一对应。这直接证明 gdesc A/B
读取和普通 LDS.128 共用约 **1×128 B/cycle** 的 SM-wide shared read data
stage。仲裁明显偏向 tensor 请求：combined 中 MMA 只增加约 13--18 cycles，
而普通 LDS 承担约 263-cycle 延迟。

旧手写版的短序列故障现在已确认是 PTX 兼容 wrapper 的误用以及 mbarrier
arrival 计数不匹配造成的人工现象，而不是 completion-window 深度。裸 U-path
长流可直接工作，不需要 ELECT/PLOP/retry wrapper。上述短窗口中测得的
64-wavefront 增量仍可作为 operand 端口流量的候选证据，但 MMA-only 的
627--629 cycle 时间不应再解读为正常发射时间；后续 shared-port 定量实验应以
裸 UTCHMMA、裸 UTCBAR 和正确的 barrier init count 复测。

同等 1-MiB payload 的 STS.128（无 destination RF writeback）给出了不同的
端口投影：

| workload | STS.128 流周期 | 相对 baseline |
|---|---:|---:|
| STS.128 only | 20,505 | -- |
| gdesc A UTCHMMA + STS.128 | 24,082 | +3,577 |
| gdesc A、collector reuse + STS.128 | 24,082 | +3,577 |
| TMEM A UTCHMMA + STS.128 | 24,082 | +3,577 |

三种形式逐周期相同，STS 的相对服务率为 `20505/24082 = 85.15%`，即连续
UTCHMMA 固定占用或阻塞约 **14.85%** 的写侧服务机会。Blackwell 的 STS
因此不像 Hopper STS occupancy meter 那样直接报告 A+B operand wavefront
总数；移除 32 个 A wavefront 并不改变其时间。

LDS.128 与 STS.128 的组合仍支持 Hopper 式“A 分发、B 广播”的数据流，但
新的四-contender 结果约束了后端：无论 A/B 在 tensor 专用网络中如何分发，
两者从 shared array 取出的 32+32 个 wavefront 都投影到普通 LDS 可见的同一
条约 128-B/cycle read data stage。A collector 命中或 A-from-TMEM 会消掉 A
的 32 个读取 wavefront；旧单-contender 对 B-only 不敏感，是 occupancy meter
未饱和，而不是 B 绕过 shared read service。STS 所见的固定 duty-cycle 压制
则仍可能发生在更靠近 shared array 读写入口的另一层仲裁。

A-from-TMEM（shared 侧只剩 B）的 N sweep 进一步得到：

| N | MMA cycles / 512 | LDS.128 cycles | STS.128 cycles |
|---:|---:|---:|---:|
| contender only | -- | 20,036 | 20,505 |
| 8 | 34,453 | 20,049 | 24,082 |
| 128 | 34,453 | 20,075 | 24,082 |
| 256 | 约 65,791 | 20,235 | 24,082 |

B-only 对单 LDS stream 留下很弱但随 N 增大的干扰；STS 则对
N8/N128/N256 给出完全相同的 24,082 cycles。N256 每条含两个内部 N128
wave，但在同样长度的 contender 窗口内仍是连续 tensor wave，故固定
duty-cycle 模型预言其 STS 服务率与 N8/N128 相同，实测正是如此。较小 N
是否只读取逻辑 B 列仍不能从这个低灵敏度差值精确计数；四-contender 饱和
实验已经取代了这里原先对 B read-path 拆分的弱推断。

## Cross-references
- `notes/sm100/instr/utccp.md` — stages A/B matrices shmem→TMEM; shares the
  `UMMAA`/`UMMAB` 64-bit matrix-descriptor operand type.
- `notes/sm100/instr/ldtm.md` / `sttm.md` — move the D accumulator between TMEM
  and registers.
- `notes/sm100/instr/utcbar.md` — `tcgen05.commit`; commits UTCHMMA completion to
  an mbarrier.
- `notes/sm90/arch/wgmma.md`, `notes/sm90/arch/tcgen05_vs_wgmma.md` — the Hopper
  predecessor (HGMMA) and the microarch shift to TMEM/warp-scalar issue.
- Sibling MMAs (TODO): `UTCIMMA` (int), `UTCQMMA` (FP8), `UTCMXQMMA` (MX-scaled),
  `UTCOMMA`.

## Latency (sm100_latencies.txt)
`UTCHMMA` is a `TCMMA_OPS` / tensor-core async op (excluded from `UDP_subset`
fixed latency). Completion is mbarrier/scoreboard-tracked, not a fixed
latency-table cycle.

## Open questions
- Full 64-bit `UMMAA`/`UMMAB` matrix-descriptor + 32-bit `idesc` bit layouts —
  **documented** in `notes/sm100/arch/tcgen05_descriptors.md` (from PTX Tables
  43/45–47). Remaining: confirm the built-descriptor field placement against real
  descriptor-construction SASS.
- `tmemE` (URe) role — secondary accumulator/scale operand? (`ISRC_E_SIZE=64`.)
- `opType` [73:72]∥[63] is pinned 0 here — what selects nonzero values?
- Weight-stationary (`.WS`) + collector-buffer runtime semantics；尤其需要把
  collector 命中与 shared-array 实际读流量分离测量。
