# B200 寄存器文件 bank 与读取带宽探测

**状态：** Modal B200 实测，2026-09-17。
**探针：** `tests/asm_construct/probe_sm100_rf_banks_modal.py`。

## 结论

B200 的 scalar GPR operand collector 暴露出的冲突域仍由寄存器编号奇偶
决定，而不是 `register % 4`：

- 可见 bank 数为 2：even / odd；
- 每个 bank 每周期只能收集 1 个独立的 warp-wide 32-bit register row；
- 同一奇偶 bank 的 N 个未复用源需要 N 个 collection cycle；
- 没有观察到能独立服务 `0 mod 4` 与 `2 mod 4`（或 `1` 与 `3`）的四 bank
  行为。

因此，若“B200 RF 是 4 bank”指的是四个由低两位选择、可独立接受 row
address 的性能 bank，本实验直接反证了该说法。内部当然仍可能物理分片为
四块甚至更多 SRAM，但若它们在共同 row decoder、collector 或端口仲裁之后
只呈现两个奇偶冲突域，就不能在 cycle-accurate simulator 中建模成四个独立
bank。

## 测量方法

所有 no-reuse timed instruction 使用最小普通调度控制
`[7:7:{}:1:0]`（stall 1、yield 0）。`stall=0` 是 DRAIN，不能表示零等待。
对于有 reusable source 的 math class，第六字段并不是普通 batch tag，而是
reuse bitmask：bit 0/1/2 分别表示 source A/B/C。因而 `:1:0:1` 是
reuse-A，不能作为 no-reuse control。每项分别展开 128/256/512 条，用
`cycles = slope * instruction_count + intercept` 拟合斜率；每个 kernel
重复七次并取最小值。目的寄存器为 `RZ`，排除普通 GPR writeback。

### 两源 FADD 与 reuse

真正的 no-reuse 对照为：

```text
FADD 2E, no reuse       2.000 cycles/instruction
FADD 2E, reuse A        1.000
FADD 1E+1O, no reuse    1.000
NOP                     1.000
```

这直接证明两个同奇偶源不能同周期读取，而 reuse cache 消除其中一个实际 RF
request 后立即恢复前端 1-cycle floor。B200 每个可见 bank 因而是有效 1R，
与 GB202 相同。HADD2 固定约 2-cycle 的 packed-FP admission floor 会隐藏这一
差异，不能单独拿它判断 bank 数。

### 三源 FFMA 判别

关键是比较三个偶数源在 mod-4 上的不同分布：

```text
source residues / parity       cycles/instruction
(0,1,2) = even,odd,even              2.000
(0,2,0), all permutations             3.000
(0,2,2), all permutations             3.000
(0,0,0)                               3.000
(2,2,2)                               3.000
odd-side equivalents                  3.000
```

在 `2 bank x 1R` 模型中，第一项对 even/odd 的需求为 2+1，需两周期；
其余项把三个读取全压到一个奇偶 bank，需三周期，与结果严格相符。

若是四个独立的 mod-4 1R bank，`(0,2,0)` 只是 2+1 分布，应为两周期；
实测却与 `(0,0,0)` 一样为三周期。operand position 的全部排列结果一致，
也排除了 A/B/C collector 端口不对称造成的假象。

显式 reuse sweep 给出逐行下降：

```text
FFMA 3E:       no reuse 3, reuse any one 2, reuse two/all 1
FFMA 2E+1O:    no reuse 2, reuse one E 1, reuse O 2
```

第二行尤其重要：reuse odd 后剩余 2E，仍需两周期；reuse even 后剩余 E+O，
降为一周期。效果完全由剩余源的奇偶计数决定。

## HFMA2

HFMA2 每个 packed-FP16 source 仍只读取一条 32-bit GPR row，但指令自身有
固定的约 2-cycle service floor。显式 no-reuse/reuse sweep 为：

```text
HFMA2 3E:       no reuse 3, reuse one 2, reuse two/all 2
HFMA2 2E+1O:    no reuse 2, reuse any tested source 2
```

因此其 collector-visible floor 是：

```text
HFMA2 cycles/instruction = max(2, even_rows, odd_rows)
```

普通 2E+1O 即使完全不 reuse，也被固有 2-cycle pipe floor 遮住；只有三个
未复用 source 全落在同一奇偶 bank 时才真正 RF-bound，从 0.5
instruction/cycle 降到约 1/3。任意命中一个 source reuse 即把 3E/3O 降回
两行请求和正常 0.5 instruction/cycle。

## FFMA2 / `fma.f32x2`

`FFMA2.F32x2.F32x2.F32x2` 一次读取三个偶数对齐的 64-bit register pair；
每个 pair 天然包含一行 even 和一行 odd。三个 pair 因而分别向两个可见 bank
提出三个 row read。真正 no-reuse 时，所有 pair 起始 residue 布局均为
3.000 cycles/instruction：

```text
all starts 0 mod 4     3.000
all starts 2 mod 4     3.000
every 2+1 permutation  3.000
```

如果是四个独立的 mod-4 1R bank，2+1 pair-start 布局对各 mod-4 bank 的最大
需求只有 2，应该降到两周期；实测保持三周期，再次确认冲突域只看奇偶。

reuse-A 消除一个 64-bit pair 后由 3.000 降到 2.000。继续 reuse 两个或三个
pair 仍是 2.000，说明 FFMA2 还有独立的约 0.5-inst/cycle pipe/admission floor；
这不影响 no-reuse 与 reuse-one 对 RF 第三个 row cost 的判别。

## 建模建议

当前最小、与全部结果一致的读侧模型是：

```text
bank = register_number & 1
read_cycles = max(even_rows, odd_rows)
instruction_cycles = max(pipe_admission_floor, read_cycles)
```

其中 row 是一条 warp-wide 32-bit GPR operand；64-bit pair 计作相邻的一奇一偶
两个 row，命中 reuse cache 的 operand 不产生 RF row request。FFMA2 的
`pipe_admission_floor` 约为 2，普通 FP32 FADD/FFMA 在本测试中约为 1。

这个公式描述 collector 可见带宽，不声称 SRAM 宏单元的物理数量。writeback
bank/port 数量也不能从本实验推出，需要独立的 completion/writeback 碰撞实验。

## 更正记录

首轮结果误用了 `[...:1:0:1]`，将第六字段当作普通 batch tag；它实际打开
reuse-A，因而得到 FADD 全部 1 cycle、FFMA 2E+1O 为 1 cycle、FFMA2 为
2 cycles 的假象，并被错误解释为 2R。显式 no-reuse/reuse 对照发现并纠正了
这个问题；本文以上数字均来自修正后的编码。
