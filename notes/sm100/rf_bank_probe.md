# B200 寄存器文件 bank 与读取带宽探测

**状态：** Modal B200 实测，2026-09-17。
**探针：** `tests/asm_construct/probe_sm100_rf_banks_modal.py`。

## 结论

B200 的 scalar GPR operand collector 暴露出的冲突域仍由寄存器编号奇偶
决定，而不是 `register % 4`：

- 可见 bank 数为 2：even / odd；
- 每个 bank 每周期至少能收集 2 个独立的 warp-wide 32-bit register row；
- 第 3 个同奇偶源需要额外一个周期；
- 没有观察到能独立服务 `0 mod 4` 与 `2 mod 4`（或 `1` 与 `3`）的四 bank
  行为。

因此，若“B200 RF 是 4 bank”指的是四个由低两位选择、可独立接受 row
address 的性能 bank，本实验直接反证了该说法。内部当然仍可能物理分片为
四块甚至更多 SRAM，但若它们在共同 row decoder、collector 或端口仲裁之后
只呈现两个奇偶冲突域，就不能在 cycle-accurate simulator 中建模成四个独立
bank。

## 测量方法

所有 timed instruction 使用最小普通调度控制
`[7:7:{}:1:0:1]`（stall 1、yield 0、batch_t 1）。`stall=0` 是 DRAIN，
不能表示零等待。每项分别展开 128/256/512 条，用
`cycles = slope * instruction_count + intercept` 拟合斜率；每个 kernel
重复七次并取最小值。目的寄存器为 `RZ`，排除普通 GPR writeback。

### 两源矩阵

FADD 对 Ra/Rb 的低两位做完整 4x4 扫描，同 residue 时使用相差 4 的不同
物理寄存器，避免同源广播或消除。16 个组合全部为：

```text
FADD:  1.000 cycle/instruction
NOP:   1.000 cycle/instruction
```

这说明两个同奇偶源本身不冲突，即每个可见 bank 至少 2R。HADD2 的所有
组合均为 2.000，但它对低位完全不敏感，且符合 packed-FP 管线自身的 admission
上限，不能拿它判断 bank 数。

### 三源 FFMA 判别

关键是比较三个偶数源在 mod-4 上的不同分布：

```text
source residues / parity       cycles/instruction
(0,1,2) = even,odd,even              1.000
(0,2,0), all permutations             2.000
(0,2,2), all permutations             2.000
(0,0,0)                               2.000
(2,2,2)                               2.000
odd-side equivalents                  2.000
```

在 `2 bank x 2R` 模型中，第一项对 even/odd 的需求为 2+1，单周期完成；
其余项把三个读取全压到一个奇偶 bank，需两周期，与结果严格相符。

若是四个独立的 mod-4 bank 且每 bank 至少 2R，`(0,2,0)` 只是 2+1 分布，
应与 `(0,1,2)` 一样单周期；实测却与 `(0,0,0)` 完全相同。operand position
的全部排列结果一致，也排除了 A/B/C collector 端口不对称造成的假象。

## FFMA2 / `fma.f32x2`

`FFMA2.F32x2.F32x2.F32x2` 一次读取三个偶数对齐的 64-bit register pair；
每个 pair 天然包含一行 even 和一行 odd。三个 pair 因而分别向两个可见 bank
提出三个 row read。所有 pair 起始 residue 布局均为 2.000 cycles/instruction：

```text
all starts 0 mod 4     2.000
all starts 2 mod 4     2.000
every 2+1 permutation  2.000
```

这与每个奇偶 bank 每周期服务两个 row、第二周期服务第三个 row 的模型吻合，
也再次没有暴露任何 mod-4 优势。FFMA2 的结果同时说明其 2-cycle 吞吐可以由
RF collection 需求解释；仅凭当前实验尚不能排除 fmalighter pipe 自身也有相同
的两周期 admission 限制。

## 建模建议

当前最小、与全部结果一致的读侧模型是：

```text
bank = register_number & 1
read_cycles = max(ceil(even_rows / 2), ceil(odd_rows / 2))
```

其中 row 是一条 warp-wide 32-bit GPR operand；64-bit pair 计作相邻的一奇一偶
两个 row。这个公式描述 collector 可见带宽，不声称 SRAM 宏单元的物理数量。
writeback bank/port 数量也不能从本实验推出，需要独立的 completion/writeback
碰撞实验。
